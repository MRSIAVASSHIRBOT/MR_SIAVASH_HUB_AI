# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0), and
the project version follows Semantic Versioning (SemVer).

## [Unreleased]

### Added
- Add an authenticated API for the synthetic, local-only Knowledge retrieval evaluation benchmark.
- Add hosted Windows clean-wheel build/install and packaged UI/API smoke coverage for Python 3.11 and 3.12.
- Add explicit encoded workflow-payload key loading regression coverage.

### Changed
- Pin checkout, setup-python, and upload-artifact GitHub Actions to verified immutable Node 24-compatible commits.
- Strengthen GitHub repository discovery by validating upstream identity, status-flag types, and bounded metadata normalization.
- Refresh release-management evidence to the 2026-11-08 main baseline; hosted CI evidence remains distinct from production acceptance.

### Notes
- The package metadata currently declares version `0.1.0` in `pyproject.toml`.
- This entry does not declare a published release or create a Git tag.
- Release notes for `0.1.0` must be assembled from merged changes and validated
  against the exact release commit before publication.
