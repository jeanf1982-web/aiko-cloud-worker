"""Fail-closed AIKO cloud job ownership gate.

This module deliberately accepts only AIKO-owned, synthetic/public,
read-only jobs. It does not route or inspect workloads owned by another
project. No cross-project fallback or secret-bearing dispatch is allowed.
"""
from __future__ import annotations

PROJECT = "AIKO"
PUBLIC_DATA_CLASS = "PUBLIC_SYNTHETIC"
DESTINATION = "AIKO_CLOUD_QA"
ALLOWED_KINDS = frozenset({"chess_options", "json_validation"})


def classify(job: object) -> dict:
    """Return an auditable, non-executing policy decision."""
    if not isinstance(job, dict):
        return {"allowed": False, "state": "REJECTED_UNSTRUCTURED_JOB"}
    if job.get("owner_project") != PROJECT:
        return {"allowed": False, "state": "REJECTED_PROJECT_BOUNDARY"}
    if job.get("destination", DESTINATION) != DESTINATION:
        return {"allowed": False, "state": "REJECTED_FOREIGN_DESTINATION"}
    if job.get("sensitivity") != "PUBLIC" or job.get("data_class") != PUBLIC_DATA_CLASS:
        return {"allowed": False, "state": "REJECTED_PRIVACY"}
    if job.get("approved_cloud") is not True:
        return {"allowed": False, "state": "REJECTED_NO_APPROVAL"}
    if job.get("kind") not in ALLOWED_KINDS:
        return {"allowed": False, "state": "REJECTED_UNKNOWN_JOB"}
    return {"allowed": True, "state": "AIKO_SYNTHETIC_QA_ONLY"}


def inspect_queue(doc: object) -> dict:
    if not isinstance(doc, dict) or doc.get("schema") != "AIKO_CLOUD_JOBS_V1":
        raise ValueError("UNKNOWN_QUEUE_SCHEMA_HOLD")
    if doc.get("owner_project") != PROJECT:
        raise ValueError("FOREIGN_QUEUE_OWNER_HOLD")
    jobs = doc.get("jobs")
    if not isinstance(jobs, list) or len(jobs) > 50:
        raise ValueError("INVALID_QUEUE_SIZE_HOLD")
    results = [classify(job) for job in jobs]
    return {
        "schema": "AIKO_BOUNDARY_REVIEW_V1",
        "total": len(jobs),
        "accepted": sum(x["allowed"] for x in results),
        "held": sum(not x["allowed"] for x in results),
        "mutation_count": 0,
        "production_deployment": False,
        "cross_project_routing": False,
    }
