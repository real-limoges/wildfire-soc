# Artifact Schema: `artifacts/fires_enriched.parquet`

## Overview

GeoParquet, geometry in **EPSG:3310** (NAD83 / California Albers, meters), snappy compression, one row per deduplicated fire perimeter, sorted by `fire_id`.
Null rates and per-column ranges below are from the reference build; the authoritative per-build numbers live in `data/processed/s09_qc_report.md`.

- Rows: 23,205
- Year range: 1878–2025 (77 fires have no recorded year)
- Artifact sha256: `b3b0f3ad4db97734cab1fdb672d1e23c2e240c16682b262a1fba88ff71a7ab3e` (the macOS reference build; see `reproduction.md`)
- FRAP release: `fire25_1`

## Identity

| Column | Type | Description |
|---|---|---|
| `fire_id` | `string` | Deterministic ID: first 12 hex chars of sha256 over `year\|fire_name_norm\|alarm_date\|src_row`. Unique; stable within release fire25_1 only, since it hashes `src_row`. |
| `src_row` | `int64` | 0-based row position in the raw FRAP layer (provenance back-reference). |

## Fire Attributes (from FRAP, Cleaned)

| Column | Type | Description |
|---|---|---|
| `year` | `Int64` | Fire year as recorded by FRAP (`YEAR_`). Null for 77 old records. |
| `state` | `string` | State code: `CA` 23,188, `NV` 11, `OR` 4, `AZ` 2 (border fires). |
| `agency` | `string` | Reporting agency code (e.g. `CDF`, `USF`, `BLM`). |
| `unit_id` | `string` | Responsibility-area unit code. |
| `fire_name` | `string` | Fire name as recorded; null for 28.4% (mostly pre-1950). |
| `fire_name_norm` | `string` | Uppercased, whitespace-collapsed name; empty string when unnamed (dedup key component). |
| `inc_num` | `string` | Incident number. |
| `irwin_id` | `string` | IRWIN incident GUID where present (15.6% of rows; modern fires). |
| `complex_name` | `string` | Complex name, if part of a complex (2.6%). |
| `complex_id` | `string` | Complex GUID, if part of a complex. |
| `alarm_date` | `timestamp` | Ignition/alarm date, normalized to midnight (null for 23.2%; source stamps are midnight-UTC instants). |
| `cont_date` | `timestamp` | Containment date, normalized to midnight (null for 54.0%). |
| `alarm_year` | `Int64` | Year of `alarm_date` (climate join key). |
| `alarm_month` | `Int64` | Month of `alarm_date` (climate join key). |
| `cause_code` | `Int64` | FRAP CAUSE domain code 1–19. |
| `cause_desc` | `string` | Decoded cause per the official domain table: 1 Lightning, 2 Equipment Use, 3 Smoking, 4 Campfire, 5 Debris, 6 Railroad, 7 Arson, 8 Playing with fire, 9 Miscellaneous, 10 Vehicle, 11 Electrical Power, 12 Firefighter Training, 13 Non-Firefighter Training, 14 Unknown/Unidentified, 15 Structure, 16 Aircraft, 17 Volcanic, 18 Escaped Prescribed Burn, 19 Illegal Alien Campfire. |
| `collection_method` | `Int64` | FRAP `C_METHOD` domain: 1 GPS Ground, 2 GPS Air, 3 Infrared, 4 Other Imagery, 5 Photo Interpretation, 6 Hand Drawn, 7 Mixed Collection Methods, 8 Unknown. |
| `objective_code` | `Int64` | FRAP `OBJECTIVE` domain: 1 Suppression (Wildfire), 2 Resource Benefit (WFU). |
| `gis_acres` | `float64` | GIS-computed acreage as published by FRAP. |

## Geometry and Metrics (Computed, EPSG:3310)

| Column | Type | Description |
|---|---|---|
| `geometry` | (Multi)Polygon | Perimeter, `make_valid`-repaired, reprojected from the source's EPSG:3857. |
| `area_km2` | `float64` | Polygon area / 10⁶. |
| `perimeter_km` | `float64` | Boundary length / 10³. |
| `n_vertices` | `int32` | Total coordinate count (4–117,172). |
| `vertices_per_km` | `float64` | `n_vertices / perimeter_km`; digitization density (median 27.4). |
| `coarse_geometry` | `bool` | `vertices_per_km < 3.0`: the empirical 1st percentile, i.e. average vertex spacing coarser than ~333 m. Flags 197 fires (0.85%). |
| `centroid_lon` / `centroid_lat` | `float64` | Centroid in EPSG:4326. |

Float columns derived from geometry are byte-identical only per platform: a Linux build differs from the macOS reference in their trailing digits.

## Climate Covariates

Keyed to the division-month of the alarm date.
Null when the fire has no division (1 row) or no alarm date (23.2%), **and also** when the division-month is absent from the source: nClimDiv sentinel months, and anything before the GSOM pull window (1980-01-01).
Pre-1980 fires therefore always have null `awnd_ms` (overall AWND coverage among joinable fires: 64.2%; nClimDiv covariates: 100%).

| Column | Type | Description |
|---|---|---|
| `division` | `Int64` | California nClimDiv climate division (1–7). |
| `division_assigned_nearest` | `bool` | True when assigned via the ≤25 km nearest-polygon fallback (42 rows). |
| `pdsi` | `float64` | Palmer Drought Severity Index (unitless; observed −8.7 to 8.87). |
| `tavg_degf` | `float64` | Division mean temperature, °F. |
| `precip_in` | `float64` | Division precipitation, inches. |
| `awnd_ms` | `float64` | Mean GSOM station wind speed in the division, m/s (metric data-service default, verified against GSOM docs and value distribution). |
| `awnd_n_stations` | `Int64` | Stations contributing to `awnd_ms` (1–31). |
