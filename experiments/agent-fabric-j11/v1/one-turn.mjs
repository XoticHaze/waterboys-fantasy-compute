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
export function admitProviderReply(reply,selector){
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
    (reply.http_status===null||integer(reply.http_status,599))&&
    (reply.prompt_tokens===null||integer(reply.prompt_tokens,1000000))&&
    (reply.completion_tokens===null||integer(reply.completion_tokens,1000000)),
    'untrusted_provider_envelope');
  if(reply.status!=='candidate_unexecuted')need(reply.action===null,'noncandidate_action_not_allowed');
  else {
    const action=reply.action;
    need(action&&typeof action==='object'&&!Array.isArray(action),
      'candidate_missing');
    const fields=Object.keys(action).sort().join(',');
    need((fields==='kind'&&action.kind==='yield') ||
      (fields==='kind,route'&&action.kind==='read'&&typeof action.route==='string') ||
      (fields==='evidence,kind,state'&&action.kind==='submit'&&
       typeof action.state==='string'&&Array.isArray(action.evidence)),
      'candidate_action_invalid');
  }
  return reply;
}
export async function runOneTurn({f,identity,store,now,leaseSeconds=90,
   routeAdmitted,budgetAdmitted,serviceTurn,reserveTurn,commitTurn}){
  need(Number.isSafeInteger(now)&&typeof routeAdmitted==='function'&&
    typeof budgetAdmitted==='function'&&typeof serviceTurn==='function'&&
    typeof reserveTurn==='function'&&typeof commitTurn==='function',
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
  try{admitProviderReply(reply,selector);}
  catch{return {schema:'agent-fabric.j11.turn_outcome.v1',status:'provider_result_untrusted_reconcile',
    dispatch:false,provider_calls:null,attempt:reserve.request.attempt,accepted_tasks:null,receipt:null};}
  // Rate limit, provider denial and transient failure always stop this caller;
  // the reserved attempt remains pending. No automatic retry/extra spend.
  if(FAIL_CLOSED.has(reply.status))return {schema:'agent-fabric.j11.turn_outcome.v1',
     status:reply.status,dispatch:false,provider_calls:reply.provider_attempt_upper_bound,
     attempt:reserve.request.attempt,accepted_tasks:null,receipt:null,stop_this_pass:true};
  const action=reply.status==='candidate_unexecuted'?reply.action:{kind:'yield'};
  const committed=await commitTurn({f,identity,store,attempt:reserve.request.attempt,
     action,now:now+1});
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
