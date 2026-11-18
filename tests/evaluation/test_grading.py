"""Grades must match their exact report, and metrics must follow from the labels."""

import hashlib
import json
from pathlib import Path

import pytest

from colombia_health_rag.evaluation.grading import GradeSet, QuestionGrade, load_and_score, score

GOLD = "Resolución 740 de 2024, artículo 5"
OTHER = "Resolución 740 de 2024, artículo 9"


def _row(qid: str, *, answerable: bool, gold: bool | None, claims: list[str]) -> dict[str, object]:
    return {
        "question_id": qid,
        "answerable": answerable,
        "gold_retrieved": gold,
        "retrieved": [
            {"citation": GOLD, "is_gold": bool(gold)},
            {"citation": OTHER, "is_gold": False if answerable else None},
        ],
        "refused": not claims,
        "claims": [{"citation": citation} for citation in claims],
    }


REPORT: dict[str, object] = {
    "generation_model": "test-model",
    "results": [
        _row("q01", answerable=True, gold=True, claims=[GOLD, OTHER]),
        _row("q02", answerable=True, gold=True, claims=[]),
        _row("q03", answerable=True, gold=False, claims=[OTHER]),
        _row("q04", answerable=True, gold=False, claims=[]),
        _row("u01", answerable=False, gold=None, claims=[]),
    ],
}


def _grades(**overrides: QuestionGrade) -> GradeSet:
    grades = {
        "q01": QuestionGrade(
            question_id="q01",
            correctness="correct",
            claim_support=["supported", "unsupported"],
            rationale="Right answer; one claim overreaches.",
        ),
        "q02": QuestionGrade(question_id="q02", rationale="Missed despite gold evidence."),
        "q03": QuestionGrade(
            question_id="q03",
            correctness="incorrect",
            claim_support=["supported"],
            rationale="Answered from the wrong article.",
        ),
        "q04": QuestionGrade(question_id="q04", rationale="Appropriate abstention."),
        "u01": QuestionGrade(question_id="u01", rationale="Outside the corpus."),
    }
    grades.update(overrides)
    return GradeSet(
        schema_version=1,
        answers_report="data/07_reporting/answers-test.json",
        answers_sha256="0" * 64,
        grader="test grader",
        graded_on="2026-11-18",
        grades=list(grades.values()),
    )


def test_metrics_follow_labels_and_mechanical_outcomes() -> None:
    metrics = score(REPORT, _grades())
    assert metrics["correct_of_answerable"] == {"count": 1, "of": 4, "rate": 0.25}
    assert metrics["correct_of_answered"] == {"count": 1, "of": 2, "rate": 0.5}
    assert metrics["claims_supported"] == {"count": 2, "of": 3, "rate": 0.666667}
    assert metrics["answers_citing_gold"] == {"count": 1, "of": 2, "rate": 0.5}
    assert metrics["abstained_when_evidence_absent"] == {"count": 2, "of": 3, "rate": 0.666667}
    assert metrics["refused_with_gold_available"] == {"count": 1, "of": 2, "rate": 0.5}


@pytest.mark.parametrize(
    "override",
    [
        QuestionGrade(question_id="q01", correctness="correct", rationale="Missing claim labels."),
        QuestionGrade(question_id="q02", correctness="correct", rationale="Refusal with a grade."),
    ],
)
def test_inconsistent_labels_are_rejected(override: QuestionGrade) -> None:
    with pytest.raises(ValueError, match=override.question_id):
        score(REPORT, _grades(**{override.question_id: override}))


def test_grades_must_cover_every_question() -> None:
    grades = _grades()
    grades.grades.pop()
    with pytest.raises(ValueError, match="exactly once"):
        score(REPORT, grades)


def test_grades_are_bound_to_the_exact_report(tmp_path: Path) -> None:
    report_path = tmp_path / "data/07_reporting/answers-test.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text(json.dumps(REPORT), encoding="utf-8")
    grades = _grades()
    grades.answers_sha256 = hashlib.sha256(report_path.read_bytes()).hexdigest()
    grades_path = tmp_path / "grades.json"
    grades_path.write_text(grades.model_dump_json(), encoding="utf-8")

    assert load_and_score(tmp_path, grades_path)["generation_model"] == "test-model"

    report_path.write_text(json.dumps(REPORT) + " ", encoding="utf-8")
    with pytest.raises(ValueError, match="do not match"):
        load_and_score(tmp_path, grades_path)
