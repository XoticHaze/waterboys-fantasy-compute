"""Offline only: primary 24-case shadow qualification and no automatic 429 retry."""
import contextlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import nvidia_micro_worker_primary_only as primary
from test_nvidia_micro_worker_campaign import receipt
from nvidia_micro_worker_campaign import Retryable

class PoolsidePrimaryOnlyTests(unittest.TestCase):
 def test_24_complete_fixed_poolside_cases_no_fallback_and_no_production(self):
  docs=[receipt(0,i) for i in range(6)]
  out=io.StringIO()
  with (patch.object(primary,"open_caller",return_value=object()) as opened,
        patch.object(primary,"close_caller") as closed,
        patch.object(primary,"call",side_effect=docs) as called,
        contextlib.redirect_stdout(out)):
   primary.main()
  self.assertEqual(called.call_count,6)
  self.assertEqual(opened.call_count,2)
  self.assertEqual(closed.call_count,2)
  self.assertTrue(all(c.args[0]==0 for c in called.call_args_list))
  summary=json.loads(next(line.split("=",1)[1] for line in out.getvalue().splitlines()
                         if line.startswith("NVIDIA_PRIMARY_SHADOW_SUMMARY=")))
  self.assertEqual(summary["attempted"],24)
  self.assertEqual(summary["protected_attempted"],12)
  self.assertEqual(summary["calls_conservatively_reserved"],24)
  self.assertFalse(summary["production_activation"])
  self.assertFalse(summary["commands_executed"])

 def test_first_provider_429_or_transient_holds_without_replay(self):
  out=io.StringIO()
  with (patch.object(primary,"open_caller",return_value=object()),
        patch.object(primary,"close_caller"),
        patch.object(primary,"call",side_effect=Retryable("PROVIDER_RATE_LIMIT")) as called,
        contextlib.redirect_stdout(out)):
   with self.assertRaisesRegex(RuntimeError,"PRIMARY_PROVIDER_HELD_NO_AUTORETRY"):
    primary.main()
  self.assertEqual(called.call_count,1)
  self.assertIn("NVIDIA_PRIMARY_HELD=PROVIDER_RATE_LIMIT",out.getvalue())

 def test_malformed_model_or_case_receipt_fails_closed(self):
  doc=receipt(1,0)
  with (patch.object(primary,"open_caller",return_value=object()),
        patch.object(primary,"close_caller"),
        patch.object(primary,"call",return_value=doc),
        contextlib.redirect_stdout(io.StringIO())):
   with self.assertRaisesRegex(RuntimeError,"MICRO_RECEIPT_IDENTITY_MISMATCH"):
    primary.main()
if __name__=="__main__":
 unittest.main()
