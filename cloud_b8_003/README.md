# AIKO B8-003 — cloud acceptance

This repository runs **public synthetic checks** on GitHub-hosted standard runners, not ACER. The workflow verifies three batches of 100 cases (delivery, recovery with stale lease rejection, and byte-exact rollback), plus a separately recomputed SHA-256 receipt linked to GitHub run ID and commit.

- No personal data, tokens, local filesystem access, or untrusted jobs are accepted.
- No production release, ACER resource usage, cloud billing activation, or real Growth provenance is implied.
- The `federation_policy.json` is a policy/registry, **not** proof that Cloudflare or Deno are integrated for B8-003.
- A cloud runner is ephemeral; durable receipts are GitHub Actions artifacts retained for seven days. These are not a durable cross-provider job queue.
- The workflow runs daily on `main` and on relevant changes, with permissions `contents: read` and no paid-provider fallback.
- A real B8 8/8 requires the actual Growth-generated code, independently verified regressions, a guarded real release, a verified rollback, and an independent certificate.

No private data or local ACER paths belong in this repository.
