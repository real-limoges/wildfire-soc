# SCHEMA — artifacts/fires_enriched.parquet

> STATUS: DRAFT — row counts and coverage statistics marked `TBD` are filled
> from the QC report once the real data build completes. Everything else
> (fields, decisions, caveats) is final pipeline behavior, verified by
> `tests/smoke_test.py`.

One row per **canonical wildfire perimeter** in California, 1878–2025, from
CAL FIRE FRAP release `fire25_1` (see PROVENANCE.md), enriched with NOAA
monthly climate covariates for the fire's climate division and alarm month.

- Rows: TBD (of TBD source features; TBD removed as duplicates — every
  removed row is preserved with its reason in
  `data/processed/s03_duplicates_removed.parquet`)
- Grain: one row per fire perimeter (not per fire-day, not per agency report)
- Primary key: `fire_id` (unique, non-null; enforced by s09 check V-01)

Read this document top to bottom before using the data; the **Caveats**
section is not optional reading. Decision tags like `D-03b` point at the
stage module and named constant that implement them — e.g. D-03b is in
`pipeline/stages/s03_dedupe_fires.py` and its thresholds are
`DUP_IOU_THRESHOLD` / `DUP_CONTAINMENT` in `pipeline/config.py`.

---

## 1. Identity fields

| Column | Type | Description |
|---|---|---|
| `fire_id` | string | Primary key. FRAP `GlobalID` (introduced in fire25_1), braces stripped, lowercased. Decision D-02h (`s02_clean_fires.py`). |
| `src_objectid` | int | OBJECTID of the source feature in the fire25_1 gdb — the row's address in the upstream release. |
| `fire_name` | string | Fire name as published (whitespace-trimmed only). |
| `fire_name_norm` | string | Uppercased, whitespace-collapsed name used for duplicate matching (D-02f). Not unique — many distinct fires share names. |
| `complex_name` | string | Complex the fire belonged to, if any. |
| `irwin_id` | string | IRWIN incident GUID (normalized lowercase, no braces) where present (post-~2014 fires mostly). |
| `inc_num` | string | Agency incident number. Not unique. |
| `agency` | string | Agency that submitted the perimeter (CDF=CAL FIRE, USF=US Forest Service, etc. — see FRAP data dictionary). |
| `unit_id` | string | Responsibility-area unit. |

## 2. Temporal fields

| Column | Type | Description |
|---|---|---|
| `fire_year` | int | Fire **season** year, from FRAP `YEAR_` — the authoritative year assignment (D-02a). Null only if `flag_bad_year`. |
| `alarm_date` | timestamp | Ignition/alarm date. Nulled (never guessed) when missing, unparseable, or outside 1878–2026 (D-02b). |
| `alarm_year`, `alarm_month` | int | Join keys derived from `alarm_date`, only when the date is usable (D-08a); null when `flag_no_alarm_month`. |
| `cont_date` | timestamp | Containment date, same validity rules (D-02b). |
| `duration_days` | int | `cont_date - alarm_date`; null when either date is missing or the pair is reversed (`flag_negative_duration`, D-02d). |

## 3. Attribute fields

| Column | Type | Description |
|---|---|---|
| `cause` | string | FRAP numeric cause code mapped to labels (LIGHTNING, ARSON, … UNKNOWN); unknown codes preserved as `UNKNOWN_CODE_<n>` (D-02e, table `CAUSE_LABELS` in `s02_clean_fires.py`). |
| `objective` | string | SUPPRESSION or RESOURCE_BENEFIT. Note: resource-benefit fires are managed wildfires — exclude them if you need "wildfire disasters" semantics. |
| `collection_method` | string | How the perimeter was captured (GPS_GROUND … UNKNOWN); a strong proxy for geometric quality era. |

## 4. Location fields

| Column | Type | Description |
|---|---|---|
| `climate_division` | int 1–7 | NOAA California climate division containing the fire's representative point (D-05a/b, `s05_assign_division.py`). |
| `rep_point_lon`, `rep_point_lat` | float | Representative point (guaranteed inside the perimeter), EPSG:4326. **Not** the centroid; chosen so concave/multipart fires still locate inside themselves (D-05b). |

