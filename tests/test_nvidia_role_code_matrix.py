"""Independent AST-only regression of five distinct fictional coding tasks."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import nvidia_role_code_matrix as matrix
from nvidia_fixed_code_repair_work import evaluate,CodeRejected

GOOD=(
 """def retry_delay_ms(attempt, max_attempts, base_ms, cap_ms):
    if attempt <= 0 or max_attempts <= 0 or attempt >= max_attempts or base_ms <= 0 or cap_ms <= 0:
        return None
    return min(cap_ms, base_ms * (2 ** (attempt - 1)))
""",
 """def clamp_window(value, low, high, fallback):
    if low > high:
        return fallback
    return max(low, min(high, value))
""",
 """def budget_remaining(limit, spent, reserved, floor):
    if limit < 0 or spent < 0 or reserved < 0 or floor < 0:
        return None
    if limit - spent - reserved < floor:
        return None
    return limit - spent - reserved
""",
 """def allocation_limit(equity, risk_bps, cap_usd, minimum_usd):
    if equity <= 0 or risk_bps <= 0 or risk_bps > 10000 or cap_usd <= 0 or minimum_usd <= 0 or cap_usd < minimum_usd:
        return None
    if min(cap_usd, (equity * risk_bps) // 10000) < minimum_usd:
        return None
    return min(cap_usd, (equity * risk_bps) // 10000)
""",
 """def staleness_status(now_ms, last_ms, warn_ms, expire_ms):
    if now_ms < 0 or last_ms < 0 or now_ms < last_ms or warn_ms <= 0 or expire_ms <= warn_ms:
        return -1
    if now_ms - last_ms >= expire_ms:
        return 2
    if now_ms - last_ms >= warn_ms:
        return 1
    return 0
""",
)
BROKEN=(
 """def retry_delay_ms(attempt, max_attempts, base_ms, cap_ms):
    if attempt > max_attempts:
        return None
    return min(cap_ms, base_ms * (2 ** attempt))
""",
 """def clamp_window(value, low, high, fallback):
    if value > high:
        return high
    return value
""",
 """def budget_remaining(limit, spent, reserved, floor):
    if spent > limit:
        return None
    return limit - spent
""",
 """def allocation_limit(equity, risk_bps, cap_usd, minimum_usd):
    return min(cap_usd, equity * risk_bps)
""",
 """def staleness_status(now_ms, last_ms, warn_ms, expire_ms):
    if now_ms - last_ms >= warn_ms:
        return 1
    return 0
""",
)
class MatrixTests(unittest.TestCase):
 def test_five_good_patches_pass_150_independent_checks(self):
  total=0
  for i,t in enumerate(matrix.TASKS):
   with self.subTest(task=t[0]):
    cases=matrix.cases_for(i)
    self.assertEqual(len(cases),30)
    result=evaluate(GOOD[i],function_name=t[1],args=t[2],cases=cases)
    self.assertTrue(result["all_passed"],result)
    total+=result["total"]
  self.assertEqual(total,150)
 def test_five_original_buggy_sources_fail_independent_checks(self):
  for i,t in enumerate(matrix.TASKS):
   with self.subTest(task=t[0]):
    r=evaluate(BROKEN[i],function_name=t[1],args=t[2],cases=matrix.cases_for(i))
    self.assertFalse(r["all_passed"])
    self.assertGreater(len(r["failed_case_indices"]),0)
 def test_exact_source_signature_required(self):
  for i,t in enumerate(matrix.TASKS):
   other=GOOD[(i+1)%5]
   with self.assertRaises(CodeRejected):
    evaluate(other,function_name=t[1],args=t[2],cases=matrix.cases_for(i))
 def test_reject_exec_import_and_network_primitives_without_execution(self):
  for code in (
   GOOD[2].replace("return None","import os\n        return None",1),
   GOOD[2].replace("return None","return eval(limit)",1),
   GOOD[2].replace("return None","return __import__(os)",1),
   GOOD[2].replace("return None","return open(token)",1),
  ):
   with self.assertRaises(CodeRejected):
    evaluate(code,function_name=matrix.TASKS[2][1],
             args=matrix.TASKS[2][2],cases=matrix.cases_for(2))
 def test_locals_are_allowed_without_exec_and_hidden_behavior_still_passes(self):
  code="""def budget_remaining(limit, spent, reserved, floor):
    if limit < 0 or spent < 0 or reserved < 0 or floor < 0:
        return None
    left = limit - spent - reserved
    if left < floor:
        return None
    return left
"""
  t=matrix.TASKS[2]
  r=evaluate(code,function_name=t[1],args=t[2],cases=matrix.cases_for(2))
  self.assertTrue(r["all_passed"],r)
 def test_model_code_cannot_assign_globals_or_unbounded_object_names(self):
  bad=(
   GOOD[1].replace("    return max", "    globals = 10\\n    return max"),
   GOOD[1].replace("    return max", "    __import__ = 10\\n    return max"),
   GOOD[1].replace("    return max", "    value = 10\\n    return max"),
   GOOD[1].replace("    return max", "    a,b = 1,2\\n    return max"),
  )
  t=matrix.TASKS[1]
  for candidate in bad:
   with self.assertRaises(CodeRejected):
    evaluate(candidate,function_name=t[1],args=t[2],cases=matrix.cases_for(1))

 def test_caller_timeout_is_model_scoped_and_exceeds_minimax_worker_deadline(self):
  self.assertEqual(matrix.fixed_role_http_timeout(0),55)
  self.assertEqual(matrix.fixed_role_http_timeout(1),90)
  self.assertGreater(matrix.fixed_role_http_timeout(1),75)
  for bad in (-1,2,"minimax",None,True,1.0):
   with self.assertRaises(RuntimeError):
    matrix.fixed_role_http_timeout(bad)

 def test_single_fixed_role_job_selector_fails_closed(self):
  for i in range(5):
   self.assertEqual(matrix.parse_role_selector(f"one:{i}"),(i,i+1))
  self.assertEqual(matrix.parse_role_selector("all"),(0,5))
  self.assertEqual(matrix.parse_role_selector("tail"),(2,5))
  self.assertEqual(matrix.parse_role_selector("last"),(4,5))
  for candidate in ("one:5","one:-1","one:00","one:2;echo hello",
       "one:../../private","poolside","work=0","job:0",None,0):
   with self.assertRaises(RuntimeError):
    matrix.parse_role_selector(candidate)
 def test_exact_selector_not_a_prompt_or_source(self):
  for i,t in enumerate(matrix.TASKS):
   self.assertEqual(matrix.safe_case({
    "schema":"commandcenter.nvidia_role_code_case.v1","model":matrix.MODELS[0],
    "model_index":0,"task_id":t[0],"task_index":i,"provider_calls":1,
    "status":"format_rejected","http_status":200,"code":None
   },0,i),("format_rejected",200,None))
  with self.assertRaises(RuntimeError):
   matrix.safe_case({"status":"candidate_unexecuted"},0,0)
if __name__=="__main__":unittest.main()
