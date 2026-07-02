"""s05: Assign each fire to a NOAA climate division (the join region).

Decisions (cross-referenced in SCHEMA.md):
  D-05a Region = NOAA nClimDiv climate division (CA has 7). Chosen because
        the climate covariates (PDSI, temperature, precipitation) are
        published exactly at this spatial unit — no re-interpolation needed.
  D-05b Each fire is located by its *representative point* (a point
        guaranteed inside the polygon; centroids of concave/multipart burns
        can fall outside). Fires spanning multiple divisions are assigned to
        the single division containing that point; perimeter-area splitting
        was rejected as false precision given perimeter quality.
  D-05c Fires whose point falls outside every division polygon (offshore
        slivers, border digitization) are assigned the *nearest* division
        and flagged flag_division_nearest, with the snap distance in
        division_snap_km. No fire is left unassigned unless geometry is
        missing entirely (flag_no_geometry).

Run: python -m pipeline.stages.s05_assign_division
Inputs: data/processed/s04_fires_flagged.parquet,
        data/raw/climdiv/CONUS_CLIMATE_DIVISIONS.shp.zip
Output: data/processed/s05_fires_with_division.parquet
"""

import geopandas as gpd
import numpy as np
import pandas as pd

from .. import config
from ..util import log, processed

IN = processed("s04_fires_flagged.parquet")
OUT = processed("s05_fires_with_division.parquet")


def load_ca_divisions() -> gpd.GeoDataFrame:
    div = gpd.read_file(f"zip://{config.CLIMDIV_SHP_ZIP}")
    cols = {c.upper(): c for c in div.columns}
    # The NOAA shapefile identifies divisions via a CLIMDIV code
    # (state*100 + division) and/or STATE/CD fields; tolerate either.
    if "CLIMDIV" in cols:
        code = pd.to_numeric(div[cols["CLIMDIV"]], errors="coerce")
        ca = div[(code >= 401) & (code <= 407)].copy()
        ca["division"] = (code[ca.index] - 400).astype(int)
    elif "STATE_CODE" in cols and "CD_2DIG" in cols:
        ca = div[pd.to_numeric(div[cols["STATE_CODE"]]) == 4].copy()
        ca["division"] = pd.to_numeric(ca[cols["CD_2DIG"]]).astype(int)
    else:
        raise RuntimeError(f"unrecognized division shapefile schema: {list(div.columns)}")
    if len(ca) != config.CA_N_DIVISIONS:
        raise RuntimeError(f"expected {config.CA_N_DIVISIONS} CA divisions, got {len(ca)}")
    return ca[["division", "geometry"]].to_crs(config.AREA_CRS)


def main() -> None:
    gdf = gpd.read_parquet(IN)
    ca = load_ca_divisions()
    log("s05", f"loaded {len(ca)} CA climate divisions")

    no_geom = gdf.geometry.isna() | gdf.geometry.is_empty
    gdf["flag_no_geometry"] = no_geom.astype(bool)

    pts = gpd.GeoDataFrame(
        {"fire_id": gdf["fire_id"]},
        geometry=gdf.geometry.representative_point().where(~no_geom),
        crs=config.AREA_CRS,
    )
    gdf["centroid_pt"] = gdf.geometry.representative_point().where(~no_geom)

    joined = gpd.sjoin(pts[~no_geom], ca, how="left", predicate="within")
    joined = joined[~joined.index.duplicated(keep="first")]  # boundary ties
    division = pd.Series(pd.NA, index=gdf.index, dtype="Int64")
    division.loc[joined.index] = joined["division"].astype("Int64")

    # D-05c: snap leftovers to nearest division
    missing = division.isna() & ~no_geom
    gdf["flag_division_nearest"] = False
    gdf["division_snap_km"] = 0.0
    if missing.any():
        near = gpd.sjoin_nearest(pts[missing], ca, how="left",
                                 distance_col="_dist")
        near = near[~near.index.duplicated(keep="first")]
        division.loc[near.index] = near["division"].astype("Int64")
        gdf.loc[near.index, "flag_division_nearest"] = True
        gdf.loc[near.index, "division_snap_km"] = near["_dist"] / 1000.0
        log("s05", f"snapped {int(missing.sum())} fires to nearest division "
                   f"(max {gdf.loc[near.index, 'division_snap_km'].max():.1f} km)")

    gdf["climate_division"] = division

    # export lon/lat of the representative point for the artifact
    pts_ll = gpd.GeoSeries(gdf["centroid_pt"], crs=config.AREA_CRS).to_crs(config.EXPORT_CRS)
    gdf["rep_point_lon"] = pts_ll.x
    gdf["rep_point_lat"] = pts_ll.y
    gdf = gdf.drop(columns=["centroid_pt"])

    log("s05", "division counts:\n" +
        gdf["climate_division"].value_counts(dropna=False).sort_index().to_string())

    gdf = gdf.sort_values("src_objectid", kind="mergesort").reset_index(drop=True)
    gdf.to_parquet(OUT, index=False)
    log("s05", f"wrote {OUT} ({len(gdf):,} rows)")


if __name__ == "__main__":
    main()
