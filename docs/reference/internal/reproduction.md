# Reproduction

Where every byte of `artifacts/fires_enriched.parquet` comes from, and how to reproduce it.
The per-source detail is in `data-sources.md` and the caveats in `known-caveats.md`.

## Steps

```sh
uv sync         # or: make sync; build .venv from uv.lock (pinned deps)
make download   # raw snapshot -> data/raw/ + MANIFEST.json checksums
make all        # stages s01-s09 -> artifacts/fires_enriched.parquet
make smoke      # synthetic end-to-end + determinism check (no network)
```

Dependencies are managed with [uv](https://docs.astral.sh/uv/): `pyproject.toml` declares exact-pinned direct dependencies and `uv.lock` pins the full transitive closure.
The `make` targets invoke stages via `uv run`, so `uv sync` is the only setup step.

## Reproducibility Contract

Given the same raw snapshot on the same platform, `make all` produces a byte-identical artifact.
Each stage verifies its inputs against `data/raw/MANIFEST.json` before reading them.

Upstream sources drift: NCEI overwrites nClimDiv files monthly, and hub exports and the GSOM API are live.
The checksummed snapshot, not the URLs, therefore defines the dataset, and `download.py` refuses to silently re-pin a drifted file.

macOS is the reference platform.
A Linux rebuild from the same snapshot is expected to differ from the reference in the trailing digits of geometry-derived floats (`area_km2`, `perimeter_km`, `vertices_per_km`, centroids); counts, nulls, coverage and flags match.
Same-platform determinism was verified on Linux on 2026-07-02 (two clean rebuilds, identical hash); a macOS double rebuild has not been run.

- Reference artifact sha256: `b3b0f3ad4db97734cab1fdb672d1e23c2e240c16682b262a1fba88ff71a7ab3e`
- Built on: macOS, 2026-07-03, from the 2026-07-03 manifest
- Artifact rows: 23,205 (fires 1878 to 2025)
- Built with: Python 3.11.15, pinned package versions in `pyproject.toml` / `uv.lock`
- Full per-file checksums: `data/raw/MANIFEST.json` (committed)
- QC detail: `data/processed/s09_qc_report.md` (committed)

The artifact parquet is gitignored and distributed out-of-band; verify a copy against the sha256 in the QC report.
