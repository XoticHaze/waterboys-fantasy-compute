#!/usr/bin/env python3
"""Fictional UI evidence-state artifact: genuine model draft -> independent tests -> feedback -> revision.

The model's source is NEVER exec'd, eval'd, compiled or imported. The existing
bounded AST interpreter evaluates its pure expression subset. Public fictional
inputs only. A code artifact is not an authenticated command or a broker action.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from nvidia_fixed_code_repair_work import evaluate, CodeRejected

URL = 'http://127.0.0.1:8787/evidence-status-step'
SCHEMA = 'commandcenter.public_synthetic_evidence_status_step.v1'
MODEL = 'poolside/laguna-xs-2.1'
ARGS = ('receipt', 'verified', 'queue', 'age_s', 'ttl_s', 'protected')
# Fixed, public-fictional, intentionally contradictory status inputs; source
# truth is the signed receipt, not the delayed UI queue projection.
SEED = (
    (1,1,1,10,120,0),(1,1,3,10,120,1),(2,1,1,10,120,1),
    (2,1,2,120,120,0),(1,1,2,121,120,0),(0,0,2,121,120,1),
    (1,0,1,10,120,0),(2,0,3,10,120,1),(0,1,0,10,120,0),
    (0,0,1,5,120,0),(0,0,2,10,120,1),(0,0,3,10,120,0),
    (0,0,4,10,120,0),(0,0,4,10,120,1),(0,0,0,10,120,1),
    (-1,0,1,10,120,0),(3,1,0,10,120,0),(0,-1,2,10,120,0),
    (0,2,1,10,120,0),(0,0,5,10,120,0),(0,0,-1,10,120,0),
    (0,0,2,-1,120,0),(0,0,2,0,0,0),(0,0,1,10,-1,0),
    (0,0,1,10,120,2),(0,0,1,10,120,-1),
)
# Independent changed-fact holdouts span signed-terminal conflict, cache expiry,
# missing provenance and protected requests. Not shown to the model at draft time.
HOLDOUT = tuple(
    (i%3, (i//3)%2, (i*5)%5, (i*37)%250, 30+(i*19)%180, (i//7)%2)
    for i in range(74)
)
CASES = SEED + HOLDOUT

def reference(v):
    if not isinstance(v,tuple) or len(v)!=6 or any(type(x) is not int for x in v):
        raise ValueError('INVALID_FIXED_CASE')
    receipt,verified,queue,age,ttl,protected=v
    if receipt not in (0,1,2) or verified not in (0,1) or queue not in (0,1,2,3,4) or protected not in (0,1) or age<0 or ttl<=0:
        return -1 # Invalid observation, never a real status
    if receipt==0 and verified==1:return -1 # Contradictory provenance
    if receipt!=0 and verified==0:return 6 # Receipt exists but cannot be trusted
    if age>ttl:return 2 # Historical only, never a current success or alert
    if receipt==1 and verified==1:return 3 # Final success wins over stale queue projections
    if receipt==2 and verified==1:return 4 # Verified failure, not inferred failure
    if protected and queue!=0:return 5 # No protected action from queue projections
    if queue in (1,2):return 1 # Pending/running, not completed
    if queue in (3,4):return 7 # Failed/duplicate unverified queue requires investigation
    return 0 # No current verified work or concern

def score(source):
    pairs=tuple((v,reference(v)) for v in CASES)
    try:
        out=evaluate(source,function_name='evidence_state',args=ARGS,cases=pairs,max_ast_nodes=160,max_local_names=5)
    except (CodeRejected,ArithmeticError,TypeError,ValueError,OverflowError):
        return {'passed':0,'total':len(pairs),'failed_case_indices':list(range(len(pairs))),'source_ast_admitted':False}
    return {**out,'source_ast_admitted':True}

def feedback(scored):
    if scored['passed']==scored['total']:return []
    # A deterministic model receives at most three *verified* failing examples.
    # No arbitrary caller-produced expected answers, secrets or private data.
    return [{'input':list(CASES[i]),'expected':reference(CASES[i])}
            for i in scored['failed_case_indices'][:3]]

def classify(first,revised):
    a,b=score(first),score(revised) if revised is not None else None
    if a['passed']==len(CASES):result='FIRST_DRAFT_PASSED_NO_CORRECTION'
    elif b is None:result='REVISION_UNAVAILABLE'
    else:
        old=set(a['failed_case_indices']);new=set(b['failed_case_indices'])
        if not new and old:result='CORRECTED_ALL_HOLDOUTS'
        elif old-new and not new-old:result='PARTIAL_IMPROVEMENT'
        elif new-old:result='REGRESSED_REJECTED'
        else:result='NO_GAIN'
    return {'baseline':a,'revised':b,'outcome':result,
            'newly_correct_count':len(set(a['failed_case_indices'])-set(b['failed_case_indices'])) if b else 0,
            'regressions_count':len(set(b['failed_case_indices'])-set(a['failed_case_indices'])) if b else 0,
            'same_source':revised==first if revised is not None else None}

def validate_reply(doc,stage):
    if not isinstance(doc,dict) or any(doc.get(k)!=v for k,v in {
        'schema':SCHEMA,'stage':stage,'model':MODEL,'provider_calls':1,
        'private_input_used':False,'model_code_executed':False,
        'commands_executed':False,'production_admitted':False}.items()):
        raise ValueError('UNTRUSTED_EVIDENCE_STATUS_RECEIPT')
    if doc.get('status')!='candidate_unexecuted' or doc.get('http_status')!=200:
        raise RuntimeError('PROVIDER_CANDIDATE_UNAVAILABLE')
    source=doc.get('source')
    if not isinstance(source,str) or not source.startswith('def evidence_state('+', '.join(ARGS)+'):\n') or not 75<=len(source)<=1051:
        raise ValueError('EVIDENCE_STATUS_SOURCE_SHAPE_REJECTED')
    return source

def call(payload):
    raw=json.dumps(payload,separators=(',',':')).encode('utf-8')
    req=Request(URL,data=raw,headers={'Content-Type':'application/json','Content-Length':str(len(raw))},method='POST')
    try:
        with urlopen(req,timeout=110) as resp:answer=resp.read(12000)
    except HTTPError as err:answer=err.read(12000)
    except (OSError,URLError,TimeoutError) as err:raise RuntimeError('PRIVATE_BOUND_PROVIDER_UNAVAILABLE') from err
    try:out=json.loads(answer)
    except ValueError as err:raise RuntimeError('INVALID_BOUND_REPLY') from err
    return validate_reply(out,payload['stage'])

def persist(first,revised,result):
    root=Path('artifacts/nvidia-evidence-status')
    root.mkdir(parents=True,exist_ok=True)
    (root/'baseline_model.py').write_text(first,encoding='utf-8')
    if revised is not None:(root/'revised_model.py').write_text(revised,encoding='utf-8')
    record={'schema':'commandcenter.public_synthetic_evidence_status_review.v1',
        'task':'fictional_readonly_ui_evidence_state', 'model':MODEL,'provider_requests':1+(revised is not None),
        'workflow_run_id':os.environ.get('GITHUB_RUN_ID'), 'controller_sha':os.environ.get('GITHUB_SHA'),
        'source_sha_baseline':hashlib.sha256(first.encode()).hexdigest(),
        'source_sha_revised':hashlib.sha256(revised.encode()).hexdigest() if revised is not None else None,
        'fictional_only':True,'private_input_used':False,'model_code_executed':False,
        'commands_executed':False,'production_admitted':False,**result}
    (root/'evaluation.json').write_text(json.dumps(record,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    return record

def main():
    first=call({'stage':0})
    a=score(first)
    print('EVIDENCE_STATUS_BASELINE='+str(a['passed'])+'/'+str(a['total']),flush=True)
    second=call({'stage':1,'source':first,'failed_examples':feedback(a)}) if a['passed']!=a['total'] else None
    result=persist(first,second,classify(first,second))
    print('EVIDENCE_STATUS_REVIEW='+json.dumps({'outcome':result['outcome'],
        'newly_correct_count':result['newly_correct_count'],
        'regressions_count':result['regressions_count'],
        'provider_requests':result['provider_requests'],
        'model_code_executed':False},sort_keys=True),flush=True)

if __name__=='__main__':main()
