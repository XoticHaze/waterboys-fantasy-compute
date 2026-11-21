"""Pure tests for fixed anonymous read-only Cloudflare factory discriminator."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/"scripts/cc_factory_access_edge_readonly.py"
spec=importlib.util.spec_from_file_location("cc_factory_access_edge_readonly",SCRIPT)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class AnonymousFactoryEdgeTests(unittest.TestCase):
    def test_access_login_redirect(self):
        z=mod.classify(302, "/cdn-cgi/access/login?redirect_url=private")
        self.assertTrue(z["cloudflare_access_redirect_observed"])
        self.assertTrue(z["unauthenticated_request_not_served"])
        self.assertFalse(z["full_policy_identity_verified"])

    def test_access_external_hostname(self):
        z=mod.classify(302,"https://slenderiq.cloudflareaccess.com/cdn-cgi/access/login")
        self.assertTrue(z["cloudflare_access_redirect_observed"])

    def test_unrelated_redirect_is_not_access_proof(self):
        z=mod.classify(302,"https://other.example.org/continue")
        self.assertFalse(z["cloudflare_access_redirect_observed"])
        self.assertTrue(z["unauthenticated_request_not_served"])

    def test_anonymous_factory_status_is_a_hold(self):
        z=mod.classify(200,"",'{"schema":"commandcenter.cloudflare.factory_status.v1","admitted":false}')
        self.assertTrue(z["anonymous_factory_status_exposed"])
        self.assertFalse(z["unauthenticated_request_not_served"])

    def test_no_leaking_redirect_or_private_body(self):
        z=mod.classify(403,"https://private.example.org/?secret=not-for-logs","bearer secretvalue")
        self.assertNotIn("secretvalue",str(z))
        self.assertNotIn("not-for-logs",str(z))
        self.assertFalse(z["cloudflare_access_redirect_observed"])

    def test_nonresponsive_is_indeterminate(self):
        z=mod.classify("NETWORK_UNAVAILABLE")
        self.assertFalse(z["unauthenticated_request_not_served"])
        self.assertFalse(z["cloudflare_access_redirect_observed"])

class ExistingAccessAppMetadataTests(unittest.TestCase):
    def test_exact_access_app_readback_redacts_audience_and_identity(self):
        import json
        from unittest.mock import patch
        spec2=importlib.util.spec_from_file_location(
            "cc_factory_existing_worker_readonly",
            SCRIPT.with_name("test_cc_factory_access_edge_readonly.py").parents[1] /
            "scripts/cc_factory_existing_worker_readonly.py")
        module=importlib.util.module_from_spec(spec2)
        spec2.loader.exec_module(module)
        class FakeHttp:
            status=200
            def __enter__(self): return self
            def __exit__(self,*args): return False
            def read(self,cap): return json.dumps({"success":True,"result":[{
                "name":"CC Shared Worker Factory","aud":"never-echo-this-aud",
                "destinations":[{"type":"worker","name":"shared-compute-worker-factory"}],
                "policies":[{"include":[{"email":{"email":"private-owner@example.com"}}]}]
            }]}).encode("utf-8")
        with patch.object(module.urllib.request,"urlopen",return_value=FakeHttp()):
            result=module.access_app_status("fixed-placeholder-token")
        self.assertTrue(result["existing_app_confirmed"])
        self.assertTrue(result["aud_present"])
        self.assertTrue(result["worker_destination_found"])
        self.assertNotIn("never-echo-this-aud",str(result))
        self.assertNotIn("private-owner@example.com",str(result))

class ExistingFactoryImmutableIdTests(unittest.TestCase):
    def test_only_exact_existing_factory_id_leaves_reader(self):
        import json
        from unittest.mock import patch
        spec3=importlib.util.spec_from_file_location(
            "cc_factory_existing_worker_readonly",
            SCRIPT.parents[1] / "scripts/cc_factory_existing_worker_readonly.py")
        module=importlib.util.module_from_spec(spec3)
        spec3.loader.exec_module(module)
        class FakeHttp:
            def __enter__(self): return self
            def __exit__(self,*args): return False
            def read(self,cap):
                return json.dumps({"success":True,"result":[
                    {"name":"some-other-worker","id":"b"*32},
                    {"name":"shared-compute-worker-factory","id":"a"*32}
                ]}).encode()
        with patch.object(module.urllib.request,"urlopen",return_value=FakeHttp()):
            result=module.factory_worker_id_readback("fixed-placeholder-token")
        self.assertTrue(result["id_verified"])
        self.assertEqual(result["factory_worker_id"],"a"*32)
        self.assertNotIn("b"*32,str(result))
        self.assertEqual(result["other_worker_ids_exported"],False)

if __name__=="__main__":
    unittest.main()
