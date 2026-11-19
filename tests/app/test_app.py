"""The chat shows the disclaimer, cited answers with PDF page links, and local search."""

from collections.abc import Iterator
from pathlib import Path
from typing import ClassVar

import pytest
import streamlit as st
from anthropic import APIError
from streamlit.testing.v1 import AppTest

from colombia_health_rag.evaluation.questions import Evidence, Question
from colombia_health_rag.indexing.vector_index import SearchHit
from colombia_health_rag.serving import service as service_module
from colombia_health_rag.serving.generation import REFUSAL, Answer, Citation, SupportedClaim

APP = Path(__file__).resolve().parents[2] / "src/colombia_health_rag/app/main.py"
URL = "https://www.minsalud.gov.co/resolucion-740.pdf"
LABEL = "Resolución 740 de 2024, artículo 5"


class _UpstreamError(APIError):
    def __init__(self) -> None:
        Exception.__init__(self, "upstream failure")


class FakeService:
    searched: ClassVar[list[str]] = []
    fail: ClassVar[bool] = False

    def __init__(self, _root: Path) -> None:
        pass

    def public_questions(self) -> list[Question]:
        return [
            Question(
                id="q01",
                question="¿Quién registra la prescripción en MIPRES?",
                expected_answer="El profesional tratante.",
                evidence=Evidence(source="r740", kind="article", article_number=5),
            ),
            Question(id="u01", question="¿Cuál es el precio de una consulta privada?"),
        ]

    def answer(self, question_id: str) -> tuple[Question, Answer]:
        if FakeService.fail:
            raise _UpstreamError()
        question = next(item for item in self.public_questions() if item.id == question_id)
        if question_id == "u01":
            return question, Answer(REFUSAL, True, (), "abstained")
        citation = Citation(
            LABEL, URL, "Resolución 740 de 2024", "2024-05-02", "Original", "b" * 64, 2
        )
        claim = SupportedClaim(
            "Lo registra el profesional tratante.", "será realizada por el profesional", citation
        )
        return question, Answer("Lo registra el profesional tratante.", False, (claim,))

    def search(self, query: str) -> list[SearchHit]:
        FakeService.searched.append(query)
        return [
            SearchHit(
                "a" * 64,
                "Artículo 5. Prescripción.",
                0.1,
                {"citation": LABEL, "source_url": URL, "page_start": 2},
            )
        ]


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch) -> Iterator[AppTest]:
    monkeypatch.setattr(service_module, "RegulationService", FakeService)
    FakeService.searched = []
    FakeService.fail = False
    st.cache_resource.clear()
    yield AppTest.from_file(str(APP), default_timeout=30).run()
    st.cache_resource.clear()


def _markdown(app: AppTest) -> str:
    return "\n".join(element.value for element in app.markdown)


def test_disclaimer_is_visible(app: AppTest) -> None:
    assert not app.exception
    assert "no es asesoría legal ni médica" in app.info[0].value


def test_reviewed_answer_shows_quote_and_page_link(app: AppTest) -> None:
    app.selectbox[0].select("q01")
    app.button[0].click().run()
    text = _markdown(app)
    assert "Lo registra el profesional tratante." in text
    assert "> será realizada por el profesional" in text
    assert f"[{LABEL}]({URL}#page=2)" in text
    assert len(app.chat_message) == 2


def test_refusal_explains_its_reason(app: AppTest) -> None:
    app.selectbox[0].select("u01")
    app.button[0].click().run()
    assert REFUSAL in app.warning[0].value
    assert any("no respaldan una respuesta" in caption.value for caption in app.caption)


def test_search_lists_cited_passages(app: AppTest) -> None:
    app.text_input[0].input("prescripción en MIPRES").run()
    assert f"[{LABEL}]({URL}#page=2)" in _markdown(app)
    assert FakeService.searched == ["prescripción en MIPRES"]


def test_generation_failure_shows_a_message_not_a_traceback(app: AppTest) -> None:
    FakeService.fail = True
    app.button[0].click().run()
    assert not app.exception
    assert "falló" in app.error[0].value
