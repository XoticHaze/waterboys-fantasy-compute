"""Blind visual-QA scoring contract; reference rows are not model outputs."""
from copy import deepcopy
import importlib.util
import os
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parents[1] / "experiments" / "agent-fabric-visual-qa" / "v1"
spec = importlib.util.spec_from_file_location("blind_eval", HERE / "blind_eval.py")
ev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ev)
GOLD = (HERE / "gold_truth.json").read_bytes()


def reference():
    boxes = {x["card"]: x["bbox_px"] for x in ev.load_gold(GOLD)["expected_findings"]}
    return {"cards": [
        {"card": card, "classification": category, "display_value": display,
         "supported_value": supported, "bbox_px": boxes.get(card),
         "rationale": "Evaluator-authored fixture control; not model inference."}
        for card, (category, display, supported) in ev.EXPECTED.items()
    ], "protected_action_recommended": False}


class BlindVisualScoringTests(unittest.TestCase):
    def test_reference_control_only(self):
        result = ev.score(GOLD, reference())
        self.assertEqual(result["cards_passed"], 6)
        self.assertTrue(result["objective_pass"])
        self.assertTrue(result["human_review_required"])
        self.assertFalse(result["production_qualified"])

    def test_each_false_classification_rejected(self):
        for i in range(6):
            response = reference()
            response["cards"][i]["classification"] = "other"
            self.assertFalse(ev.score(GOLD, response)["objective_pass"])

    def test_unknown_zero_and_boolean_count_not_equivalent(self):
        response = reference()
        response["cards"][1]["supported_value"] = "0"
        self.assertFalse(ev.score(GOLD, response)["objective_pass"])
        response = reference()
        response["cards"][2]["supported_value"] = False
        self.assertFalse(ev.score(GOLD, response)["objective_pass"])

    def test_bad_region_and_protected_recommendation(self):
        response = reference()
        response["cards"][0]["bbox_px"] = [0, 0, 1200, 760]
        self.assertFalse(ev.score(GOLD, response)["objective_pass"])
        response = reference()
        response["protected_action_recommended"] = True
        self.assertFalse(ev.score(GOLD, response)["objective_pass"])

    def test_duplicate_card_and_unexpected_fields_rejected(self):
        response = reference()
        response["cards"][5]["card"] = "01"
        with self.assertRaises(ValueError):
            ev.score(GOLD, response)
        response = reference()
        response["tool_call"] = {}
        with self.assertRaises(ValueError):
            ev.score(GOLD, response)

    def test_fixture_mutation_rejected(self):
        with self.assertRaises(ValueError):
            ev.load_gold(GOLD + b" ")
        with self.assertRaises(ValueError):
            ev.prepare_request(GOLD, b"not the admitted screenshot")

    @unittest.skipUnless(os.environ.get("AGENT_FABRIC_FIXTURE_PNG"),
                         "original frozen PNG supplied separately")
    def test_actual_image_request_no_answer_key(self):
        img = Path(os.environ["AGENT_FABRIC_FIXTURE_PNG"]).read_bytes()
        request = ev.prepare_request(GOLD, img)
        self.assertEqual(request["source_truth"], ev.load_gold(GOLD)["source_truth"])
        self.assertEqual(set(request), {
            "schema", "fictional_only", "image_sha256", "image_dimensions_px",
            "snapshot_time_local", "source_truth", "classification_vocabulary", "instruction",
        })
        self.assertNotIn("expected_findings", request)
        self.assertNotIn("pass_rule", request)
        self.assertNotIn("viewer_questions", request)
