"""Reject malformed signed-job nonces before any work or artifact is written.

Synthetic only; never accesses ACER, production, network, or private payloads.
"""
from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


class NonceBoundaryTests(unittest.TestCase):
    def run_worker(self, nonce: str):
        with tempfile.TemporaryDirectory(prefix="aiko-nonce-gate-") as d:
            args = [
                sys.executable, str(ROOT / "worker.py"),
                "--job-type", "sha256",
                "--payload-b64", base64.b64encode(b"synthetic").decode(),
                "--nonce", nonce,
                "--expires-at", str(int(time.time()) + 600),
                "--payload-sha256", hashlib.sha256(b"synthetic").hexdigest(),
                "--signature-b64", base64.b64encode(b"x" * 64).decode(),
                "--public-key", str(ROOT / "keys/aiko_cloud_worker_public.pem"),
            ]
            environment = {**os.environ, "GITHUB_ACTIONS": "true",
                           "GITHUB_REPOSITORY": "jeanf1982-web/aiko-cloud-worker"}
            result = subprocess.run(args, cwd=d, env=environment,
                                    capture_output=True, text=True, timeout=10)
            artifacts = [p.name for p in Path(d).iterdir()]
            return result, artifacts

    def test_invalid_nonces_fail_closed_without_artifacts(self):
        for nonce in ("", "short", "bad/nonce", "bad\\nonce", "with space",
                      "line\nbreak", "é" * 8, "a" * 81, "../escape"):
            with self.subTest(nonce=repr(nonce)):
                result, files = self.run_worker(nonce)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("NONCE_FORMAT_INVALID", result.stderr + result.stdout)
                self.assertEqual(files, [])

    # Positive-format control must fail exclusively on its deliberately bogus signature.
    def test_valid_nonce_reaches_signature_check_but_never_executes(self):
        result, files = self.run_worker("valid_nonce-20261025")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("BAD_SIGNATURE", result.stderr + result.stdout)
        self.assertEqual(files, [])


if __name__ == "__main__":
    unittest.main()
