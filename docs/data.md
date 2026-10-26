# Corpus policy

The corpus is restricted to public documents from the Ministerio de Salud y Protección Social and other official authorities. A source is eligible only after its official URL, title, publication date, version, retrieval time, and SHA-256 checksum are recorded in the manifest. Original PDFs are downloaded unchanged for local provenance review and are ignored by Git; the repository links to the publisher's copy rather than redistributing the PDF.

Patient information, clinical notes, prescriptions, private messages, identifiers, and other private or person-specific material are prohibited. The **only exception** is the name, public role, and signature of officials appearing in a signing or approval block of an official public act. These details remain in the unchanged local original and on the publisher's site. They are not extracted into article text, chunks, embeddings, evaluation questions, prompts, logs, or answers. A document with any other identifiable person is ineligible until reviewed and excluded. The manifest value `personal_data_scope: "official_attribution_only"` records this manual screening decision; schema validation alone cannot verify document contents.

This narrow exception does not mean that the source files contain no personal data. Public availability does not remove the need to limit processing. The published source may display a handwritten signature; the project neither republishes signature images nor uses them for identification. Source and effective-date checks remain necessary before any legal interpretation.

## Initial source decisions

| Source | Published | Inclusion and version note |
|---|---|---|
| [Resolution 740 of 2024](https://www.minsalud.gov.co/sites/rid/Lists/BibliotecaDigital/RIDE/DE/DIJ/resolucion-0740-de-2024.pdf) | 2024-05-02 | MIPRES procedure; original signed PDF. Retained to track the transition in Resolution 1816 of 2026. |
| [Resolution 1816 of 2026](https://www.minsalud.gov.co/sites/rid/Lists/BibliotecaDigital/RIDE/DE/DIJ/resolucion-1816-de-2026.pdf) | 2026-09-07 | Updated MIPRES procedure; original signed PDF. Articles 59–60 provide a three-month transition and repeal rule. |
| [Resolution 3100 of 2019](https://www.minsalud.gov.co/sites/rid/Lists/BibliotecaDigital/RIDE/DE/DIJ/resolucion-3100-de-2019.pdf) | 2019-11-26 | Service authorization and home-care requirements; original signed PDF, not a consolidated text of later amendments. |
| [Resolution 2080 of 2026](https://www.minsalud.gov.co/sites/rid/Lists/BibliotecaDigital/RIDE/DE/DIJ/resolucion-2080-de-2026.pdf) | 2026-09-08 | Revokes Resolution 1732 of 2026; original signed PDF. Included to document why Resolution 3100 remains relevant. |

The dates above are Diario Oficial publication dates, distinct from issue dates. Extracted text from all four PDFs was scanned for email addresses, ID-like values, and phone-like values; none were found by those checks. Signing and approval sections contain public officials' attribution. This screening does not guarantee that every personal datum is detectable. The parsing stage must exclude attribution blocks and flag uncertain boundaries before indexing. The original PDF is authoritative for its text; the manifest identifies the exact file with SHA-256. These are original versions, so later changes and legal effect must be checked before serving answers.

The [data layer guide](https://github.com/RafaGM1108/colombia-health-regulations-rag/blob/main/data/README.md) describes local outputs and validation.

## Refresh and version checks

Run `make corpus-check` from the repository root with `curl` and network access. The command validates every local snapshot that exists, downloads each current official URL once, and compares its SHA-256 with the manifest. It restores a missing local file only when the live bytes match a recorded checksum. It does not follow redirects or overwrite a changed raw file. Exit code `0` means the latest recorded bytes are still current; `1` means a new or reverted version or a missing historical snapshot; `2` means a download, format, or integrity error.

If the official bytes are new, the command writes `data/01_raw/candidates/<sha256>.pdf` and a matching JSON download record. Both stay local and ignored by Git. Review the candidate against the official site: confirm its authority, exact title, publication date, version or correction status, reuse terms, and the narrow personal-data policy above. Do not copy metadata blindly from the older version. After that review, record it with:

```bash
uv run --frozen python -m colombia_health_rag.ingestion.refresh record \
  data/01_raw/candidates/<sha256>.pdf \
  --title "<official title>" \
  --publication-date YYYY-MM-DD \
  --version "<reviewed version description>" \
  --reuse-terms "<reviewed terms or unknown status>" \
  --public-document-reviewed --personal-data-reviewed
```

This copies the candidate to a new checksum-named raw path and appends a manifest entry. Existing snapshots stay unchanged. Commit only the manifest and related documentation after review; never commit the PDF or its signing details. A changed live URL cannot reconstruct an older PDF on a fresh clone if that older snapshot was not retained locally or made available through an official archive. Preserve local historical snapshots accordingly; a missing one is reported instead of silently substituted.

## Article parsing

`parse_resolution` in `colombia_health_rag.ingestion.articles` accepts a reviewed manifest record and the repository root. It verifies the local PDF checksum, then extracts numbered articles from the resolution text between `RESUELVE` and its closing formula. Each record carries the resolution and article number, section path when present, one-based page span, source URL, title, publication date, version, and checksum. A missing boundary, numbering gap, unreadable PDF, or changed local file raises `ArticleParseError` for manual review.

The parser reads the main resolution articles only. It excludes the preamble, signature and approval blocks after the closing formula, and annexes that follow the resolution. Some source PDFs contain important annex material, so an article count alone is not proof of complete regulatory coverage. The four reviewed local originals currently yield 53, 60, 27, and 2 main-resolution articles in manifest order. These counts are a layout check, not a legal completeness claim.

The extracted records are kept in memory; this stage does not save parsed text or build an index. Additional official-layout tests must be completed before export or indexing. Fixed page margins remove running headers in the reviewed layouts; a new layout requires review rather than assuming the same margins are safe.

The parser recognizes a closing formula on its own line, stops before all subsequent text and images, and rejects approval, drafting, signature, or signatory-role markers found earlier than that boundary. A missing or uncertain boundary raises an error without returning partial records or copying the suspect line into logs. The original PDF may still contain public officials' signing details under the narrow policy above; derived article records contain only text before the closing formula. These rules do not detect every possible personal name or OCR error, so a new source layout still requires manual review before export or indexing.

Tests use short synthetic PDFs based on the reviewed layouts: a preamble citation, headings with missing punctuation or an OCR mark, multiline articles, a page break, running margins, and a closing line followed by approval material. A local test also verifies article counts and page spans against the four unchanged original PDFs when they are present. CI skips that local-original check because the source PDFs are intentionally not committed; the synthetic cases and failure checks still run there.

## Annex sections

`parse_annex` in `colombia_health_rag.ingestion.annexes` accepts a reviewed manifest record and repository root. It first validates and parses the main resolution, then locates an annex heading after its closing formula. Only the reviewed layouts of Resolutions 740 of 2024 and 3100 of 2019 are supported. Every returned section carries its annex identifier, one-based page span, resolution citation, source URL, title, publication date, version, and SHA-256 checksum. A missing annex or manual-body boundary raises `AnnexParseError` without returning partial records.

The annex to Resolution 740 is a four-column raster table with an OCR text layer. The parser uses the CIE column as a row anchor and keeps each page as a separate fragment under `Anexo técnico`; the eight reviewed pages currently yield 212 provisional rows. In this local extraction, 117 CIE cells fail the expected code shape. OCR also merges words across columns. Every fragment therefore has `review_required=True`, and its rows must be compared with the official page before any indexing or legal interpretation.

The annex to Resolution 3100 is a long manual. The parser skips its contents pages, starts at the body introduction, and splits at numbered headings. The reviewed original currently yields 94 records ending at section `11.6.4`; parent and numbering gaps are reported as warnings. Its OCR text and section boundaries also have `review_required=True` pending page-level comparison with the original. Neither annex parser writes extracted text to disk, and an index builder must reject records still marked for review.


### Reviewed Resolution 740 table rows

The tracked `data/reviews/resolution-740-annex.json` records a visual, page-by-page review of the unchanged official PDF with SHA-256 `d8f627565539d0340d04e653ddcbc8aa11c9eb2de23a9b3aefbad818ad997281`. Pages 30–37 contain 28, 28, 29, 31, 28, 31, 27, and 10 rows. The table has three 66-row medication blocks followed by 14 additional rows. The review records the checked CIE-10 sequence, medication/reason text, diagnosis labels, and an explicit `verified` decision for each distinct row definition. Repeated rows inherit the same checked definition while retaining their own page and row citations. It corrects common OCR confusion between `0` and the initial code letter, as well as words assigned to the wrong column or adjacent row.

Call `parse_reviewed_table_rows` only with the matching manifest record and original local PDF. It first runs the provisional parser, then requires the exact source checksum, page sequence, row counts, and numeric part of every OCR code to match the review. It returns one record per verified row with `review_required=False`, a page-local row number, and source metadata. Rows marked `verified=false` are omitted; a mismatch or incomplete review raises `AnnexParseError`. The provisional `parse_annex` result remains flagged and must never be indexed. This review applies only to the recorded original PDF. A changed official file or table layout needs a separate visual review before indexing.

The reviewed text represents the table as printed in this historical source; it is not a statement that any listed technology is currently excluded or should be prescribed. In particular, the unusual or incomplete wording of some exclusion reasons is retained from the table rather than completed by inference. The raw OCR layer still contains errors and is not a source of indexable text.
