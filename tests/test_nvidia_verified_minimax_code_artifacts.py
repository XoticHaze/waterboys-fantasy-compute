"""Verify three actual MiniMax code outputs, without model-source execution."""
import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from nvidia_role_code_matrix import TASKS,cases_for
from nvidia_fixed_code_repair_work import evaluate

class ActualMinimaxCodeEvidence(unittest.TestCase):
 def test_three_real_patches_against_90_hidden_cases(self):
  for i in (0,1,4):
   t=TASKS[i]
   path=ROOT/"artifacts"/"nvidia"/"code-role-minimax"/(t[0]+".py")
   raw=path.read_text()
   self.assertIn("ACTUAL MiniMax M3.1 Flash",raw)
   src=raw[raw.index("def "+t[1]+"("):]
   result=evaluate(src,function_name=t[1],args=t[2],cases=cases_for(i))
   self.assertEqual(result["passed"],30,(t[0],result))
   self.assertTrue(result["all_passed"])
 def test_no_unapproved_execution_sources(self):
  forbidden=("NVIDIA_API_KEY","CLOUDFLARE_API_TOKEN",
    "Authorization: Bearer","__import__","subprocess","os.system")
  for i in (0,1,4):
   raw=(ROOT/"artifacts"/"nvidia"/"code-role-minimax"/(TASKS[i][0]+".py")).read_text()
   for word in forbidden:self.assertNotIn(word,raw)
if __name__=="__main__":unittest.main()
