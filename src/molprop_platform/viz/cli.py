from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="molprop-visualize",
        description=(
            "Create quick, interactive chemical-space plots (PCA/UMAP) from a MolProp results table. "
            "This is a v1 skeleton that intentionally keeps behavior simple and table-first."
        ),
    )
    parser.add_argument("table", help="Input results table (.csv/.tsv/.parquet)")
    parser.add_argument("-o", "--outdir", default="viz", help="Output directory")
    parser.add_argument(
        "--method",
        choices=["pca", "umap"],
        default="pca",
        help="Projection method",
    )
    parser.add_argument(
        "--id-col",
        default="Compound_ID",
        help="ID column to carry through into the projection table",
    )

    args = parser.parse_args()

    from molprop_platform.viz.core import build_projection

    outdir = Path(args.outdir)
    res = build_projection(
        args.table,
        outdir=outdir,
        method=args.method,
        id_col=args.id_col,
    )

    print(f"Wrote: {res.projection_csv}")
    print(f"Wrote: {res.projection_html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
