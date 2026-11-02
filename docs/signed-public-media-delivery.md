# Signed public media delivery

The application keeps uploaded media private by default. Instagram Graph API image publishing
requires a publicly reachable HTTPS URL, so the optional signed route is disabled unless
both settings below are supplied:

- `MRH_PUBLIC_MEDIA_BASE_URL`: externally reachable HTTPS origin, for example
  `https://media.example.org`. Do not use a loopback, LAN-only, or development hostname.
- `MRH_PUBLIC_MEDIA_SIGNING_KEY`: random secret of at least 32 characters. Keep it out of
  source control and logs; rotate it if exposed.

The route `GET /public/media/{asset_id}?expires=...&signature=...` only serves JPEG/PNG
assets stored in the media metadata table. Its HMAC binds the UUID and expiry, expiry is
limited to 15 minutes, comparisons are constant-time, and the URL never accepts a path or
owner identifier. It does not expose the authenticated media management endpoints.

The origin must be configured at the public reverse proxy/CDN and verified from outside the
deployment network. Merely setting an HTTPS URL does not prove reachability. Apply request
rate limits at the edge and avoid logging query strings because they contain short-lived
bearer signatures.

The pull-driven dispatcher now generates a short-lived signed URL for approved JPEG/PNG
assets when processing an Instagram schedule. The API still does not prove that the configured
origin is reachable from Meta; verify that externally, then run an end-to-end acceptance test
against a controlled professional Instagram account before enabling production schedules.
