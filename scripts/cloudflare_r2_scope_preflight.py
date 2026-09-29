from __future__ import annotations

import json
import os
from urllib.error import HTTPError
from urllib.request import Request, urlopen

API = "https://api.cloudflare.com/client/v4"


def get(token: str, url: str):
    req = Request(
        url,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/json",
            "User-Agent": "shared-project-cloudflare-r2-preflight",
        },
    )
    try:
        with urlopen(req, timeout=30) as response:
            raw = response.read()
            status = int(response.status)
    except HTTPError as exc:
        raw = exc.read()
        status = int(exc.code)
    try:
        node = json.loads(raw.decode("utf-8")) if raw else {}
    except Exception:
        node = {}
    return status, node


def main() -> int:
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    if not account or not token:
        raise SystemExit("R2 Cloudflare credential missing")

    allowed = [
        "fleet-authority",
        "mmibkr-operator-console",
        "waterboys-fantasy-broker",
    ]
    forbidden = [
        "reference-release-broker-v1",
        "reference-release-maintainer-v1",
        "reference-maintenance-authority-v1",
    ]

    for worker in allowed:
        status, node = get(
            token,
            f"{API}/accounts/{account}/workers/scripts/{worker}/settings",
        )
        if status != 200 or node.get("success") is not True:
            raise SystemExit(
                f"shared R2 expected Worker access failed: {worker}:HTTP_{status}"
            )
        print("SHARED_R2_ALLOW_" + worker.upper().replace("-", "_") + "=1")

    for worker in forbidden:
        status, _ = get(
            token,
            f"{API}/accounts/{account}/workers/scripts/{worker}/settings",
        )
        if status == 200:
            raise SystemExit(f"shared R2 forbidden neutral Worker reachable: {worker}")
        if status not in {401, 403, 404}:
            raise SystemExit(
                f"shared R2 neutral Worker unexpected status: {worker}:HTTP_{status}"
            )
        print("SHARED_R2_DENY_" + worker.upper().replace("-", "_") + "=1")

    print("SHARED_PROJECT_CLOUDFLARE_R2_PREFLIGHT_PASS=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
