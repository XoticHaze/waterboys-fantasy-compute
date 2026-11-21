#!/usr/bin/env python3
"""Secondary frozen v2 holdout with real queue-state diversity.

Historical v1 100-case score/source IDs are preserved, NEVER silently rewritten.
This adds an independently named 74-case discriminator for future original
model source and revision artifacts. No provider calls or source execution.
"""
from __future__ import annotations
import hashlib
import json
from nvidia_evidence_status_artifact_live_loop import ARGS,SEED,reference
from nvidia_fixed_code_repair_work import evaluate,CodeRejected

PROFILE="commandcenter.public_synthetic_evidence_holdout_v2"
HOLDOUT_V2=tuple(
    (i%3,(i//3)%2,(i*7+i//3)%5,(i*37+11)%250,
     30+(i*19+7)%180,(i//7)%2)
    for i in range(74)
)
assert len(HOLDOUT_V2)==len(set(HOLDOUT_V2))==74
assert not set(HOLDOUT_V2).intersection(SEED)
assert {v[2] for v in HOLDOUT_V2}==set(range(5))
FIXTURE_SHA256=hashlib.sha256(json.dumps(
    [[list(v),reference(v)] for v in HOLDOUT_V2],
    separators=(',',':')).encode('utf-8')).hexdigest()

def score_holdout_v2(source: str)->dict:
    if not isinstance(source,str) or len(source)>1051:
        raise ValueError("INVALID_SYNTHETIC_SOURCE_BYTES")
    cases=tuple((v,reference(v)) for v in HOLDOUT_V2)
    try:
        scored=evaluate(source,function_name='evidence_state',args=ARGS,
                        cases=cases,max_ast_nodes=160,max_local_names=5)
    except (CodeRejected,ArithmeticError,TypeError,ValueError,OverflowError):
        return dict(profile=PROFILE,fixture_sha256=FIXTURE_SHA256,ast_admitted=False,
                    passed=None,total=74,failed_case_indices=None)
    return dict(profile=PROFILE,fixture_sha256=FIXTURE_SHA256,ast_admitted=True,
                passed=scored['passed'],total=74,
                failed_case_indices=scored['failed_case_indices'])

def compare_holdout_v2(first: str,revised: str|None)->dict:
    baseline=score_holdout_v2(first)
    second=score_holdout_v2(revised) if revised is not None else None
    valid=baseline['ast_admitted'] and second is not None and second['ast_admitted']
    old=set(baseline['failed_case_indices']) if valid else set()
    new=set(second['failed_case_indices']) if valid else set()
    if not baseline['ast_admitted']:result="BASELINE_STRUCTURE_REJECTED"
    elif second is None:result="REVISION_UNAVAILABLE"
    elif not second['ast_admitted']:result="REVISION_STRUCTURE_REJECTED"
    elif first==revised:result="IDENTICAL_SOURCE_NOT_SELF_CORRECTION"
    elif new-old:result="REGRESSED_REJECTED"
    elif old-new:result="HOLDOUT_V2_IMPROVED_NO_REGRESSION"
    else:result="NO_MEASURED_GAIN"
    return dict(profile=PROFILE,fixture_sha256=FIXTURE_SHA256,
                baseline=baseline,revised=second,outcome=result,
                newly_correct_count=len(old-new) if valid else 0,
                regressed_count=len(new-old) if valid else 0,
                same_source=(first==revised) if revised is not None else None,
                provider_called=False,model_code_executed=False,
                protected_execution_authorized=False,
                original_v1_cases_unchanged=True)
