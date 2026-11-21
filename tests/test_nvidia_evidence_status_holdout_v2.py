"""Independent checks for diverse, frozen secondary hidden cases."""
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'tests')]
from nvidia_evidence_status_holdout_v2 import (
    PROFILE,HOLDOUT_V2,FIXTURE_SHA256,score_holdout_v2,compare_holdout_v2,SEED
)
from test_nvidia_evidence_status_artifact import AUTHOR_REFERENCE

BROKEN="def evidence_state(receipt, verified, queue, age_s, ttl_s, protected):\n    return 0\n"

class SecondaryHoldoutTests(unittest.TestCase):
    def test_diverse_and_isolated(self):
        self.assertEqual(len(HOLDOUT_V2),74)
        self.assertEqual(len(set(HOLDOUT_V2)),74)
        self.assertFalse(set(HOLDOUT_V2)&set(SEED))
        self.assertEqual({v[2] for v in HOLDOUT_V2},set(range(5)))
        self.assertEqual({v[0] for v in HOLDOUT_V2},{0,1,2})
        self.assertEqual({v[-1] for v in HOLDOUT_V2},{0,1})
        self.assertEqual(len(FIXTURE_SHA256),64)
    def test_reference_passes_unseen_cases_independently(self):
        result=score_holdout_v2(AUTHOR_REFERENCE)
        self.assertEqual(result['profile'],PROFILE)
        self.assertEqual(result['passed'],74)
        self.assertEqual(result['failed_case_indices'],[])
    def test_bad_first_draft_is_not_accepted(self):
        result=score_holdout_v2(BROKEN)
        self.assertTrue(result['ast_admitted'])
        self.assertLess(result['passed'],74)
    def test_improved_source_has_no_holdout_regression(self):
        result=compare_holdout_v2(BROKEN,AUTHOR_REFERENCE)
        self.assertEqual(result['outcome'],'HOLDOUT_V2_IMPROVED_NO_REGRESSION')
        self.assertGreater(result['newly_correct_count'],0)
        self.assertEqual(result['regressed_count'],0)
        self.assertFalse(result['provider_called'])
        self.assertFalse(result['model_code_executed'])
    def test_identical_source_not_self_correction(self):
        result=compare_holdout_v2(BROKEN,BROKEN)
        self.assertEqual(result['outcome'],'IDENTICAL_SOURCE_NOT_SELF_CORRECTION')
        self.assertTrue(result['same_source'])
    def test_regression_is_not_improvement(self):
        result=compare_holdout_v2(AUTHOR_REFERENCE,BROKEN)
        self.assertEqual(result['outcome'],'REGRESSED_REJECTED')
        self.assertGreater(result['regressed_count'],0)

if __name__=='__main__':unittest.main()
