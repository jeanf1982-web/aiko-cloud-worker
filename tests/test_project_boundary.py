"""Read-only safety tests: 300 synthetic routing decisions and input boundary."""
import copy
import json
from pathlib import Path
import unittest

from aiko_cloud_chess_executor import decide
from project_boundary import classify, inspect_queue


ROOT = Path(__file__).resolve().parents[1]


def safe_job(n):
    return {
        "id": f"safe-{n:03}",
        "owner_project": "AIKO",
        "destination": "AIKO_CLOUD_QA",
        "kind": "chess_options",
        "data_class": "PUBLIC_SYNTHETIC",
        "sensitivity": "PUBLIC",
        "approved_cloud": True,
    }


class BoundaryTests(unittest.TestCase):
    def test_100_safe_public_jobs(self):
        for n in range(100):
            job = safe_job(n)
            self.assertTrue(classify(job)["allowed"])
            self.assertEqual(decide(job)["state"], "CLOUD_DONE_PENDING_LOCAL_VALIDATION")

    def test_100_foreign_owners_are_held(self):
        for n in range(100):
            job = safe_job(n)
            job["owner_project"] = "OTHER_PROJECT"
            self.assertEqual(classify(job)["state"], "REJECTED_PROJECT_BOUNDARY")
            self.assertEqual(decide(job)["state"], "REJECTED_PROJECT_BOUNDARY")

    def test_100_ambiguous_or_secret_jobs_are_held(self):
        for n in range(100):
            job = safe_job(n)
            if n % 5 == 0:
                job.pop("owner_project")
                expected = "REJECTED_PROJECT_BOUNDARY"
            elif n % 5 == 1:
                job["owner_project"] = ["AIKO", "OTHER_PROJECT"]
                expected = "REJECTED_PROJECT_BOUNDARY"
            elif n % 5 == 2:
                job["sensitivity"] = "PRIVATE"
                expected = "REJECTED_PRIVACY"
            elif n % 5 == 3:
                job["data_class"] = "UNCLASSIFIED"
                expected = "REJECTED_PRIVACY"
            else:
                job["destination"] = "UNKNOWN"
                expected = "REJECTED_FOREIGN_DESTINATION"
            self.assertEqual(decide(job)["state"], expected)

    def test_manifest_requires_single_explicit_project(self):
        queue = json.loads((ROOT / "aiko_cloud_jobs.json").read_text(encoding="utf8"))
        summary = inspect_queue(queue)
        self.assertEqual(summary["accepted"], 11)
        self.assertEqual(summary["held"], 0)
        self.assertEqual(summary["mutation_count"], 0)
        self.assertFalse(summary["production_deployment"])
        foreign = copy.deepcopy(queue)
        foreign["owner_project"] = "OTHER_PROJECT"
        with self.assertRaisesRegex(ValueError, "FOREIGN_QUEUE"):
            inspect_queue(foreign)

    def test_workflow_dispatch_inputs_are_never_shell_interpolated(self):
        src = (ROOT / ".github/workflows/aiko-cloud-worker.yml").read_text(encoding="utf8")
        execute_step = src.split("      - name: Execute allowlisted signed job", 1)[1].split(
            "      - name: Upload immutable result artifact", 1)[0]
        env, command = execute_step.split("        run: |", 1)
        self.assertIn("AIKO_JOB_TYPE: ${{ inputs.job_type }}", env)
        self.assertNotIn("${{ inputs.", command)
        self.assertIn('"$AIKO_SIGNATURE_B64"', command)
        self.assertIn('"$AIKO_PAYLOAD_B64"', command)

    def test_no_project_cross_route_or_cloud_fallback(self):
        policy = json.loads((ROOT / "cloud_b8_003/federation_policy.json").read_text())
        self.assertEqual(policy["project_identity"], "AIKO")
        self.assertFalse(any(policy["project_separation"].values()))
        self.assertFalse(policy["fallback"]["acer_cpu_fallback"])
        self.assertFalse(policy["fallback"]["paid_providers"])


if __name__ == "__main__":
    unittest.main()
