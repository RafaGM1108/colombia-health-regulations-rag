"""Check citation provenance, source quotes, and conservative refusals."""

import json
from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock

import pytest
from anthropic import Anthropic

from colombia_health_rag.indexing.embeddings import MODEL_DIMENSION
from colombia_health_rag.indexing.vector_index import SearchHit
from colombia_health_rag.serving.generation import (
    GENERATION_MODEL,
    OUTPUT_SCHEMA,
    AnthropicGenerator,
    answer_from_hits,
    answer_from_index,
)


class FakeGenerator:
    def __init__(self, response: dict[str, object] | str) -> None:
        self.response = response
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.response if isinstance(self.response, str) else json.dumps(self.response)


def _hit(*, article: int = 5, text: str = "El profesional registra la prescripción.") -> SearchHit:
    return SearchHit(
        id="a" * 64,
        text=text,
        distance=0.2,
        metadata={
            "citation": f"Resolución 740 de 2024, artículo {article}",
            "resolution": "Resolución 740 de 2024",
            "source_url": "https://www.minsalud.gov.co/resolucion-740.pdf",
            "source_title": "Resolución 740 de 2024",
            "publication_date": "2024-05-02",
            "version": "Original",
            "source_sha256": "b" * 64,
            "kind": "article",
            "article_number": article,
            "page_start": 2,
        },
    )


def _draft(
    *, evidence_id: str = "E1", quote: str = "El profesional registra la prescripción."
) -> dict[str, object]:
    return {
        "abstain": False,
        "claims": [
            {
                "text": "El profesional registra la prescripción.",
                "evidence_id": evidence_id,
                "quote": quote,
            }
        ],
    }


def test_supported_claim_uses_only_verified_citation_metadata() -> None:
    generator = FakeGenerator(_draft())
    result = answer_from_hits("¿Quién registra la prescripción?", [_hit()], generator)

    assert not result.refused
    assert len(result.claims) == 1
    assert result.claims[0].citation.label == "Resolución 740 de 2024, artículo 5"
    assert result.claims[0].citation.source_sha256 == "b" * 64
    assert "[Resolución 740 de 2024, artículo 5]" in result.text
    assert "https://www.minsalud.gov.co/resolucion-740.pdf#page=2" in result.text
    prompt = json.loads(generator.prompts[0])
    assert prompt["evidence"][0]["id"] == "E1"
    assert prompt["evidence"][0]["text"] == _hit().text


@pytest.mark.parametrize(
    "response",
    [
        {"abstain": True, "claims": []},
        _draft(evidence_id="E2"),
        _draft(quote="Una frase inventada que no aparece en la norma."),
        {"abstain": False, "claims": []},
        "not json",
    ],
)
def test_missing_or_invalid_support_is_refused(response: dict[str, object] | str) -> None:
    result = answer_from_hits("¿Quién registra la prescripción?", [_hit()], FakeGenerator(response))
    assert result.refused
    assert result.claims == ()
    assert "No pude verificar" in result.text


def test_no_hits_refuses_without_api_call() -> None:
    generator = FakeGenerator(_draft())
    result = answer_from_hits("¿Qué dice la norma?", [], generator)
    assert result.refused
    assert generator.prompts == []


def test_unofficial_or_mismatched_citation_is_rejected_before_api_call() -> None:
    generator = FakeGenerator(_draft())
    unofficial = _hit()
    unofficial.metadata["source_url"] = "https://example.com/private.pdf"
    with pytest.raises(ValueError, match="non-official"):
        answer_from_hits("¿Qué dice la norma?", [unofficial], generator)
    assert generator.prompts == []

    mismatched = _hit()
    mismatched.metadata["article_number"] = 9
    with pytest.raises(ValueError, match="article citation"):
        answer_from_hits("¿Qué dice la norma?", [mismatched], generator)


def test_reviewed_annex_row_keeps_its_precise_locator() -> None:
    hit = _hit(text="Tecnología: TEOFILINA; motivo: EPOC.")
    hit.metadata.update(
        {
            "citation": "Resolución 740 de 2024, anexo técnico, fila 10, p. 37",
            "kind": "annex",
            "section_id": "Anexo técnico",
            "row_number": 10,
            "page_start": 37,
        }
    )
    hit.metadata.pop("article_number")
    draft = {
        "abstain": False,
        "claims": [
            {
                "text": "La tabla menciona teofilina.",
                "evidence_id": "E1",
                "quote": "Tecnología: TEOFILINA",
            }
        ],
    }
    result = answer_from_hits("¿Qué tecnología aparece en la fila?", [hit], FakeGenerator(draft))
    assert not result.refused
    assert result.claims[0].citation.label.endswith("anexo técnico, fila 10, p. 37")


def test_retrieval_uses_query_prefix_and_normalized_vector(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeEncoder:
        def encode(
            self,
            sentences: Sequence[str],
            *,
            batch_size: int,
            normalize_embeddings: bool,
            show_progress_bar: bool,
        ) -> list[list[float]]:
            assert sentences == ["query: ¿Quién registra la prescripción?"]
            assert batch_size == 1
            assert normalize_embeddings
            assert not show_progress_bar
            return [[1.0] + [0.0] * (MODEL_DIMENSION - 1)]

    def fake_search(_index: Path, vector: list[float], *, k: int) -> list[SearchHit]:
        assert vector[0] == 1.0
        assert k == 5
        return [_hit()]

    monkeypatch.setattr("colombia_health_rag.serving.generation.search_index", fake_search)
    result = answer_from_index(
        "¿Quién registra la prescripción?",
        Path("/unused"),
        FakeEncoder(),
        FakeGenerator(_draft()),
    )
    assert not result.refused


def test_anthropic_call_requests_json_schema_and_rejects_truncation() -> None:
    response = SimpleNamespace(
        stop_reason="end_turn",
        content=[SimpleNamespace(type="text", text=json.dumps(_draft()))],
    )
    create = Mock(return_value=response)
    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    generator = AnthropicGenerator("local-test-key")
    generator.client = cast(Anthropic, client)

    assert json.loads(generator.generate("public question")) == _draft()
    kwargs = create.call_args.kwargs
    assert kwargs["model"] == GENERATION_MODEL
    assert kwargs["output_config"]["format"]["schema"] == OUTPUT_SCHEMA
    assert kwargs["messages"] == [{"role": "user", "content": "public question"}]

    response.stop_reason = "max_tokens"
    with pytest.raises(ValueError, match="complete"):
        generator.generate("public question")
