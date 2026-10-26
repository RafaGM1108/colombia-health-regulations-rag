import hashlib
from pathlib import Path

import pymupdf
import pytest

from colombia_health_rag.ingestion.articles import ArticleParseError, parse_resolution
from colombia_health_rag.ingestion.manifest import SourceRecord


def _source(tmp_path: Path, pages: list[list[str]]) -> SourceRecord:
    raw = tmp_path / "data/01_raw/example.pdf"
    raw.parent.mkdir(parents=True)
    pdf = pymupdf.open()  # type: ignore[no-untyped-call]
    for lines in pages:
        page = pdf.new_page()
        for index, line in enumerate(lines):
            page.insert_text((72, 130 + index * 25), line)
    pdf.save(raw)  # type: ignore[no-untyped-call]
    pdf.close()  # type: ignore[no-untyped-call]
    return SourceRecord.model_validate(
        {
            "source_url": "https://www.minsalud.gov.co/example.pdf",
            "authority": "Ministerio de Salud y Protección Social",
            "title": "Resolución 99 de 2024 — Texto de prueba",
            "publication_date": "2024-01-01",
            "version": "Original",
            "retrieved_at": "2024-01-02T00:00:00Z",
            "sha256": hashlib.sha256(raw.read_bytes()).hexdigest(),
            "reuse_terms": "Test fixture",
            "raw_path": "data/01_raw/example.pdf",
            "public_document_confirmed": True,
            "personal_data_scope": "official_attribution_only",
        }
    )


def test_parses_articles_sections_page_spans_and_citation_without_footer(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        [
            [
                "Articulo 99 de otra norma citado en el preambulo.",
                "RESUELVE:",
                "TITULO I",
                "CAPITULO I",
                "ARTICULO 1. Objeto. Primera parte.",
                "Continuacion del primer articulo.",
            ],
            [
                "Texto final del primer articulo.",
                "ARTICULO 2. Vigencia. Segunda parte.",
                "CUMPLASE.",
                "SIGNATURE_PRIVATE_SENTINEL",
            ],
        ],
    )

    result = parse_resolution(source, tmp_path)

    assert result.resolution == "Resolución 99 de 2024"
    assert result.sha256 == source.sha256
    assert [article.number for article in result.articles] == [1, 2]
    assert (result.articles[0].page_start, result.articles[0].page_end) == (1, 2)
    assert result.articles[0].section_path == ("Título I", "Capítulo I")
    assert result.articles[0].citation == "Resolución 99 de 2024, artículo 1"
    assert "Texto final del primer articulo." in result.articles[0].text
    assert "SIGNATURE_PRIVATE_SENTINEL" not in repr(result)
    assert "preambulo" not in repr(result)


def test_rejects_a_gap_in_article_numbers(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        [["RESUELVE", "ARTICULO 1. Objeto.", "ARTICULO 3. Vigencia.", "CUMPLASE"]],
    )

    with pytest.raises(ArticleParseError, match="Unexpected article number 3"):
        parse_resolution(source, tmp_path)


def test_rejects_missing_closing_boundary(tmp_path: Path) -> None:
    source = _source(tmp_path, [["RESUELVE", "ARTICULO 1. Objeto."]])

    with pytest.raises(ArticleParseError, match="closing formula"):
        parse_resolution(source, tmp_path)


def test_rejects_modified_local_pdf(tmp_path: Path) -> None:
    source = _source(tmp_path, [["RESUELVE", "ARTICULO 1. Objeto.", "CUMPLASE"]])
    (tmp_path / source.raw_path).write_bytes(b"modified")

    with pytest.raises(ArticleParseError, match="checksum"):
        parse_resolution(source, tmp_path)
