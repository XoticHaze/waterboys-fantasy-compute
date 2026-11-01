#!/usr/bin/env python3
"""Safely score one fixed fictional model-created Python retry fix.

The model's code is NEVER exec'd, eval'd, compiled or imported. An explicit
subset of Python's AST is interpreted with bounded integer operations.
Output is a verified synthetic artifact only, never a CommandCenter command.
"""
from __future__ import annotations
import ast
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError,URLError
from urllib.request import Request,urlopen
from nvidia_role_full_catalog_campaign import open_caller,close_caller

URL="http://127.0.0.1:8787/code-repair"
MODELS=("poolside/laguna-xs-2.1","minimaxai/minimax-m3.1-flash")
ARGUMENTS=("attempt","max_attempts","base_ms","cap_ms")
CASES=(
 ((1,3,100,500),100),
 ((2,3,100,500),200),
 ((3,3,100,500),None),
 ((4,3,100,500),None),
 ((0,3,100,500),None),
 ((-1,3,100,500),None),
 ((1,1,100,500),None),
 ((1,0,100,500),None),
 ((1,3,0,500),None),
 ((1,3,-1,500),None),
 ((1,3,100,0),None),
 ((1,3,100,-50),None),
 ((1,3,100,50),50),
 ((2,6,1000,2500),2000),
 ((3,6,1000,2500),2500),
 ((4,6,1000,2500),2500),
 ((5,6,1000,2500),2500),
 ((6,6,1000,2500),None),
 ((1,2,7,100),7),
 ((2,10,7,100),14),
 ((3,10,7,100),28),
 ((5,10,7,100),100),
 ((1,3,99999,7),7),
)

class CodeRejected(ValueError):pass
def reject(message="UNTRUSTED_MODEL_CODE"):
    raise CodeRejected(message)

def parse_subset(code):
    if not isinstance(code,str) or not 75<=len(code)<=1051 or code.count("\n")>24:
        reject()
    if any(ord(x)>127 for x in code) or "\t" in code or "#" in code or "\r" in code:
        reject()
    try: t=ast.parse(code)
    except (SyntaxError,TypeError):reject("INVALID_CODE_SYNTAX")
    if len(t.body)!=1 or not isinstance(t.body[0],ast.FunctionDef):
        reject()
    f=t.body[0]
    if (f.name!="retry_delay_ms" or f.decorator_list or f.returns is not None or
        f.type_comment is not None or f.args.posonlyargs or f.args.kwonlyargs or
        f.args.vararg or f.args.kwarg or f.args.defaults or f.args.kw_defaults or
        tuple(x.arg for x in f.args.args)!=ARGUMENTS or
        any(x.annotation is not None for x in f.args.args)):
        reject()
    nodes=list(ast.walk(f))
    if len(nodes)>100:reject("AST_COMPLEXITY_LIMIT")
    statements=(ast.If,ast.Return)
    expressions=(ast.Name,ast.Load,ast.Constant,ast.BinOp,ast.BoolOp,ast.Compare,
                 ast.UnaryOp,ast.IfExp,ast.Call,ast.And,ast.Or,ast.Add,ast.Sub,
                 ast.Mult,ast.Pow,ast.USub,ast.UAdd,ast.Eq,ast.NotEq,ast.Lt,
                 ast.LtE,ast.Gt,ast.GtE,ast.Not)
    for n in nodes:
        if isinstance(n,(ast.FunctionDef,ast.arguments,ast.arg)):continue
        if isinstance(n,ast.If):
            if n.orelse and any(not isinstance(x,statements) for x in n.orelse):
                reject()
            if not n.body or any(not isinstance(x,statements) for x in n.body):
                reject()
        elif isinstance(n,ast.Return):continue
        elif isinstance(n,expressions):
            if isinstance(n,ast.Name) and n.id not in (*ARGUMENTS,"min","max"):
                reject()
            if isinstance(n,ast.Constant) and not (
               n.value is None or type(n.value) is int and -10000<=n.value<=10000):
                reject()
            if isinstance(n,ast.Call) and (
                not isinstance(n.func,ast.Name) or n.func.id not in ("min","max")
                or not 1<=len(n.args)<=3 or n.keywords):
                reject()
        else:reject("AST_UNSUPPORTED_NODE")
    if any(not isinstance(n,statements) for n in f.body):reject()
    return f

