# Data layers

Only official public Colombian health regulations are eligible for ingestion. Patient and private data are excluded from every layer. Unchanged official PDFs in the local raw layer may contain public officials' names, roles, and signatures in signing or approval blocks; these details must not flow into derived layers. See the [corpus policy](../docs/data.md).

| Layer | Contents | Producer |
|---|---|---|
| `01_raw` | Downloaded official files, unchanged | Ingestion |
| `02_parsed` | Extracted text and document structure | Ingestion |
| `03_chunks` | Resolution, article, and section-aware passages | Ingestion |
| `04_embeddings` | Multilingual passage vectors | Indexing |
| `05_index` | Search index and metadata | Indexing |
| `06_evaluation` | Hand-written Q&A set and experiment inputs | Evaluation |
| `07_reporting` | Reproducible metrics and figures for the README | Evaluation |

Generated data remain local and are ignored by Git, except the source manifest, the source-specific reviewed table ledger, and reproducible reporting outputs. Four original PDFs have been collected locally for Phase 1 and are not committed. Clone users can retrieve the same source URLs recorded in the manifest and compare SHA-256 checksums.

The tracked `manifest.json` is a JSON array of source records. Each record requires `source_url`, `authority` (issuing authority), `title`, `publication_date` (ISO date), `version` (published version or revision), `retrieved_at` (ISO timestamp with time zone), `sha256` (lowercase SHA-256 hex), `reuse_terms`, `raw_path`, `public_document_confirmed: true`, and `personal_data_scope: "official_attribution_only"`. Review the document before setting the confirmations. The scope value means that any personal data in the original are confined to officials' signing or approval blocks. Do not add a record for a patient-specific or private document.

The validator currently accepts HTTPS URLs under `minsalud.gov.co`. Add another verified official domain through a reviewed code change before using it. Run `uv run --frozen python -m colombia_health_rag.ingestion.manifest` to check the manifest. The validator checks metadata and source domains; it does not inspect downloaded file contents or verify a live website. A changed official document is a new manifest entry, never a silent replacement of raw data.

Run `make corpus-check` to compare the live official files with their recorded checksums. The [refresh procedure](../docs/data.md) covers candidate review and new version records. Raw snapshots and candidates remain ignored by Git.

The tracked `reviews/resolution-740-annex.json` contains checked, non-personal table terms for one exact official PDF checksum. It is not a replacement for the official PDF and cannot validate a changed source version.

The tracked `reviews/resolution-3100-home-care.json` records 19 visually checked manual excerpts from the exact official PDF checksum, including consultation and therapy service blocks applicable to domiciliary care. Each excerpt has an official section citation and page span; `excerpt_id` keeps excerpts from the same section distinct. All other manual text remains flagged and excluded until reviewed.
