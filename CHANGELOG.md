# Changelog

All notable changes to this project are documented here. The project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Annex section parsing for the reviewed MIPRES table and service-habilitation manual, with citation metadata and mandatory OCR review flags.
- Synthetic and local-original layout checks for article headings, page breaks, running margins, and extraction failures.
- Exclusion checks that stop article extraction at the signing boundary and flag early approval blocks for manual review.
- PyMuPDF article parsing with resolution citations, page spans, section labels, and checksum verification.
- Reproducible official PDF checks and a reviewed, append-only source refresh workflow.
- Four original official resolutions in the provenance manifest, with source and publication details.
- Corpus screening and limited public-official attribution policy.
- Official-source manifest schema and validation for public regulation provenance.
- Public regulation RAG roadmap, source policy, FTI pipeline map, and Project workflow.
- GitHub Actions checks for locked dependencies, code quality, tests, documentation, static security issues, and committed-file secrets.

### Changed

- Adapted the data-science template to article-level regulation retrieval and removed unrelated template content.
