# Data layers

Only official public Colombian health regulations are eligible for ingestion. No patient or personal data may be added to any layer.

| Layer | Contents | Producer |
|---|---|---|
| `01_raw` | Downloaded official files, unchanged | Ingestion |
| `02_parsed` | Extracted text and document structure | Ingestion |
| `03_chunks` | Resolution, article, and section-aware passages | Ingestion |
| `04_embeddings` | Multilingual passage vectors | Indexing |
| `05_index` | Search index and metadata | Indexing |
| `06_evaluation` | Hand-written Q&A set and experiment inputs | Evaluation |
| `07_reporting` | Reproducible metrics and figures for the README | Evaluation |

Generated data remain local and are ignored by Git, except reproducible reporting outputs. Source collection starts in Phase 1; these directories contain no documents yet.

The manifest must record source URL, title, issuing authority, publication date, version or revision, retrieval timestamp, local file path, SHA-256 checksum, and any applicable reuse terms. A changed official document is a new manifest entry, never a silent replacement of raw data.
