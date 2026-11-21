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

def legacy_deploy_token_scope_readback(token: str) -> dict:
    """GET-only self-token scope metadata. Never log token ID, name, grants or email.

    Cloudflare may deny detail even when the token successfully deploys. This
    result is a discriminator, NEVER a proof of effective write DENY.
    """
    import re
    paths = [
        ("USER_TOKEN", "/user/tokens/verify", "/user/tokens/"),
        ("ACCOUNT_TOKEN", "/accounts/" + ACCOUNT + "/tokens/verify",
         "/accounts/" + ACCOUNT + "/tokens/"),
    ]
    out = {
        "schema": "commandcenter.cloudflare.factory_legacy_token_metadata.v1",
        "credential_role": "EXISTING_WATERBOYS_PUBLIC_RUNNER_DEPLOY_TOKEN",
        "read_only": True, "cloudflare_mutations": 0,
        "credential_values_exported": False, "token_id_exported": False,
        "token_name_or_email_exported": False, "policy_resources_exported": False,
        "factory_write_denial_live_proven": False,
        "token_identity_class": "NOT_VERIFIED",
        "self_verify_http": "NOT_VERIFIED",
        "self_detail_http": "NOT_ATTEMPTED",
        "policy_shape": "UNAVAILABLE",
        "manual_scope_review_still_required": True,
    }

    def get(suffix: str) -> tuple[int | str, dict]:
        # A caller may never add arbitrary API paths, use POST or follow redirects.
        allowed = (suffix == "/user/tokens/verify"
                   or suffix == "/accounts/" + ACCOUNT + "/tokens/verify"
                   or bool(re.fullmatch(r"/user/tokens/[a-f0-9]{32}", suffix))
                   or bool(re.fullmatch(
                       r"/accounts/" + ACCOUNT + r"/tokens/[a-f0-9]{32}", suffix)))
        if not allowed:
            raise ValueError("unapproved_cloudflare_token_metadata_path")
        req = urllib.request.Request(API + suffix, method="GET",
            headers={"Authorization": "Bearer " + token,
                     "Accept": "application/json",
                     "User-Agent": "cc-factory-existing-token-metadata-readonly-v1"})
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None
        opener = urllib.request.build_opener(NoRedirect())
        try:
            with opener.open(req, timeout=12) as resp:
                status, raw = resp.status, resp.read(65536)
        except urllib.error.HTTPError as e:
            return e.code, {}
        except (urllib.error.URLError, TimeoutError, ValueError, OSError):
            return "UNAVAILABLE", {}
        if status != 200:
            return status, {}
        try:
            doc = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            return status, {}
        return status, doc if isinstance(doc, dict) else {}

    for role, verify_path, detail_prefix in paths:
        http, document = get(verify_path)
        result = document.get("result") if document.get("success") is True else None
        if not isinstance(result, dict) or not re.fullmatch(
                r"[a-f0-9]{32}", str(result.get("id", ""))) or (
                result.get("status") != "active"):
            continue
        out["token_identity_class"] = role
        out["self_verify_http"] = http
        status, details = get(detail_prefix + result["id"])
        out["self_detail_http"] = status
        node = details.get("result") if details.get("success") is True else None
        if isinstance(node, dict) and isinstance(node.get("policies"), list):
            policies = node["policies"]
            valid = (len(policies) < 100 and all(
                isinstance(x, dict) and x.get("effect") in ("allow", "deny")
                and isinstance(x.get("resources"), dict) for x in policies))
            out["policy_shape"] = (
                "VISIBLE_REQUIRES_INDEPENDENT_EFFECTIVE_DENY_PROOF"
                if valid else "UNEXPECTED_DETAILS")
            out["policy_entry_count"] = len(policies) if valid else None
            out["allows_present"] = (any(x.get("effect") == "allow"
                                         for x in policies) if valid else None)
            out["denies_present"] = (any(x.get("effect") == "deny"
                                        for x in policies) if valid else None)
        return out
    return out


