# Workflow execution-input storage

Workflow requests are not persisted as plaintext. The execution-input repository stores a bounded JSON payload encrypted with Fernet only when `MRH_WORKFLOW_INPUT_ENCRYPTION_KEY` is configured. Generate a key with:

```python
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode("ascii"))
```

Store the key in the deployment's secret manager or a local environment file excluded from version control. Never commit it, log it, or include it in issue/PR text. Losing the key makes existing encrypted payloads unrecoverable; key rotation requires an explicit migration strategy and is not automatic.

The repository rejects sensitive-looking field names, caps serialized input at 64 KiB, authenticates ciphertext, checks a SHA-256 payload digest, scopes reads/deletes by owner, and supports an optional expiry. This key-name check is a guardrail, not a secret detector: callers must not put credentials or secrets into durable workflow inputs. Prefer secret references resolved at execution time.

If encryption is not configured, persistence fails closed. No plaintext fallback exists. This storage primitive does not by itself enable worker dispatch; dispatch remains disabled until the worker-owned lifecycle and cancellation/recovery integration are implemented and tested.
