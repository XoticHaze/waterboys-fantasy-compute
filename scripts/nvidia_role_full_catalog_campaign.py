#!/usr/bin/env python3
"""Single-run, synthetic-only full NVIDIA chat catalog benchmark.

Public GitHub runner. No credentials, private data, or arbitrary model prompts in
this process. Uses only the existing pinned local Wrangler Service Binding.
No production action is executed. Caller may submit at most five batches per
instance, so this script rotates that ephemeral caller every five batches.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

MAX_API_CALLS_PER_RUN = 4000
MAX_WINDOW_SECONDS = 4 * 60 * 60
# Leave 5 minutes for cleanup/diagnostic restore before the workflow timeout.
MAX_ACTIVE_SECONDS = MAX_WINDOW_SECONDS - 300
CALLS_PER_BATCH_HARD_MAX = 9  # 1 catalog GET + at most 2 * 4 completions
MODELS_PER_BATCH = 2
CALLER_MAX_BATCHES = 5
MAX_CATALOG_BATCHES = 75  # upstream current catalog sanitizer caps at 150 IDs
EXPECTED_SCHEMA = "commandcenter.nvidia_synthetic_roles.v1"
FIXED_TASKS = {"logic", "json", "math", "tool_call"}
MODEL_ID = re.compile(r"^[A-Za-z0-9_.:-]{2,80}/[A-Za-z0-9_.:-]{2,120}$")
LOCAL_URL = "http://127.0.0.1:8787/roles-batch"
# Exact fixed source and fixed ephemeral caller invocation only.
CALLER_CMD = (
    "npx", "--yes", "wrangler@4.151.3", "dev",
    "--config", "local-probe/wrangler.jsonc",
    "--ip", "127.0.0.1", "--port", "8787",
)


def check_time(start: float) -> None:
    if time.monotonic() - start >= MAX_ACTIVE_SECONDS:
        raise RuntimeError("CAMPAIGN_FOUR_HOUR_WINDOW_EXHAUSTED")


def validated_batch(doc: object, batch: int, expected_ids: list[str] | None):
    if not isinstance(doc, dict) or doc.get("schema") != EXPECTED_SCHEMA:
        raise RuntimeError("INVALID_SANITIZED_RECEIPT")
    if doc.get("batch") != batch or doc.get("status") != "batch_complete":
        raise RuntimeError("BATCH_NOT_COMPLETE_" + str(batch))
    calls = doc.get("calls")
    if type(calls) is not int or not 1 <= calls <= CALLS_PER_BATCH_HARD_MAX:
        raise RuntimeError("INVALID_PER_BATCH_PROVIDER_CALL_COUNT")
    ids = doc.get("eligible_model_ids")
    if (not isinstance(ids, list) or not 1 <= len(ids) <= 150
            or len(set(ids)) != len(ids)
            or any(not isinstance(i, str) or not MODEL_ID.fullmatch(i) for i in ids)
            or doc.get("eligible_count") != len(ids)):
        raise RuntimeError("INVALID_CATALOG_IDENTITY")
    if expected_ids is not None and ids != expected_ids:
        raise RuntimeError("CATALOG_CHANGED_DURING_BENCHMARK")
    selected = ids[batch * MODELS_PER_BATCH:(batch + 1) * MODELS_PER_BATCH]
    if not selected:
        raise RuntimeError("EMPTY_BATCH_SHOULD_NOT_BE_SUBMITTED")
    rows = doc.get("results")
    if (not isinstance(rows, list) or
            [x.get("model") for x in rows if isinstance(x, dict)] != selected):
        raise RuntimeError("MODEL_RESULT_SET_MISMATCH")
    observations = []
    for row in rows:
        tasks = row.get("results")
        if not isinstance(tasks, list) or not 1 <= len(tasks) <= 4:
            raise RuntimeError("INVALID_TASK_COUNT")
        names = [t.get("task") for t in tasks if isinstance(t, dict)]
        if len(names) != len(tasks) or len(set(names)) != len(names):
            raise RuntimeError("INVALID_TASK_IDENTITY")
        for t in tasks:
            if t.get("task") not in FIXED_TASKS:
                raise RuntimeError("UNEXPECTED_TASK_ID")
            http = t.get("http_status")
            if http is not None and (type(http) is not int or not 100 <= http <= 599):
                raise RuntimeError("INVALID_HTTP_STATUS")
            if http in (401, 402, 429):
                raise RuntimeError("PROVIDER_GLOBAL_BUDGET_AUTH_OR_RATE_HOLD_" + str(http))
            observations.append({
                "model": row["model"], "task": t["task"],
                "http": http, "passed": t.get("passed") is True,
                "format_valid": t.get("format_valid") is True,
                "latency_ms": t.get("latency_ms"),
                "error": t.get("error"),
            })
    return calls, ids, observations


def invoke(batch: int) -> dict:
    body = json.dumps({"batch": batch}, separators=(",", ":")).encode()
    request = Request(
        LOCAL_URL, data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=195) as r:
            code, payload = r.status, r.read(85000)
    except HTTPError as exc:
        code, payload = exc.code, exc.read(85000)
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError("PRIVATE_SERVICE_BINDING_UNAVAILABLE") from exc
    try:
        receipt = json.loads(payload)
    except (ValueError, UnicodeError) as exc:
        raise RuntimeError("INVALID_UPSTREAM_JSON") from exc
    if code != 200:
        raise RuntimeError("BATCH_PROVIDER_RECEIPT_REJECTED")
    return receipt


def caller_port_occupied() -> bool:
    try:
        with urlopen("http://127.0.0.1:8787/", timeout=2):
            return True
    except HTTPError:
        return True
    except (URLError, TimeoutError, OSError):
        return False


def open_caller(log_path: Path):
    if caller_port_occupied():
        raise RuntimeError("CALLER_PORT_OCCUPIED_BEFORE_LAUNCH")
    with log_path.open("ab") as log:
        # npx spawns workerd children; terminate the entire process group.
        process = subprocess.Popen(
            CALLER_CMD, stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    try:
        for _ in range(45):
            if process.poll() is not None:
                raise RuntimeError("EPHEMERAL_CALLER_EXITED")
            try:
                with urlopen("http://127.0.0.1:8787/", timeout=2):
                    pass
            except HTTPError:
                return process  # 404 at root means the caller is ready
            except (URLError, TimeoutError, OSError):
                time.sleep(1)
                continue
            return process
        raise RuntimeError("EPHEMERAL_CALLER_NOT_READY")
    except Exception:
        close_caller(process)
        raise


def close_caller(process) -> None:
    # Kill every npx/wrangler/workerd descendant, not only the npm parent.
    # Otherwise batch 6 reaches the old five-batch caller and gets HTTP 409.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)
    for _ in range(25):
        if not caller_port_occupied():
            return
        time.sleep(0.2)
    raise RuntimeError("EPHEMERAL_CALLER_PORT_NOT_RELEASED")


def main() -> int:
    start = time.monotonic()
    observed_calls = 0
    model_ids = None
    tested_models = set()
    task_rows = []
    batch = 0
    log_dir = Path(os.environ.get("RUNNER_TEMP", "/tmp"))
    print("NVIDIA_CAMPAIGN_REQUEST_CEILING=4000", flush=True)
    print("NVIDIA_CAMPAIGN_WINDOW_SECONDS=14400", flush=True)
    print("NVIDIA_CAMPAIGN_FIXED_SOURCE_ONLY=true", flush=True)
    print("NVIDIA_CAMPAIGN_NO_PRIVATE_INPUTS=true", flush=True)

    while batch < MAX_CATALOG_BATCHES:
        check_time(start)
        process = open_caller(log_dir / "nvidia_full_catalog_local_caller.log")
        try:
            for _ in range(CALLER_MAX_BATCHES):
                if model_ids is not None and batch * MODELS_PER_BATCH >= len(model_ids):
                    break
                check_time(start)
                # Reserve maximum possible requests BEFORE each batch, including
                # a catalog GET and calls that fail without a returned receipt.
                if observed_calls + CALLS_PER_BATCH_HARD_MAX > MAX_API_CALLS_PER_RUN:
                    raise RuntimeError("CAMPAIGN_4000_REQUEST_CEILING_REACHED")
                receipt = invoke(batch)
                count, ids, observations = validated_batch(receipt, batch, model_ids)
                if model_ids is None:
                    model_ids = ids
                    required_batches = math.ceil(len(ids) / MODELS_PER_BATCH)
                    if required_batches > MAX_CATALOG_BATCHES or required_batches * CALLS_PER_BATCH_HARD_MAX > MAX_API_CALLS_PER_RUN:
                        raise RuntimeError("CATALOG_EXCEEDS_ADMITTED_MAX_CALLS")
                    print("NVIDIA_CAMPAIGN_ELIGIBLE_MODELS=" + str(len(ids)), flush=True)
                observed_calls += count
                for obs in observations:
                    tested_models.add(obs["model"])
                    task_rows.append(obs)
                    print("NVIDIA_CAMPAIGN_OBSERVATION=" + json.dumps(obs, sort_keys=True, separators=(",", ":")), flush=True)
                print("NVIDIA_CAMPAIGN_BATCH=" + str(batch) + ";API_CALLS=" + str(observed_calls), flush=True)
                batch += 1
        finally:
            close_caller(process)
        if model_ids is not None and len(tested_models) == len(model_ids):
            if tested_models != set(model_ids):
                raise RuntimeError("CATALOG_COVERAGE_IDENTITY_MISMATCH")
            break
    if model_ids is None or len(tested_models) != len(model_ids):
        raise RuntimeError("FULL_CATALOG_INCOMPLETE")
    if observed_calls > MAX_API_CALLS_PER_RUN or time.monotonic() - start >= MAX_WINDOW_SECONDS:
        raise RuntimeError("CAMPAIGN_CEILING_BREACHED")
    summary = {
        "schema": "commandcenter.nvidia_full_catalog_synthetic_summary.v1",
        "eligible_models": len(model_ids),
        "attempted_models": len(tested_models),
        "batches": batch,
        "api_calls": observed_calls,
        "request_ceiling": MAX_API_CALLS_PER_RUN,
        "window_seconds": MAX_WINDOW_SECONDS,
        "elapsed_seconds": int(time.monotonic() - start),
        "task_observations": len(task_rows),
        "task_passes": sum(x["passed"] for x in task_rows),
        "non_200_observations": sum(x["http"] != 200 for x in task_rows),
        "raw_content_or_secrets_exported": False,
    }
    print("NVIDIA_CAMPAIGN_SUMMARY=" + json.dumps(summary, sort_keys=True, separators=(",", ":")), flush=True)
    print("NVIDIA_CAMPAIGN_ALL_ELIGIBLE_MODELS_ATTEMPTED=PASS", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, ValueError, OSError) as exc:
        print("NVIDIA_CAMPAIGN_HELD=" + str(exc), flush=True)
        sys.exit(1)
