from __future__ import annotations

import unittest

from waterboys_compute.sniper import evaluate_candidate
from waterboys_compute.value import score_candidate, suggest_drop


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


def player(
    pid,
    name,
    pos,
    projected_avg,
    *,
    slot="BE",
    week_projection=0,
    week_points=None,
    status="ACTIVE",
):
    return {
        "player_id": pid,
        "name": name,
        "position": pos,
        "lineup_slot": slot,
        "injury_status": status,
        "projected_avg_points": projected_avg,
        "avg_points": projected_avg,
        "current_week": {
            "projected_points": week_projection,
            "points": week_points,
            "opponent": None,
            "date": None,
        },
    }


def cheap_policy():
    return {
        "tiers": [
            {
                "name": "cheap",
                "max_bid": 25,
                "min_risk_adjusted_marginal_ppg": 1.5,
                "min_expected_added_points_remaining": 15,
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
            },
            "valuation": {"large_bid_threshold": 100},
        },
        "free_stash": {"enabled": False},
        "growth_discipline": {"enabled": False},
        "priority_caps": {},
    }


def candidate_row(*, week_projection, drop):
    return {
        "player_id": 4569603,
        "name": "Malik Washington",
        "position": "WR",
        "inputs": {
            "projected_avg_points": 21.74,
            "avg_points": 19.44,
            "injury_status": "ACTIVE",
            "availability_status": "WAIVERS",
            "availability_factor": 1,
            "current_week_projected_points": week_projection,
            "current_week_points": None,
            "current_week_opponent": None,
            "current_week_date": None,
            "recent_form": {
                "games_count": 3,
                "median": 20.2,
                "max_single_game_share": 0.39,
            },
            "percent_started": 1.27,
            "percent_owned": 33.51,
        },
        "value": {
            "risk_adjusted_marginal_ppg": 1.89,
            "expected_added_points_remaining": 20.79,
            "value_over_best_free_replacement_ppg": -0.89,
        },
        "suggested_drop": drop,
        "bid_guidance": {
            "recommended": 21,
            "reservation_ceiling": 25,
        },
        "market_reference": {"confidence": "high"},
    }


class CurrentWeekAcquisitionSafetyTests(unittest.TestCase):
    def test_special_team_candidate_replaces_same_position(self):
        roster = [
            player(
                4249087,
                "Matt Gay",
                "K",
                11.89,
                slot="K",
                week_projection=12.66,
            ),
            player(
                -16027,
                "Buccaneers D/ST",
                "D/ST",
                8.25,
                slot="D/ST",
                week_projection=12.14,
            ),
        ]
        candidate = player(
            4567104,
            "Will Reichard",
            "K",
            13.63,
            week_projection=0,
        )

        drop = suggest_drop(roster, candidate, set(), ROSTER_CFG)

        self.assertIsNotNone(drop)
        self.assertEqual(drop["player_id"], 4249087)
        self.assertEqual(drop["position"], "K")

    def test_value_row_preserves_current_week_context(self):
        roster = [
            player(
                4431268,
                "Chimere Dike",
                "WR",
                17.67,
                slot="WR",
                week_projection=17.7,
            ),
        ]
        candidate = player(
            4569603,
            "Malik Washington",
            "WR",
            21.74,
            week_projection=0,
        )
        candidate["availability_status"] = "WAIVERS"

        row = score_candidate(
            candidate,
            "free_agent",
            {
                "roster": roster,
                "acquisition_budget_remaining": 922,
            },
            [candidate],
            ROSTER_CFG,
            11,
            922,
        )

        self.assertEqual(row["inputs"]["current_week_projected_points"], 0)
        self.assertIsNone(row["inputs"]["current_week_points"])

    def test_bye_candidate_cannot_drop_playable_current_starter(self):
        drop = {
            "player_id": 4431268,
            "name": "Chimere Dike",
            "position": "WR",
            "projected_avg_points": 17.67,
        }
        snapshot = {
            "waterboys": {
                "team_id": 18,
                "acquisition_budget_remaining": 922,
                "roster": [
                    player(
                        4431268,
                        "Chimere Dike",
                        "WR",
                        17.67,
                        slot="WR",
                        week_projection=17.7,
                    ),
                ],
            },
            "league": {"roster": ROSTER_CFG},
            "survival": {"waterboys_projected_margin_over_cutline": 88.25},
            "placement_engine": {},
        }

        evaluated = evaluate_candidate(
            candidate_row(week_projection=0, drop=drop),
            snapshot,
            cheap_policy(),
        )

        self.assertFalse(evaluated["eligible"])
        self.assertFalse(evaluated["current_week_playable"])
        self.assertIn(
            "candidate_not_playable_this_week_for_starter_drop",
            evaluated["reasons"],
        )

    def test_playable_same_position_upgrade_can_replace_current_starter(self):
        drop = {
            "player_id": 4431268,
            "name": "Chimere Dike",
            "position": "WR",
            "projected_avg_points": 17.67,
        }
        snapshot = {
            "waterboys": {
                "team_id": 18,
                "acquisition_budget_remaining": 922,
                "roster": [
                    player(
                        4431268,
                        "Chimere Dike",
                        "WR",
                        17.67,
                        slot="WR",
                        week_projection=17.7,
                    ),
                ],
            },
            "league": {"roster": ROSTER_CFG},
            "survival": {"waterboys_projected_margin_over_cutline": 88.25},
            "placement_engine": {},
        }

        evaluated = evaluate_candidate(
            candidate_row(week_projection=18.5, drop=drop),
            snapshot,
            cheap_policy(),
        )

        self.assertTrue(evaluated["eligible"])
        self.assertTrue(evaluated["current_week_playable"])
        self.assertNotIn(
            "candidate_not_playable_this_week_for_starter_drop",
            evaluated["reasons"],
        )
        self.assertNotIn("current_week_starter_downgrade", evaluated["reasons"])


if __name__ == "__main__":
    unittest.main()
