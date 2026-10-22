"""FastAPI application for regulation retrieval."""

from fastapi import FastAPI
from pydantic import BaseModel

from colombia_health_rag import __version__

app = FastAPI(title="Colombian Health Regulations RAG", version=__version__)


class Health(BaseModel):
    """Health check response."""

    status: str
    version: str


@app.get("/health")
def health() -> Health:
    """Report that the service is up."""
    return Health(status="ok", version=__version__)
