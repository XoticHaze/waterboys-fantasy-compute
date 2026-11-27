import test from 'node:test';
import assert from 'node:assert/strict';
import {FIXTURE_BLOB,FIXED_MODEL,runOneTurn,candidateSelector,admitProviderReply} from './one-turn.mjs';
const f={schema:'agent-fabric.j11.public-fictional.v1',tasks:[{id:'A',goal:'fictional goal',routes:[{id:'mailbox',record:{id:'A-new'}}]}]};
const identity={mission_id:'test-j11',fixture_blob:FIXTURE_BLOB};
const reserved={status:'reserved',dispatch:true,request:{attempt:'test-j11:1',task:'A',goal:'fictional goal',observations:[]}};
const good=(action={kind:'read',route:'mailbox'},status='candidate_unexecuted')=>({schema:'commandcenter.nvidia.j11_candidate_turn.v1',fixture_blob:FIXTURE_BLOB,task_id:'A',observed_routes:[],model:FIXED_MODEL,status,http_status:200,provider_attempt_upper_bound:1,prompt_tokens:100,completion_tokens:8,elapsed_ms:110,action,private_input_used:false,model_action_executed:false,production_admitted:false});
const record={calls:[],fake:{}};
function makeEnv({route=true,budget=true,reserve=reserved,reply=good(),throwService=false,commit='written'}={}){
  const events=[];
  const args={f,identity,now:1001,store:{},postTurnNow:async()=>1002,routeAdmitted:async()=>{events.push('route');return route},
    budgetAdmitted:async x=>{events.push('budget');assert.equal(x.max_calls,1);assert.equal(x.free_only,true);return budget},
    reserveTurn:async x=>{events.push('reserve');const allow=await x.admission();if(!allow)return {status:'route_held',dispatch:false};events.push('persist');return reserve},
    serviceTurn:async x=>{events.push('provider');assert.equal(x.selector.task_id,'A');if(throwService)throw Error('timeout');return reply},
    commitTurn:async x=>{events.push('commit');assert.deepEqual(x.action,reply?.action||{kind:'yield'});return {status:commit,summary:{accepted:1},blob_sha:'a'.repeat(40),commit_sha:'b'.repeat(40)}}};
  return {events,args};
}
test('an admitted turn reserves durably before one provider call then commits receipt',async()=>{const {events,args}=makeEnv();const r=await runOneTurn(args);assert.deepEqual(events,['reserve','route','budget','persist','provider','commit']);assert.equal(r.status,'checkpoint_committed');assert.equal(r.provider_calls,1);assert.equal(r.accepted_tasks,1);assert.equal(r.receipt.production_admitted,false);});
test('held route or account budget cannot invoke provider',async()=>{for(const o of [{route:false},{budget:false}]){const {events,args}=makeEnv(o);const r=await runOneTurn(args);assert.equal(r.dispatch,false);assert.equal(r.provider_calls,0);assert.equal(events.includes('provider'),false);}});
test('429/403 holds reserved attempt with no commit and no retry',async()=>{for(const status of ['rate_limited','provider_unavailable','transport_or_decode_failure']){const {events,args}=makeEnv({reply:good(null,status)});const r=await runOneTurn(args);assert.equal(r.stop_this_pass,true);assert.equal(events.includes('commit'),false);assert.equal(r.accepted_tasks,null)}});
test('transport uncertainty leaves CAS reservation and does not fake a terminal',async()=>{const {events,args}=makeEnv({throwService:true});const r=await runOneTurn(args);assert.equal(r.status,'provider_transport_indeterminate');assert.equal(r.provider_calls,null);assert.equal(events.includes('commit'),false);});
test('wrong task/model/provenance never yields accepted job',async()=>{for(const tamper of [{model:'evil/model'},{task_id:'B'},{fixture_blob:'0'.repeat(40)},{model_action_executed:true}]){const {events,args}=makeEnv({reply:{...good(),...tamper}});const r=await runOneTurn(args);assert.equal(r.status,'provider_result_untrusted_reconcile');assert.equal(events.includes('commit'),false);}});
test('selector is derived only from durable request and rejects unobserved routes',()=>{assert.deepEqual(candidateSelector(f,identity,reserved),{fixture_blob:FIXTURE_BLOB,task_id:'A',observed_routes:[]});assert.throws(()=>candidateSelector(f,identity,{...reserved,request:{...reserved.request,observations:[{route:'secret'}]}}));});
test('noncandidate cannot convey executable model action',()=>{assert.throws(()=>admitProviderReply(good({kind:'read',route:'mailbox'},'rate_limited'),{fixture_blob:FIXTURE_BLOB,task_id:'A',observed_routes:[]}));});
test('failed checkpoint readback cannot become accepted result',async()=>{const {args}=makeEnv({commit:'indeterminate_reconcile'});const r=await runOneTurn(args);assert.equal(r.accepted_tasks,null);assert.equal(r.receipt,null);});

test('definite 429 is acknowledged with a durable held receipt when owner binding exists',async()=>{
 const {events,args}=makeEnv({reply:good(null,'rate_limited')});
 args.holdProviderTurn=async ({reason,attempt})=>{events.push('hold');assert.equal(reason,'rate_limited');assert.equal(attempt,'test-j11:1');return {status:'provider_held',blob_sha:'a'.repeat(40),commit_sha:'b'.repeat(40)}};
 const r=await runOneTurn(args);assert.equal(r.status,'provider_held');assert.equal(r.provider_status,'rate_limited');assert.equal(r.accepted_tasks,null);assert.equal(r.stop_this_pass,true);assert.equal(r.checkpoint_blob_sha,'a'.repeat(40));assert.equal(events.includes('commit'),false);
});

test('post-provider clock failure cannot commit or hide an expired reservation',async()=>{
 const {args,events}=makeEnv();args.postTurnNow=async()=>1001;
 const r=await runOneTurn(args);assert.equal(r.status,'post_turn_clock_unavailable_reconcile');
 assert.equal(r.provider_calls,null);assert.equal(events.includes('commit'),false);
});
