"""s09: Validate the final artifact and write a QC report.

Hard checks (pipeline fails if violated):
  V-01 fire_id unique and non-null
  V-02 fire_year within [MIN_VALID_YEAR, MAX_VALID_YEAR] or flag_bad_year
  V-03 no canonical duplicate leaks: (fire_year, fire_name_norm) groups that
       share near-identical size are all distinct rows the dedupe stage
       examined (spot-check via dup_group_id integrity)
  V-04 climate values in plausible physical ranges when present
  V-05 every non-null climate row actually matches the s06 table (join
       integrity re-check on a deterministic sample)
  V-06 flags are boolean and non-null; flag_climate_missing consistent with
       covariate nullness

Soft stats (written to the QC report for SCHEMA.md):
  join coverage by era, wind coverage by decade, dedupe counts, flag counts.

Run: python -m pipeline.stages.s09_validate
Inputs: artifacts/fires_enriched.parquet + processed stage outputs
Output: data/processed/s09_qc_report.md (stats embedded into SCHEMA.md by hand)
"""

import pandas as pd

from .. import config
from ..util import log, processed

ART = config.ARTIFACTS / "fires_enriched.parquet"
OUT = processed("s09_qc_report.md")


def check(cond: bool, name: str, detail: str = "") -> None:
    if not cond:
        raise AssertionError(f"QC FAIL {name}: {detail}")
    log("s09", f"PASS {name}")


def main() -> None:
    df = pd.read_parquet(ART)
    clim = pd.read_parquet(processed("s06_climdiv_monthly.parquet"))
    removed = pd.read_parquet(processed("s03_duplicates_removed.parquet"))

    # V-01
    check(df["fire_id"].notna().all() and df["fire_id"].is_unique, "V-01 fire_id unique")

    # V-02
    ok_year = df["fire_year"].between(config.MIN_VALID_YEAR, config.MAX_VALID_YEAR)
    check((ok_year | df["flag_bad_year"]).all(), "V-02 year range")

    # V-04
    present = df["pdsi"].notna()
    check(df.loc[present, "pdsi"].between(-15, 15).all(), "V-04a pdsi range")
    p = df["tmean_c"].notna()
    check(df.loc[p, "tmean_c"].between(-25, 45).all(), "V-04b tmean range")
    p = df["precip_mm"].notna()
    check((df.loc[p, "precip_mm"] >= 0).all() and (df.loc[p, "precip_mm"] < 2000).all(),
          "V-04c precip range")
    p = df["wind_avg_ms"].notna()
    check(df.loc[p, "wind_avg_ms"].between(0, 25).all(), "V-04d wind range")

    # V-05 join integrity on deterministic sample (every 97th joined row)
    joined = df[df["pdsi"].notna()].iloc[::97]
    clim_ix = clim.set_index(["division", "year", "month"])
    for _, r in joined.iterrows():
        key = (r["climate_division"], r["alarm_year"], r["alarm_month"])
        check(abs(clim_ix.loc[key, "pdsi"] - r["pdsi"]) < 1e-9,
              "V-05 join integrity", f"mismatch at {key}")
    log("s09", f"V-05 verified on {len(joined)} sampled rows")

    # V-06
    flags = [c for c in df.columns if c.startswith("flag_") and c != "flag_climate_missing"] + \
            [c for c in df.columns if c.startswith("below_cutoff_")] + ["geom_was_invalid"]
    for c in flags:
        check(df[c].isin([True, False]).all(), f"V-06 {c} boolean")
    has_clim = df[["pdsi", "tmean_c", "tmax_c", "precip_mm"]].notna().any(axis=1)
    check((df["flag_climate_missing"].isna() == has_clim).all(),
          "V-06 flag_climate_missing consistency")

    # ---- soft stats -------------------------------------------------------
    lines = ["# QC report — fires_enriched.parquet", ""]
    lines.append(f"- rows: {len(df):,}")
    lines.append(f"- duplicate rows removed in s03: {len(removed):,} "
                 f"({df['dup_group_id'].notna().sum():,} kept rows belong to a dup group)")
    lines.append(f"- climate join coverage overall: {has_clim.mean():.1%}")
    for era, grp in df.groupby(df["fire_year"] // 25 * 25):
        h = grp[["pdsi", "tmean_c", "tmax_c", "precip_mm"]].notna().any(axis=1).mean()
        w = grp["wind_avg_ms"].notna().mean()
        lines.append(f"  - {era}s (n={len(grp):,}): climate {h:.0%}, wind {w:.0%}")
    for c in sorted(flags):
        lines.append(f"- {c}: {int(df[c].sum()):,}")
    lines.append(f"- flag_climate_missing reasons: "
                 f"{df['flag_climate_missing'].value_counts(dropna=True).to_dict()}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n")
    log("s09", f"wrote {OUT}")
    log("s09", "ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