def scoped_existing_deploy_candidate_readback(token: str) -> dict:
    """GET-only compare existing R2 editor against fixed current Worker names.

    No mutation or write-DENY proof, no token/account policy values exported.
    """
    from urllib.parse import urlsplit
    names = ("waterboys-fantasy-broker", WORKER)
    output = {
        "schema": "commandcenter.cloudflare.scoped_existing_editor_readonly.v1",
        "credential_alias": "CLOUDFLARE_DEPLOY_TOKEN_R2",
        "configured": bool(token),
        "read_only": True,
        "cloudflare_mutations": 0,
        "token_value_exported": False,
        "existing_broker_settings_http": "NOT_ATTEMPTED",
        "protected_factory_settings_http": "NOT_ATTEMPTED",
        "scoped_deploy_write_admission_proven": False,
        "factory_write_denial_proven": False,
    }
    if not token:
        return output

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    opener = urllib.request.build_opener(NoRedirect())
    for worker in names:
        # Fixed approved names only, never caller-provided paths/redirects.
        url = API + "/accounts/" + ACCOUNT + "/workers/scripts/" + worker + "/settings"
        req = urllib.request.Request(url, method="GET",
            headers={"Authorization": "Bearer " + token,
                     "Accept": "application/json",
                     "User-Agent": "cc-factory-scoped-deploy-comparison-v1"})
        try:
            with opener.open(req, timeout=12) as response:
                status, raw = response.status, response.read(120000)
            try:
                node = json.loads(raw)
            except (ValueError, UnicodeDecodeError):
                node = {}
            status = status if node.get("success") is True else "UNVERIFIED"
        except urllib.error.HTTPError as e:
            status = e.code
        except (urllib.error.URLError, TimeoutError, ValueError, OSError):
            status = "UNAVAILABLE"
        field = ("existing_broker_settings_http" if worker == names[0]
                 else "protected_factory_settings_http")
        output[field] = status
    return output


def access_app_status(token: str) -> dict:
    """GET only. Never print AUD, owner email, session, policy subjects."""
    url = API + f"/accounts/{ACCOUNT}/access/apps?per_page=100&page=1"
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
    if isinstance(result, dict):
        result = result.get("apps") or result.get("data") or result.get("items") or []
    if not isinstance(result, list):
        result = []
    exact = [r for r in result if isinstance(r, dict)
             and r.get("name") == "CC Shared Worker Factory"]
    app = exact[0] if len(exact) == 1 else {}
    # Worker target matcher is supportive evidence, not an exact policy attestation.
    target = "shared-compute-worker-factory" in json.dumps(app, ensure_ascii=True)
    return {"read_http": status, "existing_app_confirmed": len(exact) == 1,
            "aud_present": bool(app.get("aud")), "worker_destination_found": target,
            "returned_app_count": len(result),
            "account_id_output": False, "aud_or_identity_exported": False}


def factory_worker_id_readback(token: str) -> dict:
    """Strict GET-only resolve of target immutable ID; no unrelated rows escape."""
    import re
    found = []
    try:
        for page in range(1, 11):
            req = urllib.request.Request(
                API + f"/accounts/{ACCOUNT}/workers/workers?per_page=100&page={page}",
                method="GET", headers={
                    "Authorization": "Bearer " + token,
                    "Accept": "application/json",
                    "User-Agent": "cc-factory-id-readonly-v1"})
            with urllib.request.urlopen(req, timeout=16) as response:
                data = json.loads(response.read(120000))
            if not isinstance(data, dict) or data.get("success") is not True:
                return {"status": "GET_REJECTED", "id_verified": False}
            rows = data.get("result") or []
            if isinstance(rows, dict):
                rows = rows.get("workers") or rows.get("data") or list(rows.values())
            if not isinstance(rows, list):
                return {"status": "UNEXPECTED_RESPONSE", "id_verified": False}
            found.extend([r for r in rows if isinstance(r, dict)
                          and r.get("name") == WORKER])
            if len(rows) < 100:
                break
        else:
            return {"status": "PAGINATION_INCOMPLETE", "id_verified": False}
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError,
            ValueError, UnicodeDecodeError):
        return {"status": "READ_UNAVAILABLE", "id_verified": False}
    if len(found) != 1 or not re.fullmatch(r"[a-f0-9]{32}", str(found[0].get("id", ""))):
        return {"status": "FACTORY_ID_NOT_UNIQUE_OR_MISSING", "id_verified": False}
    return {"status": "EXACT_IMMUTABLE_FACTORY_ID_VERIFIED",
            "id_verified": True, "factory_worker_id": found[0]["id"],
            "other_worker_ids_exported": False}


