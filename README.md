# AIKO Cloud Worker

Ephemeral zero-cost cloud worker for AIKO/OwnerBridge using GitHub Actions standard public-repository runners.

## Security model
- `workflow_dispatch` only; no `pull_request`, `push`, or arbitrary public trigger.
- Repository permissions are read-only inside the job.
- Every job manifest is signed with Ed25519 on ACER.
- The repository contains only the public verification key.
- Payload SHA-256 and expiry are verified before execution.
- Capability allowlist only: `sha256`, `json_canonicalize`, `forensics_merkle`, `hash_parallel`.
- No generic shell and no external write capability.
- Results are returned as short-lived GitHub Actions artifacts and revalidated on ACER.
- Sensitive/private payloads must remain LOCAL_ONLY and must never be routed to this public-cloud worker.
- Cost policy: EUR 0 only; no paid fallback.

## Runner target
`ubuntu-latest` standard GitHub-hosted public-repository runner.

## AIKO role
Optional third compute worker / burst node. If it is unavailable, AIKO must fall back to ACER or the persistent zero-cost queue.
