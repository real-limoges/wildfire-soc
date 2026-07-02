"""s08: Join fires with climate covariates and write the final artifact.

Decisions (cross-referenced in SCHEMA.md):
  D-08a Join keys: (climate_division, alarm_year, alarm_month). The alarm
        month is used only when the fire has a usable alarm date
        (flag_no_alarm_month == False); otherwise all climate covariates are
        NULL and flag_climate_missing explains why.
  D-08b Covariates are the *concurrent month* values (pdsi, tmean_c, tmax_c,
        precip_mm, wind_avg_ms). PDSI is itself an accumulated drought
        measure, so no additional lagging is baked in — lag construction is
        an analysis choice, deliberately left out of the dataset.
  D-08c flag_climate_missing: 'no_alarm_month' | 'pre_1895' (before nClimDiv
        record) | 'not_covered' (join found no row) | null when joined.
        Wind has its own coverage note (wind_avg_ms NULL before ~1984,
        wind_n_stations says how many stations reported).
  D-08d The artifact carries centroid/representative-point lon-lat, areas,
        and geometry-quality metrics but NOT the full polygon geometry
        (kept in data/processed/s05_fires_with_division.parquet, joinable
        on fire_id) — keeps the artifact small and analysis-ready.

Run: python -m pipeline.stages.s08_join_enrich
Inputs: data/processed/s05_fires_with_division.parquet,
        data/processed/s06_climdiv_monthly.parquet,
        data/processed/s07_wind_monthly.parquet
Output: artifacts/fires_enriched.parquet
"""

import geopandas as gpd
import numpy as np
import pandas as pd

from .. import config
from ..util import log, write_parquet

IN_FIRES = config.PROCESSED / "s05_fires_with_division.parquet"
IN_CLIM = config.PROCESSED / "s06_climdiv_monthly.parquet"
IN_WIND = config.PROCESSED / "s07_wind_monthly.parquet"
OUT = config.ARTIFACTS / "fires_enriched.parquet"

FINAL_COLUMNS = [
    # identity
    "fire_id", "src_objectid", "fire_name", "fire_name_norm", "complex_name",
    "irwin_id", "inc_num", "agency", "unit_id",
    # when
    "fire_year", "alarm_date", "alarm_year", "alarm_month", "cont_date",
    "duration_days",
    # what/why
    "cause", "objective", "collection_method",
    # where
    "climate_division", "rep_point_lon", "rep_point_lat",
    # size & geometry quality
    "gis_acres", "acres_calc", "perimeter_km", "n_vertices",
    # climate covariates
    "pdsi", "tmean_c", "tmax_c", "precip_mm", "wind_avg_ms", "wind_n_stations",
    # flags & lineage
    "flag_climate_missing",
    "flag_bad_year", "flag_alarm_date_invalid", "flag_cont_date_invalid",
    "flag_alarm_year_mismatch", "flag_negative_duration", "flag_no_alarm_month",
    "flag_area_mismatch", "flag_pre_reliable_era",
    "below_cutoff_timber", "below_cutoff_brush", "below_cutoff_grass",
    "flag_coarse_geometry", "flag_no_geometry", "flag_division_nearest",
    "geom_was_invalid", "dup_group_id", "n_duplicates_removed",
]


def main() -> None:
    fires = gpd.read_parquet(IN_FIRES)
    fires = pd.DataFrame(fires.drop(columns="geometry"))
    clim = pd.read_parquet(IN_CLIM)
    wind = pd.read_parquet(IN_WIND)

    # D-08a join keys from the alarm date, only when usable
    usable = ~fires["flag_no_alarm_month"]
    fires["alarm_year"] = fires["alarm_date"].dt.year.astype("Int64").where(usable)
    fires["alarm_month"] = fires["alarm_date"].dt.month.astype("Int64").where(usable)

    fires["duration_days"] = (
        (fires["cont_date"] - fires["alarm_date"]).dt.days
        .where(~fires["flag_negative_duration"]).astype("Int64"))

    clim_min_year = int(clim["year"].min())

    merged = fires.merge(
        clim.rename(columns={"division": "climate_division",
                             "year": "alarm_year", "month": "alarm_month"}),
        how="left", on=["climate_division", "alarm_year", "alarm_month"],
        validate="many_to_one",
    ).merge(
        wind.rename(columns={"division": "climate_division",
                             "year": "alarm_year", "month": "alarm_month"}),
        how="left", on=["climate_division", "alarm_year", "alarm_month"],
        validate="many_to_one",
    )

    # D-08c explain missing climate
    joined = merged[["pdsi", "tmean_c", "tmax_c", "precip_mm"]].notna().any(axis=1)
    reason = pd.Series(pd.NA, index=merged.index, dtype="string")
    reason = reason.mask(~joined, "not_covered")
    reason = reason.mask(~joined & (merged["alarm_year"] < clim_min_year), "pre_1895")
    reason = reason.mask(merged["alarm_year"].isna(), "no_alarm_month")
    merged["flag_climate_missing"] = reason.where(~joined)

    cov = joined.mean()
    log("s08", f"climate covariates joined for {cov:.1%} of fires; "
               f"wind non-null for {merged['wind_avg_ms'].notna().mean():.1%}")

    out = merged[FINAL_COLUMNS].copy()
    out["wind_n_stations"] = out["wind_n_stations"].astype("Int64")
    write_parquet(out, OUT, sort_by=["fire_year", "alarm_date", "fire_id"])


if __name__ == "__main__":
    main()
