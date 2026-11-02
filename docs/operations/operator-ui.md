# Local Operator UI

The operator dashboard is served by the same FastAPI process at `/ui/`. It has no CDN, remote font, analytics, external script, or external stylesheet dependency. The static shell can be opened without a token, but all private data and mutation APIs remain protected by the existing bearer authentication.

## First run and sessions

1. Open `http://127.0.0.1:8000/ui/` on the machine running the API.
2. If the owner account has not been initialized, expand **راه‌اندازی اولیه** and set a strong password. The backend accepts initial setup only from a loopback client and only once.
3. Log in as `owner`. The bearer token is held in browser `sessionStorage`, not `localStorage`, and is cleared by logout. Do not use the dashboard in a browser profile shared with untrusted users.
4. If the API restarts or the token expires, log in again.

## Dashboard functions

- Read liveness/readiness and worker status.
- View the configured provider catalog without triggering health checks or inference.
- View recent tasks.
- Create, search, and delete private memory notes.
- Ingest bounded text/Markdown knowledge documents, search citations, and delete documents.
- Invoke the local model endpoint explicitly.
- Invoke OpenRouter only by pressing the separate remote button. This sends the submitted text to a third party and may incur cost; remote inference remains disabled unless explicitly configured.

The UI does not expose arbitrary shell execution, arbitrary file paths, or automatic publishing.

## Browser security

- The UI uses same-origin API requests and does not include third-party assets.
- A restrictive Content Security Policy disallows inline scripts, external script/style origins, objects, and framing.
- Dynamic text is rendered with DOM `textContent`; user-controlled note/document text is never interpolated into HTML.
- Requests use `cache: no-store`, omit ambient cookies, and reject redirects.
- The session token exists only in `sessionStorage` for the current tab session. Logout attempts server-side invalidation and always clears the local token.

## Deployment boundary

The API binds to loopback by default. Do not expose it directly to a public network without a separate deployment review covering TLS, trusted-proxy behavior, rate-limit storage, CSRF/session boundaries, backup policy, and network egress. The browser UI does not replace API authorization.
