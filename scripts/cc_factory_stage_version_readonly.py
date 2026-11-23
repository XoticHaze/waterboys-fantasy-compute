#!/usr/bin/env python3
"""GET-only identity of the SlenderIQ factory's newest off-traffic Worker version.

Fixed account/script/endpoints. Never exports script bytes, bindings, identity
emails, tokens, or untrusted response fields. Does not attest GitHub source.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone

ACCOUNT = "ce43cd7b917d98a4bb4866d30eed99c0"
SCRIPT = "shared-compute-worker-factory"
API = "https://api.cloudflare.com/client/v4"
ACTIVE_DEPLOYMENT = "85879fcc-36d1-4c5d-b0c6-484b4159af5a"
ACTIVE_VERSION = "748797de-8fbb-42e9-8054-225086827a0c"
SOURCE_COMMIT = "97c3e7d2c948f802f4cb89017cd7164979176001"
UUID = re.compile(r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}\Z")
ALLOWED = {
    f"/accounts/{ACCOUNT}/workers/scripts/{SCRIPT}/versions?per_page=20&page=1",
    f"/accounts/{ACCOUNT}/workers/scripts/{SCRIPT}/deployments",
}


def get_only(token: str, path: str) -> tuple[int | str, dict]:
    if path not in ALLOWED:
        raise ValueError("cloudflare_endpoint_not_fixed")
    request = urllib.request.Request(
        API + path, method="GET", headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/json",
            "User-Agent": "cc-factory-offtraffic-version-readonly-v1",
        })
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(request, timeout=15) as response:
            status, data = response.status, response.read(131073)
    except urllib.error.HTTPError as exc:
        return exc.code, {}
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return "UNAVAILABLE", {}
    if status != 200 or not 0 < len(data) <= 131072:
        return status, {}
    try:
        parsed = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        return status, {}
    return status, parsed if isinstance(parsed, dict) and parsed.get("success") is True else {}


def latest_version(response: dict) -> dict:
    result = response.get("result") or []
    if isinstance(result, dict):
        result = result.get("versions") or result.get("items") or result.get("data") or []
    if not isinstance(result, list) or not 1 <= len(result) <= 20:
        return {}
    item = result[0]
    if not isinstance(item, dict) or not UUID.fullmatch(str(item.get("id", ""))):
        return {}
    meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    created = meta.get("created_on")
    origin = meta.get("source")
    return {
        "version_id": item["id"],
        "created_on": created if isinstance(created, str) and
                      re.fullmatch(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9:.]+Z", created)
                      else None,
        "source": origin if origin in ("wrangler", "api", "unknown",
                                      "dash", "integration") else "UNVERIFIED",
    }


def active_deployment(response: dict) -> dict:
    result = response.get("result") or []
    if isinstance(result, dict):
        result = result.get("deployments") or []
    if not isinstance(result, list) or not result:
        return {}
    first = result[0]
    if not isinstance(first, dict) or not UUID.fullmatch(str(first.get("id", ""))):
        return {}
    versions = first.get("versions")
    if not isinstance(versions, list) or len(versions) != 1:
        return {}
    item = versions[0]
    if not isinstance(item, dict) or item.get("percentage") != 100 or not (
            UUID.fullmatch(str(item.get("version_id", "")))):
        return {}
    return {"deployment_id": first["id"], "full_traffic_version_id": item["version_id"]}


def safe_receipt(run_id, head_sha, versions_http, version, deployments_http, deploy):
    if not re.fullmatch(r"[0-9]{5,20}", run_id) or not re.fullmatch(r"[a-f0-9]{40}", head_sha):
        raise ValueError("unverified_github_run_provenance")
    baseline = (
        deploy.get("deployment_id") == ACTIVE_DEPLOYMENT and
        deploy.get("full_traffic_version_id") == ACTIVE_VERSION
    )
    newest = version.get("version_id")
    created = version.get("created_on")
    off_traffic = bool(
        versions_http == 200 and deployments_http == 200 and baseline and
        isinstance(newest, str) and UUID.fullmatch(newest) and
        newest != ACTIVE_VERSION and
        isinstance(created, str) and created.startswith("2026-11-23T")
    )
    return {
        "schema": "commandcenter.cloudflare.factory_offtraffic_version_readonly.v1",
        "github_run_id": run_id,
        "github_head_sha": head_sha,
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "account_role": "ORIGINAL_SLENDERIQ",
        "worker": SCRIPT,
        "versions_http": versions_http,
        "deployments_http": deployments_http,
        "newest_version_id": newest if isinstance(newest, str) and UUID.fullmatch(newest) else None,
        "newest_version_created_at": created if isinstance(created, str) and
                                     len(created) <= 40 else None,
        "newest_version_source": version.get("source", "UNVERIFIED"),
        "full_traffic_version_id": deploy.get("full_traffic_version_id") if (
            isinstance(deploy.get("full_traffic_version_id"), str) and
            UUID.fullmatch(deploy["full_traffic_version_id"])) else None,
        "active_deployment_id": deploy.get("deployment_id") if (
            isinstance(deploy.get("deployment_id"), str) and
            UUID.fullmatch(deploy["deployment_id"])) else None,
        "active_baseline_unchanged": baseline,
        "newest_version_offtraffic_observed": off_traffic,
        "owner_reported_public_source_commit": SOURCE_COMMIT,
        "source_matches_reviewed_git_commit_attested": False,
        "factory_admin_admitted": False,
        "no_mac_publisher_admitted": False,
        "cloudflare_mutations": 0,
        "credential_values_exported": False,
        "classification": "STAGED_OFFTRAFFIC_VERSION_INDEPENDENTLY_OBSERVED"
        if off_traffic else "OFFTRAFFIC_VERSION_UNVERIFIED_NO_RELEASE",
    }


def main():
    if os.getenv("CLOUDFLARE_ACCOUNT_ID") != ACCOUNT:
        raise SystemExit("INVALID_FIXED_ACCOUNT")
    token = os.getenv("CLOUDFLARE_API_TOKEN", "")
    if len(token) < 20:
        raise SystemExit("EXISTING_READONLY_CREDENTIAL_NOT_CONFIGURED")
    version_path = f"/accounts/{ACCOUNT}/workers/scripts/{SCRIPT}/versions?per_page=20&page=1"
    deploy_path = f"/accounts/{ACCOUNT}/workers/scripts/{SCRIPT}/deployments"
    vs, versions = get_only(token, version_path)
    ds, deployments = get_only(token, deploy_path)
    receipt = safe_receipt(
        os.environ.get("GITHUB_RUN_ID", ""),
        os.environ.get("GITHUB_SHA", ""),
        vs, latest_version(versions), ds, active_deployment(deployments),
    )
    from pathlib import Path
    Path("cc-factory-stage-version-readback.json").write_text(
        json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print("CC_FACTORY_STAGED_VERSION_READBACK=" + receipt["classification"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
