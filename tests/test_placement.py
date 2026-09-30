from __future__ import annotations

import unittest

from waterboys_compute.placement import (
    build_placement_engine,
    command_for_lineup_repair,
    elimination_race,
    optimize_weekly,
    projected_rank,
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
        "RB": 4,
        "WR": 4,
        "TE": 2,
        "DST": 3,
        "K": 2,
    },
}


def player(pid, name, pos, weekly, average, slot="BE", injury="ACTIVE"):
    return {
        "player_id": pid,
        "name": name,
        "position": pos,
        "lineup_slot": slot,
        "injury_status": injury,
        "projected_avg_points": average,
        "avg_points": average,
        "current_week": {"projected_points": weekly, "points": None},
    }


class PlacementEngineTests(unittest.TestCase):
    def test_weekly_optimizer_repairs_zero_projection_starter(self):
        roster = [
            player(1, "QB", "QB", 30, 30, "QB"),
            player(2, "Out RB", "RB", 0, 20, "RB", "OUT"),
            player(3, "RB A", "RB", 13, 13, "RB"),
            player(4, "Bench RB", "RB", 12, 12, "BE"),
            player(5, "WR A", "WR", 20, 20, "WR"),
            player(6, "WR B", "WR", 19, 19, "WR"),
            player(7, "TE", "TE", 14, 14, "TE"),
            player(8, "Flex", "WR", 18, 18, "RB/WR/TE"),
            player(9, "DST", "D/ST", 10, 10, "D/ST"),
            player(10, "K", "K", 9, 9, "K"),
        ]
        optimized = optimize_weekly(roster, ROSTER_CFG)
        ids = optimized["ids"]
        self.assertIn(4, ids)
        self.assertNotIn(2, ids)
        self.assertEqual(optimized["projected_points"], 145.0)

        changes_snapshot = {
            "collected_at": "2026-09-30T05:00:00Z",
            "placement_engine": {
                "lineup_optimizer": {
                    "projected_lineup_leakage": 12.0,
                    "recommended_changes": {
                        "moves": [
                            {"player_id": 2, "from_slot": "RB", "to_slot": "BE"},
                            {"player_id": 4, "from_slot": "BE", "to_slot": "RB"},
                        ],
                        "auto_executable": True,
                    },
                }
            },
        }
        command = command_for_lineup_repair(changes_snapshot)
        self.assertEqual(command["action"], "lineup_move")
        self.assertEqual(len(command["moves"]), 2)
        self.assertFalse(command["dry_run"])

    def test_lineup_repair_refuses_game_locked_moves(self):
        snapshot = {
            "collected_at": "2026-09-30T05:00:00Z",
            "placement_engine": {
                "lineup_optimizer": {
                    "recommended_changes": {
                        "moves": [
                            {"player_id": 2, "from_slot": "RB", "to_slot": "BE"},
                            {"player_id": 4, "from_slot": "BE", "to_slot": "RB"},
                        ],
                        "game_locked_player_ids": [2],
                        "auto_executable": False,
                    }
                }
            },
        }
        self.assertIsNone(command_for_lineup_repair(snapshot))

    def test_projected_rank_simulates_waterboys_move(self):
        survival = {
            "current_week_ranking": [
                {"team_id": 1, "projected_points": 180},
                {"team_id": 18, "projected_points": 150},
                {"team_id": 2, "projected_points": 145},
                {"team_id": 3, "projected_points": 140},
            ]
        }
        self.assertEqual(projected_rank(150, survival, 18), 2)
        self.assertEqual(projected_rank(185, survival, 18), 1)

    def test_elimination_race_tracks_more_than_single_last_team(self):
        teams = [
            {"team_id": 18, "name": "WaterBoys", "roster_count": 1, "roster": []},
            {"team_id": 2, "name": "Near", "roster_count": 1, "roster": []},
            {"team_id": 3, "name": "Last", "roster_count": 1, "roster": []},
            {"team_id": 4, "name": "Safe", "roster_count": 1, "roster": []},
        ]
        survival = {
            "projected_cutline_points": 140,
            "current_week_ranking": [
                {"team_id": 4, "name": "Safe", "projected_points": 180, "projection_rank": 1},
                {"team_id": 18, "name": "WaterBoys", "projected_points": 158, "projection_rank": 2},
                {"team_id": 2, "name": "Near", "projected_points": 150, "projection_rank": 3},
                {"team_id": 3, "name": "Last", "projected_points": 140, "projection_rank": 4},
            ],
        }
        race = elimination_race(teams, survival, danger_points=25)
        self.assertEqual([row["team_id"] for row in race], [3, 2, 18])
        self.assertEqual(race[0]["gap_over_projected_cutline"], 0.0)

    def test_placement_engine_labels_launch_target_and_rank_gain(self):
        waterboys_roster = [
            player(1, "QB", "QB", 30, 30, "QB"),
            player(2, "RB A", "RB", 13, 13, "RB"),
            player(3, "RB B", "RB", 12, 12, "RB"),
            player(4, "WR A", "WR", 20, 20, "WR"),
            player(5, "WR B", "WR", 19, 19, "WR"),
            player(6, "TE", "TE", 14, 14, "TE"),
            player(7, "Flex", "WR", 18, 18, "RB/WR/TE"),
            player(8, "DST", "D/ST", 10, 10, "D/ST"),
            player(9, "K", "K", 9, 9, "K"),
        ]
        waterboys = {
            "team_id": 18,
            "name": "WaterBoys",
            "roster_count": len(waterboys_roster),
            "roster": waterboys_roster,
            "current_week_projected_points": 145,
            "current_week_projection_rank": 4,
            "acquisition_budget_remaining": 1000,
        }
        star = player(99, "Star RB", "RB", 32, 32, "BE")
        star["availability_status"] = "WAIVERS"
        teams = [
            waterboys,
            {"team_id": 1, "name": "Top", "roster_count": 1, "current_week_projected_points": 180, "roster": []},
            {"team_id": 2, "name": "Middle", "roster_count": 1, "current_week_projected_points": 160, "roster": []},
            {"team_id": 3, "name": "Last", "roster_count": 1, "current_week_projected_points": 140, "roster": []},
        ]
        survival = {
            "alive_team_count": 4,
            "projected_cutline_points": 140,
            "current_week_ranking": [
                {"team_id": 1, "name": "Top", "projected_points": 180, "projection_rank": 1},
                {"team_id": 2, "name": "Middle", "projected_points": 160, "projection_rank": 2},
                {"team_id": 18, "name": "WaterBoys", "projected_points": 145, "projection_rank": 3},
                {"team_id": 3, "name": "Last", "projected_points": 140, "projection_rank": 4},
            ],
        }
        value_engine = {
            "waiver_targets": [{
                "player_id": 99,
                "name": "Star RB",
                "position": "RB",
                "inputs": {
                    "injury_status": "ACTIVE",
                    "availability_status": "WAIVERS",
                },
                "value": {
                    "risk_adjusted_marginal_ppg": 12.0,
                    "expected_added_points_remaining": 120.0,
                },
                "suggested_drop": {"player_id": 3, "name": "RB B"},
                "bid_guidance": {"recommended": 200},
                "faab_reference": {"midpoint": 250},
            }],
            "trade_targets": [],
        }
        engine = build_placement_engine(
            waterboys,
            teams,
            [star],
            survival,
            {"roster": ROSTER_CFG, "waivers": {"faab_start": 1000}, "current_week": 4},
            {"regular_season_count": 14},
            value_engine,
            market={"successful_waiver_bids": []},
            waiver_offers=[],
        )
        target = engine["best_acquisitions"][0]
        self.assertEqual(target["name"], "Star RB")
        self.assertEqual(target["move_class"], "launch")
        self.assertGreaterEqual(target["estimated_rank_gain"], 1)
        self.assertIn("portfolio_scenarios", engine)
        self.assertIn("pending_claims", engine["portfolio_scenarios"])


if __name__ == "__main__":
    unittest.main()
