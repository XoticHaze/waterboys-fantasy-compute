"""Non-model public fictional screenshot/QC fixture contract.

Checks honest visual benchmark source truth. Does not invoke a provider or
claim that a vision model achieved any score.
"""
from __future__ import annotations
import json, re, unittest
from datetime import datetime
from pathlib import Path

HERE=Path(__file__).resolve().parents[1]/'experiments'/'agent-fabric-visual-qa'/'v1'
HTML=HERE/'fictional_dashboard.html'
TRUTH=HERE/'gold_truth.json'

class FictionalVisionFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html=HTML.read_text(encoding='utf-8')
        cls.gold=json.loads(TRUTH.read_text(encoding='utf-8'))
    def test_public_fictional_only_and_no_inference_claim(self):
        v=self.gold
        self.assertEqual(v['schema'],'commandcenter.public_synthetic_vision_qa_fixture.v1')
        self.assertIs(v['fictional_only'],True)
        self.assertIs(v['image_input_admitted'],False)
        self.assertIs(v['model_inference_observed'],False)
        self.assertIn('Fictional only',self.html)
        self.assertIn('No commands available',self.html)
    def test_provenance_gates_do_not_turn_old_observation_live(self):
        v=self.gold
        now=datetime.fromisoformat(v['snapshot_time_local'])
        gw=v['source_truth']['gateway']
        observed=datetime.fromisoformat(gw['last_observed_local'])
        age=(now-observed).total_seconds()
        self.assertGreater(age,gw['ttl_seconds'])
        self.assertEqual(gw['current_state'],'stale_unverified')
        self.assertIn('Connected',self.html) # a *displayed* problem, not endorsed current status
    def test_unknown_is_distinct_from_zero(self):
        v=self.gold['source_truth']
        self.assertIsNone(v['historical_bars_AMAT']['verified_count'])
        self.assertEqual(v['verified_execution_admissions'],0)
        self.assertIn('0 bars',self.html)
    def test_no_fake_feedback_learning(self):
        x=self.gold['source_truth']['poolside']
        self.assertTrue(x['baseline_equals_revision'])
        self.assertEqual(x['confirmed_feedback_corrections'],0)
        self.assertEqual(x['independent_behavior_checks'],{'passed':60,'total':60})
        self.assertIn('100%',self.html) # source-to-pixel contradiction deliberately planted
    def test_region_labels_and_expected_findings(self):
        v=self.gold
        self.assertEqual({x['id'] for x in v['expected_findings']}, {'stale_gateway','unknown_not_zero','false_model_learning','overlapping_label'})
        self.assertEqual(v['rendered_image']['bbox_format'],'xyxy_pixels')
        w,h=v['rendered_image']['width_px'],v['rendered_image']['height_px']
        self.assertEqual((w,h),(1200,760))
        self.assertRegex(v['rendered_image']['sha256'],r'^[a-f0-9]{64}$')
        for case in v['expected_findings']:
            x1,y1,x2,y2=case['bbox_px']
            self.assertTrue(0<=x1<x2<=w and 0<=y1<y2<=h)
    def test_human_review_and_no_action_path(self):
        self.assertIn('human usability review',self.gold['pass_rule'])
        self.assertIn('No claim that any live order',self.html)
        self.assertNotRegex(self.html,r'Authorization: Bearer|client_secret|ssh-rsa')

if __name__=='__main__':unittest.main()
