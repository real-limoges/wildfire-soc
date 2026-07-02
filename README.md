# wildfire-soc — California wildfire dataset with climate covariates

A reproducible pipeline that produces **`artifacts/fires_enriched.parquet`**:
CAL FIRE FRAP historical fire perimeters (pinned release, see PROVENANCE.md),
cleaned, deduplicated, quality-flagged, and joined with NOAA monthly climate
covariates (PDSI drought index, temperature, precipitation, wind) by climate
division and alarm month.

**No statistics or modeling here** — this repo stops at a documented dataset.

## The three documents that matter

| File | What it tells you |
|---|---|
| `artifacts/SCHEMA.md` | Every column, every cleaning decision (with a pointer to the code that implements it), every known gap. Read this before using the data. |
| `PROVENANCE.md` | Exactly which upstream data releases were used, from which URLs, with checksums. |
| `NOTES.md` | Running working log of how decisions were reached. |

## Layout

```
data/raw/        untouched upstream downloads (gitignored; re-fetch with `make download`)
data/processed/  intermediate stage outputs (gitignored; rebuilt by `make all`)
artifacts/       fires_enriched.parquet + SCHEMA.md  (the deliverable)
pipeline/        download step + discrete, individually re-runnable stages
```

## Reproducing

```sh
pip install -r requirements.txt
make download   # network: fetch pinned raw inputs into data/raw/
make all        # deterministic: data/raw/ -> artifacts/fires_enriched.parquet
```

`make all` runs the stages in dependency order and finishes with a validation
stage (s09) that hard-fails on integrity violations and writes a QC report to
`data/processed/s09_qc_report.md`.

To re-run one stage after changing a decision, e.g. the dedupe rules:

```sh
make s03        # re-runs s03 only; downstream stages rebuild on next `make all`
```

## Stages

| Stage | Module | Does |
|---|---|---|
| s01 | `pipeline/stages/s01_extract_fires.py` | Extract FRAP layer from the gdb, repair invalid geometries |
| s02 | `pipeline/stages/s02_clean_fires.py` | Types, dates, code→label mappings, area cross-check (drops nothing) |
| s03 | `pipeline/stages/s03_dedupe_fires.py` | Duplicate detection + canonical selection; removed rows kept in a side table |
| s04 | `pipeline/stages/s04_quality_flags.py` | Era / size-cutoff / coarse-geometry flags for FRAP's known issues |
| s05 | `pipeline/stages/s05_assign_division.py` | Assign each fire to a NOAA climate division |
| s06 | `pipeline/stages/s06_build_climdiv.py` | Parse nClimDiv monthly PDSI/temp/precip for CA |
| s07 | `pipeline/stages/s07_build_wind.py` | Division-month wind from GSOM station files |
| s08 | `pipeline/stages/s08_join_enrich.py` | Join fires × climate → `artifacts/fires_enriched.parquet` |
| s09 | `pipeline/stages/s09_validate.py` | Hard integrity checks + QC report |
