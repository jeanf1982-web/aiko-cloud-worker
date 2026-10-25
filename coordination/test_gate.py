"""Pure tests proving scope rejection. No network, credentials or mutation."""
import copy
import unittest

from gate import classify_agent_candidate


def safe_case(index=0):
    return {
        "schema": "AIKO_AGENT_CANDIDATE_V1",
        "id": f"synthetic_{index}",
        "owner_project": "AIKO",
        "destination": "AIKO_CLOUD_QA",
        "kind": "json_validation",
        "data_class": "PUBLIC_SYNTHETIC",
        "sensitivity": "PUBLIC",
        "approved_cloud": True,
        "mode": "READ_ONLY",
        "paid_api": False,
        "production_deploy": False,
        "secret_access": False,
        "remote_device_access": False,
        "model_inference": False,
    }


class AgentCandidateGateTests(unittest.TestCase):
    def test_safe_public_synthetic_candidates(self):
        for i in range(100):
            self.assertTrue(classify_agent_candidate(safe_case(i))["allowed"])

    def test_cross_project_rejected(self):
        for other in ("BOOM", "BLACKLINK", None, ["AIKO", "BOOM"]):
            case = safe_case()
            case["owner_project"] = other
            self.assertEqual(classify_agent_candidate(case)["state"], "REJECTED_PROJECT_BOUNDARY")

    def test_secret_and_private_data_rejected(self):
        for k, value in (("data_class", "PRIVATE"), ("sensitivity", "RESTRICTED"), ("secret_access", True)):
            case = safe_case()
            case[k] = value
            self.assertFalse(classify_agent_candidate(case)["allowed"])

    def test_side_effects_rejected(self):
        for k in ("paid_api", "production_deploy", "secret_access", "remote_device_access", "model_inference"):
            case = safe_case()
            case[k] = True
            self.assertEqual(classify_agent_candidate(case)["state"], "REJECTED_FORBIDDEN_EFFECT")

    def test_mutation_and_unapproved_rejected(self):
        for k, value in (("mode", "WRITE"), ("approved_cloud", False), ("kind", "shell_exec")):
            case = safe_case()
            case[k] = value
            self.assertFalse(classify_agent_candidate(case)["allowed"])

    def test_undeclared_field_and_invalid_id_rejected(self):
        case = safe_case()
        case["private_key"] = "redacted"
        self.assertEqual(classify_agent_candidate(case)["state"], "REJECTED_SCHEMA")
        for bad in ("../../", "secret token", "", None):
            case = safe_case()
            case["id"] = bad
            self.assertFalse(classify_agent_candidate(case)["allowed"])

    def test_synthetic_negative_matrix(self):
        for i in range(200):
            case = copy.deepcopy(safe_case(i))
            if i % 4 == 0:
                case["production_deploy"] = True
            elif i % 4 == 1:
                case["owner_project"] = "OTHER"
            elif i % 4 == 2:
                case["data_class"] = "MEMBER_PII"
            else:
                case["approved_cloud"] = False
            self.assertFalse(classify_agent_candidate(case)["allowed"])


if __name__ == "__main__":
    unittest.main()
