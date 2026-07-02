# Reproducible build for artifacts/fires_enriched.parquet
#
#   make download   fetch raw inputs into data/raw/ (network; run once)
#   make all        rebuild everything from data/raw/ deterministically
#   make sNN        re-run a single stage (and nothing upstream of it)
#   make clean      remove processed outputs + artifact (keeps data/raw/)
#
# Stages are plain python modules under pipeline/stages/ — each one is
# independently re-runnable and documents the decisions it implements.

PY := python3
P := data/processed
A := artifacts

.PHONY: all download clean smoke s01 s02 s03 s04 s05 s06 s07 s08 s09

smoke:
	$(PY) -m tests.smoke_test

all: s09

download:
	$(PY) -m pipeline.download

# --- fire perimeter chain ---------------------------------------------------
$(P)/s01_fires_raw.parquet: pipeline/stages/s01_extract_fires.py pipeline/config.py
	$(PY) -m pipeline.stages.s01_extract_fires

$(P)/s02_fires_clean.parquet: $(P)/s01_fires_raw.parquet pipeline/stages/s02_clean_fires.py
	$(PY) -m pipeline.stages.s02_clean_fires

$(P)/s03_fires_deduped.parquet: $(P)/s02_fires_clean.parquet pipeline/stages/s03_dedupe_fires.py
	$(PY) -m pipeline.stages.s03_dedupe_fires

$(P)/s04_fires_flagged.parquet: $(P)/s03_fires_deduped.parquet pipeline/stages/s04_quality_flags.py
	$(PY) -m pipeline.stages.s04_quality_flags

$(P)/s05_fires_with_division.parquet: $(P)/s04_fires_flagged.parquet pipeline/stages/s05_assign_division.py
	$(PY) -m pipeline.stages.s05_assign_division

# --- climate chain -----------------------------------------------------------
$(P)/s06_climdiv_monthly.parquet: pipeline/stages/s06_build_climdiv.py pipeline/config.py
	$(PY) -m pipeline.stages.s06_build_climdiv

$(P)/s07_wind_monthly.parquet: pipeline/stages/s07_build_wind.py pipeline/config.py
	$(PY) -m pipeline.stages.s07_build_wind

# --- join + validate ----------------------------------------------------------
$(A)/fires_enriched.parquet: $(P)/s05_fires_with_division.parquet $(P)/s06_climdiv_monthly.parquet $(P)/s07_wind_monthly.parquet pipeline/stages/s08_join_enrich.py
	$(PY) -m pipeline.stages.s08_join_enrich

$(P)/s09_qc_report.md: $(A)/fires_enriched.parquet pipeline/stages/s09_validate.py
	$(PY) -m pipeline.stages.s09_validate

s01: $(P)/s01_fires_raw.parquet
s02: $(P)/s02_fires_clean.parquet
s03: $(P)/s03_fires_deduped.parquet
s04: $(P)/s04_fires_flagged.parquet
s05: $(P)/s05_fires_with_division.parquet
s06: $(P)/s06_climdiv_monthly.parquet
s07: $(P)/s07_wind_monthly.parquet
s08: $(A)/fires_enriched.parquet
s09: $(P)/s09_qc_report.md

clean:
	rm -rf $(P) $(A)/fires_enriched.parquet