def guarded(value):
    if type(value) is int and abs(value)>100_000_000:
        reject("INTEGER_GROWTH_LIMIT")
    if value is not None and type(value) not in (int,bool):
        reject("INVALID_VALUE")
    return value

def expression(node,env,depth=0):
    if depth>32:reject("RECURSION_LIMIT")
    sub=lambda n:expression(n,env,depth+1)
    if isinstance(node,ast.Constant):return node.value
    if isinstance(node,ast.Name):
        if node.id not in env:reject()
        return env[node.id]
    if isinstance(node,ast.UnaryOp):
        a=sub(node.operand)
        if isinstance(node.op,ast.USub):return guarded(-a)
        if isinstance(node.op,ast.UAdd):return guarded(+a)
        if isinstance(node.op,ast.Not):return not a
        reject()
    if isinstance(node,ast.BinOp):
        a,b=sub(node.left),sub(node.right)
        if type(a) is not int or type(b) is not int:reject()
        if isinstance(node.op,ast.Add):return guarded(a+b)
        if isinstance(node.op,ast.Sub):return guarded(a-b)
        if isinstance(node.op,ast.Mult):return guarded(a*b)
        if isinstance(node.op,ast.Pow):
            if not 0<=b<=20:reject("EXPONENT_LIMIT")
            return guarded(a**b)
        reject()
    if isinstance(node,ast.BoolOp):
        if isinstance(node.op,ast.And):
            for x in node.values:
                if not sub(x):return False
            return True
        if isinstance(node.op,ast.Or):
            for x in node.values:
                if sub(x):return True
            return False
        reject()
    if isinstance(node,ast.Compare):
        prior=sub(node.left)
        for op,right in zip(node.ops,node.comparators):
            curr=sub(right)
            if isinstance(op,ast.Lt):ok=prior<curr
            elif isinstance(op,ast.LtE):ok=prior<=curr
            elif isinstance(op,ast.Gt):ok=prior>curr
            elif isinstance(op,ast.GtE):ok=prior>=curr
            elif isinstance(op,ast.Eq):ok=prior==curr
            elif isinstance(op,ast.NotEq):ok=prior!=curr
            else:reject()
            if not ok:return False
            prior=curr
        return True
    if isinstance(node,ast.IfExp):return sub(node.body) if sub(node.test) else sub(node.orelse)
    if isinstance(node,ast.Call):
        vals=[sub(x) for x in node.args]
        if any(type(x) is not int for x in vals):reject()
        return guarded(min(vals) if node.func.id=="min" else max(vals))
    reject("UNKNOWN_EXPRESSION")

def interpret(function,inputs):
    env=dict(zip(ARGUMENTS,inputs))
    def statements(body,depth):
        if depth>12:reject("NESTED_IF_LIMIT")
        for stmt in body:
            if isinstance(stmt,ast.Return):
                return True,guarded(expression(stmt.value,env) if stmt.value is not None else None)
            if isinstance(stmt,ast.If):
                selected=stmt.body if expression(stmt.test,env) else stmt.orelse
                returned,value=statements(selected,depth+1)
                if returned:return True,value
                continue
            reject("UNKNOWN_STATEMENT")
        return False,None
    returned,value=statements(function.body,0)
    if not returned:reject("MISSING_RETURN")
    return value

def evaluate(code):
    f=parse_subset(code)
    results=[]
    for input_values,expected in CASES:
        try:
            value=interpret(f,input_values)
            passed=type(value) is type(expected) and value==expected
            results.append(passed)
        except (CodeRejected,ArithmeticError,TypeError,ValueError,OverflowError):
            results.append(False)
    return {"passed":sum(results),"total":len(results),
            "all_passed":all(results),"failed_case_indices":[i for i,v in enumerate(results) if not v]}

