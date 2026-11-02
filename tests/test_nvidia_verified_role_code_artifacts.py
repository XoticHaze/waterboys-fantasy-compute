"""Reproducibly validate the five actual model-generated public synthetic artifacts.

Only the strict AST-only interpreter processes code; nothing is imported
from these model-generated .py files or executed with exec/eval/compile.
"""
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from nvidia_role_code_matrix import TASKS,cases_for
from nvidia_fixed_code_repair_work import evaluate

class RealGeneratedRoleArtifacts(unittest.TestCase):
 def test_all_five_actual_poolside_patches_pass_150_independent_cases(self):
  total=0
  for i,task in enumerate(TASKS):
   path=ROOT/"artifacts"/"nvidia"/"code-role"/(task[0]+".py")
   raw=path.read_text(encoding="utf-8")
   self.assertIn("ACTUAL Poolside Laguna",raw)
   self.assertIn("NOT a production CommandCenter patch",raw)
   code=raw[raw.index("def "+task[1]+"("):]
   result=evaluate(code,function_name=task[1],args=task[2],
       cases=cases_for(i))
   self.assertEqual(result["passed"],30,(task[0],result))
   self.assertTrue(result["all_passed"])
   total+=result["total"]
  self.assertEqual(total,150)
 def test_all_artifacts_contain_no_private_credentials_or_execution_calls(self):
  forbidden=("NVIDIA_API_KEY","CLOUDFLARE_API_TOKEN","Authorization: Bearer",
     "subprocess","__import__","curl ","private.github","os.system")
  for task in TASKS:
   raw=(ROOT/"artifacts"/"nvidia"/"code-role"/(task[0]+".py")).read_text()
   for x in forbidden:
    self.assertNotIn(x,raw)
if __name__=="__main__":unittest.main()
