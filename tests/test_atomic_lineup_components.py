from __future__ import annotations

import unittest
from unittest.mock import patch

from waterboys_compute.cli import _execute_lineup_repairs
from waterboys_compute.placement import (
    _lineup_changes,
    commands_for_lineup_repair,
    optimize_weekly,
)


ROSTER_CFG = {
    "slots": {
        "QB": 1,
        "RB": 2,
        "WR": 2,
        "TE": 1,
        "FLEX": 1,
        "DST": 1,
        "K": 1,
    },
    "position_limits": {
        "QB": 2,
        "RB": 5,
        "WR": 5,
        "TE": 3,
        "DST": 3,
        "K": 2,
    },
}


def player(pid, name, pos, projection, slot, *, status="ACTIVE", date=None):
    return {
        "player_id": pid,
        "name": name,
        "position": pos,
        "lineup_slot": slot,
        "injury_status": status,
        "projected_avg_points": projection,
        "avg_points": projection,
        "current_week": {
            "projected_points": projection,
            "points": None,
            "date": date,
            "opponent": "OPP" if date else None,
        },
    }


class AtomicLineupComponentTests(unittest.TestCase):
    def test_starter_to_starter_slot_shift_is_explicit(self):
        thursday = "2026-10-16 00:15:00"
        sunday = "2026-10-18 17:00:00"
        roster = [
            player(1, "QB", "QB", 43.0, "QB", date=sunday),
            player(2, "Dobbins", "RB", 17.17, "RB", date=thursday),
            player(3, "Etienne", "RB", 0, "RB", status="INJURY_RESERVE", date=sunday),
            player(4, "Monangai", "RB", 0, "BE", status="QUESTIONABLE", date=sunday),
            player(5, "Garrett", "WR", 19.74, "WR", date=sunday),
            player(6, "Jefferson", "WR", 0, "WR"),
            player(7, "Shaheed", "WR", 22.3, "RB/WR/TE", date=thursday),
            player(8, "Kincaid", "TE", 10.93, "BE", date=sunday),
            player(9, "Fannin", "TE", 12.88, "TE", date=sunday),
            player(10, "Jets", "D/ST", 11.77, "D/ST", date=sunday),
            player(11, "Seattle", "D/ST", 12.2, "BE", date=thursday),
            player(12, "Kicker", "K", 9, "K", date=sunday),
        ]

        optimized = optimize_weekly(roster, ROSTER_CFG)
        changes = _lineup_changes(roster, optimized)

        self.assertIn(
            {"player_id": 7, "from_slot": "RB/WR/TE", "to_slot": "WR"},
            changes["moves"],
        )
        self.assertIn(
            {"player_id": 8, "from_slot": "BE", "to_slot": "RB/WR/TE"},
            changes["moves"],
        )
        wr_flex = next(
            component for component in changes["components"]
            if set(component["slots"]) == {"WR", "RB/WR/TE"}
        )
        self.assertEqual(
            {move["player_id"] for move in wr_flex["moves"]},
            {6, 7, 8},
        )

    def test_thursday_dst_swap_is_independent_component(self):
        thursday = "2026-10-16 00:15:00"
        sunday = "2026-10-18 17:00:00"
        roster = [
            player(1, "QB", "QB", 43, "QB", date=sunday),
            player(2, "RB1", "RB", 17, "RB", date=sunday),
            player(3, "RB2", "RB", 16, "RB", date=sunday),
            player(4, "WR1", "WR", 20, "WR", date=sunday),
            player(5, "WR2", "WR", 19, "WR", date=sunday),
            player(6, "TE", "TE", 13, "TE", date=sunday),
            player(7, "Flex", "WR", 18, "RB/WR/TE", date=sunday),
            player(8, "Jets", "D/ST", 11.77, "D/ST", date=sunday),
            player(9, "Seattle", "D/ST", 12.2, "BE", date=thursday),
            player(10, "K", "K", 9, "K", date=sunday),
        ]
        optimized = optimize_weekly(roster, ROSTER_CFG)
        changes = _lineup_changes(roster, optimized)
        snapshot = {
            "collected_at": "2026-10-15T23:06:13Z",
            "waterboys": {"roster": roster},
            "placement_engine": {
                "lineup_optimizer": {
                    "projected_lineup_leakage": 0.43,
                    "recommended_changes": changes,
                }
            },
        }

        commands = commands_for_lineup_repair(snapshot)
        dst = next(
            command for command in commands
            if (command["preconditions"].get("slots") or []) == ["D/ST"]
        )
        self.assertEqual(
            {move["player_id"] for move in dst["moves"]},
            {8, 9},
        )
        self.assertEqual(dst["preconditions"]["kickoff"], thursday)

    def test_failed_component_does_not_block_next_component(self):
        first = {
            "command_id": "component-a",
            "preconditions": {"component_id": 1},
        }
        second = {
            "command_id": "component-b",
            "preconditions": {"component_id": 2},
        }
        initial = {"state": 0}
        refreshed = {"state": 1}
        executions = []

        class Broker:
            def publish_receipt(self, receipt):
                return {"ok": True}

        def commands(snapshot):
            return [first, second] if snapshot.get("state") == 0 else []

        def execute(_runtime, slot):
            command = slot["command"]
            if command["command_id"] == "component-a":
                raise RuntimeError("bad independent component")
            return {
                "command_id": "component-b",
                "action": "lineup_move",
                "status": "verified",
                "mutation_attempted": True,
            }

        with patch("waterboys_compute.cli.commands_for_lineup_repair", side_effect=commands), patch(
            "waterboys_compute.cli.execute_guarded", side_effect=execute
        ), patch(
            "waterboys_compute.cli.collect_snapshot", return_value=refreshed
        ):
            snapshot, count = _execute_lineup_repairs(
                {},
                Broker(),
                initial,
                executions,
            )

        self.assertEqual(snapshot, refreshed)
        self.assertEqual(count, 1)
        self.assertEqual(len(executions), 2)
        self.assertEqual(
            executions[0]["receipt"]["status"],
            "placement_lineup_error",
        )
        self.assertIn(
            "bad independent component",
            executions[0]["receipt"]["error"],
        )
        self.assertEqual(executions[1]["receipt"]["status"], "verified")


if __name__ == "__main__":
    unittest.main()
