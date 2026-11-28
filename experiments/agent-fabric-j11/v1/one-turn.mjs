// Existing CommandCenter J11 durable checkpoint -> exact NVIDIA Service Binding
// adapter. This is an orchestration seam, NOT an admission or credential issuer.
// One retained reservation and at most one provider request; budget, route and
// source/version identity must be admitted by an external trusted owner.
export const FIXTURE_BLOB='a459d065e6188ea8b01ab1a5b2c721789587982d';
export const FIXED_MODEL='poolside/laguna-xs-2.1';
const STATUS=new Set(['candidate_unexecuted','format_or_boundary_rejected',
  'rate_limited','provider_unavailable','transport_or_decode_failure']);
const FAIL_CLOSED=new Set(['rate_limited','provider_unavailable','transport_or_decode_failure']);
const eq=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
const integer=(v,max)=>Number.isInteger(v)&&v>=0&&v<=max;
function need(v,m){if(!v)throw Error(m);}
export function candidateSelector(f,identity,reserved){
  need(f?.schema==='agent-fabric.j11.public-fictional.v1'&&identity?.fixture_blob===FIXTURE_BLOB,
    'untrusted_fixture_identity');
  need(reserved?.status==='reserved'&&reserved.dispatch===true&&
    typeof reserved.request?.attempt==='string'&&
    /^[A-G]$/.test(reserved.request.task)&&
    Array.isArray(reserved.request.observations), 'untrusted_reservation');
  const source=f.tasks?.find(t=>t.id===reserved.request.task);
  need(source&&source.goal===reserved.request.goal,
    'goal_mismatch');
  const observedRoutes=reserved.request.observations.map(x=>x.route);
  need(observedRoutes.length<=source.routes.length &&
    new Set(observedRoutes).size===observedRoutes.length &&
    observedRoutes.every(id=>source.routes.some(r=>r.id===id)),
    'observed_route_mismatch');
  return {fixture_blob:FIXTURE_BLOB,task_id:source.id,observed_routes:observedRoutes};
}
const APPROVED_STATES=new Set(['active','stale_degraded','guest_independent_rescue_active','unhealthy','unknown']);
function verifyCandidateAction(action,selector,fixture){
  const task=fixture?.schema==='agent-fabric.j11.public-fictional.v1'
    ?fixture.tasks?.find(t=>t.id===selector.task_id):null;
  need(task&&Array.isArray(task.routes),'candidate_fixture_missing');
  const fields=Object.keys(action).sort().join(',');
  if(fields==='kind'&&action.kind==='yield')return;
  if(fields==='kind,route'&&action.kind==='read'&&
     typeof action.route==='string'&&
     task.routes.some(r=>r.id===action.route)&&
     !selector.observed_routes.includes(action.route))return;
  if(fields==='evidence,kind,state'&&action.kind==='submit'&&
     APPROVED_STATES.has(action.state)&&Array.isArray(action.evidence)&&
     action.evidence.length>=1&&action.evidence.length<=3&&
     new Set(action.evidence).size===action.evidence.length&&
     action.evidence.every(id=>typeof id==='string'&&
       task.routes.some(r=>selector.observed_routes.includes(r.id)&&r.record.id===id)))return;
  throw Error('candidate_action_not_observed_or_not_allowed');
}

