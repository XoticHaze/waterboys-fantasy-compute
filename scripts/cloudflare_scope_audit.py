from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

API="https://api.cloudflare.com/client/v4"

def get(path: str, token: str):
    req=Request(
        API+path,
        headers={
            "Authorization":"Bearer "+token,
            "Accept":"application/json",
            "User-Agent":"waterboys-cloudflare-scope-audit-r1",
        },
    )
    try:
        with urlopen(req,timeout=30) as response:
            raw=response.read()
            status=int(response.status)
    except HTTPError as exc:
        raw=exc.read()
        status=int(exc.code)
    try:
        node=json.loads(raw.decode("utf-8")) if raw else {}
    except Exception:
        node={}
    return status,node

def main() -> int:
    account=os.environ.get("CLOUDFLARE_ACCOUNT_ID","").strip()
    token=os.environ.get("CLOUDFLARE_API_TOKEN","").strip()
    if not account or not token:
        raise SystemExit("cloudflare deployment binding missing")

    verify_status,verify=get(f"/accounts/{account}/tokens/verify",token)
    owner="account"
    if verify_status != 200 or verify.get("success") is not True:
        verify_status,verify=get("/user/tokens/verify",token)
        owner="user"
    result=verify.get("result") if isinstance(verify.get("result"),dict) else {}

    workers=[
        "reference-release-broker-v1",
        "reference-release-maintainer-v1",
        "reference-maintenance-authority-v1",
        "waterboys-fantasy-broker",
    ]
    matrix={}
    for worker in workers:
        status,_=get(f"/accounts/{account}/workers/scripts/{worker}/settings",token)
        matrix[worker]=status

    receipt={
        "schema":"waterboys.cloudflare_deploy_scope_audit.r1",
        "token_owner":owner,
        "token_id":str(result.get("id") or ""),
        "token_status":str(result.get("status") or ""),
        "worker_settings_http":matrix,
        "broker_denied":matrix["reference-release-broker-v1"] in [401,403,404],
        "waterboys_reachable":matrix["waterboys-fantasy-broker"] == 200,
        "read_only":True,
        "mutation_performed":False,
        "secrets_included":False,
    }
    out=Path("rendezvous/receipts/waterboys-cloudflare-scope-audit-r1.json")
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(receipt,sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
