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

def access_app_status(token: str) -> dict:
    """GET only. Never print AUD, owner email, session, policy subjects."""
    url = API + f"/accounts/{ACCOUNT}/access/apps?name=CC%20Shared%20Worker%20Factory&exact=true&per_page=10"
    req = urllib.request.Request(
        url, method="GET",
        headers={"Authorization": "Bearer " + token,
                 "Accept": "application/json",
                 "User-Agent": "cc-factory-access-app-readonly-v1"},
    )
    try:
        with urllib.request.urlopen(req, timeout=16) as response:
            status = response.status
            data = json.loads(response.read(120000))
    except urllib.error.HTTPError as exc:
        return {"read_http": exc.code, "existing_app_confirmed": False,
                "aud_present": False, "worker_destination_found": False}
    except (ValueError, UnicodeDecodeError, urllib.error.URLError, TimeoutError):
        return {"read_http": "NOT_VERIFIED", "existing_app_confirmed": False,
                "aud_present": False, "worker_destination_found": False}
    if status != 200 or not isinstance(data, dict) or data.get("success") is not True:
        return {"read_http": status, "existing_app_confirmed": False,
                "aud_present": False, "worker_destination_found": False}
    result = data.get("result") or []
    if not isinstance(result, list):
        result = []
    exact = [r for r in result if isinstance(r, dict)
             and r.get("name") == "CC Shared Worker Factory"]
    app = exact[0] if len(exact) == 1 else {}
    # Worker target matcher is supportive evidence, not an exact policy attestation.
    target = "shared-compute-worker-factory" in json.dumps(app, ensure_ascii=True)
    return {"read_http": status, "existing_app_confirmed": len(exact) == 1,
            "aud_present": bool(app.get("aud")), "worker_destination_found": target,
            "account_id_output": False, "aud_or_identity_exported": False}


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
        "protected_access_application_readback": access_app_status(token),
        "latest_deployment_present": bool(latest),
        "latest_deployment_created_on": (latest.get("created_on")
            if isinstance(latest.get("created_on"), str) else None),
        "operator_access_audience_binding_present": "FACTORY_ACCESS_AUD" in by_name,
        "operator_owner_allowlist_binding_present": "FACTORY_ALLOWED_EMAILS" in by_name,
        "owner_ui_bindings_initialized": ("FACTORY_ACCESS_AUD" in by_name and
                                          "FACTORY_ALLOWED_EMAILS" in by_name),
        "cloudflare_worker_mutations_enabled": any(
            flags[k] == "1" for k in FLAGS
        ),
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
