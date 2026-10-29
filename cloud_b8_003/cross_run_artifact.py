"""AIKO B8 cross-run evidence probe. Public synthetic GitHub Actions artifacts ONLY.

This proves one GitHub runner can retrieve/verify a PREVIOUS run's durable synthetic
receipt without ACER. It DOES NOT prove a real Growth release or physical ACER-off.
"""
import hashlib, io, json, os, pathlib, re, sys, time, urllib.error, urllib.parse, urllib.request, zipfile
from datetime import datetime, timezone
REPO="jeanf1982-web/aiko-cloud-worker"
REPO_ID=1408649300
ARTIFACT="aiko-b8-003-isolated-recovery-proof"
FILENAME="b8-003-real-process-crash-proof.json"
API="https://api.github.com/repos/"+REPO+"/actions/artifacts?per_page=100"
MAX_ARTIFACT_AGE_S=48*3600
APPROVED_WORKFLOW_ID=388776488
APPROVED_WORKFLOW_PATH=".github/workflows/aiko-cloud-evolution-quality-gate.yml"
REQUIRED_RECOVERY_CASES=frozenset((
    "child_process_crashes", "reclaims", "stale_epoch_rejections",
    "no_duplicate_file_write", "unique_effect_receipts"))

def _fresh_utc_stamp(iso,now=None):
    if not isinstance(iso,str):return False
    try:
        dt=datetime.fromisoformat(iso.replace("Z","+00:00"))
        if dt.tzinfo is None:return False
        age=(time.time() if now is None else now)-dt.timestamp()
        return 0<=age<=MAX_ARTIFACT_AGE_S
    except (ValueError,OverflowError,TypeError):
        return False

def verify_artifact_meta(meta,current_run,now=None):
    if not isinstance(meta,dict):return False
    src=meta.get("workflow_run") or {}
    if not isinstance(src,dict):return False
    run_id=src.get("id")
    return (
        meta.get("name")==ARTIFACT and meta.get("expired") is False
        and src.get("repository_id")==REPO_ID and src.get("head_repository_id")==REPO_ID
        and type(run_id) is int and run_id>0
        and isinstance(current_run,str) and current_run.isdecimal() and str(run_id)!=current_run
        and isinstance(src.get("head_sha"),str)
        and re.fullmatch(r"[0-9a-fA-F]{40}",src["head_sha"]) is not None
        and isinstance(meta.get("digest"),str)
        and re.fullmatch(r"sha256:[0-9a-fA-F]{64}",meta["digest"]) is not None
        and _fresh_utc_stamp(meta.get("created_at"),now)
    )

def verify_source_workflow_run(run,meta):
    """Authorize the preceding artifact's PRODUCING workflow via GitHub API."""
    if not isinstance(run,dict) or not isinstance(meta,dict):
        return False
    src=meta.get("workflow_run")
    if not isinstance(src,dict):return False
    branch=run.get("head_branch")
    return (
        type(run.get("id")) is int and run["id"]==src.get("id")
        and type(run.get("workflow_id")) is int
        and run["workflow_id"]==APPROVED_WORKFLOW_ID
        and run.get("path")==APPROVED_WORKFLOW_PATH
        and run.get("status")=="completed" and run.get("conclusion")=="success"
        and run.get("event") in ("push","workflow_dispatch","schedule")
        and isinstance(branch,str) and
        (branch=="main" or (branch.startswith("aiko-") and len(branch)<=100))
        and run.get("head_sha")==src.get("head_sha")
        and isinstance(run.get("head_repository"),dict)
        and run["head_repository"].get("id")==REPO_ID
        and run.get("repository",{}).get("id")==REPO_ID
    )

def verify_archive(raw,meta):
    want=meta["digest"].split(":",1)[1]
    if len(want)!=64 or hashlib.sha256(raw).hexdigest()!=want:
        raise ValueError("GITHUB_ARTIFACT_DIGEST_MISMATCH")
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names=z.namelist()
        if names.count(FILENAME)!=1 or any(n.startswith("/") or ".." in pathlib.PurePosixPath(n).parts for n in names):
            raise ValueError("UNEXPECTED_OR_TRAVERSAL_ARCHIVE")
        info=z.getinfo(FILENAME)
        if info.file_size>250000:raise ValueError("RECEIPT_TOO_LARGE")
        r=json.loads(z.read(FILENAME))
    w=meta["workflow_run"]
    if not (
        r.get("schema")=="AIKO_B8_003_REAL_PROCESS_CRASH_QA_V1"
        and r.get("repository")==REPO
        and str(r.get("run_id"))==str(w["id"])
        and r.get("commit")==w["head_sha"]
        and type(r.get("actual_child_processes_killed")) is int
        and r["actual_child_processes_killed"]==100
        and type(r.get("cases")) is dict
        and set(r["cases"])==REQUIRED_RECOVERY_CASES
        and all(type(r["cases"][k]) is int and r["cases"][k]==100
                for k in REQUIRED_RECOVERY_CASES)
        and r.get("status")=="CLOUD_SANDBOX_CRASH_RECOVERY_PASS"
        and r.get("source")=="EPHEMERAL_GITHUB_LINUX_RUNNER"
        and r.get("production_deployment") is False
        and r.get("real_growth_source") is False
        and r.get("local_acer_changed") is False
        and r.get("real_multi_provider_failover") is False
        and r.get("B8_global_certified") is False
    ):
        raise ValueError("RECEIPT_RUN_BINDING_OR_CASE_CONTRACT_FAILED")
    return {"previous_run_id":int(w["id"]),"previous_commit":w["head_sha"],
            "archive_sha256":want,"actual_crash_recovery_probes":100,
            "receipt_scope":"SYNTHETIC_CLOUD_QA_ONLY"}

