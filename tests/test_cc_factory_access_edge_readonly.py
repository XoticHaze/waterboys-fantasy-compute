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

if __name__=="__main__":
    unittest.main()
