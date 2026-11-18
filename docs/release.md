# Release checklist: v1.0.0

Work through this list on `main` before tagging. Each item names the command or file that shows it is done.

## Code and checks

- [ ] CI is green on the release commit: lockfile, formatting, lint, types, tests with coverage, documentation, static security scan, and committed-file secrets.
- [ ] `make lint typecheck test` passes locally with the four official PDFs present, so the official-layout parsing tests run instead of being skipped.
- [ ] No open pull request or issue is labelled for the v1.0.0 milestone.

## Data and provenance

- [ ] `make corpus-check` reports every source as `unchanged`. If a PDF changed, record it through the [refresh procedure](data.md) and rerun the evaluation instead of releasing stale figures.
- [ ] `data/manifest.json`, `data/reviews/`, and `data/06_evaluation/questions.json` contain only official public material; no patient or personal data is tracked anywhere in the repository.

## Results

- [ ] `make embeddings`, `make index`, and `make evaluate` reproduce `data/07_reporting/retrieval-v1.json` without changes.
- [ ] `make score-answers` reproduces `data/07_reporting/answer-quality-v1.json` without changes.
- [ ] The README tables match those files (`tests/test_readme_results.py`), and the README and [Methodology](methodology.md) state the known limits and the grader disclosure.
- [ ] The generation model in `serving/generation.py` is the one reported as current in the README.

## Interface and policy

- [ ] `make api` and `make app` start against the local index; `/answers` rejects free text and the chat shows the informational-only disclaimer.
- [ ] The [input contract](interface.md) matches the implemented endpoints and UI.

## Release

- [ ] Set `version = "1.0.0"` in `pyproject.toml` and `__version__` in `src/colombia_health_rag/__init__.py`; run `uv lock` so the lockfile records the version.
- [ ] Move the `[Unreleased]` entries in `CHANGELOG.md` under `[1.0.0] - <release date>` and leave a new empty `[Unreleased]` section.
- [ ] Merge the release pull request, then tag the merge commit `v1.0.0` and publish a GitHub release whose notes summarize the CHANGELOG entry and link the results.
