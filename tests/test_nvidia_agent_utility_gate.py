"""The resulting capability decision is tied to actual small public samples."""
from copy import deepcopy
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / 'experiments' / 'nvidia-agent-artifact-v1'
SPEC = importlib.util.spec_from_file_location('agent_utility', DIR / 'select_utility.py')
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)
DOC = json.loads((DIR / 'capability_evidence.json').read_text(encoding='utf-8'))


class SourceScopedCapabilityGate(unittest.TestCase):
    def test_exact_observed_task_specific_defaults(self):
        value = gate.assess(DOC)
        self.assertEqual(value['code_generation'], 'REVIEW_STATIC_SOURCE_ONLY')
        self.assertEqual(value['protected_orchestration'], 'DETERMINISTIC_ROUTER_ONLY')
        self.assertEqual(value['fixed_operator_customer_drafting'], 'PREFER_DETERMINISTIC_TEMPLATES')
        self.assertFalse(value['automatic_model_activation'])
        self.assertFalse(value['production_authority'])
        self.assertFalse(value['real_user_value_human_reviewed'])

    def test_wrong_source_or_model_fails_closed(self):
        for k, v in [('model', 'unapproved/model'), ('automatic_model_promotion', True)]:
            other=deepcopy(DOC)
            other[k]=v
            with self.assertRaises(ValueError): gate.assess(other)

    def test_wrong_run_or_forged_score_fails_closed(self):
        examples=[('code_generation','run_id',44499189814),
                  ('code_generation','ast_checks_passed',149),
                  ('orchestration','protected_passed',12),
                  ('fixed_drafting','model_objective_passes',4),
                  ('fixed_drafting','template_objective_passes',3)]
        for domain, field, value in examples:
            other=deepcopy(DOC)
            other['evidence'][domain][field]=value
            with self.assertRaises(ValueError, msg=f'{domain}/{field}'):
                gate.assess(other)

    def test_private_action_or_human_claim_fails_closed(self):
        examples=[('protected_actions_executed',True),('real_private_input_used',True)]
        for k,v in examples:
            other=deepcopy(DOC);other[k]=v
            with self.assertRaises(ValueError):gate.assess(other)
        other=deepcopy(DOC)
        other['evidence']['fixed_drafting']['human_reviewed']=True
        with self.assertRaises(ValueError):gate.assess(other)


if __name__=='__main__':unittest.main()
