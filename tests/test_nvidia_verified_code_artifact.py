"""Check the preserved Poolside synthetic work artifact against 23 independent cases.

No arbitrary model code execution: reuse the strict allowlisted AST interpreter.
"""
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from nvidia_fixed_code_repair_work import evaluate,CodeRejected

class ModelWorkArtifactTests(unittest.TestCase):
 def test_poolside_source_preserved_exactly_and_correct(self):
  path=ROOT/"artifacts/nvidia/code-repair/RETRY_DEADLINE_01_poolside.py"
  text=path.read_text(encoding="utf-8")
  source=text[text.index("def retry_delay_ms("):]
  result=evaluate(source)
  self.assertEqual(result["passed"],23)
  self.assertEqual(result["total"],23)
  self.assertTrue(result["all_passed"])
 def test_artifact_never_contains_private_repo_or_keys(self):
  text=(ROOT/"artifacts/nvidia/code-repair/RETRY_DEADLINE_01_poolside.py").read_text()
  for forbidden in ("NVIDIA_API_KEY","CLOUDFLARE_API_TOKEN","XoticHaze/CommandCenter-gate-control",
                    "Authorization: Bearer","private key","subprocess","__import__"):
   self.assertNotIn(forbidden,text)
if __name__=="__main__":unittest.main()
