# Changelog

All notable changes to this project are documented here. The project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Fixed Spanish retrieval evaluation set with official-source article and annex locators, expected answers, and unanswerable cases.
- Persistent Chroma index with official-source provenance checks, versioned rebuilds, and metadata-filtered vector search.
- Pinned multilingual passage embedding build with token-bounded article chunks, reviewed-annex inputs, and resumable local batches.
- OCR-reviewed domiciliary consultation and therapy service excerpts from Resolution 3100, with distinct excerpt IDs and checked page boundaries.
- OCR-reviewed home-care manual excerpts from Resolution 3100, with section/page citations and a checksum-bound indexing gate.
- Source-checked Resolution 740 annex table ledger for 212 rows, with corrected OCR codes, page-local citations, and a verified-row indexing gate.
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
