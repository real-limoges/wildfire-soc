"""Fetch all raw inputs into data/raw/ and record a checksum manifest.

This is the ONE stage that touches the network. Everything downstream
(`make all`) is deterministic given data/raw/. Each download is recorded in
data/raw/MANIFEST.json (url, upstream filename, sha256, size, timestamp);
PROVENANCE.md is the human-readable version of that manifest.

Idempotent: files already present and checksummed are not re-fetched.
Run: python -m pipeline.download
"""

import datetime
import io
import json
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

from . import config
from .util import log, sha256_file

MANIFEST_PATH = config.RAW / "MANIFEST.json"

# --- Pinned upstream locations (see PROVENANCE.md) -------------------------

# CAL FIRE FRAP fire perimeters, release fire25_1. Resolved and pinned at
# session time; the CKAN/ArcGIS mirror of record is data.ca.gov's
# "California Fire Perimeters (all)" dataset, which carries the fire25_1 gdb.
FRAP_GDB_URL = None  # resolved in resolve_frap_url(); pinned once known

CLIMDIV_BASE = "https://www.ncei.noaa.gov/pub/data/cirs/climdiv/"
CLIMDIV_VARS = {  # stable local name -> upstream prefix
    "climdiv-pdsidv.txt": "climdiv-pdsidv-v1.0.0-",
    "climdiv-tmpcdv.txt": "climdiv-tmpcdv-v1.0.0-",
    "climdiv-tmaxdv.txt": "climdiv-tmaxdv-v1.0.0-",
    "climdiv-pcpndv.txt": "climdiv-pcpndv-v1.0.0-",
}
CLIMDIV_SHP_URL = CLIMDIV_BASE + "CONUS_CLIMATE_DIVISIONS.shp.zip"

GHCND_BASE = "https://www.ncei.noaa.gov/pub/data/ghcn/daily/"
GSOM_BASE = "https://www.ncei.noaa.gov/data/gsom/access/"

UA = {"User-Agent": "wildfire-soc-pipeline/1.0 (research data assembly)"}


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.read()


def _load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text())
    return {"downloads": {}}


def _save_manifest(m: dict) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(m, indent=2, sort_keys=True) + "\n")


def fetch(url: str, dest: Path, manifest: dict, note: str = "") -> Path:
    key = str(dest.relative_to(config.RAW))
    if dest.exists() and key in manifest["downloads"]:
        log("download", f"already have {key}")
        return dest
    log("download", f"fetching {url}")
    data = _get(url)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    manifest["downloads"][key] = {
        "url": url,
        "sha256": sha256_file(dest),
        "bytes": len(data),
        "downloaded_at_utc": datetime.datetime.now(datetime.timezone.utc)
        .isoformat(timespec="seconds"),
        "note": note,
    }
    _save_manifest(manifest)
    return dest


def list_climdiv_versions() -> dict:
    """Read the climdiv directory index to resolve current versioned filenames."""
    index = _get(CLIMDIV_BASE).decode("utf-8", "replace")
    out = {}
    for local, prefix in CLIMDIV_VARS.items():
        matches = sorted(set(re.findall(re.escape(prefix) + r"\d{8}", index)))
        if not matches:
            raise RuntimeError(f"no upstream file matching {prefix}* in index")
        out[local] = matches[-1]
    return out


def main() -> None:
    manifest = _load_manifest()

    # 1. nClimDiv monthly divisional files (PDSI, TAVG, TMAX, PRCP)
    versions = list_climdiv_versions()
    for local, upstream in versions.items():
        fetch(CLIMDIV_BASE + upstream, config.CLIMDIV_DIR / local, manifest,
              note=f"upstream file {upstream}")

    # 2. climate division polygons
    fetch(CLIMDIV_SHP_URL, config.CLIMDIV_SHP_ZIP, manifest)

    # 3. GHCN-D station metadata (for wind-station selection)
    fetch(GHCND_BASE + "ghcnd-stations.txt", config.GHCND_STATIONS, manifest)
    fetch(GHCND_BASE + "ghcnd-inventory.txt", config.GHCND_INVENTORY, manifest)

    # 4. wind stations: CA stations with AWND coverage per selection criteria
    stations = select_wind_stations()
    log("download", f"selected {len(stations)} CA wind stations")
    for sid in stations:
        fetch(GSOM_BASE + f"{sid}.csv", config.GSOM_DIR / f"{sid}.csv", manifest,
              note="GSOM monthly summaries (AWND wind)")

    # 5. FRAP fire perimeters gdb
    url = FRAP_GDB_URL
    if url is None:
        raise SystemExit("FRAP_GDB_URL not pinned yet — set it before downloading")
    zpath = fetch(url, config.RAW / "frap" / "fire25_1.gdb.zip", manifest,
                  note=f"FRAP release {config.FRAP_RELEASE}")
    if not config.FRAP_GDB.exists():
        with zipfile.ZipFile(zpath) as z:
            z.extractall(config.RAW / "frap")
        log("download", f"extracted {config.FRAP_GDB}")

    log("download", "done; manifest at " + str(MANIFEST_PATH))


def select_wind_stations() -> list:
    """Deterministic wind-station selection from the GHCN-D inventory.

    Criteria (config.WIND_*): US stations located in California whose AWND
    record starts by WIND_FIRST_YEAR_MAX and extends to at least
    WIND_LAST_YEAR_MIN. Returns sorted station IDs.
    """
    ca_ids = set()
    with open(config.GHCND_STATIONS, encoding="utf-8") as f:
        for line in f:
            if line[0:2] == "US" and line[38:40] == "CA":
                ca_ids.add(line[0:11])
    chosen = []
    with open(config.GHCND_INVENTORY, encoding="utf-8") as f:
        for line in f:
            sid, elem = line[0:11], line[31:35]
            if sid in ca_ids and elem == "AWND":
                first, last = int(line[36:40]), int(line[41:45])
                if first <= config.WIND_FIRST_YEAR_MAX and last >= config.WIND_LAST_YEAR_MIN:
                    chosen.append(sid)
    return sorted(chosen)


if __name__ == "__main__":
    main()
