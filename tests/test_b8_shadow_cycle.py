"""No production access: B8 synthetic fenced apply/recovery regression."""
from __future__ import annotations
import ast
import multiprocessing
from pathlib import Path
import sys
import tempfile
import time
import unittest

from cloud_b8_003.shadow_cycle import (
    SCHEMA, MARKER, ShadowJournal, create_disposable_shadow, demo, digest
)


def child_crash(root: str, job: str, epoch: int, after: bytes):
    journal = ShadowJournal(Path(root))
    journal.apply(job, epoch, after, crash_after_write=True)


class ShadowCycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="aiko-b8-shadow-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "aiko-b8-shadow-case"
        self.j = create_disposable_shadow(self.root)
        self.before = self.j.file.read_bytes()
        self.after = b"growth=candidate-synthetic\n"
        self.job = "synthetic-case-001"

    def review(self):
        return {"schema": SCHEMA, "job_id": self.job,
                "base_sha": digest(self.before), "candidate_sha": digest(self.after),
                "scope": "GHOST_SYNTHETIC_ONLY",
                "decision": "SHADOW_TEST_ONLY",
                "owner_release_authorized": False}

    def prepare(self):
        return self.j.prepare(self.job, self.after, self.review())

    def test_positive_apply_then_rollback(self):
        epoch = self.prepare()
        self.assertEqual(self.j.apply(self.job, epoch, self.after), digest(self.after))
        self.assertEqual(self.j.state(self.job), "APPLIED")
        self.assertEqual(self.j.file.read_bytes(), self.after)
        self.assertEqual(self.j.recover(self.job), digest(self.before))
        self.assertEqual(self.j.file.read_bytes(), self.before)
        self.assertEqual(self.j.state(self.job), "ROLLED_BACK")

    def test_crash_after_file_write_before_sqlite_commit(self):
        if sys.platform != "linux":
            self.skipTest("real process crash only in ephemeral Linux cloud")
        epoch = self.prepare()
        p = multiprocessing.get_context("fork").Process(
            target=child_crash, args=(str(self.root), self.job, epoch, self.after))
        p.start()
        p.join(timeout=8)
        if p.is_alive():
            p.kill()
            p.join(timeout=2)
            self.fail("SHADOW_CHILD_DID_NOT_TERMINATE")
        self.assertEqual(p.exitcode, 17)
        self.assertEqual(self.j.file.read_bytes(), self.after)
        self.assertEqual(self.j.state(self.job), "PREPARED")
        self.assertEqual(self.j.recover(self.job), digest(self.before))
        self.assertEqual(self.j.file.read_bytes(), self.before)
        self.assertEqual(self.j.state(self.job), "ROLLED_BACK")

    def test_no_owner_approval_in_demo(self):
        proof = demo()
        self.assertEqual(proof["state"], "ROLLED_BACK")
        self.assertFalse(proof["owner_release_authorized"])
        self.assertFalse(proof["independent_codex_approval"])
        self.assertFalse(proof["real_growth_source"])
        self.assertFalse(proof["production_deployment"])
        self.assertFalse(proof["B8_global_certified"])

    def test_reject_unreviewed_input(self):
        with self.assertRaisesRegex(ValueError, "REVIEW_SCHEMA_DENIED"):
            self.j.prepare(self.job, self.after, {})
        self.assertEqual(self.j.file.read_bytes(), self.before)

    def test_reject_forged_approved_release(self):
        review = self.review()
        review["owner_release_authorized"] = True
        with self.assertRaisesRegex(ValueError, "SHADOW_REVIEW_NOT_BOUND"):
            self.j.prepare(self.job, self.after, review)

    def test_reject_forged_project_scope(self):
        review = self.review()
        review["scope"] = "OTHER_PROJECT"
        with self.assertRaisesRegex(ValueError, "SHADOW_REVIEW_NOT_BOUND"):
            self.j.prepare(self.job, self.after, review)

    def test_reject_forged_candidate_hash(self):
        review = self.review()
        review["candidate_sha"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "SHADOW_REVIEW_NOT_BOUND"):
            self.j.prepare(self.job, self.after, review)

    def test_reject_base_hash_mismatch(self):
        review = self.review()
        review["base_sha"] = "1" * 64
        with self.assertRaisesRegex(ValueError, "SHADOW_REVIEW_NOT_BOUND"):
            self.j.prepare(self.job, self.after, review)

    def test_reject_replay_job_id(self):
        self.prepare()
        with self.assertRaisesRegex(ValueError, "JOB_REPLAY_DENIED"):
            self.prepare()

    def test_reject_stale_epoch(self):
        self.prepare()
        with self.assertRaisesRegex(ValueError, "STALE_OR_UNPREPARED"):
            self.j.apply(self.job, 2, self.after)
        self.assertEqual(self.j.file.read_bytes(), self.before)

    def test_reject_expired_lease(self):
        self.prepare()
        with self.assertRaisesRegex(ValueError, "STALE_OR_UNPREPARED"):
            self.j.apply(self.job, 1, self.after, now=time.time() + 50)
        self.assertEqual(self.j.file.read_bytes(), self.before)

    def test_reject_candidate_change_after_review(self):
        self.prepare()
        with self.assertRaisesRegex(ValueError, "CANDIDATE_SHA_MISMATCH"):
            self.j.apply(self.job, 1, b"growth=unreviewed\n")
        self.assertEqual(self.j.file.read_bytes(), self.before)

    def test_reject_dirty_base_before_apply(self):
        self.prepare()
        self.j.file.write_bytes(b"growth=unknown-change\n")
        with self.assertRaisesRegex(ValueError, "SHADOW_BASE_DIRTY_RECOVERY_REQUIRED"):
            self.j.apply(self.job, 1, self.after)

    def test_ambiguous_recovery_holds_and_preserves_file(self):
        self.prepare()
        self.j.file.write_bytes(b"third-party-unexpected-change\n")
        with self.assertRaisesRegex(ValueError, "AMBIGUOUS_EFFECT_HOLD"):
            self.j.recover(self.job)
        self.assertEqual(self.j.file.read_bytes(), b"third-party-unexpected-change\n")

    def test_recovery_before_apply_restores_old_bytes(self):
        self.prepare()
        self.assertEqual(self.j.recover(self.job), digest(self.before))
        self.assertEqual(self.j.state(self.job), "ROLLED_BACK")

    def test_refuse_second_effect_after_apply(self):
        self.prepare()
        self.j.apply(self.job, 1, self.after)
        with self.assertRaisesRegex(ValueError, "STALE_OR_UNPREPARED"):
            self.j.apply(self.job, 1, self.after)
        self.j.recover(self.job)

    def test_reject_second_rollback(self):
        self.prepare()
        self.j.recover(self.job)
        with self.assertRaisesRegex(ValueError, "NO_RECOVERABLE_SHADOW_JOB"):
            self.j.recover(self.job)

    def test_reject_non_shadow_workspace(self):
        with self.assertRaisesRegex(ValueError, "NON_SHADOW_WORKSPACE_DENIED"):
            ShadowJournal(Path(self.tmp.name) / "untrusted-workspace")

    def test_reject_missing_shadow_marker(self):
        (self.root / ".aiko_shadow_only").unlink()
        with self.assertRaisesRegex(ValueError, "SHADOW_WORKSPACE_MARKER_MISSING"):
            ShadowJournal(self.root)

    def test_reject_untrusted_target(self):
        self.prepare()
        self.j.file = self.root.parent / "untrusted.txt"
        self.j.file.write_bytes(b"NOT A SHADOW TARGET")
        with self.assertRaisesRegex(ValueError, "NON_SHADOW_TARGET_DENIED"):
            self.j.apply(self.job, 1, self.after)

    def test_reject_symlink_target(self):
        if not hasattr(Path, "symlink_to"):
            self.skipTest("symlink unsupported")
        self.j.file.unlink()
        external = Path(self.tmp.name) / "external.txt"
        external.write_bytes(self.before)
        try:
            self.j.file.symlink_to(external)
        except OSError:
            self.skipTest("symlink not allowed")
        with self.assertRaisesRegex(ValueError, "NON_SHADOW_TARGET_DENIED"):
            self.j.prepare(self.job, self.after, self.review())
        self.assertEqual(external.read_bytes(), self.before)

    def test_no_optimized_out_state_checks(self):
        path = Path(__file__).resolve().parents[1] / "cloud_b8_003" / "shadow_cycle.py"
        syntax = ast.parse(path.read_text(encoding="utf-8"))
        self.assertFalse(any(isinstance(x, ast.Assert) for x in ast.walk(syntax)))

if __name__ == "__main__":
    unittest.main()
