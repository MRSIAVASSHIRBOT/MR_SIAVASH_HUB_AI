# Workflow execution-input storage

Workflow requests are not persisted as plaintext. The execution-input repository stores a bounded JSON payload encrypted with Fernet only when `MRH_WORKFLOW_INPUT_ENCRYPTION_KEY` is configured. Generate a key with:

```python
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode("ascii"))
```

Store the key in the deployment's secret manager or a local environment file excluded from version control. Never commit it, log it, or include it in issue/PR text. Losing the key makes existing encrypted payloads unrecoverable; key rotation requires an explicit migration strategy and is not automatic.

The repository rejects sensitive-looking field names, caps serialized input at 64 KiB, authenticates ciphertext, checks a SHA-256 payload digest, scopes reads/deletes by owner, and supports an optional expiry. This key-name check is a guardrail, not a secret detector: callers must not put credentials or secrets into durable workflow inputs. Prefer secret references resolved at execution time.

If encryption is not configured, persistence fails closed. No plaintext fallback exists. The workflow API currently queues work and `WorkerEngine` dispatches `agent.workflow` tasks through the worker-owned path, which decrypts and validates the stored request before invoking allow-listed tools. Cancellation and recovery have explicit fail-closed paths, but production readiness still requires the complete CI suite to pass and additional fault-injection coverage for lease loss, cancellation races, and interrupted external side effects. Do not treat the presence of this storage primitive as proof that those operational guarantees have been validated.
