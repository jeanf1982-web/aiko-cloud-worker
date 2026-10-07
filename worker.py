from __future__ import annotations
import argparse, base64, gzip, hashlib, json, os, subprocess, sys, tempfile, time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

MAX_PAYLOAD = 1024 * 1024
MAX_FUTURE_S = 3600
NODE_ID = "AIKO_GITHUB_CLOUD_WORKER_V1"
ALLOWED = {"sha256", "json_canonicalize", "forensics_merkle", "hash_parallel"}


def canonical_manifest(job_type, nonce, expires_at, payload_sha256):
    obj = {"expires_at": int(expires_at), "job_type": job_type, "nonce": nonce, "payload_sha256": payload_sha256}
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def verify_ed25519(pub_pem: Path, message: bytes, signature: bytes):
    with tempfile.TemporaryDirectory() as d:
        d = Path(d); msg = d / "msg.bin"; sig = d / "sig.bin"
        msg.write_bytes(message); sig.write_bytes(signature)
        p = subprocess.run(["openssl", "pkeyutl", "-verify", "-pubin", "-inkey", str(pub_pem), "-rawin", "-in", str(msg), "-sigfile", str(sig)], capture_output=True, text=True)
        return p.returncode == 0


def hash_chain(args):
    seed, rounds = args
    x = seed.encode()
    for _ in range(rounds):
        x = hashlib.sha256(x).digest()
    return hashlib.sha256(x).hexdigest()


def merkle_root(items):
    nodes = [hashlib.sha256(str(x).encode()).digest() for x in items]
    if not nodes:
        return hashlib.sha256(b"").hexdigest()
    while len(nodes) > 1:
        if len(nodes) % 2:
            nodes.append(nodes[-1])
        nodes = [hashlib.sha256(nodes[i] + nodes[i+1]).digest() for i in range(0, len(nodes), 2)]
    return nodes[0].hex()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--job-type", required=True)
    ap.add_argument("--payload-b64", required=True)
    ap.add_argument("--nonce", required=True)
    ap.add_argument("--expires-at", required=True, type=int)
    ap.add_argument("--payload-sha256", required=True)
    ap.add_argument("--signature-b64", required=True)
    ap.add_argument("--public-key", default="keys/aiko_cloud_worker_public.pem")
    a = ap.parse_args()

    now = int(time.time())
    if a.job_type not in ALLOWED:
        raise SystemExit("JOB_TYPE_DENIED")
    if a.expires_at < now - 60 or a.expires_at > now + MAX_FUTURE_S:
        raise SystemExit("MANIFEST_EXPIRED_OR_TOO_FAR")
    payload = base64.b64decode(a.payload_b64, validate=True)
    if len(payload) > MAX_PAYLOAD:
        raise SystemExit("PAYLOAD_TOO_LARGE")
    calc = hashlib.sha256(payload).hexdigest()
    if calc != a.payload_sha256:
        raise SystemExit("PAYLOAD_SHA_MISMATCH")
    msg = canonical_manifest(a.job_type, a.nonce, a.expires_at, a.payload_sha256)
    sig = base64.b64decode(a.signature_b64, validate=True)
    if not verify_ed25519(Path(a.public_key), msg, sig):
        raise SystemExit("BAD_SIGNATURE")

    started = time.time(); result = None
    if a.job_type == "sha256":
        result = {"sha256": calc, "bytes": len(payload)}
    elif a.job_type == "json_canonicalize":
        obj = json.loads(payload.decode("utf-8"))
        canon = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        result = {"canonical_b64": base64.b64encode(canon).decode(), "canonical_sha256": hashlib.sha256(canon).hexdigest()}
    elif a.job_type == "forensics_merkle":
        obj = json.loads(payload.decode("utf-8")); items = obj.get("items", [])
        if not isinstance(items, list) or len(items) > 10000:
            raise SystemExit("ITEMS_DENIED")
        result = {"count": len(items), "merkle_root": merkle_root(items)}
    elif a.job_type == "hash_parallel":
        obj = json.loads(payload.decode("utf-8")); lanes = int(obj.get("lanes", 4)); rounds = int(obj.get("rounds", 200000)); seed = str(obj.get("seed", "AIKO"))
        if lanes < 1 or lanes > 4 or rounds < 1 or rounds > 2000000:
            raise SystemExit("COMPUTE_LIMIT_DENIED")
        with ProcessPoolExecutor(max_workers=lanes) as ex:
            outs = list(ex.map(hash_chain, [(f"{seed}:{i}", rounds) for i in range(lanes)]))
        result = {"lanes": lanes, "rounds": rounds, "lane_hashes": outs, "aggregate_sha256": hashlib.sha256("".join(outs).encode()).hexdigest()}

    out = {
        "schema": "AIKO_GITHUB_CLOUD_WORKER_RESULT_V1",
        "node_id": NODE_ID,
        "job_type": a.job_type,
        "nonce": a.nonce,
        "payload_sha256": a.payload_sha256,
        "started_at": started,
        "finished_at": time.time(),
        "runner": {"os": os.getenv("RUNNER_OS"), "arch": os.getenv("RUNNER_ARCH"), "github_run_id": os.getenv("GITHUB_RUN_ID"), "github_sha": os.getenv("GITHUB_SHA")},
        "result": result,
        "cost_eur": 0,
        "generic_shell": False,
    }
    raw = json.dumps(out, sort_keys=True, indent=2).encode()
    Path("result.json").write_bytes(raw)
    att = {"result_sha256": hashlib.sha256(raw).hexdigest(), "nonce": a.nonce, "payload_sha256": a.payload_sha256, "node_id": NODE_ID}
    Path("attestation.json").write_text(json.dumps(att, indent=2), encoding="utf-8")
    print(json.dumps(att))

if __name__ == "__main__":
    main()