def headers(token):
    return {"Authorization":"Bearer "+token,"Accept":"application/vnd.github+json",
      "X-GitHub-Api-Version":"2022-11-28","User-Agent":"AIKO-crossrun-proof"}

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):return None

def get_artifact_zip(artifact_id,token):
    uri="https://api.github.com/repos/"+REPO+"/actions/artifacts/"+str(artifact_id)+"/zip"
    opener=urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(urllib.request.Request(uri,headers=headers(token)),timeout=15) as f:
            content=f.read(3_000_001)
            if len(content)>3_000_000:raise ValueError("ZIP_TOO_LARGE")
            return content
    except urllib.error.HTTPError as e:
        if e.code not in (301,302,303,307,308):raise
        dest=e.headers.get("Location","")
    target=urllib.parse.urlparse(dest)
    host=target.hostname or ""
    if (target.scheme!="https" or not dest or target.username or target.password
        or not (host.endswith(".blob.core.windows.net") or host.endswith(".githubusercontent.com")
                or host in ("release-assets.githubusercontent.com","pipelines.actions.githubusercontent.com"))):
        raise ValueError("UNTRUSTED_GITHUB_ARTIFACT_REDIRECT")
    # Never pass bearer authentication to temporary signed artifact storage.
    # No implicit second redirect: a signed storage URL must be a terminal hop.
    try:
        with opener.open(urllib.request.Request(dest,headers={"User-Agent":"AIKO-crossrun-proof"}),timeout=15) as f:
            content=f.read(3_000_001)
            if len(content)>3_000_000:raise ValueError("ZIP_TOO_LARGE")
            return content
    except urllib.error.HTTPError as e:
        if e.code in (301,302,303,307,308):
            raise ValueError("SECOND_ARTIFACT_REDIRECT_DENIED") from e
        raise

def main():
    if os.environ.get("GITHUB_ACTIONS")!="true" or os.environ.get("GITHUB_REPOSITORY")!=REPO:
        raise RuntimeError("EXPECTED_GITHUB_ACTIONS_REPO_ONLY")
    token=os.environ.get("GH_TOKEN_FOR_ARTIFACT_READ","")
    nowrun=os.environ.get("GITHUB_RUN_ID","")
    if not token or not nowrun.isdigit():raise RuntimeError("GITHUB_READ_TOKEN_OR_RUN_MISSING")
    with urllib.request.urlopen(urllib.request.Request(API,headers=headers(token)),timeout=15) as f:
        artifacts=json.load(f)["artifacts"]
    accepted=[a for a in artifacts if verify_artifact_meta(a,nowrun)]
    if not accepted:raise RuntimeError("PREVIOUS_RUN_ARTIFACT_NOT_FOUND")
    # API metadata and ZIP digest alone do not prove the trusted producer workflow.
    candidate=accepted[0]
    run_url="https://api.github.com/repos/"+REPO+"/actions/runs/"+str(candidate["workflow_run"]["id"])
    with urllib.request.urlopen(urllib.request.Request(run_url,headers=headers(token)),timeout=15) as f:
        original_run=json.load(f)
    if not verify_source_workflow_run(original_run,candidate):
        raise RuntimeError("UNTRUSTED_CROSSRUN_PRODUCER_WORKFLOW")
    proof=verify_archive(get_artifact_zip(candidate["id"],token),candidate)
    proof.update(schema="AIKO_B8_CROSS_RUN_ARTIFACT_EVIDENCE_V1",
        producer_workflow_id=APPROVED_WORKFLOW_ID,
        producer_workflow_path=APPROVED_WORKFLOW_PATH,
        producer_workflow_conclusion="success",
        current_run_id=int(nowrun),artifact_id=accepted[0]["id"],
        acer_physical_off_verified=False,
        full_growth_delivery_certified=False,release_authorized=False,
        production_writes=0)
    pathlib.Path("artifacts").mkdir(exist_ok=True)
    pathlib.Path("artifacts/b8-crossrun-artifact-proof.json").write_text(
        json.dumps(proof,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print("AIKO_B8_CROSSRUN_SYNTHETIC_ARTIFACT_PASS",proof["previous_run_id"],nowrun)
if __name__=="__main__":
    try:main()
    except Exception as e:
        print("AIKO_B8_CROSSRUN_HOLD",type(e).__name__,str(e)[:120])
        sys.exit(2)
