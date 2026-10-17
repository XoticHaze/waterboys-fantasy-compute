from __future__ import annotations

import unittest

from waterboys_compute.placement import _lineup_changes, optimize_weekly

ROSTER_CFG = {
    "size": 14,
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


def player(pid, name, pos, weekly, average, slot="BE", injury="ACTIVE", points=None):
    return {
        "player_id": pid,
        "name": name,
        "position": pos,
        "lineup_slot": slot,
        "injury_status": injury,
        "projected_avg_points": average,
        "avg_points": average,
        "current_week": {
            "projected_points": weekly,
            "points": points,
        },
    }


class Week6LockByeSafetyTests(unittest.TestCase):
    def test_locked_bench_dst_is_not_selected_over_unlocked_starter(self):
        roster = [
            player(10, "Jets D/ST", "D/ST", 11, 9, "D/ST", "NORMAL"),
            player(11, "Seahawks D/ST", "D/ST", 12, 10, "BE", "NORMAL", points=12),
        ]
        optimized = optimize_weekly(roster, ROSTER_CFG)
        self.assertIn(10, optimized["ids"])
        self.assertNotIn(11, optimized["ids"])
        changes = _lineup_changes(roster, optimized)
        self.assertFalse(any(move["player_id"] == 11 for move in changes["moves"]))

    def test_bye_starter_is_reported_as_unlocked_hole(self):
        bye = player(20, "Jefferson", "WR", 0, 24, "WR", "ACTIVE")
        bye["current_week"]["opponent"] = None
        bye["current_week"]["date"] = None
        roster = [
            bye,
            player(21, "Wilson", "WR", 19, 20, "WR", "ACTIVE"),
        ]
        optimized = optimize_weekly(roster, ROSTER_CFG)
        holes = [hole for hole in optimized["starter_holes"] if hole["slot"] == "WR"]
        self.assertEqual(len(holes), 1)
        self.assertEqual(holes[0]["player_id"], 20)
        self.assertFalse(holes[0]["game_locked"])


    def test_locked_flex_stays_in_flex_and_does_not_hide_wr_bye_hole(self):
        bye = player(40, "Jefferson", "WR", 0, 24, "WR", "ACTIVE")
        bye["current_week"]["opponent"] = None
        bye["current_week"]["date"] = None
        roster = [
            bye,
            player(41, "Wilson", "WR", 19, 20, "WR", "ACTIVE"),
            player(42, "Shaheed", "WR", 22, 22, "RB/WR/TE", "ACTIVE", points=28.6),
            player(43, "Kincaid", "TE", 11, 11, "BE", "ACTIVE"),
            player(44, "Fannin", "TE", 13, 13, "TE", "ACTIVE"),
        ]
        optimized = optimize_weekly(roster, ROSTER_CFG)
        rows = {row["player_id"]: row for row in optimized["players"]}
        self.assertEqual(rows[42]["assigned_slot"], "RB/WR/TE")
        self.assertNotIn(43, optimized["ids"])
        holes = [hole for hole in optimized["starter_holes"] if hole["slot"] == "WR"]
        self.assertEqual(len(holes), 1)
        self.assertEqual(holes[0]["player_id"], 40)

    def test_positive_projection_is_eligible_even_without_schedule_metadata(self):
        candidate = player(30, "Free Agent WR", "WR", 18, 18, "BE", "ACTIVE")
        candidate["current_week"]["opponent"] = None
        candidate["current_week"]["date"] = None
        roster = [
            player(21, "Wilson", "WR", 19, 20, "WR", "ACTIVE"),
            candidate,
        ]
        optimized = optimize_weekly(roster, ROSTER_CFG)
        self.assertIn(30, optimized["ids"])


if __name__ == "__main__":
    unittest.main()
