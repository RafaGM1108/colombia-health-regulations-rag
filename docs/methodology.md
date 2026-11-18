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

## Cited generation

The local generation command accepts only IDs from the fixed public question set. It verifies the article-aware embedding build and index against the original official PDFs, embeds the selected question with the same pinned E5 model, and retrieves up to five passages. A local `.env` may supply `ANTHROPIC_API_KEY`; it is ignored by Git. The request uses the [Anthropic Python SDK](https://platform.claude.com/docs/en/api/sdks/python) and the pinned `claude-haiku-5-5` model ID at `high` effort with a [JSON output schema](https://platform.claude.com/docs/en/build-with-claude/structured-outputs). No private documents or patient details are permitted in the corpus or command input.

Each proposed claim must name a retrieved evidence ID and include a continuous quotation from that passage. The code verifies the quotation against the normalized passage and renders the citation from index metadata: resolution, article or reviewed annex location, official PDF URL, page, and source version. It refuses when retrieval returns no passages, the response abstains, an evidence ID is unknown, a quotation is absent, or the structured output is invalid. Each refusal records one reason (`no_evidence`, `abstained`, `unverified_citation`, `invalid_output`, or `model_refusal` when the model's safety classifier declines), so evaluation can separate a deliberate abstention from a failed check. `make evaluate-answers` runs every fixed question through this path and saves the retrieved citations, whether the gold location was among them, the raw model output, and the verified answer in `data/07_reporting/answers-<model>.json` for grading. The first run, before the switch to Claude Haiku 5.5, is kept as `answers-claude-sonnet-4-6.json` for comparison. API failures are surfaced as errors; they do not produce an uncited answer. The quoted-text check establishes traceability, but it cannot prove that a paraphrased claim is entailed by the quote. The initial PDFs are historical original versions, so the output must not be treated as current legal or medical guidance.

## Answer evaluation

`make evaluate-answers` sends each of the 26 fixed questions through the same retrieval and citation checks as the generation command, once per model, and saves the run in `data/07_reporting/answers-<model>.json`. Both runs below use the same index build, question set, system prompt, and output schema; only the generation model differs.

### Rubric

Each saved output is graded against its question's `expected_answer` and the text of the retrieved passages. Two judgments are manual:

- **Correctness** of an answered question: `correct` when it conveys the key facts of the expected answer without a wrong statement, `partial` when a key fact is missing, and `incorrect` when it does not answer the question or contradicts the source. Accurate extra context from the cited passages is allowed.
- **Claim support**: a claim is `supported` only when its own quotation states what the claim says. A claim that adds a detail absent from its quotation is `unsupported`, even when the detail appears elsewhere in the official text.

Two outcomes are derived from the report without judgment. A refusal is appropriate when the question is outside the corpus or the gold location was not among the five retrieved passages; a refusal with the gold location available is a missed answer. An answer cites the gold location when one of its claims carries a citation that matches the gold article or reviewed annex location.

Grades are stored in `data/07_reporting/grades-<model>.json`, one rationale per question, and are bound to the exact run by the report's SHA-256. `make score-answers` rejects grades that do not match their report or omit required labels, and writes the metrics to `data/07_reporting/answer-quality-v1.json`.

**Grader disclosure:** both runs were graded by Claude Opus 5.5 (`claude-opus-5-5`), reviewing each output against the gold answer and the passage text. The grader comes from the same model family as the systems it grades, which can bias the judgments; the per-question rationales are published so that each label can be checked.

### Results

| Metric | Claude Sonnet 4.6 | Claude Haiku 5.5 |
|---|---:|---:|
| Correct, of 22 answerable questions | 16 (72.7%) | 18 (81.8%) |
| Correct, of answered questions | 16/17 (94.1%) | 18/18 (100%) |
| Claims supported by their own quotation | 24/26 (92.3%) | 24/24 (100%) |
| Answers citing the gold location | 16/17 (94.1%) | 18/18 (100%) |
| Abstained when evidence was absent (4 out-of-corpus + 3 retrieval misses) | 6/7 | 7/7 |
| Refused although the gold location was retrieved | 3/19 | 1/19 |

Sonnet 4.6 lost three correct drafts to the citation check: two quotations joined fragments with `[...]`, and one silently corrected a spelling error in the official PDF. It also answered q07 from related articles after retrieval missed the gold article; the quotations were genuine, but the answer did not address the question. Haiku 5.5 copied every quotation exactly and abstained on all three retrieval misses, but refused q21 although the gold article ranked first. On this evidence the generation model was changed to Claude Haiku 5.5 at `high` effort.

### Limits

The set is small (22 answerable and 4 out-of-corpus questions) and each model was run once; generation is not deterministic, so a repeated run can differ. The four out-of-corpus questions are easy cases, and three of the seven abstention cases come from retrieval misses rather than designed hard negatives. Correctness is judged against short paraphrased gold answers, and the grader is a language model. No clinical or legal decision should be based solely on a generated answer.
