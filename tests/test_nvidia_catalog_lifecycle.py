import importlib.util
from datetime import datetime,timezone,timedelta
from pathlib import Path
import unittest
spec=importlib.util.spec_from_file_location("lifecycle",Path(__file__).resolve().parents[1]/"scripts/nvidia_catalog_lifecycle.py")
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
class LifecycleTests(unittest.TestCase):
    def test_delta(self):
        now=datetime(2026,11,27,tzinfo=timezone.utc)
        c={"catalog_http":200,"calls":1,"observed_at":now.isoformat(),"catalog_model_ids":["a1/old","a1/new","a1/nonchat"],"eligible_model_ids":["a1/old","a1/new"]}
        rows=[{"model":"a1/old","task":t,"at":now.isoformat(),"run":1,"job":2,"http":200,"latency_ms":100,"passed":True} for t in m.TASKS]
        rows+=[{**rows[0],"model":"a1/gone"}]
        out=m.project(c,rows,now,True)
        self.assertEqual([r["model"] for r in out["benchmark_due"]],["a1/new"])
        self.assertEqual(out["not_in_current_catalog"],["a1/gone"])
        self.assertEqual(out["ranked_assist_candidates"][0]["model"],"a1/old")
        self.assertFalse(out["activation_authorized"])
    def test_stale(self):
        now=datetime(2026,11,27,tzinfo=timezone.utc)
        c={"catalog_http":200,"calls":1,"observed_at":(now-timedelta(days=2)).isoformat(),"catalog_model_ids":[],"eligible_model_ids":[]}
        with self.assertRaises(ValueError):m.project(c,[],now,True)

    def test_select_only_due_pairs(self):
        c={"eligible_model_ids":["a1/one","a1/two","a1/three","a1/four","a1/five"]}
        plan={"history_complete":True,"benchmark_due":[{"model":x} for x in ("a1/one","a1/two","a1/three","a1/five")]}
        self.assertEqual(m.select_due_batches(c,plan),[0,2])
        plan["history_complete"]=False
        self.assertEqual(m.select_due_batches(c,plan),[])
