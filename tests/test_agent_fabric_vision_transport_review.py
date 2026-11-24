import copy
import os
import sys
import unittest
from pathlib import Path
from base64 import b64decode

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "experiments/agent-fabric-visual-qa/v1"
sys.path.insert(0, str(DIR))
from blind_eval import EXPECTED, IMAGE_SHA, load_gold
from transport_review import FIXTURE_ID, MODEL, RECEIPT_SCHEMA, prepare, review

GOLD = (DIR / "gold_truth.json").read_bytes()

def mock_receipt():
    boxes = {r["card"]: r["bbox_px"] for r in load_gold(GOLD)["expected_findings"]}
    rows = [{"card": card, "classification": c, "display_value": shown,
             "supported_value": supported, "bbox_px": boxes.get(card),
             "rationale_present": True}
            for card, (c, shown, supported) in EXPECTED.items()]
    return {"schema": RECEIPT_SCHEMA, "fixture_id": FIXTURE_ID,
            "image_sha256": IMAGE_SHA, "model": MODEL, "provider_http": 200,
            "status": "candidate_unreviewed", "elapsed_ms": 10,
            "request_attempt_upper_bound": 1,
            "candidate": {"cards": rows, "protected_action_recommended": False},
            "fictional_only": True, "private_input_used": False,
            "model_code_executed": False, "commands_executed": False,
            "production_admitted": False, "human_review_required": True,
            "raw_model_response_exported": False, "rationale_exported": False}


class TransportReviewTests(unittest.TestCase):
    def test_reference_control_score_not_live_or_human_qualification(self):
        result = review(GOLD, mock_receipt())
        self.assertEqual(result["objective_score"]["cards_passed"], 6)
        self.assertTrue(result["objective_score"]["objective_pass"])
        self.assertFalse(result["rationale_human_reviewed"])
        self.assertFalse(result["live_provider_call_verified_by_this_script"])
        self.assertFalse(result["production_admitted"])

    def test_changed_answer_scored_wrong_and_malformed_proof_rejected(self):
        m = mock_receipt()
        m["candidate"]["cards"][1]["supported_value"] = 0
        self.assertEqual(review(GOLD, m)["objective_score"]["cards_passed"], 5)
        for key, value in (("image_sha256", "0"*64), ("model", "other"),
                           ("provider_http", 429), ("request_attempt_upper_bound", True),
                           ("raw_model_response_exported", True), ("production_admitted", True)):
            q = mock_receipt()
            q[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                review(GOLD, q)
        q = mock_receipt()
        q["candidate"]["cards"][0]["rationale"] = "untrusted"
        with self.assertRaises(ValueError):
            review(GOLD, q)

    def test_wrong_image_is_rejected(self):
        with self.assertRaises(ValueError):
            prepare(GOLD, b"not the fixture")

    @unittest.skipUnless(os.getenv("NVIDIA_VISUAL_FIXTURE_PNG"), "exact fixture not locally mounted")
    def test_actual_image_preparation_no_answer_key(self):
        img = Path(os.environ["NVIDIA_VISUAL_FIXTURE_PNG"]).read_bytes()
        result = prepare(GOLD, img)
        self.assertEqual(set(result), {"fixture_id", "image_base64"})
        self.assertEqual(b64decode(result["image_base64"]), img)


if __name__ == "__main__":
    unittest.main()
