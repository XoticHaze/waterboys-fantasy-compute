"""Independent fake-data oracle checks; never call a model or execute model code."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from nvidia_evidence_status_artifact_live_loop import (
    reference,CASES,SEED,HOLDOUT,score,feedback,classify,validate_reply,SCHEMA,MODEL)

# This is TEST AUTHOR source, not model-generated. Its purpose is checking the
# fixed evidence oracle/AST scorer before any paid provider request.
AUTHOR_REFERENCE='''def evidence_state(receipt, verified, queue, age_s, ttl_s, protected):
    if not (0 <= receipt <= 2 and 0 <= verified <= 1 and 0 <= queue <= 4 and age_s >= 0 and ttl_s > 0 and 0 <= protected <= 1):
        return -1
    if receipt == 0 and verified == 1:
        return -1
    if receipt != 0 and verified == 0:
        return 6
    if age_s > ttl_s:
        return 2
    if verified == 1:
        if receipt == 1:
            return 3
        if receipt == 2:
            return 4
    if protected and queue:
        return 5
    if 1 <= queue <= 2:
        return 1
    if 3 <= queue <= 4:
        return 7
    return 0
'''

class EvidenceStatusTests(unittest.TestCase):
    def test_100_fixed_cases_and_distinct_holdouts(self):
        self.assertEqual(len(CASES),100)
        self.assertEqual(len(SEED),26)
        self.assertEqual(len(HOLDOUT),74)
        self.assertEqual(len(set(CASES)),len(CASES))
    def test_signed_terminal_wins_over_queue_conflict(self):
        self.assertEqual(reference((1,1,3,10,120,1)),3)
        self.assertEqual(reference((2,1,1,10,120,1)),4)
    def test_age_downgrade_even_verified_final(self):
        self.assertEqual(reference((1,1,2,121,120,0)),2)
        self.assertEqual(reference((0,0,2,121,120,1)),2)
    def test_untrusted_receipt_not_completed(self):
        self.assertEqual(reference((1,0,1,10,120,0)),6)
    def test_protected_request_cannot_get_automatic_route(self):
        self.assertEqual(reference((0,0,2,10,120,1)),5)
    def test_unsupported_or_missing_fields_fail_closed(self):
        for v in [(9,0,1,0,30,0),(0,1,0,0,30,0),(0,0,1,-1,30,0),(0,0,1,0,0,0)]:
            self.assertEqual(reference(v),-1)
    def test_author_oracle_is_ast_accepted_and_correct(self):
        self.assertEqual(score(AUTHOR_REFERENCE)['passed'],100)
    def test_disallowed_model_code_not_imported(self):
        bad='def evidence_state(receipt, verified, queue, age_s, ttl_s, protected):\n    import os\n    return 3\n'
        self.assertFalse(score(bad)['source_ast_admitted'])
    def test_feedback_has_independently_recomputed_values(self):
        broken='def evidence_state(receipt, verified, queue, age_s, ttl_s, protected):\n    return 0\n'
        report=score(broken)
        self.assertTrue(report['source_ast_admitted'])
        rows=feedback(report)
        self.assertEqual(len(rows),3)
        self.assertTrue(all(x['expected']==reference(tuple(x['input'])) for x in rows))
    def test_broken_source_scores_lower_and_revision_reports_gain(self):
        broken='def evidence_state(receipt, verified, queue, age_s, ttl_s, protected):\n    return 0\n'
        r=classify(broken,AUTHOR_REFERENCE)
        self.assertLess(r['baseline']['passed'],100)
        self.assertEqual(r['outcome'],'CORRECTED_ALL_HOLDOUTS')
        self.assertEqual(r['regressions_count'],0)
    def test_first_draft_full_score_is_not_false_feedback(self):
        r=classify(AUTHOR_REFERENCE,None)
        self.assertEqual(r['outcome'],'FIRST_DRAFT_PASSED_NO_CORRECTION')
    def test_receipt_authority_flags_rejected(self):
        d={'schema':SCHEMA,'stage':0,'model':MODEL,'provider_calls':1,
           'private_input_used':False,'model_code_executed':False,
           'commands_executed':False,'production_admitted':False,
           'status':'candidate_unexecuted','http_status':200,'source':AUTHOR_REFERENCE}
        self.assertEqual(validate_reply(d,0),AUTHOR_REFERENCE)
        d['production_admitted']=True
        with self.assertRaises(ValueError):validate_reply(d,0)

if __name__=='__main__':unittest.main()
