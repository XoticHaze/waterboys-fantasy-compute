from __future__ import annotations

import unittest

from waterboys_compute.placement import elimination_forecast
from waterboys_compute.value import (
    budget_competition,
    calibrated_bid_guidance,
    market_reference,
)


class EliminationFaabIntelligenceTests(unittest.TestCase):
    def test_failed_offers_do_not_contaminate_clearing_prices(self):
        candidate = {
            "player_id": 99,
            "name": "Target RB",
            "position": "RB",
            "projected_avg_points": 20,
        }
        market = {
            "successful_waiver_bids": [
                {
                    "player_id": 1,
                    "player": "Comparable RB",
                    "team_id": 2,
                    "position": "RB",
                    "projected_avg_points": 19,
                    "bid": 40,
                }
            ]
        }
        offers = [
            {
                "player_id": 2,
                "player": "Failed RB",
                "team_id": 3,
                "position": "RB",
                "projected_avg_points": 21,
                "bid": 250,
                "result": "FAILED_INVALIDPLAYERSOURCE",
            }
        ]

        ref = market_reference(candidate, market, offers)

        self.assertEqual(ref["sample_size"], 1)
        self.assertEqual(ref["median"], 40)
        self.assertEqual(ref["max"], 40)
        self.assertEqual(ref["failed_demand"]["sample_size"], 1)
        self.assertEqual(ref["failed_demand"]["max"], 250)
        self.assertFalse(ref["failed_demand"]["clearing_price_eligible"])

    def test_budget_competition_excludes_waterboys_and_eliminated_source_owner(self):
        market = {
            "budget_leaderboard": [
                {"team_id": 18, "name": "WaterBoys", "remaining": 922},
                {"team_id": 6, "name": "Eliminated Source", "remaining": 1000},
                {"team_id": 2, "name": "Rival A", "remaining": 1000},
                {"team_id": 3, "name": "Rival B", "remaining": 500},
                {"team_id": 4, "name": "Rival C", "remaining": 20},
            ]
        }

        pressure = budget_competition(
            market,
            waterboys_team_id=18,
            source_team_id=6,
            target_bid=100,
            waterboys_budget=922,
        )

        self.assertEqual(pressure["competitor_count"], 3)
        self.assertEqual(pressure["competitors_capable_at_target_bid"], 2)
        self.assertEqual(pressure["competitors_with_more_faab_than_waterboys"], 1)
        self.assertEqual(pressure["budget_rank_if_all_bid"], 2)

    def test_bid_guidance_never_chases_above_intrinsic_ceiling(self):
        value_reference = {
            "applicable": True,
            "midpoint": 60,
            "high": 75,
        }
        market_ref = {
            "sample_size": 8,
            "confidence": "high",
            "median": 80,
            "p75": 100,
            "p90": 140,
        }

        guidance = calibrated_bid_guidance(
            value_reference,
            market_ref,
            risk_delta=4,
            budget=922,
        )

        self.assertEqual(guidance["recommended"], 75)
        self.assertEqual(guidance["reservation_ceiling"], 75)
        self.assertFalse(guidance["expected_to_clear_reference"])
        self.assertEqual(guidance["market_posture"], "do_not_chase")

    def test_elimination_forecast_prefers_projected_last_not_current_actual_last(self):
        teams = [
            {
                "team_id": 2,
                "name": "Actual Last",
                "acquisition_budget_remaining": 1000,
                "roster": [],
            },
            {
                "team_id": 6,
                "name": "Projected Last",
                "acquisition_budget_remaining": 1000,
                "roster": [],
            },
            {
                "team_id": 18,
                "name": "WaterBoys",
                "acquisition_budget_remaining": 922,
                "roster": [],
            },
        ]
        survival = {
            "alive_team_count": 3,
            "current_week_ranking": [
                {
                    "rank": 3,
                    "team_id": 2,
                    "name": "Actual Last",
                    "points": 10,
                    "projected_points": 140,
                    "projection_rank": 2,
                },
                {
                    "rank": 2,
                    "team_id": 6,
                    "name": "Projected Last",
                    "points": 60,
                    "projected_points": 85,
                    "projection_rank": 3,
                },
                {
                    "rank": 1,
                    "team_id": 18,
                    "name": "WaterBoys",
                    "points": 80,
                    "projected_points": 170,
                    "projection_rank": 1,
                },
            ],
        }

        forecast = elimination_forecast(teams, survival)
        rows = forecast["teams"]

        self.assertEqual(rows[0]["team_id"], 6)
        self.assertEqual(rows[0]["forecast_tier"], "projected_favorite")
        self.assertGreater(
            rows[0]["relative_elimination_risk_share"],
            next(
                row["relative_elimination_risk_share"]
                for row in rows
                if row["team_id"] == 2
            ),
        )
        self.assertTrue(forecast["not_calibrated_probability"])


    def test_premium_bid_stress_keeps_cheap_reference_but_disclaims_clearing(self):
        candidate = {
            "player_id": 50, "position": "RB", "projected_avg_points": 30,
            "percent_started": 92, "positional_rank": 3,
        }
        market = {
            "successful_waiver_bids": [
                {"player_id": 1, "player": "Jahmyr Gibbs", "team_id": 16,
                 "position": "RB", "projected_avg_points": 39.17, "bid": 461},
                {"player_id": 2, "player": "D'Andre Swift", "team_id": 9,
                 "position": "RB", "projected_avg_points": 22.58, "bid": 55},
                {"player_id": 3, "player": "MarShawn Lloyd", "team_id": 14,
                 "position": "RB", "projected_avg_points": 3.66, "bid": 250},
                {"player_id": 4, "player": "CeeDee Lamb", "team_id": 8,
                 "position": "WR", "projected_avg_points": 25.31, "bid": 361},
                {"player_id": 5, "player": "Low WR", "team_id": 11,
                 "position": "WR", "projected_avg_points": 10, "bid": 400},
            ]
        }
        ref = market_reference(candidate, market, [])
        stress = ref["premium_auction_stress"]
        self.assertTrue(stress["premium_candidate"])
        self.assertEqual(stress["verified_same_position_premium_clears"], 1)
        self.assertEqual(stress["highest_verified_same_position_bid"], 461)
        self.assertEqual(stress["verified_cross_position_premium_clears"], 2)
        self.assertEqual(
            [row["player"] for row in stress["cross_position_winning_bids"]],
            ["Jahmyr Gibbs", "CeeDee Lamb"],
        )
        # This still shows the old projection-matched reference ($55).
        # A historical $461 star sale cannot automatically inflate our bid.
        self.assertEqual(ref["median"], 55)
        guidance = calibrated_bid_guidance(
            {"applicable": True, "midpoint": 175, "high": 200},
            ref, risk_delta=12, budget=891,
        )
        self.assertEqual(guidance["recommended"], 59)
        self.assertEqual(guidance["reservation_ceiling"], 200)
        self.assertIsNone(guidance["expected_to_clear_reference"])
        self.assertEqual(guidance["market_posture"], "premium_auction_uncertain")
        self.assertTrue(guidance["historical_premium_bid_above_reservation"])

        market["budget_leaderboard"] = [
            {"team_id": 18, "remaining": 891},
            {"team_id": 7, "remaining": 1000},  # eliminated source excluded
            {"team_id": 5, "remaining": 1000},
            {"team_id": 8, "remaining": 59},
            {"team_id": 16, "remaining": 201},
        ]
        rivals = budget_competition(
            market, waterboys_team_id=18, source_team_id=7,
            target_bid=stress["highest_verified_same_position_bid"],
            waterboys_budget=891,
        )
        self.assertEqual(rivals["competitor_count"], 3)
        self.assertEqual(rivals["competitors_capable_at_target_bid"], 1)

    def test_elite_te_without_premium_te_clear_has_unknown_clearing_probability(self):
        candidate = {
            "player_id": 55, "position": "TE", "projected_avg_points": 25.95,
            "percent_started": 96.3, "positional_rank": 2,
        }
        market = {
            "successful_waiver_bids": [
                {"player_id": 1, "position": "TE", "projected_avg_points": 12.88,
                 "player": "Dallas Goedert", "bid": 25},
                {"player_id": 2, "position": "TE", "projected_avg_points": 14.25,
                 "player": "Tyler Warren", "bid": 41},
                {"player_id": 3, "position": "WR", "projected_avg_points": 25,
                 "player": "CeeDee Lamb", "bid": 361},
            ]
        }
        ref = market_reference(candidate, market, [])
        stress = ref["premium_auction_stress"]
        self.assertTrue(stress["premium_candidate"])
        self.assertEqual(stress["verified_same_position_premium_clears"], 0)
        self.assertEqual(stress["verified_cross_position_premium_clears"], 1)
        guidance = calibrated_bid_guidance(
            {"applicable": True, "midpoint": 177, "high": 204},
            ref, risk_delta=11, budget=891,
        )
        self.assertEqual(guidance["recommended"], 45)
        self.assertIsNone(guidance["expected_to_clear_reference"])
        self.assertIsNone(guidance["historical_premium_bid_above_reservation"])

    def test_ordinary_bid_guidance_unchanged(self):
        candidate = {
            "player_id": 60, "position": "RB", "projected_avg_points": 15,
            "percent_started": 12, "positional_rank": 45,
        }
        market = {
            "successful_waiver_bids": [
                {"player_id": 1, "position": "RB",
                 "projected_avg_points": 14, "bid": 20},
            ]
        }
        ref = market_reference(candidate, market, [])
        self.assertFalse(ref["premium_auction_stress"]["premium_candidate"])
        guidance = calibrated_bid_guidance(
            {"applicable": True, "midpoint": 40, "high": 50},
            ref, risk_delta=4, budget=891,
        )
        self.assertEqual(guidance["recommended"], 24)
        self.assertTrue(guidance["expected_to_clear_reference"])
        self.assertFalse(guidance["premium_auction_warning"])


if __name__ == "__main__":
    unittest.main()
