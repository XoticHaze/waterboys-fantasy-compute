from __future__ import annotations

import unittest

from waterboys_compute.value import build_trade_exchange_board


ROSTER_CFG = {
    "size": 6,
    "slots": {
        "QB": 0,
        "RB": 1,
        "WR": 1,
        "TE": 0,
        "FLEX": 0,
        "DST": 0,
        "K": 0,
    },
    "position_limits": {
        "QB": 2,
        "RB": 4,
        "WR": 4,
        "TE": 2,
        "DST": 2,
        "K": 2,
    },
}


def player(pid, name, pos, projection, slot="BE", status="ACTIVE"):
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
        },
    }


class TradeLeverageEngineTests(unittest.TestCase):
    def setUp(self):
        self.waterboys = {
            "team_id": 18,
            "name": "WaterBoys",
            "roster_count": 3,
            "roster": [
                player(1, "Strong WR", "WR", 20, "WR"),
                player(2, "Trade WR", "WR", 18, "BE"),
                player(3, "Weak RB", "RB", 8, "RB"),
            ],
        }
        self.rival = {
            "team_id": 7,
            "name": "RB Heavy",
            "roster_count": 3,
            "roster": [
                player(10, "Strong RB", "RB", 20, "RB"),
                player(11, "Trade RB", "RB", 18, "BE"),
                player(12, "Weak WR", "WR", 8, "WR"),
            ],
        }
        self.free_agents = [
            player(100, "Free WR", "WR", 5),
            player(101, "Free RB", "RB", 5),
        ]

    def test_mutually_beneficial_exchange_uses_each_teams_roster_fit(self):
        exchanges, _ = build_trade_exchange_board(
            self.waterboys,
            [self.waterboys, self.rival],
            self.free_agents,
            ROSTER_CFG,
            8,
        )

        row = next(
            item for item in exchanges
            if item["incoming"]["player_id"] == 11
            and item["outgoing"]["player_id"] == 2
        )
        self.assertTrue(row["mutually_beneficial"])
        self.assertEqual(row["acceptance_signal"], "mutual_gain")
        self.assertEqual(row["waterboys_risk_adjusted_ppg_gain"], 10.0)
        self.assertEqual(row["counterparty_risk_adjusted_ppg_gain"], 10.0)
        self.assertEqual(row["waterboys_expected_added_points_remaining"], 80.0)

    def test_redundant_scarce_asset_is_marked_trade_before_drop(self):
        _, assets = build_trade_exchange_board(
            self.waterboys,
            [self.waterboys, self.rival],
            self.free_agents,
            ROSTER_CFG,
            8,
        )

        asset = next(item for item in assets if item["player_id"] == 2)
        self.assertEqual(asset["risk_adjusted_lineup_loss_if_removed_ppg"], 0.0)
        self.assertGreaterEqual(asset["scarcity_over_best_free_ppg"], 10)
        self.assertGreater(asset["mutually_beneficial_trade_count"], 0)
        self.assertTrue(asset["trade_before_drop"])
        self.assertEqual(
            asset["best_trade_return"]["incoming"]["player_id"],
            11,
        )

    def test_ir_assets_are_not_used_as_routine_trade_chips(self):
        self.waterboys["roster"][1]["lineup_slot"] = "IR"
        exchanges, assets = build_trade_exchange_board(
            self.waterboys,
            [self.waterboys, self.rival],
            self.free_agents,
            ROSTER_CFG,
            8,
        )

        self.assertFalse(any(
            (item.get("outgoing") or {}).get("player_id") == 2
            for item in exchanges
        ))
        self.assertFalse(any(item.get("player_id") == 2 for item in assets))


if __name__ == "__main__":
    unittest.main()
