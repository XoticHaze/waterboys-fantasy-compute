"""V2 release acceptance tests use invented UUIDs and no network."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from nvidia_evidence_release_identity import (
    REPO, SCHEMA, SOURCE, WORKER, verify_release_identity
)

RUN = "12345678901"
SHA = "a" * 40
DEPLOY = "10000000-0000-4000-8000-000000000001"
VERSION = "10000000-0000-4000-8000-000000000002"
OTHER = "10000000-0000-4000-8000-000000000003"
TIME = "2026-11-24T00:00:00Z"


def fixtures():
    proof = {"schema": SCHEMA, "repository": REPO, "run_id": RUN,
             "controller_sha": SHA, "reviewed_source_sha": SOURCE,
             "worker_name": WORKER, "deployment_id": DEPLOY, "version_id": VERSION,
             "deployment_created_on": TIME, "diagnostic_disabled": True,
             "secret_reference_preserved": True, "full_model_text_exported": False,
             "private_input_used": False, "production_admitted": False}
    active = {"id": DEPLOY, "created_on": TIME,
              "versions": [{"version_id": VERSION, "percentage": 100}]}
    return proof, active


class ExactReleaseTests(unittest.TestCase):
    def check(self, p, a):
        return verify_release_identity(p, a, run_id=RUN, controller_sha=SHA)

    def test_exact_release(self):
        p, a = fixtures()
        self.assertEqual(self.check(p, a), {"deployment_id": DEPLOY, "version_id": VERSION})

    def test_unrelated_version_same_timestamp_fails(self):
        p, a = fixtures()
        a["versions"][0]["version_id"] = OTHER
        with self.assertRaisesRegex(ValueError, "ACTIVE_VERSION_NOT_EXACT"):
            self.check(p, a)

    def test_unrelated_deployment_same_version_fails(self):
        p, a = fixtures()
        a["id"] = OTHER
        with self.assertRaisesRegex(ValueError, "ACTIVE_VERSION_NOT_EXACT"):
            self.check(p, a)

    def test_partial_traffic_fails(self):
        p, a = fixtures()
        a["versions"][0]["percentage"] = 50
        with self.assertRaisesRegex(ValueError, "ACTIVE_VERSION_NOT_SINGLE"):
            self.check(p, a)

    def test_receipt_identity_and_safety_flags(self):
        p, a = fixtures()
        for field, invalid in (("run_id", "22222222222"), ("controller_sha", "b"*40),
                               ("reviewed_source_sha", "b"*40), ("worker_name", "other"),
                               ("diagnostic_disabled", False), ("production_admitted", True),
                               ("private_input_used", True), ("secret_reference_preserved", False)):
            with self.subTest(field=field):
                bad = copy.deepcopy(p)
                bad[field] = invalid
                with self.assertRaisesRegex(ValueError, "RELEASE_PROOF_IDENTITY"):
                    self.check(bad, a)

    def test_creation_identity_must_match(self):
        p, a = fixtures()
        a["created_on"] = "2026-11-24T00:00:01Z"
        with self.assertRaisesRegex(ValueError, "CREATED_ON_MISMATCH"):
            self.check(p, a)


if __name__ == "__main__":
    unittest.main()
