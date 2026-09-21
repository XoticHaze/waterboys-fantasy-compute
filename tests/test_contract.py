from __future__ import annotations

import json
import unittest
from pathlib import Path

from waterboys_compute.command import execute_guarded
from waterboys_compute.normalize import survival_node


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
