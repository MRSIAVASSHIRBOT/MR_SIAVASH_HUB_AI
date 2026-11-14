# Instagram Graph API publishing adapter

## Implemented integration path

The opt-in `InstagramGraphPublishingAdapter` is registered through the shared content publishing adapter factory when all required Instagram credentials are configured. It preserves the existing image flow and routes approved `content_type=reel` drafts through the official Reels container flow. The pull-driven `ContentScheduleDispatcher` supports the Instagram platform and, for approved owner-scoped JPEG/PNG assets, obtains a short-lived signed HTTPS media URL from the public-media route before calling the adapter.

The adapter performs the Graph API two-step container creation and publish flow. It validates HTTPS media URLs, rejects obvious private/local targets, bounds caption length, classifies rate limits separately from ambiguous outcomes, and does not expose provider diagnostics or credentials in errors.

## Configuration gates

All of the following must be configured in the protected environment:

- `MRH_INSTAGRAM_ACCESS_TOKEN`: access token for the authorized Instagram professional account.
- `MRH_INSTAGRAM_USER_ID`: professional account ID used by the Graph API.
- `MRH_INSTAGRAM_GRAPH_API_VERSION`: explicit supported Graph API version.
- `MRH_PUBLIC_MEDIA_BASE_URL`: public HTTPS origin that routes to this application's signed public-media endpoint.
- `MRH_PUBLIC_MEDIA_SIGNING_KEY`: high-entropy signing key kept separate from the database and source control.

The public media host must actually be reachable by Meta's servers. A syntactically valid URL is not proof of external reachability, correct TLS, or successful media retrieval. The signed URL is short-lived; do not publish it in logs, analytics, screenshots, or support messages.

## Safe acceptance procedure

1. Use an authorized Instagram professional test account and confirm the app has the required publishing permissions.
2. Confirm the selected Graph API version against current Meta documentation.
3. Configure credentials and signing material only through protected environment/secret management.
4. Verify the public-media origin from an independent external network and confirm that signed URLs expire and reject tampering.
5. Create a harmless JPEG/PNG test asset, attach it to a draft, review and explicitly approve the draft, then schedule it for a controlled test.
6. Run the pull-driven dispatcher manually in the test environment. Do not enable unattended production schedules during first acceptance.
7. Verify the published post in the provider account and record its provider post ID without exposing access tokens or signed media URLs.
8. Verify that invalid media, expired signatures, rate limits, provider rejections, and ambiguous network outcomes enter their documented states.

## Delivery semantics and operational limits

- The adapter does not provide exactly-once delivery. The two-step Graph API flow has no general idempotency guarantee.
- A transport failure or ambiguous provider response is quarantined as `unknown_outcome`; do not blindly retry it. Reconcile the provider account first.
- The dispatcher rechecks draft approval, version, content hash, and the durable emergency-stop flag before the provider side effect.
- Instagram image drafts accept JPEG/PNG. Reel drafts require an owner-owned, processed MP4 render output, a signed public HTTPS media URL, and the official Reels container readiness check before publication. The current local output ceiling is 100 MB; this is stricter than Meta's documented maximum.
- The application does not create an Instagram account, grant Meta permissions, or verify account eligibility.
- Telegram and Instagram publishing adapters remain opt-in; missing configuration fails closed.
