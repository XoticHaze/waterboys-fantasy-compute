"""New unseen randomized holdout on FIVE real Poolside-generated Python repairs.

Never compile, import, exec, or eval the model's code. The existing audited
AST-only interpreter checks the exact saved public synthetic source against
2,500 deterministic pseudo-random unseen inputs and a separate semantic oracle.
"""
from pathlib import Path
import random
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from nvidia_fixed_code_repair_work import evaluate,CodeRejected
from nvidia_role_code_matrix import TASKS,oracle,cases_for

ARTIFACTS=ROOT/"artifacts/nvidia/code-role"
TASK_IDS=tuple(t[0] for t in TASKS)
SEED=20261101
HOLDOUT_SAMPLES_PER_TASK=500

def holdout_input(task,rng,i):
    if task==0:
        # Keep one-based exponent range within the safe interpreter ceiling.
        attempt=rng.randint(-3,19)
        max_attempts=rng.randint(0,20)
        base=rng.randint(-20,10000)
        cap=rng.randint(-10,20000)
        return (attempt,max_attempts,base,cap)
    if task==1:
        value=rng.randint(-20000,20000)
        low=rng.randint(-20000,20000)
        high=rng.randint(-20000,20000)
        fallback=rng.randint(-20000,20000)
        if i%13==0:high=low
        if i%17==0:value=low
        if i%19==0:value=high
        return (value,low,high,fallback)
    if task==2:
        limit=rng.randint(-1500,250000)
        spent=rng.randint(-1500,250000)
        reserved=rng.randint(-1500,250000)
        floor=rng.randint(-1500,250000)
        if i%7==0:floor=limit-spent-reserved
        if i%11==0:reserved=0
        return (limit,spent,reserved,floor)
    if task==3:
        equity=rng.randint(-1500,500000)
        bps=rng.randint(-10,12000)
        cap=rng.randint(-100,10000)
        floor=rng.randint(-100,12000)
        if i%11==0:bps=10000
        if i%13==0:bps=10001
        if i%17==0:cap=floor
        return (equity,bps,cap,floor)
    if task==4:
        if i%2==0:
            last=rng.randint(0,1000000)
            delta=rng.randint(0,20000)
            warn=rng.randint(1,10000)
            expire=rng.randint(warn+1,22000)
            if i%12==0:delta=warn
            if i%18==0:delta=expire
            return (last+delta,last,warn,expire)
        now=rng.randint(-1000,1000000)
        last=rng.randint(-1000,1000000)
        warn=rng.randint(-10,10000)
        expire=rng.randint(-10,22000)
        return (now,last,warn,expire)
    raise ValueError("unknown fixed task")

class PoolsideGeneratedPropertyHoldout(unittest.TestCase):
    def test_five_actual_generated_artifacts_pass_2500_unseen_inputs(self):
        grand_total=0
        for i,task in enumerate(TASKS):
            with self.subTest(task=task[0]):
                filename=ARTIFACTS/(task[0]+"_poolside.py")
                self.assertTrue(filename.is_file())
                src=filename.read_text(encoding="utf-8")
                self.assertTrue(src.startswith("def "+task[1]+"("))
                self.assertNotIn("import ",src)
                self.assertNotIn("exec(",src)
                rng=random.Random(SEED+i*13007)
                cases=tuple(
                    (params,oracle(i,params))
                    for j in range(HOLDOUT_SAMPLES_PER_TASK)
                    for params in (holdout_input(i,rng,j),)
                )
                self.assertEqual(len(cases),500)
                result=evaluate(src,function_name=task[1],args=task[2],cases=cases)
                self.assertEqual(result["passed"],500,
                    f"{task[0]} wrong on new inputs {result['failed_case_indices'][:12]}")
                self.assertTrue(result["all_passed"])
                original=evaluate(src,function_name=task[1],args=task[2],cases=cases_for(i))
                self.assertTrue(original["all_passed"],original)
                grand_total+=result["passed"]
        self.assertEqual(grand_total,2500)

    def test_source_files_are_data_never_imported_or_executed(self):
        # Inspection is confined to static source and AST interpreter.
        self.assertEqual(len(list(ARTIFACTS.glob("*_poolside.py"))),5)
        for id in TASK_IDS:
            src=(ARTIFACTS/(id+"_poolside.py")).read_text()
            self.assertNotIn("NVIDIA_API_KEY",src)
            self.assertNotIn("CLOUDFLARE_API_TOKEN",src)
            self.assertLessEqual(len(src),1050)
            self.assertLess(src.count("\n"),24)

if __name__=="__main__":
    unittest.main()
