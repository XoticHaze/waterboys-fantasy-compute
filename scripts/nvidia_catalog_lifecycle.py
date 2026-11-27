#!/usr/bin/env python3
"""Catalog-first advisory lifecycle. Reuses public synthetic benchmark job logs.
No provider requests, model configuration, secrets or consumer data here.
"""
from __future__ import annotations
import argparse
import json
import re
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
from statistics import median

MODEL = re.compile(r"^[A-Za-z0-9_.:-]{2,80}/[A-Za-z0-9_.:-]{2,120}$")
TASKS = frozenset(("logic", "math", "json", "tool_call"))
LOG = re.compile(r"(\d{4}-\d\d-\d\dT\S+Z) NVIDIA_(?:ROLE|CAMPAIGN)_OBSERVATION=(\{.*\})$")
REPO = "XoticHaze/waterboys-fantasy-compute"
WORKFLOW = "nvidia-private-role-benchmark-batch.yml"

def utc(s):
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("timezone required")
    return dt.astimezone(timezone.utc)

def safe_rows(rows):
    for row in rows:
        if not isinstance(row, dict):
            continue
        model = row.get("model")
        if not isinstance(model, str) or not MODEL.fullmatch(model) or row.get("task") not in TASKS:
            continue
        if type(row.get("run")) is not int or type(row.get("job")) is not int:
            continue
        try:
            utc(row["at"])
        except (TypeError, ValueError, KeyError):
            continue
        http = row.get("http")
        latency = row.get("latency_ms")
        if http is not None and (type(http) is not int or not 100 <= http <= 599):
            continue
        if latency is not None and (type(latency) is not int or not 0 <= latency <= 120000):
            continue
        yield {k: row.get(k) for k in ("at", "run", "job", "model", "task", "http", "latency_ms", "passed", "format_valid", "error")}

def api(path):
    return json.loads(subprocess.check_output(["gh", "api", path], timeout=45, text=True))

def history(now):
    """Only existing public benchmark workflow; no reruns, no artifact prompts."""
    cutoff = (now - timedelta(days=35)).date().isoformat()
    data = api(f"repos/{REPO}/actions/workflows/{WORKFLOW}/runs?per_page=100&created=>={cutoff}")
    if data.get("total_count", 0) > 100:
        raise RuntimeError("history window exceeds one page; extend bounded pagination")
    for run in data.get("workflow_runs", []):
        if run.get("status") != "completed" or run.get("event") != "push":
            continue
        rid = run["id"]
        # Catalog-only jobs have no observations; skip only after actual logs.
        jobs = api(f"repos/{REPO}/actions/runs/{rid}/jobs?per_page=100")
        for job in jobs["jobs"]:
            if job.get("name") != "synthetic-roles" or job.get("status") != "completed":
                continue
            jid = job["id"]
            log = subprocess.check_output(["gh","api","--allow-escape-sequences",f"repos/{REPO}/actions/jobs/{jid}/logs"], timeout=45, text=True)
            for line in log.splitlines():
                match = LOG.search(line)
                if match:
                    yield {"at":match[1],"run":rid,"job":jid,**json.loads(match[2])}

def project(catalog, observations, now, history_complete):
    all_ids, eligible = catalog["catalog_model_ids"], catalog["eligible_model_ids"]
    if (catalog["catalog_http"] != 200 or catalog["calls"] != 1 or
        not 0 <= (now-utc(catalog["observed_at"])).total_seconds() <= 86400 or
        any(not isinstance(v,list) or len(v)>150 or len(set(v))!=len(v) or
            not all(isinstance(m,str) and MODEL.fullmatch(m) for m in v) for v in (all_ids,eligible)) or
        not set(eligible)<=set(all_ids)):
        raise ValueError("unverified catalog")
    groups = {}
    for row in safe_rows(observations):
        if utc(row["at"]) > now:
            continue
        key = (row["model"],row["run"],row["job"])
        tasks = groups.setdefault(key,{})
        old = tasks.get(row["task"])
        if old is None or utc(row["at"]) > utc(old["at"]):
            tasks[row["task"]] = row
    latest = {}
    for (model,run,job), tasks in groups.items():
        stamp = max(utc(r["at"]) for r in tasks.values())
        if model not in latest or stamp > latest[model][0]:
            latest[model] = stamp,run,job,tasks
    due, retained, ranked, absent = [],[],[],[]
    for model in eligible:
        if model not in latest:
            due.append({"model":model,"reason":"no_prior_benchmark"})
            continue
        stamp,run,job,tasks = latest[model]
        age = (now-stamp).total_seconds()
        passed = set(tasks)==TASKS and all(r["http"]==200 and r["passed"] is True and r["latency_ms"] is not None for r in tasks.values())
        # A completed negative benchmark is evidence too; don't retry it daily.
        rec = {"model":model,"run_id":run,"job_id":job,"observed_at":stamp.isoformat(),"passed_tasks":sum(r["passed"] is True and r["http"]==200 for r in tasks.values()),"attempted_tasks":len(tasks)}
        if age >= 7*86400:
            due.append({**rec,"reason":"weekly_requalification_due"})
        else:
            retained.append(rec)
        if passed and age < 7*86400:
            ranked.append({**rec,"p50_ms":median(r["latency_ms"] for r in tasks.values())})
    for model in sorted(set(latest)-set(all_ids)):
        absent.append(model)
    ranked.sort(key=lambda r:(r["p50_ms"],r["model"]))
    return {"schema":"commandcenter.nvidia_catalog_lifecycle.v1",
            "catalog":catalog,"history_complete":history_complete,
            "retained_benchmarks":retained,"benchmark_due":due,
            "not_in_current_catalog":absent,"ranked_assist_candidates":ranked,
            "automatic_completion_calls":0,"activation_authorized":False,
            "next_action":"exact_model_benchmark_pending_budget_and_selector" if due else "reuse_current_benchmarks"}

def main():
    p=argparse.ArgumentParser()
    for name in ("catalog","seed","output"):
        p.add_argument("--"+name,required=True,type=Path)
    p.add_argument("--github-history",action="store_true")
    args=p.parse_args()
    now=datetime.now(timezone.utc)
    rows=json.loads(args.seed.read_text())["observations"]
    complete=False
    if args.github_history:
        try:
            rows.extend(history(now))
            complete=True
        except (subprocess.SubprocessError,RuntimeError,ValueError,KeyError):
            print("NVIDIA_HISTORY_PARTIAL_SEED_RETAINED")
    result=project(json.loads(args.catalog.read_text()),rows,now,complete)
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("NVIDIA_LIFECYCLE_COUNTS="+json.dumps({k:len(result[k]) for k in ("benchmark_due","retained_benchmarks","ranked_assist_candidates","not_in_current_catalog")}))
if __name__=="__main__":
    main()
