"""Independent restricted benchmark for model-generated AIKO-only text plugin."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import sys

DIR=Path("artifacts/aiko-growth-models")
RECEIPT=DIR/"generation_receipt.json"


def evaluate():
    generated=json.loads(RECEIPT.read_text(encoding="utf8"))
    output={"schema":"AIKO_MODEL_CANDIDATE_INDEPENDENT_QA_V1",
            "generator_status":generated.get("status"),
            "generator_commit":generated.get("head_sha"),
            "run_id":generated.get("run_id"),
            "candidate_sha256":generated.get("candidate_sha256"),
            "production_deployment":False,"certified_2_of_2":False,
            "growth_v3_source":False,"status":"HOLD_OR_REJECTED",
            "cases_passed":0,"cases_total":100,
            "owner_project":"AIKO"}
    if generated.get("status")!="GENERATED_PENDING_INDEPENDENT_TEST":
        return output
    src=(DIR/"candidate.py").read_bytes()
    if hashlib.sha256(src).hexdigest()!=generated.get("candidate_sha256"):
        output["status"]="REJECTED_SOURCE_HASH"
        return output
    # The child receives NO GITHUB_TOKEN, no GH_MODELS_TOKEN, no repo credentials;
    # the source is public synthetic output, not a privileged actor.
    harness=r'''
import importlib.util,json,random,sys
candidate=sys.argv[1]
spec=importlib.util.spec_from_file_location("generated_aiko_sandbox",candidate)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
cases=[]
texts=["Ciao mondo!","Perché sì?","mare e montagna","hello 123","qualità è importante"]
for i in range(100):
    phrase=texts[i%len(texts)]
    if i%4 == 0:
        user="Per favore rispondi in maiuscolo"
        expected=phrase.upper()
    elif i%4 == 1:
        user="SCRIVI TUTTO IN MAIUSCOLO, grazie."
        expected=phrase.upper()
    elif i%4 == 2:
        user="Rispondi normalmente"
        expected=phrase
    else:
        user="Non scrivere tutto in maiuscolo, grazie"
        expected=phrase
    cases.append((user,phrase,expected))
counts=0
for user,reply,expected in cases:
    before=m.preprocess(user,{})
    actual=m.postprocess(user,reply,{})
    if before==user and actual==expected:
        counts+=1
test=m.self_test()
print(json.dumps({"passed":counts,"total":100,"self_test":isinstance(test,dict) and test.get("ok") is True}))
'''
    def limits():
        resource.setrlimit(resource.RLIMIT_CPU,(3,3))
        resource.setrlimit(resource.RLIMIT_AS,(125*1024*1024,125*1024*1024))
        resource.setrlimit(resource.RLIMIT_FSIZE,(1024*1024,1024*1024))
    try:
        run=subprocess.run([sys.executable,"-I","-S","-c",harness,str((DIR/"candidate.py").resolve())],
                           cwd="/tmp",capture_output=True,text=True,timeout=5,
                           env={"PATH":"/usr/bin:/bin","PYTHONNOUSERSITE":"1"},
                           preexec_fn=limits,check=False)
        if run.returncode!=0:
            output["status"]="REJECTED_SANDBOX_EXIT"
            return output
        result=json.loads(run.stdout.strip().splitlines()[-1])
        output["cases_passed"]=int(result.get("passed",0))
        output["self_test_pass"]=bool(result.get("self_test"))
        output["status"]=("SANDBOX_PASS_NOT_DEPLOYED" if
                          result.get("passed")==100 and result.get("self_test")
                          else "REJECTED_BEHAVIOR")
    except (ValueError,IndexError,KeyError,subprocess.TimeoutExpired, OSError):
        output["status"]="REJECTED_SANDBOX_TIMEOUT_OR_FORMAT"
    return output


def main():
    obj=evaluate()
    DIR.mkdir(parents=True,exist_ok=True)
    (DIR/"independent_qa_receipt.json").write_text(
        json.dumps(obj,sort_keys=True,indent=2)+"\n",encoding="utf8")
    print("AIKO_GROWTH_MODELS_INDEPENDENT_QA",obj["status"],
          str(obj["cases_passed"])+"/100")
    # Fail closed but do not create spurious 'runner failed' email on free quota
    # exhaustion or rejected candidate. Status is recorded in artifact, not PASS.


if __name__=="__main__":
    main()
