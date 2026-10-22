# TODO: Project title

[![CI](https://github.com/RafaGM1108/ds-project/actions/workflows/ci.yml/badge.svg)](https://github.com/RafaGM1108/ds-project/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/RafaGM1108/ds-project/graph/badge.svg)](https://codecov.io/gh/RafaGM1108/ds-project)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

> TODO: one-sentence pitch: what problem this solves and for whom.

## Using this template

> Delete this section once the project is set up.

1. On GitHub, click **Use this template → Create a new repository**, then clone it.
2. Rename the placeholder package. Everything that needs renaming is spelled
   `ds_project` (Python package), `ds-project` (distribution / repo name, used in URLs) or
   `DS_PROJECT` (environment variable prefix). On Linux:

   ```bash
   PKG=rent_predictor        # snake_case package name
   REPO=rent-price-predictor # GitHub repo name
   git mv src/ds_project "src/$PKG"
   grep -rlE 'ds_project|ds-project|DS_PROJECT' --exclude-dir={.git,.venv} . \
     | xargs sed -i "s/ds_project/$PKG/g; s/ds-project/$REPO/g; s/DS_PROJECT/${PKG^^}/g"
   uv lock
   make install
   make lint typecheck test
   ```

   On macOS use `sed -i ''` instead of `sed -i`.
3. Fill in every `TODO` (`grep -rn TODO .`), starting with this README and the
   **Project** section of `CLAUDE.md`.
4. Create the labels (they are not copied from the template): `type:feat`, `type:data`,
   `type:analysis`, `type:model`, `type:docs`, `type:test`, `type:ci`, `type:bug` and `phase`.
5. Create the GitHub Project (Backlog, Ready, In Progress, In Review, Done, plus
   **Priority** and **Size** fields), link it to the repo, and create one milestone per
   roadmap phase.
6. Make sure the [Codecov GitHub App](https://github.com/apps/codecov) has access to the
   repo. Uploads authenticate with OIDC, so no token secret is needed.

## Overview

TODO: what the project does, in two or three sentences.

## Motivation

TODO: why this problem matters and who benefits.

## Data

TODO: sources, size, time span, license and how the data was collected. Full details are in
[`data/README.md`](data/README.md).

## Approach

TODO: the method, from raw data to model to deployment.

1. TODO
2. TODO
3. TODO

## Results

TODO: results go here **only** after an actual run. Every number and figure must come
from a file in [`data/08_reporting/`](data/08_reporting/).

| Metric | Value | Source |
|--------|-------|--------|
| TODO | TODO | `data/08_reporting/TODO.json` |

## Project structure

```text
├── conf/base.yaml          # Paths and parameters
├── data/                   # Layered data (01_raw … 08_reporting), see data/README.md
├── docs/                   # MkDocs Material site
├── notebooks/              # Numbered by stage (1-data … 8-reports), see notebooks/README.md
├── src/ds_project/
│   ├── data/               # Loading and cleaning
│   ├── features/           # Feature engineering
│   ├── model/              # Training and evaluation
│   ├── inference/          # Prediction logic
│   ├── pipelines/          # feature_pipeline, training_pipeline, inference_pipeline
│   ├── api/                # FastAPI service
│   ├── app/                # Streamlit app
│   └── utils/              # Config loader and logging
├── tests/                  # Mirrors src/
├── Dockerfile              # Multi-stage image for the API
└── Makefile                # Common commands (make help)
```

## Quickstart

Requires [uv](https://docs.astral.sh/uv/) and `make`.

```bash
git clone https://github.com/RafaGM1108/ds-project.git
cd ds-project
make install                 # dependencies + pre-commit hooks
cp .env.example .env         # then fill in secrets, if any
make lint typecheck test     # check everything works
```

| Command | What it does |
|---------|--------------|
| `make feature` / `make train` / `make infer` | Run the pipelines |
| `make api` | FastAPI on http://localhost:8000 (docs at `/docs`) |
| `make app` | Streamlit on http://localhost:8501 |
| `make coverage` | Tests with an HTML coverage report |
| `make docs` | Serve the documentation locally |

Docker (API):

```bash
docker build -t ds-project .
docker run --rm -p 8000:8000 ds-project
```

## Roadmap

| Phase | Milestone | Status |
|-------|-----------|--------|
| 1 | TODO: Phase 1 - Data collection | ⬜ |
| 2 | TODO: Phase 2 - Exploration | ⬜ |
| 3 | TODO: Phase 3 - Modelling | ⬜ |
| 4 | TODO: Phase 4 - Deployment | ⬜ |

## Tech stack

Python 3.12 · uv · pandas (TODO) · scikit-learn (TODO) · FastAPI · Streamlit · pytest ·
ruff · mypy · bandit · pre-commit · GitHub Actions · Docker · MkDocs Material

## Author

**Rafael E. Garcia**

- GitHub: [@RafaGM1108](https://github.com/RafaGM1108)
- LinkedIn: [linkedin.com/in/rafaelgarcia11](https://www.linkedin.com/in/rafaelgarcia11)

Licensed under the [MIT License](LICENSE).
