from __future__ import annotations

import json
import os
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

AUDIENCE = "waterboys-fantasy-compute"


def github_oidc_token(audience: str = AUDIENCE) -> str:
    raw_url = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL", "")
    request_token = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "")
    if not raw_url or not request_token:
        raise RuntimeError("GitHub OIDC environment is unavailable")

    parsed = urlparse(raw_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["audience"] = audience
    oidc_url = urlunparse(
        (parsed.scheme, parsed.netloc, parsed.path, parsed.params, urlencode(query), parsed.fragment)
    )
    req = Request(
        oidc_url,
        headers={
            "Authorization": "Bearer " + request_token,
            "Accept": "application/json",
            "User-Agent": "waterboys-fantasy-compute/0.1",
        },
    )
    with urlopen(req, timeout=20) as response:
        node = json.load(response)
    token = str(node.get("value") or "")
    if token.count(".") != 2:
        raise RuntimeError("GitHub OIDC token response was invalid")
    return token
