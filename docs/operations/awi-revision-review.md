# Revision diff and approval record

`compare_revisions` produces a stable SHA-256 digest bound to a revision number and canonicalized step data, and categorizes added, removed, changed, and unchanged step IDs.

`record_review` records an explicit boolean decision with reviewer text and an optional note. The record is bound to the exact proposal digest, so a review of one proposal does not implicitly apply to another.

**Important:** This is a review-record utility, not an authentication system or execution authorization. Reviewer identity is caller-supplied and must be authenticated by an integrating application. Approval records do not dispatch, execute, or unlock tools. Existing policy enforcement remains mandatory.
