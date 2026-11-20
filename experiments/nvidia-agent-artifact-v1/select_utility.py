#!/usr/bin/env python3
"""Research-only utility gate over exact public-fictional evidence.

It chooses a safer *review recommendation*, not a model, device, broker,
production workload or execution placement. Evidence must be independently
reconciled with the public GitHub run logs before any actual adoption.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any

INPUT = Path(__file__).resolve().with_name('capability_evidence.json')
MODEL = 'poolside/laguna-xs-2.1'
EXPECTED_RUNS = {'code_generation': 44499189813,
                 'orchestration': 44499436768,
                 'fixed_drafting': 44685699867}
EXPECTED_HASH = '65411e83e826bd039729c381e9b895d8ad83f3f954ee14b01d72122a369f6ac0'


def assess(doc: dict[str, Any]) -> dict[str, Any]:
    if (not isinstance(doc, dict) or
        doc.get('schema') != 'commandcenter.public_synthetic_agent_capability_evidence.v1' or
        doc.get('model') != MODEL or
        doc.get('fictional_only') is not True or
        doc.get('real_private_input_used') is not False or
        doc.get('protected_actions_executed') is not False or
        doc.get('automatic_model_promotion') is not False or
        not isinstance(doc.get('evidence'), dict) or set(doc['evidence']) != set(EXPECTED_RUNS)):
        raise ValueError('CAPABILITY_EVIDENCE_SCOPE_INVALID')
    e = doc['evidence']
    if any(not isinstance(e[k], dict) or e[k].get('run_id') != rid
           for k, rid in EXPECTED_RUNS.items()):
        raise ValueError('CAPABILITY_EVIDENCE_ORIGIN_INVALID')
    c, o, d = e['code_generation'], e['orchestration'], e['fixed_drafting']
    def count(v: object, total: int) -> bool:
        return type(v) is int and 0 <= v <= total
    if (c.get('model_source_sha256') != EXPECTED_HASH or
        c.get('model_code_executed') is not False or
        c.get('production_patch_applied') is not False or
        o.get('commands_executed') is not False or
        d.get('customer_messages_sent') is not False or
        d.get('human_reviewed') is not False or
        not all(count(c.get(k), 5) for k in ('model_tasks_passed',)) or
        c.get('model_tasks_total') != 5 or
        not count(c.get('ast_checks_passed'), 150) or c.get('ast_checks_total') != 150 or
        not count(o.get('decisions_passed'), 24) or o.get('decisions_total') != 24 or
        not count(o.get('protected_passed'), 12) or o.get('protected_total') != 12 or
        not count(d.get('model_objective_passes'), 4) or
        not count(d.get('template_objective_passes'), 4) or
        d.get('cases_total') != 4 or not count(d.get('unsupported_claim_flags'), 4)):
        raise ValueError('CAPABILITY_EVIDENCE_MEASUREMENT_INVALID')
    if (c['model_tasks_passed'] != 5 or c['ast_checks_passed'] != 150 or
        o['decisions_passed'] != 21 or o['protected_passed'] != 11 or
        d['model_objective_passes'] != 1 or d['template_objective_passes'] != 4 or
        d['unsupported_claim_flags'] != 0):
        raise ValueError('CAPABILITY_EVIDENCE_OUTCOME_MISMATCH')
    return {
        'schema': 'commandcenter.public_synthetic_agent_utility_review.v1',
        'model': MODEL,
        'code_generation': 'REVIEW_STATIC_SOURCE_ONLY' if c['model_tasks_passed'] == 5 and c['ast_checks_passed'] == 150 else 'HOLD_UNRELIABLE_GENERATION',
        'protected_orchestration': 'DETERMINISTIC_ROUTER_ONLY',
        'fixed_operator_customer_drafting': 'PREFER_DETERMINISTIC_TEMPLATES' if d['template_objective_passes'] >= d['model_objective_passes'] else 'MODEL_DRAFT_HUMAN_REVIEW_ONLY',
        'reason': 'task_specific_evidence_not_general_agent_intelligence',
        'automatic_model_activation': False,
        'production_authority': False,
        'real_user_value_human_reviewed': False,
        'origin_log_rechecked_by_this_script': False,
    }


def main() -> None:
    result = assess(json.loads(INPUT.read_text(encoding='utf-8')))
    print('NVIDIA_SYNTHETIC_UTILITY_REVIEW=' + json.dumps(result, sort_keys=True, separators=(',', ':')))


if __name__ == '__main__':
    main()
