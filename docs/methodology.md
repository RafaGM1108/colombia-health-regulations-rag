# Methodology

## Data layers

Data flows `01_raw → 02_intermediate → 03_primary → 04_feature → 05_model_input →
06_models → 07_model_output → 08_reporting`. Raw data is immutable. See `data/README.md`.

## Pipelines

| Pipeline | Command | Reads | Writes |
|----------|---------|-------|--------|
| Feature | `make feature` | `01_raw` | `05_model_input` |
| Training | `make train` | `05_model_input` | `06_models`, `08_reporting` |
| Inference | `make infer` | `06_models` + new data | `07_model_output` |

## Notebook stages

`1-data → 2-exploration → 3-analysis → 4-feat_eng → 5-models → 6-interpretation →
7-deploy → 8-reports`. See `notebooks/README.md`.
