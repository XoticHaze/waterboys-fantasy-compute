from __future__ import annotations

import argparse
import json

from .broker import Broker
from .collector import collect_snapshot
from .command import execute_guarded


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["snapshot", "execute"])
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


if __name__ == "__main__":
    raise SystemExit(main())
