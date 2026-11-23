"""Pure offline validation for fixed factory staged-version GET-only evidence."""
import json
import unittest
from unittest.mock import patch
from scripts.cc_factory_stage_version_readonly import (
    ACCOUNT, SCRIPT, ACTIVE_DEPLOYMENT, ACTIVE_VERSION, ALLOWED,
    get_only, latest_version, active_deployment, safe_receipt,
)

NEW = "0a0b0c0d-1111-4222-8333-444455556666"
SHA = "a"*40


class FactoryOfftrafficVersionSafety(unittest.TestCase):
    def test_fixed_endpoints_do_not_allow_network_to_other_worker(self):
        self.assertEqual(len(ALLOWED), 2)
        self.assertTrue(all(f"/accounts/{ACCOUNT}/workers/scripts/{SCRIPT}/" in x for x in ALLOWED))
        with self.assertRaises(ValueError):
            get_only("x"*32, f"/accounts/{ACCOUNT}/workers/scripts/fleet-authority/versions")

    def test_newest_version_no_emails_or_secrets(self):
        node = {"result": [{"id": NEW, "metadata": {
            "created_on": "2026-11-23T09:00:00Z", "source": "wrangler",
            "author_email": "private@example.com", "token": "never output"}}]}
        got = latest_version(node)
        self.assertEqual(got["version_id"], NEW)
        self.assertNotIn("author_email", json.dumps(got))
        self.assertNotIn("token", json.dumps(got))

    def test_active_full_traffic_pin(self):
        node = {"result": [{"id": ACTIVE_DEPLOYMENT,
            "versions": [{"version_id": ACTIVE_VERSION, "percentage": 100}]}]}
        self.assertEqual(active_deployment(node)["full_traffic_version_id"], ACTIVE_VERSION)

    def test_stage_classification_requires_baseline_and_new_version(self):
        version = {"version_id": NEW, "created_on": "2026-11-23T09:00:00Z", "source": "wrangler"}
        deployment = {"deployment_id": ACTIVE_DEPLOYMENT,
                      "full_traffic_version_id": ACTIVE_VERSION}
        result = safe_receipt("45144770284", SHA, 200, version, 200, deployment)
        self.assertEqual(result["classification"],
                         "STAGED_OFFTRAFFIC_VERSION_INDEPENDENTLY_OBSERVED")
        self.assertTrue(result["active_baseline_unchanged"])
        self.assertTrue(result["newest_version_offtraffic_observed"])
        self.assertFalse(result["source_matches_reviewed_git_commit_attested"])
        self.assertEqual(result["cloudflare_mutations"], 0)
        invalid = dict(version, version_id=ACTIVE_VERSION)
        denied = safe_receipt("45144770284", SHA, 200, invalid, 200, deployment)
        self.assertFalse(denied["newest_version_offtraffic_observed"])
        changed = dict(deployment, deployment_id=NEW)
        denied = safe_receipt("45144770284", SHA, 200, version, 200, changed)
        self.assertFalse(denied["active_baseline_unchanged"])

    def test_failed_api_and_malformed_provenance_fail_closed(self):
        deployment = {"deployment_id": ACTIVE_DEPLOYMENT,
                      "full_traffic_version_id": ACTIVE_VERSION}
        result = safe_receipt("45144770284", SHA, 403, {}, 200, deployment)
        self.assertEqual(result["classification"], "OFFTRAFFIC_VERSION_UNVERIFIED_NO_RELEASE")
        with self.assertRaises(ValueError):
            safe_receipt("bogus", SHA, 200, {}, 200, deployment)


if __name__ == "__main__":
    unittest.main()
