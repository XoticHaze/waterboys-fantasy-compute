"""Bounded GitHub public-synthetic NVIDIA release run metadata observer.

No Cloudflare token, inference, private data or deployment. The observed run
and artifacts require separate verification before any source admission.
"""
from __future__ import annotations
import json,os,re,sys,time
from pathlib import Path
from urllib.request import Request,urlopen
REPO="XoticHaze/waterboys-fantasy-compute"
WORKFLOW="nvidia-bound-worker-redeploy-preflight-once.yml"
RELEASE_SHA="f4011b5ba23a805bb9cbbce9c811f7e1493db4d0"
SOURCE_SHA="0d5131a1fec357c3317973c24febecee6f98818b"
TRIGGER="ops/nvidia_release_readback_once.txt"
MARKER="NVIDIA_V4_RELEASE_READBACK_V1_"+RELEASE_SHA[:16]
PATTERN=re.compile(r"observe=v1;release_sha="+RELEASE_SHA+r";worker_source="+SOURCE_SHA+
                   r";workflow="+WORKFLOW+r";nonce=([A-Za-z0-9_-]{12,64})")
def validate_trigger(raw):
    if not isinstance(raw,str) or len(raw)>400 or PATTERN.fullmatch(raw.strip()) is None:
        raise ValueError("exact_readback_trigger_required")
    return True
def select_run(doc):
    if not isinstance(doc,dict) or not isinstance(doc.get("workflow_runs"),list):
        raise ValueError("invalid_github_runs")
    rows=[x for x in doc["workflow_runs"] if isinstance(x,dict) and
          x.get("head_sha")==RELEASE_SHA and x.get("event")=="push" and
          x.get("head_branch")=="main" and
          str(x.get("path","")).startswith(".github/workflows/"+WORKFLOW) and
          isinstance(x.get("id"),int) and x["id"]>0]
    if len(rows)>1:raise ValueError("ambiguous_github_run")
    return rows[0] if rows else None
def summarize(run,jobs,artifacts):
    if run is None:return {"status":"NOT_DISCOVERED","release_sha":RELEASE_SHA}
    if not isinstance(jobs,dict) or not isinstance(jobs.get("jobs"),list):
        raise ValueError("invalid_github_jobs")
    if not isinstance(artifacts,dict) or not isinstance(artifacts.get("artifacts"),list):
        raise ValueError("invalid_github_artifacts")
    jj=[x for x in jobs["jobs"] if isinstance(x,dict) and
        x.get("name")=="exact-target-bound-redeploy"]
    if len(jj)!=1:raise ValueError("exact_release_job_missing")
    aa=[x for x in artifacts["artifacts"] if isinstance(x,dict) and
        x.get("name")=="nvidia-v4-reviewed-release-version"]
    if len(aa)>1:raise ValueError("duplicate_version_artifact")
    a=aa[0] if aa else None
    j=jj[0]
    return {"status":"COMPLETED" if run.get("status")=="completed" else "NOT_TERMINAL",
        "release_sha":RELEASE_SHA,"run_id":run["id"],"run_status":run.get("status"),
        "run_conclusion":run.get("conclusion"),"run_attempt":run.get("run_attempt"),
        "job_id":j.get("id"),"job_status":j.get("status"),
        "job_conclusion":j.get("conclusion"),
        "version_artifact_id":a.get("id") if a else None,
        "version_artifact_expired":a.get("expired") if a else None,
        "source_sha":SOURCE_SHA,"claims_cloudflare_source_verified":False,
        "claims_model_inference_complete":False,"private_input_used":False}
def main():
    if (os.environ.get("GITHUB_REPOSITORY")!=REPO or
        os.environ.get("GITHUB_EVENT_NAME")!="push" or
        os.environ.get("GITHUB_REF")!="refs/heads/main" or
        not re.fullmatch(r"[0-9]{6,20}",os.environ.get("GITHUB_RUN_ID",""))):
        raise RuntimeError("untrusted_readback_host")
    validate_trigger(Path(TRIGGER).read_text(encoding="utf-8"))
    token=os.environ.get("GITHUB_TOKEN","")
    if len(token)<12:raise RuntimeError("github_token_missing")
    headers={"Authorization":"Bearer "+token,
             "Accept":"application/vnd.github+json",
             "User-Agent":"cc-nvidia-public-synthetic-run-readback-v1",
             "X-GitHub-Api-Version":"2022-11-28"}
    def api(relative,method="GET",body=None):
        if not relative.startswith("/"):raise RuntimeError("relative_api_only")
        data=None if body is None else json.dumps(body).encode("utf-8")
        req=Request("https://api.github.com/repos/"+REPO+relative,
                    headers={**headers,**({"Content-Type":"application/json"} if data else {})},
                    data=data,method=method)
        with urlopen(req,timeout=20) as response:return json.load(response)
    run=None
    for attempt in range(12):
        run=select_run(api("/actions/workflows/"+WORKFLOW+
                           "/runs?event=push&head_sha="+RELEASE_SHA+"&per_page=20"))
        if run is not None and run.get("status")=="completed":break
        if attempt<11:time.sleep(15)
    if run:
        rid=str(run["id"])
        jobs=api("/actions/runs/"+rid+"/jobs?per_page=100")
        artifacts=api("/actions/runs/"+rid+"/artifacts?per_page=100")
    else:
        jobs={"jobs":[]};artifacts={"artifacts":[]}
    summary=summarize(run,jobs,artifacts)
    note=("**"+MARKER+"**\n\nPublic synthetic NVIDIA release metadata only. "
          "This is NOT independent Worker-source admission or model inference proof.\n\n"
          +json.dumps(summary,sort_keys=True,indent=2)+"\n\n"
          "Origin: MW-20261103065614536; verify run/job/artifact independently.")
    old=api("/issues/51/comments?per_page=100")
    if not isinstance(old,list):raise ValueError("invalid_issue_comment_listing")
    if any(isinstance(x,dict) and MARKER in x.get("body","") for x in old):
        print("NVIDIA_V4_READBACK_ALREADY_PUBLISHED")
        return
    response=api("/issues/51/comments",method="POST",body={"body":note})
    if not isinstance(response,dict) or not isinstance(response.get("id"),int):
        raise RuntimeError("github_readback_comment_not_confirmed")
    print("NVIDIA_V4_RELEASE_READBACK_PUBLIC_METADATA_PUBLISHED=PASS")
    print("NVIDIA_V4_RELEASE_RUN_ID="+str(summary.get("run_id","unknown")))
    print("NVIDIA_V4_RELEASE_TERMINAL_STATE="+summary["status"])
    print("NVIDIA_V4_RELEASE_PRIVATE_DATA_EXPORTED=false")
if __name__=="__main__":
    try:main()
    except Exception:
        print("NVIDIA_V4_RELEASE_READBACK_HELD_SAFE_ERROR",file=sys.stderr)
        raise SystemExit(1)
