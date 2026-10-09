from __future__ import annotations

import unittest

from waterboys_compute.collector import _reconcile_waiver_offer_rows
from waterboys_compute.espn_write import validate_preflight
from waterboys_compute.sniper import command_for_cancel, evaluate_candidate
from waterboys_compute.value import suggest_drop


class WaiverReconciliationSafetyTests(unittest.TestCase):
    def test_process_event_resolves_original_pending_offer(self):
        rows = [
            {
                "offer_id": "claim-1",
                "related_offer_id": None,
                "execution_type": "EXECUTE",
                "result": "PENDING",
                "date": 100,
                "player_id": 10,
                "bid": 25,
            },
            {
                "offer_id": "process-1",
                "related_offer_id": "claim-1",
                "execution_type": "PROCESS",
                "result": "EXECUTED",
                "date": 200,
                "player_id": 10,
                "bid": 25,
            },
        ]
        reconciled = _reconcile_waiver_offer_rows(rows)
        self.assertEqual(len(reconciled), 1)
        self.assertEqual(reconciled[0]["offer_id"], "claim-1")
        self.assertEqual(reconciled[0]["result"], "EXECUTED")
        self.assertEqual(reconciled[0]["resolution_offer_id"], "process-1")

    def test_failed_process_event_also_resolves_pending_offer(self):
        rows = [
            {
                "offer_id": "claim-2",
                "related_offer_id": None,
                "execution_type": "EXECUTE",
                "result": "PENDING",
                "date": 100,
            },
            {
                "offer_id": "process-2",
                "related_offer_id": "claim-2",
                "execution_type": "PROCESS",
                "result": "FAILED_INVALIDPLAYERSOURCE",
                "date": 200,
            },
        ]
        reconciled = _reconcile_waiver_offer_rows(rows)
        self.assertEqual(len(reconciled), 1)
        self.assertEqual(reconciled[0]["result"], "FAILED_INVALIDPLAYERSOURCE")

    def test_cancel_event_preserves_existing_canceled_semantics(self):
        rows = [
            {
                "offer_id": "claim-3",
                "related_offer_id": None,
                "execution_type": "EXECUTE",
                "result": "PENDING",
                "date": 100,
            },
            {
                "offer_id": "cancel-3",
                "related_offer_id": "claim-3",
                "execution_type": "CANCEL",
                "result": "CANCELED",
                "date": 150,
            },
        ]
        reconciled = _reconcile_waiver_offer_rows(rows)
        self.assertEqual(len(reconciled), 1)
        self.assertEqual(reconciled[0]["result"], "CANCELED")

    def test_drop_selector_never_uses_ir_occupant_for_active_add(self):
        roster = [
            {
                "player_id": 1,
                "name": "IR RB",
                "position": "RB",
                "lineup_slot": "IR",
                "projected_avg_points": 1,
            },
            {
                "player_id": 2,
                "name": "Bench WR",
                "position": "WR",
                "lineup_slot": "BE",
                "projected_avg_points": 2,
            },
        ]
        candidate = {
            "player_id": 99,
            "name": "Candidate RB",
            "position": "RB",
            "projected_avg_points": 20,
        }
        roster_cfg = {
            "slots": {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1, "DST": 1, "K": 1},
            "position_limits": {"RB": 4, "WR": 4},
        }
        drop = suggest_drop(roster, candidate, set(), roster_cfg)
        self.assertEqual(drop["player_id"], 2)

    def test_sniper_blocks_ir_drop_when_active_roster_is_full(self):
        active = [
            {
                "player_id": i,
                "name": f"Active {i}",
                "position": "WR",
                "lineup_slot": "BE",
                "projected_avg_points": 5,
                "current_week": {"points": None},
            }
            for i in range(1, 15)
        ]
        ir = {
            "player_id": 50,
            "name": "IR Player",
            "position": "RB",
            "lineup_slot": "IR",
            "projected_avg_points": 1,
            "current_week": {"points": None},
        }
        snapshot = {
            "waterboys": {"roster": active + [ir], "acquisition_budget_remaining": 900},
            "league": {"roster": {"size": 14}},
            "survival": {"waterboys_projected_margin_over_cutline": 30},
            "placement_engine": {},
        }
        row = {
            "player_id": 99,
            "name": "Candidate",
            "position": "RB",
            "inputs": {
                "availability_status": "FREEAGENT",
                "injury_status": "ACTIVE",
                "projected_avg_points": 20,
                "avg_points": 20,
                "recent_form": {"games_count": 3, "median": 20},
                "percent_started": 50,
            },
            "value": {
                "risk_adjusted_marginal_ppg": 3,
                "expected_added_points_remaining": 30,
                "value_over_best_free_replacement_ppg": 5,
            },
            "suggested_drop": {
                "player_id": 50,
                "name": "IR Player",
                "projected_avg_points": 1,
            },
            "bid_guidance": {"recommended": 0, "reservation_ceiling": 25},
            "market_reference": {"confidence": "high"},
        }
        policy = {
            "tiers": [
                {
                    "name": "cheap",
                    "max_bid": 25,
                    "min_risk_adjusted_marginal_ppg": 1,
                    "min_expected_added_points_remaining": 10,
                }
            ],
            "global_max_bid": 400,
            "survival_bands": {"green_margin": 25, "yellow_margin": 12},
            "green_reserve_faab": 150,
            "yellow_reserve_faab": 75,
            "red_reserve_faab": 0,
            "trap_guards": {"injury": {"block_statuses": ["OUT", "INJURY_RESERVE", "DOUBTFUL"]}},
        }
        evaluated = evaluate_candidate(row, snapshot, policy)
        self.assertIn("suggested_drop_does_not_free_active_slot", evaluated["reasons"])
        self.assertFalse(evaluated["eligible"])

    def test_execution_preflight_blocks_ir_drop_when_active_roster_is_full(self):
        active = [
            {
                "player_id": i,
                "lineup_slot": "BE",
            }
            for i in range(1, 15)
        ]
        ir = {"player_id": 50, "lineup_slot": "IR"}
        fresh = {
            "waterboys": {
                "roster": active + [ir],
                "acquisition_budget_remaining": 900,
            },
            "league": {"roster": {"size": 14}},
            "free_agents": [{"player_id": 99}],
        }
        command = {
            "action": "free_agent_add",
            "player_id": 99,
            "drop_player_id": 50,
        }
        with self.assertRaisesRegex(RuntimeError, "IR drop does not free"):
            validate_preflight(command, fresh)

    def test_cancel_command_id_distinguishes_duplicate_player_claims(self):
        snapshot = {"collected_at": "2026-10-09T03:00:00Z"}
        first = command_for_cancel(
            {"player_id": 10, "player": "P", "transaction_id": "aaaaaaaa-1111"},
            snapshot,
        )
        second = command_for_cancel(
            {"player_id": 10, "player": "P", "transaction_id": "bbbbbbbb-2222"},
            snapshot,
        )
        self.assertNotEqual(first["command_id"], second["command_id"])


if __name__ == "__main__":
    unittest.main()
