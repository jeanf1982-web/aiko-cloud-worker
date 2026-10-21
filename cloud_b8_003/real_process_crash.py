"""Off-ACER B8-003: actual child-process termination and durable lease replay.

100 separate Linux child processes die after a synthetic file write but
before committing. Recovery is idempotent on an ephemeral GitHub runner.
Not evidence of a real Growth production deployment.
"""
from __future__ import annotations

import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import sys
import tempfile
import time

from acceptance import Queue, atomic_write, sha


def crash_after_write(db: str, artifact: str, key: str, data: bytes):
    """Deliberate unclean process exit; MUST run only in runner sandbox."""
    q = Queue(Path(db))
    token = q.claim(key)
    if token != 1:
        os._exit(91)
    atomic_write(Path(artifact), data)
    os._exit(17)


def verify_100_actual_process_crashes() -> dict:
    if sys.platform != "linux" or os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("LINUX_EPHEMERAL_CLOUD_RUNNER_ONLY")
    with tempfile.TemporaryDirectory(prefix="aiko_b8_crash_cloud_") as tmp:
        root = Path(tmp)
        ledger = Queue(root / "journal.sqlite3")
        original = b"trusted previous version"
        candidate = b"synthetic candidate committed after process restart"
        stats = dict(child_process_crashes=0, reclaims=0,
                     stale_epoch_rejections=0, no_duplicate_file_write=0,
                     unique_effect_receipts=0)
        for i in range(100):
            key = f"crash-case-{i:03d}"
            artifact = root / f"candidate-{i:03d}.bin"
            artifact.write_bytes(original)
            ledger.put(key)
            worker = multiprocessing.Process(
                target=crash_after_write,
                args=(ledger.db, str(artifact), key, candidate),
            )
            worker.start()
            worker.join(timeout=8)
            if worker.is_alive():
                worker.kill()
                worker.join(timeout=2)
                raise AssertionError("CHILD_NOT_TERMINATED")
            assert worker.exitcode == 17, (i, worker.exitcode)
            stats["child_process_crashes"] += 1
            assert sha(artifact.read_bytes()) == sha(candidate)
            original_write_time = artifact.stat().st_mtime_ns

            # Advance a stale lease only inside the disposable test journal.
            # No Guardian/production state or real worker is manipulated.
            with ledger.connect() as connection:
                connection.execute("UPDATE jobs SET lease_until=0 WHERE id=?", (key,))
            recovered = Queue(Path(ledger.db))
            new_epoch = recovered.claim(key)
            assert new_epoch == 2, (i, new_epoch)
            stats["reclaims"] += 1
            assert not recovered.commit(key, 1, sha(candidate))
            stats["stale_epoch_rejections"] += 1

            # File hash tells a recovering worker the intended data is already
            # present: avoid rewriting it after a crash-before-commit.
            if sha(artifact.read_bytes()) != sha(candidate):
                atomic_write(artifact, candidate)
            assert artifact.stat().st_mtime_ns == original_write_time
            assert recovered.commit(key, new_epoch, sha(candidate))
            assert recovered.row(key) == ("DONE", 2, sha(candidate))
            stats["no_duplicate_file_write"] += 1

        assert ledger.unique_effects() == 100
        stats["unique_effect_receipts"] = 100
        return {
            "schema": "AIKO_B8_003_REAL_PROCESS_CRASH_QA_V1",
            "source": "EPHEMERAL_GITHUB_LINUX_RUNNER",
            "repository": os.environ.get("GITHUB_REPOSITORY"),
            "commit": os.environ.get("GITHUB_SHA"),
            "run_id": os.environ.get("GITHUB_RUN_ID"),
            "cases": stats,
            "status": "CLOUD_SANDBOX_CRASH_RECOVERY_PASS",
            "actual_child_processes_killed": 100,
            "local_acer_changed": False,
            "real_growth_source": False,
            "production_deployment": False,
            "real_multi_provider_failover": False,
            "B8_global_certified": False,
        }


if __name__ == "__main__":
    result = verify_100_actual_process_crashes()
    target = Path("artifacts") / "b8-003-real-process-crash-proof.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n",
                      encoding="utf8")
    print("AIKO_REAL_PROCESS_CRASH_RECOVERY_PASS",
          result["actual_child_processes_killed"],
          result["cases"]["unique_effect_receipts"])
