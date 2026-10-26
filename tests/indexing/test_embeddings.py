"""Check source boundaries, token limits, and resumable embedding batches."""

import json
from collections.abc import Sequence
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from colombia_health_rag.indexing.embeddings import (
    Passage,
    build_embeddings,
    collect_official_records,
    format_query,
    make_passages,
    normalize_text,
)
from colombia_health_rag.ingestion.annexes import AnnexSectionRecord
from colombia_health_rag.ingestion.articles import ArticleRecord


class WordTokenizer:
    def encode(
        self, text: str, *, add_special_tokens: bool = True, verbose: bool = False
    ) -> list[int]:
        return list(range(len(text.split())))


class RecordingEncoder:
    def __init__(self, *, invalid: bool = False) -> None:
        self.calls: list[list[str]] = []
        self.invalid = invalid

    def encode(
        self,
        sentences: Sequence[str],
        *,
        batch_size: int,
        normalize_embeddings: bool,
        show_progress_bar: bool,
    ) -> list[list[float]]:
        assert batch_size == 2
        assert normalize_embeddings
        assert not show_progress_bar
        assert all(sentence.startswith("passage: ") for sentence in sentences)
        self.calls.append(list(sentences))
        if self.invalid:
            return [[float("nan"), 0.0, 0.0] for _ in sentences]
        return [[1.0, 0.0, 0.0] for _ in sentences]


def _article(text: str) -> ArticleRecord:
    return ArticleRecord(
        number=7,
        text=text,
        page_start=3,
        page_end=4,
        section_path=("Título I",),
        resolution="Resolución 100 de 2024",
        source_url="https://www.minsalud.gov.co/resolution.pdf",
        source_title="Resolución 100 de 2024",
        publication_date=date(2024, 1, 1),
        version="Original",
        sha256="a" * 64,
    )


def _annex(*, reviewed: bool, excerpt_id: str) -> AnnexSectionRecord:
    return AnnexSectionRecord(
        section_id="11.3.1",
        heading="Terapias",
        text="Criterio de atención domiciliaria verificado.",
        page_start=94,
        page_end=94,
        resolution="Resolución 3100 de 2019",
        source_url="https://www.minsalud.gov.co/resolution.pdf",
        source_title="Resolución 3100 de 2019",
        publication_date=date(2019, 11, 26),
        version="Original",
        sha256="b" * 64,
        review_required=not reviewed,
        excerpt_id=excerpt_id,
    )


def test_normalized_article_chunks_fit_model_window_and_keep_citations() -> None:
    text = "Uno  dos\n tres cuatro cinco seis siete ocho nueve diez"
    tokenizer = WordTokenizer()
    passages = make_passages([_article(text)], tokenizer, max_tokens=5)

    assert len(passages) == 3
    assert sorted(passage.part_number for passage in passages) == [1, 2, 3]
    assert all(passage.part_count == 3 for passage in passages)
    assert all(len(tokenizer.encode(f"passage: {passage.text}")) <= 5 for passage in passages)
    assert all(passage.citation == "Resolución 100 de 2024, artículo 7" for passage in passages)
    assert all((passage.page_start, passage.page_end) == (3, 4) for passage in passages)
    assert normalize_text(text) == "Uno dos tres cuatro cinco seis siete ocho nueve diez"
    assert format_query("  ¿Qué\n exige? ") == "query: ¿Qué exige?"
    assert make_passages([_article(text)], tokenizer, max_tokens=5) == passages


def test_unreviewed_annex_is_rejected_and_reviewed_excerpts_stay_distinct() -> None:
    tokenizer = WordTokenizer()
    with pytest.raises(ValueError, match="Unreviewed annex"):
        make_passages([_annex(reviewed=False, excerpt_id="11.3.1-a")], tokenizer, 20)

    passages = make_passages(
        [
            _annex(reviewed=True, excerpt_id="11.3.1-a"),
            _annex(reviewed=True, excerpt_id="11.3.1-b"),
        ],
        tokenizer,
        20,
    )
    assert len({passage.id for passage in passages}) == 2
    assert {passage.excerpt_id for passage in passages} == {"11.3.1-a", "11.3.1-b"}
    assert all(passage.citation.endswith("sección 11.3.1, p. 94") for passage in passages)


def test_embedding_build_resumes_exact_batches_and_rejects_tampering(tmp_path: Path) -> None:
    passages = make_passages(
        [_article("uno dos tres cuatro cinco seis siete ocho")], WordTokenizer(), 5
    )
    assert len(passages) == 2
    passages = (*passages, replace(passages[0], id="c" * 64, text="otro texto"))
    encoder = RecordingEncoder()

    def run_build(items: Sequence[Passage]) -> Path:
        return build_embeddings(
            items,
            encoder,
            tmp_path,
            model_id="pinned-model",
            model_revision="reviewed-revision",
            software_versions={"sentence-transformers": "5.7.0"},
            batch_size=2,
            dimension=3,
        )

    build_dir = run_build(passages)
    manifest = json.loads((build_dir / "build.json").read_text())
    assert manifest["passage_count"] == 3
    assert manifest["source_sha256s"] == ["a" * 64]
    assert len(manifest["batch_files"]) == 2
    assert len(encoder.calls) == 2
    assert run_build(tuple(reversed(passages))) == build_dir
    assert len(encoder.calls) == 2

    batch_path = build_dir / manifest["batch_files"][0]
    batch = json.loads(batch_path.read_text())
    batch["vectors"][0] = [0.0]
    batch_path.write_text(json.dumps(batch))
    with pytest.raises(ValueError, match="failed validation"):
        run_build(passages)


def test_invalid_vectors_are_not_saved(tmp_path: Path) -> None:
    passage: Passage = make_passages([_article("una norma")], WordTokenizer(), 8)[0]
    with pytest.raises(ValueError, match="invalid vectors"):
        build_embeddings(
            [passage],
            RecordingEncoder(invalid=True),
            tmp_path,
            model_id="pinned-model",
            model_revision="reviewed-revision",
            software_versions={"sentence-transformers": "5.7.0"},
            batch_size=2,
            dimension=3,
        )
    assert not list(tmp_path.rglob("batch-*.json"))


def test_official_record_collection_when_local_pdfs_are_available() -> None:
    root = Path(__file__).resolve().parents[2]
    if not (root / "data/01_raw/resolution-3100.pdf").is_file():
        pytest.skip("Original official PDFs are intentionally excluded from Git")

    records = collect_official_records(root)

    assert len(records) == 53 + 60 + 27 + 2 + 212 + 19
    assert all(
        not record.review_required for record in records if isinstance(record, AnnexSectionRecord)
    )
    assert not any("@" in record.text for record in records)
