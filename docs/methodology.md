# Methodology

## Pipeline map

| FTI role | This project | Main output |
|---|---|---|
| Feature | Ingestion and article-aware chunking | Passage with source and article metadata |
| Training | Multilingual embedding and index build | Versioned vector index |
| Inference | Retrieval and cited generation | Answer grounded in retrieved passages |

Raw files are immutable. Parsing preserves resolution and article boundaries when present. Every indexed chunk retains its document URL, title, version, article or section identifier, and page reference so that answers can cite evidence precisely.

## Passage embeddings

`make embeddings` uses the [multilingual E5 small model](https://huggingface.co/intfloat/multilingual-e5-small) at revision `614241f622f53c4eeff9890bdc4f31cfecc418b3`. The model card lists a 512-token limit and 384-dimensional vectors and requires `passage: ` and `query: ` prefixes for retrieval. The build uses the passage prefix, counts tokens with the pinned model tokenizer, splits long articles at word boundaries, and L2-normalizes vectors. It runs on CPU; the optional `embeddings` dependency group uses CPU-only PyTorch on Linux. The dependency lock records library versions.

Inputs come only from checksum-matched manifest documents: numbered main-resolution articles, 212 reviewed rows of the Resolution 740 annex, and 19 reviewed excerpts of the Resolution 3100 manual. Provisional annex text is rejected. Each passage keeps the source checksum, URL, title, version, resolution, article or section number, page span, and part number. Normalization collapses whitespace and applies Unicode NFC without rewriting source words. A SHA-256 identity covers each passage and its source location.

The local `03_chunks` snapshot and `04_embeddings/<build-id>` batches are ignored by Git. Batch files are written atomically; a resumed run validates existing input fingerprints, passage metadata, and vector shape before skipping them. The build identifier covers the passage set, model revision, batch size, vector dimension, and installed embedding-library versions. CPU inference uses deterministic operations, although floating-point values can vary slightly across different hardware or library builds. These embeddings are a historical-source snapshot; legal effect and later amendments still require separate review.

## Vector index

`make index` builds a persistent [Chroma](https://docs.trychroma.com/docs/run-chroma/cloud-client) collection from the already computed vectors. Before indexing, it checks the raw source checksums and compares passage provenance with the official manifest. The index manifest records the embedding build ID, hashes of the build manifest and batches, model revision, passage count, indexed passage IDs, and Chroma version. The local collection stores text plus resolution, article or section, exact citation, source URL, title, date, version, checksum, and page span. It uses cosine distance and disables telemetry. Repeating an unchanged build verifies the stored IDs; changed batches require an explicit rebuild. `search_index` accepts a normalized vector from the pinned model and supports resolution, article, section, and kind filters. Query text must be prefixed with `query: ` before embedding, as described above.

## Evaluation plan

Phase 4 will use a hand-written Q&A set with expected source and article identifiers. Retrieval will be scored with hit rate@k and mean reciprocal rank (MRR). Article-aware chunks will be compared with at least one baseline chunking strategy on the same questions.

Phase 5 will evaluate whether each generated claim is supported by cited passages, whether the answer addresses the question, and whether the system abstains when the corpus lacks evidence. Metrics and examples will be published only after an actual run. No clinical or legal decision should be based solely on a generated answer.
