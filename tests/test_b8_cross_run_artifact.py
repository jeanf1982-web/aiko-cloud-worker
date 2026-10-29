"""No network, no credentials: contract tests for cross-run B8 synthetic evidence."""
import hashlib, io, json, unittest, zipfile, time
import urllib.error
from unittest.mock import patch
from datetime import datetime, timezone, timedelta
from cloud_b8_003.cross_run_artifact import (verify_artifact_meta, verify_archive,
    verify_source_workflow_run, get_artifact_zip, REPO, REPO_ID, ARTIFACT,
    FILENAME, APPROVED_WORKFLOW_ID, APPROVED_WORKFLOW_PATH)

class CrossRunTests(unittest.TestCase):
    def setUp(self):
        self.meta={"name":ARTIFACT,"expired":False,"digest":"",
           "created_at":datetime.now(timezone.utc).isoformat(),
           "workflow_run":{"id":501,"repository_id":REPO_ID,
             "head_repository_id":REPO_ID,"head_sha":"a"*40}}
        self.receipt={"schema":"AIKO_B8_003_REAL_PROCESS_CRASH_QA_V1","repository":REPO,
          "run_id":"501","commit":"a"*40,"actual_child_processes_killed":100,
          "cases":{"child_process_crashes":100,"reclaims":100,"stale_epoch_rejections":100,
                   "no_duplicate_file_write":100,"unique_effect_receipts":100},
          "status":"CLOUD_SANDBOX_CRASH_RECOVERY_PASS",
          "source":"EPHEMERAL_GITHUB_LINUX_RUNNER",
          "local_acer_changed":False,"real_multi_provider_failover":False,
          "production_deployment":False,"real_growth_source":False,"B8_global_certified":False}
    def pack(self,member=FILENAME):
        file=io.BytesIO()
        with zipfile.ZipFile(file,"w",zipfile.ZIP_DEFLATED) as z:
            z.writestr(member,json.dumps(self.receipt))
        raw=file.getvalue()
        self.meta["digest"]="sha256:"+hashlib.sha256(raw).hexdigest()
        return raw
    def test_positive_previous_run_proof(self):
        raw=self.pack()
        self.assertTrue(verify_artifact_meta(self.meta,"502"))
        self.assertEqual(verify_archive(raw,self.meta)["actual_crash_recovery_probes"],100)
    def test_reject_current_run(self):
        self.pack();self.assertFalse(verify_artifact_meta(self.meta,"501"))
    def test_reject_other_project(self):
        self.pack();self.meta["workflow_run"]["head_repository_id"]=1
        self.assertFalse(verify_artifact_meta(self.meta,"502"))
    def test_reject_expired(self):
        self.pack();self.meta["expired"]=True
        self.assertFalse(verify_artifact_meta(self.meta,"502"))
    def test_reject_stale_cross_run_artifact(self):
        self.pack()
        self.meta["created_at"]=(datetime.now(timezone.utc)-timedelta(days=3)).isoformat()
        self.assertFalse(verify_artifact_meta(self.meta,"502"))
    def test_reject_future_cross_run_artifact(self):
        self.pack()
        self.meta["created_at"]=(datetime.now(timezone.utc)+timedelta(minutes=15)).isoformat()
        self.assertFalse(verify_artifact_meta(self.meta,"502"))
    def test_reject_nonhex_commit_sha(self):
        self.pack();self.meta["workflow_run"]["head_sha"]="z"*40
        self.assertFalse(verify_artifact_meta(self.meta,"502"))
    def test_reject_nonhex_artifact_digest(self):
        self.pack();self.meta["digest"]="sha256:"+"x"*64
        self.assertFalse(verify_artifact_meta(self.meta,"502"))
    def test_reject_forged_boolean_run_id(self):
        self.pack();self.meta["workflow_run"]["id"]=True
        self.assertFalse(verify_artifact_meta(self.meta,"502"))
    def test_reject_non_utc_metadata(self):
        self.pack();self.meta["created_at"]="2026-10-29T00:00:00"
        self.assertFalse(verify_artifact_meta(self.meta,"502"))
    def test_reject_missing_artifact_timestamp(self):
        self.pack();del self.meta["created_at"]
        self.assertFalse(verify_artifact_meta(self.meta,"502"))
    def test_reject_forged_digest(self):
        raw=self.pack();self.meta["digest"]="sha256:"+"0"*64
        with self.assertRaises(ValueError):verify_archive(raw,self.meta)
    def test_reject_wrong_commit(self):
        self.receipt["commit"]="b"*40
        raw=self.pack()
        with self.assertRaises(ValueError):verify_archive(raw,self.meta)
    def test_reject_wrong_run(self):
        self.receipt["run_id"]="777";raw=self.pack()
        with self.assertRaises(ValueError):verify_archive(raw,self.meta)
    def test_reject_missing_100_crashes(self):
        self.receipt["actual_child_processes_killed"]=99;raw=self.pack()
        with self.assertRaises(ValueError):verify_archive(raw,self.meta)
    def test_reject_false_production_release(self):
        self.receipt["production_deployment"]=True;raw=self.pack()
        with self.assertRaises(ValueError):verify_archive(raw,self.meta)
    def good_run(self):
        return {"id":501,"workflow_id":APPROVED_WORKFLOW_ID,
            "path":APPROVED_WORKFLOW_PATH,"status":"completed","conclusion":"success",
            "event":"push","head_branch":"aiko-growth-delivery-integrated-ghost-20261029",
            "head_sha":"a"*40,"head_repository":{"id":REPO_ID},
            "repository":{"id":REPO_ID}}
    def test_authorized_producer_workflow(self):
        self.pack()
        self.assertTrue(verify_source_workflow_run(self.good_run(),self.meta))
    def test_reject_other_workflow(self):
        self.pack();r=self.good_run();r["workflow_id"]+=1
        self.assertFalse(verify_source_workflow_run(r,self.meta))
    def test_reject_failed_producing_workflow(self):
        self.pack();r=self.good_run();r["conclusion"]="failure"
        self.assertFalse(verify_source_workflow_run(r,self.meta))
    def test_reject_wrong_producing_branch(self):
        self.pack();r=self.good_run();r["head_branch"]="unknown-feature"
        self.assertFalse(verify_source_workflow_run(r,self.meta))
    def test_reject_wrong_producing_commit(self):
        self.pack();r=self.good_run();r["head_sha"]="b"*40
        self.assertFalse(verify_source_workflow_run(r,self.meta))
    def test_reject_other_repository_producer(self):
        self.pack();r=self.good_run();r["repository"]["id"]=1
        self.assertFalse(verify_source_workflow_run(r,self.meta))
    def test_reject_forged_case_counter_names(self):
        self.receipt["cases"]={"inventato":100}
        with self.assertRaises(ValueError):verify_archive(self.pack(),self.meta)
    def test_reject_receipt_with_false_status(self):
        self.receipt["status"]="FAIL"
        with self.assertRaises(ValueError):verify_archive(self.pack(),self.meta)
    def test_reject_float_crash_counter(self):
        self.receipt["actual_child_processes_killed"]=100.0
        with self.assertRaises(ValueError):verify_archive(self.pack(),self.meta)
    def test_reject_boolean_case_count(self):
        self.receipt["cases"]["reclaims"]=True
        with self.assertRaises(ValueError):verify_archive(self.pack(),self.meta)
    def test_reject_receipt_false_source(self):
        self.receipt["source"]="SPOOF"
        with self.assertRaises(ValueError):verify_archive(self.pack(),self.meta)
    def test_reject_second_redirect_from_artifact_storage(self):
        class FakeOpener:
            def __init__(self):self.calls=0
            def open(self,req,timeout=15):
                self.calls+=1
                location=("https://account.blob.core.windows.net/proof.zip" if self.calls==1
                    else "https://127.0.0.1/forbidden")
                raise urllib.error.HTTPError(req.full_url,302,"redirect",
                    {"Location":location},None)
        fake=FakeOpener()
        with patch("cloud_b8_003.cross_run_artifact.urllib.request.build_opener",return_value=fake):
            with self.assertRaisesRegex(ValueError,"SECOND_ARTIFACT_REDIRECT_DENIED"):
                get_artifact_zip(123,"synthetic-readonly-token")
        self.assertEqual(fake.calls,2)
    def test_reject_archive_traversal(self):
        raw=self.pack("../"+FILENAME)
        with self.assertRaises(ValueError):verify_archive(raw,self.meta)

if __name__=="__main__":unittest.main()
