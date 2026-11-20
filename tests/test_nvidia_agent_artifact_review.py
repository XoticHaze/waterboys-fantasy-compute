"""Review the exact model-produced artifact, never execute it as Python."""
import hashlib
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = ROOT / "experiments" / "nvidia-agent-artifact-v1"
SPEC = importlib.util.spec_from_file_location("artifact_verifier", ARTIFACT_DIR / "verify_artifact.py")
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)


class RealGeneratedArtifactChecks(unittest.TestCase):
    def test_exact_source_identity_matches_provider_log_readback(self):
        raw = (ARTIFACT_DIR / "model_generated_functions.py").read_bytes()
        self.assertEqual(len(raw), 1355)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), verifier.SOURCE_SHA256)
        self.assertEqual(verifier.RUN_ID, 44499189813)
        self.assertEqual(verifier.JOB_ID, 135474137996)

    def test_five_generated_functions_score_150_independent_ast_cases(self):
        receipt = verifier.verify()
        self.assertEqual(receipt["status"], "static_accepted")
        self.assertEqual(receipt["checks_passed"], 150)
        self.assertEqual(receipt["checks_total"], 150)
        self.assertEqual(len(receipt["functions"]), 5)
        self.assertTrue(all(x["pass"] and x["checks_passed"] == 30 for x in receipt["functions"]))

    def test_no_arbitrary_code_execution_or_protected_authority_claim(self):
        receipt = verifier.verify()
        for field in ("source_code_executed", "source_imported", "production_admitted", "commands_executed"):
            self.assertIs(receipt[field], False, field)
        self.assertIs(receipt["independent_git_log_identity_authenticated_by_this_script"], False)

    def test_any_change_to_generated_source_fails_closed(self):
        raw = (ARTIFACT_DIR / "model_generated_functions.py").read_bytes()
        with self.assertRaisesRegex(ValueError, "ARTIFACT_SOURCE_HASH_MISMATCH"):
            verifier.verify(raw + b"\n")
        with self.assertRaisesRegex(ValueError, "ARTIFACT_SOURCE_HASH_MISMATCH"):
            verifier.verify(raw.replace(b"return 2", b"return 3"))

    def test_invalid_inputs_are_not_accepted(self):
        with self.assertRaisesRegex(ValueError, "ARTIFACT_SOURCE_HASH_MISMATCH"):
            verifier.verify(None if False else b"")
        with self.assertRaisesRegex(ValueError, "ARTIFACT_SOURCE_HASH_MISMATCH"):
            verifier.verify("not bytes")


if __name__ == "__main__":
    unittest.main()
