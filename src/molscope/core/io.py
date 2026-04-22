from __future__ import annotations

from pathlib import Path

import pandas as pd


def read_table(path: str | Path) -> pd.DataFrame:
    """Read CSV/TSV/Parquet into a DataFrame.

    This intentionally keeps a small local reader in place so MolScope can still
    open tables before the toolkit is installed in the same environment.

    When the toolkit is available, the shared MolScope table reader remains the
    better source of truth.
    """

    p = Path(path)
    suffix = p.suffix.lower()

    if suffix == ".parquet":
        return pd.read_parquet(p)
    if suffix in (".csv", ".txt"):
        return pd.read_csv(p)
    if suffix == ".tsv":
        return pd.read_csv(p, sep="\t")

    raise ValueError(f"Unsupported input format: {p}")


def write_table(df: pd.DataFrame, path: str | Path) -> None:
    p = Path(path)
    suffix = p.suffix.lower()

    if suffix == ".parquet":
        df.to_parquet(p, index=False)
        return
    if suffix == ".csv":
        df.to_csv(p, index=False)
        return
    if suffix == ".tsv":
        df.to_csv(p, sep="\t", index=False)
        return

    raise ValueError(f"Unsupported output format: {p}")
