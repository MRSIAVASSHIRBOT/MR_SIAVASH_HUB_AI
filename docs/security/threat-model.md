# Initial Threat Model

## 1. Security objective

Protect the user's device, accounts, private data, credentials, generated assets, and external services while enabling legitimate productivity, development, content creation, and defensive security work.

## 2. Assets

- Provider and integration credentials
- User files, conversation history, and memories
- Repository contents and source code
- Social publishing accounts and drafts
- Generated media and project assets
- Workflow definitions and execution logs
- Local machine and network access
- Audit records and configuration

## 3. Trust boundaries

1. Browser/UI to local API
2. User request to model-generated content
3. Orchestrator to tool adapters
4. Local runtime to external providers
5. Plugin publisher to installed plugin
6. Uploaded file to parsers and processors
7. Worker process to host operating system
8. Workspace data to retrieval/context assembly

Treat user content, model output, web pages, documents, and plugin responses as untrusted data.

## 4. Principal threats and controls

| Threat | Required control |
|---|---|
| Prompt injection in documents or web pages | Treat retrieved text as data; tool calls require independent policy checks |
| Secret leakage | Secret store/environment injection; redaction; no secrets in prompts or logs |
| Excessive agent authority | Least privilege; per-tool grants; scoped credentials; deny by default |
| SSRF or unsafe URL fetch | Scheme/host validation, private-address blocking, redirect revalidation, egress policy |
| Malicious or oversized uploads | Size/type limits, parser isolation, timeouts, safe temporary directories |
| Dependency compromise | Lockfiles, pinned versions, vulnerability scanning, review before upgrades |
| Cross-workspace data exposure | Workspace-scoped queries and authorization tests |
| Unintended public publishing | Draft-first default; approval gate for publish actions |
| Destructive file or repository changes | Dry-run, diff preview, backup, explicit approval and rollback plan |
| Resource exhaustion | Bounded concurrency, CPU/memory/time limits, queue quotas |
| Local API exposure | Loopback bind by default, authentication, CSRF protections where relevant |
| Password guessing / login resource exhaustion | Per-client failed-login throttling, bounded limiter state, generic authentication errors, no-store responses |
| Session token disclosure through caches | Bearer tokens returned only in no-store responses; session tokens stored as hashes |
| Audit tampering or data loss | Append-oriented audit records, backup, integrity checks |

## 5. Risk classes

- **Low:** local read-only queries and non-sensitive transformations.
- **Moderate:** reversible local writes, draft creation, bounded analysis.
- **High:** public publishing, external messages, account changes, repository writes, deletion, access to sensitive data, or financial side effects. Require explicit approval and a clear preview.
- **Prohibited:** credential theft, phishing kits, covert tracking, malware/payload generation, unauthorized access, evasion, or other harmful operations. Reject rather than route to a tool.

## 6. Execution policy

- Model output is never executable authority.
- Every tool call is schema-validated and policy-checked.
- Tools declare capabilities; undeclared capabilities are denied.
- Network access is off unless explicitly granted to a tool.
- Shell access is not a general-purpose agent tool.
- Long-running jobs are cancellable and bounded.
- High-impact operations require a human approval token tied to the exact action parameters.
- Approval expires and cannot be reused for modified parameters.

## 7. Secrets and privacy

- Never commit credentials, tokens, cookies, or private keys.
- Provide `.env.example` with placeholders only.
- Keep local secret files outside version control and restrict filesystem permissions.
- Redact authorization headers and known secret patterns.
- Do not send private files to cloud models unless the configured policy permits it.
- Memory retrieval must enforce source, workspace, and sensitivity scopes.

## 8. Defensive security scope

The Cybersecurity Lab is limited to defensive and authorized work: static analysis, dependency auditing, secure configuration review, log analysis, asset inventory within explicitly authorized scope, and educational safe-lab exercises. No credential collection, victim tracking, exploit deployment, payload generation, stealth, or evasion features.

## 9. Verification

Security tests must cover authorization boundaries, prompt-injection resistance at the tool boundary, SSRF controls, upload limits, secret redaction, workspace isolation, cancellation, and approval-token binding.

The current login throttle is process-local and assumes the documented single-process local runtime. A multi-worker or reverse-proxy deployment must use a shared rate-limit store and trusted-proxy configuration before exposure; forwarded client-address headers are not trusted by the application.

This is an initial threat model. Update it whenever a new integration, permission, data source, or execution capability is introduced.
