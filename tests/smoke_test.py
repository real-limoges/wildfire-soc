"""End-to-end smoke test on synthetic fixtures — no network, no real data.

Builds a miniature fake of every raw input (FRAP gdb, nClimDiv files,
division shapefile, GSOM csvs) in a temp directory, runs stages s01–s09
against it via WILDFIRE_DATA_ROOT, and asserts the cleaning/dedup/join
decisions behave as documented. Also rebuilds twice and compares artifact
hashes to prove determinism.

Run: python -m tests.smoke_test
"""

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
from shapely.geometry import Polygon, box

REPO = Path(__file__).resolve().parent.parent

# 7 fake CA "divisions": vertical lon strips covering (-124..-117, 33..42)
STRIPS = [(-124 + i, -123 + i) for i in range(7)]  # division i+1


def build_divisions(raw: Path) -> None:
    geoms, codes = [], []
    for i, (lo, hi) in enumerate(STRIPS):
        geoms.append(box(lo, 33, hi, 42))
        codes.append(401 + i)
    gdf = gpd.GeoDataFrame({"CLIMDIV": codes, "STATE": ["California"] * 7},
                           geometry=geoms, crs="EPSG:4326")
    shp_dir = raw / "climdiv" / "_shp"
    shp_dir.mkdir(parents=True, exist_ok=True)
    gdf.to_file(shp_dir / "GIS.OFFICIAL_CLIM_DIVISIONS.shp")
    zpath = raw / "climdiv" / "CONUS_CLIMATE_DIVISIONS.shp.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        for f in sorted(shp_dir.iterdir()):
            z.write(f, f.name)
    shutil.rmtree(shp_dir)


def sq(lon, lat, half_deg=0.05):
    return box(lon - half_deg, lat - half_deg, lon + half_deg, lat + half_deg)


def build_fires_gdb(raw: Path) -> None:
    rows = []

    def add(year, name, alarm, cont, acres, lon, lat, geom=None, agency="CDF",
            irwin=None, cause=1):
        rows.append(dict(
            YEAR_=str(year) if year else None, STATE="CA", AGENCY=agency,
            UNIT_ID="XXX", FIRE_NAME=name, INC_NUM="00001234",
            ALARM_DATE=alarm, CONT_DATE=cont, CAUSE=cause, C_METHOD=1,
            OBJECTIVE=1, GIS_ACRES=acres, COMMENTS=None, COMPLEX_NAME=None,
            IRWINID=irwin, FIRE_NUM=None, COMPLEX_ID=None, DECADES=None,
            GlobalID="{" + f"00000000-0000-0000-0000-{len(rows):012d}" + "}",
            geometry=geom if geom is not None else sq(lon, lat),
        ))

    # 0 normal modern fire, division 1
    add(2020, "ALPHA", "2020-07-10", "2020-07-20", 1000.0, -123.5, 36.0)
    # 1+2 near-duplicate pair (same name/year, overlapping), division 2
    g = sq(-122.5, 37.0)
    add(2018, "BRAVO", "2018-08-01", "2018-08-15", 800.0, 0, 0, geom=g)
    add(2018, "BRAVO", "2018-08-01", None, 780.0, 0, 0,
        geom=sq(-122.5, 37.0, 0.049), agency="USF")
    # 3 pre-1950, coarse triangle, no alarm date, division 3
    add(1930, "CHARLIE", None, None, 5000.0, 0, 0,
        geom=Polygon([(-121.5, 35.0), (-121.2, 35.0), (-121.35, 35.6)]))
    # 4 invalid alarm date (out of range), division 4
    add(2015, "DELTA", "1800-01-01", None, 200.0, -120.5, 38.0)
    # 5 tiny fire below all cutoffs, division 5
    add(2015, "ECHO", "2015-06-05", "2015-06-06", 5.0, -119.5, 36.5)
    # 6 reversed dates, division 6
    add(2019, "FOXTROT", "2019-09-10", "2019-09-01", 400.0, -118.5, 35.5)
    # 7 bowtie (invalid) geometry, division 7
    add(2021, "GOLF", "2021-10-02", "2021-10-30", 600.0, 0, 0,
        geom=Polygon([(-117.6, 34.0), (-117.4, 34.2), (-117.6, 34.2),
                      (-117.4, 34.0)]))
    # 8 pre-nClimDiv era fire with alarm date, division 1
    add(1890, "HOTEL", "1890-08-01", None, 12000.0, -123.5, 40.0)
    # 9 alarm year mismatch (YEAR_=2010, alarm 2005), division 2
    add(2010, "INDIA", "2005-03-03", None, 300.0, -122.5, 39.0)
    # 10+11 exact-WKB duplicate with different names, division 3
    g2 = sq(-121.5, 37.5)
    add(2012, "JULIET", "2012-07-07", None, 250.0, 0, 0, geom=g2)
    add(2012, "JULIETTE", None, None, 250.0, 0, 0, geom=g2, agency="LRA")

    gdf = gpd.GeoDataFrame(rows, crs="EPSG:4326").to_crs("EPSG:3310")
    for c in ("ALARM_DATE", "CONT_DATE"):
        gdf[c] = pd.to_datetime(gdf[c])
    out = raw / "frap" / "fire25_1.gdb"
    out.parent.mkdir(parents=True, exist_ok=True)
    pyogrio.write_dataframe(gdf, out, layer="firep25_1", driver="OpenFileGDB")


