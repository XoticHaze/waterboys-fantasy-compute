from __future__ import annotations

import unittest

from waterboys_compute.sniper import evaluate_candidate


def policy():
    return {
        "tiers": [
            {
                "name": "standard",
                "max_bid": 100,
                "min_risk_adjusted_marginal_ppg": 3,
                "min_expected_added_points_remaining": 25,
            }
        ],
        "global_max_bid": 400,
        "green_reserve_faab": 150,
        "yellow_reserve_faab": 75,
        "red_reserve_faab": 0,
        "survival_bands": {"green_margin": 25, "yellow_margin": 12},
        "trap_guards": {
            "injury": {
                "block_statuses": ["OUT", "INJURY_RESERVE", "DOUBTFUL"],
                "soft_block_statuses": ["QUESTIONABLE", "DAY_TO_DAY"],
                "soft_status_require_current_week_playable": True,
                "soft_status_min_risk_adjusted_marginal_ppg": 3,
                "soft_status_min_independent_value_signals": 2,
                "soft_status_allowed_move_classes": ["material", "launch"],
                "soft_status_max_bid": 25,
            },
            "valuation": {"large_bid_threshold": 100},
            "recent_form": {"min_games_for_large_bid": 2},
        },
        "free_stash": {"enabled": False},
        "growth_discipline": {"enabled": False},
        "priority_caps": {},
    }


def snapshot(move_class="maintenance"):
    return {
        "waterboys": {
            "team_id": 18,
            "acquisition_budget_remaining": 900,
            "roster": [
                {
                    "player_id": 2,
                    "name": "Bench WR",
                    "position": "WR",
                    "lineup_slot": "BE",
                    "projected_avg_points": 10,
                    "current_week": {
                        "projected_points": 8,
                        "points": None,
                    },
                }
            ],
        },
        "league": {"roster": {"size": 14}},
        "survival": {"waterboys_projected_margin_over_cutline": 30},
        "placement_engine": {
            "best_acquisitions": [
                {
                    "player_id": 99,
                    "acquisition_path": "waiver",
                    "move_class": move_class,
                    "estimated_rank_gain": 1 if move_class != "maintenance" else 0,
                }
            ]
        },
    }


def row(injury="QUESTIONABLE", week_projection=15, risk=3.5, recommended=20):
    return {
        "player_id": 99,
        "name": "Candidate",
        "position": "WR",
        "inputs": {
            "availability_status": "WAIVERS",
            "injury_status": injury,
            "projected_avg_points": 20,
            "avg_points": 18,
            "current_week_projected_points": week_projection,
            "current_week_points": None,
            "recent_form": {
                "games_count": 3,
                "median": 16,
                "max_single_game_share": 0.4,
            },
            "percent_started": 40,
        },
        "value": {
            "risk_adjusted_marginal_ppg": risk,
            "expected_added_points_remaining": 35,
            "value_over_best_free_replacement_ppg": 3,
        },
        "suggested_drop": {
            "player_id": 2,
            "name": "Bench WR",
            "position": "WR",
            "projected_avg_points": 10,
        },
        "bid_guidance": {
            "recommended": recommended,
            "reservation_ceiling": 100,
        },
        "market_reference": {"confidence": "high"},
    }


class SoftInjuryAcquisitionGateTests(unittest.TestCase):
    def test_questionable_maintenance_move_is_blocked(self):
        evaluated = evaluate_candidate(
            row(),
            snapshot("maintenance"),
            policy(),
        )
        self.assertFalse(evaluated["eligible"])
        self.assertIn(
            "soft_injury_requires_material_or_launch",
            evaluated["reasons"],
        )

    def test_day_to_day_player_must_be_playable_this_week(self):
        evaluated = evaluate_candidate(
            row(injury="DAY_TO_DAY", week_projection=0),
            snapshot("material"),
            policy(),
        )
        self.assertFalse(evaluated["eligible"])
        self.assertIn(
            "soft_injury_not_playable_this_week",
            evaluated["reasons"],
        )

    def test_soft_injury_paid_move_is_capped_at_cheap_tier(self):
        evaluated = evaluate_candidate(
            row(recommended=50, risk=5),
            snapshot("launch"),
            policy(),
        )
        self.assertFalse(evaluated["eligible"])
        self.assertIn("soft_injury_bid_above_cap", evaluated["reasons"])

    def test_material_questionable_move_can_pass_at_small_bid(self):
        evaluated = evaluate_candidate(
            row(recommended=20, risk=4),
            snapshot("material"),
            policy(),
        )
        self.assertTrue(evaluated["eligible"])
        self.assertEqual(evaluated["selected_bid"], 20)


if __name__ == "__main__":
    unittest.main()
