"""Validate graded answer runs against their exact reports and compute answer-quality metrics."""

import argparse
import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from colombia_health_rag.indexing.embeddings import _write_atomic

Correctness = Literal["correct", "partial", "incorrect"]
Support = Literal["supported", "unsupported"]


class QuestionGrade(BaseModel):
    """Judgments for one question; refusals carry no correctness or claim labels."""

    model_config = ConfigDict(extra="forbid", strict=True)

    question_id: str = Field(pattern=r"^[qu][0-9]{2}$")
    correctness: Correctness | None = None
    claim_support: list[Support] = Field(default_factory=list)
    rationale: str = Field(min_length=1)


class GradeSet(BaseModel):
    """Grades tied by checksum to one saved generation report."""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1]
    answers_report: str = Field(min_length=1)
    answers_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    grader: str = Field(min_length=1)
    graded_on: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    grades: list[QuestionGrade]


def _ratio(numerator: int, denominator: int) -> dict[str, float | int]:
    value = round(numerator / denominator, 6) if denominator else 0.0
    return {"count": numerator, "of": denominator, "rate": value}


def score(report: dict[str, object], grades: GradeSet) -> dict[str, object]:
    """Check grades against the report's outputs and derive the answer-quality metrics."""
    results = {row["question_id"]: row for row in report["results"]}  # type: ignore[attr-defined]
    by_id = {grade.question_id: grade for grade in grades.grades}
    if set(results) != set(by_id) or len(by_id) != len(grades.grades):
        raise ValueError("Grades must cover each reported question exactly once")
    correct = answered = missed = 0
    evidence_absent = abstained_without_evidence = 0
    gold_available = gold_cited = 0
    supported = claims = 0
    for question_id, row in results.items():
        grade = by_id[question_id]
        if row["refused"]:
            if grade.correctness is not None or grade.claim_support:
                raise ValueError(f"Refused answer cannot be graded for content: {question_id}")
        elif grade.correctness is None or len(grade.claim_support) != len(row["claims"]):
            raise ValueError(f"Answered question needs correctness and claim labels: {question_id}")
        claims += len(grade.claim_support)
        supported += grade.claim_support.count("supported")
        if not row["answerable"] or not row["gold_retrieved"]:
            evidence_absent += 1
            abstained_without_evidence += bool(row["refused"])
        if not row["answerable"]:
            continue
        if row["gold_retrieved"]:
            gold_available += 1
            missed += bool(row["refused"])
        if row["refused"]:
            continue
        answered += 1
        correct += grade.correctness == "correct"
        gold_labels = {entry["citation"] for entry in row["retrieved"] if entry["is_gold"]}
        gold_cited += any(claim["citation"] in gold_labels for claim in row["claims"])
    answerable = sum(bool(row["answerable"]) for row in results.values())
    return {
        "answers_report": grades.answers_report,
        "generation_model": report["generation_model"],
        "grader": grades.grader,
        "correct_of_answerable": _ratio(correct, answerable),
        "correct_of_answered": _ratio(correct, answered),
        "claims_supported": _ratio(supported, claims),
        "answers_citing_gold": _ratio(gold_cited, answered),
        "abstained_when_evidence_absent": _ratio(abstained_without_evidence, evidence_absent),
        "refused_with_gold_available": _ratio(missed, gold_available),
    }


def load_and_score(root: Path, grades_path: Path) -> dict[str, object]:
    """Read one grade file, verify the exact report it refers to, and score it."""
    grades = GradeSet.model_validate_json(grades_path.read_bytes())
    report_path = root / grades.answers_report
    raw = report_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != grades.answers_sha256:
        raise ValueError(f"Grades do not match the current report: {grades.answers_report}")
    return score(json.loads(raw), grades)


def main() -> None:
    """Score every graded run and save one comparison report."""
    parser = argparse.ArgumentParser(description="Score graded answer runs")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    reporting = args.root / "data/07_reporting"
    runs = [load_and_score(args.root, path) for path in sorted(reporting.glob("grades-*.json"))]
    if not runs:
        parser.error("No grades-*.json files found in data/07_reporting")
    output = reporting / "answer-quality-v1.json"
    _write_atomic(output, {"schema_version": 1, "runs": runs}, indent=2)
    for run in runs:
        print(run["generation_model"])
        for key, value in run.items():
            if isinstance(value, dict):
                print(f"  {key}: {value['count']}/{value['of']} ({value['rate']:.1%})")
    print(f"Saved {output}")


if __name__ == "__main__":
    main()
