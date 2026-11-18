"""Record raw generations, gold retrieval, and refusal reasons for later grading."""

import json
from pathlib import Path
from typing import cast

import pytest

from colombia_health_rag.evaluation import answers
from colombia_health_rag.evaluation.answers import evaluate_answers, summarize
from colombia_health_rag.evaluation.questions import Evidence, Question, QuestionSet
from colombia_health_rag.indexing.vector_index import SearchHit

SHA = "b" * 64
TEXT = "El profesional de la salud tratante registra la prescripción en MIPRES."


class ScriptedGenerator:
    """Return one prepared response per call, in order."""

    def __init__(self, *responses: str) -> None:
        self.responses = list(responses)

    def generate(self, prompt: str) -> str:
        return self.responses.pop(0)


def _hit(article: int) -> SearchHit:
    return SearchHit(
        id=f"{article:064d}",
        text=TEXT,
        distance=0.1,
        metadata={
            "citation": f"Resolución 740 de 2024, artículo {article}",
            "resolution": "Resolución 740 de 2024",
            "source_url": "https://www.minsalud.gov.co/resolucion-740.pdf",
            "source_title": "Resolución 740 de 2024",
            "publication_date": "2024-05-02",
            "version": "Original",
            "source_sha256": SHA,
            "kind": "article",
            "article_number": article,
            "page_start": 2,
            "page_end": 2,
            "part_number": 1,
            "part_count": 1,
        },
    )


def _questions() -> QuestionSet:
    return QuestionSet(
        schema_version=1,
        sources={"r740": SHA},
        questions=[
            Question(
                id="q01",
                question="¿Quién registra la prescripción en MIPRES?",
                expected_answer="El profesional tratante.",
                evidence=Evidence(source="r740", kind="article", article_number=5),
            ),
            Question(
                id="q02",
                question="¿Qué artículo define el reporte de suministro?",
                expected_answer="El artículo 9.",
                evidence=Evidence(source="r740", kind="article", article_number=9),
            ),
            Question(id="u01", question="¿Cuál es el precio de una consulta privada?"),
        ],
    )


def test_records_gold_retrieval_raw_output_and_refusal_reason() -> None:
    answer = json.dumps(
        {
            "abstain": False,
            "claims": [
                {
                    "text": "Lo registra el profesional tratante.",
                    "evidence_id": "E2",
                    "quote": "profesional de la salud tratante registra",
                }
            ],
        }
    )
    abstain = json.dumps({"abstain": True, "claims": []})
    generator = ScriptedGenerator(answer, "not json", abstain)

    records = evaluate_answers(_questions(), lambda _q: [_hit(3), _hit(5), _hit(7)], generator)

    first, second, third = records
    assert first["gold_retrieved"] is True
    retrieved = cast(list[dict[str, object]], first["retrieved"])
    assert [entry["is_gold"] for entry in retrieved] == [False, True, False]
    assert first["raw_output"] == answer
    assert first["refused"] is False
    assert first["refusal_reason"] is None
    assert first["claims"] == [
        {
            "text": "Lo registra el profesional tratante.",
            "quote": "profesional de la salud tratante registra",
            "citation": "Resolución 740 de 2024, artículo 5",
        }
    ]
    assert second["gold_retrieved"] is False
    assert second["refusal_reason"] == "invalid_output"
    assert second["raw_output"] == "not json"
    assert third["answerable"] is False
    assert third["gold_retrieved"] is None
    assert third["refusal_reason"] == "abstained"


def test_empty_retrieval_records_no_model_output() -> None:
    records = evaluate_answers(_questions(), lambda _q: [], ScriptedGenerator())
    assert all(row["raw_output"] is None for row in records)
    assert all(row["refusal_reason"] == "no_evidence" for row in records)


def test_summary_separates_answerable_and_out_of_corpus_outcomes() -> None:
    rows: list[dict[str, object]] = [
        {"answerable": True, "gold_retrieved": True, "refused": False, "refusal_reason": None},
        {
            "answerable": True,
            "gold_retrieved": False,
            "refused": True,
            "refusal_reason": "unverified_citation",
        },
        {
            "answerable": False,
            "gold_retrieved": None,
            "refused": True,
            "refusal_reason": "abstained",
        },
    ]
    assert summarize(rows) == {
        "answerable": {
            "count": 2,
            "gold_retrieved": 1,
            "outcomes": {"answered": 1, "unverified_citation": 1},
        },
        "unanswerable": {"count": 1, "outcomes": {"abstained": 1}},
    }


def test_run_saves_fingerprinted_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = Path(__file__).resolve().parents[2]
    monkeypatch.setattr(answers, "open_article_index", lambda _root: ("build", tmp_path, None))
    monkeypatch.setattr(answers, "retrieve", lambda *_args, **_kwargs: [_hit(5)])
    abstain = json.dumps({"abstain": True, "claims": []})
    report_path = tmp_path / "answers.json"

    report = answers.run(root, report_path, ScriptedGenerator(*[abstain] * 26))

    saved = json.loads(report_path.read_text(encoding="utf-8"))
    assert saved["index_build_id"] == "build"
    assert saved["generation_model"] == "claude-sonnet-4-6"
    assert len(saved["generator_config_sha256"]) == 64
    assert len(saved["results"]) == 26
    assert saved["summary"] == report["summary"]
    assert saved["summary"]["unanswerable"] == {"count": 4, "outcomes": {"abstained": 4}}
