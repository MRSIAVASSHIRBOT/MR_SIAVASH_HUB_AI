# Instagram Graph API publishing configuration

Instagram publishing is opt-in and remains disabled unless all three settings are present:

- `MRH_INSTAGRAM_ACCESS_TOKEN`: access token for the authorized Instagram professional account.
- `MRH_INSTAGRAM_USER_ID`: Instagram professional account ID used by the Graph API.
- `MRH_INSTAGRAM_GRAPH_API_VERSION`: explicitly selected Graph API version, such as `v24.0`.

Do not commit tokens to source control or include them in logs. Use environment secrets or a protected local environment file, and rotate credentials if exposed. The application does not create an Instagram account, grant permissions, or verify that the token has the required publishing scopes.

The image adapter creates an image media container and then requests publication. The combined Instagram publishing adapter also supports approved Reels: it creates a `media_type=REELS` container with `video_url`, checks `status_code`, and only requests `media_publish` after the container reports `FINISHED`. Both flows require a publicly reachable HTTPS media URL; a private local asset is not enough. The authenticated media-download route is private. The optional signed public-media route is integrated with the pull-driven dispatcher for approved JPEG/PNG assets and processed MP4 render outputs. It remains disabled unless its public HTTPS origin and signing key are configured. MP4 delivery validates the ISO-BMFF `ftyp` signature and enforces the local 100 MB output ceiling. External reachability and a controlled professional-account acceptance test are still required.

The adapter does not claim exactly-once delivery. Ambiguous network/provider outcomes are quarantined by the scheduler rather than blindly retried. Start with a controlled test account and verify the published result in Instagram before enabling production schedules.
