#!/usr/bin/env python3
"""12- or 16-call public-safe enum-only NVIDIA micro policy diagnostic.

Runs exact fixed synthetic batches T and P for both fixed models. This is a
discriminator, not full validation or production admission.
"""
import json
import os
from pathlib import Path
import time
from nvidia_role_full_catalog_campaign import (
 MAX_API_CALLS_PER_RUN,MAX_WINDOW_SECONDS,check_time,open_caller,close_caller,
)
from nvidia_micro_worker_campaign import call,validate,MODELS,Retryable

TASKS=((0,0),(0,2),(1,0),(1,2))
def main():
 begin=time.monotonic()
 done=0;reserved=0;retries={}
 print("MICRO_DIAGNOSTIC_ENUM_ONLY=true",flush=True)
 while done<len(TASKS):
  check_time(begin)
  proc=open_caller(Path(os.environ.get("RUNNER_TEMP","/tmp"))/"nvidia_micro_enum_diagnostic.log")
  cooldown=0
  try:
   for _ in range(4):
    if done>=len(TASKS):break
    if reserved+4>MAX_API_CALLS_PER_RUN:raise RuntimeError("MICRO_DIAGNOSTIC_REQUEST_CEILING")
    mi,batch=TASKS[done]
    reserved+=4
    try:doc=call(mi,batch)
    except Retryable as exc:
     n=retries.get((mi,batch),0)+1;retries[(mi,batch)]=n
     if n>3:raise RuntimeError("MICRO_DIAGNOSTIC_RATE_OR_TRANSPORT_HELD")
     cooldown=min(150,30*n if str(exc)!="PROVIDER_RATE_LIMIT" else 60*n)
     print("MICRO_DIAGNOSTIC_RETRY="+json.dumps({"model":MODELS[mi],
       "batch":batch,"class":str(exc),"retry":n,"cooldown_s":cooldown},
       sort_keys=True,separators=(",",":")),flush=True)
     break
    observations=validate(doc,mi,batch)
    for item in observations:
     print("MICRO_DIAGNOSTIC_ENUM="+json.dumps(item,sort_keys=True,separators=(",",":")),flush=True)
    done+=1
    print("MICRO_DIAGNOSTIC_BATCH_COMPLETE="+str(done)+"/4",flush=True)
  finally:
   close_caller(proc)
  if cooldown:
   check_time(begin)
   time.sleep(cooldown)
 if done!=4 or time.monotonic()-begin>=MAX_WINDOW_SECONDS:
  raise RuntimeError("MICRO_DIAGNOSTIC_INCOMPLETE")
 print("MICRO_DIAGNOSTIC_COMPLETE=PASS",flush=True)
 print("MICRO_DIAGNOSTIC_REQUESTS_PESSIMISTIC="+str(reserved),flush=True)
 print("MICRO_DIAGNOSTIC_PRODUCTION_ACTIVATED=false",flush=True)
if __name__=="__main__":
 try:main()
 except (OSError,RuntimeError,ValueError) as exc:
  print("MICRO_DIAGNOSTIC_HELD="+str(exc),flush=True)
  raise SystemExit(1)
