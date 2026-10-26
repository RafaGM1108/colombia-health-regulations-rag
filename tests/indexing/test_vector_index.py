"""Verify persistent retrieval and refuse mismatched official inputs."""

import hashlib
import json
from collections.abc import Iterable, Sequence
from pathlib import Path

import pytest

from colombia_health_rag.indexing.embeddings import (
    MODEL_DIMENSION,
    MODEL_ID,
    MODEL_REVISION,
    Passage,
    _sha256,
    build_embeddings,
)
from colombia_health_rag.indexing.vector_index import build_index, search_index


class FakeEncoder:
    """Return distinct normalized vectors without downloading model weights."""

    def encode(
        self,
        sentences: Sequence[str],
        *,
        batch_size: int,
        normalize_embeddings: bool,
        show_progress_bar: bool,
    ) -> Iterable[Iterable[float]]:
        for text in sentences:
            vector = [0.0] * MODEL_DIMENSION
            vector[0 if "primero" in text else 1] = 1.0
            yield vector


@pytest.fixture
def source_build(tmp_path: Path) -> tuple[Path, Path]:
    """Produce a minimal checksum-matched official snapshot and two article vectors."""
    raw_path = tmp_path / "data/01_raw/resolution.pdf"
    raw_path.parent.mkdir(parents=True)
    raw_path.write_bytes(b"official fixture")
    digest = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    source_url = "https://www.minsalud.gov.co/test/resolution.pdf"
    title = "Resolución 1 de 2024"
    version = "Original"
    manifest = [
        {
            "source_url": source_url,
            "authority": "Ministerio de Salud y Protección Social",
            "title": title,
            "publication_date": "2024-01-01",
            "version": version,
            "retrieved_at": "2024-01-02T00:00:00Z",
            "sha256": digest,
            "reuse_terms": "Public source",
            "raw_path": "data/01_raw/resolution.pdf",
            "public_document_confirmed": True,
            "personal_data_scope": "official_attribution_only",
        }
    ]
    manifest_path = tmp_path / "data/manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    passages = [
        Passage(
            id=str(number).zfill(64),
            text=f"Artículo {number} {'primero' if number == 1 else 'segundo'}",
            resolution=title,
            citation=f"{title}, artículo {number}",
            source_url=source_url,
            source_title=title,
            publication_date="2024-01-01",
            version=version,
            source_sha256=digest,
            kind="article",
            article_number=number,
            section_id=None,
            row_number=None,
            excerpt_id=None,
            page_start=1,
            page_end=1,
            part_number=1,
            part_count=1,
        )
        for number in (1, 2)
    ]
    build_dir = build_embeddings(
        passages,
        FakeEncoder(),
        tmp_path / "data/04_embeddings",
        model_id=MODEL_ID,
        model_revision=MODEL_REVISION,
        software_versions={"test": "1"},
        batch_size=1,
    )
    return tmp_path, build_dir


def test_index_reopens_and_filters_with_citation(source_build: tuple[Path, Path]) -> None:
    root, build_dir = source_build
    index_dir = build_index(root, build_dir)
    assert build_index(root, build_dir) == index_dir
    query = [1.0] + [0.0] * (MODEL_DIMENSION - 1)
    hits = search_index(index_dir, query, k=2)
    assert [hit.metadata["article_number"] for hit in hits] == [1, 2]
    assert hits[0].metadata["citation"] == "Resolución 1 de 2024, artículo 1"
    assert hits[0].metadata["source_url"] == "https://www.minsalud.gov.co/test/resolution.pdf"
    filtered = search_index(index_dir, query, article_number=2, kind="article", k=2)
    assert len(filtered) == 1
    assert filtered[0].metadata["article_number"] == 2
    assert search_index(index_dir, query, resolution="Resolución 2 de 2024") == []
    with pytest.raises(ValueError, match="normalized"):
        search_index(index_dir, [0.0] * MODEL_DIMENSION)


def test_changed_batch_requires_rebuild_and_rejects_corruption(
    source_build: tuple[Path, Path],
) -> None:
    root, build_dir = source_build
    index_dir = build_index(root, build_dir)
    batch_path = build_dir / "batch-00000.json"
    batch = json.loads(batch_path.read_text(encoding="utf-8"))
    batch["vectors"][0] = [0.0, 1.0] + [0.0] * (MODEL_DIMENSION - 2)
    batch_path.write_text(json.dumps(batch), encoding="utf-8")
    with pytest.raises(ValueError, match="differs from embedding inputs"):
        build_index(root, build_dir)
    assert build_index(root, build_dir, rebuild=True) == index_dir
    batch["vectors"][0] = [0.0] * MODEL_DIMENSION
    batch_path.write_text(json.dumps(batch), encoding="utf-8")
    with pytest.raises(ValueError, match="integrity checks"):
        build_index(root, build_dir, rebuild=True)


def test_source_checksum_and_passage_provenance_are_required(
    source_build: tuple[Path, Path],
) -> None:
    root, build_dir = source_build
    raw_path = root / "data/01_raw/resolution.pdf"
    raw_path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="checksum changed"):
        build_index(root, build_dir)
    raw_path.write_bytes(b"official fixture")
    batch_path = build_dir / "batch-00000.json"
    batch = json.loads(batch_path.read_text(encoding="utf-8"))
    batch["passages"][0]["source_url"] = "https://example.com/unofficial.pdf"
    batch["input_sha256"] = _sha256(batch["passages"])
    batch_path.write_text(json.dumps(batch), encoding="utf-8")
    with pytest.raises(ValueError, match="unverified official provenance"):
        build_index(root, build_dir)
