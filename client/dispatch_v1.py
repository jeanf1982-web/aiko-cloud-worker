from __future__ import annotations
import base64, hashlib, json, os, subprocess, sys, tempfile, time, uuid
from pathlib import Path
from cryptography.hazmat.primitives import serialization

REPO = "jeanf1982-web/aiko-cloud-worker"
WORKFLOW = "aiko-cloud-worker.yml"
ROOT = Path(r"C:\AIKO_BRIDGE\cloud_worker_github")
PRIVATE_KEY = ROOT / "keys" / "aiko_cloud_worker_private.pem"
NONCE_REGISTRY = ROOT / "client" / "nonce_registry.json"
RESULTS = ROOT / "results"
RESULTS.mkdir(parents=True, exist_ok=True)


def sh(args, timeout=300):
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(f"command failed {p.returncode}: {' '.join(args)}\n{p.stdout}\n{p.stderr}")
    return p.stdout.strip()


def load_registry():
    try:
        return set(json.loads(NONCE_REGISTRY.read_text(encoding="utf-8")))
    except Exception:
        return set()


def save_registry(values):
    NONCE_REGISTRY.write_text(json.dumps(sorted(values), indent=2), encoding="utf-8")


def manifest_bytes(job_type, nonce, expires_at, payload_sha256):
    obj = {"expires_at": int(expires_at), "job_type": job_type, "nonce": nonce, "payload_sha256": payload_sha256}
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def sign(message: bytes):
    key = serialization.load_pem_private_key(PRIVATE_KEY.read_bytes(), password=None)
    return key.sign(message)


def dispatch(job_type: str, payload: bytes, ttl_s=900):
    used = load_registry()
    nonce = uuid.uuid4().hex
    if nonce in used:
        raise RuntimeError("nonce collision")
    payload_sha = hashlib.sha256(payload).hexdigest()
    expires_at = int(time.time()) + int(ttl_s)
    sig = sign(manifest_bytes(job_type, nonce, expires_at, payload_sha))
    payload_b64 = base64.b64encode(payload).decode()
    sig_b64 = base64.b64encode(sig).decode()
    before = int(time.time())
    sh(["gh", "workflow", "run", WORKFLOW, "--repo", REPO, "--ref", "main",
        "-f", f"job_type={job_type}", "-f", f"payload_b64={payload_b64}", "-f", f"nonce={nonce}",
        "-f", f"expires_at={expires_at}", "-f", f"payload_sha256={payload_sha}", "-f", f"signature_b64={sig_b64}"], timeout=60)
    run_id = None
    for _ in range(30):
        rows = json.loads(sh(["gh", "run", "list", "--repo", REPO, "--workflow", WORKFLOW, "--event", "workflow_dispatch", "--limit", "20", "--json", "databaseId,displayTitle,createdAt,status,conclusion"], timeout=30) or "[]")
        for r in rows:
            if nonce in (r.get("displayTitle") or ""):
                run_id = str(r["databaseId"]); break
        if run_id: break
        time.sleep(2)
    if not run_id:
        raise RuntimeError("workflow run not found")
    sh(["gh", "run", "watch", run_id, "--repo", REPO, "--exit-status"], timeout=1200)
    outdir = RESULTS / nonce
    outdir.mkdir(parents=True, exist_ok=True)
    sh(["gh", "run", "download", run_id, "--repo", REPO, "--name", f"aiko-result-{nonce}", "--dir", str(outdir)], timeout=120)
    result = json.loads((outdir / "result.json").read_text(encoding="utf-8"))
    att = json.loads((outdir / "attestation.json").read_text(encoding="utf-8"))
    raw = (outdir / "result.json").read_bytes()
    checks = {
        "nonce": result.get("nonce") == nonce == att.get("nonce"),
        "payload_sha": result.get("payload_sha256") == payload_sha == att.get("payload_sha256"),
        "node_id": result.get("node_id") == "AIKO_GITHUB_CLOUD_WORKER_V1",
        "result_sha": hashlib.sha256(raw).hexdigest() == att.get("result_sha256"),
        "cost_zero": result.get("cost_eur") == 0,
        "generic_shell_false": result.get("generic_shell") is False,
    }
    if not all(checks.values()):
        raise RuntimeError(f"result validation failed: {checks}")
    used.add(nonce); save_registry(used)
    receipt = {"schema":"AIKO_GITHUB_CLOUD_DISPATCH_RECEIPT_V1","run_id":run_id,"nonce":nonce,"job_type":job_type,"checks":checks,"result":result,"attestation":att,"accepted_at":time.time()}
    (outdir / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return receipt


if __name__ == "__main__":
    job_type = sys.argv[1] if len(sys.argv) > 1 else "sha256"
    if len(sys.argv) > 2:
        payload = Path(sys.argv[2]).read_bytes()
    else:
        payload = b"AIKO_GITHUB_CLOUD_WORKER_SMOKE_TEST_V1"
    print(json.dumps(dispatch(job_type, payload), indent=2))