def build_climdiv(raw: Path) -> None:
    (raw / "climdiv").mkdir(parents=True, exist_ok=True)
    elem = {"pdsidv": "05", "tmpcdv": "02", "tmaxdv": "27", "pcpndv": "01"}
    base = {"pdsidv": -2.5, "tmpcdv": 65.0, "tmaxdv": 80.0, "pcpndv": 1.5}
    for var, ee in elem.items():
        lines = []
        for div in range(1, 8):
            for year in range(1895, 2026):
                vals = [f"{base[var] + div * 0.1 + m * 0.01:7.2f}"
                        for m in range(12)]
                lines.append(f"04{div:02d}{ee}{year}" + "".join(
                    f" {v}" for v in vals))
        (raw / "climdiv" / f"climdiv-{var}.txt").write_text("\n".join(lines) + "\n")


def build_gsom(raw: Path) -> None:
    (raw / "gsom").mkdir(parents=True, exist_ok=True)
    stations = [("USW00000001", 36.0, -123.5), ("USW00000002", 37.0, -122.5)]
    for sid, lat, lon in stations:
        recs = []
        for year in range(1984, 2026):
            for month in range(1, 13):
                recs.append({"STATION": sid, "DATE": f"{year}-{month:02d}",
                             "LATITUDE": lat, "LONGITUDE": lon,
                             "AWND": 3.5 + 0.01 * month})
        pd.DataFrame(recs).to_csv(raw / "gsom" / f"{sid}.csv", index=False)


def run_stage(mod: str, env: dict) -> None:
    r = subprocess.run([sys.executable, "-m", mod], cwd=REPO, env=env,
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout)
        print(r.stderr)
        raise SystemExit(f"stage {mod} failed")


ALL_STAGES = [f"pipeline.stages.{m}" for m in [
    "s01_extract_fires", "s02_clean_fires", "s03_dedupe_fires",
    "s04_quality_flags", "s05_assign_division", "s06_build_climdiv",
    "s07_build_wind", "s08_join_enrich", "s09_validate"]]


def build_all(root: Path) -> str:
    env = dict(os.environ, WILDFIRE_DATA_ROOT=str(root))
    for mod in ALL_STAGES:
        run_stage(mod, env)
    art = root / "artifacts" / "fires_enriched.parquet"
    return hashlib.sha256(art.read_bytes()).hexdigest()


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="wildfire-smoke-"))
    raw = tmp / "data" / "raw"
    build_divisions(raw)
    build_fires_gdb(raw)
    build_climdiv(raw)
    build_gsom(raw)

    h1 = build_all(tmp)

    df = pd.read_parquet(tmp / "artifacts" / "fires_enriched.parquet")
    removed = pd.read_parquet(tmp / "data" / "processed" /
                              "s03_duplicates_removed.parquet")

    def one(name):
        m = df[df["fire_name"] == name]
        assert len(m) == 1, f"{name}: expected 1 row, got {len(m)}"
        return m.iloc[0]

    assert len(df) == 10, f"expected 10 canonical rows, got {len(df)}"
    assert len(removed) == 2, f"expected 2 removed dupes, got {len(removed)}"

    a = one("ALPHA")
    assert a["climate_division"] == 1
    assert abs(a["pdsi"] - (-2.5 + 0.1 + 0.06)) < 1e-6, a["pdsi"]
    assert a["wind_avg_ms"] > 3.5 and a["wind_n_stations"] == 1
    assert not a["flag_pre_reliable_era"] and not a["below_cutoff_timber"]
    assert a["duration_days"] == 10

    b = one("BRAVO")  # canonical survivor of the near-dup pair
    assert b["n_duplicates_removed"] == 1 and pd.notna(b["dup_group_id"])
    assert b["agency"] == "CDF"  # more complete attributes wins

    c = one("CHARLIE")
    assert c["flag_pre_reliable_era"] and c["flag_no_alarm_month"]
    assert c["flag_climate_missing"] == "no_alarm_month"
    assert c["flag_coarse_geometry"]

    d = one("DELTA")
    assert d["flag_alarm_date_invalid"] and pd.isna(d["alarm_date"])
    assert d["flag_climate_missing"] == "no_alarm_month"

    e = one("ECHO")
    assert e["below_cutoff_timber"] and e["below_cutoff_brush"] and e["below_cutoff_grass"]
    assert pd.notna(e["pdsi"])

    f = one("FOXTROT")
    assert f["flag_negative_duration"] and pd.isna(f["duration_days"])

    g = one("GOLF")
    assert g["geom_was_invalid"]
    assert g["climate_division"] == 7

    h = one("HOTEL")
    assert h["flag_climate_missing"] == "pre_1895" and pd.isna(h["pdsi"])

    i = one("INDIA")
    assert i["flag_alarm_year_mismatch"] and i["flag_no_alarm_month"]
    assert pd.isna(i["pdsi"])

    j = one("JULIET")  # exact-WKB dup collapsed despite different names
    assert j["n_duplicates_removed"] == 1
    assert "JULIETTE" in set(removed["fire_name"])

    # determinism: full rebuild from the same raw -> identical artifact bytes
    shutil.rmtree(tmp / "data" / "processed")
    (tmp / "artifacts" / "fires_enriched.parquet").unlink()
    h2 = build_all(tmp)
    assert h1 == h2, f"artifact not deterministic: {h1} != {h2}"

    shutil.rmtree(tmp)
    print("SMOKE TEST PASSED (incl. determinism check)")


if __name__ == "__main__":
    main()
