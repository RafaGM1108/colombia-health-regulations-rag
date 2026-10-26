# Colombian Health Regulations RAG

[![CI](https://github.com/RafaGM1108/colombia-health-regulations-rag/actions/workflows/ci.yml/badge.svg)](https://github.com/RafaGM1108/colombia-health-regulations-rag/actions/workflows/ci.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Retrieval and article-level citation of public Colombian health regulations. The planned system answers questions about topics such as MIPRES prescriptions and home healthcare using only official public documents.

> Informational only; not legal or medical advice. Confirm current rules in the cited official document before acting.

## Scope and data policy

- Sources are limited to public documents published by the Ministerio de Salud y Protección Social and other official Colombian authorities.
- Each document must have a recorded URL, title, publication date, version or revision, retrieval date, and SHA-256 checksum before indexing.
- Patient records, private messages, and non-public documents are excluded. Original official PDFs may contain the names, roles, and signatures of officials in signing or approval blocks; this is the sole permitted personal-data exception. Those details are never indexed or reproduced in answers. See the [corpus policy](docs/data.md).
- Answers must cite the resolution and article or section. When the indexed corpus cannot support an answer, the system must say so.
- The initial source manifest contains four official resolutions. Article parsing is available for reviewed local PDFs; indexing and evaluation results are not yet available. The first release will report measured results from a reproducible evaluation run.

## Architecture

The FTI pattern is mapped to this retrieval system as follows:

| Pipeline | Input | Output | Roadmap |
|---|---|---|---|
| Ingestion | Official public documents and source manifest | Parsed articles and sections with provenance | Phases 1–2 |
| Indexing | Validated chunks | Multilingual embeddings and vector index | Phases 3–4 |
| Serving | Question, index, and cited passages | Grounded answer with resolution and article citations | Phases 5–6 |

The stack uses PyMuPDF for article parsing. Sentence-transformers, Chroma or DuckDB VSS, Anthropic API, FastAPI, and Streamlit cover the planned later stages. The current repository also contains a health endpoint and a UI landing page. Retrieval and answer generation will be added through the roadmap issues.

## Roadmap

| Phase | Deliverable |
|---|---|
| 0 | Repository, public [Project](https://github.com/users/RafaGM1108/projects/13), and green CI |
| 1 | Official-source corpus and metadata manifest |
| 2 | PDF parsing and article-aware chunking with tests |
| 3 | Multilingual embeddings and reproducible index |
| 4 | Hand-written Q&A set, hit rate@k, MRR, and chunking comparison |
| 5 | Cited generation, faithfulness and correctness evaluation, and refusal on missing evidence |
| 6 | FastAPI and Streamlit chat with visible disclaimer |
| 7 | README results from real measurements and v1.0.0 release |

Each phase is a [GitHub milestone](https://github.com/RafaGM1108/colombia-health-regulations-rag/milestones). Work moves through Backlog, Ready, In Progress, In Review, and Done, with at most two items In Progress. Each issue is developed on a branch and reviewed in a pull request before merging.

## Development

Requires Python 3.12, [uv](https://docs.astral.sh/uv/), and `make`.

```bash
git clone https://github.com/RafaGM1108/colombia-health-regulations-rag.git
cd colombia-health-regulations-rag
make install
make lint typecheck test
```

The local API health endpoint is available with `make api`; the landing page with `make app`. A real Anthropic key belongs only in a local `.env` file, never in Git. The generation feature is not available during Phase 0.

CI checks lockfile consistency, formatting, lint, types, tests with coverage, documentation, static security issues, and committed-file secrets. The same core checks run locally with `make lint typecheck test`.

`make corpus-check` downloads the current official PDFs and compares them with the manifest. It requires `curl` and network access. A changed PDF is saved as an ignored local candidate for manual review; [the refresh procedure](docs/data.md) explains how to record a new version without replacing the old one.

The [article parsing procedure](docs/data.md#article-parsing) reads a checksum-verified local PDF and returns numbered articles with resolution, section, and page metadata. It keeps results in memory while the signing-block exclusion checks are completed.

## Repository structure

```text
conf/base.yaml                 Paths and application name
data/                          Local raw, parsed, chunk, embedding, index, evaluation, reporting layers
docs/                          Source policy and methodology
src/colombia_health_rag/       Ingestion, indexing, serving, API, UI, and shared utilities
tests/                         Configuration and API checks
```

The [data policy](data/README.md) explains the layer boundaries. [Methodology](docs/methodology.md) describes the planned evaluation and citation contract.

## Results

Evaluation metrics will appear here only after the Q&A set and index are run. Values will link to committed files in `data/07_reporting/`.

## Author

Rafael E. Garcia · [GitHub](https://github.com/RafaGM1108) · [LinkedIn](https://www.linkedin.com/in/rafaelgarcia11)

Code is licensed under [MIT](LICENSE). Source documents retain their original terms and remain attributable to their publishers.
