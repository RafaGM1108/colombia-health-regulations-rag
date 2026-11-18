"""Privacy-bounded entry points shared by the API and the chat UI.

Input contract:
- Generation sends text to an external API, so it accepts only the ID of a reviewed public
  question from the fixed evaluation set. Free-form text never reaches the external API.
- Search runs locally (embedding model and index on this machine) and accepts a short
  free-form query. Queries are neither stored nor logged.
"""

import threading
from collections.abc import Callable
from pathlib import Path

from colombia_health_rag.evaluation.questions import Question, load_questions
from colombia_health_rag.indexing.embeddings import Encoder, normalize_text
from colombia_health_rag.indexing.vector_index import SearchHit
from colombia_health_rag.serving.generation import (
    Answer,
    AnthropicGenerator,
    TextGenerator,
    answer_from_index,
    api_key_from_env,
    open_article_index,
    retrieve,
)

MAX_QUERY_CHARS = 300
SEARCH_RESULTS = 5


class UnknownQuestionError(LookupError):
    """The requested ID is not a reviewed public question."""


class GenerationUnavailableError(RuntimeError):
    """No API key is configured, so cited answers cannot be generated."""


def _default_generator(root: Path) -> TextGenerator:
    api_key = api_key_from_env(root)
    if not api_key:
        raise GenerationUnavailableError("ANTHROPIC_API_KEY is not configured")
    return AnthropicGenerator(api_key)


class RegulationService:
    """Load the verified index once and expose only the permitted operations."""

    def __init__(
        self,
        root: Path,
        *,
        open_index: Callable[[Path], tuple[str, Path, Encoder]] = open_article_index,
        make_generator: Callable[[Path], TextGenerator] = _default_generator,
    ) -> None:
        """Validate the reviewed question set now; load the index on first use."""
        self.root = root
        question_set = load_questions(
            root / "data/06_evaluation/questions.json", root / "data/manifest.json"
        )
        self._questions = {item.id: item for item in question_set.questions}
        self._open_index = open_index
        self._make_generator = make_generator
        self._index: tuple[Path, Encoder] | None = None
        self._generator: TextGenerator | None = None
        self._lock = threading.Lock()

    def public_questions(self) -> list[Question]:
        """Return the reviewed public questions that may be sent for generation."""
        return list(self._questions.values())

    def _loaded_index(self) -> tuple[Path, Encoder]:
        with self._lock:
            if self._index is None:
                _, index_dir, encoder = self._open_index(self.root)
                self._index = (index_dir, encoder)
            return self._index

    def search(self, query: str) -> list[SearchHit]:
        """Retrieve official passages locally; the query is not stored, logged, or sent."""
        text = normalize_text(query)
        if not 3 <= len(text) <= MAX_QUERY_CHARS:
            raise ValueError(f"Query must have between 3 and {MAX_QUERY_CHARS} characters")
        index_dir, encoder = self._loaded_index()
        return retrieve(text, index_dir, encoder, k=SEARCH_RESULTS)

    def answer(self, question_id: str) -> tuple[Question, Answer]:
        """Generate a cited answer for a reviewed public question, never for free text."""
        question = self._questions.get(question_id)
        if question is None:
            raise UnknownQuestionError(question_id)
        with self._lock:
            if self._generator is None:
                self._generator = self._make_generator(self.root)
            generator = self._generator
        index_dir, encoder = self._loaded_index()
        return question, answer_from_index(question.question, index_dir, encoder, generator)
