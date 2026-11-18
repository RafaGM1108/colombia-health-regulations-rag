"""Free-form text stays local; only reviewed public question IDs reach generation."""

import json
import logging
from collections.abc import Sequence
from pathlib import Path

import pytest

from colombia_health_rag.indexing.embeddings import MODEL_DIMENSION, Encoder
from colombia_health_rag.indexing.vector_index import SearchHit
from colombia_health_rag.serving import service as service_module
from colombia_health_rag.serving.generation import TextGenerator
from colombia_health_rag.serving.service import (
    GenerationUnavailableError,
    RegulationService,
    UnknownQuestionError,
)

ROOT = Path(__file__).resolve().parents[2]
TEXT = "El profesional de la salud tratante registra la prescripción."
# Synthetic personal details; never real data.
PRIVATE_QUERY = "Mi paciente Ana Pérez, cédula 1234567890, necesita oxígeno en casa"


class FakeEncoder:
    def __init__(self) -> None:
        self.sentences: list[str] = []

    def encode(
        self,
        sentences: Sequence[str],
        *,
        batch_size: int,
        normalize_embeddings: bool,
        show_progress_bar: bool,
    ) -> list[list[float]]:
        self.sentences.extend(sentences)
        return [[1.0] + [0.0] * (MODEL_DIMENSION - 1)]


class RecordingGenerator:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return json.dumps({"abstain": True, "claims": []})


def _hit() -> SearchHit:
    return SearchHit(
        id="a" * 64,
        text=TEXT,
        distance=0.1,
        metadata={
            "citation": "Resolución 740 de 2024, artículo 5",
            "resolution": "Resolución 740 de 2024",
            "source_url": "https://www.minsalud.gov.co/resolucion-740.pdf",
            "source_title": "Resolución 740 de 2024",
            "publication_date": "2024-05-02",
            "version": "Original",
            "source_sha256": "b" * 64,
            "kind": "article",
            "article_number": 5,
            "page_start": 2,
        },
    )


@pytest.fixture
def parts(monkeypatch: pytest.MonkeyPatch) -> tuple[RegulationService, FakeEncoder, list[object]]:
    monkeypatch.setattr(
        "colombia_health_rag.serving.generation.search_index", lambda *_a, **_k: [_hit()]
    )
    encoder = FakeEncoder()
    generators: list[object] = []

    def make_generator(_root: Path) -> TextGenerator:
        generator = RecordingGenerator()
        generators.append(generator)
        return generator

    def open_index(_root: Path) -> tuple[str, Path, Encoder]:
        return "build", Path("/unused"), encoder

    return (
        RegulationService(ROOT, open_index=open_index, make_generator=make_generator),
        (encoder),
        generators,
    )


def test_only_reviewed_questions_are_offered(
    parts: tuple[RegulationService, FakeEncoder, list[object]],
) -> None:
    service, _, _ = parts
    questions = service.public_questions()
    assert len(questions) == 26
    assert {item.id for item in questions} >= {"q01", "u04"}


def test_free_text_never_reaches_generation(
    parts: tuple[RegulationService, FakeEncoder, list[object]],
) -> None:
    service, encoder, generators = parts
    with pytest.raises(UnknownQuestionError):
        service.answer(PRIVATE_QUERY)
    assert generators == []
    assert encoder.sentences == []


def test_reviewed_question_is_the_only_text_sent(
    parts: tuple[RegulationService, FakeEncoder, list[object]],
) -> None:
    service, _, generators = parts
    question, answer = service.answer("q01")
    assert answer.refusal_reason == "abstained"
    (generator,) = generators
    assert isinstance(generator, RecordingGenerator)
    assert json.loads(generator.prompts[0])["question"] == question.question


def test_search_stays_local_and_is_not_logged(
    parts: tuple[RegulationService, FakeEncoder, list[object]],
    caplog: pytest.LogCaptureFixture,
) -> None:
    service, encoder, generators = parts
    with caplog.at_level(logging.DEBUG):
        hits = service.search(PRIVATE_QUERY)
    assert hits[0].metadata["citation"] == "Resolución 740 de 2024, artículo 5"
    assert generators == []
    assert encoder.sentences == [f"query: {PRIVATE_QUERY}"]
    assert "1234567890" not in caplog.text
    assert "Ana Pérez" not in caplog.text


@pytest.mark.parametrize("query", ["ab", "x" * 301, "   "])
def test_search_rejects_empty_or_long_queries(
    parts: tuple[RegulationService, FakeEncoder, list[object]], query: str
) -> None:
    service, encoder, _ = parts
    with pytest.raises(ValueError, match="between 3 and 300"):
        service.search(query)
    assert encoder.sentences == []


def test_missing_api_key_disables_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(GenerationUnavailableError):
        service_module._default_generator(tmp_path)
