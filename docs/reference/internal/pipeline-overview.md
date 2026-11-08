# Pipeline Overview

The repo is a reproducible data pipeline that produces `artifacts/fires_enriched.parquet`.
That artifact is CAL FIRE FRAP fire perimeters (pinned release **fire25_1**), cleaned and deduplicated, then joined with NOAA climate covariates: PDSI, temperature and precipitation by nClimDiv division-month, and wind from GSOM stations.
The repo is dataset and docs only; it contains no analysis.

## Stages

Each stage is a module under `pipeline/`, runnable as `python -m pipeline.<module>` and chained by `pipeline/run_all.py`.

| Stage | Module | Does |
|---|---|---|
| `s01` | `s01_extract` | Read the raw FRAP layer |
| `s02` | `s02_clean` | Column normalization, midnight-UTC date parsing, cause decoding, `make_valid` geometry repair, reprojection to EPSG:3310 |
| `s03` | `s03_dedup` | Near-duplicate collapse on (year, normalized name, alarm date), keeping the largest `gis_acres` |
| `s04` | `s04_geom_metrics` | Area, perimeter, vertex density, coarse-geometry flag (below 3.0 vertices/km) |
| `s05` | `s05_divisions` | Fire to climate division: representative point, else nearest within 25 km, else null |
| `s06` | `s06_climdiv` | Fixed-width nClimDiv parse with per-element sentinels |
| `s07` | `s07_gsom` | GSOM station wind to division-month mean |
| `s08` | `s08_join` | Left-join climate onto fires by alarm month |
| `s09` | `s09_finalize` | Deterministic output (fixed sort, columns, compression, no timestamps) and QC report |

All I/O lives under `data/{raw,interim,processed}` and `artifacts/`, redirectable via `PIPELINE_DATA_ROOT`.
The smoke test (`scripts/smoke_pipeline.py`, fixtures in `tests/fixtures/pipeline/`) uses that variable to isolate itself.

## Related Reference

- `reproduction.md`: how to rebuild and what the reproducibility contract promises.
- `data-sources.md`: the four pinned inputs.
- `known-caveats.md`: limits a user of the artifact needs to know.
- `artifact-schema.md`: every column of the artifact.