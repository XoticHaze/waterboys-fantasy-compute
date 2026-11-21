"""The legacy v1 feedback branch must never reveal final-evaluation cases."""
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from nvidia_evidence_status_artifact_live_loop import feedback,SEED,CASES,reference

class LegacyFeedbackHoldoutIsolation(unittest.TestCase):
    def test_only_holdout_failures_mean_no_model_visible_examples(self):
        a=feedback({'source_ast_admitted':True,'passed':90,'total':100,
                    'failed_case_indices':[len(SEED),len(SEED)+1,len(CASES)-1]})
        self.assertEqual(a,[])
    def test_mixed_failures_use_only_diagnostic_indices(self):
        a=feedback({'source_ast_admitted':True,'passed':95,'total':100,
                    'failed_case_indices':[0,17,len(SEED),len(CASES)-1]})
        self.assertEqual([x["input"] for x in a],[list(SEED[0]),list(SEED[17])])
        self.assertTrue(all(x["expected"]==reference(tuple(x["input"])) for x in a))
    def test_rejected_structure_returns_no_examples(self):
        a=feedback({'source_ast_admitted':False,'passed':0,'total':100,
                    'failed_case_indices':list(range(len(CASES)))})
        self.assertEqual(a,[])
    def test_all_passed_returns_no_examples(self):
        a=feedback({'source_ast_admitted':True,'passed':100,'total':100,
                    'failed_case_indices':[]})
        self.assertEqual(a,[])

if __name__=="__main__":unittest.main()
