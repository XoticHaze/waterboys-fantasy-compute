"""Offline guard for the exact-source NVIDIA v4 public-fictional release path.

Source tests only. No provider, secret, Actions dispatch or Cloudflare access.
The workflow and deploy run must be separately accepted by the owning release.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V4 = ROOT / ".github/workflows/nvidia-workforce-shadow-qualification.yml"
DEPLOY = ROOT / ".github/workflows/nvidia-bound-worker-redeploy-preflight-once.yml"
RELEASE = ROOT / "ops/nvidia_authorized_bound_source_deploy_trigger.txt"
V4_TRIGGER = ROOT / "ops/nvidia_v4_workforce_campaign_trigger.txt"
SOURCE = "0d5131a1fec357c3317973c24febecee6f98818b"
V3_SOURCE = "d18a85c78e3db84ffde6d51cb3d785971e6f0a38"


def test_exact_public_v4_source_is_pinned_not_a_moving_branch():
    release = DEPLOY.read_text()
    v4 = V4.read_text()
    assert "ref: " + SOURCE in release
    assert "ref: " + SOURCE in v4
    assert V3_SOURCE not in release
    assert V3_SOURCE not in v4
    assert "41589590058" in release  # original exact public source CI
    assert "npm test" in release
    assert "npm test" in v4


def test_deploy_requires_new_reviewed_manifest_without_executing():
    release = DEPLOY.read_text()
    current_trigger = RELEASE.read_text()
    assert "EXACT_REVIEWED_V4_RELEASE_MANIFEST=PASS" in release
    assert "REVIEWED_V4_RELEASE_REQUEST_NOT_ADMITTED" in release
    assert "existing_private_synthetic_model_research_mechanism_v4_only" in release
    assert "REVIEWED_NVIDIA_WORKFORCE_CAUSAL_NEWS_ORACLE_V3_DEPLOY" in current_trigger
    assert SOURCE not in current_trigger
    assert release.count("flag.get('text')!='0'") == 2
    assert "ACCOUNT_SECRET_BINDING_NOT_PRESERVED" in release
    assert "NVIDIA_SECRET_VALUE_ACCESSED=0" in release
    assert "workers_dev" in release
    assert "preview_urls" in release


def test_v4_public_synthetic_workflow_requires_verified_prior_release():
    v4 = V4.read_text()
    assert "ops/nvidia_v4_workforce_campaign_trigger.txt" in v4
    assert "WORKFORCE_V4_SOURCE_SHA: " + SOURCE in v4
    assert "ops/nvidia_workforce_campaign_trigger.txt" not in v4
    assert not V4_TRIGGER.exists()  # the PR must not start a provider session
    assert 'test "$GITHUB_RUN_ATTEMPT" = "1"' in v4
    assert 'run.get("conclusion")=="success"' in v4
    assert 'run.get("run_attempt")==1' in v4
    assert "V4_RELEASE_WORKFLOW_SOURCE_NOT_VERIFIED" in v4
    assert "V4_DEPLOYMENT_SCOPE_MISMATCH" in v4
    assert "model=(25|53)" in v4
    assert "case//20!=(case+limit-1)//20" in v4
    assert "V4_ROLE_BOUNDARY_EXCEEDED" in v4


def test_v4_result_is_only_sanitized_fictional_metadata():
    v4 = V4.read_text()
    assert "V4_MODEL_RESULT_PRIVACY_GUARD_REJECT" in v4
    assert "V4_PUBLIC_ARTIFACT_CONTRACT_INVALID" in v4
    assert "raw_responses_stored" in v4
    assert "private_input_used" in v4
    assert "answer_exported" in v4
    assert "raw_response_exported" in v4
    assert "tools_executed" in v4
    assert "nvidia-v4-mechanism/campaign_progress.json" in v4
    assert "if: always()" in v4
    assert "nvidia_private_diagnostic_gate_once.py restore" in v4
    assert "runs-on: self-hosted" not in v4
    assert "workflow_dispatch:" not in v4


def test_existing_shared_worker_concurrency_and_least_privileges():
    deploy = DEPLOY.read_text()
    v4 = V4.read_text()
    assert "cc-shared-nvidia-private-controlled-provider-test" in deploy
    assert "cc-shared-nvidia-private-controlled-provider-test" in v4
    assert "  contents: read" in v4
    assert "  actions: read" in v4
    assert "contents: write" not in v4
    assert "actions: write" not in v4
    assert "issues: write" not in v4
    assert "GITHUB_API_READ_TOKEN:" in v4
    assert "Authorization" in v4
    assert "@@ACCOUNT_ID@@" not in v4
    assert "@@API_TOKEN@@" not in v4
    assert "@@GITHUB_TOKEN@@" not in v4
