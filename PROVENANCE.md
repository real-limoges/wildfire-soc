# PROVENANCE — exact upstream sources

Machine-readable copy: `data/raw/MANIFEST.json` (written by `make download`).
Checksums below are SHA-256 of the files as downloaded.

> STATUS: skeleton — checksums, exact versioned filenames, and download
> timestamps are filled in by the download step. Anything marked TBD has
> not been fetched yet.

## 1. CAL FIRE FRAP historical fire perimeters — release `fire25_1`

- Publisher: California Department of Forestry and Fire Protection,
  Fire and Resource Assessment Program (FRAP)
- Release: **fire25_1**, published April 2026. Adds 516 fires from the 2025
  season plus 11 late-arriving 2016–2024 fires; removes one duplicate
  (1984 HURRICANE); moves one controlled burn to the rxburn dataset;
  introduces a GlobalID unique key.
- Landing page: https://www.fire.ca.gov/what-we-do/fire-resource-assessment-program/fire-perimeters
- Download URL: TBD
- File: TBD (`fire25_1.gdb.zip`), layer `firep25_1`
- SHA-256: TBD
- Downloaded: TBD (UTC)
- License/terms: public domain-style open data published by the State of
  California; see landing page.

## 2. NOAA nClimDiv monthly divisional data (drought, temperature, precipitation)

- Publisher: NOAA National Centers for Environmental Information (NCEI)
- Dataset: U.S. Climate Divisional Database (nClimDiv), monthly, by climate
  division. California = state code 04, divisions 1–7.
- Base URL: https://www.ncei.noaa.gov/pub/data/cirs/climdiv/
- Files (upstream names are versioned & dated; saved locally under stable names):
  - `climdiv-pdsidv.txt` ← TBD — Palmer Drought Severity Index
  - `climdiv-tmpcdv.txt` ← TBD — monthly mean temperature (°F)
  - `climdiv-tmaxdv.txt` ← TBD — monthly mean daily-max temperature (°F)
  - `climdiv-pcpndv.txt` ← TBD — monthly precipitation (inches)
- SHA-256: TBD (see MANIFEST.json)
- Downloaded: TBD
- Note: nClimDiv values for recent months are subject to upstream revision;
  the checksums pin exactly what this artifact was built from.

## 3. NOAA climate division boundaries

- File: `CONUS_CLIMATE_DIVISIONS.shp.zip` from the same climdiv directory
- SHA-256: TBD
- Used to assign fires (and wind stations) to divisions.

## 4. NOAA GSOM station monthly summaries (wind)

- Publisher: NOAA NCEI, Global Summary of the Month (GSOM)
- Base URL: https://www.ncei.noaa.gov/data/gsom/access/
- Station selection: deterministic rule implemented in
  `pipeline/download.py:select_wind_stations` — US GHCN stations in
  California whose AWND (average wind) record starts ≤ 1990 and extends
  ≥ 2024, per `ghcnd-inventory.txt`. Selected station list: TBD.
- Station metadata: `ghcnd-stations.txt`, `ghcnd-inventory.txt` from
  https://www.ncei.noaa.gov/pub/data/ghcn/daily/
- SHA-256 per station file: see MANIFEST.json
- Downloaded: TBD

## 5. Build environment

- OS / Python / library versions: TBD (recorded at build time)
