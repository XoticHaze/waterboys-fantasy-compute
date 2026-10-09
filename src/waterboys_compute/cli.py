from __future__ import annotations

import argparse
import json

from .broker import Broker
from .collector import collect_player_history, collect_snapshot
from .command import execute_guarded
from .placement import command_for_lineup_repair
from .sniper import command_for_cancel, command_for_selection, plan_sniper


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["snapshot", "execute", "snipe"])
    parser.add_argument("--broker", required=True)
    args = parser.parse_args()

    broker = Broker(args.broker)
    runtime = broker.runtime_config()

    if args.action == "snapshot":
        snapshot = collect_snapshot(runtime)
        result = broker.publish_snapshot(snapshot)
        print(json.dumps({
            "WATERBOYS_SNAPSHOT": "accepted",
            "collected_at": snapshot["collected_at"],
            "team_count": len(snapshot["teams"]),
            "free_agent_count": len(snapshot["free_agents"]),
            "broker_result": result,
        }, sort_keys=True))
        return 0

    if args.action == "execute":
        command_slot = broker.next_command()
        receipt = execute_guarded(runtime, command_slot)
        result = broker.publish_receipt(receipt)
        print(json.dumps({
            "WATERBOYS_EXECUTION": receipt["status"],
            "command_id": receipt.get("command_id"),
            "mutation_attempted": receipt.get("mutation_attempted"),
            "broker_result": result,
        }, sort_keys=True))
        return 0

    snapshot = collect_snapshot(runtime)
    policy = runtime.get("sniper") or {}
    previous = runtime.get("sniper_state")
    live = policy.get("enabled") is True and str(policy.get("mode") or "").lower() == "live"
    executions = []
    lineup_repair_count = 0

    if live:
        lineup_command = command_for_lineup_repair(snapshot)
        if lineup_command:
            try:
                receipt = execute_guarded(
                    runtime,
                    {"status": "pending", "command": lineup_command},
                )
                broker_result = broker.publish_receipt(receipt)
                executions.append({"receipt": receipt, "broker_result": broker_result})
                lineup_repair_count = 1
                if receipt.get("status") == "verified":
                    snapshot = collect_snapshot(runtime)
            except Exception as exc:
                executions.append({
                    "receipt": {
                        "command_id": lineup_command.get("command_id"),
                        "status": "placement_lineup_error",
                        "mutation_attempted": False,
                        "error": f"{type(exc).__name__}: {str(exc)[:240]}",
                    },
                    "broker_result": None,
                })

    history_error = None
    try:
        waiver_rows = list(((snapshot.get("value_engine") or {}).get("waiver_targets") or []))
        priority_ids = {
            int(pid) for pid in (policy.get("priority_caps") or {})
            if str(pid).lstrip("-").isdigit()
        }
        history_ids = [
            row.get("player_id")
            for row in waiver_rows[:30]
            if isinstance(row.get("player_id"), int)
        ]
        history_ids.extend(
            row.get("player_id")
            for row in waiver_rows
            if row.get("player_id") in priority_ids
        )
        history = collect_player_history(
            runtime,
            history_ids,
            int((snapshot.get("league") or {}).get("current_week") or 0),
        )
        for row in waiver_rows:
            card = history.get(row.get("player_id"))
            if not card:
                continue
            inputs = row.setdefault("inputs", {})
            inputs["recent_form"] = card.get("recent_form") or {}
            inputs["percent_started"] = card.get("percent_started")
            inputs["percent_owned"] = card.get("percent_owned")
            inputs["avg_points"] = card.get("avg_points")
            inputs["positional_rank"] = card.get("positional_rank")
            if card.get("injury_status"):
                inputs["injury_status"] = card.get("injury_status")
    except Exception as exc:
        history_error = f"{type(exc).__name__}: {str(exc)[:240]}"

    snapshot_result = broker.publish_snapshot(snapshot)
    report = plan_sniper(snapshot, policy, previous)
    report["history_hydration_error"] = history_error

    if live:
        for cancel in report.get("cancel_actions") or []:
            try:
                command = command_for_cancel(cancel, snapshot)
                receipt = execute_guarded(runtime, {"status": "pending", "command": command})
                broker_result = broker.publish_receipt(receipt)
                executions.append({"receipt": receipt, "broker_result": broker_result})
                replacement = cancel.get("replacement_selection")
                if receipt.get("status") == "verified" and isinstance(replacement, dict):
                    replacement_command = command_for_selection(replacement, snapshot)
                    replacement_receipt = execute_guarded(
                        runtime,
                        {"status": "pending", "command": replacement_command},
                    )
                    replacement_result = broker.publish_receipt(replacement_receipt)
                    executions.append({
                        "receipt": replacement_receipt,
                        "broker_result": replacement_result,
                    })
            except Exception as exc:
                executions.append({
                    "receipt": {
                        "command_id": None,
                        "status": "sniper_action_error",
                        "mutation_attempted": False,
                        "error": f"{type(exc).__name__}: {str(exc)[:240]}",
                    },
                    "broker_result": None,
                })

        for selection in report.get("selected") or []:
            try:
                command = command_for_selection(selection, snapshot)
                receipt = execute_guarded(runtime, {"status": "pending", "command": command})
                broker_result = broker.publish_receipt(receipt)
                executions.append({"receipt": receipt, "broker_result": broker_result})
            except Exception as exc:
                executions.append({
                    "receipt": {
                        "command_id": None,
                        "status": "sniper_action_error",
                        "mutation_attempted": False,
                        "error": f"{type(exc).__name__}: {str(exc)[:240]}",
                    },
                    "broker_result": None,
                })

    verified_mutation = any(
        item["receipt"].get("status") == "verified"
        and item["receipt"].get("mutation_attempted") is True
        for item in executions
    )
    if live and verified_mutation:
        snapshot = collect_snapshot(runtime)
        snapshot_result = broker.publish_snapshot(snapshot)
        report["post_action_snapshot_collected_at"] = snapshot.get("collected_at")

    report["executions"] = [
        {
            "command_id": item["receipt"].get("command_id"),
            "status": item["receipt"].get("status"),
            "mutation_attempted": item["receipt"].get("mutation_attempted"),
        }
        for item in executions
    ]
    report_result = broker.publish_sniper_report(report)
    print(json.dumps({
        "WATERBOYS_SNIPER": "live" if live else "shadow",
        "selected_count": len(report.get("selected") or []),
        "cancel_count": len(report.get("cancel_actions") or []),
        "execution_count": len(executions),
        "lineup_repair_count": lineup_repair_count,
        "snapshot_result": snapshot_result,
        "report_result": report_result,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
