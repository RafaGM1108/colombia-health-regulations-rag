from collections.abc import Iterator

import pytest
from anthropic import APIError
from fastapi.testclient import TestClient

from colombia_health_rag import __version__
from colombia_health_rag.api.main import DISCLAIMER, app, get_service
from colombia_health_rag.evaluation.questions import Question
from colombia_health_rag.indexing.vector_index import SearchHit
from colombia_health_rag.serving.generation import Answer, Citation, SupportedClaim
from colombia_health_rag.serving.service import (
    GenerationUnavailableError,
    UnknownQuestionError,
)

URL = "https://www.minsalud.gov.co/resolucion-740.pdf"
LABEL = "Resolución 740 de 2024, artículo 5"


class _UpstreamError(APIError):
    def __init__(self) -> None:
        Exception.__init__(self, "upstream failure")


class FakeService:
    def __init__(self) -> None:
        self.error: Exception | None = None
        self.searched: list[str] = []

    def public_questions(self) -> list[Question]:
        return [Question(id="u01", question="¿Cuál es el precio de una consulta privada?")]

    def search(self, query: str) -> list[SearchHit]:
        if self.error:
            raise self.error
        self.searched.append(query)
        return [
            SearchHit(
                id="a" * 64,
                text="El profesional registra la prescripción.",
                distance=0.1,
                metadata={
                    "citation": LABEL,
                    "resolution": "Resolución 740 de 2024",
                    "source_url": URL,
                    "page_start": 2,
                },
            )
        ]

    def answer(self, question_id: str) -> tuple[Question, Answer]:
        if self.error:
            raise self.error
        if question_id != "u01":
            raise UnknownQuestionError(question_id)
        citation = Citation(
            LABEL, URL, "Resolución 740 de 2024", "2024-05-02", "Original", "b" * 64, 2
        )
        claim = SupportedClaim("Lo registra el profesional.", "El profesional registra", citation)
        return self.public_questions()[0], Answer("Lo registra el profesional.", False, (claim,))


@pytest.fixture
def fake() -> Iterator[FakeService]:
    service = FakeService()
    app.dependency_overrides[get_service] = lambda: service
    yield service
    app.dependency_overrides.clear()


def test_health() -> None:
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


def test_questions_list_reviewed_ids(fake: FakeService) -> None:
    response = TestClient(app).get("/questions")
    assert response.json() == [
        {"id": "u01", "question": "¿Cuál es el precio de una consulta privada?"}
    ]


def test_search_returns_cited_passages_with_page_links(fake: FakeService) -> None:
    response = TestClient(app).post("/search", json={"query": "prescripción en MIPRES"})
    assert response.status_code == 200
    body = response.json()
    assert body["disclaimer"] == DISCLAIMER
    assert body["results"][0]["citation"] == LABEL
    assert body["results"][0]["link"] == f"{URL}#page=2"
    assert fake.searched == ["prescripción en MIPRES"]


@pytest.mark.parametrize(
    "payload", [{"query": "ab"}, {"query": "x" * 301}, {"query": "ok?", "patient": "x"}, {}]
)
def test_search_validates_input(fake: FakeService, payload: dict[str, str]) -> None:
    assert TestClient(app).post("/search", json=payload).status_code == 422
    assert fake.searched == []


def test_answer_returns_claims_with_official_citations(fake: FakeService) -> None:
    response = TestClient(app).post("/answers", json={"question_id": "u01"})
    assert response.status_code == 200
    body = response.json()
    assert body["refused"] is False
    assert body["refusal_reason"] is None
    assert body["claims"][0]["citation"]["label"] == LABEL
    assert body["claims"][0]["citation"]["link"] == f"{URL}#page=2"
    assert body["disclaimer"] == DISCLAIMER


@pytest.mark.parametrize(
    "payload",
    [
        {"question": "Mi paciente con cédula 1234567890 necesita oxígeno"},
        {"question_id": "Mi paciente necesita oxígeno"},
        {"question_id": "u01", "question": "texto libre"},
    ],
)
def test_answer_rejects_free_text(fake: FakeService, payload: dict[str, str]) -> None:
    assert TestClient(app).post("/answers", json=payload).status_code == 422


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (None, 404),
        (GenerationUnavailableError("no key"), 503),
        (FileNotFoundError("index"), 503),
        (_UpstreamError(), 502),
    ],
)
def test_answer_errors_map_to_status_codes(
    fake: FakeService, error: Exception | None, status: int
) -> None:
    fake.error = error
    question_id = "q99" if error is None else "u01"
    response = TestClient(app).post("/answers", json={"question_id": question_id})
    assert response.status_code == status
    assert "1234567890" not in response.text


def test_search_reports_missing_index(fake: FakeService) -> None:
    fake.error = FileNotFoundError("index")
    assert TestClient(app).post("/search", json={"query": "MIPRES"}).status_code == 503
