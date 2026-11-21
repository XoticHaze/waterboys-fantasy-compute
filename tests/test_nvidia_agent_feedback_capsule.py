"""Independent checks for scoped failure translation, without inference or source execution."""
import hashlib
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
sys.path.insert(0,str(ROOT/"tests"))
from nvidia_agent_feedback_capsule import translate,SCHEMA
from test_nvidia_evidence_status_artifact import AUTHOR_REFERENCE

BROKEN="def evidence_state(receipt, verified, queue, age_s, ttl_s, protected):\n    return 0\n"
INVALID="def evidence_state(receipt, verified, queue, age_s, ttl_s, protected):\n    import os\n    return 0\n"

class CapsuleTests(unittest.TestCase):
    def test_not_a_second_provider_request_or_authority(self):
        p=translate(BROKEN)
        self.assertEqual(p["schema"],SCHEMA)
        self.assertEqual(p["scope"],"READ_ONLY_UI_STATE_CLASSIFICATION")
        self.assertFalse(p["provider_called"])
        self.assertFalse(p["model_code_executed"])
        self.assertFalse(p["protected_execution_authorized"])
        self.assertEqual(p["delivery"],"RESEARCH_EVIDENCE_ONLY_NOT_PROVIDER_INPUT")
    def test_source_and_fixture_pinned(self):
        p=translate(BROKEN)
        self.assertEqual(p["source_sha256"],hashlib.sha256(BROKEN.encode()).hexdigest())
        self.assertEqual(len(p["fixture_sha256"]),64)
        self.assertEqual(p["cases_total"],100)
        self.assertEqual(p["tests_total"],100)
    def test_actual_and_expected_are_not_conflated(self):
        p=translate(BROKEN)
        self.assertTrue(p["ast_admitted"])
        self.assertTrue(p["failing_examples"])
        self.assertEqual(len(p["failing_examples"]),3)
        self.assertTrue(any(r["actual"]==0 and r["expected"]!=0 for r in p["failing_examples"]))
        self.assertTrue(all(isinstance(x["input"],list) and len(x["input"])==6 for x in p["failing_examples"]))
    def test_failure_classes_are_diverse(self):
        p=translate(BROKEN)
        self.assertEqual(len(set(r["category"] for r in p["failing_examples"])),3)
        self.assertIn("PROTECTED_QUEUE_NEVER_AUTHORITY",[r["category"] for r in p["failing_examples"]])
    def test_success_controls_are_preserved(self):
        p=translate(BROKEN)
        self.assertGreaterEqual(len(p["preserve_examples"]),1)
        self.assertTrue(all(r["actual"]==r["expected"] for r in p["preserve_examples"]))
        self.assertLess(p["tests_passed"],100)
        self.assertEqual(p["next_step"],"REVISE_WITH_GROUNDED_COUNTEREXAMPLES")
    def test_perfect_first_attempt_cannot_be_called_learning(self):
        p=translate(AUTHOR_REFERENCE)
        self.assertEqual(p["tests_passed"],100)
        self.assertEqual(p["failing_examples"],[])
        self.assertEqual(p["next_step"],"FIRST_DRAFT_ACCEPTED_NO_CORRECTION")
    def test_invalid_structure_does_not_fabricate_behavior_fails(self):
        p=translate(INVALID)
        self.assertFalse(p["ast_admitted"])
        self.assertIsNone(p["failure_count"])
        self.assertEqual(p["failing_examples"],[])
        self.assertEqual(p["next_step"],"SOURCE_STRUCTURE_REJECTED_DO_NOT_CLAIM_100_BEHAVIORAL_FAILURES")
    def test_cannot_accept_external_scope_or_malformed_attempt(self):
        for i in (0,4,True,"2"):
            with self.subTest(i=i),self.assertRaises(ValueError):
                translate(BROKEN,attempt=i)
    def test_scope_is_immutable_with_attempt_counter(self):
        p=translate(BROKEN,attempt=2)
        self.assertEqual(p["attempt"],2)
        self.assertEqual(p["scope"],"READ_ONLY_UI_STATE_CLASSIFICATION")

if __name__=="__main__":
    unittest.main()
