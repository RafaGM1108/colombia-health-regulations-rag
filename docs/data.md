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
