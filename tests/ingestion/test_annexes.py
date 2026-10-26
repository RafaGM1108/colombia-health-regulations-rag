"""Exercise both reviewed annex layouts with small non-personal PDFs."""

import hashlib
import json
from pathlib import Path
from typing import cast

import pymupdf
import pytest

from colombia_health_rag.ingestion.annexes import (
    AnnexParseError,
    parse_annex,
    parse_reviewed_table_rows,
)
from colombia_health_rag.ingestion.manifest import SourceRecord, load_manifest


def _source(tmp_path: Path, number: int, pages: list[list[tuple[int, int, str]]]) -> SourceRecord:
    raw = tmp_path / "data/01_raw/annex.pdf"
    raw.parent.mkdir(parents=True)
    pdf = pymupdf.open()  # type: ignore[no-untyped-call]
    for entries in pages:
        page = pdf.new_page(width=614, height=945)
        for x, y, text in entries:
            page.insert_text((x, y), text)
    pdf.save(raw)  # type: ignore[no-untyped-call]
    pdf.close()  # type: ignore[no-untyped-call]
    year = 2019 if number == 3100 else 2024
    return SourceRecord.model_validate(
        {
            "source_url": "https://www.minsalud.gov.co/annex.pdf",
            "authority": "Ministerio de Salud y Protección Social",
            "title": f"Resolución {number} de {year} — Diseño sintético",
            "publication_date": "2024-01-01",
            "version": "Original",
            "retrieved_at": "2024-01-02T00:00:00Z",
            "sha256": hashlib.sha256(raw.read_bytes()).hexdigest(),
            "reuse_terms": "Test fixture",
            "raw_path": "data/01_raw/annex.pdf",
            "public_document_confirmed": True,
            "personal_data_scope": "official_attribution_only",
        }
    )


def _main_page() -> list[tuple[int, int, str]]:
    return [
        (72, 130, "RESUELVE"),
        (72, 160, "ARTICULO 1. Objeto."),
        (72, 200, "PUBUQUESE Y CUMPLASE"),
        (72, 230, "FIRMA: SIGNATURE_SENTINEL"),
    ]


def test_reconstructs_table_columns_as_review_required_page_records(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        740,
        [
            _main_page(),
            [
                (72, 160, "ANEXO TECNICO"),
                (90, 250, "TEC A"),
                (180, 250, "MOTIVO A"),
                (320, 250, "G379"),
                (380, 250, "DIAGNOSTICO A"),
                (90, 300, "TEC B"),
                (180, 300, "MOTIVO B"),
                (320, 300, "G518"),
                (380, 300, "DIAGNOSTICO B"),
            ],
        ],
    )

    result = parse_annex(source, tmp_path)
    page = result.sections[0]

    assert len(result.sections) == 1
    assert page.row_count == 2
    assert page.page_start == page.page_end == 2
    assert page.review_required
    assert page.section_path == ("Anexo técnico",)
    assert page.source_title == source.title
    assert page.sha256 == source.sha256
    assert page.citation == "Resolución 740 de 2024, anexo técnico, p. 2"
    assert "Tecnología: TEC A; motivo: MOTIVO A; CIE-10: G379" in page.text
    assert "Tecnología: TEC B; motivo: MOTIVO B; CIE-10: G518" in page.text
    assert "SIGNATURE_SENTINEL" not in page.text
    assert result.warnings


def test_finds_manual_body_after_contents_and_preserves_numbered_sections(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        3100,
        [
            _main_page(),
            [
                (72, 160, "ANEXO TECNICO"),
                (72, 190, "Tabla de contenido"),
                (72, 220, "INTRODUCCION .......................... 3"),
            ],
            [
                (72, 160, "INTRODUCCION"),
                (72, 190, "Texto introductorio."),
                (72, 220, "1. ESTRUCTURA DE SERVICIOS"),
                (72, 250, "Texto de la seccion uno."),
            ],
            [
                (85, 160, "1.1."),
                (125, 160, "GRUPO"),
                (72, 190, "Texto del grupo."),
                (72, 220, "1.2. SERVICIO"),
                (72, 250, "Texto del servicio."),
            ],
        ],
    )

    result = parse_annex(source, tmp_path)

    assert [section.section_id for section in result.sections] == [
        "Introducción",
        "1",
        "1.1",
        "1.2",
    ]
    assert result.sections[2].section_path == ("1", "1.1")
    assert result.sections[2].citation.endswith("sección 1.1, p. 4")
    assert all(section.review_required for section in result.sections)
    assert "SIGNATURE_SENTINEL" not in repr(result)
    assert result.warnings == (
        "OCR text and heading boundaries require comparison with the official PDF",
    )


def test_flags_missing_manual_heading_for_review(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        3100,
        [
            _main_page(),
            [(72, 160, "ANEXO TECNICO")],
            [
                (72, 160, "INTRODUCCION"),
                (72, 190, "1. ESTRUCTURA DE SERVICIOS"),
                (72, 220, "1.2. SEGUNDO GRUPO"),
            ],
        ],
    )

    result = parse_annex(source, tmp_path)

    assert "Previous heading missing before section 1.2" in result.warnings


def test_rejects_annex_without_an_identifiable_heading(tmp_path: Path) -> None:
    source = _source(tmp_path, 740, [_main_page(), [(72, 160, "TABLA SIN TITULO")]])

    with pytest.raises(AnnexParseError, match="Annex heading was not found"):
        parse_annex(source, tmp_path)