def fixed_factory_deployment_identity(latest: dict) -> dict:
    """Sanitized UUID readback from an existing immutable deployment, never source approval."""
    import re
    uuid = re.compile(r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}\Z")
    result={"deployment_id":None, "full_traffic_version_id":None,
            "unique_full_traffic_version":False,
            "source_content_attested":False}
    if not isinstance(latest,dict):return result
    if isinstance(latest.get("id"),str) and uuid.fullmatch(latest["id"]):
        result["deployment_id"]=latest["id"]
    versions=latest.get("versions") or []
    if not isinstance(versions,list) or len(versions)>50:return result
    active=[v.get("version_id") for v in versions
            if isinstance(v,dict) and v.get("percentage")==100
            and isinstance(v.get("version_id"),str) and uuid.fullmatch(v["version_id"])]
    if len(active)==1 and len(versions)==1:
        result["full_traffic_version_id"]=active[0]
        result["unique_full_traffic_version"]=True
    return result


def public_audit_report(receipt: dict, run_id: str, head_sha: str) -> dict:
    """Allowlisted nonsecret JSON that a separate credential-free job can publish."""
    import re
    from datetime import datetime, timezone
    if not re.fullmatch(r"[0-9]{5,20}", run_id) or not re.fullmatch(
            r"[a-f0-9]{40}", head_sha):
        raise ValueError("missing_exact_public_run_identity")
    legacy = receipt.get("existing_legacy_token_scope_metadata") or {}
    scoped = receipt.get("existing_scoped_deploy_comparison") or {}
    flags = receipt.get("activation_flags") or {}
    def values(data, names):
        return {k: data.get(k) for k in names}
    return {
        "schema": "commandcenter.cloudflare.factory_scope_audit_receipt.v1",
        "github_run_id": run_id,
        "github_head_sha": head_sha,
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_role": "EXISTING_WATERBOYS_PUBLIC_READONLY_WORKFLOW",
        "factory_settings_http": receipt.get("settings_http"),
        "factory_id_verified": bool(
            (receipt.get("existing_factory_immutable_id") or {}).get("id_verified")),
        "factory_deployment_identity": receipt.get("factory_deployment_identity"),
        "access_app_present": bool(
            (receipt.get("protected_access_application_readback") or {}).get(
                "existing_app_confirmed")),
        "factory_execution_flags": values(flags, (
            "FACTORY_EXECUTOR_ENABLED", "FACTORY_CREATE_ENABLED",
            "FACTORY_SCOPED_TOKEN_ENABLED")),
        "legacy_token": values(legacy, (
            "token_identity_class", "self_verify_http", "self_detail_http",
            "policy_shape", "policy_entry_count", "allows_present", "denies_present")),
        "scoped_r2_token": values(scoped, (
            "configured", "existing_broker_settings_http",
            "protected_factory_settings_http")),
        "cloudflare_mutations": 0,
        "credential_values_exported": False,
        "write_denial_proven": False,
        "release_or_admin_admitted": False,
        "classification": "GET_ONLY_SCOPE_EVIDENCE_NOT_WRITE_DENIAL_PROOF",
    }


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
        "existing_factory_immutable_id": factory_worker_id_readback(token),
        "latest_deployment_present": bool(latest),
        "factory_deployment_identity": fixed_factory_deployment_identity(latest),
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
        "existing_legacy_token_scope_metadata": legacy_deploy_token_scope_readback(token),
        "existing_scoped_deploy_comparison": scoped_existing_deploy_candidate_readback(
            os.getenv("CLOUDFLARE_DEPLOY_TOKEN_R2", "").strip()),
    }
    print(json.dumps(receipt, sort_keys=True))
    if os.environ.get("GITHUB_ACTIONS") == "true":
        from pathlib import Path
        safe = public_audit_report(receipt, os.environ.get("GITHUB_RUN_ID", ""),
                                   os.environ.get("GITHUB_SHA", ""))
        Path("cc-factory-readback.json").write_text(
            json.dumps(safe, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    if settings_status != 200:
        raise SystemExit("FACTORY_READBACK_HOLD_SETTINGS_NOT_ACCESSIBLE")
    print("CC_EXISTING_FACTORY_WORKER_SETTINGS_READABLE=PASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
