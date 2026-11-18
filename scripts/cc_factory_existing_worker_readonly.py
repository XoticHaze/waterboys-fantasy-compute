#!/usr/bin/env python3
"""Bounded GET-only Cloudflare factory inventory; secrets are never printed."""
from __future__ import annotations
import json
import os
import urllib.error
import urllib.request

ACCOUNT = "ce43cd7b917d98a4bb4866d30eed99c0"
WORKER = "shared-compute-worker-factory"
API = "https://api.cloudflare.com/client/v4"
FLAGS = (
    "FACTORY_EXECUTOR_ENABLED",
    "FACTORY_CREATE_ENABLED",
    "FACTORY_SCOPED_TOKEN_ENABLED",
)
PRIVILEGED = (
    "FACTORY_WORKERS_ADMIN",
    "FACTORY_TOKEN_ISSUER",
    "FACTORY_SECRET_WRITER",
    "FACTORY_QUEUE_GITHUB_TOKEN",
)
def read(token: str, suffix: str) -> tuple[int, dict]:
    if not suffix.startswith("/accounts/" + ACCOUNT + "/workers/scripts/" + WORKER + "/"):
        raise ValueError("endpoint not pinned")
    request = urllib.request.Request(
        API + suffix, headers={"Authorization": "Bearer " + token,
            "Accept": "application/json", "User-Agent": "cc-factory-readonly-v1"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=16) as response:
            status, raw = response.status, response.read(120000)
    except urllib.error.HTTPError as exc:
        status, raw = exc.code, b""
    if status != 200:
        return status, {}
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return status, {}
    return status, data if isinstance(data, dict) else {}

def main() -> int:
    if os.getenv("CLOUDFLARE_ACCOUNT_ID") != ACCOUNT:
        raise SystemExit("FACTORY_AUDIT_WRONG_ACCOUNT")
    token = os.getenv("CLOUDFLARE_API_TOKEN", "")
    if len(token) < 20:
        raise SystemExit("FACTORY_AUDIT_EXISTING_IDENTITY_ABSENT")
    settings_status, doc = read(token, f"/accounts/{ACCOUNT}/workers/scripts/{WORKER}/settings")
    body = doc.get("result") if doc.get("success") is True else None
    if not isinstance(body, dict):
        body = {}
    bindings = body.get("bindings")
    if not isinstance(bindings, list):
        bindings = []
    by_name = {x.get("name"): x for x in bindings if isinstance(x, dict) and
               isinstance(x.get("name"), str)}
    flags = {k: by_name.get(k, {}).get("text") if
             by_name.get(k, {}).get("text") in ("0", "1") else "UNVERIFIED"
             for k in FLAGS}
    privileged = {k: ("PRESENT" if k in by_name else "NOT_LISTED")
                  for k in PRIVILEGED}
    dep_status, dep_doc = read(token, f"/accounts/{ACCOUNT}/workers/scripts/{WORKER}/deployments")
    deps = dep_doc.get("result") if dep_doc.get("success") is True else None
    if isinstance(deps, dict):
        deps = deps.get("deployments") or []
    if not isinstance(deps, list):
        deps = []
    latest = deps[0] if deps and isinstance(deps[0], dict) else {}
    receipt = {
        "schema": "commandcenter.cloudflare.factory_existing_worker_readonly.v1",
        "account_role": "ORIGINAL_SLENDERIQ_ORDINARY_ONLY",
        "worker": WORKER,
        "read_only": True,
        "mutations": 0,
        "settings_http": settings_status,
        "deployments_http": dep_status,
        "bindings_listed": sorted(k for k in by_name if
            k in FLAGS + PRIVILEGED + ("FACTORY_LEDGER", "FACTORY_ACCESS_AUD", "FACTORY_ALLOWED_EMAILS")),
        "activation_flags": flags,
        "privileged_binding_presence": privileged,
        "ledger_binding_present": "FACTORY_LEDGER" in by_name,
        "latest_deployment_present": bool(latest),
        "latest_deployment_created_on": (latest.get("created_on")
            if isinstance(latest.get("created_on"), str) else None),
        "credential_values_exported": False,
        "runtime_source_attested": False,
        "neutral_account_mutation_authority": False,
    }
    print(json.dumps(receipt, sort_keys=True))
    if settings_status != 200:
        raise SystemExit("FACTORY_READBACK_HOLD_SETTINGS_NOT_ACCESSIBLE")
    print("CC_EXISTING_FACTORY_WORKER_SETTINGS_READABLE=PASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
