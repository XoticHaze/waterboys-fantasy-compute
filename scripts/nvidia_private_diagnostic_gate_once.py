"""Exact-target temporary NVIDIA diagnostic admission. Never reads secret values.

This tool only toggles CC_NVIDIA_DIAGNOSTIC_ENABLED on the *existing*
cc-shared-nvidia-inference Worker in the ordinary SlenderIQ account, while
re-attesting the unchanged account Secrets Store reference on readback.

A separate always-run recovery step restores 0 after one bounded probe.
"""
from __future__ import annotations
import json
import os
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API = "https://api.cloudflare.com/client/v4"
ACCOUNT_RE = re.compile(r"^[0-9a-fA-F]{32}$")
TARGET = "cc-shared-nvidia-inference"
REFERENCE = "NVIDIA_API_KEY"
SWITCH = "CC_NVIDIA_DIAGNOSTIC_ENABLED"


def fail(reason):
    raise RuntimeError(reason)


def cf(account, token, method, relative, payload=None):
    headers = {
        "Authorization": "Bearer " + token,
        "Accept": "application/json",
        "User-Agent": "nvidia-private-fixed-diagnostic-v1",
    }
    data = None
    if payload is not None:
        # Cloudflare script/version settings PATCH accepts a multipart
        # form-data part named 'settings' containing application/json.
        boundary = "ccnvidiadiagnostics20261023"
        data = (
            "--" + boundary + "\r\n"
            'Content-Disposition: form-data; name="settings"\r\n'
            "Content-Type: application/json\r\n\r\n"
            + json.dumps(payload, separators=(",", ":")) + "\r\n"
            + "--" + boundary + "--\r\n"
        ).encode("utf-8")
        headers["Content-Type"] = "multipart/form-data; boundary=" + boundary
    req = Request(API + "/accounts/" + account + relative, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=25) as r:
            status, raw = r.status, r.read(300000)
    except HTTPError as e:
        status, raw = e.code, e.read(300000)
    except (URLError, TimeoutError, OSError):
        return None, {}
    try:
        response = json.loads(raw)
        if not isinstance(response, dict):
            response = {}
    except (UnicodeError, ValueError):
        response = {}
    return status, response


def validate_settings(doc):
    if not isinstance(doc, dict) or doc.get("success") is not True:
        fail("WORKER_SETTINGS_NOT_SUCCESSFUL")
    info = doc.get("result")
    if not isinstance(info, dict):
        fail("WORKER_SETTINGS_INVALID")
    items = info.get("bindings")
    if not isinstance(items, list) or len(items) != 2:
        fail("UNEXPECTED_BINDING_COUNT")
    mapping = {b.get("name"): b for b in items if isinstance(b, dict)}
    if set(mapping) != {REFERENCE, SWITCH}:
        fail("EXACT_WORKER_BINDING_NAMES_MISMATCH")
    key = mapping[REFERENCE]
    switch = mapping[SWITCH]
    if (key.get("type") != "secrets_store_secret"
            or key.get("secret_name") != REFERENCE
            or not isinstance(key.get("store_id"), str)
            or not ACCOUNT_RE.fullmatch(key["store_id"])):
        fail("EXISTING_ACCOUNT_SECRET_BINDING_UNVERIFIED")
    if (switch.get("type") != "plain_text"
            or switch.get("text") not in ("0", "1")):
        fail("EXISTING_DIAGNOSTIC_FLAG_UNVERIFIED")
    return key, switch["text"]


def read(account, token):
    status, doc = cf(account, token, "GET", "/workers/scripts/" + TARGET + "/settings")
    if status != 200:
        fail("EXACT_TARGET_SETTINGS_UNAVAILABLE")
    return validate_settings(doc)


def set_switch(account, token, target):
    prior_key, prior_value = read(account, token)
    if target == "1" and prior_value != "0":
        fail("ENABLE_REQUIRES_DISABLED_PRECONDITION")
    if target == "0" and prior_value == "0":
        print("NVIDIA_DIAGNOSTIC_RESTORE_ALREADY_DISABLED=1")
        return
    if target == prior_value:
        fail("UNEXPECTED_NOOP")
    # Explicitly preserve the already deployed Secrets Store ref, never
    # authorize any unrelated Worker bindings or source code mutation.
    key_binding = {
        "name": REFERENCE,
        "type": "secrets_store_secret",
        "store_id": prior_key["store_id"],
        "secret_name": REFERENCE,
    }
    vars_binding = {"name": SWITCH, "type": "plain_text", "text": target}
    status, doc = cf(account, token, "PATCH", "/workers/scripts/" + TARGET + "/settings",
                      {"bindings": [key_binding, vars_binding]})
    if status not in (200, 201) or doc.get("success") is not True:
        errors = doc.get("errors") if isinstance(doc, dict) else None
        codes = [e.get("code") for e in errors if isinstance(e, dict)] if isinstance(errors, list) else []
        safe_codes = [str(x) for x in codes if type(x) is int and 0 <= x <= 999999]
        print("NVIDIA_PATCH_CLOUDFLARE_ERROR_CODES=" + (",".join(safe_codes[:4]) if safe_codes else "none"))
        fail("WORKER_EXACT_SETTINGS_PATCH_DENIED_OR_FAILED_HTTP_" + str(status if isinstance(status, int) else "transport"))
    after_key, after_value = read(account, token)
    if (after_key.get("store_id") != prior_key.get("store_id")
            or after_value != target):
        fail("EXACT_BINDING_OR_FLAG_READBACK_MISMATCH")
    print("NVIDIA_DIAGNOSTIC_FLAG_VERIFIED=" + target)
    print("NVIDIA_ACCOUNT_SECRETS_STORE_BINDING_PRESERVED=1")
    print("NVIDIA_SECRET_VALUE_READ=0")


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("enable", "restore"):
        fail("EXACT_GATE_MODE_REQUIRED")
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    if ACCOUNT_RE.fullmatch(account) is None or not token:
        fail("APPROVED_ORDINARY_COMPUTE_IDENTITY_MISSING")
    status, doc = cf(account, token, "GET", "/workers/scripts/waterboys-fantasy-broker/settings")
    if status != 200 or doc.get("success") is not True:
        fail("ORDINARY_SLENDERIQ_ACCOUNT_NOT_ATTESTED")
    set_switch(account, token, "1" if sys.argv[1] == "enable" else "0")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError) as e:
        print("NVIDIA_PRIVATE_GATE=" + str(e))
        raise SystemExit(1)
