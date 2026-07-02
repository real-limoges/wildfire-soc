"""s06: Parse NOAA nClimDiv divisional monthly files into a tidy table.

Produces one row per (division, year, month) for California with PDSI, mean
temperature, mean daily-max temperature, and precipitation.

Decisions (cross-referenced in SCHEMA.md):
  D-06a Source is nClimDiv *divisional* data — the official monthly series
        published at exactly the climate-division unit used for the join.
  D-06b Missing-value sentinels (-99.99 for pdsi/pcpn, -99.90 for temps —
        any value <= -99 after parsing) become NULL, never zero.
  D-06c Units converted at this boundary and only here: temperatures
        deg F -> deg C, precipitation inches -> mm. PDSI is unitless.
  D-06d Rows are kept for 1878-onward only where the fire dataset needs
        them; nClimDiv itself starts in 1895, so fires 1878-1894 will have
        NULL climate covariates (documented gap, flag_climate_missing in s08).

File format (per NOAA README): whitespace-separated records
  <SSDDEEYYYY> v_jan v_feb ... v_dec
where SS=state code (CA=04), DD=division (01-07), EE=element, YYYY=year.

Run: python -m pipeline.stages.s06_build_climdiv
Inputs: data/raw/climdiv/climdiv-{pdsidv,tmpcdv,tmaxdv,pcpndv}.txt
Output: data/processed/s06_climdiv_monthly.parquet
"""

import pandas as pd

from .. import config
from ..util import log, write_parquet, processed

OUT = processed("s06_climdiv_monthly.parquet")

MISSING_CUTOFF = -99.0  # D-06b


def parse_climdiv(path, state_code: str) -> pd.DataFrame:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            parts = line.split()
            if len(parts) != 13:
                continue
            ident = parts[0]
            # 10-digit ID: SSDDEEYYYY (state may print as 3 digits for
            # some non-CONUS codes; CA is always '04' + 2-digit division)
            if len(ident) != 10 or ident[0:2] != state_code:
                continue
            div = int(ident[2:4])
            year = int(ident[6:10])
            for m in range(12):
                v = float(parts[1 + m])
                rows.append((div, year, m + 1, None if v <= MISSING_CUTOFF else v))
    return pd.DataFrame(rows, columns=["division", "year", "month", "value"])


def main() -> None:
    frames = {}
    for var, path in config.CLIMDIV_FILES.items():
        df = parse_climdiv(path, config.CA_CLIMDIV_STATE_CODE)
        if df.empty:
            raise RuntimeError(f"no CA records parsed from {path}")
        frames[var] = df.set_index(["division", "year", "month"])["value"]
        log("s06", f"{var}: {df['value'].notna().sum():,} non-null CA "
                   f"division-months, {df['year'].min()}–{df['year'].max()}")

    out = pd.DataFrame(frames).reset_index()

    # D-06c: unit conversions at this boundary only
    out["pdsi"] = out.pop("pdsi") if "pdsi" in out else pd.NA
    out["tmean_c"] = (out.pop("tmpc") - 32.0) * 5.0 / 9.0
    out["tmax_c"] = (out.pop("tmax") - 32.0) * 5.0 / 9.0
    out["precip_mm"] = out.pop("pcpn") * 25.4

    out = out[(out["division"] >= 1) & (out["division"] <= config.CA_N_DIVISIONS)]
    out["division"] = out["division"].astype("int8")
    out["year"] = out["year"].astype("int16")
    out["month"] = out["month"].astype("int8")

    # trailing months of the current year are all-null placeholders — drop
    # rows where every climate value is missing
    vals = ["pdsi", "tmean_c", "tmax_c", "precip_mm"]
    out = out[~out[vals].isna().all(axis=1)]

    write_parquet(out, OUT, sort_by=["division", "year", "month"])


if __name__ == "__main__":
    main()
