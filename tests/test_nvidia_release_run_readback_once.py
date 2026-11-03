"""Public-synthetic run discovery is exact and cannot grant deployment."""
from scripts.nvidia_release_run_readback_once import (
    RELEASE_SHA,SOURCE_SHA,WORKFLOW,validate_trigger,select_run,summarize)
import pytest

TRIGGER=("observe=v1;release_sha="+RELEASE_SHA+";worker_source="+SOURCE_SHA+
         ";workflow="+WORKFLOW+";nonce=MW-20261103065614536-readback")
def run(**kw):
    return {"head_sha":RELEASE_SHA,"head_branch":"main","event":"push",
            "path":".github/workflows/"+WORKFLOW,
            "id":41590012345,"status":"completed","conclusion":"success",
            "run_attempt":1,**kw}
def test_exact_trigger_rejects_arbitrary_repo_workflow_or_input():
    assert validate_trigger(TRIGGER) is True
    for bad in ["","observe=v1;source=evil",
        TRIGGER.replace(RELEASE_SHA,"a"*40),
        TRIGGER.replace(SOURCE_SHA,"b"*40),
        TRIGGER.replace(WORKFLOW,"evil.yml"),
        TRIGGER+";prompt=SECRET",
        TRIGGER.replace("nonce=MW-20261103065614536-readback","nonce=x")]:
        with pytest.raises(ValueError):validate_trigger(bad)
def test_selects_only_exact_push_main_release_identity():
    expected=run()
    assert select_run({"workflow_runs":[expected]})==expected
    for mismatch in [{"head_sha":"f"*40},{"head_branch":"feature"},
        {"event":"pull_request"},{"path":".github/workflows/another.yml"},
        {"id":-2}]:
        row={**expected,**mismatch}
        assert select_run({"workflow_runs":[row]}) is None
    with pytest.raises(ValueError):
        select_run({"workflow_runs":[expected,expected]})
    with pytest.raises(ValueError):
        select_run({"workflow_runs":"invalid"})
def test_job_and_artifact_status_is_observed_not_production_admission():
    rr=run()
    jobs={"jobs":[{"name":"exact-target-bound-redeploy","id":12445,
                   "status":"completed","conclusion":"success"}]}
    arts={"artifacts":[{"name":"nvidia-v4-reviewed-release-version",
                        "id":3222,"expired":False}]}
    result=summarize(rr,jobs,arts)
    assert result["run_id"]==41590012345
    assert result["job_id"]==12445
    assert result["version_artifact_id"]==3222
    assert result["claims_cloudflare_source_verified"] is False
    assert result["claims_model_inference_complete"] is False
    assert result["private_input_used"] is False
    assert summarize(None,{"jobs":[]},{"artifacts":[]})["status"]=="NOT_DISCOVERED"
    for bad_jobs in ({"jobs":[]},{"jobs":[jobs["jobs"][0]]*2}):
        with pytest.raises(ValueError):summarize(rr,bad_jobs,arts)
