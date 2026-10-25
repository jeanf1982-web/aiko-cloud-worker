"""AIKO cloud candidate policy. This is a pure, nonexecuting decision gate.

It does not authenticate an agent, access any external project, dispatch jobs,
or authorize real deployment. Exactly specified synthetic/public request shapes only.
"""
from __future__ import annotations

EXPECTED = frozenset({
    "schema", "id", "owner_project", "destination", "kind",
    "data_class", "sensitivity", "approved_cloud", "mode",
    "paid_api", "production_deploy", "secret_access",
    "remote_device_access", "model_inference",
})
ALLOWED_KIND = frozenset({"json_validation", "chess_options"})
MAX_ID_LENGTH = 80


def classify_agent_candidate(job: object) -> dict:
    """Fail closed before any cloud agent dispatch. Never executes input."""
    if not isinstance(job, dict) or set(job) != EXPECTED:
        return {"allowed": False, "state": "REJECTED_SCHEMA"}
    if job["schema"] != "AIKO_AGENT_CANDIDATE_V1":
        return {"allowed": False, "state": "REJECTED_SCHEMA"}
    if not isinstance(job["id"], str) or not 1 <= len(job["id"]) <= MAX_ID_LENGTH or not job["id"].isascii() or not all(c.isalnum() or c in "-_" for c in job["id"]):
        return {"allowed": False, "state": "REJECTED_ID"}
    if job["owner_project"] != "AIKO" or job["destination"] != "AIKO_CLOUD_QA":
        return {"allowed": False, "state": "REJECTED_PROJECT_BOUNDARY"}
    if job["data_class"] != "PUBLIC_SYNTHETIC" or job["sensitivity"] != "PUBLIC":
        return {"allowed": False, "state": "REJECTED_PRIVACY"}
    if job["approved_cloud"] is not True:
        return {"allowed": False, "state": "REJECTED_NO_APPROVAL"}
    if job["kind"] not in ALLOWED_KIND or job["mode"] != "READ_ONLY":
        return {"allowed": False, "state": "REJECTED_CAPABILITY"}
    for forbidden in ("paid_api", "production_deploy", "secret_access", "remote_device_access", "model_inference"):
        if job[forbidden] is not False:
            return {"allowed": False, "state": "REJECTED_FORBIDDEN_EFFECT"}
    return {"allowed": True, "state": "AIKO_PUBLIC_SYNTHETIC_QA_ONLY"}
