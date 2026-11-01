"""Offline-only proof for exact MiniMax case checkpoint resume; no provider calls."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import nvidia_micro_worker_fallback_resume_2 as resume
from test_nvidia_micro_worker_campaign import receipt
from nvidia_micro_worker_campaign import Retryable

class MiniMaxCheckpointTests(unittest.TestCase):
 def test_exact_committed_synthetic_checkpoint_is_admitted(self):
  rows=resume.read_checkpoint()
  self.assertEqual([v["case"] for v in rows],resume.EXPECTED_CASES)
  self.assertEqual(sum(v["passed"] for v in rows),7)

 def test_checkpoint_identity_or_private_data_or_invalid_rows_are_rejected(self):
  current=json.loads(resume.CHECKPOINT.read_text())
  for field,value in (("raw_model_output_included",True),("private_data_included",True),
                       ("credentials_included",True),("next_eligible_batch_index",1)):
   altered=json.loads(json.dumps(current));altered[field]=value
   with tempfile.TemporaryDirectory() as d:
    p=Path(d)/"checkpoint.json";p.write_text(json.dumps(altered))
    with self.assertRaisesRegex(RuntimeError,"UNTRUSTED_FIXED_MINIMAX_CHECKPOINT"):
     resume.read_checkpoint(p)
  altered=json.loads(json.dumps(current));altered["completed_cases"]=[{"case":"R03","passed":True}]
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"checkpoint.json";p.write_text(json.dumps(altered))
   with self.assertRaisesRegex(RuntimeError,"UNTRUSTED_FIXED_MINIMAX_CHECKPOINT"):
    resume.read_checkpoint(p)

 def test_only_mini_max_unattempted_batches_2_3_4_5_are_called(self):
  mock_receipts=[receipt(1,batch) for batch in range(2,6)]
  out=io.StringIO()
  with (patch.object(resume,"open_caller",return_value=object()) as opened,
        patch.object(resume,"close_caller"),
        patch.object(resume,"call",side_effect=mock_receipts) as invoked,
        contextlib.redirect_stdout(out)):
   resume.main()
  self.assertEqual(opened.call_count,1)
  self.assertEqual([c.args for c in invoked.call_args_list],
                   [(1,2),(1,3),(1,4),(1,5)])
  doc=json.loads(next(s.split("=",1)[1] for s in out.getvalue().splitlines()
                    if s.startswith("NVIDIA_MINIMAX_RESUMED_SUMMARY=")))
  self.assertEqual(doc["source_run"],resume.EXPECTED_RUN)
  self.assertEqual(doc["first_run_cases"],8)
  self.assertEqual(doc["new_run_cases"],16)
  self.assertEqual(doc["total_fixed_cases"],24)
  self.assertEqual(doc["exact_matches"],23)
  self.assertEqual(doc["new_run_provider_calls_conservatively_reserved"],16)
  self.assertFalse(doc["model_activated"])

 def test_provider_429_is_one_attempt_then_held_without_retry(self):
  with (patch.object(resume,"open_caller",return_value=object()),
        patch.object(resume,"close_caller"),
        patch.object(resume,"call",side_effect=Retryable("PROVIDER_RATE_LIMIT")) as invoked,
        contextlib.redirect_stdout(io.StringIO())):
   with self.assertRaisesRegex(RuntimeError,"FIXED_MINIMAX_PROVIDER_HELD_NO_AUTO_RETRY"):
    resume.main()
  self.assertEqual(invoked.call_count,1)
if __name__=="__main__":
 unittest.main()
