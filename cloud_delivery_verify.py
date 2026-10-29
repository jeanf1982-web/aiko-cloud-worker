"""AIKO-only independent cloud delivery verifier.

Runs as a distinct GitHub Actions step *after* the signed worker. It does
not trust the attestation alone and never authorizes a production release.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time


REPOSITORY = "jeanf1982-web/aiko-cloud-worker"
ALLOWED = frozenset(("sha256", "json_canonicalize", "forensics_merkle", "hash_parallel"))


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical_manifest(kind, nonce, expires, payload_hash):
    return json.dumps({
        "expires_at": int(expires),
        "job_type": kind,
        "nonce": nonce,
        "payload_sha256": payload_hash,
    }, separators=(",", ":"), sort_keys=True).encode()


def merkle(items):
    nodes = [hashlib.sha256(str(i).encode()).digest() for i in items]
    if not nodes:
        return hashlib.sha256(b"").hexdigest()
    while len(nodes) > 1:
        if len(nodes) % 2:
            nodes.append(nodes[-1])
        nodes = [hashlib.sha256(nodes[i] + nodes[i + 1]).digest()
                 for i in range(0, len(nodes), 2)]
    return nodes[0].hex()


def hash_chain(seed, rounds):
    value = seed.encode()
    for _ in range(rounds):
        value = hashlib.sha256(value).digest()
    return hashlib.sha256(value).hexdigest()


def check(test, reason):
    if not test:
        raise ValueError(reason)


def verify(root: Path, env: dict, public_key: Path) -> dict:
    """Raise on any missing, stale or altered receipt; emit no private payload."""
    check(env.get("GITHUB_ACTIONS") == "true", "NOT_GITHUB_RUNNER")
    check(env.get("GITHUB_REPOSITORY") == REPOSITORY, "FOREIGN_REPOSITORY")
    run_id = env.get("GITHUB_RUN_ID", "")
    commit = env.get("GITHUB_SHA", "")
    check(bool(re.fullmatch(r"[0-9]{1,22}", run_id)), "RUN_ID_INVALID")
    check(bool(re.fullmatch(r"[a-fA-F0-9]{40}", commit)), "COMMIT_INVALID")

    kind = env.get("AIKO_JOB_TYPE")
    nonce = env.get("AIKO_NONCE")
    check(kind in ALLOWED, "JOB_TYPE_DENIED")
    check(isinstance(nonce, str) and bool(re.fullmatch(r"[A-Za-z0-9_-]{8,80}", nonce)),
          "NONCE_FORMAT_INVALID")
    expires = int(env["AIKO_EXPIRES_AT"])
    now = int(time.time())
    check(now - 60 <= expires <= now + 3600, "MANIFEST_EXPIRY_OUT_OF_RANGE")
    payload = base64.b64decode(env["AIKO_PAYLOAD_B64"], validate=True)
    check(len(payload) <= 1024 * 1024, "PAYLOAD_TOO_LARGE")
    requested_hash = env["AIKO_PAYLOAD_SHA256"]
    check(digest(payload) == requested_hash, "PAYLOAD_SHA_MISMATCH")

    manifest = canonical_manifest(kind, nonce, expires, requested_hash)
    signature = base64.b64decode(env["AIKO_SIGNATURE_B64"], validate=True)
    with tempfile.TemporaryDirectory() as temp:
        msg = Path(temp) / "message"
        sig = Path(temp) / "signature"
        msg.write_bytes(manifest)
        sig.write_bytes(signature)
        valid = subprocess.run(
            ["openssl", "pkeyutl", "-verify", "-pubin", "-inkey", str(public_key),
             "-rawin", "-in", str(msg), "-sigfile", str(sig)],
            capture_output=True, timeout=10, check=False,
        )
        check(valid.returncode == 0, "INVALID_SIGNATURE")

    raw_result = (root / "result.json").read_bytes()
    result = json.loads(raw_result)
    att = json.loads((root / "attestation.json").read_text(encoding="utf-8"))
    check(result.get("schema") == "AIKO_GITHUB_CLOUD_WORKER_RESULT_V1", "BAD_SCHEMA")
    check(result.get("node_id") == "AIKO_GITHUB_CLOUD_WORKER_V1", "WRONG_NODE")
    check(result.get("job_type") == kind, "JOB_MISMATCH")
    check(result.get("nonce") == nonce, "NONCE_MISMATCH")
    check(result.get("payload_sha256") == requested_hash, "PAYLOAD_MISMATCH")
    started_at = result.get("started_at")
    finished_at = result.get("finished_at")
    check(type(started_at) in (int, float) and type(finished_at) in (int, float)
          and math.isfinite(started_at) and math.isfinite(finished_at),
          "RESULT_TIME_INVALID")
    check(0 <= finished_at - started_at <= 20 * 60 and finished_at <= time.time() + 60,
          "RESULT_TIMING_INVALID")
    runner = result.get("runner") or {}
    check(str(runner.get("github_run_id")) == run_id, "RUN_MISMATCH")
    check(str(runner.get("github_sha")).lower() == commit.lower(), "COMMIT_MISMATCH")
    check(att.get("result_sha256") == digest(raw_result), "RESULT_DIGEST_MISMATCH")
    check(att.get("node_id") == result["node_id"], "ATTESTED_NODE_MISMATCH")
    check(att.get("nonce") == nonce, "ATTESTED_NONCE_MISMATCH")
    check(att.get("payload_sha256") == requested_hash, "ATTESTED_PAYLOAD_MISMATCH")
    check(result.get("generic_shell") is False, "GENERIC_SHELL_DENIED")
    check(result.get("cost_eur") == 0, "UNEXPECTED_COST")

    value = result.get("result") or {}
    if kind == "sha256":
        check(value.get("sha256") == requested_hash and
              value.get("bytes") == len(payload), "SHA256_RESULT_INVALID")
    elif kind == "json_canonicalize":
        original = json.loads(payload.decode("utf-8-sig"))
        expected = json.dumps(original, sort_keys=True, separators=(",", ":"),
                              ensure_ascii=False).encode()
        check(base64.b64decode(value["canonical_b64"], validate=True) == expected
              and value.get("canonical_sha256") == digest(expected),
              "CANONICAL_JSON_INVALID")
    elif kind == "forensics_merkle":
        items = json.loads(payload.decode("utf-8-sig")).get("items", [])
        check(isinstance(items, list) and len(items) <= 10000, "MERKLE_INPUT_DENIED")
        check(value.get("count") == len(items) and
              value.get("merkle_root") == merkle(items), "MERKLE_RESULT_INVALID")
    elif kind == "hash_parallel":
        obj = json.loads(payload.decode("utf-8-sig"))
        lanes, rounds = int(obj.get("lanes", 4)), int(obj.get("rounds", 200000))
        seed = str(obj.get("seed", "AIKO"))
        check(1 <= lanes <= 4 and 1 <= rounds <= 2000000, "HASH_BUDGET_DENIED")
        expected = [hash_chain(f"{seed}:{i}", rounds) for i in range(lanes)]
        check(value.get("lane_hashes") == expected and
              value.get("aggregate_sha256") == digest("".join(expected).encode()) and
              value.get("rounds") == rounds and value.get("lanes") == lanes,
              "PARALLEL_RESULT_INVALID")

    return {
        "schema": "AIKO_INDEPENDENT_SIGNED_DELIVERY_PROOF_V1",
        "repository": REPOSITORY,
        "run_id": run_id,
        "commit": commit,
        "job_type": kind,
        "nonce": nonce,
        "manifest_sha256": digest(manifest),
        "result_sha256": digest(raw_result),
        "attestation_sha256": digest((root / "attestation.json").read_bytes()),
        "signature_verified_again": True,
        "result_recomputed": True,
        "cross_project_access": False,
        "production_deployment": False,
        "real_growth_code_delivery_certified": False,
        "B8_global_certified": False,
        "status": "INDEPENDENT_DELIVERY_PASS",
    }


def main():
    root = Path(".")
    proof = verify(root, dict(os.environ),
                   Path("keys/aiko_cloud_worker_public.pem"))
    out = root / "delivery_verification.json"
    out.write_text(json.dumps(proof, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print("AIKO_INDEPENDENT_SIGNED_DELIVERY_PASS", proof["result_sha256"])


if __name__ == "__main__":
    main()
