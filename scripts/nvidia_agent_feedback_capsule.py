#!/usr/bin/env python3
"""Deterministic feedback translator for public-fictional Agent Fabric code tasks.

An independent bounded AST interpreter, not Python exec/import/eval/compile of
model source, supplies actual outcomes. This capsule is evidence, NOT an
authorized provider payload or CommandCenter action.
"""
from __future__ import annotations
import hashlib
import json
from nvidia_fixed_code_repair_work import parse_subset, interpret, CodeRejected
from nvidia_evidence_status_artifact_live_loop import ARGS, CASES, reference, score

SCHEMA = "commandcenter.public_synthetic_agent_feedback_capsule.v1"
LABELS = {
    -1:"INVALID_OR_CONTRADICTORY_EVIDENCE",
     0:"NO_VERIFIED_CURRENT_WORK",
     1:"QUEUE_PENDING_NOT_COMPLETED",
     2:"STALE_SOURCE_NOT_CURRENT",
     3:"VERIFIED_SUCCESS_PRECEDENCE",
     4:"VERIFIED_FAILURE_PRECEDENCE",
     5:"PROTECTED_QUEUE_NEVER_AUTHORITY",
     6:"UNVERIFIED_RECEIPT",
     7:"QUEUE_PROJECTION_REQUIRES_INVESTIGATION",
}
# Order matters: protected and signed/invalid precedence outrank cosmetic errors.
PRIORITY = (5,3,4,6,2,-1,7,1,0)
SCOPE = "READ_ONLY_UI_STATE_CLASSIFICATION"
RULES = (
    "Do not mutate the queue, execution router, receipts or permissions.",
    "Verified signed terminal receipts outrank delayed status projections.",
    "A stale observation is historical, not current health or a zero reading.",
    "Never interpret a code score as evidence of autonomous correction.",
)

def _index(rows, limit):
    """Take distinct semantic classes first, then additional failing cases."""
    selected, seen, kept = [], set(), set()
    for expected in PRIORITY:
        for row in rows:
            if row["expected"] == expected and expected not in seen:
                selected.append(row); seen.add(expected); kept.add(row["case_index"]); break
        if len(selected) == limit: return selected
    for row in rows:
        if row["case_index"] not in kept:
            selected.append(row)
        if len(selected) == limit: break
    return selected

def translate(source: str, *, attempt: int = 1) -> dict:
    if not isinstance(source,str) or type(attempt) is not int or not 1 <= attempt <= 3:
        raise ValueError("INVALID_FEEDBACK_SCOPE")
    fixture = [[list(row),reference(row)] for row in CASES]
    fixture_hash = hashlib.sha256(json.dumps(fixture,separators=(",",":")).encode()).hexdigest()
    evidence = score(source)
    base = {
        "schema": SCHEMA, "scope":SCOPE, "attempt":attempt,
        "source_sha256":hashlib.sha256(source.encode()).hexdigest(),
        "fixture_sha256":fixture_hash, "cases_total":len(CASES),
        "ast_admitted":evidence["source_ast_admitted"],
        "tests_passed":evidence["passed"], "tests_total":evidence["total"],
        "failure_count":len(evidence["failed_case_indices"]) if evidence["source_ast_admitted"] else None,
        "model_code_executed":False, "provider_called":False,
        "protected_execution_authorized":False, "work_scope":list(RULES),
        "failing_examples":[], "preserve_examples":[],
        "delivery": "RESEARCH_EVIDENCE_ONLY_NOT_PROVIDER_INPUT"
    }
    if not evidence["source_ast_admitted"]:
        return {**base,"next_step":"SOURCE_STRUCTURE_REJECTED_DO_NOT_CLAIM_100_BEHAVIORAL_FAILURES"}
    function=parse_subset(source,function_name="evidence_state",args=ARGS,
                         max_ast_nodes=160,max_local_names=5)
    bad, good = [],[]
    for index, inputs in enumerate(CASES):
        expected=reference(inputs)
        try:
            actual=interpret(function,inputs,args=ARGS)
            interpreter_rejected=False
        except (CodeRejected,ArithmeticError,TypeError,ValueError,OverflowError):
            actual=None
            interpreter_rejected=True
        correct=(not interpreter_rejected and type(actual) is type(expected) and actual==expected)
        row={"case_index":index,"input":list(inputs),"expected":expected,
             "actual":actual,"category":LABELS[expected],
             "interpreter_rejected":interpreter_rejected}
        (good if correct else bad).append(row)
    if len(good)!=evidence["passed"] or len(bad)!=len(evidence["failed_case_indices"]):
        raise AssertionError("INDEPENDENT_SCORE_RECONCILIATION_FAILED")
    return {**base,"next_step":"FIRST_DRAFT_ACCEPTED_NO_CORRECTION" if not bad else "REVISE_WITH_GROUNDED_COUNTEREXAMPLES",
            "failing_examples":_index(bad,3),
            "preserve_examples":_index(good,3)}

if __name__=="__main__":
    import argparse
    from pathlib import Path
    p=argparse.ArgumentParser(description="Translate a fictional model-generated artifact's deterministic test failures")
    p.add_argument("source",type=Path)
    p.add_argument("--attempt",type=int,default=1)
    args=p.parse_args()
    print(json.dumps(translate(args.source.read_text(),attempt=args.attempt),indent=2,sort_keys=True))
