# HTTP error-detail disclosure audit

**Scope:** the API route layer on the H8 security PR head. All 31 Python modules
under `backend/mrhub/api/routes/` were reviewed for `HTTPException(detail=...)`
construction and dynamic detail propagation.

## Route-by-route coverage

| Route module | Review outcome |
|---|---|
| `__init__.py` | No public detail source; covered by the shared handler |
| `agent.py` | Static literals are allowlisted; exception text and provider codes fall back to the status message |
| `agent_context.py` | Static literals are allowlisted; dynamic values fall back |
| `agent_model_runs.py` | Static literals are allowlisted; dynamic values fall back |
| `agent_proposals.py` | Static literals are allowlisted; dynamic values fall back |
| `agent_run.py` | Static literals are allowlisted; dynamic values fall back |
| `approvals.py` | Static literals are allowlisted; exception text falls back |
| `auth.py` | Static literals are allowlisted; dynamic values fall back |
| `capabilities.py` | Static literals are allowlisted; `str(exc)` and dynamic code/message mappings fall back |
| `content.py` | Static literals are allowlisted; exception text falls back |
| `content_campaigns.py` | Static literals are allowlisted; exception text falls back |
| `content_schedules.py` | Static literals are allowlisted; exception text falls back |
| `devices.py` | Static literals are allowlisted; pairing/task exception text is not reflected unless separately reviewed |
| `health.py` | Static literals are allowlisted; dynamic values fall back |
| `jobs.py` | Static literals are allowlisted; exception text falls back |
| `knowledge.py` | Static literals are allowlisted; dynamic values fall back |
| `knowledge_evaluation.py` | Static literals are allowlisted; dynamic values fall back |
| `media.py` | Static literals are allowlisted; dynamic values fall back |
| `memory.py` | Static literals are allowlisted; dynamic values fall back |
| `models.py` | Static literals are allowlisted; dynamic profile identifiers and exception text fall back |
| `nexus.py` | Static literals are allowlisted; dynamic values fall back |
| `platform.py` | Static literals are allowlisted; dynamic values fall back |
| `policy.py` | Static literals are allowlisted; policy reasons are replaced by the fixed decision-message map |
| `projects.py` | Static literals are allowlisted; dynamic values fall back |
| `public_media.py` | Static literals are allowlisted; dynamic values fall back |
| `research.py` | Static literals are allowlisted; exception-derived validation/conflict messages fall back |
| `resource_reply.py` | Static literals are allowlisted; exception text falls back |
| `security_lab.py` | Static literals are allowlisted; dynamic values fall back |
| `tasks.py` | Static literals are allowlisted; dynamic values fall back |
| `telegram_integration.py` | Static literals are allowlisted; provider/exception values fall back |
| `video_intelligence.py` | Static literals are allowlisted; dynamic provider/exception values fall back |

## Enforced disclosure policy

1. `SAFE_PUBLIC_ERROR_DETAILS` contains exact reviewed static messages only.
   The current allowlist contains 241 bounded source literals; interpolated
   values, exception text, provider bodies and request-controlled data are not
   admitted.
2. The legacy object compatibility set is exact-match only. Arbitrary nested
   objects, provider payloads and user-controlled identifiers are rejected.
3. Policy decisions preserve only the fixed decision enum
   (`allow`, `deny`, `require_approval`) and a server-authored reason message.
   An optional correlation ID is retained only when it is a canonical UUID.
4. Every unreviewed `HTTPException.detail` falls back to the generic message
   associated with the HTTP status. This centrally covers dynamic call sites
   such as `str(exc)`, `exc.code`, `decision.reason` and structured provider
   errors without relying on each route to remember a redaction rule.
5. Request-validation errors retain bounded structural locations and error
   types only; raw input, Pydantic context and arbitrary field names are omitted.
6. Unhandled exceptions return a generic 500 body. Server logs contain the
   request correlation ID and exception type, not exception text.

## Regression coverage

- `tests/test_api_error_contract.py`: reviewed legacy detail compatibility,
  dynamic string/nested-object sentinel rejection, policy decision mapping,
  request correlation and generic unhandled errors.
- `tests/test_device_pairing.py`: verifies that reviewed static pairing
  messages remain compatible while the typed error envelope stays stable.
- `tests/test_api_error_openapi_contract.py`: verifies the documented shared
  error schema and runtime model contract.

This is a source-level boundary. It does not claim that a secret was previously
exposed, and it does not change live database state, deployment settings,
provider credentials, or external services.
