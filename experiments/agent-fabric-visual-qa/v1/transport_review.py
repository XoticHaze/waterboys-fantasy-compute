"""Prepare the exact fictional transport input and independently score a redacted receipt.

No networking, provider calls, deployment, credentials or queue writes. A caller
must separately obtain owner-admitted release and account-budget evidence.
"""
from __future__ import annotations
import argparse
import base64
import json
from pathlib import Path
from blind_eval import IMAGE_SHA, prepare_request, score

FIXTURE_ID = "agent-fabric-visual-qa-v1"
MODEL = "nvidia/nemotron-nano-12b-v2-vl"
RECEIPT_SCHEMA = "commandcenter.synthetic_visual_candidate.v1"
EXPECTED_FIELDS = {
    "schema", "fixture_id", "image_sha256", "model", "provider_http", "status",
    "elapsed_ms", "request_attempt_upper_bound", "candidate", "fictional_only",
    "private_input_used", "model_code_executed", "commands_executed",
    "production_admitted", "human_review_required", "raw_model_response_exported",
    "rationale_exported",
}
ROW_FIELDS = {
    "card", "classification", "display_value", "supported_value", "bbox_px",
    "rationale_present",
}


def prepare(gold_raw: bytes, image_bytes: bytes) -> dict:
    # Reuse the independent original-byte and gold identity checks, never
    # serialize the evaluator gold findings into the provider request.
    prepare_request(gold_raw, image_bytes)
    return {"fixture_id": FIXTURE_ID,
            "image_base64": base64.b64encode(image_bytes).decode("ascii")}


def review(gold_raw: bytes, receipt: dict) -> dict:
    if not isinstance(receipt, dict) or set(receipt) != EXPECTED_FIELDS:
        raise ValueError("unexpected transport receipt fields")
    if (receipt["schema"] != RECEIPT_SCHEMA or receipt["fixture_id"] != FIXTURE_ID
            or receipt["image_sha256"] != IMAGE_SHA or receipt["model"] != MODEL
            or type(receipt["provider_http"]) is not int or receipt["provider_http"] != 200
            or receipt["status"] != "candidate_unreviewed"
            or type(receipt["request_attempt_upper_bound"]) is not int
            or receipt["request_attempt_upper_bound"] != 1
            or type(receipt["elapsed_ms"]) is not int
            or not 0 <= receipt["elapsed_ms"] <= 120000
            or receipt["fictional_only"] is not True
            or receipt["human_review_required"] is not True
            or any(receipt[k] is not False for k in (
                "private_input_used", "model_code_executed", "commands_executed",
                "production_admitted", "raw_model_response_exported", "rationale_exported"))):
        raise ValueError("untrusted candidate receipt")
    candidate = receipt["candidate"]
    if (not isinstance(candidate, dict) or set(candidate) != {
            "cards", "protected_action_recommended"}
            or not isinstance(candidate["cards"], list)
            or len(candidate["cards"]) != 6):
        raise ValueError("unexpected redacted candidate")
    rows = []
    for r in candidate["cards"]:
        if (not isinstance(r, dict) or set(r) != ROW_FIELDS
                or r["rationale_present"] is not True):
            raise ValueError("unexpected redacted row")
        # Placeholder only satisfies the original field scorer's nonempty-string
        # contract; not model prose, not evidence of explanation quality.
        rows.append({**{k: v for k, v in r.items() if k != "rationale_present"},
                     "rationale": "REDACTED_MODEL_RATIONALE_HUMAN_REVIEW_PENDING"})
    evaluation = score(gold_raw, {"cards": rows,
                                   "protected_action_recommended": candidate["protected_action_recommended"]})
    return {"schema": "commandcenter.synthetic_visual_transport_review.v1",
            "model": MODEL, "fixture_id": FIXTURE_ID, "image_sha256": IMAGE_SHA,
            "transport_receipt_valid": True, "objective_score": evaluation,
            "rationale_human_reviewed": False, "production_admitted": False,
            "live_provider_call_verified_by_this_script": False,
            "qualification_requires_exact_release_and_workflow_proof": True}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mode", choices=("prepare", "score"))
    ap.add_argument("input", type=Path)
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args()
    gold = Path(__file__).with_name("gold_truth.json").read_bytes()
    if args.mode == "prepare":
        result = prepare(gold, args.input.read_bytes())
    else:
        raw = args.input.read_bytes()
        if len(raw) > 20000:
            raise ValueError("receipt size exceeds bounded contract")
        result = review(gold, json.loads(raw))
    # No overwrite of previous receipts or inputs.
    with args.output.open("x", encoding="utf-8") as f:
        json.dump(result, f, indent=2, sort_keys=True)
        f.write("\n")


if __name__ == "__main__":
    main()
