from __future__ import annotations

import unittest

from waterboys_compute.sniper import acquisition_roster_blocker, plan_sniper


def policy():
    return {
        "mode": "live", "enabled": True, "max_actions_per_run": 3,
        "tiers": [
            {
                "name": "standard", "max_bid": 100,
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
            "injury": {"block_statuses": ["OUT", "INJURY_RESERVE", "DOUBTFUL"]},
            "valuation": {"large_bid_threshold": 100},
            "recent_form": {"min_games_for_large_bid": 2},
        },
        "free_stash": {"enabled": False},
        "growth_discipline": {"enabled": False},
    }


def snapshot(ir_status="ACTIVE", roster_limit=1):
    return {
        "collected_at": "2026-10-27T23:40:21Z",
        "waterboys": {
            "team_id": 18,
            "acquisition_budget_remaining": 891,
            "roster": [
                {
                    "player_id": 10, "name": "Bench D/ST",
                    "lineup_slot": "BE", "position": "D/ST",
                },
                {
                    "player_id": 11, "name": "Jordan Mason",
                    "lineup_slot": "IR", "injury_status": ir_status, "position": "RB",
                },
            ],
        },
        "league": {"roster": {"size": roster_limit}},
        "survival": {"waterboys_projected_margin_over_cutline": 56},
        "placement_engine": {
            "best_acquisitions": [
                {"player_id": 99, "acquisition_path": "waiver",
                 "move_class": "launch", "estimated_rank_gain": 1},
            ],
        },
        "waiver_offers": [],
        "value_engine": {
            "waiver_targets": [
                {
                    "player_id": 99,
                    "name": "Javonte Williams",
                    "position": "RB",
                    "inputs": {
                        "availability_status": "WAIVERS",
                        "injury_status": "ACTIVE",
                        "projected_avg_points": 26,
                        "avg_points": 26,
                        "current_week_projected_points": 31,
                        "recent_form": {
                            "games_count": 3, "median": 19.4,
                            "max_single_game_share": 0.5357,
                        },
                        "percent_started": 90,
                    },
                    "value": {
                        "risk_adjusted_marginal_ppg": 10.57,
                        "expected_added_points_remaining": 95.13,
                        "value_over_best_free_replacement_ppg": 6,
                    },
                    "suggested_drop": {
                        "player_id": 10, "name": "Bench D/ST",
                        "position": "D/ST", "projected_avg_points": 9,
                    },
                    "market_reference": {"confidence": "high"},
                    "bid_guidance": {"recommended": 59, "reservation_ceiling": 156},
                }
            ],
        },
    }


class HealthyIrAcquisitionBlockTests(unittest.TestCase):
    def test_healthy_ir_player_blocks_new_claims_with_a_reported_plan(self):
        state = snapshot()
        report = plan_sniper(state, policy())
        blocker = report["acquisition_roster_blocker"]
        self.assertEqual(blocker["code"], "healthy_player_in_ir")
        self.assertEqual(blocker["players"][0]["name"], "Jordan Mason")
        self.assertTrue(blocker["requires_active_roster_release"])
        self.assertEqual(blocker["active_roster_count"], 1)
        self.assertEqual(blocker["active_roster_limit"], 1)
        self.assertEqual(report["selected"], [])
        self.assertEqual(
            report["blocked_acquisition_opportunities"][0]["name"], "Javonte Williams"
        )
        self.assertEqual(
            report["blocked_acquisition_opportunities"][0]["selected_bid"], 59
        )
        self.assertTrue(report["top_evaluations"][0]["eligible"])

    def test_questionable_ir_player_does_not_trigger_hard_block(self):
        state = snapshot(ir_status="QUESTIONABLE")
        report = plan_sniper(state, policy())
        self.assertIsNone(report["acquisition_roster_blocker"])
        self.assertEqual(report["selected"][0]["name"], "Javonte Williams")

    def test_open_roster_still_blocks_new_add_until_healthy_ir_is_fixed(self):
        report = plan_sniper(snapshot(roster_limit=2), policy())
        blocker = report["acquisition_roster_blocker"]
        self.assertFalse(blocker["requires_active_roster_release"])
        self.assertEqual(report["selected"], [])

    def test_existing_pending_claim_not_canceled_just_because_ir_became_healthy(self):
        state = snapshot()
        state["waiver_offers"] = [
            {"team_id": 18, "player_id": 99, "offer_id": "pending-claim",
             "result": "PENDING", "bid": 59}
        ]
        report = plan_sniper(state, policy())
        self.assertEqual(report["selected"], [])
        self.assertEqual(report["cancel_actions"], [])
        self.assertEqual(report["acquisition_roster_blocker"]["code"], "healthy_player_in_ir")


if __name__ == "__main__":
    unittest.main()
