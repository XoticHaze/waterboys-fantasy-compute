#!/usr/bin/env python3
"""Bounded 24-case Poolside-only shadow qualification using the existing private NVIDIA route.

No provider call on 429 after the first refusal, no automatic switchover,
no arbitrary prompt/model, no real command. The existing Workflow restores
disabled Cloudflare diagnostic state even on a failed test.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import time
from nvidia_role_full_catalog_campaign import (
    MAX_API_CALLS_PER_RUN,MAX_WINDOW_SECONDS,check_time,open_caller,close_caller,
)
from nvidia_micro_worker_campaign import call,validate,Retryable,MODELS,CATEGORIES

TARGET_MODEL_INDEX=0
TASKS=tuple((TARGET_MODEL_INDEX,b) for b in range(6))
def main():
    start=time.monotonic()
    done=0; reserved=0;rows=[]
    print("NVIDIA_MICRO_PRIMARY_ONLY_MODEL="+MODELS[TARGET_MODEL_INDEX],flush=True)
    print("NVIDIA_MICRO_PRIMARY_BUDGET_MAX_PROVIDER_CALLS=24",flush=True)
    while done<len(TASKS):
        check_time(start)
        process=open_caller(Path(os.environ.get("RUNNER_TEMP","/tmp"))/"nvidia_primary_shadow_probe.log")
        try:
            for _ in range(5):
                if done>=len(TASKS):break
                check_time(start)
                if reserved+4>24 or reserved+4>MAX_API_CALLS_PER_RUN:
                    raise RuntimeError("PRIMARY_BUDGET_REACHED")
                mi,batch=TASKS[done]
                reserved+=4 # pessimistic reservation, including a lost reply
                try:
                    reply=call(mi,batch)
                except Retryable as exc:
                    # Do not repeatedly probe a provider 429 or ambiguous
                    # private transport. Leave diagnostic off and hold.
                    print("NVIDIA_PRIMARY_HELD="+str(exc),flush=True)
                    raise RuntimeError("PRIMARY_PROVIDER_HELD_NO_AUTORETRY") from exc
                current=validate(reply,mi,batch)
                rows.extend(current)
                for item in current:
                    print("NVIDIA_PRIMARY_OBSERVATION="+json.dumps(
                        item,sort_keys=True,separators=(",",":")),flush=True)
                done+=1
                print("NVIDIA_PRIMARY_BATCH="+str(done)+"/6",flush=True)
        finally:close_caller(process)
    if done!=6 or len(rows)!=24 or len({x["case"] for x in rows})!=24 or time.monotonic()-start>=MAX_WINDOW_SECONDS:
        raise RuntimeError("PRIMARY_COVERAGE_INCOMPLETE")
    protected=[x for x in rows if x["category"] in ("placement","security","command")]
    summary={
        "schema":"commandcenter.nvidia_micro_primary_shadow_receipt.v1",
        "status":"24_cases_observed_no_execution",
        "model":MODELS[0],"attempted":24,"passed":sum(x["passed"] for x in rows),
        "protected_attempted":len(protected),
        "protected_passed":sum(x["passed"] for x in protected),
        "format_valid":sum(x["format_valid"] for x in rows),
        "categories":{c:{"passed":sum(x["passed"] for x in rows if x["category"]==c),
                         "attempted":sum(x["category"]==c for x in rows)} for c in CATEGORIES},
        "calls_conservatively_reserved":reserved,
        "limit_provider_calls":24,
        "window_seconds":MAX_WINDOW_SECONDS,
        "elapsed_seconds":int(time.monotonic()-start),
        "production_activation":False,"commands_executed":False,
    }
    print("NVIDIA_PRIMARY_SHADOW_SUMMARY="+json.dumps(summary,sort_keys=True,separators=(",",":")),flush=True)
    print("NVIDIA_PRIMARY_FIXED_SYNTHETIC_COVERAGE=PASS",flush=True)

if __name__=="__main__":
    try:main()
    except (OSError,RuntimeError,ValueError) as exc:
        print("NVIDIA_PRIMARY_CAMPAIGN_HELD="+str(exc),flush=True)
        raise SystemExit(1)
