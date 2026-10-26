"""Validate human-written questions and their official evidence locators."""

from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from colombia_health_rag.indexing.embeddings import Passage
from colombia_health_rag.ingestion.manifest import load_manifest


class Evidence(BaseModel):
    """A source document and one article or reviewed annex excerpt."""

    model_config = ConfigDict(extra="forbid", strict=True)

    source: str = Field(min_length=1)
    kind: Literal["article", "annex"]
    article_number: int | None = Field(default=None, ge=1)
    section_id: str | None = None
    excerpt_id: str | None = None
    row_number: int | None = Field(default=None, ge=1)
    page_start: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def valid_locator(self) -> "Evidence":
        """Require a precise, unambiguous article or annex location."""
        if self.kind == "article":
            if self.article_number is None or any(
                value is not None
                for value in (self.section_id, self.excerpt_id, self.row_number, self.page_start)
            ):
                raise ValueError("Article evidence needs only an article number")
        elif (
            self.article_number is not None
            or not self.section_id
            or (self.excerpt_id is None) == (self.row_number is None)
            or (self.row_number is not None and self.page_start is None)
        ):
            raise ValueError("Annex evidence needs one reviewed excerpt or page-local row")
        return self


class Question(BaseModel):
    """A public question with a concise gold answer or an abstention target."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str = Field(pattern=r"^[qu][0-9]{2}$")
    question: str = Field(min_length=12)
    expected_answer: str | None = Field(default=None, min_length=1)
    evidence: Evidence | None = None

    @model_validator(mode="after")
    def answer_matches_evidence(self) -> "Question":
        """Unanswerable examples must not accidentally carry gold evidence."""
        if (self.expected_answer is None) != (self.evidence is None):
            raise ValueError("Expected answer and evidence must both be present or absent")
        if self.id.startswith("u") != (self.evidence is None):
            raise ValueError("Question ID does not match answerability")
        return self


class QuestionSet(BaseModel):
    """A frozen evaluation set keyed to exact official source checksums."""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1]
    sources: dict[str, str] = Field(min_length=1)
    questions: list[Question] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_references(self) -> "QuestionSet":
        """Reject duplicate examples and missing source aliases."""
        ids = [item.id for item in self.questions]
        texts = [item.question.casefold().strip() for item in self.questions]
        if len(ids) != len(set(ids)) or len(texts) != len(set(texts)):
            raise ValueError("Evaluation question IDs and texts must be unique")
        if len(set(self.sources.values())) != len(self.sources):
            raise ValueError("Source aliases must identify distinct documents")
        if any(
            item.evidence is not None and item.evidence.source not in self.sources
            for item in self.questions
        ):
            raise ValueError("Evaluation question references an unknown source alias")
        return self


def load_questions(path: Path, manifest_path: Path) -> QuestionSet:
    """Load the fixed set and verify every source hash against the official manifest."""
    questions = QuestionSet.model_validate_json(path.read_bytes())
    official_hashes = {source.sha256 for source in load_manifest(manifest_path)}
    if not set(questions.sources.values()) <= official_hashes:
        raise ValueError("Evaluation set references a document outside the official manifest")
    return questions


def matches_evidence(passage: Passage, evidence: Evidence, sources: dict[str, str]) -> bool:
    """Match gold locations across article-aware and alternative passage splits."""
    if passage.source_sha256 != sources[evidence.source] or passage.kind != evidence.kind:
        return False
    if evidence.kind == "article":
        return passage.article_number == evidence.article_number
    return (
        passage.section_id == evidence.section_id
        and passage.excerpt_id == evidence.excerpt_id
        and passage.row_number == evidence.row_number
        and (evidence.page_start is None or passage.page_start == evidence.page_start)
    )


def validate_gold_locations(question_set: QuestionSet, passages: Sequence[Passage]) -> None:
    """Fail before scoring if a gold location is absent from the reviewed corpus."""
    for item in question_set.questions:
        if item.evidence is not None and not any(
            matches_evidence(passage, item.evidence, question_set.sources) for passage in passages
        ):
            raise ValueError(f"Gold evidence is missing from reviewed passages: {item.id}")
