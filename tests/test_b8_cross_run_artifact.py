"""No network, no credentials: contract tests for cross-run B8 synthetic evidence."""
import hashlib, io, json, unittest, zipfile
from cloud_b8_003.cross_run_artifact import verify_artifact_meta, verify_archive, REPO, REPO_ID, ARTIFACT, FILENAME

class CrossRunTests(unittest.TestCase):
    def setUp(self):
        self.meta={"name":ARTIFACT,"expired":False,"digest":"",
           "workflow_run":{"id":501,"repository_id":REPO_ID,
             "head_repository_id":REPO_ID,"head_sha":"a"*40}}
        self.receipt={"schema":"AIKO_B8_003_REAL_PROCESS_CRASH_QA_V1","repository":REPO,
          "run_id":"501","commit":"a"*40,"actual_child_processes_killed":100,
          "cases":{"crashes":100,"verified":100},
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
    def test_reject_archive_traversal(self):
        raw=self.pack("../"+FILENAME)
        with self.assertRaises(ValueError):verify_archive(raw,self.meta)

if __name__=="__main__":unittest.main()
