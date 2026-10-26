"""Check observed official PDF layouts without committing the source files."""

import hashlib
from pathlib import Path

import pymupdf
import pytest

from colombia_health_rag.ingestion.articles import ArticleParseError, parse_resolution
from colombia_health_rag.ingestion.manifest import SourceRecord, load_manifest


def _fixture(tmp_path: Path, pages: list[list[tuple[int, str]]]) -> SourceRecord:
    path = tmp_path / "data/01_raw/layout.pdf"
    path.parent.mkdir(parents=True)
    pdf = pymupdf.open()  # type: ignore[no-untyped-call]
    for lines in pages:
        page = pdf.new_page()
        for top, text in lines:
            page.insert_text((72, top), text)
    pdf.save(path)  # type: ignore[no-untyped-call]
    pdf.close()  # type: ignore[no-untyped-call]
    return SourceRecord.model_validate(
        {
            "source_url": "https://www.minsalud.gov.co/layout.pdf",
            "authority": "Ministerio de Salud y Protección Social",
            "title": "Resolución 99 de 2024 — Diseño sintético",
            "publication_date": "2024-01-01",
            "version": "Original",
            "retrieved_at": "2024-01-02T00:00:00Z",
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "reuse_terms": "Test fixture",
            "raw_path": "data/01_raw/layout.pdf",
            "public_document_confirmed": True,
            "personal_data_scope": "official_attribution_only",
        }
    )


def test_observed_heading_variants_page_breaks_and_running_margins(tmp_path: Path) -> None:
    source = _fixture(
        tmp_path,
        [
            [(40, "RUNNING_HEADER_SENTINEL"), (140, "ARTICULO 5. Cita en el preambulo.")],
            [
                (40, "RUNNING_HEADER_SENTINEL"),
                (130, "RESUELVE:"),
                (155, "TITULO 1"),
                (180, "CAPITULO I"),
                (205, "ARTICULO 1. Objeto. Primera linea."),
                (230, "Segunda linea del articulo."),
                (255, "ARTICULO 2 Contenido sin punto."),
                (280, "ARTICULO '3. Reporte con marca OCR."),
                (800, "RUNNING_FOOTER_SENTINEL"),
            ],
            [
                (130, "Continuacion del tercer articulo."),
                (155, "PUBUQUESE y CUMPLASE"),
                (180, "APRO8O: SIGNATURE_SENTINEL"),
                (205, "ANEXO TECNICO"),
            ],
        ],
    )

    parsed = parse_resolution(source, tmp_path)
    texts = "\n".join(article.text for article in parsed.articles)

    assert [article.number for article in parsed.articles] == [1, 2, 3]
    assert parsed.articles[0].section_path == ("Título 1", "Capítulo I")
    assert (parsed.articles[-1].page_start, parsed.articles[-1].page_end) == (2, 3)
    assert "Segunda linea del articulo." in parsed.articles[0].text
    assert "Continuacion del tercer articulo." in parsed.articles[-1].text
    assert all(
        marker not in texts
        for marker in (
            "RUNNING_HEADER_SENTINEL",
            "RUNNING_FOOTER_SENTINEL",
            "preambulo",
            "SIGNATURE_SENTINEL",
            "ANEXO TECNICO",
        )
    )


def test_pdf_without_extractable_text_requires_manual_review(tmp_path: Path) -> None:
    source = _fixture(tmp_path, [[]])

    with pytest.raises(ArticleParseError, match="could not be found"):
        parse_resolution(source, tmp_path)


def test_unreadable_pdf_requires_manual_review(tmp_path: Path) -> None:
    source = _fixture(tmp_path, [[]])
    path = tmp_path / source.raw_path
    path.write_bytes(b"invalid-pdf")
    source = source.model_copy(update={"sha256": hashlib.sha256(path.read_bytes()).hexdigest()})

    with pytest.raises(ArticleParseError, match="not a readable PDF"):
        parse_resolution(source, tmp_path)


def test_reviewed_local_official_layouts_when_available() -> None:
    root = Path(__file__).resolve().parents[2]
    sources = load_manifest(root / "data/manifest.json")
    if not all((root / source.raw_path).is_file() for source in sources):
        pytest.skip("Original official PDFs are intentionally excluded from Git")

    expected = {
        "Resolución 740 de 2024": (53, 3, 29),
        "Resolución 1816 de 2026": (60, 4, 35),
        "Resolución 3100 de 2019": (27, 2, 13),
        "Resolución 2080 de 2026": (2, 7, 8),
    }
    for source in sources:
        parsed = parse_resolution(source, root)
        assert (
            len(parsed.articles),
            parsed.articles[0].page_start,
            parsed.articles[-1].page_end,
        ) == expected[parsed.resolution]
        assert all(article.sha256 == source.sha256 for article in parsed.articles)
