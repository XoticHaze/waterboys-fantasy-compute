#!/usr/bin/env python3
"""Evaluate exactly four *fictional* writing tasks through private Service Binding.

No raw drafts, customer/private data, prompts, API keys, or model answers leave
the private Worker. This is a factual/safety rubric versus static templates,
not proof that model language is more useful or production-ready.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from nvidia_role_full_catalog_campaign import open_caller,close_caller

URL="http://127.0.0.1:8787/draft-pilot"
EXPECTED=("OP01","OP02","CX01","CX02")
MODEL="poolside/laguna-xs-2.1"

def validate(doc):
    if not isinstance(doc,dict) or doc.get("schema")!="commandcenter.nvidia_fixed_draft_pilot.v1" or doc.get("model")!=MODEL:
        raise RuntimeError("DRAFT_RECEIPT_IDENTITY_INVALID")
    status=doc.get("status")
    rows=doc.get("results")
    if not isinstance(rows,list) or len(rows)>4 or doc.get("attempted")!=len(rows):
        raise RuntimeError("DRAFT_RECEIPT_COVERAGE_INVALID")
    if [v.get("id") for v in rows if isinstance(v,dict)] != list(EXPECTED[:len(rows)]):
        raise RuntimeError("DRAFT_RECEIPT_CASE_ORDER_INVALID")
    observations=[]
    for row in rows:
        if not isinstance(row,dict) or row.get("kind") not in ("operator","customer"):
            raise RuntimeError("DRAFT_RECEIPT_CASE_TYPE_INVALID")
        code=row.get("http_status")
        if code is not None and (type(code)!=int or not 100<=code<=599):
            raise RuntimeError("DRAFT_RECEIPT_HTTP_INVALID")
        facts=row.get("anchor_groups")
        met=row.get("anchor_groups_met")
        if type(facts)!=int or type(met)!=int or not 1<=facts<=8 or not 0<=met<=facts:
            raise RuntimeError("DRAFT_RECEIPT_FACTS_INVALID")
        if type(row.get("latency_ms"))!=int or not 0<=row["latency_ms"]<=120000:
            raise RuntimeError("DRAFT_RECEIPT_LATENCY_INVALID")
        vals=("format_valid","unsupported_claim_flag","human_review_flag",
              "draft_length_ok","draft_passed","template_passed")
        if any(type(row.get(v))!=bool for v in vals):
            raise RuntimeError("DRAFT_RECEIPT_FLAGS_INVALID")
        observations.append({k:row[k] for k in ("id","kind","http_status","latency_ms",
            "format_valid","anchor_groups","anchor_groups_met","unsupported_claim_flag",
            "human_review_flag","draft_length_ok","draft_passed","template_passed")})
    if status!="completed_not_human_reviewed":
        print("NVIDIA_DRAFT_VALUE_HELD="+json.dumps({"status":status,"cases_completed":len(rows)},sort_keys=True),flush=True)
        raise RuntimeError("DRAFT_PROVIDER_OR_RATE_HELD_NO_RETRY")
    if len(rows)!=4 or any(v["http_status"]!=200 for v in observations):
        raise RuntimeError("DRAFT_FIXED_COVERAGE_INCOMPLETE")
    return observations

def main():
    process=open_caller(Path(os.environ.get("RUNNER_TEMP","/tmp"))/"nvidia_fixed_draft_pilot_caller.log")
    try:
        req=Request(URL,data=b"",method="POST")
        try:
            with urlopen(req,timeout=150) as r:
                doc=json.loads(r.read(24000))
        except HTTPError as e:
            try:
                doc=json.loads(e.read(24000))
            except ValueError as ex:
                raise RuntimeError("DRAFT_LOCAL_RECEIPT_INVALID") from ex
        except (URLError,OSError,TimeoutError,ValueError) as ex:
            raise RuntimeError("DRAFT_LOCAL_BINDING_UNAVAILABLE_NO_RETRY") from ex
        rows=validate(doc)
    finally:
        close_caller(process)
    for row in rows:
        print("NVIDIA_DRAFT_VALUE_OBSERVATION="+json.dumps(row,sort_keys=True,separators=(",",":")),flush=True)
    passed=sum(v["draft_passed"] for v in rows)
    baseline=sum(v["template_passed"] for v in rows)
    unsupported=sum(v["unsupported_claim_flag"] for v in rows)
    result={
       "schema":"commandcenter.nvidia_draft_value_result.v1",
       "status":"4_of_4_fixed_synthetic_drafts_scored",
       "model":MODEL,"calls_conservatively_reserved":4,
       "drafts_attempted":4,"drafts_passed_objective_gate":passed,
       "template_baseline_passed_objective_gate":baseline,
       "unsupported_claim_flags":unsupported,
       "qualitative_value_over_templates":"NOT_MEASURED_HUMAN_REVIEW_REQUIRED",
       "automatic_model_promotion":False,"command_execution":False,
       "customer_messages_sent":False,"raw_drafts_exposed":False,
       "outcome":"TEMPLATE_MATCH_OR_UNPROVEN_LIFT" if passed==baseline else "MODEL_UNDERPERFORMS_TEMPLATE_GATE"
    }
    print("NVIDIA_DRAFT_VALUE_SUMMARY="+json.dumps(result,sort_keys=True,separators=(",",":")),flush=True)
    print("NVIDIA_DRAFT_VALUE_COVERAGE=PASS",flush=True)

if __name__=="__main__":
    try:main()
    except (RuntimeError,OSError,ValueError) as exc:
        print("NVIDIA_DRAFT_VALUE_CAMPAIGN_HELD="+str(exc),flush=True)
        raise SystemExit(1)