Full polygon geometry is deliberately **not** in this artifact (D-08d) — it
lives in `data/processed/s05_fires_with_division.parquet` (GeoParquet,
EPSG:3310), joinable 1:1 on `fire_id`, rebuildable with `make s05`.

## 5. Size & geometry-quality fields

| Column | Type | Description |
|---|---|---|
| `gis_acres` | float | FRAP's published GIS-computed acreage — the value of record. |
| `acres_calc` | float | Area recomputed from the geometry in EPSG:3310 (equal-area). Cross-check only (D-02g). |
| `perimeter_km` | float | Perimeter length in EPSG:3310 km. |
| `n_vertices` | int | Vertex count of the polygon — with `perimeter_km`, lets you set your own generalization threshold. |

## 6. Climate covariates (NOAA)

All covariates describe the fire's `climate_division` in the fire's **alarm
month** (concurrent month — lag construction is left to analysis, D-08b).
Sources and exact file versions: PROVENANCE.md.

| Column | Type | Units | Source | Description |
|---|---|---|---|---|
| `pdsi` | float | unitless | nClimDiv `pdsidv` | Palmer Drought Severity Index (≈ -6 extreme drought … +6 extreme wet). |
| `tmean_c` | float | °C | nClimDiv `tmpcdv` | Monthly mean temperature (converted from °F at the parse boundary, D-06c). |
| `tmax_c` | float | °C | nClimDiv `tmaxdv` | Monthly mean of daily maximum temperature. |
| `precip_mm` | float | mm | nClimDiv `pcpndv` | Monthly total precipitation (converted from inches, D-06c). |
| `wind_avg_ms` | float | m/s | GSOM `AWND` | Mean of monthly-average wind speed across the division's reporting stations (D-07c). See wind caveat below. |
| `wind_n_stations` | int | count | GSOM | How many stations contributed to `wind_avg_ms` (null when no wind). |
| `flag_climate_missing` | string | — | s08 | Why covariates are null: `no_alarm_month`, `pre_1895` (before the nClimDiv record), or `not_covered`; null when joined (D-08c). |

## 7. Quality flags

All booleans, non-null. Nothing was dropped based on these — they exist so
*you* can choose a consistently observed subset.

| Column | Decision | Meaning |
|---|---|---|
| `flag_bad_year` | D-02a | `YEAR_` missing/out of range; `fire_year` is null. |
| `flag_alarm_date_invalid` | D-02b | Source alarm date was present but unusable → nulled. |
| `flag_cont_date_invalid` | D-02b | Same for containment date. |
| `flag_alarm_year_mismatch` | D-02c | Alarm date ≠ season year beyond ±1 yr; alarm date not trusted for the climate join. |
| `flag_negative_duration` | D-02d | Containment before alarm; `duration_days` nulled. |
| `flag_no_alarm_month` | D-04d | No usable alarm month → climate covariates null. |
| `flag_area_mismatch` | D-02g | Recomputed area differs from `gis_acres` by >10%. |
| `flag_pre_reliable_era` | D-04a | `fire_year` < 1950 (or unknown): the era FRAP itself flags as substantially incomplete. |
| `below_cutoff_timber` / `_brush` / `_grass` | D-04b | `gis_acres` below FRAP's modern inclusion cutoffs (10 / 30 / 300 acres). See size-cutoff caveat. |
| `flag_coarse_geometry` | D-04c | Vertex density < 1 vertex/km of perimeter — over-generalized (typically old hand-drawn) shape. |
| `flag_no_geometry` | D-05c | Source feature had no usable geometry. |
| `flag_division_nearest` | D-05c | Representative point fell outside all division polygons; snapped to nearest (distance in `division_snap_km` in the s05 table). |
| `geom_was_invalid` | s01 | Geometry failed OGC validity and was repaired with `make_valid` (shape unchanged, topology encoding fixed). |
| `dup_group_id` | D-03c | Non-null if this row survived a duplicate group; `n_duplicates_removed` says how many rows it absorbed. |

## 8. Cleaning decisions — index

Every decision is implemented at exactly one place:

