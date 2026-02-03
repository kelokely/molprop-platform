from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from molprop_platform.viz.core import build_projection
from molprop_platform.web.runner import (
    detect_input_kind,
    make_run_dir,
    run_command_capture,
    save_uploaded_file,
    try_run_toolkit_pipeline,
    which,
    write_run_metadata,
    zip_run_directory,
)

st.set_page_config(page_title="MolProp Platform", layout="wide")

st.title("MolProp Platform")
st.caption(
    "A table-first companion to MolProp Toolkit. Use the tabs to generate results from SMILES or analyze existing tables."
)


def _status_row() -> None:
    col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
    with col1:
        st.write("**Core calc**")
        st.write("✅" if which("molprop-calc-v5") else "—")
    with col2:
        st.write("**Report**")
        st.write("✅" if which("molprop-report") else "—")
    with col3:
        st.write("**Picklists**")
        st.write("✅" if which("molprop-picklists") else "—")
    with col4:
        st.write("**Viz deps**")
        try:
            import plotly  # noqa: F401
            import sklearn  # noqa: F401

            st.write("✅")
        except Exception:
            st.write("—")


_status_row()

st.markdown("""
Both workflows converge on the same artifact: a MolProp results table (CSV/Parquet) plus a run folder containing logs,
plots, and optional reports. The safest long-term interface between **molprop-toolkit** and **molprop-platform** is
**table-in/table-out**.
""")


tab_generate, tab_analyze, tab_about = st.tabs(
    ["Generate (SMILES → table)", "Analyze (table → artifacts)", "About"]
)

with tab_generate:
    st.subheader("Generate a results table from SMILES")
    st.caption(
        "This mode calls MolProp Toolkit console scripts. If `molprop-calc-v5` is missing, install platform with `.[core]`."
    )

    enabled = which("molprop-calc-v5") is not None
    if not enabled:
        st.warning(
            "Calculator mode is disabled because `molprop-calc-v5` is not available in this environment. "
            "Install with: pip install -e '.[core,web]'"
        )

    uploaded = st.file_uploader(
        "Upload a SMILES file (.smi)",
        type=["smi", "smiles"],
        disabled=not enabled,
        help="One SMILES per line (optionally with an ID column).",
    )

    c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
    with c1:
        out_format = st.selectbox("Output format", ["parquet", "csv"], index=0)
    with c2:
        do_report = st.checkbox("Build report", value=True)
    with c3:
        do_picklists = st.checkbox("Picklists (HTML)", value=False)
    with c4:
        do_viz = st.checkbox("Quick viz (PCA)", value=True)

    run_btn = st.button("Run pipeline", disabled=(uploaded is None) or (not enabled))

    if run_btn and uploaded is not None:
        ctx = make_run_dir()
        in_path = save_uploaded_file(
            uploaded, ctx.run_dir / "inputs" / Path(uploaded.name).name
        )

        st.info(f"Run directory: {ctx.run_dir}")
        st.write(f"Detected input kind: {detect_input_kind(in_path)}")

        with st.spinner("Running pipeline..."):
            try:
                res = try_run_toolkit_pipeline(
                    ctx,
                    in_path,
                    out_format=out_format,
                    run_report=do_report,
                    run_picklists=do_picklists,
                    run_visualize=do_viz,
                )
                write_run_metadata(
                    ctx,
                    {
                        "mode": "generate",
                        "input": str(in_path),
                        "pipeline_result": res,
                    },
                )
            except Exception as e:
                write_run_metadata(
                    ctx,
                    {
                        "mode": "generate",
                        "input": str(in_path),
                        "error": repr(e),
                    },
                )
                st.error(str(e))
                res = None

        if res is not None:
            st.success("Pipeline finished")
            if res.get("results_table"):
                st.write(f"Results table: `{res['results_table']}`")

            for key in ["calc_log_tail", "report_log_tail", "picklists_log_tail"]:
                if res.get(key):
                    st.text_area(key, res[key], height=220)

            zip_bytes = zip_run_directory(ctx)
            st.download_button(
                "Download run bundle (zip)",
                data=zip_bytes,
                file_name=f"{ctx.run_dir.name}.zip",
                mime="application/zip",
            )

