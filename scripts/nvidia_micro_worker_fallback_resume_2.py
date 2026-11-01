#!/usr/bin/env python3
"""Continue *only* MiniMax fixed synthetic batches 2..5 from verified sanitized checkpoint.

No prompt/secret/response bytes persisted. Independent Workflow restores the
existing Cloudflare diagnostic flag whether all cases pass or a 429 holds.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import time
from nvidia_role_full_catalog_campaign import (
    open_caller,close_caller,check_time,MAX_WINDOW_SECONDS,MAX_API_CALLS_PER_RUN
)
from nvidia_micro_worker_campaign import MODELS,call,validate,Retryable,CATEGORIES

ROOT=Path(__file__).resolve().parents[1]
CHECKPOINT=ROOT/"ops/nvidia_minimax_synthetic_checkpoint_20261101.v1.json"
EXPECTED_RUN=41353813429
EXPECTED_SOURCE="d86ed0b9417b590d44ed159badb6e0e114c54278"
EXPECTED_CASES=["T01","T02","T03","T04","R01","R02","R03","R04"]
MODEL_INDEX=1
REMAINING=(2,3,4,5)

def read_checkpoint(path=CHECKPOINT):
    doc=json.loads(Path(path).read_text(encoding="utf-8"))
    source=doc.get("source") or {}
    rows=doc.get("completed_cases") or []
    if (doc.get("schema")!="commandcenter.nvidia_minimax_fixed_synthetic_checkpoint.v1"
        or doc.get("model")!=MODELS[1]
        or doc.get("status")!="INCOMPLETE_AFTER_PROVIDER_HTTP_429_NO_AUTO_RETRY"
        or source.get("run")!=EXPECTED_RUN or source.get("worker_source_sha")!=EXPECTED_SOURCE
        or doc.get("completed_batch_indices")!=[0,1]
        or doc.get("next_eligible_batch_index")!=2
        or doc.get("complete_cases")!=8 or doc.get("format_valid_cases")!=8
        or doc.get("http_200_cases")!=8
        or [r.get("case") for r in rows]!=EXPECTED_CASES
        or any(type(r.get("passed"))!=bool or set(r)!={"case","passed"} for r in rows)
        or doc.get("raw_model_output_included") is not False
        or doc.get("private_data_included") is not False
        or doc.get("credentials_included") is not False
        or doc.get("production_activation") is not False
        or doc.get("diagnostic_flag_restored_0") is not True):
        raise RuntimeError("UNTRUSTED_FIXED_MINIMAX_CHECKPOINT")
    return rows

def main():
    baseline=read_checkpoint()
    start=time.monotonic(); done=0;reserved=0;observations=[]
    print("NVIDIA_MINIMAX_RESUME_SOURCE_RUN="+str(EXPECTED_RUN),flush=True)
    print("NVIDIA_MINIMAX_RESUME_FIRST_UNTESTED_BATCH=2",flush=True)
    while done<len(REMAINING):
        check_time(start)
        caller=open_caller(Path(os.environ.get("RUNNER_TEMP","/tmp"))/"nvidia_minimax_fixed_resume_2.log")
        try:
            for _ in range(4):
                if done>=len(REMAINING):break
                check_time(start)
                if reserved+4>16 or reserved+4>MAX_API_CALLS_PER_RUN:
                    raise RuntimeError("FIXED_MINIMAX_RESUME_BUDGET_EXCEEDED")
                batch=REMAINING[done];reserved+=4
                try:doc=call(MODEL_INDEX,batch)
                except Retryable as exc:
                    print("NVIDIA_MINIMAX_RESUME_PROVIDER_HELD="+str(exc),flush=True)
                    raise RuntimeError("FIXED_MINIMAX_PROVIDER_HELD_NO_AUTO_RETRY") from exc
                rows=validate(doc,MODEL_INDEX,batch)
                observations.extend(rows)
                for row in rows:
                    print("NVIDIA_MINIMAX_RESUME_OBSERVATION="+json.dumps(
                      row,sort_keys=True,separators=(",",":")),flush=True)
                done+=1
                print("NVIDIA_MINIMAX_RESUME_BATCH="+str(done)+"/4",flush=True)
        finally:close_caller(caller)
    if (done!=4 or len(observations)!=16 or len({x["case"] for x in observations})!=16
        or time.monotonic()-start>=MAX_WINDOW_SECONDS):
        raise RuntimeError("FIXED_MINIMAX_RESUME_INCOMPLETE")
    original_passes=sum(x["passed"] for x in baseline)
    new_passes=sum(x["passed"] for x in observations)
    protected=[x for x in observations if x["category"] in ("placement","security","command")]
    summary={
       "schema":"commandcenter.nvidia_minimax_resumed_shadow.v1",
       "status":"all_24_fixed_cases_observed_across_two_runs",
       "source_run":EXPECTED_RUN,"model":MODELS[1],
       "first_run_cases":8,"new_run_cases":16,"total_fixed_cases":24,
       "exact_matches":original_passes+new_passes,
       "protected_attempted":len(protected),
       "protected_exact_matches":sum(x["passed"] for x in protected),
       "new_run_provider_calls_conservatively_reserved":reserved,
       "max_new_run_calls":16,"no_retry_on_429":True,
       "model_activated":False,"external_actions":False,
       "requires_independent_protected_case_adjudication":True
    }
    print("NVIDIA_MINIMAX_RESUMED_SUMMARY="+json.dumps(
       summary,sort_keys=True,separators=(",",":")),flush=True)
    print("NVIDIA_MINIMAX_RESUME_FIXED_COVERAGE=PASS",flush=True)

if __name__=="__main__":
    try:main()
    except (OSError,RuntimeError,ValueError) as exc:
        print("NVIDIA_MINIMAX_RESUME_HELD="+str(exc),flush=True)
        raise SystemExit(1)