def test_rejects_signing_marker_inside_annex_table(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        740,
        [
            _main_page(),
            [
                (72, 160, "ANEXO TECNICO"),
                (90, 250, "TEC A"),
                (180, 250, "MOTIVO A"),
                (320, 250, "G379"),
                (380, 250, "DIAGNOSTICO A"),
                (72, 400, "APROBO: OFFICIAL_SENTINEL"),
            ],
        ],
    )

    with pytest.raises(AnnexParseError, match="Possible signing details") as error:
        parse_annex(source, tmp_path)
    assert "OFFICIAL_SENTINEL" not in str(error.value)


def test_rejects_manual_contents_without_body_boundary(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        3100,
        [
            _main_page(),
            [(72, 160, "ANEXO TECNICO"), (72, 190, "INTRODUCCION ......... 3")],
        ],
    )

    with pytest.raises(AnnexParseError, match="Manual body boundary"):
        parse_annex(source, tmp_path)


def test_reviewed_local_annex_layouts_when_available() -> None:
    root = Path(__file__).resolve().parents[2]
    sources = [
        source
        for source in load_manifest(root / "data/manifest.json")
        if "resolution-740" in source.raw_path or "resolution-3100" in source.raw_path
    ]
    if not all((root / source.raw_path).is_file() for source in sources):
        pytest.skip("Original official PDFs are intentionally excluded from Git")

    results = {
        result.resolution: result for source in sources if (result := parse_annex(source, root))
    }
    table = results["Resolución 740 de 2024"]
    manual = results["Resolución 3100 de 2019"]

    assert len(table.sections) == 8
    assert sum(section.row_count or 0 for section in table.sections) == 212
    assert any("CIE cells" in warning for warning in table.warnings)
    assert (table.sections[0].page_start, table.sections[-1].page_end) == (30, 37)
    assert len(manual.sections) == 94
    assert manual.sections[0].section_id == "Introducción"
    assert manual.sections[-1].section_id == "11.6.4"
    assert (manual.sections[0].page_start, manual.sections[-1].page_end) == (18, 230)
    assert all(
        section.review_required for result in results.values() for section in result.sections
    )


def test_only_verified_review_rows_are_indexable(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        740,
        [
            _main_page(),
            [
                (72, 160, "ANEXO TECNICO"),
                (90, 250, "TEC A"),
                (180, 250, "MOTIVO A"),
                (320, 250, "0379"),
                (380, 250, "DIAGNOSTICO A"),
                (90, 300, "TEC B"),
                (180, 300, "MOTIVO B"),
                (320, 300, "G518"),
                (380, 300, "DIAGNOSTICO B"),
            ],
        ],
    )
    review = {
        "source_sha256": source.sha256,
        "source_pages": [2],
        "page_row_counts": [2],
        "common_rows": [
            {"code": "G379", "diagnosis": "DIAGNOSTICO REVISADO A", "verified": True},
            {"code": "G518", "diagnosis": "DIAGNOSTICO B", "verified": False},
        ],
        "common_technologies": ["TEC REVISADA"],
        "common_reason": "MOTIVO REVISADO",
        "additional_rows": [],
    }
    review_path = tmp_path / "review.json"
    review_path.write_text(json.dumps(review))

    provisional = parse_annex(source, tmp_path)
    result = parse_reviewed_table_rows(source, tmp_path, review_path)

    assert all(section.review_required for section in provisional.sections)
    assert len(result.sections) == 1
    assert not result.sections[0].review_required
    assert result.sections[0].citation == "Resolución 740 de 2024, anexo técnico, fila 1, p. 2"
    assert result.sections[0].text == (
        "Tecnología: TEC REVISADA; motivo: MOTIVO REVISADO; "
        "CIE-10: G379; diagnóstico: DIAGNOSTICO REVISADO A"
    )
    assert "TEC B" not in repr(result)
    assert result.warnings == ("1 unverified table rows excluded",)

    review["source_sha256"] = "0" * 64
    review_path.write_text(json.dumps(review))
    with pytest.raises(AnnexParseError, match="source checksum"):
        parse_reviewed_table_rows(source, tmp_path, review_path)

    review["source_sha256"] = source.sha256
    review["page_row_counts"] = [1]
    review_path.write_text(json.dumps(review))
    with pytest.raises(AnnexParseError, match="row layout"):
        parse_reviewed_table_rows(source, tmp_path, review_path)

    review["page_row_counts"] = [2]
    cast(list[dict[str, object]], review["common_rows"])[0]["code"] = "G999"
    review_path.write_text(json.dumps(review))
    with pytest.raises(AnnexParseError, match="failed validation"):
        parse_reviewed_table_rows(source, tmp_path, review_path)


def test_reviewed_local_table_rows_when_available() -> None:
    root = Path(__file__).resolve().parents[2]
    source = next(
        source
        for source in load_manifest(root / "data/manifest.json")
        if "resolution-740" in source.raw_path
    )
    if not (root / source.raw_path).is_file():
        pytest.skip("Original official PDF is intentionally excluded from Git")

    result = parse_reviewed_table_rows(source, root)

    assert len(result.sections) == 212
    assert all(not row.review_required for row in result.sections)
    assert [row.page_start for row in result.sections[:29]] == [30] * 28 + [31]
    assert [row.text.split("CIE-10: ", 1)[1].split(";", 1)[0] for row in result.sections[:3]] == [
        "G379",
        "G518",
        "G519",
    ]
    assert result.sections[198].text.startswith("Tecnología: DIAZEPAM")
    assert result.sections[-1].citation.endswith("fila 10, p. 37")
    assert not result.warnings
