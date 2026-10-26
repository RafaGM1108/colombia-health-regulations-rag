PACKAGE := colombia_health_rag
export UV_CACHE_DIR := .uv-cache

.PHONY: help install lint typecheck test coverage security corpus-check embeddings index evaluate app api docs docs-check clean

help:  ## Show this help
	@grep -E '^[a-z]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

install:  ## Install locked dependencies
	uv sync --frozen

lint:  ## Lint, check formatting and run the security scan
	uv run --frozen ruff format --check src tests
	uv run --frozen ruff check src tests
	uv run --frozen python -m colombia_health_rag.ingestion.manifest
	uv run --frozen bandit -c pyproject.toml -r src -q
	$(MAKE) docs-check
	$(MAKE) security

typecheck:  ## Static type checking
	uv run --frozen mypy

test:  ## Run the test suite with coverage and JUnit reports
	uv run --frozen pytest --cov --cov-report=term --cov-report=xml --junitxml=report.xml

coverage:  ## Run tests with a coverage report (terminal + htmlcov/)
	uv run --frozen pytest --cov --cov-report=term --cov-report=html

security:  ## Check committed files for secrets
	uv run --frozen detect-secrets-hook --baseline .secrets.baseline $$(git ls-files | grep -v '^.secrets.baseline$$')

corpus-check:  ## Compare official PDFs with the source manifest (requires curl and network)
	uv run --frozen python -m colombia_health_rag.ingestion.refresh check

embeddings:  ## Build local embeddings from reviewed official passages
	uv run --frozen --group embeddings python -m colombia_health_rag.indexing.embeddings

index:  ## Build a local provenance-aware search index from embedding batches
	uv run --frozen python -m colombia_health_rag.indexing.vector_index

evaluate:  ## Compare article-aware and fixed-window retrieval on the frozen Q&A set
	uv run --frozen --group embeddings python -m colombia_health_rag.evaluation.retrieval

app:  ## Launch the Streamlit app
	uv run --frozen streamlit run src/$(PACKAGE)/app/main.py

api:  ## Launch the FastAPI service with auto-reload
	uv run --frozen uvicorn $(PACKAGE).api.main:app --reload

docs:  ## Serve the documentation locally
	uv run --frozen mkdocs serve

docs-check:  ## Build documentation with strict link validation
	uv run --frozen mkdocs build --strict

clean:  ## Remove caches and build artifacts
	rm -rf .mypy_cache .pytest_cache .ruff_cache htmlcov .coverage coverage.xml site dist build
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
