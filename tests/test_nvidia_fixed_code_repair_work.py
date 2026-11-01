"""Offline, zero-provider verification of the strict AST-only code review."""
import unittest
import io
import contextlib
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import nvidia_fixed_code_repair_work as w

GOOD="""def retry_delay_ms(attempt, max_attempts, base_ms, cap_ms):
    if attempt <= 0 or max_attempts <= 0 or attempt >= max_attempts:
        return None
    if base_ms <= 0 or cap_ms <= 0:
        return None
    return min(cap_ms, base_ms * (2 ** (attempt - 1)))
"""
BAD="""def retry_delay_ms(attempt, max_attempts, base_ms, cap_ms):
    if attempt > max_attempts:
        return None
    return min(cap_ms, base_ms * (2 ** attempt))
"""
class CodeRepairTests(unittest.TestCase):
 def test_good_repair_fully_passes_exact_independent_behavior(self):
    result=w.evaluate(GOOD)
    self.assertTrue(result["all_passed"])
    self.assertEqual(result["passed"],len(w.CASES))
    self.assertGreaterEqual(len(w.CASES),20)
 def test_original_bug_fails_real_case_checks(self):
    result=w.evaluate(BAD)
    self.assertFalse(result["all_passed"])
    self.assertLess(result["passed"],len(w.CASES))
 def test_no_python_execution_and_reject_arbitrary_import_or_exec(self):
    for code in (
      GOOD.replace("    return min", "    import os\n    return min"),
      GOOD.replace("    return min", "    return eval(attempt)\n    return min"),
      GOOD.replace("    return min", "    open(secret)\n    return min"),
      GOOD.replace("    return min", "    while attempt: return 1\n    return min"),
      GOOD.replace("    return min", "    x = 7\n    return min"),
      GOOD.replace("    return min", "    return __import__(os)\n    return min"),
    ):
     with self.assertRaises(w.CodeRejected):w.evaluate(code)
 def test_untrusted_identity_or_rate_limit_never_promotes(self):
    receipt={"schema":"commandcenter.nvidia_fixed_code_repair.v1",
     "model_index":0,"model":w.MODELS[0],"task_id":"RETRY_DEADLINE_01",
     "provider_calls":1,"status":"candidate_unexecuted","http_status":200,"code":GOOD}
    self.assertEqual(w.validate_receipt(receipt,0),GOOD)
    with self.assertRaisesRegex(RuntimeError,"REJECTED"):
      w.validate_receipt({**receipt,"model":"other"},0)
    with self.assertRaisesRegex(RuntimeError,"429"):
      w.validate_receipt({**receipt,"status":"rate_limited","http_status":429,"code":None},0)
 def test_safe_status_logs_only_reviewed_classification_and_no_code(self):
    rec={"schema":"commandcenter.nvidia_fixed_code_repair.v1",
         "model_index":1,"model":w.MODELS[1],
         "task_id":"RETRY_DEADLINE_01","provider_calls":1,
         "status":"candidate_format_rejected","http_status":200,
         "code":"DO_NOT_LEAK_PRIVATE_MODEL_BODY"}
    out=io.StringIO()
    with contextlib.redirect_stdout(out):
     with self.assertRaisesRegex(RuntimeError,"NOT_ADMITTED"):
      w.validate_receipt(rec,1)
    self.assertIn("NVIDIA_CODE_REPAIR_SAFE_GATE=",out.getvalue())
    self.assertIn("candidate_format_rejected",out.getvalue())
    self.assertNotIn("DO_NOT_LEAK",out.getvalue())

 def test_no_arbitrary_code_execution_or_infinite_growth(self):
    code="""def retry_delay_ms(attempt, max_attempts, base_ms, cap_ms):
    return 1000 ** 100
"""
    self.assertFalse(w.evaluate(code)["all_passed"])
if __name__=="__main__":unittest.main()
