// Durable controller seam for existing CommandCenter checkpoint ownership.
// No credentials, network transport, provider activation, or generic prompt proxy.
// The owner supplies fixed-path read/CAS, current trusted clock, and an admitted
// typed executor. This module never treats a review-workspace claim as execution authority.
import {newSession,nextTurn,acceptTurn,report} from "./session.mjs";
const SHA=/^[a-f0-9]{40}$/;
const ID=/^[a-zA-Z0-9_-]{1,80}$/;
function need(ok,why){if(!ok)throw Error(why);}
const eq=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
const clone=x=>JSON.parse(JSON.stringify(x));
const keys=(x,k)=>x&&typeof x==="object"&&!Array.isArray(x)&&Object.keys(x).sort().join(",")===k.split(",").sort().join(",");
export function makeCheckpoint(f,identity,now){
 need(keys(identity,"mission_id,fixture_blob,controller_blob,deadline,max_attempts")&&ID.test(identity.mission_id)&&SHA.test(identity.fixture_blob)&&SHA.test(identity.controller_blob),"identity");
 need(Number.isSafeInteger(now)&&Number.isSafeInteger(identity.deadline)&&identity.deadline>now&&identity.deadline-now<=18000&&Number.isSafeInteger(identity.max_attempts)&&identity.max_attempts>=1&&identity.max_attempts<=1000,"session_bounds");
 return {schema:"agent-fabric.j11.durable_checkpoint.v1",identity:clone(identity),state:newSession(f,identity.mission_id,identity.max_attempts,identity.deadline)};
}
export function verifyCheckpoint(f,d,identity){
 need(keys(d,"schema,identity,state")&&d.schema==="agent-fabric.j11.durable_checkpoint.v1"&&eq(d.identity,identity),"checkpoint_identity");
 const s=d.state;
 need(s?.schema==="agent-fabric.j11.checkpoint.v1"&&s.session_id===identity.mission_id&&s.deadline===identity.deadline&&s.max_attempts===identity.max_attempts&&Number.isSafeInteger(s.revision)&&s.revision>=0&&Number.isSafeInteger(s.reserved)&&s.reserved>=0&&s.reserved<=s.max_attempts&&Array.isArray(s.tasks)&&Array.isArray(s.events)&&typeof s.stopped==="boolean","checkpoint_shape");
 need(s.tasks.length===f.tasks.length&&s.tasks.every((t,i)=>t.id===f.tasks[i].id&&Number.isSafeInteger(t.visits)&&t.visits>=0&&Array.isArray(t.observations)),"task_identity");
 const ids=new Set(),open=new Map(),accepted=new Map();
 for(const e of s.events){
  need(e&&f.tasks.some(t=>t.id===e.task)&&typeof e.attempt==="string","event_identity");
  if(e.type==="RESERVED"){need(!ids.has(e.attempt)&&e.attempt===s.session_id+":"+(ids.size+1),"reservation_replay");ids.add(e.attempt);open.set(e.attempt,e.task);}
  else {need(open.get(e.attempt)===e.task,"terminal_without_reservation");open.delete(e.attempt);if(e.type==="ACCEPTED"){need(!accepted.has(e.task),"duplicate_accept");accepted.set(e.task,e.attempt);}}
 }
 need(ids.size===s.reserved&&s.tasks.reduce((n,t)=>n+t.visits,0)===s.reserved&&open.size===(s.pending?1:0),"reservation_count");
 if(s.pending)need(open.get(s.pending.id)===s.pending.task&&Number.isSafeInteger(s.pending.expires)&&s.pending.expires<=s.deadline,"pending_identity");
 for(let i=0;i<s.tasks.length;i++){
  const t=s.tasks[i],source=f.tasks[i],observed=new Set();
  for(const o of t.observations){const r=source.routes.find(r=>r.id===o.route);need(r&&!observed.has(o.route)&&eq(o.record,r.record),"observation_identity");observed.add(o.route);}
  if(t.accepted)need(accepted.get(t.id)===t.accepted.attempt&&t.accepted.state===source.gold.state&&eq([...t.accepted.evidence].sort(),[...source.gold.evidence].sort())&&t.accepted.evidence.every(id=>t.observations.some(o=>o.record.id===id)),"accepted_evidence");
  else need(!accepted.has(t.id),"missing_accepted_result");
 }
 return d;
}
async function readExact(f,identity,store){
 const raw=await store.read();
 need(raw&&SHA.test(raw.blob_sha),"checkpoint_missing");
 verifyCheckpoint(f,raw.document,identity);
 return raw;
}
async function persist(f,identity,store,before,document){
 verifyCheckpoint(f,document,identity);
 let result;
 try{result=await store.compareAndSet(before.blob_sha,document);}catch{return {status:"indeterminate_reconcile",dispatch:false};}
 if(result?.status==="conflict")return {status:"revision_conflict",dispatch:false};
 if(result?.status!=="written"||!SHA.test(result.blob_sha)||!SHA.test(result.commit_sha))return {status:"indeterminate_reconcile",dispatch:false};
 let read;
 try{read=await readExact(f,identity,store);}catch{return {status:"indeterminate_reconcile",dispatch:false};}
 if(read.blob_sha!==result.blob_sha||!eq(read.document,document))return {status:"indeterminate_reconcile",dispatch:false};
 return {status:"written",blob_sha:result.blob_sha,commit_sha:result.commit_sha,dispatch:false};
}
// Reserve only after route admission is independently verified by the owning
// control plane. admission is a trusted host interface, never model input.
export async function reserveTurn({f,identity,store,now,leaseSeconds=90,admission}){
 need(typeof admission==="function","trusted_admission_required");
 const grant=await admission(identity,now);
 if(grant!==true)return {status:"route_held",dispatch:false};
 const before=await readExact(f,identity,store);
 let next;
 try{next=nextTurn(f,before.document.state,now,leaseSeconds);}catch(e){if(e.message==="active lease")return {status:"lease_active",dispatch:false};throw e;}
 if(eq(next.state,before.document.state))return {status:report(next.state).complete?"complete":"held_or_exhausted",dispatch:false};
 const saved=await persist(f,identity,store,before,{...before.document,state:next.state});
 if(saved.status!=="written"||!next.request)return saved;
 return {...saved,status:"reserved",dispatch:true,request:next.request};
}
export async function commitTurn({f,identity,store,attempt,action,now}){
 const before=await readExact(f,identity,store);
 const prior=before.document.state.events.find(e=>e.attempt===attempt&&e.type!=="RESERVED");
 if(prior)return {status:"already_terminal",dispatch:false,event:clone(prior)};
 const state=acceptTurn(f,before.document.state,attempt,action,now);
 const saved=await persist(f,identity,store,before,{...before.document,state});
 return {...saved,summary:saved.status==="written"?report(state):null};
}
export async function observeSession({f,identity,store,now}){
 const {blob_sha,document}=await readExact(f,identity,store);
 const s=document.state;
 return {...report(s),schema:"agent-fabric.j11.session_observation.v1",mission_id:identity.mission_id,blob_sha,revision:s.revision,deadline:s.deadline,lease_active:!!s.pending&&now<s.pending.expires,expired:now>=s.deadline,remaining_attempts:s.max_attempts-s.reserved,dispatch_authority:false};
}
