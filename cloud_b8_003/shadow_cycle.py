"""B8-004: a fenced, recoverable SHADOW file effect.

This cannot handle arbitrary paths, production inputs, paid resources, code
execution, or Guardian approval. "Review" is a synthetic fixture, NOT an
authenticated independent review. Demonstrates only crash-consistent semantics.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import time


MARKER = "AIKO_B8_SHADOW_ONLY_V1"
SCHEMA = "AIKO_B8_SHADOW_REVIEW_V1"
TARGET = "candidate.txt"
MAX_SIZE = 100000


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _atomic_write(path: Path, data: bytes) -> None:
    if type(data) is not bytes or len(data) > MAX_SIZE:
        raise ValueError("SHADOW_BYTES_INVALID")
    with tempfile.NamedTemporaryFile(prefix=".aiko_shadow_", dir=path.parent,
                                     delete=False) as f:
        tmp = Path(f.name)
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    try:
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


class ShadowJournal:
    """Fences the filesystem effect while holding a SQLite write transaction.

    In case of process death after os.replace and before DB commit, SQLite
    rolls back PREPARED->APPLIED, and recover() restores a durable saved base.
    No guarantee is claimed for hardware power loss / multi-host coordination.
    """
    def __init__(self, root: Path):
        root = Path(root).resolve()
        if not root.name.startswith("aiko-b8-shadow-"):
            raise ValueError("NON_SHADOW_WORKSPACE_DENIED")
        marker = root / ".aiko_shadow_only"
        if not marker.is_file() or marker.is_symlink() or marker.read_text(
                encoding="ascii") != MARKER:
            raise ValueError("SHADOW_WORKSPACE_MARKER_MISSING")
        self.root = root
        self.file = root / TARGET
        self.db = root / "journal.sqlite3"
        with self.connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS tasks("
                "id TEXT PRIMARY KEY, epoch INTEGER NOT NULL,"
                "state TEXT NOT NULL, before_sha TEXT NOT NULL,"
                "after_sha TEXT NOT NULL, before_bytes BLOB NOT NULL,"
                "lease_until REAL NOT NULL)"
            )

    def connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db), timeout=6, isolation_level=None)

    def _file_is_local(self) -> None:
        if self.file.is_symlink() or self.file.resolve().parent != self.root:
            raise ValueError("NON_SHADOW_TARGET_DENIED")
        if not self.file.is_file():
            raise ValueError("SHADOW_TARGET_MISSING")

    def prepare(self, job_id: str, proposed: bytes, review: dict,
                now: float | None = None) -> int:
        self._file_is_local()
        if type(job_id) is not str or not re.fullmatch(
                r"synthetic-[A-Za-z0-9_-]{3,48}", job_id):
            raise ValueError("INVALID_SHADOW_JOB_ID")
        if type(proposed) is not bytes or len(proposed) > MAX_SIZE:
            raise ValueError("INVALID_CANDIDATE")
        before = self.file.read_bytes()
        if len(before) > MAX_SIZE:
            raise ValueError("BASE_TOO_LARGE")
        if type(review) is not dict or set(review) != {
                "schema", "job_id", "base_sha", "candidate_sha",
                "scope", "decision", "owner_release_authorized"}:
            raise ValueError("REVIEW_SCHEMA_DENIED")
        if (review["schema"] != SCHEMA or review["job_id"] != job_id or
                review["base_sha"] != digest(before) or
                review["candidate_sha"] != digest(proposed) or
                review["scope"] != "GHOST_SYNTHETIC_ONLY" or
                review["decision"] != "SHADOW_TEST_ONLY" or
                review["owner_release_authorized"] is not False):
            raise ValueError("SHADOW_REVIEW_NOT_BOUND")
        t = time.time() if now is None else now
        if type(t) not in (float, int) or not 0 < t < 1e12:
            raise ValueError("INVALID_CLOCK")
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            if c.execute("SELECT id FROM tasks WHERE id=?", (job_id,)).fetchone():
                raise ValueError("JOB_REPLAY_DENIED")
            c.execute(
                "INSERT INTO tasks VALUES (?,?,?,?,?,?,?)",
                (job_id, 1, "PREPARED", digest(before),
                 digest(proposed), before, t + 30),
            )
        return 1

    def apply(self, job_id: str, epoch: int, proposed: bytes,
              crash_after_write: bool = False, now: float | None = None) -> str:
        self._file_is_local()
        if type(epoch) is not int:
            raise ValueError("EPOCH_TYPE_DENIED")
        if type(proposed) is not bytes:
            raise ValueError("CANDIDATE_TYPE_DENIED")
        t = time.time() if now is None else now
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute(
                "SELECT epoch,state,before_sha,after_sha,lease_until"
                " FROM tasks WHERE id=?", (job_id,)
            ).fetchone()
            if not row or row[0] != epoch or row[1] != "PREPARED" or row[4] <= t:
                raise ValueError("STALE_OR_UNPREPARED_SHADOW_EFFECT")
            if digest(proposed) != row[3]:
                raise ValueError("CANDIDATE_SHA_MISMATCH")
            if digest(self.file.read_bytes()) != row[2]:
                raise ValueError("SHADOW_BASE_DIRTY_RECOVERY_REQUIRED")
            _atomic_write(self.file, proposed)
            if crash_after_write:
                os._exit(17)  # Test-only child process; DB transaction rolls back.
            c.execute("UPDATE tasks SET state='APPLIED' WHERE id=?", (job_id,))
        return digest(proposed)

    def recover(self, job_id: str) -> str:
        """Always restores the exact journalled previous state, even after a crash."""
        self._file_is_local()
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute(
                "SELECT state,before_sha,after_sha,before_bytes"
                " FROM tasks WHERE id=?", (job_id,)
            ).fetchone()
            if not row or row[0] not in ("PREPARED", "APPLIED"):
                raise ValueError("NO_RECOVERABLE_SHADOW_JOB")
            if digest(row[3]) != row[1]:
                raise ValueError("JOURNAL_BASE_CORRUPTED")
            current = digest(self.file.read_bytes())
            if current not in (row[1], row[2]):
                raise ValueError("AMBIGUOUS_EFFECT_HOLD")
            _atomic_write(self.file, row[3])
            if digest(self.file.read_bytes()) != row[1]:
                raise ValueError("ROLLBACK_VERIFICATION_FAILED")
            c.execute("UPDATE tasks SET state='ROLLED_BACK',"
                      " lease_until=0 WHERE id=?", (job_id,))
        return row[1]

    def state(self, job_id: str) -> str | None:
        with self.connect() as c:
            row = c.execute("SELECT state FROM tasks WHERE id=?", (job_id,)).fetchone()
        return row[0] if row else None


def create_disposable_shadow(root: Path) -> ShadowJournal:
    root = Path(root)
    if not root.name.startswith("aiko-b8-shadow-"):
        raise ValueError("DISPOSABLE_SHADOW_ROOT_REQUIRED")
    root.mkdir(parents=True, exist_ok=False)
    (root / ".aiko_shadow_only").write_text(MARKER, encoding="ascii")
    (root / TARGET).write_bytes(b"growth=original-synthetic\n")
    return ShadowJournal(root)


def demo() -> dict:
    with tempfile.TemporaryDirectory(prefix="aiko-b8-shadow-") as _unused:
        # tempfile itself creates the directory, so create fixture in a child.
        root = Path(_unused) / "aiko-b8-shadow-fixture"
        journal = create_disposable_shadow(root)
        before = journal.file.read_bytes()
        after = b"growth=revised-synthetic\n"
        job = "synthetic-shadow-demo"
        review = {"schema": SCHEMA, "job_id": job,
                  "base_sha": digest(before), "candidate_sha": digest(after),
                  "scope": "GHOST_SYNTHETIC_ONLY",
                  "decision": "SHADOW_TEST_ONLY",
                  "owner_release_authorized": False}
        epoch = journal.prepare(job, after, review)
        proof = journal.apply(job, epoch, after)
        if digest(journal.file.read_bytes()) != proof:
            raise ValueError("SYNTHETIC_SHADOW_VERIFICATION_FAILED")
        restored = journal.recover(job)
        if restored != digest(before) or journal.state(job) != "ROLLED_BACK":
            raise ValueError("SHADOW_ROLLBACK_FAILED")
        return {"schema": "AIKO_B8_SHADOW_FENCED_ROLLBACK_PROOF_V1",
                "applied_sha256": proof, "restored_sha256": restored,
                "state": journal.state(job), "result": "SYNTHETIC_SHADOW_PASS",
                "independent_codex_approval": False,
                "owner_release_authorized": False,
                "real_growth_source": False,
                "production_deployment": False, "B8_global_certified": False}


if __name__ == "__main__":
    print(json.dumps(demo(), sort_keys=True))
