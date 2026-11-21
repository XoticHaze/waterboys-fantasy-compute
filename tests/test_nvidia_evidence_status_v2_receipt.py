"""NVIDIA v2 receipt checks are separate from the v1 pinned experiment."""
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from nvidia_evidence_status_artifact_live_loop import validate_reply,SCHEMA,SCHEMA_V2,MODEL,ARGS

SOURCE='def evidence_state('+', '.join(ARGS)+'):\n    return 0\n'
def receipt(schema=SCHEMA_V2,stage=1):
    return {'schema':schema,'stage':stage,'model':MODEL,'provider_calls':1,
     'private_input_used':False,'model_code_executed':False,'commands_executed':False,
     'production_admitted':False,'status':'candidate_unexecuted','http_status':200,
     'source':SOURCE,'source_hash_verified':True}

class FixedV2ReceiptTests(unittest.TestCase):
    def test_v2_accepts_attested_source_hash_receipt(self):
        self.assertEqual(validate_reply(receipt(),1,feedback_v2=True),SOURCE)
    def test_v2_does_not_accept_v1_receipt(self):
        with self.assertRaises(ValueError):
            validate_reply(receipt(SCHEMA),1,feedback_v2=True)
    def test_v1_does_not_accept_v2_receipt(self):
        with self.assertRaises(ValueError):
            validate_reply(receipt(),1,feedback_v2=False)
    def test_v2_rejects_missing_hash_or_wrong_stage(self):
        a=receipt();a.pop('source_hash_verified')
        with self.assertRaises(ValueError):validate_reply(a,1,feedback_v2=True)
        with self.assertRaises(ValueError):validate_reply(receipt(stage=0),0,feedback_v2=True)
    def test_no_production_or_execution_claim_allowed(self):
        for key in ('model_code_executed','commands_executed','production_admitted','private_input_used'):
            with self.subTest(key=key):
                a=receipt();a[key]=True
                with self.assertRaises(ValueError):validate_reply(a,1,feedback_v2=True)

if __name__=='__main__':unittest.main()
