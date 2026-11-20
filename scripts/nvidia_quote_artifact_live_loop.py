#!/usr/bin/env python3
"""One live synthetic model -> AST score -> failed-case feedback -> revision artifact.
Never exec/import/compile model-produced source. No actual customer or workbook data.
"""
from __future__ import annotations
import hashlib
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from nvidia_fixed_code_repair_work import evaluate, CodeRejected

URL = "http://127.0.0.1:8787/quote-artifact-step"
ARGS = ("minutes","hourly_cents","travel_cents","supplies_cents","overhead_bps","margin_bps")
SCHEMA = "commandcenter.public_synthetic_quote_artifact_step.v1"
MODEL = "poolside/laguna-xs-2.1"
TRAIN = (
 (90,3500,500,250,1000,2500),(1,100,0,0,0,0),(0,0,0,0,0,0),
 (0,0,800,0,500,2000),(60,2500,0,0,0,2000),
 (45,1700,200,100,1250,3500),(120,4000,0,0,0,9999),
 (0,1000,500,500,500,0),(15,2001,10,20,1000,2500),
 (3,1000,0,0,3333,4999),(-1,2500,10,20,100,2000),
 (15,2500,10,20,100,10000),(5,2000,10,20,10001,100),
 (30,-100,10,20,1000,500),(59,1999,125,0,900,3400),
 (300,4999,999,123,0,0),
)
# Independently frozen secondary cases. No scorer generated or mutated by model.
HOLD = tuple(
 ((i*29)%301, 1099+(i*317)%5001, (i*43)%651, (i*37)%477,
  (i*113)%8501, (i*257)%9901) for i in range(40)
) + ((0,0,1,0,0,9999),(0,0,0,0,9999,0),
     (100,1500,50,-1,100,1500),(1,1,0,0,1,1))
CASES = TRAIN + HOLD

def reference(inp):
    if len(inp)!=6 or any(type(x) is not int for x in inp):
        raise ValueError("INVALID_FIXED_CASE")
    minutes,hourly,travel,supplies,overhead_bps,margin_bps=inp
    if any(x<0 for x in inp) or overhead_bps>10000 or margin_bps>=10000:
        return None
    base=(minutes*hourly+59)//60+travel+supplies
    cost=base+(base*overhead_bps+9999)//10000
    if cost==0:return None
    price=(cost*10000+9999-margin_bps)//(10000-margin_bps)
    return price if price<=1_000_000_000 else None

def score(source):
    cases=tuple((args,reference(args)) for args in CASES)
    try:
        data=evaluate(source,function_name="quote_price_cents",args=ARGS,cases=cases, max_ast_nodes=160, max_local_names=5)
    except (CodeRejected,ArithmeticError,TypeError,ValueError,OverflowError):
        return {"passed":0,"total":len(cases),
                "failed_case_indices":list(range(len(cases))),
                "source_ast_admitted":False}
    return {**data,"source_ast_admitted":True}

def validate_step(value,stage):
    if isinstance(value,dict) and isinstance(value.get("error"),str):
        allowed={
          "invalid_selector","binding_unavailable","binding_transport_unavailable",
          "invalid_receipt","untrusted_receipt","invalid_source_receipt",
          "upstream_quote_step_selector_rejected","upstream_diagnostic_not_admitted",
          "upstream_binding_unavailable","upstream_secret_unavailable",
          "upstream_unavailable","upstream_unclassified"
        }
        error=value["error"]
        raise RuntimeError("QUOTE_CALLER_"+(error.upper() if error in allowed else "UNCLASSIFIED"))
    if not isinstance(value,dict) or any(value.get(k)!=v for k,v in {
      "schema":SCHEMA,"stage":stage,"model":MODEL,"provider_calls":1,
      "private_input_used":False,"model_code_executed":False,
      "commands_executed":False,"production_admitted":False}.items()):
        raise ValueError("QUOTE_MODEL_RECEIPT_UNTRUSTED")
    if value.get("status")!="candidate_unexecuted" or value.get("http_status")!=200:
        raise RuntimeError("QUOTE_PROVIDER_OR_FORMAT_HELD_"+str(value.get("status")))
    source=value.get("source")
    if not isinstance(source,str) or not source.startswith(
      "def quote_price_cents("+", ".join(ARGS)+"):\n") or not 110<=len(source)<=1051:
        raise ValueError("QUOTE_SOURCE_SHAPE_REJECTED")
    return source

