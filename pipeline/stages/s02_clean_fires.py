"""s02: Clean and normalize fire attributes. Nothing is dropped here.

Decisions implemented in this stage (each cross-referenced in SCHEMA.md):
  D-02a fire_year comes from FRAP's YEAR_ (the season assignment), coerced to
        int; rows with unparseable YEAR_ get fire_year null + flag_bad_year.
  D-02b ALARM_DATE / CONT_DATE outside [MIN_VALID_YEAR, MAX_VALID_YEAR+1] or
        unparseable are set null and flagged (flag_alarm_date_invalid /
        flag_cont_date_invalid) — never guessed.
  D-02c ALARM_DATE more than config.ALARM_YEAR_TOLERANCE calendar years from
        fire_year → flag_alarm_year_mismatch (date kept; the year field wins
        for season-level use, the date is still used for the monthly climate
        join only when this flag is False).
  D-02d containment before alarm → flag_negative_duration (both dates kept).
  D-02e CAUSE/C_METHOD/OBJECTIVE integer codes mapped to labels from the FRAP
        data dictionary; unknown codes -> "UNKNOWN_CODE_<n>" (nothing nulled).
  D-02f fire_name normalized (upper, collapsed whitespace) into
        fire_name_norm for dedup matching; original kept.
  D-02g area recomputed from geometry in EPSG:3310 (acres_calc); relative
        disagreement with GIS_ACRES beyond AREA_MISMATCH_RATIO →
        flag_area_mismatch. GIS_ACRES kept as the reported value of record.
  D-02h primary key fire_id: FRAP GlobalID if present & unique, else
        src_objectid-based fallback (recorded in the QC report which one).

Run: python -m pipeline.stages.s02_clean_fires
Input: data/processed/s01_fires_raw.parquet
Output: data/processed/s02_fires_clean.parquet
"""

import re

import geopandas as gpd
import numpy as np
import pandas as pd

from .. import config
from ..util import log, processed

IN = processed("s01_fires_raw.parquet")
OUT = processed("s02_fires_clean.parquet")

SQM_PER_ACRE = 4046.8564224

# FRAP data dictionary code tables (fire25_1 metadata).
CAUSE_LABELS = {
    1: "LIGHTNING", 2: "EQUIPMENT_USE", 3: "SMOKING", 4: "CAMPFIRE",
    5: "DEBRIS", 6: "RAILROAD", 7: "ARSON", 8: "PLAYING_WITH_FIRE",
    9: "MISCELLANEOUS", 10: "VEHICLE", 11: "POWERLINE",
    12: "FIREFIGHTER_TRAINING", 13: "NON_FIREFIGHTER_TRAINING",
    14: "UNKNOWN", 15: "STRUCTURE", 16: "AIRCRAFT", 17: "VOLCANIC",
    18: "ESCAPED_PRESCRIBED_BURN", 19: "ILLEGAL_ALIEN_CAMPFIRE",
}
C_METHOD_LABELS = {
    1: "GPS_GROUND", 2: "GPS_AIR", 3: "INFRARED", 4: "OTHER_IMAGERY",
    5: "PHOTO_INTERPRETATION", 6: "HAND_DRAWN", 7: "MIXED_METHODS",
    8: "UNKNOWN",
}
OBJECTIVE_LABELS = {1: "SUPPRESSION", 2: "RESOURCE_BENEFIT"}


def _norm_name(s):
    if pd.isna(s):
        return pd.NA
    s = re.sub(r"\s+", " ", str(s).strip().upper())
    return s if s else pd.NA


def _map_code(series, table):
    def f(v):
        if pd.isna(v):
            return pd.NA
        v = int(v)
        return table.get(v, f"UNKNOWN_CODE_{v}")
    return series.map(f).astype("string")


