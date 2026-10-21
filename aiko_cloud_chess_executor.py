"""AIKO cloud-safe chess workload. Never execute generated or user-provided code."""
import datetime,hashlib,json,os,pathlib
from project_boundary import classify,inspect_queue
ROOT=pathlib.Path(__file__).resolve().parent
JOBS=ROOT/"aiko_cloud_jobs.json"
OUTPUT=ROOT/"aiko_cloud_results.json"
def decide(job):
    gate=classify(job)
    if not gate["allowed"]:
        return {"state":gate["state"],"reason":"AIKO ownership, privacy or capability gate","next_action":"HOLD_AND_REVIEW_WITH_PROJECT_OWNER","automatic_reassignment":False}
    if job.get("kind")=="chess_options":
        options=[{"move":"DOCUMENT_REUSABLE_TEST","score":10},{"move":"DESIGN_SANDBOX_CASE","score":8},{"move":"WAIT_FOR_LOCAL_VALIDATION","score":5}]
        return {"state":"CLOUD_DONE_PENDING_LOCAL_VALIDATION","options":options,"recommended":options[0]["move"]}
    if job.get("kind")=="json_validation":
        raw=job.get("payload")
        if not isinstance(raw,str) or len(raw)>10000:return {"state":"REJECTED_SIZE"}
        try:
            obj=json.loads(raw)
            return {"state":"CLOUD_DONE_PENDING_LOCAL_VALIDATION","valid":True,"value_sha256":hashlib.sha256(raw.encode()).hexdigest(),"shape":type(obj).__name__}
        except ValueError:return {"state":"CLOUD_DONE_PENDING_LOCAL_VALIDATION","valid":False}
    return {"state":"REJECTED_UNKNOWN_JOB"}
def main():
    doc=json.loads(JOBS.read_text(encoding="utf-8"))
    boundary_review=inspect_queue(doc)
    jobs=doc.get("jobs",[])
    if not isinstance(jobs,list) or len(jobs)>50:raise ValueError("bad queue")
    seen=set();results=[]
    for job in jobs:
        jid=job.get("id")
        if not isinstance(jid,str) or not jid.isascii() or not jid.replace("-","").replace("_","").isalnum() or jid in seen:raise ValueError("invalid job id")
        seen.add(jid)
        result=decide(job)
        results.append({"id":jid,"input_sha256":hashlib.sha256(json.dumps(job,sort_keys=True).encode()).hexdigest(),**result})
    out={"schema":"AIKO_CLOUD_CHESS_RESULTS_V1","created_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),"jobs":results,"cloud_authorized_to_deploy":False,"project_boundary":boundary_review}
    OUTPUT.write_text(json.dumps(out,indent=2),encoding="utf-8")
    print(json.dumps({"processed":len(results),"completed":sum(x["state"]=="CLOUD_DONE_PENDING_LOCAL_VALIDATION" for x in results),"rejected":sum(x["state"].startswith("REJECTED") for x in results)}))
if __name__=="__main__":main()
