"""Pinned constants and paths for the fires_enriched pipeline.

Every tunable cleaning decision lives here (or is a named constant in its
stage module) so a single decision can be changed without touching the rest
of the pipeline. artifacts/SCHEMA.md points each documented decision at the
constant or function that implements it.
"""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
# WILDFIRE_DATA_ROOT relocates data/ and artifacts/ (used by the smoke test;
# defaults to the repo itself for normal builds).
DATA_ROOT = Path(os.environ.get("WILDFIRE_DATA_ROOT", REPO_ROOT))
RAW = DATA_ROOT / "data" / "raw"
PROCESSED = DATA_ROOT / "data" / "processed"
ARTIFACTS = DATA_ROOT / "artifacts"

# ---------------------------------------------------------------------------
# Source pinning (see PROVENANCE.md for URLs, versions, and checksums)
# ---------------------------------------------------------------------------

# CAL FIRE FRAP historical fire perimeters, release fire25_1 (April 2026).
FRAP_RELEASE = "fire25_1"
FRAP_GDB = RAW / "frap" / f"{FRAP_RELEASE}.gdb"
FRAP_FIRE_LAYER = "firep25_1"  # wildfire perimeters layer inside the gdb

# NOAA nClimDiv monthly divisional data. Downloaded under stable local names;
# the versioned upstream filenames are recorded in PROVENANCE.md.
CLIMDIV_DIR = RAW / "climdiv"
CLIMDIV_FILES = {
    "pdsi": CLIMDIV_DIR / "climdiv-pdsidv.txt",   # Palmer Drought Severity Index
    "tmpc": CLIMDIV_DIR / "climdiv-tmpcdv.txt",   # monthly mean temperature (deg F)
    "tmax": CLIMDIV_DIR / "climdiv-tmaxdv.txt",   # monthly mean of daily max temp (deg F)
    "pcpn": CLIMDIV_DIR / "climdiv-pcpndv.txt",   # monthly precipitation (inches)
}
CA_CLIMDIV_STATE_CODE = "04"  # California in nClimDiv state coding
CA_N_DIVISIONS = 7

# NOAA climate division polygons (for assigning fires to divisions).
CLIMDIV_SHP_ZIP = RAW / "climdiv" / "CONUS_CLIMATE_DIVISIONS.shp.zip"

# NOAA GSOM (Global Summary of the Month) station CSVs for wind (AWND).
GSOM_DIR = RAW / "gsom"
GHCND_STATIONS = RAW / "ghcnd" / "ghcnd-stations.txt"
GHCND_INVENTORY = RAW / "ghcnd" / "ghcnd-inventory.txt"

# Wind-station selection criteria (applied at download time; the resulting
# station list is frozen in data/raw/gsom/ and PROVENANCE.md):
# US stations in California reporting AWND with a record starting by
# WIND_FIRST_YEAR_MAX and still active in WIND_LAST_YEAR_MIN.
WIND_FIRST_YEAR_MAX = 1990
WIND_LAST_YEAR_MIN = 2024

# ---------------------------------------------------------------------------
# Cleaning decisions (each referenced from artifacts/SCHEMA.md)
# ---------------------------------------------------------------------------

# CRS: FRAP ships in EPSG:3310 (California Albers, equal-area). All area and
# geometry math happens in 3310; exported coordinates are EPSG:4326 lon/lat.
AREA_CRS = "EPSG:3310"
EXPORT_CRS = "EPSG:4326"

# Dataset temporal bounds: FRAP nominally starts 1878; anything outside
# [1878, current release year] is treated as a data error.
MIN_VALID_YEAR = 1878
MAX_VALID_YEAR = 2025  # last season included in fire25_1

# Dates outside this window (or unparseable) are nulled and flagged rather
# than guessed. ALARM_DATE more than 1 calendar year away from YEAR_ is
# treated as unreliable (flagged, kept).
ALARM_YEAR_TOLERANCE = 1

# Duplicate detection (s03): candidate pairs share the same fire year and
# either the same IRWIN ID or the same normalized fire name; a pair is a
# duplicate when geometry IoU exceeds DUP_IOU_THRESHOLD or one geometry is
# almost entirely contained in the other (containment > DUP_CONTAINMENT).
DUP_IOU_THRESHOLD = 0.5
DUP_CONTAINMENT = 0.9

# Exact-geometry duplicates: identical WKB within the same year are always
# collapsed regardless of name.

# Size-cutoff flag (s04): FRAP's stated modern inclusion thresholds vary by
# fuel type (timber/brush/grass); fuel type per fire is not recorded, so we
# flag fires below the *smallest* stated cutoff (timber) as potentially
# inconsistently observed across eras/agencies. Value verified against the
# fire25_1 metadata at download time.
MIN_CUTOFF_ACRES_TIMBER = 10.0
MIN_CUTOFF_ACRES_BRUSH = 30.0
MIN_CUTOFF_ACRES_GRASS = 300.0

# Era reliability flag (s04): FRAP documents the record as most reliable from
# ~1950 onward.
RELIABLE_FROM_YEAR = 1950

# Coarse-geometry flag (s04): perimeters digitized from generalized historical
# maps have very low vertex density. Threshold in vertices per km of perimeter;
# calibrated on the actual distribution (see NOTES.md) and documented in SCHEMA.md.
COARSE_VERTICES_PER_KM = 1.0

# GIS_ACRES vs recomputed geometry area cross-check (s02): relative difference
# above this ratio is flagged.
AREA_MISMATCH_RATIO = 0.10
