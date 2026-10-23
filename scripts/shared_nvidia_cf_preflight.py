"""Read-only Cloudflare compute-account preflight for shared NVIDIA Worker.

Runs under existing WaterBoys cloud deployment identity, never imports or
prints NVIDIA key, Cloudflare bearer, account/store/secret identifiers.
Only GETs trusted fixed endpoints; creates and mutates nothing.

Recheck after operator deploys existing NVIDIA Secrets Store binding.
The ordinary deployment token cannot read Secrets Store metadata, so preserve
Worker binding configuration proof separately from secret-value/runtime proof.
"""
from __future__ import annotations
import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, HTTPRedirectHandler, build_opener

API = "https://api.cloudflare.com/client/v4"
HEX = re.compile(r"[a-fA-F0-9]{32}\Z")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def get_json(path, token):
    if not path.startswith("/accounts/"):
        raise ValueError("unexpected_path")
    request = Request(API + path, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/json",
        "User-Agent": "shared-nvidia-compute-readonly",
    }, method="GET")
    try:
        with build_opener(NoRedirect()).open(request, timeout=15) as response:
            status, data = int(response.status), response.read(300000)
    except HTTPError as error:
        status, data = int(error.code), error.read(300000)
    except (URLError, OSError, TimeoutError):
        return None, {}
    try:
        parsed = json.loads(data)
        return status, parsed if isinstance(parsed, dict) else {}
    except (ValueError, UnicodeDecodeError):
        return status, {}


def check(account, token, probe=get_json):
    receipt = dict(
        schema="commandcenter.shared_nvidia_cf_readonly_preflight.v1",
        read_only=True, worker_created=False, worker_deployed=False,
        nvidia_called=False, secret_value_accessed=False,
        private_ids_exported=False, binding_verified=False,
        waterboys_http=None, nvidia_worker_http=None,
        stores_http=None, secret_list_http=None,
        secret_seen=None, secret_active=None, workers_scope=None,
        classification="unattempted",
        nvidia_binding_present=False,
        nvidia_binding_observed_type="not_present",
        nvidia_binding_type_correct=False,
        nvidia_binding_secret_reference_correct=False,
        nvidia_binding_metadata_verified=False,
    )
    if not HEX.fullmatch(account or "") or not token:
        receipt["classification"] = "approved_cloudflare_identity_missing"
        return receipt
    root = "/accounts/" + account
    def call(path):
        status, body = probe(root + path, token)
        return (status if status is None or (isinstance(status, int) and 100 <= status <= 599) else None), body
    status, _ = call("/workers/scripts/waterboys-fantasy-broker/settings")
    receipt["waterboys_http"] = status
    if status != 200:
        receipt["classification"] = "ordinary_account_identity_not_proven"
        return receipt
    status, worker_settings = call("/workers/scripts/cc-shared-nvidia-inference/settings")
    receipt["nvidia_worker_http"] = status
    if status == 200 and worker_settings.get("success") is True:
        bindings = (worker_settings.get("result") or {}).get("bindings")
        bindings = bindings if isinstance(bindings, list) else []
        candidates = [b for b in bindings if isinstance(b, dict) and b.get("name") == "NVIDIA_API_KEY"]
        receipt["nvidia_binding_present"] = len(candidates) == 1
        if len(candidates) == 1:
            entry = candidates[0]
            kind = entry.get("type")
            receipt["nvidia_binding_observed_type"] = (
                kind if kind in ("secrets_store_secret", "secret_text", "secret_key",
                                  "secrets_store", "secret", "var", "plain_text")
                else "unrecognized_or_missing"
            )
            receipt["nvidia_binding_type_correct"] = entry.get("type") == "secrets_store_secret"
            receipt["nvidia_binding_secret_reference_correct"] = (
                receipt["nvidia_binding_type_correct"]
                and entry.get("secret_name") == "NVIDIA_API_KEY"
                and isinstance(entry.get("store_id"), str)
                and HEX.fullmatch(entry["store_id"]) is not None
            )
            receipt["nvidia_binding_metadata_verified"] = receipt["nvidia_binding_secret_reference_correct"]
    status, body = call("/secrets_store/stores?per_page=100")
    receipt["stores_http"] = status
    if status != 200 or body.get("success") is not True:
        receipt["classification"] = (
            "worker_secrets_store_binding_metadata_verified_store_read_denied"
            if receipt["nvidia_binding_metadata_verified"]
            else "secrets_store_read_authority_unavailable"
        )
        return receipt
    stores = body.get("result")
    if not isinstance(stores, list) or len(stores) != 1:
        receipt["classification"] = "single_compute_store_unverified"
        return receipt
    store = stores[0]
    store_id = store.get("id") if isinstance(store, dict) else None
    if not isinstance(store_id, str) or not HEX.fullmatch(store_id):
        receipt["classification"] = "store_id_metadata_invalid"
        return receipt
    status, body = call("/secrets_store/stores/" + store_id + "/secrets?per_page=100")
    receipt["secret_list_http"] = status
    if status != 200 or body.get("success") is not True or not isinstance(body.get("result"), list):
        receipt["classification"] = "store_secret_list_unavailable"
        return receipt
    matches = [s for s in body["result"] if isinstance(s, dict) and s.get("name") == "NVIDIA_API_KEY"]
    receipt["secret_seen"] = len(matches) == 1
    if len(matches) != 1:
        receipt["classification"] = "target_secret_not_verified_by_runner"
        return receipt
    secret = matches[0]
    receipt["secret_active"] = secret.get("status") == "active"
    receipt["workers_scope"] = isinstance(secret.get("scopes"), list) and "workers" in secret["scopes"]
    if not receipt["secret_active"] or not receipt["workers_scope"]:
        receipt["classification"] = "secret_scope_or_status_mismatch"
        return receipt
    receipt["classification"] = (
        "worker_present_binding_requires_separate_proof"
        if receipt["nvidia_worker_http"] == 200
        else "compute_secret_proven_worker_creation_or_access_pending"
    )
    return receipt


if __name__ == "__main__":
    result = check(os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip(),
                   os.environ.get("CLOUDFLARE_API_TOKEN", "").strip())
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(2 if result["classification"] == "approved_cloudflare_identity_missing" else 0)
