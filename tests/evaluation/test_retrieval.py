"""Verify exact ranking, source-level metrics, and the fixed-window split."""

from dataclasses import replace
from typing import cast

from colombia_health_rag.evaluation.questions import Evidence, Question, QuestionSet
from colombia_health_rag.evaluation.retrieval import evaluate_strategy, rank_passages
from colombia_health_rag.indexing.embeddings import Passage, split_text


class WordTokenizer:
    def encode(
        self, text: str, *, add_special_tokens: bool = True, verbose: bool = False
    ) -> list[int]:
        return list(range(len(text.split())))


def _passage(article: int, passage_id: str) -> Passage:
    return Passage(
        id=passage_id,
        text=f"Artículo {article}",
        resolution="Resolución 1 de 2024",
        citation=f"Resolución 1 de 2024, artículo {article}",
        source_url="https://www.minsalud.gov.co/resolution.pdf",
        source_title="Resolución 1 de 2024",
        publication_date="2024-01-01",
        version="Original",
        source_sha256="a" * 64,
        kind="article",
        article_number=article,
        section_id=None,
        row_number=None,
        excerpt_id=None,
        page_start=1,
        page_end=1,
        part_number=1,
        part_count=1,
    )


def test_fixed_windows_overlap_without_crossing_record_or_token_limit() -> None:
    parts = split_text(
        "uno dos tres cuatro cinco seis siete ocho nueve diez",
        WordTokenizer(),
        5,
        overlap_words=2,
    )
    assert parts == (
        "uno dos tres cuatro",
        "tres cuatro cinco seis",
        "cinco seis siete ocho",
        "siete ocho nueve diez",
    )
    assert all(len(WordTokenizer().encode(f"passage: {part}")) <= 5 for part in parts)


def test_exact_ranking_and_answerable_metrics() -> None:
    first = _passage(1, "a")
    second = _passage(2, "b")
    questions = QuestionSet(
        schema_version=1,
        sources={"original": "a" * 64},
        questions=[
            Question(
                id="q01",
                question="¿Qué indica el primer artículo?",
                expected_answer="Primero",
                evidence=Evidence(source="original", kind="article", article_number=1),
            ),
            Question(
                id="q02",
                question="¿Qué indica el segundo artículo?",
                expected_answer="Segundo",
                evidence=Evidence(source="original", kind="article", article_number=2),
            ),
            Question(id="u01", question="¿Cuál es el precio actual?"),
        ],
    )
    passages = [first, second]
    vectors = [[1.0, 0.0], [0.0, 1.0]]
    assert rank_passages(passages, vectors, [1.0, 1.0]) == passages
    assert rank_passages([replace(first, id="z"), second], vectors, [1.0, 1.0]) == [
        second,
        replace(first, id="z"),
    ]
    result = evaluate_strategy(questions, passages, vectors, [[0.0, 1.0], [0.0, 1.0]])
    assert result["hit_rate_at_k"] == {"1": 0.5, "3": 1.0, "5": 1.0, "10": 1.0}
    assert result["mrr"] == 0.75
    assert result["unanswerable_count"] == 1
    per_question = cast(list[dict[str, object]], result["per_question"])
    assert [item["first_relevant_rank"] for item in per_question] == [2, 1]
