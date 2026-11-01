"""Offline tests: strict public-safe four-prose-case rubric reader."""
import contextlib
import io
import unittest
from unittest.mock import patch
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import nvidia_fixed_draft_value_pilot as pilot
def receipt(code=200):
  results=[]
  for i,case in enumerate(pilot.EXPECTED):
    results.append({"id":case,"kind":"operator" if i<2 else "customer",
       "http_status":code,"latency_ms":1000,"format_valid":True,
       "anchor_groups":4,"anchor_groups_met":4,
       "unsupported_claim_flag":False,"human_review_flag":True,
       "draft_length_ok":True,"draft_passed":True,
       "template_passed":True})
  return {"schema":"commandcenter.nvidia_fixed_draft_pilot.v1",
     "model":pilot.MODEL,"status":"completed_not_human_reviewed",
     "attempted":4,"results":results}
class FixedDraftPilotTests(unittest.TestCase):
 def test_four_fixed_synthetic_fictional_cases_only(self):
    r=pilot.validate(receipt())
    self.assertEqual(len(r),4)
    self.assertEqual([x["id"] for x in r],list(pilot.EXPECTED))
    self.assertEqual(sum(x["draft_passed"] for x in r),4)
 def test_malformed_case_id_and_private_prose_are_not_surfaced(self):
    doc=receipt();doc["results"][0]["id"]="UNKNOWN"
    with self.assertRaisesRegex(RuntimeError,"CASE_ORDER_INVALID"):pilot.validate(doc)
    doc=receipt();doc["results"][0]["raw_model_reply"]="PRIVATE_STRING_SHOULD_NOT_LEAK"
    text=str(pilot.validate(doc))
    self.assertNotIn("PRIVATE_STRING_SHOULD_NOT_LEAK",text)
 def test_429_holds_without_claiming_full_case_success(self):
    doc=receipt(429)
    doc["results"]=doc["results"][:1];doc["attempted"]=1;doc["status"]="rate_limited"
    with contextlib.redirect_stdout(io.StringIO()) as out:
       with self.assertRaisesRegex(RuntimeError,"NO_RETRY"):
          pilot.validate(doc)
    self.assertIn("rate_limited",out.getvalue())
 def test_incomplete_and_untrusted_schema_rejected(self):
    doc=receipt();doc["results"]=doc["results"][:3];doc["attempted"]=3
    with self.assertRaisesRegex(RuntimeError,"DRAFT_FIXED_COVERAGE_INCOMPLETE"):
       pilot.validate(doc)
    doc=receipt();doc["schema"]="attack"
    with self.assertRaisesRegex(RuntimeError,"IDENTITY_INVALID"):
       pilot.validate(doc)
if __name__=="__main__":unittest.main()
