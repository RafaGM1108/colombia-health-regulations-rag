"""FastAPI application for regulation retrieval and cited answers.

The input contract is in docs/interface.md: answers only for reviewed public question IDs,
free-form text only for local passage search. Request bodies are never stored or logged.
"""

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from anthropic import APIError
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from colombia_health_rag import __version__
from colombia_health_rag.indexing.vector_index import SearchHit
from colombia_health_rag.serving.generation import RefusalReason
from colombia_health_rag.serving.service import (
    MAX_QUERY_CHARS,
    GenerationUnavailableError,
    RegulationService,
    UnknownQuestionError,
)

DISCLAIMER = (
    "Informational only; not legal or medical advice. Confirm in the cited official document."
)

app = FastAPI(title="Colombian Health Regulations RAG", version=__version__)


@lru_cache(maxsize=1)
def get_service() -> RegulationService:
    """Create one service per process; the index loads on first search or answer."""
    return RegulationService(Path.cwd())


Service = Annotated[RegulationService, Depends(get_service)]


class Health(BaseModel):
    """Health check response."""

    status: str
    version: str


class PublicQuestion(BaseModel):
    """A reviewed public question that may be answered."""

    id: str
    question: str


class SearchRequest(BaseModel):
    """A short regulation topic; it is searched locally and not stored."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=3, max_length=MAX_QUERY_CHARS)


class Passage(BaseModel):
    """An official passage with its exact citation and a page link."""

    citation: str
    resolution: str
    text: str
    source_url: str
    page: int
    link: str


class SearchResponse(BaseModel):
    """Ranked official passages; not an answer."""

    results: list[Passage]
    disclaimer: str = DISCLAIMER


class AnswerRequest(BaseModel):
    """The ID of a reviewed public question; free text is not accepted."""

    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(pattern=r"^[qu][0-9]{2}$")


class Citation(BaseModel):
    """Source reference rendered from verified index metadata."""

    label: str
    source_url: str
    source_title: str
    publication_date: str
    version: str
    page: int
    link: str


class Claim(BaseModel):
    """One statement with its exact official quotation."""

    text: str
    quote: str
    citation: Citation


class AnswerResponse(BaseModel):
    """A cited answer, or a refusal with its reason."""

    question_id: str
    question: str
    refused: bool
    refusal_reason: RefusalReason | None
    text: str
    claims: list[Claim]
    disclaimer: str = DISCLAIMER


def _link(url: str, page: int) -> str:
    return f"{url}#page={page}"


def _passage(hit: SearchHit) -> Passage:
    url = str(hit.metadata["source_url"])
    page = int(hit.metadata["page_start"])
    return Passage(
        citation=str(hit.metadata["citation"]),
        resolution=str(hit.metadata["resolution"]),
        text=hit.text,
        source_url=url,
        page=page,
        link=_link(url, page),
    )


@app.get("/health")
def health() -> Health:
    """Report that the service is up."""
    return Health(status="ok", version=__version__)


@app.get("/questions")
def questions(service: Service) -> list[PublicQuestion]:
    """List the reviewed public questions accepted by `/answers`."""
    return [
        PublicQuestion(id=item.id, question=item.question) for item in service.public_questions()
    ]


@app.post("/search")
def search(request: SearchRequest, service: Service) -> SearchResponse:
    """Return up to five official passages for a regulation topic, searched locally."""
    try:
        hits = service.search(request.query)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="The local index is not built") from None
    return SearchResponse(results=[_passage(hit) for hit in hits])


@app.post("/answers")
def answers(request: AnswerRequest, service: Service) -> AnswerResponse:
    """Answer a reviewed public question with citations, or refuse with a reason."""
    try:
        question, answer = service.answer(request.question_id)
    except UnknownQuestionError:
        raise HTTPException(status_code=404, detail="Unknown public question ID") from None
    except GenerationUnavailableError:
        raise HTTPException(status_code=503, detail="Answer generation is not configured") from None
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="The local index is not built") from None
    except APIError:
        raise HTTPException(status_code=502, detail="The generation service failed") from None
    return AnswerResponse(
        question_id=question.id,
        question=question.question,
        refused=answer.refused,
        refusal_reason=answer.refusal_reason,
        text=answer.text,
        claims=[
            Claim(
                text=claim.text,
                quote=claim.quote,
                citation=Citation(
                    label=claim.citation.label,
                    source_url=claim.citation.source_url,
                    source_title=claim.citation.source_title,
                    publication_date=claim.citation.publication_date,
                    version=claim.citation.version,
                    page=claim.citation.page_start,
                    link=_link(claim.citation.source_url, claim.citation.page_start),
                ),
            )
            for claim in answer.claims
        ],
    )
