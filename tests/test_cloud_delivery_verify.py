"""Ephemeral independent verification against the actual signed worker.

Uses a freshly generated disposable Ed25519 test key, never the live signer.
100 adversarial receipt cases prove that changed artifacts are not trusted.
"""
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from cloud_delivery_verify import verify

ROOT = Path(__file__).resolve().parents[1]


class SignedDeliveryProofTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.session = tempfile.TemporaryDirectory(prefix="aiko_cloud_proof_test_")
        cls.home = Path(cls.session.name)
        cls.priv = cls.home / "test_only_ed25519.pem"
        cls.pub = cls.home / "test_only_public.pem"
        subprocess.run(["openssl", "genpkey", "-algorithm", "ED25519",
                        "-out", str(cls.priv)], check=True, capture_output=True)
        subprocess.run(["openssl", "pkey", "-in", str(cls.priv), "-pubout",
                        "-out", str(cls.pub)], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.session.cleanup()

    @classmethod
    def signed_worker(cls, kind, payload, nonce):
        raw = payload if isinstance(payload, bytes) else json.dumps(
            payload, ensure_ascii=False).encode("utf8")
        h = hashlib.sha256(raw).hexdigest()
        expires = int(time.time()) + 900
        manifest = json.dumps({
            "expires_at": expires,
            "job_type": kind,
            "nonce": nonce,
            "payload_sha256": h,
        }, sort_keys=True, separators=(",", ":")).encode()
        with tempfile.TemporaryDirectory() as tmp:
            message = Path(tmp) / "manifest.bin"
            sig_file = Path(tmp) / "signature.bin"
            message.write_bytes(manifest)
            subprocess.run(["openssl", "pkeyutl", "-sign", "-inkey",
                            str(cls.priv), "-rawin", "-in", str(message),
                            "-out", str(sig_file)], check=True, capture_output=True)
            signature = base64.b64encode(sig_file.read_bytes()).decode("ascii")

        env = {
            **os.environ,
            "GITHUB_ACTIONS": "true",
            "GITHUB_REPOSITORY": "jeanf1982-web/aiko-cloud-worker",
            "GITHUB_RUN_ID": "1234567890",
            "GITHUB_SHA": "a" * 40,
            "AIKO_JOB_TYPE": kind,
            "AIKO_PAYLOAD_B64": base64.b64encode(raw).decode("ascii"),
            "AIKO_NONCE": nonce,
            "AIKO_EXPIRES_AT": str(expires),
            "AIKO_PAYLOAD_SHA256": h,
            "AIKO_SIGNATURE_B64": signature,
        }
        case = cls.home / nonce
        case.mkdir(exist_ok=True)
        args = [sys.executable, str(ROOT / "worker.py"), "--job-type", kind,
                "--payload-b64", env["AIKO_PAYLOAD_B64"], "--nonce", nonce,
                "--expires-at", str(expires), "--payload-sha256", h,
                "--signature-b64", signature, "--public-key", str(cls.pub)]
        output = subprocess.run(args, cwd=case, env=env, capture_output=True,
                                text=True, timeout=35)
        assert output.returncode == 0, output.stderr
        return case, env

    def test_four_real_signed_capabilities(self):
        items = [
            ("sha256", b"independent signed blob"),
            ("json_canonicalize", {"x": "à", "z": [2, 3]}),
            ("forensics_merkle", {"items": ["a", "b", "c"]}),
            ("hash_parallel", {"lanes": 2, "rounds": 4, "seed": "QA"}),
        ]
        for i, (kind, payload) in enumerate(items):
            with self.subTest(kind=kind):
                case, env = self.signed_worker(kind, payload, f"proofvalid{i:02d}")
                proof = verify(case, env, self.pub)
                self.assertEqual(proof["status"], "INDEPENDENT_DELIVERY_PASS")
                self.assertTrue(proof["signature_verified_again"])
                self.assertTrue(proof["result_recomputed"])
                self.assertFalse(proof["B8_global_certified"])

    def test_manifest_expiry_matches_worker_policy(self):
        case, env = self.signed_worker("sha256", b"public synthetic expiry",
                                       "proofexpirynegative")
        future = dict(env)
        future["AIKO_EXPIRES_AT"] = str(int(time.time()) + 7200)
        with self.assertRaisesRegex(ValueError, "MANIFEST_EXPIRY_OUT_OF_RANGE"):
            verify(case, future, self.pub)

    def test_result_clock_must_be_finite_and_monotonic(self):
        case, env = self.signed_worker("sha256", b"public synthetic timing",
                                       "prooftimingnegative")
        raw = (case / "result.json").read_bytes()
        original_att = (case / "attestation.json").read_text(encoding="utf-8")
        for started, finished in ((10, 9), (0, 1300), (float("nan"), 100),
                                  (time.time() + 120, time.time() + 130)):
            with self.subTest(started=started, finished=finished):
                result = json.loads(raw)
                result["started_at"] = started
                result["finished_at"] = finished
                altered = json.dumps(result, sort_keys=True).encode()
                (case / "result.json").write_bytes(altered)
                attestation = json.loads(original_att)
                attestation["result_sha256"] = hashlib.sha256(altered).hexdigest()
                (case / "attestation.json").write_text(
                    json.dumps(attestation), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "RESULT_TIME_INVALID|RESULT_TIMING_INVALID"):
                    verify(case, env, self.pub)

    def test_100_mutated_receipts_are_rejected(self):
        case, env = self.signed_worker("sha256", b"truthful signed result",
                                       "proofmutationbaseline")
        original_result = (case / "result.json").read_bytes()
        original_att = (case / "attestation.json").read_bytes()
        for i in range(100):
            with self.subTest(case=i):
                (case / "result.json").write_bytes(original_result)
                (case / "attestation.json").write_bytes(original_att)
                changed = dict(env)
                mode = i % 5
                if mode in (0, 1):
                    result = json.loads(original_result)
                    if mode == 0:
                        result["nonce"] = f"forgednonce{i:04d}"
                    else:
                        result["result"]["sha256"] = "0" * 64
                    raw = json.dumps(result, sort_keys=True).encode()
                    (case / "result.json").write_bytes(raw)
                    att = json.loads(original_att)
                    att["result_sha256"] = hashlib.sha256(raw).hexdigest()
                    (case / "attestation.json").write_text(json.dumps(att))
                elif mode == 2:
                    att = json.loads(original_att)
                    att["result_sha256"] = "0" * 64
                    (case / "attestation.json").write_text(json.dumps(att))
                elif mode == 3:
                    changed["AIKO_NONCE"] = f"forgednonce{i:04d}"
                else:
                    changed["AIKO_SIGNATURE_B64"] = base64.b64encode(b"x" * 64).decode()
                with self.assertRaises((ValueError, AssertionError, KeyError)):
                    verify(case, changed, self.pub)


if __name__ == "__main__":
    unittest.main()
