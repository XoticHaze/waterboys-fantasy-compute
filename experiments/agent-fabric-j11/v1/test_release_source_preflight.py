"""Local-only structural review of the owner-held J11 source release workflow.
Never executes its embedded Cloudflare calls or deploys a Worker.
"""
import ast
import pathlib
import re
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[3]
WORKFLOW=ROOT/".github/workflows/nvidia-j11-v2-bound-source-release-r1.yml"
SOURCE="e954bf5964a7d7d25888881d4894ce25400bf1ac"
PREDECESSOR="b5ec0a32-9ac1-43d4-a87e-7e52a68d4c35"
BASE="7ff97c4982b32cf08900dea000dd269a1f9d8ff1"
CI="46143876262"

def scripts(text):
    lines=text.splitlines();out=[];i=0
    while i<len(lines):
        line=lines[i];match=re.match(r"^(\s*)python(?:3)? - <<'PY'\s*$",line)
        if not match: i+=1;continue
        prefix=len(match.group(1));block=[];i+=1
        while i<len(lines) and lines[i].strip()!="PY":
            current=lines[i]
            if current.strip() and current[:prefix]!=" "*prefix:
                raise ValueError("heredoc_indentation_invalid")
            block.append(current[prefix:])
            i+=1
        if i>=len(lines):raise ValueError("heredoc_unterminated")
        out.append("\n".join(block)+"\n")
        i+=1
    return out

def admitted(text):
    required=[
        "name: NVIDIA J11 Isolated V2 Bound Source Release",
        "branches: [main]",
        "ops/nvidia_j11_v2_bound_release_trigger.txt",
        SOURCE,BASE,CI,PREDECESSOR,
        "NVIDIA_API_KEY","secrets_store_secret",
        "CC_NVIDIA_DIAGNOSTIC_ENABLED","J11_RELEASE_TARGET_CAS_PREFLIGHT=PASS",
        "J11_JUST_BEFORE_DEPLOY_VERSION_CHANGED__SAFE_HALT",
        "production_admitted", "False",
        "NVIDIA_PROVIDER_CALLS=0",
    ]
    if not all(term in text for term in required):return False
    if "workflow_dispatch" in text:return False
    if "branches: [agent-fabric/" in text:return False
    if "private.github" in text:return False
    if "WRANGLER" in text.upper() and "--dry-run" in text and "deploy --config wrangler.bound.jsonc" not in text:
        return False
    return True

class ExactJ11OwnerReleasePreflight(unittest.TestCase):
    def setUp(self):self.text=WORKFLOW.read_text(encoding="utf8")

    def test_exact_source_release_held_only_by_mainline_reviewed_trigger(self):
        self.assertTrue(admitted(self.text))
        self.assertEqual(self.text.count("ref: "+SOURCE),1)
        self.assertNotIn("workflow_dispatch",self.text)

    def test_all_embedded_python_blocks_parse_without_execution(self):
        chunks=scripts(self.text)
        self.assertEqual(len(chunks),4)
        for i,src in enumerate(chunks):
            with self.subTest(script=i): ast.parse(src)

    def test_no_implicit_provider_call_or_new_worker_config(self):
        self.assertNotIn("integrate.api.nvidia.com",self.text)
        self.assertIn("workers_dev",self.text)
        self.assertIn("preview_urls",self.text)
        self.assertIn("NVIDIA_BOUND_WORKER_REDEPLOY_READBACK=PASS",self.text)
        self.assertIn("J11_EXACT_V2_PREDECESSOR_READBACK=PASS",self.text)

    def test_changing_target_source_version_or_trigger_fails_contract(self):
        for old in [SOURCE,PREDECESSOR,CI,"ops/nvidia_j11_v2_bound_release_trigger.txt"]:
            with self.subTest(field=old):
                self.assertFalse(admitted(self.text.replace(old,"invalid-review-proof")))

    def test_distinct_source_release_requires_no_inference_admission(self):
        self.assertIn("J11_PROVIDER_INFERENCE=NOT_ADMITTED",self.text)
        self.assertIn("NVIDIA_PROVIDER_CALLS=0",self.text)
        self.assertIn("preserve_CC_NVIDIA_DIAGNOSTIC_ENABLED",self.text)

if __name__=="__main__": unittest.main()
