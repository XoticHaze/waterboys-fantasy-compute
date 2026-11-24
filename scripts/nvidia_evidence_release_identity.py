#!/usr/bin/env python3
"""Exact source-bound release receipt verification for the existing synthetic Worker.

GitHub's authenticated release artifact supplies the precise deployment/version
identity. A timestamp window alone never admits a different active version.
No Cloudflare mutation or provider call occurs here.
"""
from __future__ import annotations

import io
import json
import re
import uuid
import zipfile
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen
from urllib.error import HTTPError

REPO = "XoticHaze/waterboys-fantasy-compute"
API = "https://api.github.com/repos/" + REPO
ARTIFACT = "nvidia-evidence-status-reviewed-release-version"
FILE = "nvidia-evidence-status-release-version.json"
SCHEMA = "commandcenter.nvidia_evidence_status_public_synthetic_release_version.v2"
WORKER = "cc-shared-nvidia-inference"
SOURCE = "7ff97c4982b32cf08900dea000dd269a1f9d8ff1"


def require(condition, code):
    if not condition:
        raise ValueError(code)


def exact_uuid(value):
    require(isinstance(value, str), "RELEASE_UUID_INVALID")
    try:
        out = str(uuid.UUID(value))
    except (ValueError, AttributeError):
        raise ValueError("RELEASE_UUID_INVALID") from None
    require(out == value, "RELEASE_UUID_NOT_CANONICAL")
    return out


def verify_release_identity(proof, active, *, run_id, controller_sha):
    require(isinstance(proof, dict) and isinstance(active, dict), "RELEASE_PROOF_SHAPE_INVALID")
    expected = {
        "schema": SCHEMA, "repository": REPO, "run_id": str(run_id),
        "controller_sha": controller_sha, "reviewed_source_sha": SOURCE,
        "worker_name": WORKER, "diagnostic_disabled": True,
        "secret_reference_preserved": True, "full_model_text_exported": False,
        "private_input_used": False, "production_admitted": False,
    }
    require(all(type(proof.get(k)) is type(v) and proof[k] == v for k, v in expected.items()),
            "RELEASE_PROOF_IDENTITY_MISMATCH")
    versions = active.get("versions")
    require(isinstance(versions, list) and len(versions) == 1
            and isinstance(versions[0], dict) and versions[0].get("percentage") == 100,
            "ACTIVE_VERSION_NOT_SINGLE_FULL")
    require(exact_uuid(proof.get("deployment_id")) == exact_uuid(active.get("id"))
            and exact_uuid(proof.get("version_id")) == exact_uuid(versions[0].get("version_id")),
            "ACTIVE_VERSION_NOT_EXACT_REVIEWED_RELEASE")
    require(isinstance(proof.get("deployment_created_on"), str)
            and proof["deployment_created_on"] == active.get("created_on"),
            "ACTIVE_DEPLOYMENT_CREATED_ON_MISMATCH")
    return {"deployment_id": active["id"], "version_id": versions[0]["version_id"]}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_release_proof(run_id, github_token):
    require(re.fullmatch(r"[0-9]{8,20}", str(run_id)) is not None, "INVALID_RELEASE_RUN_ID")
    require(isinstance(github_token, str) and len(github_token) >= 10, "GITHUB_READ_IDENTITY_MISSING")
    headers = {"Authorization": "Bearer " + github_token, "Accept": "application/vnd.github+json",
               "User-Agent": "cc-nvidia-v2-release-proof"}
    # Bound the authenticated list; do not accept an arbitrary artifact URL.
    opener = build_opener(NoRedirect())
    with opener.open(Request(f"{API}/actions/runs/{run_id}/artifacts?per_page=100", headers=headers), timeout=20) as r:
        listing = json.loads(r.read(1000000))
    rows = listing.get("artifacts")
    require(isinstance(rows, list) and type(listing.get("total_count")) is int
            and listing["total_count"] == len(rows), "RELEASE_ARTIFACT_LIST_INCOMPLETE")
    found = [x for x in rows if isinstance(x, dict) and x.get("name") == ARTIFACT]
    require(len(found) == 1 and found[0].get("expired") is False, "RELEASE_ARTIFACT_MISSING_OR_EXPIRED")
    item = found[0]
    require(type(item.get("id")) is int and type(item.get("size_in_bytes")) is int
            and 0 < item["size_in_bytes"] <= 65536, "RELEASE_ARTIFACT_ID_OR_SIZE_INVALID")
    # Do not forward a GitHub bearer to the storage host after redirect.
    try:
        with opener.open(Request(f"{API}/actions/artifacts/{item['id']}/zip", headers=headers), timeout=20) as r:
            raw = r.read(65537)
    except HTTPError as e:
        require(e.code in (302, 303, 307), "RELEASE_ARTIFACT_DOWNLOAD_REJECTED")
        location = e.headers.get("Location", "")
        u = urlsplit(location)
        require(u.scheme == "https" and u.hostname and not u.username and not u.password
                and (u.hostname.endswith(".blob.core.windows.net") or u.hostname.endswith(".actions.githubusercontent.com")
                     or u.hostname.endswith(".githubusercontent.com")),
                "RELEASE_ARTIFACT_REDIRECT_UNTRUSTED")
        # No auth header and no further redirects.
        with opener.open(Request(location, headers={"User-Agent": "cc-nvidia-v2-release-proof"}), timeout=20) as r:
            raw = r.read(65537)
    require(0 < len(raw) <= 65536, "RELEASE_ARTIFACT_BYTES_INVALID")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        require(archive.namelist() == [FILE], "RELEASE_ARTIFACT_CONTENTS_MISMATCH")
        entry = archive.getinfo(FILE)
        require(0 < entry.file_size <= 16384, "RELEASE_PROOF_SIZE_INVALID")
        proof = json.loads(archive.read(entry))
    require(isinstance(proof, dict), "RELEASE_PROOF_JSON_INVALID")
    return proof
