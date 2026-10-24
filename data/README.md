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

Generated data remain local and are ignored by Git, except the source manifest and reproducible reporting outputs. Source collection starts in Phase 1; these directories contain no documents yet.

The tracked `manifest.json` is a JSON array of source records. Each record requires `source_url`, `authority` (issuing authority), `title`, `publication_date` (ISO date), `version` (published version or revision), `retrieved_at` (ISO timestamp with time zone), `sha256` (lowercase SHA-256 hex), `reuse_terms`, `raw_path`, `public_document_confirmed: true`, and `personal_data_excluded: true`. Review the document before setting the two confirmations. Do not add a record for a patient-specific or private document.

The validator currently accepts HTTPS URLs under `minsalud.gov.co`. Add another verified official domain through a reviewed code change before using it. Run `uv run --frozen python -m colombia_health_rag.ingestion.manifest` to check the manifest. The validator checks metadata and source domains; it does not inspect downloaded file contents or verify a live website. A changed official document is a new manifest entry, never a silent replacement of raw data.
