"""s07: Build division-month wind speed from NOAA GSOM station files.

nClimDiv has no wind element, so wind comes from GHCN/GSOM station monthly
summaries (AWND = average wind speed). Decisions (cross-referenced in
SCHEMA.md):

  D-07a Stations were selected at download time by a deterministic rule
        (see pipeline/download.py:select_wind_stations and PROVENANCE.md):
        US GHCN stations in California with an AWND record starting by 1990
        and running through at least 2024 — long-record airport/ASOS sites.
  D-07b Each station is assigned to a climate division by point-in-polygon
        on its GSOM lat/lon (nearest division if just outside, e.g. piers).
  D-07c wind_avg_ms for a division-month = unweighted mean of AWND over that
        division's reporting stations; wind_n_stations ships alongside so
        users can weight or filter thin coverage.
  D-07d KNOWN GAP (documented, not patched): AWND exists only from the
        ASOS era (~1984 onward), so wind is NULL for earlier fires and for
        division-months with no reporting station. No backfill, no
        interpolation.
  D-07e Unit sanity check: GSOM AWND is m/s; the stage asserts the statewide
        long-run mean is in a plausible 1-8 m/s band to catch a silent
        upstream unit change.

Run: python -m pipeline.stages.s07_build_wind
Inputs: data/raw/gsom/*.csv, data/raw/climdiv/CONUS_CLIMATE_DIVISIONS.shp.zip
Output: data/processed/s07_wind_monthly.parquet
"""

import glob

import geopandas as gpd
import pandas as pd

from .. import config
from ..util import log, write_parquet, processed
from .s05_assign_division import load_ca_divisions

OUT = processed("s07_wind_monthly.parquet")


def main() -> None:
    paths = sorted(glob.glob(str(config.GSOM_DIR / "*.csv")))
    if not paths:
        raise RuntimeError(f"no GSOM csvs under {config.GSOM_DIR}")

    frames = []
    for p in paths:
        df = pd.read_csv(p, dtype={"DATE": "string"}, low_memory=False)
        if "AWND" not in df.columns:
            continue
        sub = df[["STATION", "DATE", "LATITUDE", "LONGITUDE", "AWND"]].dropna(
            subset=["AWND"])
        frames.append(sub)
    wind = pd.concat(frames, ignore_index=True)
    wind["year"] = wind["DATE"].str[0:4].astype(int)
    wind["month"] = wind["DATE"].str[5:7].astype(int)
    log("s07", f"{len(wind):,} station-months with AWND from "
               f"{wind['STATION'].nunique()} stations, "
               f"{wind['year'].min()}–{wind['year'].max()}")

    # D-07e unit sanity
    mean_ms = wind["AWND"].mean()
    if not (1.0 <= mean_ms <= 8.0):
        raise RuntimeError(
            f"AWND statewide mean {mean_ms:.2f} outside plausible m/s band — "
            "check GSOM units before proceeding")

    # D-07b station -> division
    st = wind.groupby("STATION")[["LATITUDE", "LONGITUDE"]].first().reset_index()
    stg = gpd.GeoDataFrame(
        st, geometry=gpd.points_from_xy(st["LONGITUDE"], st["LATITUDE"]),
        crs="EPSG:4326").to_crs(config.AREA_CRS)
    ca = load_ca_divisions()
    j = gpd.sjoin(stg, ca, how="left", predicate="within")
    j = j[~j.index.duplicated(keep="first")]
    missing = j["division"].isna()
    if missing.any():
        near = gpd.sjoin_nearest(stg[missing], ca, how="left")
        near = near[~near.index.duplicated(keep="first")]
        j.loc[near.index, "division"] = near["division"]
        log("s07", f"{int(missing.sum())} stations snapped to nearest division")
    st_div = j.set_index("STATION")["division"].astype(int)

    wind["division"] = wind["STATION"].map(st_div)

    # D-07c aggregate
    agg = (wind.groupby(["division", "year", "month"])
           .agg(wind_avg_ms=("AWND", "mean"),
                wind_n_stations=("STATION", "nunique"))
           .reset_index())
    agg["division"] = agg["division"].astype("int8")
    agg["year"] = agg["year"].astype("int16")
    agg["month"] = agg["month"].astype("int8")
    agg["wind_n_stations"] = agg["wind_n_stations"].astype("int16")

    log("s07", f"division-month coverage: {len(agg):,} rows, "
               f"earliest year with data {agg['year'].min()}")
    write_parquet(agg, OUT, sort_by=["division", "year", "month"])


if __name__ == "__main__":
    main()
