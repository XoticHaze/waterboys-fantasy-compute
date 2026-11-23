"""No-network tests of safe incumbent-token scope introspection."""
from __future__ import annotations
import importlib.util
import json
import hashlib
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
              "FACTORY_CREATE_ENABLED":"0","FACTORY_SCOPED_TOKEN_ENABLED":"0",
              "FACTORY_INSPECT_ENABLED":"0","FACTORY_STAGE_VERSION_ENABLED":"0",
              "FACTORY_MACHINE_READONLY_ENABLED":"0",
              "FACTORY_MACHINE_INSPECT_ENABLED":"0"},
            "factory_script_fingerprint":{"http_status":200,"sha256":"f"*64,
              "byte_length":12,"complete_read":True,
              "source_equals_reviewed_commit":False,"source_bytes_exported":False},
            "privileged_binding_presence":{
              "FACTORY_WORKERS_ADMIN":"malicious-secret-value",
              "FACTORY_TOKEN_ISSUER":"NOT_LISTED",
              "FACTORY_SECRET_WRITER":"PRESENT",
              "FACTORY_QUEUE_GITHUB_TOKEN":"NOT_LISTED"},
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
        self.assertEqual(r["factory_script_fingerprint"]["sha256"],"f"*64)
        self.assertFalse(r["factory_script_fingerprint"]["source_equals_reviewed_commit"])
        self.assertFalse(r["factory_script_fingerprint"]["source_bytes_exported"])
        self.assertEqual(r["factory_execution_flags"]["FACTORY_STAGE_VERSION_ENABLED"],"0")
        self.assertEqual(r["factory_privileged_bindings"]["FACTORY_WORKERS_ADMIN"],"UNVERIFIED")
        self.assertEqual(r["factory_privileged_bindings"]["FACTORY_SECRET_WRITER"],"PRESENT")
        self.assertEqual(set(r["factory_execution_flags"]),set(module.FLAGS))
        self.assertEqual(set(r["factory_privileged_bindings"]),set(module.PRIVILEGED))
        self.assertFalse(r["write_denial_proven"])
        self.assertEqual(r["cloudflare_mutations"],0)
        clean=json.dumps(r)
        for private in ["secret-value","sensitive@example.com","secret-owner-aud",
                        "scope-secret","a"*32,"malicious-secret-value"]:
            self.assertNotIn(private,clean)
        with self.assertRaises(ValueError):
            module.public_audit_report(receipt,"not-numeric","f"*40)
    def test_only_exact_full_traffic_deployment_version_is_released(self):
        v="123e4567-e89b-42d3-a456-426614174000"
        deployment="aabbccdd-eeff-4411-8899-aabbccddeeff"
        good=module.fixed_factory_deployment_identity({
            "id":deployment,"source":"wrangler",
            "versions":[{"version_id":v,"percentage":100}],
            "hidden_script":"do-not-echo-this"})
        self.assertEqual(good["deployment_id"],deployment)
        self.assertEqual(good["full_traffic_version_id"],v)
        self.assertTrue(good["unique_full_traffic_version"])
        self.assertFalse(good["source_content_attested"])
        self.assertNotIn("do-not-echo-this",str(good))
        mixed=module.fixed_factory_deployment_identity({"id":deployment,
            "versions":[{"version_id":v,"percentage":75},
                        {"version_id":"bad-value","percentage":25}]})
        self.assertIsNone(mixed["full_traffic_version_id"])
        self.assertFalse(mixed["unique_full_traffic_version"])
        bad=module.fixed_factory_deployment_identity({"id":"unverified",
            "versions":[{"version_id":"malformed","percentage":100}]})
        self.assertIsNone(bad["deployment_id"])
        self.assertIsNone(bad["full_traffic_version_id"])
    def test_no_scope_visibility_never_proves_denial(self):
        opener=MockOpener({USER_VERIFY:403,ACCOUNT_VERIFY:403})
        with patch.object(module.urllib.request,"build_opener",return_value=opener):
            receipt=module.legacy_deploy_token_scope_readback("token-private")
        self.assertEqual(receipt["token_identity_class"],"NOT_VERIFIED")
        self.assertEqual(receipt["self_detail_http"],"NOT_ATTEMPTED")
        self.assertFalse(receipt["factory_write_denial_live_proven"])
        self.assertTrue(receipt["manual_scope_review_still_required"])

    def test_deployed_script_raw_fingerprint_is_get_only_and_secret_free(self):
        data=b"export default {fetch(){return new Response('secret-source-data');}}"
        calls=[]
        class Script:
            status=200
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def read(self,n):return data[:n]
        class Opener:
            def open(self,request,timeout=None):
                calls.append((request.get_method(),request.full_url))
                return Script()
        with patch.object(module.urllib.request,"build_opener",return_value=Opener()):
            r=module.factory_script_fingerprint_readback("secret-bearer")
        self.assertEqual(r["sha256"],hashlib.sha256(data).hexdigest())
        self.assertEqual(r["byte_length"],len(data))
        self.assertTrue(r["complete_read"])
        self.assertEqual(calls,[("GET",module.API+"/accounts/"+module.ACCOUNT+
                               "/workers/scripts/"+module.WORKER)])
        self.assertFalse(r["source_equals_reviewed_commit"])
        self.assertFalse(r["source_bytes_exported"])
        self.assertNotIn("secret-bearer",str(r))
        self.assertNotIn("secret-source-data",str(r))

    def test_oversize_script_never_returns_truncated_digest(self):
        class Big:
            status=200
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def read(self,n):return b"x"*n
        class Opener:
            def open(self,request,timeout=None):return Big()
        with patch.object(module.urllib.request,"build_opener",return_value=Opener()):
            r=module.factory_script_fingerprint_readback("secret-bearer")
        self.assertEqual(r["http_status"],200)
        self.assertIsNone(r["sha256"])
        self.assertIsNone(r["byte_length"])
        self.assertFalse(r["complete_read"])

    def test_script_get_http403_never_promotes_source_identity(self):
        class Opener:
            def open(self,request,timeout=None):
                raise urllib.error.HTTPError(request.full_url,403,"denied",{},None)
        with patch.object(module.urllib.request,"build_opener",return_value=Opener()):
            r=module.factory_script_fingerprint_readback("secret-bearer")
        self.assertEqual(r["http_status"],403)
        self.assertIsNone(r["sha256"])
        self.assertFalse(r["source_equals_reviewed_commit"])

if __name__=="__main__":
    unittest.main()
