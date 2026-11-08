# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0), and
the project version follows Semantic Versioning (SemVer).

## [Unreleased]

### Added
- Harden the scheduled development publisher's artifact boundary with normalized staged-path validation and Node 24 artifact actions.
- Initial release-management baseline and release-readiness documentation.

### Changed
- Refresh release-management evidence to the 2026-11-04 main baseline and align platform acceptance references with the maintained Windows checklist.

### Notes
- The package metadata currently declares version `0.1.0` in `pyproject.toml`.
- This entry does not declare a published release or create a Git tag.
- Release notes for `0.1.0` must be assembled from merged changes and validated
  against the exact release commit before publication.

- Harden scheduled development: disable OpenCode shell execution and external-directory access while the provider credential is present; protect OpenCode project configuration from agent proposals.
- Expand the scheduled publisher's protected-path policy to cover API authorization/policy/tool routes, workflow execution endpoints, API dependencies/configuration, and the tool registry/built-ins.
