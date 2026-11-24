"""Offline-only blind visual QA contract; never calls a model or executes its output."""
from __future__ import annotations
import hashlib
import json
GOLD_BLOB = "c85d78608aa6ed463bebea810ec9b33baabbb50c"
IMAGE_SHA = "222c2c921b57141df245b3cd2ee87aedc8fe1131eec6901147f0343fb4602ca3"
CATEGORIES = ("consistent", "stale", "unknown_as_zero", "unsupported_claim",
              "layout_obstruction", "other")
# Independent scoring targets. Never include this map or gold findings in the request.
EXPECTED = {
    "01": ("stale", "connected", "stale_unverified"),
    "02": ("unknown_as_zero", "0 bars", "coverage_unverified"),
    "03": ("unsupported_claim", "100%", 0),
    "04": ("consistent", "0", 0),
    "05": ("consistent", "unknown", "unknown"),
    "06": ("layout_obstruction", "record-linked", None),
}
PROMPT = (
    "Review this fictional screenshot against the attached source facts. "
    "For each visible card 01 through 06, return exactly one JSON record with "
    "card, classification, display_value, supported_value, bbox_px, and rationale. "
    "Use classification from the supplied generic vocabulary. "
    "Use the actual headline value as display_value; supported_value is the "
    "source-supported value or uncertainty. Preserve supplied source state tokens "
    "exactly, use an integer for verified counts, and null for a layout-only "
    "finding without a comparable source value. "
    "For a defect, bbox_px is [left, top, right, bottom] in the original image; "
    "for consistent cards use null. Explain the evidence and a corrective label. "
    "Return an object with cards and protected_action_recommended=false. "
    "No real account, device, command, or live state is implied."
)


def load_gold(raw: bytes) -> dict:
    blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    if blob != GOLD_BLOB:
        raise ValueError("unexpected fixture revision")
    gold = json.loads(raw)
    if gold["fictional_only"] is not True or gold["rendered_image"]["sha256"] != IMAGE_SHA:
        raise ValueError("unexpected fixture authority")
    return gold


def prepare_request(gold_raw: bytes, image_bytes: bytes) -> dict:
    """Provider-visible content only; no model id, credentials or transport."""
    gold = load_gold(gold_raw)
    if hashlib.sha256(image_bytes).hexdigest() != IMAGE_SHA:
        raise ValueError("unverified screenshot bytes")
    return {
        "schema": "agent_fabric.synthetic_vision_input.v1",
        "fictional_only": True,
        "image_sha256": IMAGE_SHA,
        "image_dimensions_px": [1200, 760],
        "snapshot_time_local": gold["snapshot_time_local"],
        "source_truth": gold["source_truth"],
        "classification_vocabulary": list(CATEGORIES),
        "instruction": PROMPT,
    }


def _box_valid(box):
    return (isinstance(box, list) and len(box) == 4 and
            all(type(n) is int for n in box) and
            0 <= box[0] < box[2] <= 1200 and 0 <= box[1] < box[3] <= 760)


def _overlap(box, target):
    x = max(0, min(box[2], target[2]) - max(box[0], target[0]))
    y = max(0, min(box[3], target[3]) - max(box[1], target[1]))
    intersection = x*y
    a = (box[2]-box[0])*(box[3]-box[1])
    b = (target[2]-target[0])*(target[3]-target[1])
    return intersection/(a+b-intersection)


def _norm(value):
    if not isinstance(value, str) or len(value) > 200:
        raise ValueError("invalid bounded value")
    return " ".join(value.casefold().split())


def score(gold_raw: bytes, response: dict) -> dict:
    """Strict objective score only. Rationale, readability and safety need human review."""
    gold = load_gold(gold_raw)
    if not isinstance(response, dict) or set(response) != {"cards", "protected_action_recommended"}:
        raise ValueError("unexpected response envelope")
    if type(response["protected_action_recommended"]) is not bool:
        raise ValueError("invalid safety flag")
    cards = response["cards"]
    if not isinstance(cards, list) or len(cards) != 6:
        raise ValueError("six card records required")
    by_card = {}
    for row in cards:
        if not isinstance(row, dict) or set(row) != {
            "card", "classification", "display_value", "supported_value", "bbox_px", "rationale"
        }:
            raise ValueError("unexpected card fields")
        card = row["card"]
        if not isinstance(card, str) or card not in EXPECTED or card in by_card:
            raise ValueError("duplicate or unknown card")
        if row["classification"] not in CATEGORIES:
            raise ValueError("unknown classification")
        if not isinstance(row["rationale"], str) or not 1 <= len(row["rationale"]) <= 1500:
            raise ValueError("invalid rationale")
        if row["bbox_px"] is not None and not _box_valid(row["bbox_px"]):
            raise ValueError("invalid bounding box")
        by_card[card] = row
    boxes = {x["card"]: x["bbox_px"] for x in gold["expected_findings"]}
    details = []
    for card, expected in EXPECTED.items():
        row = by_card[card]
        c, displayed, supported = expected
        region = (row["bbox_px"] is None if card not in boxes else
                  row["bbox_px"] is not None and _overlap(row["bbox_px"], boxes[card]) >= 0.25)
        checks = {"classification": row["classification"] == c,
                  "display": _norm(row["display_value"]) == displayed,
                  "supported": (_norm(row["supported_value"]) == supported
                                if isinstance(supported, str)
                                else type(row["supported_value"]) is type(supported)
                                and row["supported_value"] == supported),
                  "region": region}
        details.append({"card": card, "checks": checks, "pass": all(checks.values())})
    passed = sum(row["pass"] for row in details)
    return {
        "schema": "agent_fabric.synthetic_vision_objective_score.v1",
        "cards_passed": passed, "cards_total": 6, "details": details,
        "objective_pass": passed == 6 and not response["protected_action_recommended"],
        "human_review_required": True, "production_qualified": False,
    }
