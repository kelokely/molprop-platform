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

    try:
        import pandas as pd
        import plotly.express as px
        from sklearn.decomposition import PCA

        if args.method == "umap":
            import umap  # type: ignore
    except Exception as e:
        raise SystemExit(
            "Visualization dependencies not installed. Install with: "
            "pip install -e '.[viz]'"
        ) from e

    # Prefer molprop-toolkit table reader when available.
    try:
        from molprop_toolkit.core import read_table as core_read_table  # type: ignore

        df = core_read_table(args.table)
    except Exception:
        from molprop_platform.core.io import read_table

        df = read_table(args.table)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # Select numeric columns only; drop obviously non-feature columns.
    numeric = df.select_dtypes(include=["number"]).copy()
    if numeric.shape[1] < 2:
        raise SystemExit(
            "Not enough numeric columns to project. Provide a results table with descriptors."
        )

    X = numeric.to_numpy(dtype=float)

    if args.method == "pca":
        model = PCA(n_components=2, random_state=0)
        coords = model.fit_transform(X)
        xname, yname = "PCA_1", "PCA_2"
    else:
        model = umap.UMAP(n_components=2, random_state=0)
        coords = model.fit_transform(X)
        xname, yname = "UMAP_1", "UMAP_2"

    proj = pd.DataFrame({xname: coords[:, 0], yname: coords[:, 1]})
    if args.id_col in df.columns:
        proj.insert(0, args.id_col, df[args.id_col].astype(str).values)

    proj_path = outdir / f"projection_{args.method}.csv"
    proj.to_csv(proj_path, index=False)

    fig = px.scatter(
        proj,
        x=xname,
        y=yname,
        hover_name=args.id_col if args.id_col in proj.columns else None,
        title=f"MolProp Platform — {args.method.upper()} projection",
    )

    html_path = outdir / f"projection_{args.method}.html"
    fig.write_html(str(html_path), include_plotlyjs="cdn")

    print(f"Wrote: {proj_path}")
    print(f"Wrote: {html_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
