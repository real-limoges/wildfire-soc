"""Shared helpers: deterministic parquet IO, hashing, logging."""

import hashlib
import sys

import pandas as pd

from . import config


def log(stage: str, msg: str) -> None:
    print(f"[{stage}] {msg}", file=sys.stderr)


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_parquet(df: pd.DataFrame, path, sort_by=None) -> None:
    """Write a DataFrame as parquet with deterministic content.

    Rows are sorted by a stable key and the RangeIndex is dropped so that
    re-running a stage on identical inputs yields byte-identical output.
    """
    if sort_by:
        df = df.sort_values(sort_by, kind="mergesort").reset_index(drop=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False, engine="pyarrow")
    log("io", f"wrote {path} ({len(df):,} rows, sha256 {sha256_file(path)[:12]}…)")


def read_parquet(path) -> pd.DataFrame:
    return pd.read_parquet(path, engine="pyarrow")


def processed(name: str):
    return config.PROCESSED / name
