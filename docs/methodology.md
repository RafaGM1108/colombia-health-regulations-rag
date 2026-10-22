# Methodology

## Pipeline map

| FTI role | This project | Main output |
|---|---|---|
| Feature | Ingestion and article-aware chunking | Passage with source and article metadata |
| Training | Multilingual embedding and index build | Versioned vector index |
| Inference | Retrieval and cited generation | Answer grounded in retrieved passages |

Raw files are immutable. Parsing preserves resolution and article boundaries when present. Every indexed chunk retains its document URL, title, version, article or section identifier, and page reference so that answers can cite evidence precisely.

## Evaluation plan

Phase 4 will use a hand-written Q&A set with expected source and article identifiers. Retrieval will be scored with hit rate@k and mean reciprocal rank (MRR). Article-aware chunks will be compared with at least one baseline chunking strategy on the same questions.

Phase 5 will evaluate whether each generated claim is supported by cited passages, whether the answer addresses the question, and whether the system abstains when the corpus lacks evidence. Metrics and examples will be published only after an actual run. No clinical or legal decision should be based solely on a generated answer.
