"""Official-source manifest validation checks."""

import json
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from colombia_health_rag.ingestion.manifest import SourceRecord, load_manifest


def record() -> dict[str, object]:
    return {
        "source_url": "https://www.minsalud.gov.co/normativa/resolucion.pdf",
        "authority": "Ministerio de Salud y Protección Social",
        "title": "Resolución de prueba",
        "publication_date": "2024-01-15",
        "version": "Publicación original",
        "retrieved_at": "2026-10-24T12:00:00Z",
        "sha256": "a" * 64,
        "reuse_terms": "Acceso público; verificar condiciones del portal",
        "raw_path": "data/01_raw/resolucion.pdf",
        "public_document_confirmed": True,
        "personal_data_excluded": True,
    }


def test_valid_official_record_and_manifest(tmp_path: Path) -> None:
    metadata = record()
    source = SourceRecord.model_validate(metadata)
    assert source.publication_date == date(2024, 1, 15)
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps([metadata]), encoding="utf-8")
    assert load_manifest(path) == [source]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_url", "https://minsalud.gov.co.evil.example/resolucion.pdf"),
        ("source_url", "http://minsalud.gov.co/resolucion.pdf"),
        ("sha256", "not-a-checksum"),
        ("retrieved_at", "2026-10-24T12:00:00"),
        ("raw_path", "data/01_raw/../private.pdf"),
        ("personal_data_excluded", False),
    ],
)
def test_rejects_untrusted_or_incomplete_metadata(field: str, value: object) -> None:
    metadata = record()
    metadata[field] = value
    with pytest.raises(ValidationError):
        SourceRecord.model_validate(metadata)


def test_required_fields_and_unknown_fields_are_rejected() -> None:
    metadata = record()
    del metadata["reuse_terms"]
    metadata["unreviewed_field"] = "value"
    with pytest.raises(ValidationError) as error:
        SourceRecord.model_validate(metadata)
    assert "reuse_terms" in str(error.value)
    assert "unreviewed_field" in str(error.value)
