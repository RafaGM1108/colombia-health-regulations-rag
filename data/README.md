# Data layers

Data moves through numbered layers. Each layer is produced only from the layers
before it, by code in `src/`, so any layer can be rebuilt from `01_raw`.

| Layer | Contents | Written by |
|-------|----------|------------|
| `01_raw` | Data exactly as received or scraped. **Immutable: never edit, overwrite or clean in place.** | Ingestion code / manual download |
| `02_intermediate` | Raw data parsed into a typed, consistent format (e.g. Parquet), with no business logic. | `ds_project.data` |
| `03_primary` | Cleaned, validated, domain-level tables (one row = one entity). | `ds_project.data` |
| `04_feature` | Engineered features, keyed by entity. | `ds_project.features` |
| `05_model_input` | Features joined and split into train/validation/test sets. | Feature pipeline |
| `06_models` | Trained, serialised models. | Training pipeline |
| `07_model_output` | Predictions and scores from the models. | Inference pipeline |
| `08_reporting` | Metrics (JSON/CSV) and figures (PNG) used in the README and reports. | Training / reporting code |

## Rules

- `01_raw` is read-only. If raw data is wrong, fix it in `02_intermediate`.
- Paths are set in `conf/base.yaml`. Code never hard-codes them.
- Only small, redistributable samples (`*_sample.*`) and `08_reporting/` are committed.
  Everything else is ignored by git.
- Each source's origin, license and download date is recorded below.

## Sources

| Source | License | Retrieved | Notes |
|--------|---------|-----------|-------|
| TODO | TODO | TODO | TODO |
