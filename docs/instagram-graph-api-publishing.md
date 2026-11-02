# Instagram Graph API publishing configuration

Instagram publishing is opt-in and remains disabled unless all three settings are present:

- `MRH_INSTAGRAM_ACCESS_TOKEN`: access token for the authorized Instagram professional account.
- `MRH_INSTAGRAM_USER_ID`: Instagram professional account ID used by the Graph API.
- `MRH_INSTAGRAM_GRAPH_API_VERSION`: explicitly selected Graph API version, such as `v24.0`.

Do not commit tokens to source control or include them in logs. Use environment secrets or a protected local environment file, and rotate credentials if exposed. The application does not create an Instagram account, grant permissions, or verify that the token has the required publishing scopes.

The adapter creates a media container and then requests publication. It requires a publicly reachable HTTPS image URL in the adapter payload; a private local media asset is not enough. The current authenticated media-download route is not a public media host, so end-to-end scheduled Instagram image publishing is not considered complete until an explicitly configured public media delivery path is implemented and tested.

The adapter does not claim exactly-once delivery. Ambiguous network/provider outcomes are quarantined by the scheduler rather than blindly retried. Start with a controlled test account and verify the published result in Instagram before enabling production schedules.
