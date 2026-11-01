# Task manager operations

The task lifecycle is persisted in SQLite and exposed through authenticated
API routes. Tasks are submitted with `POST /tasks`, listed with
`GET /tasks`, and inspected with `GET /tasks/{task_id}`.

## Queue summary

`GET /jobs/summary` returns aggregate task counts by lifecycle status, the
number of scheduled retries, the explicitly registered handler names, and the
worker execution mode. It does not include task descriptions, prompts, or
execution results. The worker remains pull-driven: this endpoint does not
start a worker or process queued tasks.

## Execution results

`GET /tasks/{task_id}/result` returns the persisted result and sanitized
execution metadata after a worker has processed the task. It returns 409 while
the task has not been processed and 404 when the task does not exist. Error
details are represented by stable error codes rather than raw exception text.

## Operational boundaries

- The worker is invoked explicitly with `WorkerEngine.run_once()`; application
  startup does not execute queued tasks.
- Only registered handlers can run. Unknown task types fail closed.
- Retry is restricted to the explicitly allow-listed deterministic
  `demo.echo` task type.
- High-risk tasks require an approval matching the task-intent fingerprint.
- Queue summaries and result retrieval require an authenticated session.
