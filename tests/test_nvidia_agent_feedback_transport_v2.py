"""Sealed diagnosis DTO: holdout isolation, source binding, bounded retry memory."""
import hashlib
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
sys.path.insert(0,str(ROOT/"tests"))
from nvidia_agent_feedback_capsule import provider_feedback_v2,translate,SEED,SCHEMA
from test_nvidia_evidence_status_artifact import AUTHOR_REFERENCE

BROKEN="def evidence_state(receipt, verified, queue, age_s, ttl_s, protected):\n    return 0\n"
INVALID="def evidence_state(receipt, verified, queue, age_s, ttl_s, protected):\n    import os\n    return 0\n"

class FeedbackTransportTests(unittest.TestCase):
    def test_no_holdout_case_exposure_even_after_full_score(self):
        c=translate(BROKEN)
        self.assertEqual(c["cases_total"],100)
        self.assertEqual(c["diagnostic_cases_total"],len(SEED))
        self.assertEqual(c["held_out_cases_total"],74)
        self.assertFalse(c["holdout_case_details_disclosed"])
        for row in c["failing_examples"]+c["preserve_examples"]:
            self.assertLess(row["case_index"],len(SEED))
    def test_verifier_observations_and_known_good_controls(self):
        dto=provider_feedback_v2(BROKEN)
        self.assertEqual(dto["stage"],1)
        f=dto["feedback"]
        self.assertEqual(f["schema"],SCHEMA)
        self.assertEqual(f["scope"],"READ_ONLY_UI_STATE_CLASSIFICATION")
        self.assertEqual(f["source_sha256"],hashlib.sha256(BROKEN.encode()).hexdigest())
        self.assertTrue(f["failing_examples"])
        for row in f["failing_examples"]:
            self.assertIn(tuple(row["input"]),SEED)
            self.assertNotEqual(row["actual"],row["expected"])
            self.assertIn("category",row)
        for row in f["preserve_examples"]:
            self.assertIn(tuple(row["input"]),SEED)
            self.assertEqual(row["actual"],row["expected"])
        self.assertLessEqual(len(f["failing_examples"]),3)
        self.assertLessEqual(len(f["preserve_examples"]),3)
    def test_strategy_memory_bounded_no_free_form(self):
        f=provider_feedback_v2(BROKEN,attempt=2,rejected_strategy_ids=("queue_first",))["feedback"]
        self.assertEqual(f["attempt"],2)
        self.assertEqual(f["rejected_strategy_ids"],["queue_first"])
        for invalid in (("execute shell",),("queue_first","queue_first"),("queue_first","receipt_first")):
            with self.subTest(invalid=invalid),self.assertRaises(ValueError):
                provider_feedback_v2(BROKEN,attempt=2,rejected_strategy_ids=invalid)
    def test_no_repair_fabricated_for_perfect_or_invalid_source(self):
        for src in (INVALID,AUTHOR_REFERENCE):
            with self.subTest(src=src[:30]),self.assertRaises(ValueError):
                provider_feedback_v2(src)
    def test_attempts_cannot_be_spoofed(self):
        for i in (0,4,True,"1"):
            with self.subTest(i=i),self.assertRaises(ValueError):
                provider_feedback_v2(BROKEN,attempt=i)
    def test_no_secret_or_unbounded_authority_fields(self):
        f=provider_feedback_v2(BROKEN)["feedback"]
        self.assertEqual(set(f),{"schema","scope","attempt","source_sha256","failing_examples",
                                 "preserve_examples","rejected_strategy_ids"})
        self.assertEqual(f["rejected_strategy_ids"],[])

if __name__=="__main__":unittest.main()