| Tag | Where | One-line summary |
|---|---|---|
| D-02a…h | `pipeline/stages/s02_clean_fires.py` | Year/date validation, code→label maps, name normalization, area cross-check, primary key. |
| D-03a…d | `pipeline/stages/s03_dedupe_fires.py` | Duplicate candidates, geometric confirmation, canonical selection, removed-rows side table. |
| D-04a…d | `pipeline/stages/s04_quality_flags.py` | Era, size-cutoff, coarse-geometry, no-alarm-month flags. |
| D-05a…c | `pipeline/stages/s05_assign_division.py` | Region choice, representative point, nearest-snap. |
| D-06a…d | `pipeline/stages/s06_build_climdiv.py` | nClimDiv parsing, missing sentinels, unit conversions. |
| D-07a…e | `pipeline/stages/s07_build_wind.py` | Wind source, station→division, aggregation, coverage gap, unit sanity. |
| D-08a…d | `pipeline/stages/s08_join_enrich.py` | Join keys, concurrent-month covariates, missingness reasons, geometry exclusion. |
| Thresholds | `pipeline/config.py` | All numeric knobs (IoU, cutoffs, tolerances) as named constants. |

## 9. Known gaps and caveats — READ THIS

1. **The record is incomplete, and incompleteness is not random.** FRAP
   states the dataset is the most complete digital record available and
   *still* cautions against treating it as complete. Coverage improves
   dramatically over time. Fire *counts* over time confound real trends with
   reporting effort; do not compute naive counts across eras. Use
   `flag_pre_reliable_era` (and consider starting at 1950).
2. **Minimum-size reporting cutoffs vary by fuel type and era** (≈10 ac
   timber / 30 ac brush / 300 ac grass in the modern criteria — and looser
   historically). Since per-fire fuel type isn't recorded, small fires are
   inconsistently observed. For a consistently observed population, filter
   to `gis_acres >= 300` (`below_cutoff_grass == False`); the timber cutoff
   (≥10 ac) is the bare minimum. (D-04b)
3. **Duplicates were collapsed, not deleted from history.** TBD rows removed
   (see s03 side table). Detection requires geometric agreement, so
   same-name same-year fires in different places survive. Residual risk:
   duplicates with *different* names AND >meaningfully different geometry are
   undetectable by D-03 and may remain, especially pre-GPS. Complex fires may
   also appear both as members and as a complex-wide perimeter under
   different names — not collapsible without fire-level truth. (D-03)
4. **Old perimeters are over-generalized.** `flag_coarse_geometry`,
   `collection_method`, `n_vertices` are your tools. `gis_acres` from a
   hand-drawn 1920s perimeter is a rough estimate, not a measurement.
5. **Climate covariates are monthly division means, not fire-front
   weather.** A division is huge (CA has 7); a fire's actual microclimate,
   slope winds, or fire-generated weather are not represented. These are
   *covariates for regional conditions*, suitable for coarse conditioning,
   not for reconstructing fire behavior. (D-05a)
6. **Wind starts ~1984 and is thin.** nClimDiv has no wind; wind comes from
   TBD long-record airport stations (GSOM `AWND`), which exist mostly from
   the ASOS era. `wind_avg_ms` is null for TBD% of fires, non-randomly
   (older fires). Airport wind also under-represents ridgetop/canyon winds
   that drive fire spread. Use `wind_n_stations` to gauge support. (D-07d)
7. **Fires before 1895 have no climate covariates at all** — the nClimDiv
   record begins 1895 (`flag_climate_missing == 'pre_1895'`). (D-06d)
8. **Fires without a usable alarm date get null covariates**
   (`no_alarm_month`, TBD% of rows, concentrated in older records). Their
   season year is still valid; only the monthly join is impossible. (D-08a)
9. **A fire is assigned to exactly one division** by representative point,
   even if the perimeter crosses a division boundary. (D-05b)
10. **nClimDiv values are subject to upstream revision**; the artifact is
    pinned to the exact files (checksums in PROVENANCE.md), so a rebuild
    from a later NOAA download may differ slightly in covariates.
11. **`objective == RESOURCE_BENEFIT`** rows are managed fires, and FRAP
    also publishes prescribed burns *separately* (not included here);
    fire25_1 moved one record (1987 PEPPERTREE) out of the wildfire layer
    for this reason.

## 10. Regenerating

```sh
pip install -r requirements.txt
make download && make all    # see README.md
```

QC statistics backing the TBDs above: `data/processed/s09_qc_report.md`.
