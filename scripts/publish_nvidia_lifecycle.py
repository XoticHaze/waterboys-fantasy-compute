"""Publish public model metadata only to the fixed evidence branch."""
from __future__ import annotations
import base64
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO = "XoticHaze/waterboys-fantasy-compute"
BRANCH = "evidence/nvidia-model-lifecycle"
PATH = "ops/nvidia-model-lifecycle.json"
ENDPOINT = f"repos/{REPO}/contents/{PATH}"
def call(args, body=None):
    return subprocess.run(["gh","api",*args],input=body,text=True,capture_output=True,timeout=30)
def stamp(doc):
    return datetime.fromisoformat(doc["catalog"]["observed_at"].replace("Z","+00:00"))
def main():
    if os.environ.get("GITHUB_REPOSITORY")!=REPO or os.environ.get("GITHUB_REF")!="refs/heads/main":
        raise ValueError("unexpected publication source")
    raw=Path(sys.argv[1]).read_bytes()
    if len(raw)>200000:
        raise ValueError("artifact too large")
    doc=json.loads(raw)
    if (doc.get("schema")!="commandcenter.nvidia_catalog_lifecycle.v1"
            or doc.get("activation_authorized") is not False
            or doc["catalog"]["run_id"]!=int(os.environ["GITHUB_RUN_ID"])
            or doc["catalog"]["head_sha"]!=os.environ["GITHUB_SHA"]):
        raise ValueError("unexpected artifact identity")
    previous=call([ENDPOINT+"?ref="+BRANCH])
    body={"message":"Refresh shared NVIDIA model lifecycle "+str(doc["catalog"]["run_id"]),
          "branch":BRANCH,"content":base64.b64encode(raw).decode("ascii")}
    if previous.returncode==0:
        current=json.loads(previous.stdout)
        old=json.loads(base64.b64decode(current["content"]))
        if stamp(old)>=stamp(doc):
            print("NVIDIA_PUBLICATION_ALREADY_CURRENT")
            return
        body["sha"]=current["sha"]
    elif "HTTP 404" not in previous.stderr:
        raise RuntimeError("prior publication read failed")
    updated=call(["--method","PUT",ENDPOINT,"--input","-"],json.dumps(body))
    if updated.returncode:
        raise RuntimeError("publication CAS failed")
    readback=call([ENDPOINT+"?ref="+BRANCH])
    if readback.returncode or base64.b64decode(json.loads(readback.stdout)["content"])!=raw:
        raise RuntimeError("publication readback mismatch")
    print("NVIDIA_SHARED_PUBLICATION_VERIFIED="+json.loads(readback.stdout)["sha"])
if __name__=="__main__":
    main()
