import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from nvidia_quote_artifact_live_loop import (
 ARGS,CASES,TRAIN,HOLD,reference,score,failures_for_revision,
 score_pair,outcome,validate_step
)
GOOD="""def quote_price_cents(minutes, hourly_cents, travel_cents, supplies_cents, overhead_bps, margin_bps):
    if min(minutes, hourly_cents, travel_cents) < 0 or min(supplies_cents, overhead_bps, margin_bps) < 0 or overhead_bps > 10000 or margin_bps >= 10000:
        return None
    base = (minutes * hourly_cents + 59) // 60 + travel_cents + supplies_cents
    cost = base + (base * overhead_bps + 9999) // 10000
    if cost == 0:
        return None
    return (cost * 10000 + 9999 - margin_bps) // (10000 - margin_bps)
"""
BROKEN="""def quote_price_cents(minutes, hourly_cents, travel_cents, supplies_cents, overhead_bps, margin_bps):
    base = minutes * hourly_cents // 60 + travel_cents + supplies_cents
    cost = base + base * overhead_bps // 10000
    return cost * (10000 + margin_bps) // 10000
"""
class QuoteArtifactTests(unittest.TestCase):
 def test_oracle_business_math(self):
  self.assertEqual(reference((90,3500,500,250,1000,2500)),8800)
  self.assertEqual(reference((1,100,0,0,0,0)),2)
  self.assertEqual(reference((0,0,0,0,0,0)),None)
  self.assertEqual(reference((5,1000,0,0,0,10000)),None)
  self.assertEqual(reference((0,0,250,0,0,0)),250)
 def test_known_good_ast_acceptance(self):
  x=score(GOOD)
  self.assertTrue(x["source_ast_admitted"])
  self.assertEqual(x["passed"],len(CASES))
  self.assertEqual(len(TRAIN),16)
  self.assertEqual(len(CASES),60)
 def test_known_broken_rejected_by_oracle(self):
  x=score(BROKEN)
  self.assertLess(x["passed"],x["total"])
  self.assertTrue(x["source_ast_admitted"])
  self.assertLessEqual(len(failures_for_revision(x)),3)
  for e in failures_for_revision(x):
   self.assertEqual(e["expected"],reference(tuple(e["input"])))
 def test_unsafe_source_never_runs(self):
  x=score("import os\n"+GOOD)
  self.assertFalse(x["source_ast_admitted"])
  self.assertEqual(x["passed"],0)
 def test_improvement_gate_rejects_zero_gain(self):
  a,b,keep=score_pair(BROKEN,BROKEN)
  self.assertEqual(outcome(a,b,keep),"NO_GAIN_REJECTED")
 def test_good_revision_accepted(self):
  a,b,keep=score_pair(BROKEN,GOOD)
  self.assertTrue(keep)
  self.assertEqual(outcome(a,b,keep),"ACCEPTED_REVIEW_READY")
 def test_pre_model_errors_are_categorized_without_raw_data(self):
  with self.assertRaisesRegex(RuntimeError,"QUOTE_CALLER_UPSTREAM_QUOTE_STEP_SELECTOR_REJECTED"):
   validate_step({"error":"upstream_quote_step_selector_rejected"},0)
  with self.assertRaisesRegex(RuntimeError,"QUOTE_CALLER_UNCLASSIFIED"):
   validate_step({"error":"Bearer SECRET"},0)
 def test_origin_task_stays_public_synthetic(self):
  self.assertEqual(ARGS,("minutes","hourly_cents","travel_cents","supplies_cents","overhead_bps","margin_bps"))
if __name__=="__main__":unittest.main()
