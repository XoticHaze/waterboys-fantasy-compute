"""Offline fail-closed tests; all Cloudflare data is synthetic."""
import importlib.util
import pathlib
import unittest

FILE = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "shared_nvidia_cf_preflight.py"
spec = importlib.util.spec_from_file_location("preflight", FILE)
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
ACCOUNT = "a" * 32
STORE = "b" * 32


def happy(path, _token):
    if path.endswith("/waterboys-fantasy-broker/settings"):
        return 200, {"success": True}
    if path.endswith("/cc-shared-nvidia-inference/settings"):
        return 404, {"success": False}
    if path.endswith("/secrets_store/stores?per_page=100"):
        return 200, {"success": True, "result": [{"id": STORE}]}
    if path.endswith("/secrets_store/stores/" + STORE + "/secrets?per_page=100"):
        return 200, {"success": True, "result": [{
            "name": "NVIDIA_API_KEY", "status": "active",
            "scopes": ["workers"], "value": "SECRET_MUST_NEVER_APPEAR",
        }]}
    raise AssertionError("unexpected cloud path")


class TestCloudflareNvidiaPreflight(unittest.TestCase):
    def go(self, probe=happy):
        return p.check(ACCOUNT, "FAKE_BEARER_VALUE", probe)

    def test_expected_account_verified_with_secret_but_worker_absent(self):
        record = self.go()
        self.assertEqual(record["classification"], "compute_secret_proven_worker_creation_or_access_pending")
        self.assertTrue(record["workers_scope"])
        self.assertFalse(record["binding_verified"])

    def test_no_sensitive_metadata_exported(self):
        serialized = str(self.go())
        for sensitive in (ACCOUNT, STORE, "FAKE_BEARER_VALUE", "SECRET_MUST_NEVER_APPEAR"):
            self.assertNotIn(sensitive, serialized)

    def test_only_four_fixed_cloud_gets(self):
        paths = []
        def run(path, token):
            paths.append(path)
            return happy(path, token)
        self.go(run)
        self.assertEqual(len(paths), 4)
        self.assertTrue(all(path.startswith("/accounts/" + ACCOUNT + "/") for path in paths))

    def test_no_credential_means_no_probe(self):
        r = p.check("wrong", "token", lambda *_: self.fail("network attempt"))
        self.assertEqual(r["classification"], "approved_cloudflare_identity_missing")

    def test_wrong_account_denied_without_store_query(self):
        r = self.go(lambda path, token: (403, {}) if path.endswith("/waterboys-fantasy-broker/settings") else happy(path, token))
        self.assertEqual(r["classification"], "ordinary_account_identity_not_proven")
        self.assertIsNone(r["stores_http"])

    def test_no_secrets_permission_not_confused_with_secret_absence(self):
        r = self.go(lambda path, token: (403, {}) if path.endswith("/secrets_store/stores?per_page=100") else happy(path, token))
        self.assertEqual(r["classification"], "secrets_store_read_authority_unavailable")
        self.assertIsNone(r["secret_seen"])

    def test_wrong_scope_fails_closed(self):
        def test_probe(path, token):
            status, doc = happy(path, token)
            if path.endswith("/secrets?per_page=100"):
                doc["result"][0]["scopes"] = ["ai_gateway"]
            return status, doc
        self.assertEqual(self.go(test_probe)["classification"], "secret_scope_or_status_mismatch")

    def test_multiple_stores_fail_closed(self):
        def test_probe(path, token):
            if path.endswith("/secrets_store/stores?per_page=100"):
                return 200, {"success": True, "result": [{"id": STORE}, {"id": "c" * 32}]}
            return happy(path, token)
        self.assertEqual(self.go(test_probe)["classification"], "single_compute_store_unverified")

    def test_worker_present_not_binding_proof(self):
        def test_probe(path, token):
            if path.endswith("/cc-shared-nvidia-inference/settings"):
                return 200, {"success": True, "bindings": [{"name": "OTHER"}]}
            return happy(path, token)
        r = self.go(test_probe)
        self.assertEqual(r["classification"], "worker_present_binding_requires_separate_proof")
        self.assertFalse(r["binding_verified"])


if __name__ == "__main__":
    unittest.main()
