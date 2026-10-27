"""AIKO B8 cross-run evidence probe. Public synthetic GitHub Actions artifacts ONLY.

This proves one GitHub runner can retrieve/verify a PREVIOUS run's durable synthetic
receipt without ACER. It DOES NOT prove a real Growth release or physical ACER-off.
"""
import hashlib, io, json, os, pathlib, sys, urllib.error, urllib.parse, urllib.request, zipfile
REPO="jeanf1982-web/aiko-cloud-worker"
REPO_ID=1408649300
ARTIFACT="aiko-b8-003-isolated-recovery-proof"
FILENAME="b8-003-real-process-crash-proof.json"
API="https://api.github.com/repos/"+REPO+"/actions/artifacts?per_page=100"

def verify_artifact_meta(meta,current_run):
    src=meta.get("workflow_run") or {}
    return (
        meta.get("name")==ARTIFACT and meta.get("expired") is False
        and src.get("repository_id")==REPO_ID and src.get("head_repository_id")==REPO_ID
        and str(src.get("id") or "")!=str(current_run)
        and isinstance(src.get("head_sha"),str) and len(src["head_sha"])==40
        and isinstance(meta.get("digest"),str) and meta["digest"].startswith("sha256:")
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
        and r.get("actual_child_processes_killed")==100
        and isinstance(r.get("cases"),dict)
        and bool(r["cases"])
        and all(isinstance(n,int) and n==100 for n in r["cases"].values())
        and r.get("production_deployment") is False
        and r.get("real_growth_source") is False
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
    with urllib.request.urlopen(urllib.request.Request(dest,headers={"User-Agent":"AIKO-crossrun-proof"}),timeout=15) as f:
        content=f.read(3_000_001)
        if len(content)>3_000_000:raise ValueError("ZIP_TOO_LARGE")
        return content

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
    # Use latest eligible artifact, never the one produced by the current run.
    proof=verify_archive(get_artifact_zip(accepted[0]["id"],token),accepted[0])
    proof.update(schema="AIKO_B8_CROSS_RUN_ARTIFACT_EVIDENCE_V1",
        current_run_id=int(nowrun),artifact_id=accepted[0]["id"],
        acer_physical_off_verified=False if False else False,
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
