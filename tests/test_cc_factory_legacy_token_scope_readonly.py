"""No-network tests of safe incumbent-token scope introspection."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import urllib.error

SCRIPT=Path(__file__).resolve().parents[1]/"scripts/cc_factory_existing_worker_readonly.py"
spec=importlib.util.spec_from_file_location("cc_factory_existing_worker_readonly",SCRIPT)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

USER_VERIFY="/user/tokens/verify"
ACCOUNT_VERIFY="/accounts/"+module.ACCOUNT+"/tokens/verify"
class Http:
    status=200
    def __init__(self,body):self.body=body
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self,n):return json.dumps(self.body).encode()

class MockOpener:
    def __init__(self,payloads):
        self.payloads=payloads
        self.calls=[]
    def open(self,request,timeout=None):
        self.calls.append((request.get_method(),request.full_url))
        suffix=request.full_url.split("/client/v4",1)[-1]
        result=self.payloads.get(suffix)
        if isinstance(result,int):
            raise urllib.error.HTTPError(request.full_url,result,"expected",{},None)
        if result is None:
            raise AssertionError("Unexpected URL "+request.full_url)
        return Http(result)

class ExistingLegacyTokenScopeTests(unittest.TestCase):
    def test_user_token_visible_policies_are_redacted_and_not_denial_proof(self):
        token_id="a"*32
        opener=MockOpener({
            USER_VERIFY:{"success":True,"result":{"id":token_id,"status":"active"}},
            "/user/tokens/"+token_id:{"success":True,"result":{
                "name":"owner-private-api",
                "creator_email_at_creation":"secret@example.com",
                "policies":[
                    {"effect":"allow","resources":{"sensitive-account":"*"}},
                    {"effect":"deny","resources":{"worker-id-hidden":"*"}}
                ]}}
        })
        with patch.object(module.urllib.request,"build_opener",return_value=opener):
            receipt=module.legacy_deploy_token_scope_readback("secret-token-plaintext")
        self.assertEqual(receipt["token_identity_class"],"USER_TOKEN")
        self.assertEqual(receipt["policy_entry_count"],2)
        self.assertTrue(receipt["allows_present"])
        self.assertTrue(receipt["denies_present"])
        self.assertFalse(receipt["factory_write_denial_live_proven"])
        self.assertTrue(all(x[0]=="GET" for x in opener.calls))
        text=json.dumps(receipt)
        for secret in ("secret-token-plaintext",token_id,"secret@example.com",
                       "sensitive-account","worker-id-hidden","owner-private-api"):
            self.assertNotIn(secret,text)
    def test_account_token_detail_403_is_not_absence_or_write_denial(self):
        token_id="b"*32
        opener=MockOpener({
            USER_VERIFY:403,
            ACCOUNT_VERIFY:{"success":True,"result":{"id":token_id,"status":"active"}},
            "/accounts/"+module.ACCOUNT+"/tokens/"+token_id:403,
        })
        with patch.object(module.urllib.request,"build_opener",return_value=opener):
            receipt=module.legacy_deploy_token_scope_readback("valid-token-not-exported")
        self.assertEqual(receipt["token_identity_class"],"ACCOUNT_TOKEN")
        self.assertEqual(receipt["self_detail_http"],403)
        self.assertEqual(receipt["policy_shape"],"UNAVAILABLE")
        self.assertFalse(receipt["factory_write_denial_live_proven"])
        self.assertNotIn(token_id,json.dumps(receipt))
    def test_scoped_r2_reaches_broker_but_factory_get_denied_without_write_proof(self):
        root="/accounts/"+module.ACCOUNT+"/workers/scripts/"
        opener=MockOpener({
            root+"waterboys-fantasy-broker/settings":
                {"success":True,"result":{"bindings":[{"name":"PRIVATE_SECRET","text":"x"}]}},
            root+"shared-compute-worker-factory/settings":403,
        })
        with patch.object(module.urllib.request,"build_opener",return_value=opener):
            receipt=module.scoped_existing_deploy_candidate_readback("r2-secret-private")
        self.assertEqual(receipt["existing_broker_settings_http"],200)
        self.assertEqual(receipt["protected_factory_settings_http"],403)
        self.assertTrue(receipt["configured"])
        self.assertFalse(receipt["factory_write_denial_proven"])
        self.assertFalse(receipt["scoped_deploy_write_admission_proven"])
        self.assertEqual(len(opener.calls),2)
        self.assertTrue(all(method=="GET" for method,url in opener.calls))
        self.assertNotIn("r2-secret-private",json.dumps(receipt))
        self.assertNotIn("PRIVATE_SECRET",json.dumps(receipt))
    def test_missing_scoped_r2_does_not_promote_legacy(self):
        receipt=module.scoped_existing_deploy_candidate_readback("")
        self.assertFalse(receipt["configured"])
        self.assertEqual(receipt["existing_broker_settings_http"],"NOT_ATTEMPTED")
        self.assertFalse(receipt["factory_write_denial_proven"])
    def test_public_report_omits_private_metadata_and_pins_run(self):
        receipt={
            "settings_http":200,
            "existing_factory_immutable_id":{"id_verified":True,"factory_worker_id":"a"*32},
            "protected_access_application_readback":{"existing_app_confirmed":True,
                 "aud":"secret-owner-aud"},
            "activation_flags":{"FACTORY_EXECUTOR_ENABLED":"0",
              "FACTORY_CREATE_ENABLED":"0","FACTORY_SCOPED_TOKEN_ENABLED":"0"},
            "existing_legacy_token_scope_metadata":{"token_identity_class":"USER_TOKEN",
              "self_verify_http":200,"self_detail_http":403,
              "policy_shape":"UNAVAILABLE", "token":"secret-value",
              "creator_email":"sensitive@example.com","factory_write_denial_live_proven":False},
            "existing_scoped_deploy_comparison":{"configured":True,
              "existing_broker_settings_http":200,
              "protected_factory_settings_http":403,"token":"scope-secret"}
        }
        r=module.public_audit_report(receipt,"44900012345","f"*40)
        self.assertEqual(r["schema"],"commandcenter.cloudflare.factory_scope_audit_receipt.v1")
        self.assertEqual(r["github_run_id"],"44900012345")
        self.assertEqual(r["factory_execution_flags"]["FACTORY_EXECUTOR_ENABLED"],"0")
        self.assertFalse(r["write_denial_proven"])
        self.assertEqual(r["cloudflare_mutations"],0)
        clean=json.dumps(r)
        for private in ["secret-value","sensitive@example.com","secret-owner-aud",
                        "scope-secret","a"*32]:
            self.assertNotIn(private,clean)
        with self.assertRaises(ValueError):
            module.public_audit_report(receipt,"not-numeric","f"*40)
    def test_no_scope_visibility_never_proves_denial(self):
        opener=MockOpener({USER_VERIFY:403,ACCOUNT_VERIFY:403})
        with patch.object(module.urllib.request,"build_opener",return_value=opener):
            receipt=module.legacy_deploy_token_scope_readback("token-private")
        self.assertEqual(receipt["token_identity_class"],"NOT_VERIFIED")
        self.assertEqual(receipt["self_detail_http"],"NOT_ATTEMPTED")
        self.assertFalse(receipt["factory_write_denial_live_proven"])
        self.assertTrue(receipt["manual_scope_review_still_required"])

if __name__=="__main__":
    unittest.main()
