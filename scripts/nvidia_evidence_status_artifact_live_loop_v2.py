#!/usr/bin/env python3
"""Versioned V2 synthetic correction controller.

Only the existing fixed loopback caller is used. The 26 diagnostic cases may
inform one revision; neither independent holdout supplies provider input.
No model source execution or operational authority.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from nvidia_agent_feedback_capsule import translate, provider_feedback_v2
from nvidia_evidence_status_artifact_live_loop import MODEL, call, classify
from nvidia_evidence_status_holdout_v2 import compare_holdout_v2, score_holdout_v2

SCHEMA = "commandcenter.public_synthetic_evidence_status_review.v2"
ROOT = Path("artifacts/nvidia-evidence-status-v2")


def evaluate_pair(first, second):
    legacy = classify(first, second)
    balanced = compare_holdout_v2(first, second)
    # A model must improve independent balanced cases and preserve previously
    # correct behavior across BOTH evaluation profiles.
    qualifies = (
        balanced["outcome"] == "HOLDOUT_V2_IMPROVED_NO_REGRESSION"
        and legacy["baseline"]["source_ast_admitted"]
        and legacy["revised"] is not None
        and legacy["revised"]["source_ast_admitted"]
        and legacy["regressions_count"] == 0
    )
    if not legacy["baseline"]["source_ast_admitted"] or not balanced["baseline"]["ast_admitted"]:
        outcome = "BASELINE_STRUCTURE_REJECTED"
    elif second is None:
        if legacy["baseline"]["passed"] == legacy["baseline"]["total"] and balanced["baseline"]["passed"] == balanced["baseline"]["total"]:
            outcome = "FIRST_DRAFT_PASSED_NO_CORRECTION"
        else:
            outcome = "REVISION_UNAVAILABLE"
    elif not legacy["revised"]["source_ast_admitted"] or not balanced["revised"]["ast_admitted"]:
        outcome = "REVISION_STRUCTURE_REJECTED"
    elif legacy["regressions_count"] or balanced["regressed_count"]:
        outcome = "REGRESSED_REJECTED"
    elif qualifies:
        outcome = "INDEPENDENT_HOLDOUT_IMPROVED_NO_REGRESSION"
    elif first == second:
        outcome = "IDENTICAL_SOURCE_NOT_SELF_CORRECTION"
    else:
        outcome = "NO_MEASURED_INDEPENDENT_GAIN"
    return {"legacy_v1": legacy, "balanced_v2": balanced,
            "outcome": outcome, "correction_qualified": qualifies}


def run_pair(caller=call):
    attempts = 1
    confirmed = 0
    first = second = None
    stop = None
    try:
        first = caller({"stage": 0})
        confirmed += 1
    except (RuntimeError, ValueError):
        stop = "BASELINE_REPLY_UNAVAILABLE"
    if first is not None:
        capsule = translate(first)
        balanced = score_holdout_v2(first)
        if not capsule["ast_admitted"] or not balanced["ast_admitted"]:
            stop = "BASELINE_STRUCTURE_REJECTED"
        elif capsule["failing_examples"]:
            payload = provider_feedback_v2(first)
            attempts += 1
            try:
                second = caller(payload, feedback_v2=True)
                confirmed += 1
            except (RuntimeError, ValueError):
                # A failed receipt is not proof that the provider was never
                # called. Never retry and retain the baseline artifact.
                stop = "REVISION_REPLY_UNAVAILABLE"
        elif capsule["tests_passed"] < capsule["tests_total"] or balanced["passed"] < balanced["total"]:
            stop = "HOLDOUT_ONLY_FAILURE_NO_DIAGNOSTIC_FEEDBACK"
        else:
            stop = "FIRST_DRAFT_PASSED_NO_CORRECTION"
    result = evaluate_pair(first, second) if first is not None else {
        "legacy_v1": None, "balanced_v2": None,
        "outcome": "BASELINE_REPLY_UNAVAILABLE", "correction_qualified": False}
    result.update({
        "schema": SCHEMA, "model": MODEL, "feedback_protocol": "observed_vs_expected_v2",
        "workflow_run_id": os.environ.get("GITHUB_RUN_ID"),
        "controller_sha": os.environ.get("GITHUB_SHA"),
        "reviewed_source_sha": os.environ.get("EVIDENCE_STATUS_SOURCE_SHA"),
        "request_attempt_upper_bound": attempts,
        "confirmed_provider_candidate_replies": confirmed,
        "provider_call_count_exact": attempts if attempts == confirmed else None,
        "stop_reason": stop,
        "baseline_sha256": hashlib.sha256(first.encode()).hexdigest() if first is not None else None,
        "revised_sha256": hashlib.sha256(second.encode()).hexdigest() if second is not None else None,
        "holdout_case_details_disclosed_to_provider": False,
        "fictional_only": True, "private_input_used": False,
        "model_code_executed": False, "commands_executed": False,
        "production_admitted": False,
    })
    return first, second, result


def persist(first, second, result, root=ROOT):
    # Refuse stale artifacts or an accidental replay into a prior directory.
    root.mkdir(parents=True, exist_ok=False)
    if first is not None:
        (root / "baseline_model.py").write_text(first, encoding="utf-8")
    if second is not None:
        (root / "revised_model.py").write_text(second, encoding="utf-8")
    (root / "evaluation.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main():
    # The protected live workflow must set this explicitly. A plain invocation
    # is not a new provider admission or an implicit V1 fallback.
    if os.environ.get("NVIDIA_EVIDENCE_FEEDBACK_PROTOCOL") != "v2":
        raise SystemExit("EXPLICIT_V2_PROTOCOL_REQUIRED")
    first, second, result = run_pair()
    persist(first, second, result)
    print("EVIDENCE_STATUS_V2_OUTCOME=" + result["outcome"], flush=True)
    if result["stop_reason"] in {"BASELINE_REPLY_UNAVAILABLE", "REVISION_REPLY_UNAVAILABLE"}:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
