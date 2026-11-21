#!/usr/bin/env python3
"""Single-Worker Editor deployment admission for the existing WaterBoys Worker.

This is a GET-only diagnostic performed by the existing public deploy job.
It can reject a too-broad token, but HTTP 403/404 is not a live write-denial
proof. An owner must separately attest Individual Workers -> Editor resource
scope before activating the scoped-token cutover.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

API = "https://api.cloudflare.com/client/v4"
ORIGINAL_ACCOUNT = "ce43cd7b917d98a4bb4866d30eed99c0"
NEUTRAL_ACCOUNT = "b33595eb85f346b0d1bf201810b4499a"
ALLOW_WORKER = "waterboys-fantasy-broker"
FACTORY_WORKER = "shared-compute-worker-factory"
OTHER_ORIGINAL_WORKERS = ("fleet-authority", "mmibkr-operator-console")
PROTECTED_NEUTRAL = (
    "reference-release-broker-v1",
    "reference-release-maintainer-v1",
    "reference-maintenance-authority-v1",
)

# Fixed allowlist, no caller-controlled URLs, account IDs, methods or names.
TARGETS = (
    ("waterboys", ORIGINAL_ACCOUNT, ALLOW_WORKER, True),
    ("factory", ORIGINAL_ACCOUNT, FACTORY_WORKER, False),
    *(("other_original_" + name, ORIGINAL_ACCOUNT, name, False)
      for name in OTHER_ORIGINAL_WORKERS),
    *(("protected_neutral_" + name, NEUTRAL_ACCOUNT, name, False)
      for name in PROTECTED_NEUTRAL),
)

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None

def read_settings(token: str, account: str, worker: str) -> tuple[int, bool]:
    if (account, worker) not in {(a, w) for _, a, w, _ in TARGETS}:
        raise ValueError("unapproved_cloudflare_resource")
    url = f"{API}/accounts/{account}/workers/scripts/{worker}/settings"
    req = urllib.request.Request(
        url, method="GET",
        headers={"Authorization": "Bearer " + token,
                 "Accept": "application/json",
                 "User-Agent": "commandcenter-waterboys-narrow-r2-scope-v2"},
    )
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(req, timeout=15) as response:
            status = int(response.status)
            body = response.read(32769)
    except urllib.error.HTTPError as exc:
        return int(exc.code), False
    # Any redirects, oversized bodies, bad JSON or network problems fail shut.
    if status != 200 or len(body) > 32768:
        return status, False
    try:
        result = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return status, False
    return status, bool(isinstance(result, dict)
                        and result.get("success") is True)

def validate_scope(probe) -> dict:
    receipt = {
        "schema": "commandcenter.waterboys.scoped_worker_editor_readonly.v2",
        "account": "ORIGINAL_SLENDERIQ_ONLY",
        "requested_worker": ALLOW_WORKER,
        "fixed_target_count": len(TARGETS),
        "allowed_worker_metadata_read": False,
        "other_worker_metadata_inaccessible": False,
        "write_isolation_live_proven": False,
        "cloudflare_mutations": 0,
        "token_value_exported": False,
        "token_creation_or_rotation": False,
        "owner_individual_worker_editor_policy_review_required": True,
    }
    inaccessible = []
    for key, account, worker, expected_allow in TARGETS:
        status, success = probe(account, worker)
        if type(status) is not int:
            raise ValueError("unexpected_cloudflare_status")
        if expected_allow:
            if status != 200 or success is not True:
                raise ValueError("waterboys_exact_worker_access_not_verified")
            receipt["allowed_worker_metadata_read"] = True
        else:
            # Treat any 200 as a broad-credential warning. 403/404 do not
            # prove write-denial and do not replace owner policy review.
            if status not in (401, 403, 404):
                raise ValueError("scoped_credential_unexpected_other_worker_read")
            inaccessible.append(key)
    receipt["other_worker_metadata_inaccessible"] = (
        len(inaccessible) == len(TARGETS) - 1)
    receipt["result"] = "GET_ONLY_SCOPE_CONSISTENT_REQUIRES_OWNER_POLICY_AND_DEPLOY_PROOF"
    return receipt

def main() -> int:
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip().lower()
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    if account != ORIGINAL_ACCOUNT or len(token) < 20 or "\n" in token or "\r" in token:
        raise SystemExit("WATERBOYS_SCOPED_TOKEN_OR_ACCOUNT_NOT_ADMITTED")
    try:
        receipt = validate_scope(
            lambda account, worker: read_settings(token, account, worker))
    except (ValueError, urllib.error.URLError, TimeoutError, OSError) as exc:
        # No token, response body, arbitrary endpoint or secret details in logs.
        raise SystemExit("WATERBOYS_SCOPED_SCOPE_PREFLIGHT_FAIL_CLOSED") from None
    print(json.dumps(receipt, sort_keys=True))
    print("WATERBOYS_SCOPED_R2_READONLY_PREFLIGHT_PASS=1")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
