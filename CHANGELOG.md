# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- Author name is Rafael E. Garcia (#5).

### Changed

- Codecov uploads authenticate with OIDC instead of a token secret and fail the CI on error;
  added `codecov.yml` with 80% project and patch targets (#3).
- Dependabot no longer proposes major/minor Python bumps of the Docker base image (#3).
- README rename procedure takes separate package and repo names; setup steps list the labels
  to create and the Codecov app (#3).
- Issue forms apply `type:feat` and `type:bug`; CLAUDE.md workflow heading renamed to
  "Kanban workflow" (#3).

### Added

- Initial project template: layered data folders, staged notebooks, `ds_project` package
  with feature/training/inference pipelines, FastAPI service and Streamlit app.
- Typed configuration loader for `conf/base.yaml` and shared logging setup.
- Tooling: uv, ruff, mypy, bandit, pytest + coverage, pre-commit, Makefile.
- GitHub Actions CI with Codecov upload, Dependabot, PR and issue templates.
- MkDocs Material documentation skeleton, devcontainer and multi-stage Dockerfile.
