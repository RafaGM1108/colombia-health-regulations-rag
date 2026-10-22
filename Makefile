PACKAGE := ds_project

.PHONY: help install lint typecheck test coverage feature train infer app api docs clean

help:  ## Show this help
	@grep -E '^[a-z]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

install:  ## Install all dependencies and the pre-commit hooks
	uv sync
	uv run pre-commit install

lint:  ## Lint, check formatting and run the security scan
	uv run ruff check .
	uv run ruff format --check .
	uv run bandit -c pyproject.toml -r src -q

typecheck:  ## Static type checking
	uv run mypy

test:  ## Run the test suite
	uv run pytest

coverage:  ## Run tests with a coverage report (terminal + htmlcov/)
	uv run pytest --cov --cov-report=term --cov-report=html

feature:  ## Run the feature pipeline
	uv run python -m $(PACKAGE).pipelines.feature_pipeline

train:  ## Run the training pipeline
	uv run python -m $(PACKAGE).pipelines.training_pipeline

infer:  ## Run the inference pipeline
	uv run python -m $(PACKAGE).pipelines.inference_pipeline

app:  ## Launch the Streamlit app
	uv run streamlit run src/$(PACKAGE)/app/main.py

api:  ## Launch the FastAPI service with auto-reload
	uv run uvicorn $(PACKAGE).api.main:app --reload

docs:  ## Serve the documentation locally
	uv run mkdocs serve

clean:  ## Remove caches and build artifacts
	rm -rf .mypy_cache .pytest_cache .ruff_cache htmlcov .coverage coverage.xml site dist build
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
