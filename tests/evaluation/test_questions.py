"""Keep the fixed evaluation set tied to reviewed, official sources."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError

from colombia_health_rag.evaluation.questions import (
    Evidence,
    Question,
    QuestionSet,
    load_questions,
    matches_evidence,
    validate_gold_locations,
)
from colombia_health_rag.indexing.embeddings import Passage

ROOT = Path(__file__).resolve().parents[2]
QUESTIONS = ROOT / "data/06_evaluation/questions.json"
MANIFEST = ROOT / "data/manifest.json"


def test_fixed_set_has_source_linked_answers_and_corpus_gaps() -> None:
    question_set = load_questions(QUESTIONS, MANIFEST)
    answerable = [item for item in question_set.questions if item.evidence is not None]
    unanswerable = [item for item in question_set.questions if item.evidence is None]
    assert len(answerable) == 22
    assert len(unanswerable) == 4
    assert {item.evidence.source for item in answerable if item.evidence} == set(
        question_set.sources
    )
    assert {item.evidence.kind for item in answerable if item.evidence} == {"article", "annex"}


def test_annex_gold_locations_come_from_reviewed_ledgers() -> None:
    question_set = load_questions(QUESTIONS, MANIFEST)
    manual = json.loads((ROOT / "data/reviews/resolution-3100-home-care.json").read_bytes())
    table = json.loads((ROOT / "data/reviews/resolution-740-annex.json").read_bytes())
    reviewed_sections = {
        (entry["section_id"], entry.get("excerpt_id", entry["section_id"]))
        for entry in manual["entries"]
        if entry["verified"]
    }
    for item in question_set.questions:
        evidence = item.evidence
        if evidence is None or evidence.kind != "annex":
            continue
        if evidence.source == "r3100":
            assert (evidence.section_id, evidence.excerpt_id) in reviewed_sections
        elif evidence.source == "r740":
            page_index = table["source_pages"].index(evidence.page_start)
            assert evidence.row_number is not None
            assert evidence.row_number <= table["page_row_counts"][page_index]
        else:
            pytest.fail(f"Unexpected annex source: {evidence.source}")


def test_rejects_unknown_document_and_false_abstention(tmp_path: Path) -> None:
    payload = json.loads(QUESTIONS.read_bytes())
    payload["sources"]["r740"] = "0" * 64
    changed = tmp_path / "questions.json"
    changed.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="outside the official manifest"):
        load_questions(changed, MANIFEST)
    with pytest.raises(ValidationError, match="both be present or absent"):
        Question.model_validate(
            {"id": "u99", "question": "¿Qué dice esta fuente oficial?", "expected_answer": "Sí"}
        )


def test_gold_match_requires_exact_source_and_annex_excerpt() -> None:
    question_set = load_questions(QUESTIONS, MANIFEST)
    item = next(item for item in question_set.questions if item.id == "q19")
    assert item.evidence is not None
    source_hash = question_set.sources[item.evidence.source]
    passage = Passage(
        id="a" * 64,
        text="Consulta externa general: modalidad domiciliaria",
        resolution="Resolución 3100 de 2019",
        citation="Resolución 3100 de 2019, anexo técnico, sección 11.2.1, p. 80",
        source_url="https://www.minsalud.gov.co/test.pdf",
        source_title="Resolución 3100 de 2019",
        publication_date="2019-11-26",
        version="Original",
        source_sha256=source_hash,
        kind="annex",
        article_number=None,
        section_id="11.2.1",
        row_number=None,
        excerpt_id="11.2.1-modalities",
        page_start=80,
        page_end=80,
        part_number=1,
        part_count=1,
    )
    assert matches_evidence(passage, item.evidence, question_set.sources)
    one_question = QuestionSet(schema_version=1, sources=question_set.sources, questions=[item])
    validate_gold_locations(one_question, [passage])
    wrong_excerpt = replace(passage, excerpt_id="11.2.1-equipment")
    assert not matches_evidence(wrong_excerpt, item.evidence, question_set.sources)
    with pytest.raises(ValueError, match="q19"):
        validate_gold_locations(one_question, [wrong_excerpt])


def test_annex_locator_requires_reviewed_excerpt_or_page_row() -> None:
    with pytest.raises(ValidationError, match="Annex evidence"):
        Evidence(source="r3100", kind="annex", section_id="11.2.1")
