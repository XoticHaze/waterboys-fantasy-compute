"""One-Worker, reversible NVIDIA private diagnostic using Workers secret PUT.

Rationale: Cloudflare rejects the legacy full bindings PATCH with invalid
script config (10202). This API changes exactly one worker-local flag via
Workers Secrets Write; it must preserve the existing account Secrets Store
binding. No NVIDIA key values are read or copied. Public routes unchanged.

The preflight mode only writes DISABLED 0; enable is forbidden unless that
live no-op conversion was independently read back as safe.
"""
from __future__ import annotations
import json
import os
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API = "https://api.cloudflare.com/client/v4/accounts/"
HEX = re.compile(r"^[0-9a-fA-F]{32}$")
WORKER = "cc-shared-nvidia-inference"
BINDING = "NVIDIA_API_KEY"
FLAG = "CC_NVIDIA_DIAGNOSTIC_ENABLED"


def call(account, token, method, path, payload=None):
    hdr = {"Authorization": "Bearer " + token, "Accept": "application/json"}
    raw = None
    if payload is not None:
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        hdr["Content-Type"] = "application/json"
    req = Request(API + account + path, method=method, headers=hdr, data=raw)
    try:
        with urlopen(req, timeout=18) as response:
            status, value = response.status, response.read(200000)
    except HTTPError as e:
        status, value = e.code, e.read(200000)
    except (TimeoutError, URLError, OSError):
        return None, {}
    try:
        decoded = json.loads(value)
        if isinstance(decoded, dict):
            return status, decoded
    except (ValueError, UnicodeError):
        pass
    return status, {}


def settings(account, token):
    http, data = call(account, token, "GET", "/workers/scripts/" + WORKER + "/settings")
    if http != 200 or data.get("success") is not True:
        raise RuntimeError("WORKER_SETTINGS_READ_DENIED")
    records = data.get("result", {}).get("bindings", [])
    if not isinstance(records, list) or len(records) != 2:
        raise RuntimeError("WRONG_BINDING_COUNT")
    bindings = {b.get("name"): b for b in records if isinstance(b, dict)}
    if set(bindings) != {BINDING, FLAG}:
        raise RuntimeError("WRONG_BINDING_NAMES")
    key = bindings[BINDING]
    if (key.get("type") != "secrets_store_secret" or
            key.get("secret_name") != BINDING or
            not isinstance(key.get("store_id"), str) or
            HEX.fullmatch(key["store_id"]) is None):
        raise RuntimeError("ACCOUNT_SECRET_STORE_REFERENCE_UNVERIFIED")
    flag = bindings[FLAG]
    if flag.get("type") not in ("plain_text", "secret_text"):
        raise RuntimeError("DIAGNOSTIC_FLAG_BINDING_TYPE_INVALID")
    if flag.get("type") == "plain_text" and flag.get("text") not in ("0", "1"):
        raise RuntimeError("DIAGNOSTIC_PLAIN_TEXT_VALUE_INVALID")
    return key["store_id"], flag


def update_flag(account, token, value):
    http, result = call(account, token, "PUT", "/workers/scripts/" + WORKER + "/secrets",
                         {"name": FLAG, "text": value, "type": "secret_text"})
    if http not in (200, 201) or result.get("success") is not True:
        codes = result.get("errors") if isinstance(result, dict) else None
        numeric = [str(x.get("code")) for x in codes if isinstance(x, dict) and type(x.get("code")) is int] if isinstance(codes, list) else []
        print("NVIDIA_SECRET_FLAG_PUT_HTTP=" + str(http if isinstance(http, int) else "transport"))
        print("NVIDIA_SECRET_FLAG_PUT_ERROR_CODES=" + (",".join(numeric[:3]) or "none"))
        raise RuntimeError("SINGLE_FLAG_SECRET_API_REJECTED")
    print("NVIDIA_SINGLE_WORKER_FLAG_PUT_ACCEPTED=1")


def run(mode):
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    if HEX.fullmatch(account) is None or not token:
        raise RuntimeError("ORDINARY_COMPUTE_IDENTITY_UNAVAILABLE")
    http, owner = call(account, token, "GET", "/workers/scripts/waterboys-fantasy-broker/settings")
    if http != 200 or owner.get("success") is not True:
        raise RuntimeError("SLENDERIQ_ACCOUNT_IDENTITY_NOT_PROVEN")
    before_store, flag = settings(account, token)
    if mode == "preflight":
        # Functionally no-op. This only changes plain_text(0) to
        # secret_text(0), then confirms our account binding is untouched.
        if flag.get("type") != "plain_text" or flag.get("text") != "0":
            raise RuntimeError("PREFLIGHT_REQUIRES_INITIAL_DISABLED_PLAIN_VAR")
        update_flag(account, token, "0")
        after_store, after_flag = settings(account, token)
        if after_store != before_store or after_flag.get("type") != "secret_text":
            raise RuntimeError("PREFLIGHT_READBACK_MISMATCH")
        print("NVIDIA_PRIVATE_GATE_PREPARED_DISABLED=1")
        return
    if mode == "enable":
        if flag.get("type") != "secret_text":
            raise RuntimeError("PREPARED_DISABLED_SECRET_FLAG_REQUIRED")
        # Cloudflare does not return Worker secret plaintext in settings.
        # Only run enable immediately after a successful, same-job
        # preflight, with no intervening workflow modifying this flag.
        if os.environ.get("NVIDIA_SAME_JOB_PREFLIGHT") != "1":
            raise RuntimeError("SAME_JOB_PREFLIGHT_NOT_PROVEN")
        update_flag(account, token, "1")
        after_store, after_flag = settings(account, token)
        if after_store != before_store or after_flag.get("type") != "secret_text":
            raise RuntimeError("ENABLE_READBACK_BINDINGS_CHANGED")
        print("NVIDIA_PRIVATE_GATE_SET_ENABLED=1")
        return
    if mode == "restore":
        # Must be callable independently even after job cancellation,
        # even when the preflight was denied. If plain_text 0, do nothing.
        if flag.get("type") == "plain_text" and flag.get("text") == "0":
            print("NVIDIA_PRIVATE_GATE_ALREADY_DISABLED=1")
            return
        update_flag(account, token, "0")
        after_store, after_flag = settings(account, token)
        if after_store != before_store or after_flag.get("type") != "secret_text":
            raise RuntimeError("RESTORE_READBACK_BINDINGS_CHANGED")
        print("NVIDIA_PRIVATE_GATE_RESTORED_TO_ZERO=1")
        return
    raise RuntimeError("UNKNOWN_FIXED_MODE")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("preflight", "enable", "restore"):
        raise SystemExit("NVIDIA_EXACT_SINGLE_WORKER_MODE_REQUIRED")
    try:
        run(sys.argv[1])
    except RuntimeError as error:
        # Error strings are fixed categories only, never Cloudflare payloads.
        print("NVIDIA_PRIVATE_FLAG_PROBE=" + str(error))
        raise SystemExit(1)
