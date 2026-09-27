from __future__ import annotations

import argparse
import json

from .broker import Broker
from .collector import collect_snapshot
from .command import execute_guarded
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
    snapshot_result = broker.publish_snapshot(snapshot)
    policy = runtime.get("sniper") or {}
    previous = runtime.get("sniper_state")
    report = plan_sniper(snapshot, policy, previous)
    executions = []

    live = policy.get("enabled") is True and str(policy.get("mode") or "").lower() == "live"
    if live:
        for cancel in report.get("cancel_actions") or []:
            command = command_for_cancel(cancel, snapshot)
            receipt = execute_guarded(runtime, {"status": "pending", "command": command})
            broker_result = broker.publish_receipt(receipt)
            executions.append({"receipt": receipt, "broker_result": broker_result})

        for selection in report.get("selected") or []:
            command = command_for_selection(selection, snapshot)
            receipt = execute_guarded(runtime, {"status": "pending", "command": command})
            broker_result = broker.publish_receipt(receipt)
            executions.append({"receipt": receipt, "broker_result": broker_result})

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
        "snapshot_result": snapshot_result,
        "report_result": report_result,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
