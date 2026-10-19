"""Independent cloud sandbox: deterministic generated JSON validation utility and tests."""
import ast,hashlib,json,pathlib,subprocess,sys,datetime
OUT=pathlib.Path("cloud_sandbox_artifacts")
OUT.mkdir(exist_ok=True)
source='''def validate_json_text(text):
    if not isinstance(text,str) or len(text)>10000:
        return {"valid":False,"reason":"INVALID_INPUT"}
    try:
        value=json.loads(text)
    except ValueError:
        return {"valid":False,"reason":"BAD_JSON"}
    return {"valid":True,"shape":type(value).__name__}
'''
target=OUT/"aiko_json_validator_candidate.py"
target.write_text(source,encoding="utf-8")
ast.parse(source)
ns={}
exec(compile(source,str(target),"exec"),{"__builtins__":{"str":str,"isinstance":isinstance,"len":len,"type":type,"ValueError":ValueError},"json":json},ns)
# Compile under restricted builtins and reject any unexpected behavior.
checks=[
 ('{"a":1}',True), ('[1,2]',True), ('{"oops":}',False), ('',False), ('null',True), ('["x"]',True),
 ('{"x":true}',True), ('[',False)]
results=[]
for text,expected in checks:
 result=ns["validate_json_text"](text)
 results.append({"case":len(results)+1,"pass":result.get("valid") is expected})
receipt={"schema":"AIKO_CLOUD_SANDBOX_CANDIDATE_V1","created_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),
 "generated_candidate":"aiko_json_validator_candidate.py","sha256":hashlib.sha256(target.read_bytes()).hexdigest(),
 "tests_passed":sum(x["pass"] for x in results),"tests_total":len(results),"cases":results,
 "cloud_sandbox_certified":all(x["pass"] for x in results),"local_deployed":False,
 "growth_autonomous_end_to_end_certified":False,"source_origin":"deterministic_safe_cloud_template"}
(OUT/"certification.json").write_text(json.dumps(receipt,indent=2),encoding="utf-8")
print(json.dumps({"passed":receipt["tests_passed"],"total":receipt["tests_total"],"sandbox_certified":receipt["cloud_sandbox_certified"]}))
if not receipt["cloud_sandbox_certified"]:raise SystemExit(2)
