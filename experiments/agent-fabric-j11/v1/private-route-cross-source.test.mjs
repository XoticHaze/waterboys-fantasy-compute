// Cross-repository J11 fictional bound-call contract, offline only.
// Imported Worker code is pinned to the exact isolated V2-derived source commit.
// All auth, provider fetches, CAS writes and time are synthetic mocks.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {makeCheckpoint,reserveTurn,commitTurn,holdProviderTurn,observeSession} from './durable-session.mjs';
import {runOneTurn,FIXTURE_BLOB} from './one-turn.mjs';
import {createJ11Caller} from '../../../j11-worker-source/cloudflare/shared-nvidia-inference/local-probe/src/j11_caller.js';
import {handleJ11PrivateRoute} from '../../../j11-worker-source/cloudflare/shared-nvidia-inference/src/j11_private_route.js';
import {admitSelector,runFixedJ11Turn} from '../../../j11-worker-source/cloudflare/shared-nvidia-inference/src/j11_fixed_turn.js';
const fixture=JSON.parse(await readFile(new URL('./fixture.json',import.meta.url),'utf8'));
const identity={mission_id:'offline-j11-cross-source',fixture_blob:FIXTURE_BLOB};
const task=fixture.tasks.find(t=>t.id==='A');
const reserved={status:'reserved',dispatch:true,request:{attempt:'offline-j11-cross-source:1',task:'A',goal:task.goal,observations:[]}};
function harness({budget=true,providerStatus=200}={}){
 let providerCalls=0,commits=0,bindingCalls=0;
 const caller=createJ11Caller();
 const cloud={CC_NVIDIA_DIAGNOSTIC_ENABLED:'1',NVIDIA_API_KEY:{get:async()=> 'fake-j11-secret-not-exported'}};
 const privateServices={admitSelector,runFixedJ11Turn,pacedProviderFetch:async(u,opts)=>{
    providerCalls++;
    assert.equal(u,'https://integrate.api.nvidia.com/v1/chat/completions');
    assert.equal(opts.headers.Authorization,'Bearer fake-j11-secret-not-exported');
    assert.equal(opts.redirect,'manual');
    const b=JSON.parse(opts.body);
    assert.equal(b.model,'poolside/laguna-xs-2.1');
    assert.equal(b.max_tokens,512);
    assert.equal(JSON.stringify(b).includes('gold'),false);
    if(providerStatus!==200)return new Response(null,{status:providerStatus});
    return Response.json({choices:[{message:{content:'{"kind":"read","route":"mailbox"}'}}],
       usage:{prompt_tokens:68,completion_tokens:8}},{status:200});
 }};
 const local={NVIDIA_SERVICE:{fetch:async req=>{
   bindingCalls++;
   assert.equal(req.headers.get('content-length'),null);
   return handleJ11PrivateRoute(req,cloud,privateServices);
 }}};
 const serviceTurn=async ({selector})=>{
   const body=JSON.stringify(selector);
   const request=new Request('http://127.0.0.1:8787/j11-once',
       {method:'POST',headers:{'content-type':'application/json'},body});
   assert.equal(request.headers.get('content-length'),null);
   const response=await caller.fetch(request,local);
   return response.json();
 };
 const args={f:fixture,identity,store:{},now:1001,postTurnNow:async()=>1002,
   routeAdmitted:async()=>true,budgetAdmitted:async()=>budget,
   reserveTurn:async ({admission})=>await admission()?reserved:{status:'route_held',dispatch:false},
   commitTurn:async ({action})=>{commits++;assert.deepEqual(action,{kind:'read',route:'mailbox'});
      return {status:'written',summary:{accepted:0},blob_sha:'a'.repeat(40),commit_sha:'b'.repeat(40)};
   },serviceTurn};
 return {args,caller,local,counters:()=>({providerCalls,commits,bindingCalls})};
}
test('headerless Service Binding -> fictional model -> controller receipt, exactly once',async()=>{
 const x=harness(),r=await runOneTurn(x.args);
 assert.equal(r.status,'checkpoint_committed');
 assert.equal(r.provider_status,'candidate_unexecuted');
 assert.equal(r.provider_calls,1);
 assert.equal(r.accepted_tasks,0);
 assert.equal(r.receipt.production_admitted,false);
 assert.deepEqual(x.counters(),{providerCalls:1,commits:1,bindingCalls:1});
 const body=JSON.stringify({fixture_blob:FIXTURE_BLOB,task_id:'A',observed_routes:[]});
 const replay=new Request('http://127.0.0.1:8787/j11-once',{method:'POST',headers:{'content-type':'application/json'},body});
 assert.equal((await x.caller.fetch(replay,x.local)).status,409);
 assert.deepEqual(x.counters(),{providerCalls:1,commits:1,bindingCalls:1});
 assert.equal(JSON.stringify(r).includes('fake-j11-secret-not-exported'),false);
});
test('held shared budget means zero local, bound or provider calls',async()=>{
 const x=harness({budget:false}),r=await runOneTurn(x.args);
 assert.equal(r.status,'account_budget_held');
 assert.equal(r.provider_calls,0);
 assert.deepEqual(x.counters(),{providerCalls:0,commits:0,bindingCalls:0});
});
test('upstream 429 yields held non-replayable turn and zero accepted work',async()=>{
 const x=harness({providerStatus:429}),r=await runOneTurn(x.args);
 assert.equal(r.status,'rate_limited');
 assert.equal(r.provider_calls,1);
 assert.equal(r.stop_this_pass,true);
 assert.equal(r.accepted_tasks,null);
 assert.equal(r.receipt,null);
 assert.deepEqual(x.counters(),{providerCalls:1,commits:0,bindingCalls:1});
});

