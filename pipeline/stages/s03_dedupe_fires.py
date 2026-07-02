"""s03: Identify and collapse duplicate perimeters — explicitly, with receipts.

FRAP is a multi-agency compilation, so the same fire sometimes appears more
than once (submitted by two agencies, re-digitized, or carried forward from
an old release). Decisions implemented here (cross-referenced in SCHEMA.md):

  D-03a Candidate duplicate pairs are rows with the same fire_year that share
        (i) the same non-null irwin_id, OR
        (ii) the same non-null fire_name_norm, OR
        (iii) byte-identical geometry (WKB hash).
  D-03b A candidate pair is confirmed as duplicate when geometries agree:
        IoU > config.DUP_IOU_THRESHOLD, or the smaller geometry is
        > config.DUP_CONTAINMENT contained in the larger, or WKB-identical.
        (Name/IRWIN match alone is NOT enough — many distinct fires share
        names like "GRASS" across units within a year.)
  D-03c Confirmed duplicates are grouped transitively (union-find). One
        canonical row is kept per group: most non-null core attributes,
        then largest gis_acres, then lowest src_objectid (deterministic).
  D-03d Non-canonical rows are REMOVED from the main table but written in
        full to data/processed/s03_duplicates_removed.parquet with their
        dup_group_id and the fire_id of the kept row — nothing disappears
        silently. Canonical rows keep dup_group_id + n_duplicates_removed.

Run: python -m pipeline.stages.s03_dedupe_fires
Input: data/processed/s02_fires_clean.parquet
Outputs: data/processed/s03_fires_deduped.parquet,
         data/processed/s03_duplicates_removed.parquet
"""

import hashlib
from collections import defaultdict
from itertools import combinations

import geopandas as gpd
import pandas as pd

from .. import config
from ..util import log, processed

IN = processed("s02_fires_clean.parquet")
OUT = processed("s03_fires_deduped.parquet")
OUT_REMOVED = processed("s03_duplicates_removed.parquet")

CORE_ATTRS = ["fire_name", "alarm_date", "cont_date", "cause", "agency",
              "unit_id", "inc_num", "irwin_id", "gis_acres", "objective"]


class UnionFind:
    def __init__(self):
        self.parent = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def _geom_agree(ga, gb) -> bool:
    """D-03b: do two geometries describe the same burned area?"""
    if ga is None or gb is None or ga.is_empty or gb.is_empty:
        return False
    if ga.equals_exact(gb, tolerance=0):
        return True
    inter = ga.intersection(gb).area
    if inter == 0:
        return False
    union = ga.area + gb.area - inter
    iou = inter / union if union > 0 else 0.0
    contain = inter / min(ga.area, gb.area) if min(ga.area, gb.area) > 0 else 0.0
    return iou > config.DUP_IOU_THRESHOLD or contain > config.DUP_CONTAINMENT


def main() -> None:
    gdf = gpd.read_parquet(IN)
    n0 = len(gdf)
    gdf["_wkb_hash"] = gdf.geometry.apply(
        lambda g: hashlib.sha1(g.wkb).hexdigest() if g is not None else None)

    # --- D-03a: candidate pairs -------------------------------------------
    uf = UnionFind()
    pairs_checked = 0
    confirmed = 0

    def add_candidates(groups):
        nonlocal pairs_checked, confirmed
        for _, idx in groups:
            idx = list(idx)
            if len(idx) < 2 or len(idx) > 50:  # >50 same-name rows in a year
                continue                        # would be a data pathology; none expected
            for i, j in combinations(idx, 2):
                pairs_checked += 1
                if _geom_agree(gdf.geometry.iloc[i], gdf.geometry.iloc[j]):
                    uf.union(gdf.index[i], gdf.index[j])
                    confirmed += 1

    with_year = gdf[gdf["fire_year"].notna()]
    by_irwin = with_year[with_year["irwin_id"].notna()].groupby(
        ["fire_year", "irwin_id"]).indices.items()
    add_candidates(((k, v) for k, v in by_irwin))
    by_name = with_year[with_year["fire_name_norm"].notna()].groupby(
        ["fire_year", "fire_name_norm"]).indices.items()
    add_candidates(((k, v) for k, v in by_name))

    # identical WKB in the same year always collapses, name or not
    by_wkb = with_year[with_year["_wkb_hash"].notna()].groupby(
        ["fire_year", "_wkb_hash"]).indices.items()
    for _, idx in by_wkb:
        idx = list(idx)
        for i, j in zip(idx, idx[1:]):
            uf.union(gdf.index[i], gdf.index[j])
            confirmed += 1

    log("s03", f"checked {pairs_checked:,} candidate pairs, "
               f"{confirmed:,} confirmed duplicate links")

    # --- D-03c: pick canonical row per group -------------------------------
    groups = defaultdict(list)
    for lbl in uf.parent:
        groups[uf.find(lbl)].append(lbl)
    groups = {root: sorted(members) for root, members in groups.items()
              if len(members) > 1}

    completeness = gdf[CORE_ATTRS].notna().sum(axis=1)
    keep_flags = pd.Series(True, index=gdf.index)
    group_id = pd.Series(pd.NA, index=gdf.index, dtype="string")
    kept_fire_id = pd.Series(pd.NA, index=gdf.index, dtype="string")
    n_removed_for = pd.Series(0, index=gdf.index)

    for gnum, (root, members) in enumerate(sorted(groups.items())):
        ranked = sorted(members, key=lambda ix: (
            -completeness.loc[ix],
            -(gdf.loc[ix, "gis_acres"] if pd.notna(gdf.loc[ix, "gis_acres"]) else -1),
            gdf.loc[ix, "src_objectid"],
        ))
        keep = ranked[0]
        gid = f"dup-{gnum:05d}"
        for ix in members:
            group_id.loc[ix] = gid
            kept_fire_id.loc[ix] = gdf.loc[keep, "fire_id"]
        for ix in ranked[1:]:
            keep_flags.loc[ix] = False
        n_removed_for.loc[keep] = len(members) - 1

    gdf["dup_group_id"] = group_id
    gdf["n_duplicates_removed"] = n_removed_for
    removed = gdf[~keep_flags].copy()
    removed["kept_fire_id"] = kept_fire_id[~keep_flags]
    kept = gdf[keep_flags].copy()

    log("s03", f"{len(groups)} duplicate groups; removed {len(removed)} rows; "
               f"kept {len(kept):,}/{n0:,}")

    kept = kept.drop(columns=["_wkb_hash"]).sort_values(
        "src_objectid", kind="mergesort").reset_index(drop=True)
    removed = removed.drop(columns=["_wkb_hash"]).sort_values(
        "src_objectid", kind="mergesort").reset_index(drop=True)
    kept.to_parquet(OUT, index=False)
    removed.to_parquet(OUT_REMOVED, index=False)
    log("s03", f"wrote {OUT} and {OUT_REMOVED}")


if __name__ == "__main__":
    main()
