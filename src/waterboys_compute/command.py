from __future__ import annotations

from .collector import collect_snapshot
from .normalize import utc_now


def execute_guarded(runtime: dict, command_slot: dict) -> dict:
    if command_slot.get("status") != "pending" or not isinstance(command_slot.get("command"), dict):
        return {
            "schema": "waterboys.execution_receipt.v1",
            "status": "no_command",
            "created_at": utc_now(),
            "command_id": None,
            "mutation_attempted": False,
        }

    command = command_slot["command"]
    command_id = str(command.get("command_id") or "")
    if not command_id:
        raise RuntimeError("pending command is missing command_id")

    policy = runtime.get("policy") or {}
    write_policy = policy.get("writes") or {}

    # Always acquire fresh authenticated state before deciding whether mutation is allowed.
    fresh = collect_snapshot(runtime)

    dry_run = bool(command.get("dry_run", True))
    writes_enabled = write_policy.get("enabled") is True
    mode = str(write_policy.get("mode") or "dry_run")

    if dry_run or not writes_enabled or mode != "live":
        return {
            "schema": "waterboys.execution_receipt.v1",
            "status": "dry_run",
            "created_at": utc_now(),
            "command_id": command_id,
            "action": command.get("action"),
            "mutation_attempted": False,
            "reason": "live ESPN mutation authority is disabled",
            "preflight": {
                "snapshot_collected_at": fresh.get("collected_at"),
                "waterboys_team_id": (fresh.get("waterboys") or {}).get("team_id"),
                "team_count": len(fresh.get("teams") or []),
            },
            "command": command,
        }

    # Fail closed until a canary proves the exact current ESPN write contract.
    return {
        "schema": "waterboys.execution_receipt.v1",
        "status": "blocked_unproven_write_contract",
        "created_at": utc_now(),
        "command_id": command_id,
        "action": command.get("action"),
        "mutation_attempted": False,
        "reason": "live policy was enabled before the ESPN write adapter passed canary acceptance",
        "preflight": {
            "snapshot_collected_at": fresh.get("collected_at"),
            "waterboys_team_id": (fresh.get("waterboys") or {}).get("team_id"),
        },
    }
