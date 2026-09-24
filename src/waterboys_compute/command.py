from __future__ import annotations

from .collector import collect_snapshot
from .espn_write import (
    build_transaction,
    post_transaction,
    redacted_transaction,
    validate_preflight,
    verify_cancel,
    verify_pending_claim,
)
from .normalize import utc_now


def _preflight_node(fresh: dict) -> dict:
    return {
        "snapshot_collected_at": fresh.get("collected_at"),
        "waterboys_team_id": (fresh.get("waterboys") or {}).get("team_id"),
        "team_count": len(fresh.get("teams") or []),
        "faab_remaining": (fresh.get("waterboys") or {}).get("acquisition_budget_remaining"),
    }


def _verify_snapshot(command: dict, fresh: dict) -> dict:
    roster = list((fresh.get("waterboys") or {}).get("roster") or [])
    by_id = {player.get("player_id"): player for player in roster}
    action = str(command.get("action") or "")

    if action == "free_agent_add":
        player_id = command.get("player_id")
        drop_id = command.get("drop_player_id")
        return {
            "verified": player_id in by_id and (drop_id is None or drop_id not in by_id),
            "player_present": player_id in by_id,
            "drop_absent": drop_id is None or drop_id not in by_id,
        }

    if action == "free_agent_drop":
        player_id = command.get("player_id")
        return {
            "verified": player_id not in by_id,
            "player_absent": player_id not in by_id,
        }

    if action in {"lineup_move", "ir_move"}:
        moves = command.get("moves") if isinstance(command.get("moves"), list) else [command]
        checks = []
        for move in moves:
            player = by_id.get(move.get("player_id")) or {}
            expected = "IR" if action == "ir_move" else str(move.get("to_slot") or "")
            checks.append({
                "player_id": move.get("player_id"),
                "expected_slot": expected,
                "actual_slot": player.get("lineup_slot"),
                "ok": str(player.get("lineup_slot") or "") == expected,
            })
        return {"verified": bool(checks) and all(row["ok"] for row in checks), "moves": checks}

    return {"verified": False, "reason": f"no snapshot verifier for {action}"}


def _live_authorized(write_policy: dict, command_id: str, action: str) -> tuple[bool, str]:
    canary = write_policy.get("canary") or {}
    if canary.get("enabled") is True and str(canary.get("command_id") or "") == command_id:
        canary_action = str(canary.get("action") or "")
        if not canary_action or canary_action == action:
            return True, "explicit_canary_command"

    proven_actions = set(write_policy.get("proven_actions") or [])
    autonomy = write_policy.get("autonomy") or {}
    if action in proven_actions and autonomy.get("routine_auto_execute") is True:
        return True, "proven_action_autonomy"

    return False, f"{action} is not proven for autonomous live execution and this command is not the authorized canary"


def _execute_one(runtime: dict, command: dict, *, batch_live_allowed: bool = True) -> dict:
    command_id = str(command.get("command_id") or "")
    if not command_id:
        raise RuntimeError("pending command is missing command_id")

    policy = runtime.get("policy") or {}
    write_policy = policy.get("writes") or {}
    action = str(command.get("action") or "")
    allowed_actions = set(write_policy.get("allowed_actions") or [])
    if action not in allowed_actions:
        return {
            "command_id": command_id,
            "action": action,
            "status": "blocked_action_not_allowed",
            "mutation_attempted": False,
            "reason": f"{action} is not allowed by execution policy",
        }

    fresh = collect_snapshot(runtime)
    validate_preflight(command, fresh)
    body = build_transaction(runtime, command, fresh)
    safe_body = redacted_transaction(body)

    dry_run = bool(command.get("dry_run", True))
    writes_enabled = write_policy.get("enabled") is True
    mode = str(write_policy.get("mode") or "dry_run")

    if dry_run or not writes_enabled or mode != "live":
        return {
            "command_id": command_id,
            "action": action,
            "status": "dry_run",
            "mutation_attempted": False,
            "reason": "live ESPN mutation authority is disabled",
            "preflight": _preflight_node(fresh),
            "would_send": safe_body,
            "command": command,
        }

    if not batch_live_allowed:
        return {
            "command_id": command_id,
            "action": action,
            "status": "blocked_batch_live_disabled",
            "mutation_attempted": False,
            "preflight": _preflight_node(fresh),
        }

    authorized, authority = _live_authorized(write_policy, command_id, action)
    if not authorized:
        return {
            "command_id": command_id,
            "action": action,
            "status": "blocked_unproven_write_contract",
            "mutation_attempted": False,
            "reason": authority,
            "preflight": _preflight_node(fresh),
            "would_send": safe_body,
        }

    status_code, response = post_transaction(runtime, body)

    if action == "waiver_claim":
        verification = verify_pending_claim(runtime, command)
    elif action == "waiver_cancel":
        verification = verify_cancel(runtime, str(command.get("transaction_id") or ""))
    else:
        verification = _verify_snapshot(command, collect_snapshot(runtime))

    verified = verification.get("verified") is True
    response_summary = {
        "http_status": status_code,
        "transaction_id": response.get("id") if isinstance(response, dict) else None,
        "status": response.get("status") if isinstance(response, dict) else None,
        "type": response.get("type") if isinstance(response, dict) else None,
    }
    return {
        "command_id": command_id,
        "action": action,
        "status": "verified" if verified else "write_sent_unverified",
        "mutation_attempted": True,
        "authority": authority,
        "preflight": _preflight_node(fresh),
        "sent": safe_body,
        "response": response_summary,
        "verification": verification,
    }


def execute_guarded(runtime: dict, command_slot: dict) -> dict:
    if command_slot.get("status") != "pending":
        return {
            "schema": "waterboys.execution_receipt.v1",
            "status": "no_command",
            "created_at": utc_now(),
            "command_id": None,
            "mutation_attempted": False,
        }

    single = command_slot.get("command")
    batch = command_slot.get("commands")
    if isinstance(single, dict):
        commands = [single]
        batch_id = str(single.get("command_id") or "")
    elif isinstance(batch, list) and batch and all(isinstance(row, dict) for row in batch):
        commands = batch
        batch_id = str(command_slot.get("batch_id") or "")
        if not batch_id:
            raise RuntimeError("pending command batch is missing batch_id")
    else:
        raise RuntimeError("pending command slot contains no valid command or command batch")

    write_policy = ((runtime.get("policy") or {}).get("writes") or {})
    live_requested = any(not bool(command.get("dry_run", True)) for command in commands)
    batch_live_allowed = (
        len(commands) == 1
        or not live_requested
        or write_policy.get("batch_live_enabled") is True
    )

    results = [
        _execute_one(runtime, command, batch_live_allowed=batch_live_allowed)
        for command in commands
    ]
    attempted = any(result.get("mutation_attempted") is True for result in results)

    if len(results) == 1:
        result = results[0]
        return {
            "schema": "waterboys.execution_receipt.v1",
            "created_at": utc_now(),
            **result,
        }

    statuses = [str(result.get("status") or "") for result in results]
    if all(status == "dry_run" for status in statuses):
        status = "batch_dry_run"
    elif all(status == "verified" for status in statuses):
        status = "batch_verified"
    elif any(status.startswith("blocked") for status in statuses):
        status = "batch_blocked"
    else:
        status = "batch_partial"

    return {
        "schema": "waterboys.execution_receipt.v1",
        "created_at": utc_now(),
        "command_id": batch_id,
        "status": status,
        "mutation_attempted": attempted,
        "results": results,
    }
