"""Offline-only regression tests for the full catalog NVIDIA campaign."""
import contextlib
import io
import json
import unittest
from unittest.mock import patch

from scripts import nvidia_role_full_catalog_campaign as mod


def fake_doc(batch, ids, http=200, count=3):
    chosen = ids[batch * 2:(batch + 1) * 2]
    return {
        "schema": mod.EXPECTED_SCHEMA,
        "batch": batch,
        "status": "batch_complete",
        "calls": count,
        "eligible_count": len(ids),
        "eligible_model_ids": ids,
        "results": [{
            "model": name,
            "results": [{"task": "logic", "http_status": http,
                         "passed": http == 200, "format_valid": http == 200,
                         "latency_ms": 10, "error": None}],
        } for name in chosen],
    }


class FullCatalogCampaignTests(unittest.TestCase):
    def setUp(self):
        self.ids = ["example/model%02d" % i for i in range(61)]

    def test_61_models_mapped_to_31_batches_without_leaking_prompts(self):
        with (patch.object(mod, "open_caller", return_value=object()) as started,
              patch.object(mod, "close_caller"),
              patch.object(mod, "invoke",
                           side_effect=lambda b: fake_doc(b, self.ids, count=2 if b == 30 else 3)) as called,
              contextlib.redirect_stdout(io.StringIO()) as output):
            self.assertEqual(mod.main(), 0)
        self.assertEqual(called.call_count, 31)
        self.assertEqual(started.call_count, 7)
        result = [line for line in output.getvalue().splitlines()
                  if line.startswith("NVIDIA_CAMPAIGN_SUMMARY=")]
        self.assertEqual(len(result), 1)
        summary = json.loads(result[0].split("=", 1)[1])
        self.assertEqual(summary["attempted_models"], 61)
        self.assertEqual(summary["eligible_models"], 61)
        self.assertEqual(summary["batches"], 31)
        self.assertEqual(summary["api_calls_receipted"], 92)
        self.assertEqual(summary["request_ceiling"], 4000)
        self.assertFalse(summary["raw_content_or_secrets_exported"])

    def test_transient_batch_restarts_caller_and_reserves_unknown_calls(self):
        ids = self.ids[:2]
        with (patch.object(mod, "open_caller", return_value=object()) as started,
              patch.object(mod, "close_caller"),
              patch.object(mod.time, "sleep"),
              patch.object(mod, "invoke", side_effect=[
                  mod.TemporaryBatchFailure("PRIVATE_SERVICE_RESPONSE_TRANSIENT", cooldown=1),
                  fake_doc(0, ids),
              ]) as called,
              contextlib.redirect_stdout(io.StringIO()) as output):
            self.assertEqual(mod.main(), 0)
        self.assertEqual(called.call_count, 2)
        self.assertEqual(started.call_count, 2)
        result = next(line for line in output.getvalue().splitlines()
                      if line.startswith("NVIDIA_CAMPAIGN_SUMMARY="))
        summary = json.loads(result.split("=", 1)[1])
        self.assertEqual(summary["transient_retries"], 1)
        self.assertEqual(summary["api_calls_max_possible_reserved"], 18)
        self.assertEqual(summary["api_calls_receipted"], 3)

    def test_mismatching_catalog_stops(self):
        with self.assertRaisesRegex(RuntimeError, "CATALOG_CHANGED"):
            mod.validated_batch(fake_doc(1, self.ids),
                                1, self.ids[:-1])

    def test_payment_or_quota_gate_stops(self):
        for status in (401, 402, 429):
            with self.subTest(status=status):
                with self.assertRaisesRegex(RuntimeError, "PROVIDER_GLOBAL"):
                    mod.validated_batch(fake_doc(0, self.ids, http=status),
                                        0, self.ids)

    def test_model_coverage_must_match_expected_identity(self):
        doc = fake_doc(0, self.ids)
        doc["results"] = doc["results"][:1]
        with self.assertRaisesRegex(RuntimeError, "MODEL_RESULT_SET_MISMATCH"):
            mod.validated_batch(doc, 0, self.ids)

    def test_per_batch_request_count_fails_closed(self):
        doc = fake_doc(0, self.ids, count=10)
        with self.assertRaisesRegex(RuntimeError, "INVALID_PER_BATCH"):
            mod.validated_batch(doc, 0, self.ids)

    def test_changed_task_identity_fails_closed(self):
        doc = fake_doc(0, self.ids)
        doc["results"][0]["results"][0]["task"] = "broker_trade"
        with self.assertRaisesRegex(RuntimeError, "UNEXPECTED_TASK"):
            mod.validated_batch(doc, 0, self.ids)

    def test_rotating_caller_terminates_process_group(self):
        from unittest.mock import Mock
        process = Mock()
        process.pid = 4242
        with (patch.object(mod.os, "killpg") as kill,
              patch.object(mod, "caller_port_occupied", return_value=False)):
            mod.close_caller(process)
        kill.assert_called_once_with(4242, mod.signal.SIGTERM)

    def test_orphan_caller_port_causes_fail_closed(self):
        from unittest.mock import Mock
        process = Mock()
        process.pid = 4242
        with (patch.object(mod.os, "killpg"),
              patch.object(mod, "caller_port_occupied", return_value=True),
              patch.object(mod.time, "sleep")):
            with self.assertRaisesRegex(RuntimeError, "PORT_NOT_RELEASED"):
                mod.close_caller(process)

    def test_duplicate_catalog_ids_fails_closed(self):
        doc = fake_doc(0, self.ids)
        doc["eligible_model_ids"][1] = doc["eligible_model_ids"][0]
        with self.assertRaisesRegex(RuntimeError, "INVALID_CATALOG"):
            mod.validated_batch(doc, 0, None)


if __name__ == "__main__":
    unittest.main()
