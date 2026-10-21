"""Read-only public-surface audit for AIKO federation; not a global product certificate."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request
import datetime

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts"
OUT.mkdir(exist_ok=True)
PUBLIC_BASE = "https://organization-it.vercel.app"
ROUTES = ("/", "/join", "/recover")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def probe_route(path):
    url = PUBLIC_BASE + path
    details = {"path": path, "base": PUBLIC_BASE, "pass": False}
    req = urllib.request.Request(
        url, headers={"User-Agent": "AIKO-Cloud-Certification/1.0",
                      "Accept": "text/html"},
        method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            final = response.geturl()
            final_parts = urllib.parse.urlsplit(final)
            expected = urllib.parse.urlsplit(PUBLIC_BASE)
            data = response.read(120000)
            status = response.status
            frontend = response.headers.get("x-frontend-version", "").strip()
            content_type = response.headers.get("Content-Type", "")
            destination_allowed = (
                final_parts.scheme == "https"
                and final_parts.hostname == expected.hostname
                and final_parts.port is None
            )
            details.update({
                "http": status, "final_host": final_parts.hostname,
                "bytes_inspected": len(data), "version_header": frontend[:80],
                "html_content_type": "text/html" in content_type.lower(),
                "no_external_redirect": destination_allowed,
            })
            details["pass"] = bool(
                status == 200 and destination_allowed and len(data) > 500
                and frontend and details["html_content_type"]
            )
    except Exception as exc:
        details["error_type"] = type(exc).__name__
        details["error_message"] = str(exc)[:160]
    return details


def main():
    policies = json.loads(
        (ROOT / "cloud_b8_003" / "federation_policy.json").read_text(encoding="utf8"))
    workflow = (ROOT / ".github" / "workflows" /
                "aiko-b8-003-federated-acceptance.yml").read_text(encoding="utf8")
    quality_gate = (ROOT / ".github" / "workflows" /
                    "aiko-cloud-evolution-quality-gate.yml").read_text(encoding="utf8")
    privacy = (
        policies["privacy"]["public_synthetic_only"] is True
        and policies["privacy"]["transfer_private_data"] is False
        and policies["fallback"]["acer_cpu_fallback"] is False
        and policies["fallback"]["paid_providers"] is False
        and policies["claims"]["B8_8_of_8"] is False
    )
    read_only = (
        "permissions:\n  contents: read" in workflow
        and "permissions:\n  contents: read" in quality_gate
        and "persist-credentials: false" in workflow
        and "persist-credentials: false" in quality_gate
    )
    forbidden_files = [
        str(p.relative_to(ROOT)) for p in ROOT.rglob("*")
        if p.is_file() and not ".git" in p.parts
        and (p.name == ".env" or p.name.endswith((".key", ".p12", ".pfx"))
             or "private_key" in p.name.lower())
    ]
    public_apps = [probe_route(route) for route in ROUTES]
    report = {
        "schema": "AIKO_PUBLIC_CROSS_SECTOR_CERT_V1",
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source": "EPHEMERAL_GITHUB_RUNNER_INDEPENDENT_OF_ACER",
        "repository": os.environ.get("GITHUB_REPOSITORY", "UNKNOWN"),
        "head_sha": os.environ.get("GITHUB_SHA", "UNKNOWN"),
        "run_id": os.environ.get("GITHUB_RUN_ID", "UNKNOWN"),
        "scope": ["public_BOOM_route_smoke", "B8_cloud_policy_static",
                  "workflow_read_only", "forbidden_file_names"],
        "public_boom_routes": public_apps,
        "checks": {
            "boom_routes": all(route["pass"] for route in public_apps),
            "cloud_privacy_policy": privacy,
            "cloud_workflow_read_only": read_only,
            "no_obvious_private_key_file_names": not forbidden_files,
        },
        "forbidden_file_names": forbidden_files,
        "explicitly_not_certified": [
            "BOOM authentication/registration/payment full flows",
            "actual medical, camera or microphone usage",
            "Supabase private row-level authorization",
            "real Growth generated code delivery and recovery",
            "Cloudflare or Deno deployment",
            "production release/rollback",
            "AIKO B8 global 8/8",
        ],
        "claims": {"overall_global_certified": False, "B8_8_of_8": False},
        "changes_to_acer": False,
        "production_mutations": False,
        "paid_cloud_fallback": False,
    }
    report["public_scope_pass"] = all(report["checks"].values())
    f = OUT / "aiko-cross-sector-public-cert.json"
    f.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf8")
    result = {"public_scope_pass": report["public_scope_pass"],
              "checks": report["checks"],
              "route_results": [
                  {k: r.get(k) for k in ("path", "http", "pass", "error_type")}
                  for r in public_apps
              ]}
    print("AIKO_PUBLIC_CROSS_SECTOR", json.dumps(result, sort_keys=True))
    if not report["public_scope_pass"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
