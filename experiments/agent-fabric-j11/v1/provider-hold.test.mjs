import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {makeCheckpoint,reserveTurn,holdProviderTurn,observeSession} from './durable-session.mjs';

const f={schema:'agent-fabric.j11.public-fictional.v1',as_of:1000,freshness_seconds:60,tasks:[{id:'A',goal:'fictional heartbeat',routes:[{id:'mailbox',record:{id:'A-new',target:'A',ts:990}}],gold:{state:'active',evidence:['A-new']}}]};
const identity={mission_id:'synthetic-hold',fixture_blob:'a459d065e6188ea8b01ab1a5b2c721789587982d',controller_blob:'2d86d46e91c1fb13f2d7e6db708f2866e8de64b2',deadline:1400,max_attempts:5};
const copy=x=>JSON.parse(JSON.stringify(x));
const gitsha=x=>{const b=Buffer.from(JSON.stringify(x));return createHash('sha1').update('blob '+b.length+'\0').update(b).digest('hex')};
function store(initial,{conflict=false}={}){
  let current=copy(initial),sha=gitsha(current);
  return {read:async()=>({blob_sha:sha,document:copy(current)}),compareAndSet:async(old,next)=>{
     if(conflict||old!==sha)return {status:'conflict'};
     current=copy(next);sha=gitsha(current);
     return {status:'written',blob_sha:sha,commit_sha:'b'.repeat(40)};
   }};
}
test('provider 429 persists one stopped mission, no false accepted task or repeat turn',async()=>{
 const s=store(makeCheckpoint(f,identity,1000));
 const a=await reserveTurn({f,identity,store:s,now:1001,admission:async()=>true});
 assert.equal(a.status,'reserved');assert.equal(a.dispatch,true);
 const h=await holdProviderTurn({f,identity,store:s,attempt:a.request.attempt,reason:'rate_limited',now:1002});
 assert.equal(h.status,'provider_held');assert.equal(h.dispatch,false);assert.equal(h.model_work_accepted,false);
 const observed=await observeSession({f,identity,store:s,now:1003});
 assert.equal(observed.accepted,0);assert.equal(observed.reserved_attempts,1);
 assert.equal(observed.dispatch_authority,false);
 const next=await reserveTurn({f,identity,store:s,now:1004,admission:async()=>true});
 assert.equal(next.dispatch,false);assert.equal(next.status,'held_or_exhausted');
 await assert.rejects(()=>holdProviderTurn({f,identity,store:s,attempt:a.request.attempt,reason:'rate_limited',now:1005}));
});
test('held provider reason must be an exact admitted enum',async()=>{
 const s=store(makeCheckpoint(f,identity,1000));const a=await reserveTurn({f,identity,store:s,now:1001,admission:async()=>true});
 await assert.rejects(()=>holdProviderTurn({f,identity,store:s,attempt:a.request.attempt,reason:'approved',now:1002}));
 const h=await holdProviderTurn({f,identity,store:s,attempt:a.request.attempt,reason:'provider_unavailable',now:1002});
 assert.equal(h.status,'provider_held');
});
test('CAS conflict cannot claim terminal provider hold',async()=>{
 const s=store(makeCheckpoint(f,identity,1000));const a=await reserveTurn({f,identity,store:s,now:1001,admission:async()=>true});
 const raw=await s.read(),failing={read:s.read,compareAndSet:async()=>({status:'conflict'})};
 const h=await holdProviderTurn({f,identity,store:failing,attempt:a.request.attempt,reason:'rate_limited',now:1002});
 assert.equal(h.status,'hold_commit_indeterminate');assert.equal(h.dispatch,false);
 assert.deepEqual((await s.read()).document,raw.document);
});
