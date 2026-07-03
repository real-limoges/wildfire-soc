.PHONY: download all smoke pipeline-clean

PY ?= python3

# Fetch raw inputs and write data/raw/MANIFEST.json checksums.
download:
	$(PY) -m pipeline.download

# Run stages s01-s09 -> artifacts/fires_enriched.parquet (needs `make download` first).
all:
	$(PY) -m pipeline.run_all

# Full pipeline on synthetic fixtures + determinism check; no network needed.
smoke:
	$(PY) scripts/smoke_pipeline.py

pipeline-clean:
	rm -rf data/interim data/processed artifacts/fires_enriched.parquet
