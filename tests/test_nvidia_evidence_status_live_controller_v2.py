"""Controller tests use test-author code and an in-process fake transport."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tests")]
from test_nvidia_evidence_status_artifact import AUTHOR_REFERENCE
from nvidia_evidence_status_artifact_live_loop_v2 import run_pair, persist, evaluate_pair

BROKEN = "def evidence_state(receipt, verified, queue, age_s, ttl_s, protected):\n    return 0\n"
INVALID = "def evidence_state(receipt, verified, queue, age_s, ttl_s, protected):\n    import os\n    return 0\n"
# All diagnostics have age <= 121. Deliberately fail a hidden aged case.
HIDDEN_ONLY = AUTHOR_REFERENCE.replace("    if age_s > ttl_s:", "    if age_s == 185:\n        return 0\n    if age_s > ttl_s:")


class V2ControllerTests(unittest.TestCase):
    def pair(self, first, second=None, error=False):
        calls = []
        def fake(payload, *, feedback_v2=False):
            calls.append((payload, feedback_v2))
            if payload["stage"] == 0:
                return first
            if error:
                raise RuntimeError("test transport failure")
            return second
        a, b, result = run_pair(fake)
        return calls, a, b, result

    def test_real_independent_gain_required(self):
        calls, _, _, r = self.pair(BROKEN, AUTHOR_REFERENCE)
        self.assertEqual(len(calls), 2)
        self.assertTrue(calls[1][1])
        self.assertTrue(r["correction_qualified"])
        self.assertGreater(r["balanced_v2"]["newly_correct_count"], 0)
        self.assertEqual(r["legacy_v1"]["regressions_count"], 0)
        self.assertEqual(r["provider_call_count_exact"], 2)
        self.assertFalse(r["production_admitted"])

    def test_identical_output_is_not_learning(self):
        _, _, _, r = self.pair(BROKEN, BROKEN)
        self.assertFalse(r["correction_qualified"])
        self.assertEqual(r["outcome"], "IDENTICAL_SOURCE_NOT_SELF_CORRECTION")

    def test_full_baseline_does_not_consume_revision(self):
        calls, _, _, r = self.pair(AUTHOR_REFERENCE)
        self.assertEqual(len(calls), 1)
        self.assertEqual(r["outcome"], "FIRST_DRAFT_PASSED_NO_CORRECTION")

    def test_hidden_only_failure_is_not_sent_to_provider(self):
        calls, _, _, r = self.pair(HIDDEN_ONLY)
        self.assertEqual(len(calls), 1)
        self.assertEqual(r["stop_reason"], "HOLDOUT_ONLY_FAILURE_NO_DIAGNOSTIC_FEEDBACK")
        self.assertFalse(r["correction_qualified"])

    def test_invalid_structure_is_not_a_behavior_failure(self):
        calls, _, _, r = self.pair(INVALID)
        self.assertEqual(len(calls), 1)
        self.assertEqual(r["outcome"], "BASELINE_STRUCTURE_REJECTED")

    def test_failed_revision_keeps_artifact_and_uncertain_cost(self):
        calls, a, b, r = self.pair(BROKEN, error=True)
        self.assertEqual(len(calls), 2)
        self.assertIsNone(r["provider_call_count_exact"])
        self.assertEqual(r["request_attempt_upper_bound"], 2)
        self.assertEqual(r["confirmed_provider_candidate_replies"], 1)
        self.assertEqual(r["stop_reason"], "REVISION_REPLY_UNAVAILABLE")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "receipt"
            persist(a, b, r, root)
            self.assertEqual((root / "baseline_model.py").read_text(), BROKEN)
            self.assertFalse((root / "revised_model.py").exists())
            self.assertEqual(json.loads((root / "evaluation.json").read_text()), r)
            with self.assertRaises(FileExistsError):
                persist(a, b, r, root)

    def test_regression_is_rejected(self):
        r = evaluate_pair(AUTHOR_REFERENCE, BROKEN)
        self.assertEqual(r["outcome"], "REGRESSED_REJECTED")
        self.assertFalse(r["correction_qualified"])

    def test_failed_baseline_records_uncertain_cost(self):
        def fail(*args, **kwargs):
            raise RuntimeError("test transport failure")
        a, b, r = run_pair(fail)
        self.assertIsNone(a)
        self.assertIsNone(b)
        self.assertEqual(r["request_attempt_upper_bound"], 1)
        self.assertIsNone(r["provider_call_count_exact"])
        self.assertEqual(r["outcome"], "BASELINE_REPLY_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
