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


if __name__ == "__main__":
    unittest.main()