const cFixture={...fixture,tasks:[fixture.tasks[0]]};
const cIdentity={mission_id:'cross-source-real-cas',fixture_blob:FIXTURE_BLOB,
  controller_blob:'2d86d46e91c1fb13f2d7e6db708f2866e8de64b2',deadline:1400,max_attempts:3};
const clone=x=>JSON.parse(JSON.stringify(x));
const gitSHA=x=>{const bytes=Buffer.from(JSON.stringify(x));return createHash('sha1').update('blob '+bytes.length+'\\0').update(bytes).digest('hex')};
function casStore(initial){
 let value=clone(initial),sha=gitSHA(value);
 return {read:async()=>({blob_sha:sha,document:clone(value)}),
   compareAndSet:async(old,next)=>{
     if(old!==sha)return {status:'conflict'};
     value=clone(next);sha=gitSHA(value);
     return {status:'written',blob_sha:sha,commit_sha:'b'.repeat(40)};
   }};
}
function realCASArgs({providerStatus=200}={}){
 const mocked=harness({providerStatus});
 const store=casStore(makeCheckpoint(cFixture,cIdentity,1000));
 return {mocked,store,args:{...mocked.args,f:cFixture,identity:cIdentity,store,
   now:1001,postTurnNow:async()=>1002,
   reserveTurn,commitTurn,holdProviderTurn,
   budgetAdmitted:async()=>true,routeAdmitted:async()=>true}};
}
test('cross-source J11 read action is persisted by actual durable CAS and independent readback',async()=>{
 const x=realCASArgs();
 const r=await runOneTurn(x.args);
 assert.equal(r.status,'checkpoint_committed');
 assert.equal(r.provider_calls,1);
 assert.equal(r.accepted_tasks,0);
 const obs=await observeSession({f:cFixture,identity:cIdentity,store:x.store,now:1003});
 assert.equal(obs.reserved_attempts,1);
 assert.equal(obs.accepted,0);
 assert.equal(obs.dispatch_authority,false);
 const state=(await x.store.read()).document.state;
 assert.equal(state.tasks[0].observations[0].record.id,'A-new');
 assert.equal(state.events.at(-1).type,'READ');
 assert.equal(x.mocked.counters().providerCalls,1);
});
test('cross-source J11 429 persists terminal provider hold through actual durable CAS, no replay',async()=>{
 const x=realCASArgs({providerStatus:429});
 const r=await runOneTurn(x.args);
 assert.equal(r.status,'provider_held');
 assert.equal(r.stop_this_pass,true);
 assert.equal(r.accepted_tasks,null);
 const obs=await observeSession({f:cFixture,identity:cIdentity,store:x.store,now:1003});
 assert.equal(obs.reserved_attempts,1);
 assert.equal(obs.accepted,0);
 const state=(await x.store.read()).document.state;
 assert.equal(state.stopped,true);
 assert.equal(state.events.at(-1).type,'PROVIDER_HELD');
 assert.equal(state.events.at(-1).reason,'rate_limited');
 assert.equal(x.mocked.counters().providerCalls,1);
 assert.equal(x.mocked.counters().bindingCalls,1);
});
