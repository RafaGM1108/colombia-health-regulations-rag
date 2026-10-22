# Notebooks

Notebooks are for exploration and narrative. Reusable logic belongs in `src/ds_project`
and is imported here.

| Folder | Stage |
|--------|-------|
| `1-data` | Getting data in: sources, loading, first sanity checks |
| `2-exploration` | EDA: distributions, missing values, data quality |
| `3-analysis` | Answering specific questions and hypotheses |
| `4-feat_eng` | Designing and checking features |
| `5-models` | Training, comparing and tuning models |
| `6-interpretation` | Explaining models: importances, errors, fairness |
| `7-deploy` | Checking the API/app and inference in practice |
| `8-reports` | Final figures and narrative for reporting |

## Conventions

- Start from `_template.ipynb`.
- Name files `<stage>.<seq>-<initials>-<short-description>.ipynb`, for example
  `2.01-rgm-target-distribution.ipynb`.
- Load paths with `from ds_project.utils.config import get_config`, never with hard-coded paths.
- Save figures and metrics for reports to `data/08_reporting/`.
- Restart the kernel and run all cells before committing.
