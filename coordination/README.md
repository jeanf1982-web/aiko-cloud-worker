# AIKO cloud agent coordination — Candidate only

Scope: PUBLIC/SYNTHETIC AIKO data only. This folder is intentionally
**not a multi-project runtime** and is **not an OpenCode/Codex installation**.

- No token, secret, user data, chats, PII, payment, cryptographic material, or phone identity.
- No OpenCode/Codex authentication in GitHub Actions.
- No paid model inference; no hidden fallback to paid providers.
- No shell execution from requests, production deployment or access to ACER.
- All candidate effects are rejected by a **pure function**. This is a policy unit
  test, not a security boundary against hostile untrusted software.
- Workflow runs only Python stdlib checks on an ephemeral cloud runner,
  with read-only GitHub permissions; no automatic merge, releases or deploy.
- OwnerBridge staging & agent CLIs remain separate from cloud runner.
- Cloud running while ACER is off is validated only for the existing AIKO
  self-tests and synthetic workloads, not for always-on general-purpose AI.
- To add real unattended coding models later: assess official allowed
  authentication, privacy, quota, cost and cloud execution sandbox first.
  Consumer ChatGPT login must not be copied to unattended CI.
- AIKO, BOOM and BLACKLINK each require their own separated repository,
  policy, sensitive-data handling and production acceptance.
- Full change control: inventory -> isolated patch -> tests -> dependency
  review -> rollback plan -> explicit target-specific deployment approval.

Run local equivalent:
`python3 -m unittest discover -s coordination -p 'test_*.py' -v`

This is a nonproduction proposal. Main remains unchanged until reviewed.
