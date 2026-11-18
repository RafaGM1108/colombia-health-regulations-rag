# Colombian Health Regulations RAG

[![CI](https://github.com/RafaGM1108/colombia-health-regulations-rag/actions/workflows/ci.yml/badge.svg)](https://github.com/RafaGM1108/colombia-health-regulations-rag/actions/workflows/ci.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Retrieval and article-level citation of public Colombian health regulations. The system answers questions about topics such as MIPRES prescriptions and home healthcare using only official public documents.

> Informational only; not legal or medical advice. Confirm current rules in the cited official document before acting.

## Scope and data policy

- Sources are limited to public documents published by the Ministerio de Salud y Protección Social and other official Colombian authorities.
- Each document must have a recorded URL, title, publication date, version or revision, retrieval date, and SHA-256 checksum before indexing.
- Patient records, private messages, and non-public documents are excluded. Original official PDFs may contain the names, roles, and signatures of officials in signing or approval blocks; this is the sole permitted personal-data exception. Those details are never indexed or reproduced in answers. See the [corpus policy](docs/data.md).
- Answers must cite the resolution and article or section. When the indexed corpus cannot support an answer, the system must say so.
- Generation accepts only reviewed public question IDs; free-form text is limited to local passage search and is never stored, logged, or sent to an external API. See the [input contract](docs/interface.md).
- The source manifest contains four official resolutions. Article parsing, reviewed annex excerpts, multilingual embeddings, and a provenance-aware local Chroma index are available. Retrieval has been measured on the fixed Q&A set. Citation-checked generation is available for fixed public questions, and answer correctness, claim support, and abstention have been graded on the same set.

## Architecture

The FTI pattern is mapped to this retrieval system as follows:

| Pipeline | Input | Output | Roadmap |
|---|---|---|---|
| Ingestion | Official public documents and source manifest | Parsed articles and sections with provenance | Phases 1–2 |
| Indexing | Validated chunks | Multilingual embeddings and vector index | Phases 3–4 |
| Serving | Question, index, and cited passages | Grounded answer with resolution and article citations | Phases 5–6 |

The implemented parsing and indexing stack uses PyMuPDF, sentence-transformers, and Chroma. Cited generation uses Claude Haiku 5.5 through the Anthropic API. A FastAPI service and a Streamlit chat expose reviewed-question answers and local passage search.

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
| 7 | Final README results, including answer evaluation, and v1.0.0 release |

Each phase is a [GitHub milestone](https://github.com/RafaGM1108/colombia-health-regulations-rag/milestones). Work moves through Backlog, Ready, In Progress, In Review, and Done, with at most two items In Progress. Each issue is developed on a branch and reviewed in a pull request before merging.

## Development

Requires Python 3.12, [uv](https://docs.astral.sh/uv/), and `make`.

```bash
git clone https://github.com/RafaGM1108/colombia-health-regulations-rag.git
cd colombia-health-regulations-rag
make install
make lint typecheck test
```

The local API is available with `make api` and the chat UI with `make app`; both need the local index described below. A real Anthropic key belongs only in a local `.env` file, never in Git.

CI checks lockfile consistency, formatting, lint, types, tests with coverage, documentation, static security issues, and committed-file secrets. The same core checks run locally with `make lint typecheck test`.

`make corpus-check` downloads the current official PDFs and compares them with the manifest. It requires `curl` and network access. A changed PDF is saved as an ignored local candidate for manual review; [the refresh procedure](docs/data.md) explains how to record a new version without replacing the old one.

After obtaining the four checksum-matched PDFs, build the local vectors and index, then reproduce the retrieval comparison:

```bash
make embeddings
make index
make evaluate
```

The [data-layer instructions](data/README.md) cover build IDs and local outputs. The [parsing procedure](docs/data.md#article-parsing) reads checksum-verified PDFs and returns numbered articles or annex sections with resolution, section, and page metadata. Only reviewed annex rows and excerpts enter the index; unreviewed text remains excluded.

With the article-aware index built and `ANTHROPIC_API_KEY` set in local `.env`, run a fixed public question by ID:

```bash
uv run --frozen --group embeddings python -m colombia_health_rag.serving.generation q01
```

The command accepts IDs from the public evaluation set, not patient details, and prints a refusal if a response lacks a verified source quote. `make api` serves the same operations over HTTP and `make app` opens the Spanish chat UI; the endpoints and input rules are in the [input contract](docs/interface.md). See [Methodology](docs/methodology.md) for the citation checks and their limits.

## Repository structure

```text
conf/base.yaml                 Paths and application name
data/                          Local raw, parsed, chunk, embedding, index, evaluation, reporting layers
docs/                          Source policy and methodology
src/colombia_health_rag/       Ingestion, indexing, serving, API, UI, and shared utilities
tests/                         Parsing, indexing, evaluation, API, and UI checks
```

The [data policy](data/README.md) explains the layer boundaries. [Methodology](docs/methodology.md) describes the retrieval evaluation and citation contract.

## Results

Retrieval-only results on 22 answerable questions from the fixed set of original official documents:

| Chunking | Hit@1 | Hit@5 | MRR |
|---|---:|---:|---:|
| Article-aware | 0.454545 | 0.863636 | 0.629270 |
| Fixed-window | 0.590909 | 0.772727 | 0.674260 |

The [reproducible report](data/07_reporting/retrieval-v1.json) includes hit@3, hit@10, input fingerprints, and per-question ranks. Four questions outside the corpus are excluded from these retrieval metrics.

Cited answers on the same 26 questions, graded per the [answer rubric](docs/methodology.md#answer-evaluation):

| Generation model | Correct of 22 answerable | Correct of answered | Claims supported | Abstained without evidence |
|---|---:|---:|---:|---:|
| Claude Sonnet 4.6 (baseline) | 16 | 16/17 | 24/26 | 6/7 |
| Claude Haiku 5.5 (current) | 18 | 18/18 | 24/24 | 7/7 |

Grades were assigned by Claude Opus 5.5 with a published rationale per question; see the [grades and metrics](data/07_reporting/answer-quality-v1.json) and the evaluation limits in [Methodology](docs/methodology.md#limits).

### Reproducing the results

Every figure above is read from a tracked file in `data/07_reporting/`, and a test checks that the README tables match those files.

| Step | Command | Output | Deterministic |
|---|---|---|---|
| Official sources | `make corpus-check` | Four PDFs in `data/01_raw/`, verified by SHA-256 | Yes, while the published PDFs are unchanged |
| Embeddings and index | `make embeddings`, `make index` | Local build named by the build ID in `retrieval-v1.json` | Yes on CPU with the locked dependencies; use `--build-id` when several builds exist |
| Retrieval metrics | `make evaluate` | `retrieval-v1.json` | Yes |
| Cited answers | `make evaluate-answers` | `answers-<model>.json` | No: needs `ANTHROPIC_API_KEY`, costs API usage, and model output can vary between runs |
| Answer metrics | `make score-answers` | `answer-quality-v1.json` from the committed grades | Yes |

A new answer run produces a new report, so its grades must be redone; `make score-answers` rejects grades whose report checksum no longer matches.

### Known limits

- The corpus holds four original, unconsolidated resolutions. Answers describe those texts, not the law currently in force.
- The evaluation set is small and hand-written: 22 answerable and 4 out-of-corpus questions. Each generation model was run once.
- Retrieval misses the gold location for 3 of 22 questions within the five passages sent to the model; those questions can only be refused.
- Annex and manual text enters the index only after manual OCR review, so most of the Resolution 3100 manual is not searchable.
- Answers were graded by a language model from the same family as the systems under test; per-question rationales are published for review.
- Generation is limited to the reviewed public questions; free-form text is searched locally but not answered.

The [v1.0.0 release checklist](docs/release.md) lists the checks to run before tagging.

## Author

Rafael E. Garcia · [GitHub](https://github.com/RafaGM1108) · [LinkedIn](https://www.linkedin.com/in/rafaelgarcia11)

Code is licensed under [MIT](LICENSE). Source documents retain their original terms and remain attributable to their publishers.
