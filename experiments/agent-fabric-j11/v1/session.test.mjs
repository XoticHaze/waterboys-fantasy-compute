import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {newSession,nextTurn,acceptTurn,report} from "./session.mjs";
const f=JSON.parse(readFileSync(new URL("./fixture.json",import.meta.url),"utf8"));
const roundtrip=s=>JSON.parse(JSON.stringify(s));
test("all seven dispositions, interrupted after two accepted tasks",()=>{
 let s=newSession(f,"control",40,5000),now=1001,interrupted=false;
 while(!report(s).complete){
  const {state,request}=nextTurn(f,s,now);s=state;assert.ok(request);
  assert.equal(Object.hasOwn(request,"gold"),false);
  if(report(s).accepted===2&&!interrupted){
   const accepted=s.tasks.filter(x=>x.accepted);
   s=roundtrip(s);now+=31;interrupted=true;
   assert.deepEqual(s.tasks.filter(x=>x.accepted),accepted);continue;
  }
  const t=f.tasks.find(x=>x.id===request.task);
  const route=t.routes.find(r=>t.gold.evidence.includes(r.record.id)&&!request.observations.some(o=>o.route===r.id));
  const act=route?{kind:"read",route:route.id}:{kind:"submit",state:t.gold.state,evidence:t.gold.evidence};
  s=acceptTurn(f,s,request.attempt,act,now+1);now+=2;
 }
 assert.equal(report(s).accepted,7);assert.equal(report(s).uncertain_attempts,1);
 assert.equal(report(s).boundary_violations,0);assert.equal(report(s).model_calls,0);
});
test("wrong route stops mission; stale reply cannot be replayed",()=>{
 const a=nextTurn(f,newSession(f,"boundary",5,5000),1001);
 const s=acceptTurn(f,a.state,a.request.attempt,{kind:"read",route:"arbitrary"},1002);
 assert.equal(report(s).boundary_violations,1);
 assert.equal(nextTurn(f,s,1003).request,null);
 assert.throws(()=>acceptTurn(f,s,a.request.attempt,{kind:"yield"},1003));
});
test("expired unknown attempt conservatively consumes budget",()=>{
 const a=nextTurn(f,newSession(f,"budget",1,5000),1001);
 assert.throws(()=>nextTurn(f,a.state,1002));
 const b=nextTurn(f,roundtrip(a.state),1032);
 assert.equal(b.request,null);assert.equal(report(b.state).uncertain_attempts,1);
 assert.equal(b.state.reserved,1);
});
test("false completion rejected, other work selected",()=>{
 const a=nextTurn(f,newSession(f,"false",10,5000),1001);
 const s=acceptTurn(f,a.state,a.request.attempt,{kind:"submit",state:"active",evidence:["A-new"]},1002);
 assert.equal(report(s).accepted,0);assert.equal(report(s).unbound_evidence,1);
 const b=nextTurn(f,s,1003);assert.notEqual(b.request.task,a.request.task);
});
test("session deadline cannot be extended by a turn",()=>{
 const a=nextTurn(f,newSession(f,"deadline",10,1002),1001,30);
 assert.equal(a.state.pending.expires,1002);
 assert.equal(nextTurn(f,a.state,1002).request,null);
});
