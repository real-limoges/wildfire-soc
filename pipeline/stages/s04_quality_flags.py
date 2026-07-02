"""s04: Attach data-quality flags for FRAP's documented weaknesses.

Nothing is dropped — these flags let a downstream user choose a consistently
observed subset instead of us silently choosing for them. Decisions
(cross-referenced in SCHEMA.md):

  D-04a flag_pre_reliable_era: fire_year < config.RELIABLE_FROM_YEAR (1950).
        FRAP documents pre-1950 perimeters as substantially incomplete;
        counts by decade go in the QC report.
  D-04b Size-cutoff flags. FRAP's inclusion thresholds vary by fuel type and
        the per-fire fuel type is not recorded, so we publish three nested
        booleans (below_cutoff_timber/brush/grass at 10/30/300 acres,
        config.MIN_CUTOFF_ACRES_*) computed from gis_acres. Analyses that
        need a consistently-observed population should restrict to fires
        >= the grass cutoff (the most conservative), or at minimum >= the
        timber cutoff; SCHEMA.md explains the trade-off.
  D-04c flag_coarse_geometry: vertex density below
        config.COARSE_VERTICES_PER_KM vertices per km of perimeter marks
        over-generalized (typically hand-drawn historical) shapes.
        n_vertices and perimeter_km ship as columns so users can pick their
        own threshold.
  D-04d flag_no_alarm_month: no usable alarm date (missing/invalid, or
        flag_alarm_year_mismatch) — these rows get NULL monthly climate
        covariates in s08 rather than a guessed month.

Run: python -m pipeline.stages.s04_quality_flags
Input: data/processed/s03_fires_deduped.parquet
Output: data/processed/s04_fires_flagged.parquet
"""

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely import get_coordinates

from .. import config
from ..util import log, processed

IN = processed("s03_fires_deduped.parquet")
OUT = processed("s04_fires_flagged.parquet")


def main() -> None:
    gdf = gpd.read_parquet(IN)

    # D-04a
    gdf["flag_pre_reliable_era"] = (
        gdf["fire_year"] < config.RELIABLE_FROM_YEAR).fillna(True).astype(bool)

    # D-04b
    acres = gdf["gis_acres"]
    gdf["below_cutoff_timber"] = (acres < config.MIN_CUTOFF_ACRES_TIMBER).fillna(True)
    gdf["below_cutoff_brush"] = (acres < config.MIN_CUTOFF_ACRES_BRUSH).fillna(True)
    gdf["below_cutoff_grass"] = (acres < config.MIN_CUTOFF_ACRES_GRASS).fillna(True)

    # D-04c
    def vertex_count(g):
        if g is None or g.is_empty:
            return 0
        return len(get_coordinates(g))

    gdf["n_vertices"] = gdf.geometry.apply(vertex_count).astype("int32")
    gdf["perimeter_km"] = gdf.geometry.length / 1000.0  # EPSG:3310 meters
    density = gdf["n_vertices"] / gdf["perimeter_km"].replace(0, np.nan)
    gdf["flag_coarse_geometry"] = (
        density < config.COARSE_VERTICES_PER_KM).fillna(True).astype(bool)
    log("s04", f"coarse geometry: {int(gdf['flag_coarse_geometry'].sum())} rows "
               f"(density < {config.COARSE_VERTICES_PER_KM}/km)")

    # D-04d
    gdf["flag_no_alarm_month"] = (
        gdf["alarm_date"].isna() | gdf["flag_alarm_year_mismatch"]).astype(bool)
    log("s04", f"no usable alarm month: {int(gdf['flag_no_alarm_month'].sum())} rows")

    gdf = gdf.sort_values("src_objectid", kind="mergesort").reset_index(drop=True)
    gdf.to_parquet(OUT, index=False)
    log("s04", f"wrote {OUT} ({len(gdf):,} rows)")


if __name__ == "__main__":
    main()
