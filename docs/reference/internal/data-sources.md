# Data Sources

The four pinned inputs to `artifacts/fires_enriched.parquet`, with URL, checksum, license and the stages that consume each.
Full per-file checksums and retrieval times are in `data/raw/MANIFEST.json`; abbreviated hashes below are prefix…suffix of those.
The pinned snapshot was retrieved 2026-07-03 between 22:36Z and 23:49Z.

## Source 1: CAL FIRE FRAP Fire Perimeters (Release `fire25_1`)

- What: statewide historical wildland fire perimeters maintained by CAL FIRE's Fire and Resource Assessment Program (FRAP).
  Annual release fire25_1 was published April 2026 and adds 516 fires from the 2025 season.
  23,334 raw perimeters, single layer `California_Fire_Perimeters__all_`, EPSG:3857.
- URL: `https://gis.data.cnra.ca.gov/api/download/v1/items/c3c10388e3b24cec8a954ba10458039d/filegdb?layers=0`.
  This is the CNRA hub file-geodatabase export of CAL FIRE's AGOL item `c3c10388e3b24cec8a954ba10458039d` ("California Fire Perimeters (all)", layer 0), which carries the fire25_1 release data.
- **Deviation from the official file:** the canonical `fire25_1.gdb.zip` on fire.ca.gov sits behind a WAF that blocks automated fetches, so the hub export is the pinned source instead.
  Consequences: geometry arrives in Web Mercator (EPSG:3857, the hosted-service CRS) rather than FRAP-native EPSG:3310 and is reprojected in s02 (sub-meter round-trip effect); the export omits the prescribed-burn layer (unused here anyway).
  The hub regenerates exports server-side, so only the manifest sha256 pins the snapshot.
- sha256: `1bc7e1ef21014f5048631631b79d9db03e298201cf0d2bf9cbc4e5ed8e0bd68a` (45,719,838 bytes).
- License/terms: per the official "Wildland Fire Perimeter Metadata" PDF (AGOL item `a31aa1efe1d6466f8530b501c30ab00a`).
  No restrictions on distribution.
  Users must cite CAL FIRE (Department of Forestry and Fire Protection) as the original source and denote modifications.
  The State provides the data without warranty.
- Processing: s01 extract; s02 clean (column normalization, midnight-UTC date-stamp parsing, CAUSE decoding per the official domain table, `make_valid` repair of 408 invalid geometries, reprojection to EPSG:3310); s03 near-duplicate collapse (129 rows removed: rows sharing year, normalized name and alarm date, keeping the largest `gis_acres`); s04 geometry metrics.

## Source 2: NOAA nClimDiv Division-Month Climate

- What: monthly PDSI (`climdiv-pdsidv`), average temperature (`climdiv-tmpcdv`, °F), and precipitation (`climdiv-pcpndv`, inches) for California's 7 climate divisions (nClimDiv state code 04), 1895 to present.
- Base URL: https://www.ncei.noaa.gov/pub/data/cirs/climdiv/
- Pinned filenames (procdate 20260604).
  NCEI replaces these monthly and does not retain old versions, so the manifest checksums are the real pin.
  - `climdiv-pdsidv-v1.0.0-20260604`: sha256 `db6c4e40…a3e101`
  - `climdiv-tmpcdv-v1.0.0-20260604`: sha256 `b5eaaa08…9cdc792`
  - `climdiv-pcpndv-v1.0.0-20260604`: sha256 `cd127848…8afbe5109`
- Processing: s06 fixed-width parse (ID plus 12 monthly values; element codes validated per record: pdsi=05, tavg=02, pcpn=01), CA only, element sentinels (−99.99 / −99.90 / −9.99), yielding 11,088 division-months, 1895 to 2026.

## Source 3: NOAA Climate-Division Boundaries

- What: CONUS climate-division polygons used to assign fires and GSOM stations to divisions (representative point in EPSG:3310 intersecting a division, else the nearest division within 25 km, flagged, else null).
  CA is identified via the `CLIMDIV` attribute (401 to 407).
- URL: https://www.ncei.noaa.gov/pub/data/cirs/climdiv/CONUS_CLIMATE_DIVISIONS.shp.zip
- sha256: `edcfadfd390f41eafb8cd4e112d3ead7444a25e505f43fa29107f0c64516aeb3`.
- Processing: s05 for fires (42 assigned via the nearest fallback; 1 left null, the 2002 BISCUIT fire, whose representative point lies in Oregon).
  Reused by s07 for stations (19 of 118 stations fall outside CA divisions + 25 km and are excluded).

## Source 4: NOAA GSOM Station Wind (AWND)

- What: Global Summary of the Month average wind speed, pulled in two steps via NCEI Access services.
  1. The search service enumerates the 118 GSOM stations reporting AWND in a California bounding box (42.1, −124.6, 32.4, −113.9), pinned as `gsom_stations.json`.
  2. The data service pulls AWND for those stations, 1980-01-01 to 2025-12-31, in 3 chunks of ≤40 stations, concatenated to `gsom_ca_awnd.csv` (44,461 station-months).
- Units: meters/second, the Access Data Service default (metric).
  Confirmed against the GSOM documentation ("miles per hour or meters per second depending on user specification") and the value distribution (mean 2.9 m/s, max 8.3 m/s).
- sha256: stations `c54fe94c…e9fb6814`, data `45512cf4…439ef49`.
- Processing: s07 station-to-division assignment, then division-month mean AWND plus contributing-station count (3,413 division-months).
  s08 left-joins all climate onto fires by (division, alarm year, alarm month).
