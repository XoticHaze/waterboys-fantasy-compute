#!/usr/bin/env python3
"""Replay a fixed, public-fictional model artifact with the incumbent AST interpreter.

This validator never compiles, imports, executes, or evals the model output.
Its only admissible input is the source-pinned five-function candidate next to it.
"""
from __future__ import annotations

import ast
import hashlib
import json
import sys
from pathlib import Path

ARTIFACT_DIR = Path(__file__).resolve().parent
ROOT = ARTIFACT_DIR.parents[1]
SOURCE = ARTIFACT_DIR / "model_generated_functions.py"
SOURCE_SHA256 = "65411e83e826bd039729c381e9b895d8ad83f3f954ee14b01d72122a369f6ac0"
RUN_ID = 44499189813
JOB_ID = 135474137996
MODEL = "poolside/laguna-xs-2.1"
PINNED_WORKER_SOURCE = "abd8fcac5299aaf5308e831db6a1fcfcd5066898"
EXPECTED_NAMES = (
    "retry_delay_ms", "clamp_window", "budget_remaining",
    "allocation_limit", "staleness_status",
)


def verify(candidate: bytes | None = None) -> dict[str, object]:
    """Return a human-readable, non-promoting receipt after 150 AST checks.

    Passing source integrity is not equivalent to independently authenticating
    GitHub job identity. Provenance is read back separately from the originating
    public GitHub job and linked in the README; no token is required here.
    """
    data = SOURCE.read_bytes() if candidate is None else candidate
    if not isinstance(data, bytes) or hashlib.sha256(data).hexdigest() != SOURCE_SHA256:
        raise ValueError("ARTIFACT_SOURCE_HASH_MISMATCH")
    try:
        source = data.decode("utf-8", errors="strict")
        tree = ast.parse(source, filename="model_generated_functions.py", mode="exec")
    except (UnicodeDecodeError, SyntaxError) as exc:
        raise ValueError("ARTIFACT_SOURCE_NOT_REVIEWABLE") from exc
    if len(tree.body) != 5 or any(type(n) is not ast.FunctionDef for n in tree.body):
        raise ValueError("ARTIFACT_UNEXPECTED_TOP_LEVEL_CODE")
    if tuple(n.name for n in tree.body) != EXPECTED_NAMES:
        raise ValueError("ARTIFACT_FUNCTION_IDENTITY_MISMATCH")

    # Existing approved source-only interpreter and hidden fixtures. The
    # evaluated Python code is *data*, never an imported module or executable.
    sys.path.insert(0, str(ROOT / "scripts"))
    from nvidia_fixed_code_repair_work import CodeRejected, evaluate
    from nvidia_role_code_matrix import TASKS, cases_for

    rows: list[dict[str, object]] = []
    for i, node in enumerate(tree.body):
        task_id, function_name, arguments = TASKS[i]
        assert node.name == function_name
        one_function = ast.get_source_segment(source, node)
        if not isinstance(one_function, str):
            raise ValueError("ARTIFACT_MISSING_SOURCE_SECTION")
        try:
            grade = evaluate(one_function, function_name=function_name,
                             args=arguments, cases=cases_for(i))
        except (CodeRejected, ValueError, TypeError) as exc:
            raise ValueError("ARTIFACT_AST_REJECTED") from exc
        rows.append({"task_id": task_id, "checks_passed": grade["passed"],
                     "checks_total": grade["total"], "pass": grade["all_passed"]})

    success = len(rows) == 5 and all(x["pass"] for x in rows)
    return {
        "schema": "commandcenter.public_synthetic_agent_artifact_review.v1",
        "artifact": "five_reviewable_pure_python_functions",
        "status": "static_accepted" if success else "static_rejected",
        "source_sha256": SOURCE_SHA256,
        "origin_run_id": RUN_ID,
        "origin_job_id": JOB_ID,
        "model": MODEL,
        "worker_source_sha": PINNED_WORKER_SOURCE,
        "functions": rows,
        "checks_passed": sum(x["checks_passed"] for x in rows),
        "checks_total": sum(x["checks_total"] for x in rows),
        "source_code_executed": False,
        "source_imported": False,
        "production_admitted": False,
        "commands_executed": False,
        "independent_git_log_identity_authenticated_by_this_script": False,
    }


def main() -> int:
    try:
        result = verify()
    except ValueError as exc:
        print("AGENT_ARTIFACT_REJECTED=" + str(exc))
        return 1
    print("AGENT_ARTIFACT_REVIEW=" + json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["status"] == "static_accepted" else 1


if __name__ == "__main__":
    raise SystemExit(main())
