# Public GitHub repository discovery

## Current implementation

The authenticated `POST /capabilities/discover` endpoint accepts a public repository URL such as `https://github.com/OWNER/REPO`. It calls only the fixed GitHub API metadata endpoint and uses a bounded timeout and response-size limit. It records the candidate in the local catalog with repository name, description, default branch, primary language, topics, license identifier when available, archive/fork flags, update time, and public activity counts.

The endpoint is metadata-only. It does not clone the repository, fetch source files, install dependencies, import modules, execute scripts, or approve the candidate. Duplicate sources return a conflict. Missing repositories, rate limits, timeouts, and upstream failures are reported with bounded error responses.

## API example

Request:

```http
POST /capabilities/discover
Content-Type: application/json
Authorization: Bearer <local-session-token>

{
  "source_url": "https://github.com/OWNER/REPO"
}
```

The result contains the discovered repository metadata, the local candidate record, and explicit false flags for source execution, installation, and approval.

## Next stages

1. Retrieve release metadata and license-file metadata using fixed GitHub API routes.
2. Pin the repository identity and observed revision so future reviews are reproducible.
3. Compare declared capabilities against the existing registry to find duplicates and complementary features.
4. Inspect source files as inert text only, with size and file-type limits.
5. Evaluate dependency, license, security, compatibility, and data/network behavior.
6. Run approved tests in an isolated, resource-bounded environment.
7. Activate only a reviewed adapter behind a feature flag, with logs and rollback.

Discovery is not approval. No discovered repository should gain filesystem, network, process, secret, or shell access merely because it was registered.
