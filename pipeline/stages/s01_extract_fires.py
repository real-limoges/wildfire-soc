"""s01: Extract the FRAP wildfire perimeter layer from the pinned geodatabase.

Reads the firep25_1 layer verbatim — no value changes — and writes a
GeoParquet snapshot so later stages never re-touch the gdb. The only
transformations here are representational:
  * geometry kept in the native CRS (EPSG:3310, California Albers)
  * invalid geometries repaired with shapely make_valid(), recorded in
    `geom_was_invalid` (repair changes topology encoding, not the drawn shape)
  * a stable row identifier `src_objectid` from the gdb OBJECTID

Run: python -m pipeline.stages.s01_extract_fires
Input: data/raw/frap/fire25_1.gdb
Output: data/processed/s01_fires_raw.parquet
"""

import geopandas as gpd
from shapely.validation import make_valid

from .. import config
from ..util import log, processed

OUT = processed("s01_fires_raw.parquet")


def main() -> None:
    gdf = gpd.read_file(config.FRAP_GDB, layer=config.FRAP_FIRE_LAYER,
                        fid_as_index=True)
    gdf = gdf.reset_index().rename(columns={"fid": "src_objectid"})
    log("s01", f"read {len(gdf):,} features from {config.FRAP_FIRE_LAYER}; "
               f"CRS={gdf.crs}")

    if gdf.crs is None or gdf.crs.to_epsg() != 3310:
        gdf = gdf.to_crs(config.AREA_CRS)
        log("s01", "reprojected to EPSG:3310")

    invalid = ~gdf.geometry.is_valid & gdf.geometry.notna()
    gdf["geom_was_invalid"] = invalid.fillna(False)
    if invalid.any():
        gdf.loc[invalid, "geometry"] = gdf.loc[invalid, "geometry"].apply(make_valid)
        log("s01", f"repaired {int(invalid.sum())} invalid geometries (make_valid)")

    gdf = gdf.sort_values("src_objectid", kind="mergesort").reset_index(drop=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_parquet(OUT, index=False)
    log("s01", f"wrote {OUT} ({len(gdf):,} rows)")


if __name__ == "__main__":
    main()