def main() -> None:
    gdf = gpd.read_parquet(IN)
    n = len(gdf)

    # --- D-02h: primary key -------------------------------------------------
    gid = gdf.get("GlobalID")
    if gid is not None and gid.notna().all() and gid.is_unique:
        gdf["fire_id"] = gid.astype("string").str.strip("{}").str.lower()
        log("s02", "fire_id = FRAP GlobalID")
    else:
        gdf["fire_id"] = "objectid-" + gdf["src_objectid"].astype(str)
        log("s02", "fire_id = src_objectid fallback (GlobalID missing/dup)")

    # --- D-02a: fire year ----------------------------------------------------
    year = pd.to_numeric(gdf["YEAR_"], errors="coerce")
    bad_year = year.isna() | (year < config.MIN_VALID_YEAR) | (year > config.MAX_VALID_YEAR)
    gdf["fire_year"] = year.where(~bad_year).astype("Int64")
    gdf["flag_bad_year"] = bad_year
    if bad_year.any():
        log("s02", f"{int(bad_year.sum())} rows with missing/out-of-range YEAR_")

    # --- D-02b: dates --------------------------------------------------------
    for col, out, flag in [("ALARM_DATE", "alarm_date", "flag_alarm_date_invalid"),
                           ("CONT_DATE", "cont_date", "flag_cont_date_invalid")]:
        d = pd.to_datetime(gdf[col], errors="coerce")
        try:
            d = d.dt.tz_localize(None)
        except TypeError:
            pass
        in_range = (d.dt.year >= config.MIN_VALID_YEAR) & \
                   (d.dt.year <= config.MAX_VALID_YEAR + 1)
        invalid = gdf[col].notna() & (d.isna() | ~in_range.fillna(False))
        gdf[out] = d.where(in_range.fillna(False))
        gdf[flag] = invalid
        if invalid.any():
            log("s02", f"{int(invalid.sum())} invalid {col} values nulled")

    # --- D-02c: alarm vs season year -----------------------------------------
    ay = gdf["alarm_date"].dt.year
    mismatch = (gdf["alarm_date"].notna() & gdf["fire_year"].notna() &
                ((ay - gdf["fire_year"]).abs() > config.ALARM_YEAR_TOLERANCE))
    gdf["flag_alarm_year_mismatch"] = mismatch.fillna(False).astype(bool)

    # --- D-02d: containment before alarm --------------------------------------
    negdur = (gdf["alarm_date"].notna() & gdf["cont_date"].notna() &
              (gdf["cont_date"] < gdf["alarm_date"]))
    gdf["flag_negative_duration"] = negdur

    # --- D-02e: coded attributes ----------------------------------------------
    gdf["cause"] = _map_code(pd.to_numeric(gdf["CAUSE"], errors="coerce"), CAUSE_LABELS)
    gdf["collection_method"] = _map_code(
        pd.to_numeric(gdf["C_METHOD"], errors="coerce"), C_METHOD_LABELS)
    gdf["objective"] = _map_code(
        pd.to_numeric(gdf["OBJECTIVE"], errors="coerce"), OBJECTIVE_LABELS)

    # --- D-02f: names ----------------------------------------------------------
    gdf["fire_name"] = gdf["FIRE_NAME"].astype("string").str.strip()
    gdf["fire_name_norm"] = gdf["FIRE_NAME"].map(_norm_name).astype("string")
    gdf["complex_name"] = gdf.get("COMPLEX_NAME", pd.Series(pd.NA, index=gdf.index)).astype("string")
    gdf["irwin_id"] = (gdf.get("IRWINID", pd.Series(pd.NA, index=gdf.index))
                       .astype("string").str.strip().str.strip("{}").str.lower()
                       .replace("", pd.NA))

    # --- passthrough identifiers ------------------------------------------------
    gdf["agency"] = gdf["AGENCY"].astype("string")
    gdf["unit_id"] = gdf["UNIT_ID"].astype("string")
    gdf["inc_num"] = gdf.get("INC_NUM", pd.Series(pd.NA, index=gdf.index)).astype("string")

    # --- D-02g: area ---------------------------------------------------------
    gdf["gis_acres"] = pd.to_numeric(gdf["GIS_ACRES"], errors="coerce")
    area_m2 = gdf.geometry.area
    gdf["acres_calc"] = area_m2 / SQM_PER_ACRE
    rel = (gdf["acres_calc"] - gdf["gis_acres"]).abs() / gdf["gis_acres"].clip(lower=0.1)
    gdf["flag_area_mismatch"] = (rel > config.AREA_MISMATCH_RATIO).fillna(False)
    log("s02", f"area mismatch >{config.AREA_MISMATCH_RATIO:.0%}: "
               f"{int(gdf['flag_area_mismatch'].sum())} rows")

    gdf = gdf.sort_values("src_objectid", kind="mergesort").reset_index(drop=True)
    gdf.to_parquet(OUT, index=False)
    log("s02", f"wrote {OUT} ({len(gdf):,}/{n:,} rows — nothing dropped)")


if __name__ == "__main__":
    main()
