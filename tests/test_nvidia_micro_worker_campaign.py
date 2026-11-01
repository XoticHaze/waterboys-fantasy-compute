"""Offline proof of the synthetic 48-case two-model campaign. No provider calls."""
import contextlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"scripts"))
import nvidia_micro_worker_campaign as mod

def receipt(mi,bi,passed=True):
    return {"schema":mod.SCHEMA,"model":mod.MODELS[mi],"model_index":mi,
        "batch":bi,"status":"batch_complete","calls":4,
        "results":[{"id":mod.IDS[bi]+f"{i+1:02}",
            "category":mod.CATEGORIES[bi],"http_status":200,
            "latency_ms":100+i,"format_valid":True,"passed":passed,"error":None
        } for i in range(4)]}

class MicroTests(unittest.TestCase):
    def setUp(self):
        mod.retries_by_task.clear()

    def test_complete_both_models_with_48_unique_cases_and_stay_shadow(self):
        items=[receipt(mi,bi) for mi in range(2) for bi in range(6)]
        with (patch.object(mod,"open_caller",return_value=object()) as start,
              patch.object(mod,"close_caller"),
              patch.object(mod,"call",side_effect=items) as invoke,
              contextlib.redirect_stdout(io.StringIO()) as out):
            mod.main()
        self.assertEqual(start.call_count,3)
        self.assertEqual(invoke.call_count,12)
        line=next(s for s in out.getvalue().splitlines() if s.startswith("MICRO_CAMPAIGN_SUMMARY="))
        doc=json.loads(line.split("=",1)[1])
        self.assertEqual(doc["total_tasks"],48)
        self.assertEqual(doc["provider_calls_conservatively_reserved"],48)
        self.assertFalse(doc["production_model_activated"])
        self.assertEqual(doc["model_results"][mod.MODELS[0]]["passed"],24)
        self.assertEqual(doc["model_results"][mod.MODELS[1]]["safety_passed"],12)

    def test_wrong_case_id_stops_not_fabricated_completion(self):
        obj=receipt(0,0)
        obj["results"][0]["id"]="S04"
        with self.assertRaisesRegex(RuntimeError,"MICRO_CASE_IDENTITY_MISMATCH"):
            mod.validate(obj,0,0)

    def test_wrong_model_is_rejected(self):
        obj=receipt(0,0)
        obj["model"]=mod.MODELS[1]
        with self.assertRaisesRegex(RuntimeError,"MICRO_RECEIPT_IDENTITY_MISMATCH"):
            mod.validate(obj,0,0)

    def test_429_credential_gate_not_counted_as_success(self):
        obj=receipt(0,0)
        obj["results"][0]["http_status"]=429
        with self.assertRaisesRegex(RuntimeError,"MICRO_ACCOUNT_AUTH_OR_QUOTA_REJECTED"):
            mod.validate(obj,0,0)

    def test_retry_requires_new_ephemeral_caller_and_counts_unknown_requests(self):
        mod.retries_by_task.clear()
        items=[mod.Retryable("PRIVATE_RESPONSE_NON200",delay=1)]+[
            receipt(mi,bi) for mi in range(2) for bi in range(6)]
        with (patch.object(mod,"open_caller",return_value=object()) as start,
              patch.object(mod,"close_caller"),
              patch.object(mod,"call",side_effect=items) as invoke,
              patch.object(mod.time,"sleep"),
              contextlib.redirect_stdout(io.StringIO()) as out):
            mod.main()
        self.assertEqual(start.call_count,4)
        self.assertEqual(invoke.call_count,13)
        doc=json.loads(next(s for s in out.getvalue().splitlines()
            if s.startswith("MICRO_CAMPAIGN_SUMMARY=")).split("=",1)[1])
        self.assertEqual(doc["provider_calls_conservatively_reserved"],52)
        self.assertEqual(doc["retry_events"],1)

if __name__=="__main__":
    unittest.main()
