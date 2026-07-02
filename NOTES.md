# NOTES — running log of decisions and progress

Working log for the fires_enriched pipeline. Newest entries at the bottom.
Final, polished documentation lives in PROVENANCE.md and artifacts/SCHEMA.md;
this file is the honest scratch record of how decisions were reached.

## 2026-07-02 — Session start, design

### Goal
`artifacts/fires_enriched.parquet`: cleaned, deduplicated CA wildfire perimeters
(CAL FIRE FRAP) joined with NOAA climate covariates by region + month.
No analysis/fitting — dataset + docs only.

### Source pinning
- **FRAP fire perimeters**: current release is **fire25_1** (published April 2026,
  adds 516 fires from the 2025 season; removed 1 duplicate — 1984 HURRICANE;
  added a GlobalID field). Confirmed via CAL FIRE fire-perimeters page (web search,
  2026-07-02). Pinning to fire25_1. Exact download URL + sha256 to be recorded in
  PROVENANCE.md once fetched.
- **NOAA nClimDiv** (monthly, by climate division; ncei.noaa.gov/pub/data/cirs/climdiv):
  PDSI (`climdiv-pdsidv*`), mean temp (`climdiv-tmpcdv*`), max temp (`climdiv-tmaxdv*`),
  precipitation (`climdiv-pcpndv*`). California = state code 04, divisions 1–7.
  Files carry a version+date suffix — pin the exact filenames downloaded.
- **NOAA climate division polygons**: `CONUS_CLIMATE_DIVISIONS.shp.zip` from the same
  climdiv directory — needed to assign each fire to a division.
- **Wind**: nClimDiv has *no* wind variable. Plan: NOAA GSOM (Global Summary of the
  Month) per-station CSVs (`ncei.noaa.gov/data/gsom/access/<GHCND id>.csv`), field
  `AWND` (avg wind speed). Select long-record CA stations (mostly airport ASOS),
  assign to divisions by point-in-polygon, division-month wind = mean over stations.
  KNOWN GAP: AWND is essentially absent before ~1984 (ASOS era) — wind covariates
  will be null for older fires. Document, don't fake.

### Join design
- Region = NOAA CA climate division (1–7) via fire *representative point*
  (guaranteed inside polygon, unlike centroid for concave/multipart shapes).
- Date = year+month of `ALARM_DATE`. Fires with missing/unusable alarm date get
  NULL climate covariates + an explicit flag (no imputation).

### Handling FRAP's known issues (explicit, not silent)
1. **Duplicates / near-duplicates**: group by (year, normalized name) + spatial
   overlap; pick one canonical record per group (best-attributed / largest),
   removed rows written to a side table with reasons, counts documented.
2. **Historical undercounting**: nothing is dropped by year; a `pre_1950` /
   era-reliability flag lets users filter. FRAP itself calls pre-1950 data least
   reliable.
3. **Minimum-size cutoffs varying by fuel type & era**: can't reconstruct fuel type
   per fire; instead ship size-class flags (incl. a "below any modern cutoff" flag)
   so users can restrict to a consistently-observed size class. Document FRAP's
   stated inclusion criteria in SCHEMA.md.
4. **Over-generalized old perimeters**: ship geometry-quality metrics
   (vertex count / density) + a coarse-geometry flag rather than editing shapes.

### Repo layout
- `data/raw/` untouched downloads (gitignored; checksums in PROVENANCE.md)
- `data/processed/` intermediate stage outputs (gitignored)
- `artifacts/fires_enriched.parquet` + `artifacts/SCHEMA.md` (committed)
- `pipeline/` discrete named stages, each independently re-runnable
  (`python -m pipeline.stages.s03_dedupe_fires`), orchestrated by Makefile;
  `make all` rebuilds everything from data/raw deterministically;
  `make download` (separate) fetches raw data.

### Environment hiccup
Bash tool safety classifier temporarily unavailable at session start — file writes
and web research still work; deferring shell checks (python libs, network) until it
recovers. WebFetch returns 403 for data.ca.gov / frap.fire.ca.gov / ncei.noaa.gov —
need to determine via proxy status endpoint whether that's egress policy or
tool-specific once shell is back.

### Drafted blind during the outage (to be validated against real data)
Entire pipeline scaffold written before any data was inspected: config.py,
download.py, stages s01–s09, Makefile, README, PROVENANCE skeleton. Every
FRAP-schema-dependent assumption (column names YEAR_/ALARM_DATE/GIS_ACRES/…,
CAUSE code table, gdb layer name firep25_1, climdiv fixed-width layout, GSOM
AWND units) is provisional until checked against the downloaded files —
expect and plan for a validation/fix pass. Verified release facts so far
(via web search only): fire25_1 published April 2026; adds 516 fires from
2025 season; removed dup 1984 HURRICANE; added GlobalID field.

### Environment confirmed (bootstrap probe, 2026-07-02 ~01:07 UTC)
- Python 3.11.15, 4 cpus, 32 GB free disk. No geo stack preinstalled →
  installed from PyPI (PyPI is proxy-exempt): geopandas 1.1.4, pyogrio 0.13.0,
  shapely 2.1.2, pandas 3.0.3, pyarrow 24.0.0, pyproj 3.7.2.
- **BLOCKER**: the sandbox egress policy denies CONNECT to every data host we
  need — www.ncei.noaa.gov, data.ca.gov, gis.data.ca.gov, frap.fire.ca.gov,
  services1.arcgis.com, opendata.arcgis.com (proxy status shows
  "gateway answered 403 to CONNECT (policy denial)"). GitHub + PyPI are open.
  Per proxy README this must be reported, not worked around → asked the user
  to widen the environment's network allowlist.

### Smoke test (2026-07-02)
Wrote tests/smoke_test.py: builds a synthetic FRAP gdb (OpenFileGDB via
pyogrio), fake 7-division shapefile, synthetic climdiv + GSOM files, runs
s01–s09 end to end, asserts every documented decision (dedupe canonical
choice, WKB-dup collapse, date/era/size/geometry flags, pre-1895 and
no-alarm-month climate-missing reasons, join values, wind coverage), then
rebuilds from scratch and asserts byte-identical artifact. PASSED after two
fixes: mkdir for gdb parent dir; s03 groupby indices were positional
(pandas .indices) → switched to label-based .groups (real bug caught in
review, would have mis-paired rows on the filtered frame).
