#!/usr/bin/env python3
"""Small, GET-only original-account Cloudflare readback for IncomeEngine Studio.

Public code may name the requested DNS hostname; it must never receive or print
Studio GLBs, private source, user email/AUD, secret values, or other tenant zones.
This is a preflight, NOT Worker/DNS/Access admission or a deployment command.
"""
import json
import os
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

ACCOUNT = 'ce43cd7b917d98a4bb4866d30eed99c0'
ZONE = 'lifelatelycounseling.com'
STUDIO = 'studio.' + ZONE
PRESERVE = 'ha.' + ZONE
OWNER_POLICY_NAME = 'CC Factory Owner Only'
API = 'https://api.cloudflare.com/client/v4'


def get_fixed(token, path):
    if not path.startswith(('/zones?', f'/zones/', f'/accounts/{ACCOUNT}/')):
        raise ValueError('read path not admitted')
    if '/../' in path or not path.isascii():
        raise ValueError('invalid path')
    req = Request(API + path, method='GET', headers={
        'Authorization': 'Bearer ' + token,
        'Accept': 'application/json',
        'User-Agent': 'cc-incomeengine-studio-zone-preflight-v1',
    })
    try:
        with urlopen(req, timeout=12) as res:
            status, body = res.status, res.read(120000)
    except HTTPError as e:
        return e.code, None
    except (URLError, TimeoutError):
        return 'TRANSPORT_UNAVAILABLE', None
    try:
        parsed = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return status, None
    if status != 200 or parsed.get('success') is not True:
        return status, None
    return status, parsed.get('result')


def summarize(token, get=get_fixed):
    receipt = {
        'schema':'commandcenter.incomeengine.studio_cloudflare_readonly.v1',
        'scope':'TARGET_ORIGINAL_ACCOUNT_ONLY',
        'target':'incomeengine_studio',
        'account_original_verified_from_zone':False,
        'zone_visible_in_credential':False,
        'zone_get_http':None,
        'studio_dns_state':'UNKNOWN',
        'studio_dns_get_http':None,
        'ha_dns_mutated':False,
        'access_application_state':'UNKNOWN',
        'access_app_get_http':None,
        'reusable_owner_policy_state':'UNKNOWN',
        'reusable_policy_get_http':None,
        'credential_values_exported':False,
        'identities_or_jwt_audience_exported':False,
        'cloudflare_mutations':0,
        'production_deployment_admitted':False,
        'hosted_acceptance':False,
    }
    status, zones = get(token, '/zones?' + urlencode({'name':ZONE,'per_page':50,'page':1}))
    receipt['zone_get_http'] = status
    if status != 200 or not isinstance(zones,list):
        return receipt
    matches=[z for z in zones if isinstance(z,dict) and z.get('name')==ZONE]
    if len(matches)!=1:
        receipt['zone_visible_in_credential']=False
        return receipt
    z=matches[0]
    zid=str(z.get('id') or '')
    import re
    if not re.fullmatch('[0-9a-f]{32}',zid):
        return receipt
    receipt['zone_visible_in_credential']=True
    receipt['account_original_verified_from_zone']=(z.get('account') or {}).get('id')==ACCOUNT
    if not receipt['account_original_verified_from_zone']:
        return receipt
    status, records=get(token,f'/zones/{zid}/dns_records?'+urlencode({'name':STUDIO,'per_page':100,'page':1}))
    receipt['studio_dns_get_http']=status
    if status==200 and isinstance(records,list):
        exact=[x for x in records if isinstance(x,dict) and x.get('name')==STUDIO]
        receipt['studio_dns_state']='RECORD_PRESENT' if exact else 'NO_RECORD_IN_VISIBLE_ZONE'
    status, apps=get(token,f'/accounts/{ACCOUNT}/access/apps?per_page=100&page=1')
    receipt['access_app_get_http']=status
    if status==200 and isinstance(apps,list):
        # Cloudflare apps may return domains in a list, or one fixed domain.
        exact=[x for x in apps if isinstance(x,dict) and
               (STUDIO==x.get('domain') or STUDIO in (x.get('self_hosted_domains') or []))]
        receipt['access_application_state']='EXACT_HOST_APP_PRESENT' if exact else 'NO_EXACT_APP_IN_FIRST_PAGE'
    status, policy=get(token,f'/accounts/{ACCOUNT}/access/policies?per_page=100&page=1')
    receipt['reusable_policy_get_http']=status
    if status==200 and isinstance(policy,list):
        exact=[x for x in policy if isinstance(x,dict) and x.get('name')==OWNER_POLICY_NAME]
        receipt['reusable_owner_policy_state']='EXACT_POLICY_LISTED' if len(exact)==1 else 'NOT_LISTED_ON_FIRST_PAGE'
    return receipt


def main():
    if os.getenv('CLOUDFLARE_ACCOUNT_ID')!=ACCOUNT:
        raise SystemExit('INCOMEENGINE_ZONE_READONLY_WRONG_ACCOUNT')
    token=os.getenv('CLOUDFLARE_API_TOKEN','')
    if len(token)<20:
        raise SystemExit('INCOMEENGINE_ZONE_READONLY_CREDENTIAL_NOT_PRESENT')
    receipt=summarize(token)
    print(json.dumps(receipt,sort_keys=True))
    print('INCOMEENGINE_STUDIO_CLOUDFLARE_GET_ONLY=PASS')
    return 0

if __name__=='__main__':
    raise SystemExit(main())