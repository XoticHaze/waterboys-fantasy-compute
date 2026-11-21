import unittest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/"scripts"))
from cc_incomeengine_studio_cloudflare_readonly import summarize, ACCOUNT, ZONE, STUDIO, OWNER_POLICY_NAME

class StudioZoneGetOnlyTests(unittest.TestCase):
    def test_zone_denied_no_false_negative(self):
        calls=[]
        def mock(token,path):
            calls.append(path);return 403,None
        r=summarize('fake',mock)
        self.assertEqual(r['zone_get_http'],403)
        self.assertEqual(r['studio_dns_state'],'UNKNOWN')
        self.assertFalse(r['production_deployment_admitted'])
        self.assertEqual(len(calls),1)
    def test_visible_zone_and_exact_host_not_modified(self):
        calls=[]
        def mock(token,path):
            calls.append(path)
            if path.startswith('/zones?'):
                return 200,[{'name':ZONE,'id':'a'*32,'account':{'id':ACCOUNT}}]
            if '/dns_records?' in path:
                return 200,[{'name':'ha.'+ZONE,'type':'CNAME'}]
            if '/access/apps?' in path:
                return 200,[]
            if '/access/policies?' in path:
                return 200,[{'name':OWNER_POLICY_NAME}]
            raise AssertionError(path)
        r=summarize('fake',mock)
        self.assertEqual(r['studio_dns_state'],'NO_RECORD_IN_VISIBLE_ZONE')
        self.assertEqual(r['reusable_owner_policy_state'],'EXACT_POLICY_LISTED')
        self.assertEqual(r['access_application_state'],'NO_EXACT_APP_IN_FIRST_PAGE')
        self.assertEqual(r['cloudflare_mutations'],0)
        self.assertFalse(r['ha_dns_mutated'])
        self.assertTrue(all(p.startswith(('/zones?', '/zones/','/accounts/'+ACCOUNT+'/')) for p in calls))
    def test_foreign_account_causes_no_additional_reads(self):
        calls=[]
        def mock(token,path):
            calls.append(path);return 200,[{'name':ZONE,'id':'a'*32,'account':{'id':'b'*32}}]
        r=summarize('fake',mock)
        self.assertFalse(r['account_original_verified_from_zone'])
        self.assertEqual(len(calls),1)

if __name__=='__main__': unittest.main()