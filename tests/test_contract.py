from __future__ import annotations

import json
import unittest
from pathlib import Path

from waterboys_compute.command import execute_guarded
from waterboys_compute.normalize import survival_node
from waterboys_compute.value import build_value_engine, optimize


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
