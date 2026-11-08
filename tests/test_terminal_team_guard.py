from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from waterboys_compute.command import _execute_one
from waterboys_compute.sniper import plan_sniper
from waterboys_compute.team_lifecycle import team_write_block_reason


def snapshot(*, eliminated=False, roster=None, rankings=True):
    if roster is None:
        roster = [{"player_id": 101, "lineup_slot": "QB"}]
    return {
        "collected_at": "2026-10-05T18:00:00Z",
        "waterboys": {
            "team_id": 3,
            "name": "Example Team",
            "roster": roster,
            "roster_count": len(roster),
        },
        "survival": {
            "eliminated_teams": [{"team_id": 3}] if eliminated else [],
            "current_week_ranking": (
                [{"team_id": 2}, {"team_id": 3}] if rankings else []
            ),
        },
        "value_engine": {"waiver_targets": []},
    }


class TerminalTeamGateTests(unittest.TestCase):
    def test_known_elimination_blocks_even_with_nonempty_roster(self):
        self.assertEqual(team_write_block_reason(snapshot(eliminated=True)), "team_eliminated")

    def test_empty_roster_without_elimination_flag_fails_closed(self):
        self.assertEqual(team_write_block_reason(snapshot(roster=[])), "team_roster_empty")

    def test_missing_survival_state_fails_closed(self):
        self.assertEqual(
            team_write_block_reason({"waterboys": {"team_id": 3, "roster": [1]}}),
            "team_or_survival_state_missing",
        )

    def test_ranking_exclusion_fails_closed(self):
        state = snapshot()
        state["survival"]["current_week_ranking"] = [{"team_id": 4}]
        self.assertEqual(
            team_write_block_reason(state),
            "team_absent_from_survivor_ranking",
        )

    def test_active_team_still_eligible(self):
        self.assertIsNone(team_write_block_reason(snapshot()))

    def test_sniper_planner_never_attempts_add_or_cancel_for_eliminated_team(self):
        state = snapshot(eliminated=True, roster=[])
        state["waiver_offers"] = [{
            "team_id": 3, "player_id": 70, "result": "PENDING", "offer_id": "offer-test"
        }]
        state["value_engine"]["waiver_targets"] = [{
            "player_id": 70, "name": "Example Player", "position": "RB",
            "inputs": {"availability_status": "FREEAGENT", "injury_status": "ACTIVE"},
            "value": {"risk_adjusted_marginal_ppg": 20, "expected_added_points_remaining": 200},
        }]
        report = plan_sniper(state, {"mode": "live", "enabled": True})
        self.assertEqual(report["status"], "blocked_team_inactive")
        self.assertEqual(report["inactivity_reason"], "team_eliminated")
        self.assertEqual(report["selected"], [])
        self.assertEqual(report["cancel_actions"], [])
        self.assertEqual(report["top_evaluations"], [])

    @patch("waterboys_compute.command.validate_preflight")
    @patch("waterboys_compute.command.build_transaction")
    @patch("waterboys_compute.command.post_transaction")
    @patch("waterboys_compute.command.collect_snapshot")
    def test_direct_command_blocks_before_constructing_or_sending_transaction(
        self, collect, send, build, validate
    ):
        collect.return_value = snapshot(eliminated=True, roster=[])
        runtime = {"policy": {"writes": {
            "enabled": True, "mode": "live",
            "allowed_actions": ["free_agent_add"],
            "proven_actions": ["free_agent_add"],
            "autonomy": {"routine_auto_execute": True},
        }}}
        receipt = _execute_one(runtime, {
            "command_id": "synthetic-example",
            "action": "free_agent_add",
            "player_id": 101,
            "dry_run": False,
        })
        self.assertEqual(receipt["status"], "blocked_team_inactive")
        self.assertFalse(receipt["mutation_attempted"])
        validate.assert_not_called()
        build.assert_not_called()
        send.assert_not_called()

    @patch("waterboys_compute.cli.collect_player_history")
    @patch("waterboys_compute.cli.execute_guarded")
    @patch("waterboys_compute.cli._execute_lineup_repairs")
    @patch("waterboys_compute.cli.collect_snapshot")
    @patch("waterboys_compute.cli.Broker")
    @patch("sys.argv", ["waterboys", "snipe", "--broker", "https://example.invalid"])
    def test_cli_emits_read_only_inactive_report(self, broker_type, collect, repairs, execute, history):
        from waterboys_compute.cli import main

        collect.return_value = snapshot(eliminated=True, roster=[])
        instance = broker_type.return_value
        instance.runtime_config.return_value = {
            "sniper": {"enabled": True, "mode": "live"}, "sniper_state": None
        }
        instance.publish_snapshot.return_value = {"status": "accepted"}
        instance.publish_sniper_report.return_value = {"status": "accepted"}
        with patch("builtins.print"):
            self.assertEqual(main(), 0)
        reports = instance.publish_sniper_report.call_args.args[0]
        self.assertEqual(reports["status"], "blocked_team_inactive")
        self.assertEqual(reports["executions"], [])
        repairs.assert_not_called()
        execute.assert_not_called()
        history.assert_not_called()


if __name__ == "__main__":
    unittest.main()
