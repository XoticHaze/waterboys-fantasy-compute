from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from waterboys_compute.collector import collect_available_statuses, collect_waiver_offers
from waterboys_compute.command import _live_authorized, execute_guarded
from waterboys_compute.espn_write import build_transaction, redacted_transaction
from waterboys_compute.normalize import survival_node
from waterboys_compute.value import (
    build_value_engine,
    calibrated_bid_guidance,
    market_reference,
    optimize,
)


ROOT = Path(__file__).resolve().parents[1]


class ContractTests(unittest.TestCase):
    def test_public_repo_contains_no_private_state_files(self):
        forbidden = [
            ROOT / "state",
            ROOT / "history",
            ROOT / "receipts",
            ROOT / "control" / "pending-command.json",
        ]
        self.assertTrue(all(not path.exists() for path in forbidden))

    def test_worker_uses_exact_oidc_audience(self):
        worker = (ROOT / "cloudflare/waterboys-broker/src/index.js").read_text(encoding="utf-8")
        self.assertIn("waterboys-fantasy-compute", worker)
        self.assertIn("XoticHaze/waterboys-fantasy-compute", worker)
        self.assertIn("repository_visibility !== 'public'", worker)
        self.assertIn("runner_environment !== 'github-hosted'", worker)

    def test_login_bootstrap_is_exact_workflow_gated_and_preserves_worker_secrets(self):
        worker = (ROOT / "cloudflare/waterboys-broker/src/index.js").read_text(encoding="utf-8")
        self.assertIn("espn-session-bootstrap.yml@refs/heads/main", worker)
        self.assertIn("url.pathname === '/v1/login-bootstrap'", worker)
        self.assertIn("url.pathname === '/v1/login-otp'", worker)
        self.assertIn("requireWorkflow(identity, 'login')", worker)
        self.assertIn("env.ESPN_OTP", worker)

        config = json.loads(
            (ROOT / "cloudflare/waterboys-broker/wrangler.jsonc").read_text(encoding="utf-8")
        )
        self.assertIs(config.get("keep_vars"), True)

        workflow = (ROOT / ".github/workflows/espn-session-bootstrap.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("xvfb-run -a node scripts/espn_session_bootstrap.mjs", workflow)
        self.assertIn("WATERBOYS_ESPN_SESSION_PLAINTEXT_DESTROYED=1", workflow)
        bootstrap = (ROOT / "scripts/espn_session_bootstrap.mjs").read_text(encoding="utf-8")
        self.assertIn("WATERBOYS_ESPN_OTP_WAITING", bootstrap)
        self.assertIn("WATERBOYS_ESPN_OTP_RECEIVED", bootstrap)
        self.assertIn("WATERBOYS_ESPN_OTP_RESULT", bootstrap)
        self.assertNotIn("secrets.ESPN_USERNAME", workflow)
        self.assertNotIn("secrets.ESPN_PASSWORD", workflow)
        self.assertNotIn("secrets.ESPN_S2", workflow)
        self.assertNotIn("secrets.ESPN_SWID", workflow)

    def test_survival_node_models_all_play_cutline(self):
        teams = [
            {"team_id": 1, "name": "A", "roster_count": 14, "current_week_points": 120.0, "current_week_projected_points": 130.0},
            {"team_id": 2, "name": "WaterBoys", "roster_count": 14, "current_week_points": 110.0, "current_week_projected_points": 140.0},
            {"team_id": 3, "name": "Eliminated", "roster_count": 0, "current_week_points": None, "current_week_projected_points": None},
        ]
        node = survival_node(teams, 2)
        self.assertEqual(node["alive_team_count"], 2)
        self.assertEqual(node["eliminated_team_count"], 1)
        self.assertEqual(node["current_week_cutline_points"], 110.0)
        self.assertEqual(node["waterboys_margin_over_cutline"], 0.0)
        self.assertEqual(node["elimination_watch"]["team_id"], 2)
        self.assertEqual(node["elimination_watch"]["gap_to_next_team"], 10.0)
        self.assertEqual(teams[0]["current_week_rank"], 1)
        self.assertEqual(teams[1]["current_week_projection_rank"], 1)

    def test_survival_node_uses_projection_before_scoring_starts(self):
        teams = [
            {"team_id": 1, "name": "A", "roster_count": 14, "current_week_points": None, "current_week_projected_points": 150.0, "roster": []},
            {"team_id": 2, "name": "WaterBoys", "roster_count": 14, "current_week_points": None, "current_week_projected_points": 160.0, "roster": []},
            {"team_id": 3, "name": "C", "roster_count": 14, "current_week_points": None, "current_week_projected_points": 140.0, "roster": []},
        ]
        node = survival_node(teams, 2)
        self.assertIsNone(node["current_week_cutline_points"])
        self.assertEqual(node["projected_cutline_points"], 140.0)
        self.assertEqual(node["waterboys_projected_margin_over_cutline"], 20.0)
        self.assertEqual(node["elimination_watch"]["basis"], "projection")
        self.assertEqual(node["elimination_watch"]["team_id"], 3)
        self.assertEqual(node["elimination_watch"]["gap_to_next_team"], 10.0)
        self.assertIsNone(teams[0]["current_week_rank"])
        self.assertEqual(teams[1]["current_week_projection_rank"], 1)

    def test_value_engine_measures_marginal_lineup_gain(self):
        roster_cfg = {
            "slots": {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1, "DST": 1, "K": 1},
            "position_limits": {"QB": 2, "RB": 4, "WR": 4, "TE": 2, "DST": 3, "K": 2},
        }
        def p(pid, name, pos, proj, status="ACTIVE"):
            return {
                "player_id": pid, "name": name, "position": pos,
                "projected_avg_points": proj, "avg_points": proj,
                "injury_status": status, "injured": False,
            }

        waterboys = {
            "team_id": 18, "name": "WaterBoys",
            "acquisition_budget_remaining": 1000,
            "roster": [
                p(1, "QB", "QB", 30), p(2, "RB1", "RB", 18),
                p(3, "RB2", "RB", 13.5), p(4, "WR1", "WR", 25),
                p(5, "WR2", "WR", 19), p(6, "WR3", "WR", 14.5),
                p(7, "TE1", "TE", 15), p(8, "DST", "D/ST", 9),
                p(9, "K", "K", 10), p(10, "QB2", "QB", 28),
                p(11, "WR4", "WR", 7), p(12, "TE2", "TE", 5),
                p(13, "DST2", "D/ST", 8), p(14, "DST3", "D/ST", 7.5),
            ],
        }
        free_agents = [
            p(100, "Cheap RB", "RB", 13.0),
            p(101, "Cheap WR", "WR", 12.0),
            p(102, "Better DST", "D/ST", 13.0),
        ]
        at_risk = {
            "team_id": 3, "name": "At Risk", "roster_count": 14,
            "roster": [p(200, "Elite RB", "RB", 31.0)],
        }
        teams = [waterboys, at_risk]
        survival = {"elimination_watch": {"team_id": 3}}
        settings = {"regular_season_count": 17}
        league_cfg = {
            "current_week": 2, "roster": roster_cfg,
            "waivers": {"faab_start": 1000},
        }

        base = optimize(waterboys["roster"], roster_cfg)
        self.assertAlmostEqual(base["projected_ppg"], 154.0)

        engine = build_value_engine(
            waterboys, teams, free_agents, survival, league_cfg, settings
        )
        elite = engine["elimination_watch_targets"][0]
        self.assertAlmostEqual(elite["value"]["marginal_lineup_ppg"], 17.5)
        self.assertAlmostEqual(elite["value"]["expected_added_points_remaining"], 262.5)
        self.assertEqual(elite["value"]["best_free_replacement"], "Cheap RB")
        self.assertTrue(elite["value"]["immediate_starter"])
        self.assertGreaterEqual(elite["faab_reference"]["midpoint"], 300)
        self.assertLessEqual(elite["faab_reference"]["midpoint"], 500)
        self.assertTrue(elite["faab_reference"]["advisory_only"])
        self.assertGreater(elite["cost_efficiency"]["remaining_points_per_100_faab_at_midpoint"], 0)

        better_dst = next(
            row for row in engine["waiver_targets"] if row["name"] == "Better DST"
        )
        self.assertEqual(better_dst["suggested_drop"]["position"], "D/ST")

    def test_live_authority_is_action_scoped_after_canary(self):
        policy = {
            "proven_actions": ["waiver_claim"],
            "autonomy": {"routine_auto_execute": True},
            "canary": {"enabled": False, "command_id": None, "action": None},
        }
        self.assertEqual(
            _live_authorized(policy, "routine-waiver", "waiver_claim"),
            (True, "proven_action_autonomy"),
        )
        allowed, reason = _live_authorized(policy, "routine-lineup", "lineup_move")
        self.assertFalse(allowed)
        self.assertIn("lineup_move", reason)

        canary_policy = {
            "proven_actions": [],
            "autonomy": {"routine_auto_execute": False},
            "canary": {
                "enabled": True,
                "command_id": "canary-waiver-001",
                "action": "waiver_claim",
            },
        }
        self.assertTrue(
            _live_authorized(canary_policy, "canary-waiver-001", "waiver_claim")[0]
        )
        self.assertFalse(
            _live_authorized(canary_policy, "canary-waiver-001", "lineup_move")[0]
        )

    def test_broker_clears_only_matching_completed_command_slot(self):
        worker = (ROOT / "cloudflare/waterboys-broker/src/index.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("function commandSlotIdentity(slot)", worker)
        self.assertIn("clearCommandSlotIfMatched", worker)
        self.assertIn("command_slot_moved", worker)
        self.assertIn("'control/pending-command.json'", worker)

    def test_available_status_probe_distinguishes_free_agent_and_waivers(self):
        class FakeRequest:
            def league_get(self, params=None, headers=None):
                self.params = params
                self.headers = headers
                return {
                    "players": [
                        {"status": "FREEAGENT", "player": {"id": 100}},
                        {"status": "WAIVERS", "player": {"id": 200}},
                    ]
                }

        class FakeLeague:
            def __init__(self):
                self.espn_request = FakeRequest()

        statuses = collect_available_statuses(FakeLeague(), 3)
        self.assertEqual(statuses[100], "FREEAGENT")
        self.assertEqual(statuses[200], "WAIVERS")

    def test_waiver_offer_compat_reads_mtransactions2_without_unreleased_helper(self):
        class FakeRequest:
            def league_get(self, params=None, headers=None):
                self.params = params
                self.headers = headers
                return {
                    "transactions": [
                        {
                            "id": "offer-1",
                            "teamId": 7,
                            "type": "WAIVER",
                            "status": "EXECUTED",
                            "processDate": 123456,
                            "bidAmount": 51,
                            "items": [
                                {"type": "ADD", "playerId": 100},
                                {"type": "DROP", "playerId": 200},
                            ],
                        },
                        {
                            "id": "offer-2",
                            "teamId": 8,
                            "type": "WAIVER_ERROR",
                            "status": "FAILED",
                            "errorCode": "OUTBID",
                            "processDate": 123455,
                            "bidAmount": 44,
                            "items": [{"type": "ADD", "playerId": 100}],
                        },
                    ]
                }

        class FakeLeague:
            def __init__(self):
                self.espn_request = FakeRequest()
                self.player_map = {100: "Premium RB", 200: "Roster Cut"}

        player_index = {
            100: {"name": "Premium RB", "position": "RB", "projected_avg_points": 30.0},
            200: {"name": "Roster Cut", "position": "WR", "projected_avg_points": 7.0},
        }
        rows = collect_waiver_offers(
            FakeLeague(),
            1,
            {7: "Winner", 8: "Runner Up"},
            player_index,
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["bid"], 51)
        self.assertEqual(rows[0]["position"], "RB")
        self.assertEqual(rows[1]["bid"], 44)
        self.assertIn("OUTBID", rows[1]["result"])

    def test_waiver_write_adapter_builds_faab_add_drop_without_leaking_member_id(self):
        runtime = {
            "league": {"league_id": 594260315, "season": 2026, "team_id": 18},
            "swid": "{TEST-SWID}",
            "espn_s2": "test-secret",
        }
        fresh = {
            "league": {"current_week": 3, "nfl_week": 3},
            "waterboys": {
                "team_id": 18,
                "acquisition_budget_remaining": 1000,
                "roster": [{"player_id": 4430834, "name": "Jalen McMillan"}],
            },
            "free_agents": [{"player_id": 4569371, "name": "Isaiah Williams"}],
        }
        command = {
            "command_id": "waiver-isaiah-001",
            "action": "waiver_claim",
            "player_id": 4569371,
            "drop_player_id": 4430834,
            "faab_bid": 71,
            "dry_run": True,
        }
        body = build_transaction(runtime, command, fresh)
        self.assertEqual(body["type"], "WAIVER")
        self.assertEqual(body["bidAmount"], 71)
        self.assertEqual(body["teamId"], 18)
        self.assertEqual(body["items"][0]["type"], "ADD")
        self.assertEqual(body["items"][1]["type"], "DROP")
        safe = redacted_transaction(body)
        self.assertEqual(safe["memberId"], "[REDACTED]")
        self.assertNotIn("test-secret", json.dumps(safe))

    def test_standalone_free_agent_drop_builds_and_dry_runs_without_mutation(self):
        runtime = {
            "league": {"league_id": 594260315, "season": 2026, "team_id": 18},
            "swid": "{TEST-SWID}",
            "espn_s2": "test-secret",
            "policy": {
                "writes": {
                    "enabled": True,
                    "mode": "live",
                    "allowed_actions": ["free_agent_drop"],
                    "proven_actions": [],
                    "autonomy": {"routine_auto_execute": True},
                    "canary": {"enabled": False, "command_id": None, "action": None},
                }
            },
        }
        fresh = {
            "collected_at": "2026-09-23T21:00:00Z",
            "league": {"current_week": 3, "nfl_week": 3},
            "waterboys": {
                "team_id": 18,
                "acquisition_budget_remaining": 1000,
                "roster": [{"player_id": -16020, "name": "Jets D/ST"}],
            },
            "teams": [{"team_id": 18}],
            "free_agents": [],
        }
        command = {
            "command_id": "drop-dryrun-jets-001",
            "action": "free_agent_drop",
            "player_id": -16020,
            "dry_run": True,
        }
        body = build_transaction(runtime, command, fresh)
        self.assertEqual(body["type"], "FREEAGENT")
        self.assertEqual(body["items"], [
            {"playerId": -16020, "type": "DROP", "fromTeamId": 18}
        ])

        with patch("waterboys_compute.command.collect_snapshot", return_value=fresh):
            receipt = execute_guarded(runtime, {
                "status": "pending",
                "command": command,
            })
        self.assertEqual(receipt["status"], "dry_run")
        self.assertFalse(receipt["mutation_attempted"])
        self.assertEqual(receipt["would_send"]["items"][0]["type"], "DROP")

    def test_command_lane_accepts_multiple_dry_run_claims(self):
        fresh = {
            "collected_at": "2026-09-23T19:00:00Z",
            "league": {"current_week": 3, "nfl_week": 3},
            "waterboys": {
                "team_id": 18,
                "acquisition_budget_remaining": 1000,
                "roster": [
                    {"player_id": 4430834, "name": "Jalen McMillan"},
                    {"player_id": -16006, "name": "Cowboys D/ST"},
                ],
            },
            "teams": [{"team_id": 18}],
            "free_agents": [
                {"player_id": 4569371, "name": "Isaiah Williams"},
                {"player_id": 4428557, "name": "Tyjae Spears"},
            ],
        }
        runtime = {
            "league": {"league_id": 594260315, "season": 2026, "team_id": 18},
            "swid": "{TEST-SWID}",
            "espn_s2": "test-secret",
            "policy": {
                "writes": {
                    "enabled": False,
                    "mode": "dry_run",
                    "allowed_actions": ["waiver_claim"],
                }
            },
        }
        slot = {
            "status": "pending",
            "batch_id": "week3-claims-001",
            "commands": [
                {
                    "command_id": "week3-isaiah",
                    "action": "waiver_claim",
                    "player_id": 4569371,
                    "drop_player_id": 4430834,
                    "faab_bid": 71,
                    "dry_run": True,
                },
                {
                    "command_id": "week3-spears",
                    "action": "waiver_claim",
                    "player_id": 4428557,
                    "drop_player_id": -16006,
                    "faab_bid": 5,
                    "dry_run": True,
                },
            ],
        }
        with patch("waterboys_compute.command.collect_snapshot", return_value=fresh):
            receipt = execute_guarded(runtime, slot)
        self.assertEqual(receipt["status"], "batch_dry_run")
        self.assertFalse(receipt["mutation_attempted"])
        self.assertEqual(len(receipt["results"]), 2)
        self.assertEqual(receipt["results"][0]["would_send"]["bidAmount"], 71)
        self.assertEqual(receipt["results"][1]["would_send"]["bidAmount"], 5)

    def test_faab_guidance_uses_market_price_but_preserves_value_ceiling(self):
        candidate = {
            "player_id": 900,
            "name": "Premium RB",
            "position": "RB",
            "projected_avg_points": 30.0,
        }
        market = {
            "successful_waiver_bids": [
                {"player_id": 1, "player": "RB A", "position": "RB", "projected_avg_points": 29.0, "bid": 51},
                {"player_id": 2, "player": "RB B", "position": "RB", "projected_avg_points": 18.0, "bid": 20},
                {"player_id": 3, "player": "WR A", "position": "WR", "projected_avg_points": 27.0, "bid": 351},
            ]
        }
        market_ref = market_reference(candidate, market, [])
        self.assertEqual(market_ref["sample_basis"], "same_position_similar_projection")
        self.assertEqual(market_ref["sample_size"], 1)
        self.assertEqual(market_ref["p90"], 51)

        guidance = calibrated_bid_guidance(
            {"applicable": True, "low": 280, "midpoint": 400, "high": 460},
            market_ref,
            risk_delta=17.0,
            budget=1000,
        )
        self.assertEqual(guidance["recommended"], 56)
        self.assertEqual(guidance["reservation_ceiling"], 460)
        self.assertLess(guidance["recommended"], guidance["reservation_ceiling"])

    def test_broker_reads_large_private_files_via_git_blob_fallback(self):
        worker = (ROOT / "cloudflare/waterboys-broker/src/index.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("/git/blobs/", worker)
        self.assertIn("github_blob_read_", worker)
        self.assertIn("github_blob_invalid", worker)
        self.assertIn("Contents API omits inline content", worker)

    def test_worker_persists_compact_takeover_brief(self):
        worker = (ROOT / "cloudflare/waterboys-broker/src/index.js").read_text(encoding="utf-8")
        self.assertIn("function buildBrief(snapshot, runId, stateCommit)", worker)
        self.assertIn("'state/brief.json'", worker)
        self.assertIn("waterboys.brief.v1", worker)
        self.assertIn("market_reference: row && row.market_reference", worker)
        self.assertIn("bid_guidance: row && row.bid_guidance", worker)
        self.assertIn("diagnostics: snapshot.diagnostics || {}", worker)

    def test_snapshot_workflow_has_dedicated_concurrency(self):
        text = (ROOT / ".github/workflows/snapshot.yml").read_text(encoding="utf-8")
        self.assertIn("group: waterboys-snapshot-r1", text)
        self.assertNotIn("mmibkr", text.lower())
        self.assertNotIn("commandcenter", text.lower())

    def test_private_credentials_are_not_named_as_actions_secrets(self):
        workflows = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (ROOT / ".github/workflows").glob("*.yml")
        )
        self.assertNotIn("secrets.ESPN_S2", workflows)
        self.assertNotIn("secrets.ESPN_SWID", workflows)
        self.assertNotIn("secrets.OPS_GITHUB_TOKEN", workflows)


if __name__ == "__main__":
    unittest.main()
