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

## Retrieval evaluation

Phase 4 uses the fixed [Spanish Q&A set](https://github.com/RafaGM1108/colombia-health-regulations-rag/blob/main/data/06_evaluation/questions.json): 22 answerable questions and four cases outside the corpus. Gold locations identify the exact official PDF version by SHA-256 plus article number or reviewed annex excerpt/row and page. Questions about older acts explicitly refer to their original text, because the source manifest contains original, unconsolidated PDFs. The short gold answers are paraphrases for evaluation, not current legal guidance. The loader rejects sources absent from the official manifest, and the scoring run verifies every gold location against reviewed passages.

Run `make evaluate` after downloading and verifying the four manifest PDFs. The command uses the pinned multilingual E5 model and the same reviewed records for both strategies. The article-aware strategy splits each article or reviewed annex record only when it exceeds 512 model tokens, without overlap. The fixed-window baseline splits each record into passages of at most 192 model tokens, overlapping by 24 words; it also stays within record boundaries to retain exact official citations. Both strategies use the same `query: ` and `passage: ` prefixes, L2-normalized vectors, and exact cosine ranking with passage ID as the tie breaker. The local embedding batches can be reused after their source and vector checks pass. Chroma's approximate index is not involved in this comparison, so the retrieval algorithm is identical for both splits.

For each answerable question, a hit requires the exact source PDF checksum and article number or reviewed annex excerpt/row location. Hit rate@1, @3, @5, and @10 is the fraction of questions with at least one matching passage in the first *k* positions; MRR is the mean inverse rank of the first match. The four questions outside the corpus are listed but excluded from both metrics: a similarity ranking alone does not establish whether the system should abstain. The committed [retrieval report](https://github.com/RafaGM1108/colombia-health-regulations-rag/blob/main/data/07_reporting/retrieval-v1.json) records input checksums, model revision, library versions, passage counts, aggregate metrics, and per-question first relevant ranks and top-five citations. Labels are at the source-location level, so a hit does not prove that the returned fragment contains the exact answer within a long article. The small, hand-written question set also limits generalization.

| Split | Passages | Hit@1 | Hit@3 | Hit@5 | Hit@10 | MRR |
|---|---:|---:|---:|---:|---:|---:|
| Article-aware | 416 | 0.454545 | 0.727273 | 0.863636 | 0.863636 | 0.629270 |
| Fixed-window | 617 | 0.590909 | 0.727273 | 0.772727 | 0.863636 | 0.674260 |

The baseline ranks the correct location first more often and has higher MRR; article-aware chunks have higher hit@5. Both reach the same hit@10 on this set. The comparison does not justify choosing one strategy for every question type, and its extra baseline passages affect ranking opportunity.

Phase 5 will evaluate whether each generated claim is supported by cited passages, whether the answer addresses the question, and whether the system abstains when the corpus lacks evidence. Metrics and examples will be published only after an actual run. No clinical or legal decision should be based solely on a generated answer.
