"""Corpus snapshots must be reproducible and immutable."""

import hashlib
import json
import subprocess
from datetime import date
from pathlib import Path

import pytest

from colombia_health_rag.ingestion.refresh import (
    RefreshError,
    check_sources,
    fetch_pdf,
    record_candidate,
)

SOURCE_URL = "https://www.minsalud.gov.co/normativa/resolucion.pdf"
ORIGINAL = b"%PDF-1.6\noriginal official bytes\n%%EOF"
CHANGED = b"%PDF-1.6\ncorrected official bytes\n%%EOF"


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _manifest(tmp_path: Path, *, local: bool = True) -> Path:
    raw = tmp_path / "data/01_raw/resolution.pdf"
    raw.parent.mkdir(parents=True)
    if local:
        raw.write_bytes(ORIGINAL)
    path = tmp_path / "data/manifest.json"
    path.write_text(
        json.dumps(
            [
                {
                    "source_url": SOURCE_URL,
                    "authority": "Ministerio de Salud y Protección Social",
                    "title": "Resolución de prueba",
                    "publication_date": "2024-01-15",
                    "version": "Original signed PDF",
                    "retrieved_at": "2026-10-25T10:00:00Z",
                    "sha256": _digest(ORIGINAL),
                    "reuse_terms": "Public source; no PDF redistribution",
                    "raw_path": "data/01_raw/resolution.pdf",
                    "public_document_confirmed": True,
                    "personal_data_scope": "official_attribution_only",
                }
            ]
        ),
        encoding="utf-8",
    )
    return path


def test_unchanged_source_restores_only_matching_missing_snapshot(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path, local=False)
    before = manifest.read_bytes()
    results, missing = check_sources(manifest, lambda _url: ORIGINAL)
    assert [result.status for result in results] == ["unchanged"]
    assert missing == []
    assert (tmp_path / "data/01_raw/resolution.pdf").read_bytes() == ORIGINAL
    assert manifest.read_bytes() == before


def test_changed_source_is_quarantined_until_reviewed(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    before = manifest.read_bytes()
    results, missing = check_sources(manifest, lambda _url: CHANGED)
    candidate = results[0].candidate_path
    assert results[0].status == "changed"
    assert candidate is not None
    assert candidate.read_bytes() == CHANGED
    download_record = candidate.with_suffix(".json").read_bytes()
    assert json.loads(download_record)["sha256"] == _digest(CHANGED)
    check_sources(manifest, lambda _url: CHANGED)
    assert candidate.with_suffix(".json").read_bytes() == download_record
    assert (tmp_path / "data/01_raw/resolution.pdf").read_bytes() == ORIGINAL
    assert manifest.read_bytes() == before
    assert missing == []

    with pytest.raises(RefreshError, match="confirmations"):
        record_candidate(
            manifest,
            candidate,
            title="Corrected resolution",
            publication_date=date(2026, 10, 25),
            version="Corrected official PDF",
            reuse_terms="Public source; no PDF redistribution",
            public_document_reviewed=True,
            personal_data_reviewed=False,
        )
    assert manifest.read_bytes() == before

    source = record_candidate(
        manifest,
        candidate,
        title="Corrected resolution",
        publication_date=date(2026, 10, 25),
        version="Corrected official PDF",
        reuse_terms="Public source; no PDF redistribution",
        public_document_reviewed=True,
        personal_data_reviewed=True,
    )
    assert source.sha256 == _digest(CHANGED)
    assert (tmp_path / source.raw_path).read_bytes() == CHANGED
    assert (tmp_path / "data/01_raw/resolution.pdf").read_bytes() == ORIGINAL
    assert len(json.loads(manifest.read_text())) == 2
    current, missing = check_sources(manifest, lambda _url: CHANGED)
    assert [result.status for result in current] == ["unchanged"]
    assert missing == []
    with pytest.raises(RefreshError, match="already recorded"):
        record_candidate(
            manifest,
            candidate,
            title="Corrected resolution",
            publication_date=date(2026, 10, 25),
            version="Corrected official PDF",
            reuse_terms="Public source; no PDF redistribution",
            public_document_reviewed=True,
            personal_data_reviewed=True,
        )


def test_local_checksum_mismatch_stops_before_download(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    raw = tmp_path / "data/01_raw/resolution.pdf"
    raw.write_bytes(CHANGED)
    called = False

    def fetch(_url: str) -> bytes:
        nonlocal called
        called = True
        return ORIGINAL

    with pytest.raises(RefreshError, match="Local snapshot differs"):
        check_sources(manifest, fetch)
    assert not called
    assert raw.read_bytes() == CHANGED


def test_non_pdf_response_is_not_saved(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    with pytest.raises(RefreshError, match="not a PDF"):
        check_sources(manifest, lambda _url: b"<html>not a source PDF</html>")
    assert not (tmp_path / "data/01_raw/candidates").exists()


def test_download_accepts_only_pdf_bytes_without_following_redirects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    downloaded = ORIGINAL
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, downloaded)

    monkeypatch.setattr(
        "colombia_health_rag.ingestion.refresh.shutil.which", lambda _name: "/usr/bin/curl"
    )
    monkeypatch.setattr("colombia_health_rag.ingestion.refresh.subprocess.run", fake_run)
    assert fetch_pdf(SOURCE_URL) == ORIGINAL
    assert commands[0][-1] == SOURCE_URL
    assert "--location" not in commands[0]
    assert commands[0][commands[0].index("--proto") + 1] == "=https"

    downloaded = b"<html>redirect page</html>"
    with pytest.raises(RefreshError, match="not a PDF"):
        fetch_pdf(SOURCE_URL)