with tab_analyze:
    st.subheader("Analyze an existing results table")
    st.caption(
        "Upload an existing MolProp results table and generate artifacts like interactive PCA/UMAP plots, reports, and picklists."
    )

    uploaded_tbl = st.file_uploader(
        "Upload a results table (.csv/.tsv/.parquet)",
        type=["csv", "tsv", "parquet"],
    )

    if uploaded_tbl is not None:
        ctx = make_run_dir()
        table_path = save_uploaded_file(
            uploaded_tbl, ctx.run_dir / "inputs" / Path(uploaded_tbl.name).name
        )

        st.success(f"Uploaded: {uploaded_tbl.name}")

        # Lightweight preview
        try:
            if table_path.suffix.lower() == ".parquet":
                df = pd.read_parquet(table_path)
            elif table_path.suffix.lower() == ".tsv":
                df = pd.read_csv(table_path, sep="\t")
            else:
                df = pd.read_csv(table_path)
            st.dataframe(df.head(20), use_container_width=True)
        except Exception:
            st.info(
                "Preview unavailable (file may be large or requires optional dependencies)."
            )

        st.divider()

        st.markdown("### 1) Visualization")
        method = st.selectbox("Projection method", ["pca", "umap"], index=0)
        id_col = st.text_input("ID column", value="Compound_ID")

        viz_btn = st.button("Generate interactive plot")
        if viz_btn:
            with st.spinner("Building projection..."):
                try:
                    outdir = ctx.run_dir / "outputs" / "viz"
                    proj = build_projection(
                        table_path,
                        outdir=outdir,
                        method=method,
                        id_col=id_col,
                    )
                    st.success("Visualization created")
                    st.write(f"HTML: `{proj.projection_html}`")
                    st.write(f"CSV: `{proj.projection_csv}`")
                except Exception as e:
                    st.error(str(e))

        st.divider()

        st.markdown("### 2) Optional: report and picklists (toolkit)")
        report_ok = which("molprop-report") is not None
        pick_ok = which("molprop-picklists") is not None

        c1, c2 = st.columns([1, 1])
        with c1:
            run_report = st.checkbox(
                "Run molprop-report", value=False, disabled=not report_ok
            )
        with c2:
            run_pick = st.checkbox(
                "Run molprop-picklists --html", value=False, disabled=not pick_ok
            )

        run_ops = st.button("Run selected operations")
        if run_ops:
            if run_report:
                cmd = ["molprop-report", str(table_path)]
                rc, tail = run_command_capture(
                    cmd,
                    cwd=ctx.run_dir,
                    log_path=ctx.run_dir / "logs" / "report_existing.log",
                )
                if rc == 0:
                    st.success("Report complete")
                else:
                    st.error("Report failed")
                st.text_area("report log tail", tail, height=220)

            if run_pick:
                cmd = ["molprop-picklists", str(table_path), "--html"]
                rc, tail = run_command_capture(
                    cmd,
                    cwd=ctx.run_dir,
                    log_path=ctx.run_dir / "logs" / "picklists_existing.log",
                )
                if rc == 0:
                    st.success("Picklists complete")
                else:
                    st.error("Picklists failed")
                st.text_area("picklists log tail", tail, height=220)

        write_run_metadata(ctx, {"mode": "analyze", "input": str(table_path)})

        zip_bytes = zip_run_directory(ctx)
        st.download_button(
            "Download run bundle (zip)",
            data=zip_bytes,
            file_name=f"{ctx.run_dir.name}.zip",
            mime="application/zip",
        )

with tab_about:
    st.subheader("About")
    st.markdown("""
MolProp Platform is designed to keep MolProp Toolkit intact by remaining table-first and additive.

If you want the app to run calculators from SMILES, install MolProp Toolkit and RDKit in the same environment. For public installs,
conda-forge is usually the most reliable path for RDKit.
""")