def validate_receipt(doc,index):
    if(not isinstance(doc,dict) or doc.get("schema")!="commandcenter.nvidia_fixed_code_repair.v1" or
       doc.get("model_index")!=index or doc.get("model")!=MODELS[index] or
       doc.get("task_id")!="RETRY_DEADLINE_01" or doc.get("provider_calls")!=1):
        raise RuntimeError("SYNTHETIC_CODE_RECEIPT_REJECTED")
    status=doc.get("status")
    if status=="rate_limited":raise RuntimeError("NVIDIA_429_HELD_ZERO_AUTORETRY")
    if status!="candidate_unexecuted" or doc.get("http_status")!=200:
        raise RuntimeError("NVIDIA_CODE_CANDIDATE_NOT_ADMITTED")
    code=doc.get("code")
    if not isinstance(code,str):raise RuntimeError("NO_SYNTHETIC_SOURCE_ARTIFACT")
    return code

def call(index):
    payload=json.dumps({"model_index":index},separators=(",",":")).encode("utf-8")
    request=Request(URL,data=payload,headers={"Content-Type":"application/json"},method="POST")
    try:
        with urlopen(request,timeout=45) as r:
            body=r.read(9000)
    except HTTPError as err:
        body=err.read(9000)
    except (URLError,TimeoutError,OSError) as err:
        raise RuntimeError("FIXED_CODE_PRIVATE_TRANSPORT_HELD") from err
    try:return json.loads(body)
    except ValueError as err:raise RuntimeError("INVALID_FIXED_CODE_RECEIPT") from err

def main(index):
    if type(index)!=int or index not in (0,1):
        raise RuntimeError("INVALID_FIXED_MODEL_SELECTION")
    rows=[]
    for i in (index,):
        proc=open_caller(Path(os.environ.get("RUNNER_TEMP","/tmp"))/f"nvidia_code_{i}.log")
        try:doc=call(i)
        finally:close_caller(proc)
        code=validate_receipt(doc,i)
        grading=evaluate(code) # AST-only, never Python exec/eval
        receipt={"schema":"commandcenter.nvidia_verified_synthetic_code.v1",
                 "model":MODELS[i],"task_id":"RETRY_DEADLINE_01",
                 "http_status":200,"latency_ms":doc.get("elapsed_ms"),
                 "tests_passed":grading["passed"],"tests_total":grading["total"],
                 "all_tests_passed":grading["all_passed"],
                 "failed_case_indices":grading["failed_case_indices"],
                 "model_code_executed":False,"production_patch_applied":False,
                 "private_inputs_exposed":False}
        rows.append(receipt)
        print("NVIDIA_CODE_REPAIR_OBSERVATION="+json.dumps(receipt,sort_keys=True,separators=(",",":")),flush=True)
        if grading["all_passed"]:
            # Source passed whitelist and pure AST interpretation. Public,
            # fictional code only. No private model prompts or credentials.
            print("NVIDIA_VERIFIED_SYNTHETIC_PATCH="+json.dumps({
                "model":MODELS[i],"path":"synthetic/retry_schedule.py",
                "source":code},sort_keys=True,separators=(",",":")),flush=True)
    print("NVIDIA_CODE_REPAIR_SUMMARY="+json.dumps({
      "models":len(rows),"provider_calls_reserved":1,"role":"code_repair",
      "full_correct_count":sum(x["all_tests_passed"] for x in rows),
      "tests_per_model":len(CASES),"production_routing":False,
      "manual_code_execution":False,"automatic_commit":False,
      "other_project_source_used":False
    },sort_keys=True,separators=(",",":")),flush=True)

if __name__=="__main__":
    try:
        if len(sys.argv)!=2 or sys.argv[1] not in ("poolside","minimax"):
            raise RuntimeError("ONLY_FIXED_MODEL_ARG_ALLOWED")
        main(0 if sys.argv[1]=="poolside" else 1)
    except (RuntimeError,CodeRejected,OSError,ValueError) as err:
        print("NVIDIA_CODE_REPAIR_HELD="+str(err),flush=True)
        raise SystemExit(1)
