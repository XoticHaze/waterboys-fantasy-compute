from __future__ import annotations

import json
import os
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .oidc import github_oidc_token


class Broker:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def _post(self, path: str, body: dict | None = None) -> dict:
        token = github_oidc_token()
        payload = json.dumps(body or {}, separators=(",", ":")).encode("utf-8")
        req = Request(
            self.base_url + path,
            data=payload,
            method="POST",
            headers={
                "Authorization": "Bearer " + token,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "waterboys-fantasy-compute/0.1",
                "X-WaterBoys-Caller-Run-Id": os.environ.get("GITHUB_RUN_ID", ""),
            },
        )
        try:
            with urlopen(req, timeout=30) as response:
                return json.load(response)
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:2000]
            raise RuntimeError(f"broker {path} failed: HTTP {exc.code}: {detail}") from exc

    def runtime_config(self) -> dict:
        return self._post("/v1/runtime-config")

    def publish_snapshot(self, snapshot: dict) -> dict:
        return self._post("/v1/snapshot", snapshot)

    def next_command(self) -> dict:
        return self._post("/v1/command/next")

    def publish_receipt(self, receipt: dict) -> dict:
        return self._post("/v1/receipt", receipt)
