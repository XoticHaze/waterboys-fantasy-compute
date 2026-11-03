from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from waterboys_compute.health import sniper_cadence
from waterboys_compute.live_projection import (
    attach_live_finish,
    estimate_player_finish,
    live_survival_forecast,
)
from waterboys_compute.placement import defense_projection_review, elimination_forecast, elimination_race
from waterboys_compute.weekly_audit import weekly_lineup_audit


NOW = datetime(2026, 10, 5, 6, 20, tzinfo=timezone.utc)


def starter(pid, slot, scored, projected, date):
    return {
        "player_id": pid, "name": str(pid), "lineup_slot": slot,
        "position": "RB", "injury_status": "ACTIVE",
        "current_week": {
            "points": scored, "projected_points": projected,
            "date": date,
        },
    }


def team(team_id, name, projected, players):
    scored = sum(
        p["current_week"]["points"]
        for p in players if p["current_week"]["points"] is not None
    )
    return {
        "team_id": team_id, "name": name, "roster_count": len(players),
        "roster": players, "current_week_points": scored,
        "current_week_projected_points": projected,
    }


class LiveSundayForecastTests(unittest.TestCase):
    def test_sunday_finished_points_replace_static_projections(self):
        waterboys = team(18, "WaterBoys", 100.0, [
            starter(1, "QB", 31.0, 27.0, "2026-10-02 00:15:00"),
            starter(2, "RB", 29.0, 48.0, "2026-10-04 18:00:00"),
            starter(3, "D/ST", None, 10.0, "2026-10-06 01:15:00"),
            starter(4, "RB/WR/TE", None, 15.0, "2026-10-06 01:15:00"),
        ])
        higher = team(7, "Opponent", 92, [
            starter(5, "QB", 90.0, 92.0, "2026-10-04 18:00:00"),
        ])
        teams = [waterboys, higher]
        attach_live_finish(teams, NOW)
        self.assertEqual(waterboys["current_week_live_estimated_points"], 85.0)
        self.assertEqual(waterboys["current_week_projected_points"], 100.0)
        forecast = live_survival_forecast(teams, 18)
        self.assertEqual(forecast["waterboys_rank"], 2)
        self.assertEqual(forecast["waterboys_margin"], 0)
        self.assertEqual(forecast["cutline_points"], 85.0)

        survival = {
            "alive_team_count": 2,
            "current_week_ranking": [
                {"team_id": 18, "name": "WaterBoys", "projected_points": 100.0, "projection_rank": 1},
                {"team_id": 7, "name": "Opponent", "projected_points": 92, "projection_rank": 2},
            ],
            "projected_cutline_points": 92,
            "live_forecast": forecast,
        }
        race = elimination_race(teams, survival)
        self.assertEqual(race[0]["team_id"], 18)
        self.assertEqual(race[0]["forecast_basis"], "live_finish_estimate")
        forecasted_elimination = elimination_forecast(teams, survival)
        self.assertEqual(forecasted_elimination["teams"][0]["team_id"], 18)

    def test_live_game_interpolation_does_not_count_entire_projection(self):
        kickoff = NOW - timedelta(hours=2)
        player = starter(1, "QB", 6, 18, kickoff.isoformat())
        estimate = estimate_player_finish(player, NOW)
        self.assertEqual(estimate["mode"], "in_progress_estimate")
        self.assertEqual(estimate["estimated_points"], 12.0)
        self.assertTrue(estimate["uncertain"])

    def test_unavailable_missing_scores_are_explicit(self):
        player = starter(1, "RB", None, 20, "2026-10-04 18:00:00")
        estimate = estimate_player_finish(player, NOW)
        self.assertEqual(estimate["mode"], "missing_completed_score")
        self.assertTrue(estimate["uncertain"])

        empty = team(18, "WaterBoys", 20, [
            starter(1, "QB", None, None, None),
        ])
        attach_live_finish([empty], NOW)
        self.assertIsNone(empty["current_week_live_estimated_points"])
        self.assertEqual(live_survival_forecast([empty], 18)["status"], "unavailable")

    def test_completed_zero_and_negative_points_are_not_treated_missing(self):
        zero = starter(1, "K", 0, 14.0, "2026-10-04 18:00:00")
        negative = starter(2, "D/ST", -2, 10.0, "2026-10-04 18:00:00")
        self.assertEqual(estimate_player_finish(zero, NOW)["estimated_points"], 0)
        self.assertEqual(estimate_player_finish(negative, NOW)["estimated_points"], -2)

    def test_bench_dst_opportunity_waits_for_both_games_to_finish(self):
        seattle = starter(1, "D/ST", None, 10.0, "2026-10-06 01:15:00")
        seattle["name"] = "Defense A"
        seattle["position"] = "D/ST"
        tampa = starter(2, "BE", 23, 8, "2026-10-04 18:00:00")
        tampa["name"] = "Defense B"
        tampa["position"] = "D/ST"
        waterboys = team(18, "WaterBoys", 18, [seattle, tampa])
        partial = weekly_lineup_audit(waterboys, NOW)
        self.assertEqual(partial["status"], "partial")
        self.assertEqual(partial["bench_opportunities"], [])

        seattle["current_week"]["points"] = 6
        after_monday = datetime(2026, 10, 6, 6, 20, tzinfo=timezone.utc)
        finished = weekly_lineup_audit(waterboys, after_monday)
        self.assertEqual(finished["status"], "finished")
        self.assertEqual(finished["bench_opportunities"][0]["hindsight_gain"], 17)
        self.assertTrue(finished["hindsight_only"])

    def test_close_defense_decision_is_review_only(self):
        starter_dst = starter(1, "D/ST", None, 11, "2026-10-06 01:15:00")
        starter_dst["position"] = "D/ST"
        starter_dst["recent_form"] = {"median": 6, "games_count": 3}
        bench_dst = starter(2, "BE", None, 9, "2026-10-05 18:00:00")
        bench_dst["position"] = "D/ST"
        result = defense_projection_review([starter_dst, bench_dst])
        self.assertTrue(result["review_flag"])
        self.assertTrue(result["advisory_only"])
        self.assertEqual(result["projected_starter_edge"], 2)
        self.assertEqual(result["status"], "review_close_projection")

    def test_scheduled_sniper_gap_is_reported(self):
        previous = {"created_at": "2026-10-05T00:30:30Z"}
        health = sniper_cadence(previous, "2026-10-05T06:20:30Z")
        self.assertEqual(health["status"], "overdue")
        self.assertGreaterEqual(health["missed_expected_intervals"], 4)
        self.assertEqual(sniper_cadence(None, "2026-10-05T06:20:30Z")["status"], "unknown_no_previous_report")


if __name__ == "__main__":
    unittest.main()
