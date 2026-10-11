from __future__ import annotations

import unittest

from waterboys_compute.espn_write import validate_preflight
from waterboys_compute.placement import _lineup_changes, optimize_weekly
from waterboys_compute.sniper import evaluate_candidate


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


class SundayStarterHoleSafetyTests(unittest.TestCase):
    def test_out_starter_is_preserved_as_placeholder_instead_of_promoting_ir_bench(self):
        roster = [
            player(1, "Dobbins", "RB", 18, 18, "RB"),
            player(2, "Monangai", "RB", 0, 16, "RB", "OUT"),
            player(3, "Etienne", "RB", 0, 19, "BE", "INJURY_RESERVE"),
        ]
        optimized = optimize_weekly(roster, ROSTER_CFG)

        self.assertIn(1, optimized["ids"])
        self.assertIn(2, optimized["ids"])
        self.assertNotIn(3, optimized["ids"])
        holes = optimized["starter_holes"]
        self.assertEqual(len(holes), 1)
        self.assertEqual(holes[0]["player_id"], 2)
        self.assertFalse(holes[0]["game_locked"])

        changes = _lineup_changes(roster, optimized)
        self.assertEqual(changes["moves"], [])
        self.assertFalse(changes["auto_executable"])

    def test_healthy_bench_rb_replaces_out_starter(self):
        roster = [
            player(1, "Dobbins", "RB", 18, 18, "RB"),
            player(2, "Monangai", "RB", 0, 16, "RB", "OUT"),
            player(3, "Etienne", "RB", 0, 19, "BE", "INJURY_RESERVE"),
            player(4, "Healthy RB", "RB", 11, 7, "BE", "ACTIVE"),
        ]
        optimized = optimize_weekly(roster, ROSTER_CFG)

        self.assertIn(4, optimized["ids"])
        self.assertNotIn(2, optimized["ids"])
        self.assertNotIn(3, optimized["ids"])
        self.assertEqual(optimized["starter_holes"], [])

        changes = _lineup_changes(roster, optimized)
        self.assertTrue(changes["auto_executable"])
        self.assertEqual({move["player_id"] for move in changes["moves"]}, {2, 4})

    def test_locked_zero_starter_is_preserved_and_marked_locked(self):
        roster = [
            player(1, "Dobbins", "RB", 18, 18, "RB"),
            player(2, "Etienne", "RB", 0, 19, "RB", "INJURY_RESERVE", points=0),
            player(3, "Healthy RB", "RB", 11, 7, "BE", "ACTIVE"),
        ]
        optimized = optimize_weekly(roster, ROSTER_CFG)

        self.assertIn(2, optimized["ids"])
        holes = optimized["starter_holes"]
        self.assertEqual(len(holes), 1)
        self.assertEqual(holes[0]["player_id"], 2)
        self.assertTrue(holes[0]["game_locked"])

        changes = _lineup_changes(roster, optimized)
        self.assertEqual(changes["moves"], [])
        self.assertFalse(changes["auto_executable"])

    def test_execution_preflight_rejects_ir_status_promotion_to_starter(self):
        fresh = {
            "waterboys": {
                "roster": [
                    player(2, "Etienne", "RB", 0, 19, "BE", "INJURY_RESERVE"),
                ]
            },
            "free_agents": [],
            "league": {"roster": ROSTER_CFG},
        }
        command = {
            "action": "lineup_move",
            "moves": [
                {
                    "player_id": 2,
                    "from_slot": "BE",
                    "to_slot": "RB",
                }
            ],
        }
        with self.assertRaisesRegex(RuntimeError, "cannot start INJURY_RESERVE"):
            validate_preflight(command, fresh)

    def test_emergency_free_agent_can_override_durable_value_floor(self):
        snapshot = {
            "waterboys": {
                "team_id": 18,
                "acquisition_budget_remaining": 938,
                "roster": [
                    player(2, "Monangai", "RB", 0, 16, "RB", "OUT"),
                ],
            },
            "league": {"roster": ROSTER_CFG},
            "survival": {"waterboys_projected_margin_over_cutline": 8},
            "placement_engine": {
                "lineup_optimizer": {
                    "starter_holes": [
                        {
                            "player_id": 2,
                            "name": "Monangai",
                            "position": "RB",
                            "slot": "RB",
                            "injury_status": "OUT",
                            "projected_points": 0,
                            "game_locked": False,
                            "reason": "nonstartable_starter_no_healthy_replacement",
                        }
                    ]
                },
                "best_acquisitions": [
                    {
                        "player_id": 99,
                        "name": "Emergency RB",
                        "position": "RB",
                        "acquisition_path": "waiver",
                        "risk_adjusted_current_week_marginal_points": 10.0,
                        "estimated_rank_gain": 2,
                        "move_class": "material",
                    }
                ],
                "weekly_rank_up_targets": [],
                "durable_rank_up_targets": [],
            },
        }
        row = {
            "player_id": 99,
            "name": "Emergency RB",
            "position": "RB",
            "inputs": {
                "availability_status": "FREEAGENT",
                "injury_status": "ACTIVE",
                "projected_avg_points": 6,
                "avg_points": 5,
                "recent_form": {"games_count": 1, "median": 5},
                "percent_started": 1,
            },
            "value": {
                "risk_adjusted_marginal_ppg": 0,
                "expected_added_points_remaining": 0,
                "value_over_best_free_replacement_ppg": 0,
            },
            "suggested_drop": {
                "player_id": 2,
                "name": "Monangai",
                "position": "RB",
                "projected_avg_points": 16,
            },
            "bid_guidance": {"recommended": 0, "reservation_ceiling": 0},
            "market_reference": {"confidence": "low"},
        }
        policy = {
            "tiers": [
                {
                    "name": "cheap",
                    "max_bid": 25,
                    "min_risk_adjusted_marginal_ppg": 1.5,
                    "min_expected_added_points_remaining": 15,
                }
            ],
            "global_max_bid": 400,
            "survival_bands": {"green_margin": 25, "yellow_margin": 12},
            "green_reserve_faab": 150,
            "yellow_reserve_faab": 75,
            "red_reserve_faab": 0,
            "trap_guards": {
                "injury": {
                    "block_statuses": ["OUT", "INJURY_RESERVE", "DOUBTFUL"],
                }
            },
            "emergency_lineup_repair": {
                "enabled": True,
                "min_risk_adjusted_weekly_gain": 3,
            },
        }

        evaluated = evaluate_candidate(row, snapshot, policy)
        self.assertTrue(evaluated["eligible"])
        self.assertTrue(evaluated["emergency_repair"])
        self.assertEqual(evaluated["tier"], "emergency_lineup_repair")
        self.assertEqual(evaluated["action"], "free_agent_add")
        self.assertNotIn("below_value_floor", evaluated["reasons"])
        self.assertNotIn("candidate_not_better_than_drop_asset", evaluated["reasons"])

    def test_waiver_candidate_does_not_count_as_same_week_emergency_repair(self):
        snapshot = {
            "waterboys": {
                "team_id": 18,
                "acquisition_budget_remaining": 938,
                "roster": [
                    player(2, "Monangai", "RB", 0, 16, "RB", "OUT"),
                ],
            },
            "league": {"roster": ROSTER_CFG},
            "survival": {"waterboys_projected_margin_over_cutline": 8},
            "placement_engine": {
                "lineup_optimizer": {
                    "starter_holes": [
                        {
                            "player_id": 2,
                            "position": "RB",
                            "slot": "RB",
                            "game_locked": False,
                        }
                    ]
                },
                "best_acquisitions": [
                    {
                        "player_id": 99,
                        "acquisition_path": "waiver",
                        "risk_adjusted_current_week_marginal_points": 10,
                        "estimated_rank_gain": 2,
                    }
                ],
                "weekly_rank_up_targets": [],
                "durable_rank_up_targets": [],
            },
        }
        row = {
            "player_id": 99,
            "name": "Waiver RB",
            "position": "RB",
            "inputs": {
                "availability_status": "WAIVERS",
                "injury_status": "ACTIVE",
                "projected_avg_points": 6,
                "avg_points": 5,
                "recent_form": {"games_count": 1, "median": 5},
                "percent_started": 1,
            },
            "value": {
                "risk_adjusted_marginal_ppg": 0,
                "expected_added_points_remaining": 0,
                "value_over_best_free_replacement_ppg": 0,
            },
            "suggested_drop": {
                "player_id": 2,
                "name": "Monangai",
                "position": "RB",
                "projected_avg_points": 16,
            },
            "bid_guidance": {"recommended": 10, "reservation_ceiling": 10},
            "market_reference": {"confidence": "low"},
        }
        policy = {
            "tiers": [],
            "global_max_bid": 400,
            "survival_bands": {"green_margin": 25, "yellow_margin": 12},
            "green_reserve_faab": 150,
            "yellow_reserve_faab": 75,
            "red_reserve_faab": 0,
            "trap_guards": {
                "injury": {
                    "block_statuses": ["OUT", "INJURY_RESERVE", "DOUBTFUL"],
                }
            },
            "emergency_lineup_repair": {
                "enabled": True,
                "min_risk_adjusted_weekly_gain": 3,
            },
        }

        evaluated = evaluate_candidate(row, snapshot, policy)
        self.assertFalse(evaluated["emergency_repair"])
        self.assertFalse(evaluated["eligible"])


if __name__ == "__main__":
    unittest.main()