def call(value,stage):
    payload=json.dumps(value,separators=(",",":")).encode()
    request=Request(URL,data=payload,method="POST",
       headers={"Content-Type":"application/json","Content-Length":str(len(payload))})
    try:
        with urlopen(request,timeout=110) as response:
            body=response.read(12000)
    except HTTPError as error:
        body=error.read(12000)
    except (OSError,TimeoutError,URLError) as error:
        raise RuntimeError("QUOTE_PRIVATE_BINDING_UNAVAILABLE") from error
    try:doc=json.loads(body)
    except (ValueError,UnicodeError) as error:
        raise RuntimeError("QUOTE_STEP_RESPONSE_INVALID") from error
    return validate_step(doc,stage)

def failures_for_revision(scored):
    return [{"input":list(CASES[i]),"expected":reference(CASES[i])}
            for i in scored["failed_case_indices"][:3]]

def score_pair(initial,revised):
    a=score(initial)
    b=score(revised) if revised is not None else None
    no_loss=(b is not None and all(
       i in a["failed_case_indices"] or i not in b["failed_case_indices"]
       for i in range(len(CASES))))
    return a,b,no_loss

def outcome(a,b,no_loss):
    if a["passed"]==a["total"]:return "ALREADY_PASSED_ONE_CALL"
    if b is None:return "REVISION_UNAVAILABLE"
    if b["passed"]==b["total"] and no_loss and b["passed"]>a["passed"]:
        return "ACCEPTED_REVIEW_READY"
    if b["passed"]>a["passed"] and no_loss:return "IMPROVED_NOT_ACCEPTED"
    if b["passed"]<a["passed"] or not no_loss:return "REGRESSED_REJECTED"
    return "NO_GAIN_REJECTED"

def persist(initial,revised,a,b,no_loss):
    dest=Path("artifacts/nvidia-quote-artifact")
    dest.mkdir(parents=True,exist_ok=True)
    (dest/"baseline_model.py").write_text(initial,encoding="utf-8")
    if revised is not None:(dest/"revised_model.py").write_text(revised,encoding="utf-8")
    result={
      "schema":"commandcenter.public_synthetic_quote_artifact_review.v1",
      "workflow_run_id":os.getenv("GITHUB_RUN_ID"),
      "controller_sha":os.getenv("GITHUB_SHA"),
      "model":MODEL,
      "source_sha_baseline":hashlib.sha256(initial.encode()).hexdigest(),
      "source_sha_revised":hashlib.sha256(revised.encode()).hexdigest() if revised else None,
      "baseline":a,"revised":b,"no_regression":no_loss,
      "outcome":outcome(a,b,no_loss),"provider_requests":1+(revised is not None),
      "task":"fictional_IE-V003_quote_price_cents",
      "synthetic_only":True,"real_workbook_modified":False,
      "model_code_executed":False,"protected_actions":False,
      "production_admitted":False,"cost_measurement":"not_available"
    }
    (dest/"evaluation.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return result

def main():
    first=call({"stage":0},0)
    a=score(first)
    print("QUOTE_BASELINE_AST_ADMITTED="+str(a["source_ast_admitted"]).lower(),flush=True)
    print("QUOTE_BASELINE_PASSED="+str(a["passed"])+"/"+str(a["total"]),flush=True)
    revised=None
    if a["passed"]!=a["total"]:
        feedback=failures_for_revision(a)
        revised=call({"stage":1,"source":first,"failed_examples":feedback},1)
    x,y,no_loss=score_pair(first,revised)
    result=persist(first,revised,x,y,no_loss)
    print("NVIDIA_QUOTE_LOOP_OUTCOME="+result["outcome"],flush=True)
    print("NVIDIA_QUOTE_LOOP_REVISED_PASSED="+(
      str(y["passed"])+"/"+str(y["total"]) if y else "not_needed"),flush=True)
    print("NVIDIA_QUOTE_LOOP_PROVIDER_CALLS="+str(result["provider_requests"]),flush=True)
    print("NVIDIA_QUOTE_MODEL_CODE_EXECUTED=false",flush=True)
    return 0

if __name__=="__main__":
    sys.exit(main())
