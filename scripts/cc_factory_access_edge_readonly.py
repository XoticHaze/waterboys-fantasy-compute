#!/usr/bin/env python3
"""Anonymous edge GET probe for one exact preexisting CommandCenter factory.

Public, fixed-target, no token, no login or cookies, no mutation, no redirect
following, no response-body logging. Tests *one* production route. This only
proves whether anonymous callers can reach Worker content, not full policy
correctness, or authenticated operation readiness.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request

URL = "https://shared-compute-worker-factory.slenderiq.workers.dev/v1/status"
SCHEMA = "commandcenter.cloudflare.factory_anonymous_edge_readback.v1"


class NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def classify(status: int | str, location: str = "", response_body: str = "") -> dict:
    """Only strict, nonsecret status semantics. Never store raw location/body."""
    parsed = urllib.parse.urlsplit(location)
    login_path = parsed.path.lower()
    login_host = (parsed.hostname or "").lower()
    access_redirect = (
        status in (301, 302, 303, 307, 308)
        and (
            "/cdn-cgi/access/login" in login_path
            or (login_host.endswith(".cloudflareaccess.com")
                and ("/cdn-cgi/access/" in login_path or "/login" in login_path))
        )
    )
    factory_body_exposed = (
        status == 200
        and '"commandcenter.cloudflare.factory_status.v1"' in response_body
    )
    return {
        "status": status,
        "cloudflare_access_redirect_observed": bool(access_redirect),
        "anonymous_factory_status_exposed": bool(factory_body_exposed),
        "unauthenticated_request_not_served": status in (301, 302, 303, 307, 308, 401, 403),
        "full_policy_identity_verified": False,
        "browser_session_required_for_protected_access": True,
    }


def probe() -> dict:
    request = urllib.request.Request(
        URL,
        method="GET",
        headers={
            "Accept": "application/json",
            "User-Agent": "commandcenter-factory-anonymous-edge-readback-v1",
        },
    )
    opener = urllib.request.build_opener(NoRedirects())
    status: int | str = "NETWORK_UNAVAILABLE"
    location = ""
    body = ""
    try:
        with opener.open(request, timeout=15) as resp:
            status = resp.status
            # Read only enough to recognize the *fixed nonsecret* status schema.
            body = resp.read(1024).decode("utf-8", "replace")
            location = resp.headers.get("Location", "")
    except urllib.error.HTTPError as exc:
        status = exc.code
        location = exc.headers.get("Location", "") if exc.headers else ""
    except (urllib.error.URLError, TimeoutError, OSError):
        pass
    result = classify(status, location, body)
    return {
        "schema": SCHEMA,
        "destination": "shared-compute-worker-factory (ordinary account)",
        "request_kind": "anonymous_fixed_production_GET",
        "authenticated": False,
        "request_mutations": 0,
        "redirect_followed": False,
        "cookies_or_bearers_sent": False,
        "credentials_or_response_body_exported": False,
        **result,
    }


def main() -> int:
    result = probe()
    print(json.dumps(result, sort_keys=True))
    if result["anonymous_factory_status_exposed"]:
        raise SystemExit("FACTORY_PUBLIC_STATUS_EXPOSED_REVIEW_REQUIRED")
    if result["cloudflare_access_redirect_observed"]:
        print("FACTORY_ACCESS_ANONYMOUS_REDIRECT=PASS")
    elif result["unauthenticated_request_not_served"]:
        print("FACTORY_ANONYMOUS_REQUEST_DENIED__ACCESS_SOURCE_UNVERIFIED")
    else:
        print("FACTORY_ACCESS_ANONYMOUS_EDGE=INDETERMINATE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
