# Automated Python Code Scanning

The repository uses GitHub CodeQL advanced setup as a second, semantic security-analysis layer alongside the local read-only NEXUS checks, defensive configuration review, Ruff, and dependency auditing.

## Coverage

- Language: Python
- Build mode: `none` (the supported interpreted-language mode; the workflow does not execute project code to build a database)
- Query suite: `security-extended`
- Triggers: pull requests and pushes to `main`, manual dispatch, and a weekly scheduled scan
- Results: uploaded to GitHub Code Scanning and associated with the analyzed commit or pull request

The action references are pinned to full commit SHAs. Update them only after reviewing the upstream release, its changelog, and the resolved commit.

## Permissions

The workflow grants only `contents: read`, `actions: read`, and `security-events: write`. It does not receive repository write, package, deployment, or secret-management permissions. CodeQL analysis does not run arbitrary agent tools and does not modify the analyzed source tree.

## Operational notes

1. Review findings in the repository's **Security → Code scanning** view and in pull-request checks.
2. Treat findings as review evidence, not as proof that a vulnerability is exploitable. Validate the affected data flow and the actual deployment boundary.
3. Fix confirmed issues in a separate change and retain regression tests.
4. Keep the existing local checks: CodeQL complements them; it does not replace Ruff, pytest, dependency auditing, or the project's own defensive analysis.
5. If code scanning is unavailable for the repository or organization, the workflow will report an upload/permission failure. Do not silently interpret that as a clean scan.

## Upstream component and licensing

This workflow uses the official [GitHub CodeQL Action](https://github.com/github/codeql-action), whose action code is MIT-licensed. The CodeQL CLI/bundle has separate GitHub CodeQL terms. GitHub documents use of the CodeQL CLI for open-source projects hosted on GitHub and for eligible private repositories with GitHub Advanced Security. This repository is public; verify current GitHub terms before changing repository visibility or reusing the workflow elsewhere.

No third-party scanner source code is copied into this repository.