export function admitProviderReply(reply,selector,fixture){
  // The private inference Worker has already constrained model output to a
  // fixed action. This consumer still validates exact provenance and safe flags.
  need(reply&&typeof reply==='object'&&!Array.isArray(reply)&&
    reply.schema==='commandcenter.nvidia.j11_candidate_turn.v1'&&
    reply.fixture_blob===FIXTURE_BLOB&&reply.task_id===selector.task_id&&
    eq(reply.observed_routes,selector.observed_routes)&&
    reply.model===FIXED_MODEL&&STATUS.has(reply.status)&&
    reply.private_input_used===false&&reply.model_action_executed===false&&
    reply.production_admitted===false&&reply.provider_attempt_upper_bound===1&&
    integer(reply.elapsed_ms,120000)&&
    (reply.http_status===null||(Number.isInteger(reply.http_status)&&reply.http_status>=100&&reply.http_status<=599))&&
    (reply.prompt_tokens===null||integer(reply.prompt_tokens,1000000))&&
    (reply.completion_tokens===null||integer(reply.completion_tokens,1000000)),
    'untrusted_provider_envelope');
  need((['candidate_unexecuted','format_or_boundary_rejected'].includes(reply.status) && reply.http_status===200) ||
    (reply.status==='rate_limited'&&reply.http_status===429) ||
    (reply.status==='provider_unavailable'&&reply.http_status!==200&&reply.http_status!==429) ||
    (reply.status==='transport_or_decode_failure'&&[null,200].includes(reply.http_status)),
    'status_http_mismatch');
  if(reply.status!=='candidate_unexecuted')need(reply.action===null,'noncandidate_action_not_allowed');
  else {
    const action=reply.action;
    need(action&&typeof action==='object'&&!Array.isArray(action),
      'candidate_missing');
    verifyCandidateAction(action,selector,fixture);
  }
  return reply;
}
export async function runOneTurn({f,identity,store,now,leaseSeconds=90,
   routeAdmitted,budgetAdmitted,serviceTurn,reserveTurn,commitTurn,holdProviderTurn=null,postTurnNow}){
  need(Number.isSafeInteger(now)&&typeof routeAdmitted==='function'&&
    typeof budgetAdmitted==='function'&&typeof serviceTurn==='function'&&
    typeof reserveTurn==='function'&&typeof commitTurn==='function'&&
    typeof postTurnNow==='function',
    'trusted_host_interfaces_required');
  let budgetHeld=false;
  const reserve=await reserveTurn({f,identity,store,now,leaseSeconds,
    admission:async()=>{
      if(await routeAdmitted(identity,now)!==true)return false;
      if(await budgetAdmitted({mission_id:identity.mission_id,
         task_fixture_blob:FIXTURE_BLOB,model:FIXED_MODEL,
         max_calls:1,max_completion_tokens:512,free_only:true})!==true){budgetHeld=true;return false;}
      return true;
    }});
  if(reserve?.status!=='reserved'||reserve.dispatch!==true)
    return {schema:'agent-fabric.j11.turn_outcome.v1',status:budgetHeld?'account_budget_held':reserve?.status||'not_reserved',
      dispatch:false,provider_calls:0,accepted_tasks:null,receipt:null};
  const selector=candidateSelector(f,identity,reserve);
  // The durable CAS reservation is independently read back before invoking
  // Service Binding. A transport exception is INDETERMINATE: do not commit a
  // fabricated YIELD or retry same attempt. Preserve lease for reconciliation.
  let reply;
  try{reply=await serviceTurn({selector,attempt:reserve.request.attempt});}
  catch{return {schema:'agent-fabric.j11.turn_outcome.v1',status:'provider_transport_indeterminate',
    dispatch:false,provider_calls:null,attempt:reserve.request.attempt,accepted_tasks:null,receipt:null};}
  try{admitProviderReply(reply,selector,f);}
  catch{return {schema:'agent-fabric.j11.turn_outcome.v1',status:'provider_result_untrusted_reconcile',
    dispatch:false,provider_calls:null,attempt:reserve.request.attempt,accepted_tasks:null,receipt:null};}
  // Read a NEW trusted clock AFTER the external provider response. Synthetic
  // now+1 would silently accept expired leases during slow/uncertain calls.
  let finished;
  try{finished=await postTurnNow(identity);}catch{finished=null;}
  if(!Number.isSafeInteger(finished)||finished<=now)return {
    schema:'agent-fabric.j11.turn_outcome.v1',status:'post_turn_clock_unavailable_reconcile',
    dispatch:false,provider_calls:null,attempt:reserve.request.attempt,
    accepted_tasks:null,receipt:null,stop_this_pass:true};
  // Rate limit, provider denial and transient failure always stop this caller;
  // the reserved attempt remains pending. No automatic retry/extra spend.
  if(FAIL_CLOSED.has(reply.status)){
    // Definite provider 429/denial can be persisted terminally through the
    // existing same-ID checkpoint CAS. An indeterminate transport may have
    // executed; never claim a definite hold or force an automatic replay.
    let hold=null;
    if(reply.status!=='transport_or_decode_failure'&&typeof holdProviderTurn==='function'){
      try{hold=await holdProviderTurn({f,identity,store,
        attempt:reserve.request.attempt,reason:reply.status,now:finished});}
      catch{return {schema:'agent-fabric.j11.turn_outcome.v1',
        status:'provider_hold_indeterminate_reconcile',dispatch:false,provider_calls:1,
        attempt:reserve.request.attempt,accepted_tasks:null,receipt:null,stop_this_pass:true};}
    }
    return {schema:'agent-fabric.j11.turn_outcome.v1',
      status:hold?.status==='provider_held'?'provider_held':reply.status,
      provider_status:reply.status,dispatch:false,provider_calls:1,
      attempt:reserve.request.attempt,accepted_tasks:null,
      checkpoint_blob_sha:hold?.status==='provider_held'?hold.blob_sha:null,
      checkpoint_commit_sha:hold?.status==='provider_held'?hold.commit_sha:null,
      receipt:null,stop_this_pass:true};
  }
  const action=reply.status==='candidate_unexecuted'?reply.action:{kind:'yield'};
  const committed=await commitTurn({f,identity,store,attempt:reserve.request.attempt,
     action,now:finished});
  const pass=committed?.status==='written';
  return {schema:'agent-fabric.j11.turn_outcome.v1',
    status:pass?'checkpoint_committed':committed?.status||'commit_indeterminate',
    dispatch:false,provider_calls:reply.provider_attempt_upper_bound,
    task_id:selector.task_id,attempt:reserve.request.attempt,
    provider_status:reply.status,model:FIXED_MODEL,
    accepted_tasks:pass?committed.summary?.accepted:null,
    checkpoint_blob_sha:pass?committed.blob_sha:null,
    checkpoint_commit_sha:pass?committed.commit_sha:null,
    receipt:pass?{model:FIXED_MODEL,task_id:selector.task_id,
       provider_status:reply.status,http_status:reply.http_status,
       prompt_tokens:reply.prompt_tokens,completion_tokens:reply.completion_tokens,
       elapsed_ms:reply.elapsed_ms,provider_attempt_upper_bound:1,
       checkpoint_blob_sha:committed.blob_sha,checkpoint_commit_sha:committed.commit_sha,
       private_input_used:false,production_admitted:false}:null};
}
