# Local Operator UI

The operator dashboard is served by the same FastAPI process at `/ui/`. It has no CDN, remote font, analytics, external script, or external stylesheet dependency. The static shell can be opened without a token, but all private data and mutation APIs remain protected by the existing bearer authentication.

## First run and sessions

1. Open `http://127.0.0.1:8000/ui/` on the machine running the API.
2. If the owner account has not been initialized, expand **راه‌اندازی اولیه** and set a strong password. The backend accepts initial setup only from a loopback client and only once.
3. Log in as `owner`. The bearer token is held in browser `sessionStorage`, not `localStorage`, and is cleared by logout. Do not use the dashboard in a browser profile shared with untrusted users.
4. If the API restarts or the token expires, log in again.

## Dashboard functions

- Read liveness/readiness and worker status.
- View live Job Engine counters: task states, retry schedule, recovery-required workflows, expired leases, oldest queued age, and pull-driven execution mode.
- View bounded, owner-scoped workflow history and inspect step status, attempt count, and sanitized error codes.
- Cancel eligible queued/running tasks and queued/running/paused workflows.
- Check a paused workflow's resume decision and enqueue a resume. The original request JSON must be supplied again; the UI never receives stored payloads or executes workflow steps.
- Reconcile an unknown external outcome only after independently verifying the remote result. The UI records a user-supplied outcome and digest; it does not call the external service.
- View the configured provider catalog without triggering health checks or inference.
- View recent tasks.
- Create, search, and delete private memory notes.
- Ingest bounded text/Markdown knowledge documents, search citations, and delete documents.
- Invoke the local model endpoint explicitly.
- Invoke OpenRouter only by pressing the separate remote button. This sends the submitted text to a third party and may incur cost; remote inference remains disabled unless explicitly configured.

The UI does not expose arbitrary shell execution, arbitrary file paths, or automatic publishing. Workflow resume is queued for the pull worker; no workflow tool is executed in the browser or API request handler.

## Browser security

- The UI uses same-origin API requests and does not include third-party assets.
- A restrictive Content Security Policy disallows inline scripts, external script/style origins, objects, and framing.
- Dynamic text is rendered with DOM `textContent`; user-controlled note/document text is never interpolated into HTML.
- Requests use `cache: no-store`, omit ambient cookies, and reject redirects.
- The session token exists only in `sessionStorage` for the current tab session. Logout attempts server-side invalidation and always clears the local token.

## Deployment boundary

The API binds to loopback by default. Do not expose it directly to a public network without a separate deployment review covering TLS, trusted-proxy behavior, rate-limit storage, CSRF/session boundaries, backup policy, and network egress. The browser UI does not replace API authorization.


## Owner-scoped media and video rendering

- Upload, list, download and delete owner-scoped media assets. Downloads use an authenticated same-origin request with no ambient cookies or cache.
- Submit a cut-only MP4 render from a completed video analysis with a valid timeline, manually refresh status, and request cancellation for queued/running renders.
- Render IDs and the analysis association are retained only in the current browser tab session. The pending idempotency key is also retained for the same analysis so an uncertain submission can be retried without creating a duplicate job.
- Completed output is downloaded through the authenticated media route; the bearer token is never placed in a URL.
- Render output is silent and hard-cut-only. The UI does not claim audio, captions, graphics, transitions, effects or AI-generated video.
- Status refresh is user-initiated; the page does not start background polling. The pull Worker must be running separately for queued jobs to execute.
