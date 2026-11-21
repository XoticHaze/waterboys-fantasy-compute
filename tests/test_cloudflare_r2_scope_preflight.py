"""Offline fixed-scope checks for WaterBoys' existing scoped R2 deployment job."""
from __future__ import annotations
import importlib.util
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts/cloudflare_r2_scope_preflight.py"
spec = importlib.util.spec_from_file_location("cc_waterboys_r2_preflight", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class NarrowScopePreflightTests(unittest.TestCase):
    def safe_probe(self, account, worker):
        if worker == module.ALLOW_WORKER and account == module.ORIGINAL_ACCOUNT:
            return (200, True)
        return (403, False)

    def test_exact_single_worker_read_and_inaccessible_others_pass(self):
        visited = []
        def probe(account, worker):
            visited.append((account, worker))
            return self.safe_probe(account, worker)
        receipt = module.validate_scope(probe)
        self.assertEqual(visited, [(a, w) for _, a, w, _ in module.TARGETS])
        self.assertEqual(len(visited), 2 + len(module.OTHER_ORIGINAL_WORKERS) +
                         len(module.PROTECTED_NEUTRAL))
        self.assertEqual(receipt["allowed_worker_metadata_read"], True)
        self.assertEqual(receipt["other_worker_metadata_inaccessible"], True)
        self.assertFalse(receipt["write_isolation_live_proven"])
        self.assertTrue(receipt["owner_individual_worker_editor_policy_review_required"])
        self.assertEqual(receipt["cloudflare_mutations"], 0)
        self.assertFalse(receipt["token_value_exported"])
        self.assertNotIn("Bearer", json.dumps(receipt))

    def test_factory_settings_readable_fail_closed(self):
        def probe(account, worker):
            if worker == module.FACTORY_WORKER:
                return (200, True)
            return self.safe_probe(account, worker)
        with self.assertRaisesRegex(ValueError, "unexpected_other_worker"):
            module.validate_scope(probe)

    def test_other_original_worker_access_rejected(self):
        def probe(account, worker):
            if worker == "fleet-authority":
                return (200, True)
            return self.safe_probe(account, worker)
        with self.assertRaises(ValueError):
            module.validate_scope(probe)

    def test_protected_neutral_worker_access_rejected(self):
        def probe(account, worker):
            if worker == "reference-release-broker-v1":
                return (200, True)
            return self.safe_probe(account, worker)
        with self.assertRaises(ValueError):
            module.validate_scope(probe)

    def test_unexpected_errors_redirects_or_server_failures_denied(self):
        for status in [302, 429, 500, 599]:
            def probe(account, worker):
                if worker == module.FACTORY_WORKER:
                    return (status, False)
                return self.safe_probe(account, worker)
            with self.assertRaises(ValueError):
                module.validate_scope(probe)

    def test_403_and_404_are_observations_not_write_denial_proof(self):
        def probe(account, worker):
            if worker == module.ALLOW_WORKER:
                return (200, True)
            return (404, False)
        receipt = module.validate_scope(probe)
        self.assertFalse(receipt["write_isolation_live_proven"])
        self.assertIn("GET_ONLY", receipt["result"])

    def test_exact_primary_worker_must_return_json_success(self):
        with self.assertRaises(ValueError):
            module.validate_scope(lambda a, w: (200, False))

    def test_no_other_or_arbitrary_account_or_worker_query_allowed(self):
        for account, worker in [
            (module.ORIGINAL_ACCOUNT, "unrelated-worker"),
            (module.NEUTRAL_ACCOUNT, module.ALLOW_WORKER),
            (module.NEUTRAL_ACCOUNT, "reference-release-unknown"),
        ]:
            with self.assertRaisesRegex(ValueError, "unapproved_cloudflare_resource"):
                module.read_settings("synthetic-placeholder", account, worker)

    def test_main_wrong_account_never_accesses_cloudflare(self):
        with patch.dict(os.environ, {
            "CLOUDFLARE_ACCOUNT_ID": module.NEUTRAL_ACCOUNT,
            "CLOUDFLARE_API_TOKEN": "synthetic-test-token-not-a-real-credential",
        }):
            with patch.object(module, "read_settings",
                              side_effect=AssertionError("network_called")):
                with self.assertRaisesRegex(SystemExit,
                                             "TOKEN_OR_ACCOUNT_NOT_ADMITTED"):
                    module.main()

if __name__ == "__main__":
    unittest.main()
