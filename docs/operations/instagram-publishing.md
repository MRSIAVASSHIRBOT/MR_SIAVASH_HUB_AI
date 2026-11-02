# Instagram Graph API publishing adapter

## Current scope

The repository now contains a bounded, opt-in image-publishing adapter for the
Instagram Graph API. It uses an explicit API version, performs the two-step
container/publish flow, validates obvious non-public media URLs, bounds caption
length, classifies rate limits separately from ambiguous outcomes, and avoids
returning provider diagnostics or credentials in exceptions.

## Important integration gate

This adapter is not yet registered in the production publishing dispatcher.
The current media library stores local files, while Instagram's Graph API needs
an image URL it can fetch from the public internet. A local filesystem path or
loopback-only media endpoint is not sufficient. Do not enable Instagram dispatch
until a controlled public media-hosting adapter is implemented and connected to
approved draft media assets.

The adapter does not fetch user-supplied URLs itself. A future media-hosting
integration must use owner-scoped assets, enforce content-type and size limits,
use expiring or otherwise controlled public URLs where supported, and keep
provider tokens outside source control and logs.

## Required deployment acceptance

- Use an Instagram professional account and a Meta app with the necessary
  permissions and publishing access.
- Confirm the chosen Graph API version against current Meta documentation.
- Configure secrets through deployment environment/secret management only.
- Test with a controlled image and a test account after the public-media path is
  ready; verify the published result in the provider account.
- Keep ambiguous outcomes quarantined for operator reconciliation; do not
  blindly replay a publish request.
