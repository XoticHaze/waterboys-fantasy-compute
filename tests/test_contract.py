from __future__ import annotations

import json
import unittest
from pathlib import Path

from waterboys_compute.command import execute_guarded


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
