#!/usr/bin/env python3
"""Five actual model-generated Python repair tasks using independent AST-only verification.

Only public fictional source; no arbitrary model code is compiled, imported,
executed or eval'd. No private GitHub Actions compute, arbitrary source input,
broker/device/root actions or model-output tool execution.
"""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
from nvidia_role_full_catalog_campaign import open_caller,close_caller
from nvidia_fixed_code_repair_work import evaluate,CodeRejected

MODELS=("poolside/laguna-xs-2.1","minimaxai/minimax-m3.1-flash")
TASKS=(
 ("RETRY_DEADLINE_01","retry_delay_ms",("attempt","max_attempts","base_ms","cap_ms")),
 ("BOUNDED_CLAMP_02","clamp_window",("value","low","high","fallback")),
 ("RESERVED_BUDGET_03","budget_remaining",("limit","spent","reserved","floor")),
 ("ALLOCATION_BPS_04","allocation_limit",("equity","risk_bps","cap_usd","minimum_usd")),
 ("STALE_HEARTBEAT_05","staleness_status",("now_ms","last_ms","warn_ms","expire_ms")),
)
URL="http://127.0.0.1:8787/role-code-case"
def oracle(task,x):
 a,b,c,d=x
 if task==0:
  return None if a<=0 or b<=0 or a>=b or c<=0 or d<=0 else min(d,c*2**(a-1))
 if task==1:
  return d if b>c else min(c,max(b,a))
 if task==2:
  if any(z<0 for z in x):return None
  left=a-b-c
  return None if left<d else left
 if task==3:
  if a<=0 or b<=0 or b>10000 or c<=0 or d<=0 or c<d:return None
  n=min(c,(a*b)//10000)
  return n if n>=d else None
 if task==4:
  if a<0 or b<0 or a<b or c<=0 or d<=c:return -1
  delta=a-b
  return 2 if delta>=d else 1 if delta>=c else 0
 raise ValueError("unknown_fixed_task")

# Boundary-heavy fixtures deliberately not included in the provider prompt.
INPUTS=(
 ((1,3,100,500),(2,3,100,500),(3,3,100,500),(4,3,100,500),
  (0,3,100,500),(-1,3,100,500),(1,1,100,500),(1,0,100,500),
  (1,3,0,500),(1,3,-1,500),(1,3,100,0),(1,3,100,-50),
  (1,3,100,50),(2,6,1000,2500),(3,6,1000,2500),(4,6,1000,2500),
  (5,6,1000,2500),(6,6,1000,2500),(1,2,7,100),(2,10,7,100),
  (3,10,7,100),(5,10,7,100),(1,3,99999,7),(2,7,1,1),
  (1,10,1,1),(9,10,1,1000),(10,10,1,1000),(2,3,1,10000),
  (2,2,1,10000),(1,8,100,100)),
 ((-4,0,8,99),(9,0,8,99),(5,8,2,99),(0,0,8,99),(8,0,8,99),
  (-1,-5,5,0),(-9,-5,5,0),(10,-5,5,0),(-5,-5,5,0),(5,-5,5,0),
  (3,3,3,0),(2,3,3,0),(4,3,3,0),(2,5,4,17),(-2,-1,-1,7),
  (-1,-1,-1,7),(0,-1,-1,7),(500,100,1000,1),(-500,100,1000,1),
  (0,1,-1,99),(22,0,100,0),(1000,0,100,0),(-1000,-100,-10,42),
  (7,7,7,0),(0,0,0,0),(3,2,5,0),(2,2,5,0),(5,2,5,0),
  (3,5,2,0),(9,10,5,100)),
 ((100,40,20,30),(100,70,20,11),(100,90,10,0),(0,0,0,0),
  (10,10,0,0),(10,10,1,0),(10,11,0,0),(100,40,60,0),
  (100,40,59,1),(100,40,59,2),(100,0,101,0),(-1,0,0,0),
  (1,-1,0,0),(1,0,-1,0),(1,0,0,-1),(100,40,20,41),
  (100,40,20,40),(100,40,20,39),(100,40,20,0),
  (100,99,0,1),(100,98,1,1),(100,98,1,2),
  (1000,500,100,400),(1000,500,100,401),(999,400,500,99),
  (999,400,500,100),(200,5,5,190),(200,5,5,191),
  (10,0,0,10),(10,0,0,11)),
 ((100000,100,1500,10),(100000,200,1500,10),(10000,1,1000,2),
  (10000,1,1000,1),(10000,10000,1000,1),
  (10000,10001,1000,1),(10000,0,1000,1),(-1,100,1000,1),
  (0,100,1000,1),(1000,100,0,1),(1000,100,100,-1),
  (1000,100,100,0),(1000,100,5,6),(1000,100,6,6),
  (1000,100,6,5),(900,100,100,9),(900,100,100,10),
  (100000,25,1000,200),(100000,25,1000,251),
  (100000,1,1,1),(9999,1,1,1),(10000,1,1,1),
  (100000,9999,10000,20),(100000,10000,10000,20),
  (99999,10,99,99),(99999,10,99,100),
  (1000,9999,500,1),(1,10000,10,1),(1,10000,10,2),
  (1000,500,100,1)),
 ((250,0,100,300),(300,0,100,300),(50,100,10,20),
  (0,0,10,20),(9,0,10,20),(10,0,10,20),(19,0,10,20),
  (20,0,10,20),(21,0,10,20),(99,50,50,100),
  (100,50,50,100),(150,50,50,100),(149,50,50,100),
  (-1,0,10,20),(0,-1,10,20),(100,0,0,20),
  (100,0,-1,20),(100,0,10,10),(100,0,10,9),
  (100,0,10,11),(0,0,1,2),(1,0,1,2),
  (2,0,1,2),(1000,900,100,200),(1100,900,100,200),
  (1099,900,100,200),(1200,900,100,200),
  (50,49,1,2),(52,49,1,2),(101,100,1,2)),
)
def cases_for(index):
 if type(index)!=int or index not in range(len(TASKS)):
  raise ValueError("INVALID_FIXED_ROLE_TASK")
 return tuple((x,oracle(index,x)) for x in INPUTS[index])

def fixed_role_http_timeout(model_index):
 # Allow the caller to outlive the approved 75-second MiniMax Worker cap,
 # without silently raising Poolside's normal 55-second caller budget.
 if type(model_index)!=int or model_index not in (0,1):
  raise RuntimeError("INVALID_MODEL")
 return 90 if model_index==1 else 55

def call_case(model_index,task_index):
 selector=json.dumps({"model_index":model_index,"task_index":task_index},separators=(",",":")).encode()
 req=Request(URL,data=selector,headers={"Content-Type":"application/json"},method="POST")
 try:
  with urlopen(req,timeout=fixed_role_http_timeout(model_index)) as r:
   return json.loads(r.read(14000))
 except HTTPError as exc:
  try:return json.loads(exc.read(14000))
  except ValueError:raise RuntimeError("UNTRUSTED_FIXED_ROLE_RECEIPT")
 except (URLError,TimeoutError,OSError,ValueError) as err:
  raise RuntimeError("FIXED_ROLE_TRANSPORT_OR_RECEIPT_HELD") from err

def safe_case(doc,model_index,task_index):
 task=TASKS[task_index]
 if(not isinstance(doc,dict) or doc.get("schema")!="commandcenter.nvidia_role_code_case.v1"
    or doc.get("model")!=MODELS[model_index] or doc.get("model_index")!=model_index
    or doc.get("task_id")!=task[0] or doc.get("task_index")!=task_index
    or doc.get("provider_calls")!=1):
  raise RuntimeError("UNTRUSTED_ROLE_CASE_IDENTITY")
 status=doc.get("status")
 if status not in ("candidate_unexecuted","format_rejected","provider_rate_limited",
    "provider_unavailable","provider_transport_or_decode_failure"):
  raise RuntimeError("UNTRUSTED_ROLE_CASE_STATUS")
 code=doc.get("http_status")
 if code is not None and (type(code)!=int or not 100<=code<=599):
  raise RuntimeError("UNTRUSTED_ROLE_CASE_HTTP")
 src=doc.get("code") if status=="candidate_unexecuted" else None
 if status=="candidate_unexecuted" and (code!=200 or not isinstance(src,str)):
  raise RuntimeError("UNTRUSTED_ROLE_CASE_SOURCE")
 return status,code,src

def run_model(model_index,first_task=0,end_task=None):
 if type(model_index)!=int or model_index not in (0,1):raise RuntimeError("INVALID_MODEL")
 if end_task is None:end_task=len(TASKS)
 if (type(first_task)!=int or type(end_task)!=int or
     not ((first_task,end_task) in ((0,5),(2,5),(4,5)) or
          0<=first_task<5 and end_task==first_task+1)):
  raise RuntimeError("INVALID_FIXED_ROLE_JOB_BOUNDARY")
 rows=[];verified={}
 for task_index in range(first_task,end_task):
  task=TASKS[task_index]
  proc=open_caller(Path(os.environ.get("RUNNER_TEMP","/tmp"))/f"nvidia_role_{model_index}_{task_index}.log")
  try: doc=call_case(model_index,task_index)
  finally:close_caller(proc)
  status,http,code=safe_case(doc,model_index,task_index)
  scores={"passed":0,"total":len(INPUTS[task_index]),"all_passed":False,
          "failed_case_indices":[]}
  rejection_reason=None
  if code is not None:
   try:
    scores=evaluate(code,function_name=task[1],args=task[2],
        cases=cases_for(task_index))
   except CodeRejected as exc:
    status="ast_rejected"
    # A strict enum of reviewer-originated labels only. No source or
    # model output is used as an error string.
    allowed={"AST_UNSUPPORTED_NODE","AST_COMPLEXITY_LIMIT",
     "UNTRUSTED_MODEL_CODE","INTEGER_GROWTH_LIMIT","INVALID_VALUE",
     "ZERO_DIVISION_REJECTED","EXPONENT_LIMIT","NESTED_IF_LIMIT",
     "MISSING_RETURN","INVALID_CODE_SYNTAX","AST_INVALID_ASSIGNMENT",
     "AST_TOO_MANY_LOCALS","UNKNOWN_EXPRESSION"}
    rejection_reason=str(exc) if str(exc) in allowed else "AST_OTHER"
   except (TypeError,ValueError):
    status="ast_rejected"
    rejection_reason="AST_TYPE_REJECTED"
  receipt={"model":MODELS[model_index],"task_id":task[0],"task_index":task_index,
   "provider_status":status,"http_status":http,
   "latency_ms":doc.get("elapsed_ms"),"tests_passed":scores["passed"],
   "tests_total":scores["total"],"all_tests_passed":scores["all_passed"],
   "model_code_executed":False,"real_repo_mutated":False,
   "private_data_used":False,
   "rejection_reason":rejection_reason}
  rows.append(receipt)
  print("NVIDIA_ROLE_CODE_OBSERVATION="+json.dumps(receipt,sort_keys=True,separators=(",",":")),flush=True)
  if scores["all_passed"]:
   verified[task[0]]=code
   print("NVIDIA_ROLE_VERIFIED_SYNTHETIC_PATCH="+json.dumps({
    "model":MODELS[model_index],"task_id":task[0],"source":code},
    sort_keys=True,separators=(",",":")),flush=True)
  if status=="provider_rate_limited":
   print("NVIDIA_ROLE_CODE_STOP=HTTP_429_NO_RETRY",flush=True)
   break
  if status=="provider_unavailable" or status=="provider_transport_or_decode_failure":
   print("NVIDIA_ROLE_CODE_STOP=PROVIDER_UNAVAILABLE_NO_RETRY",flush=True)
   break
 summary={"model":MODELS[model_index],"cases_attempted":len(rows),
   "cases_total":len(TASKS),"cases_correct":sum(v["all_tests_passed"] for v in rows),
   "behavior_checks_passed":sum(v["tests_passed"] for v in rows),
   "behavior_checks_run":sum(v["tests_total"] for v in rows),
   "api_calls_reserved":len(rows),"production_activated":False,
   "model_code_executed":False,"private_data_sent":False,
   "first_task_index":first_task,
   "selected_tasks":end_task-first_task,
   "complete_selected_tasks":len(rows)==end_task-first_task,
   "complete_all_five":first_task==0 and end_task==5 and len(rows)==len(TASKS)}
 print("NVIDIA_ROLE_CODE_SUMMARY="+json.dumps(summary,sort_keys=True,separators=(",",":")),flush=True)
 return summary

def parse_role_selector(selector):
 if not isinstance(selector,str):raise RuntimeError("ONLY_FIXED_ROLE_JOB_SELECTOR_ALLOWED")
 if selector=="all":start,end=0,5
 elif selector=="tail":start,end=2,5
 elif selector=="last":start,end=4,5
 elif selector in ("one:0","one:1","one:2","one:3","one:4"):
  start=int(selector[-1]);end=start+1
 else:raise RuntimeError("ONLY_FIXED_ROLE_JOB_SELECTOR_ALLOWED")
 return start,end

def main():
 if len(sys.argv)!=3 or sys.argv[1] not in ("poolside","minimax"):
  raise RuntimeError("ONLY_FIXED_MODEL_AND_ROLE_SELECTOR_ALLOWED")
 start,end=parse_role_selector(sys.argv[2])
 run_model(0 if sys.argv[1]=="poolside" else 1,start,end)
if __name__=="__main__":
 try:main()
 except (RuntimeError,CodeRejected,OSError,ValueError) as ex:
  print("NVIDIA_ROLE_CODE_HELD="+str(ex),flush=True)
  raise SystemExit(1)
