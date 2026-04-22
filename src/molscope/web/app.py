from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any

import streamlit as st
import streamlit.components.v1 as components

from molscope.commands import COMMAND_SPECS, COMMANDS_BY_NAME
from molscope.core import read_table
from molscope.toolkit import command_available, split_args
from molscope.viz.core import build_projection
from molscope.web.runner import (
    RunContext,
    detect_input_kind,
    make_run_dir,
    resolve_workspace_path,
    run_generate_pipeline,
    run_toolkit_subcommand,
    save_uploaded_file,
    workspace_directories,
    workspace_files,
    workspace_smiles,
    workspace_tables,
    write_run_metadata,
    zip_run_directory,
)

st.set_page_config(page_title="MolScope", layout="wide")


OUTPUT_FLAGS = {
    "calc": "-o",
    "prep": "-o",
    "analyze": "-o",
    "report": "--outdir",
    "picklists": "--outdir",
    "integrate": "-o",
    "compare": "-o",
    "sar": "-o",
    "mmp": "-o",
    "search": "-o",
    "series": "--outdir",
    "similarity": "--output",
    "featurize": "-o",
    "retro": "--outdir",
    "learnings": "-o",
    "dashboard": "-o",
    "portal": "-o",
}


def _set_workspace(ctx: RunContext) -> None:
    st.session_state["molscope_workspace_dir"] = str(ctx.run_dir)
    st.session_state["molscope_workspace_created_at"] = ctx.created_at
    st.session_state["molscope_last_action"] = None


def _current_workspace() -> RunContext:
    raw_dir = st.session_state.get("molscope_workspace_dir")
    created_at = st.session_state.get("molscope_workspace_created_at")
    if raw_dir:
        run_dir = Path(str(raw_dir))
        if run_dir.exists():
            return RunContext(run_dir=run_dir, created_at=float(created_at or 0.0))
    ctx = make_run_dir()
    _set_workspace(ctx)
    return ctx


def _new_workspace() -> None:
    ctx = make_run_dir()
    _set_workspace(ctx)


def _record_action(payload: dict[str, Any]) -> None:
    st.session_state["molscope_last_action"] = payload


def _unpack_zip(zip_path: Path, target_dir: Path) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as archive:
        archive.extractall(target_dir)
    return target_dir


def _handle_uploads(ctx: RunContext, uploads: list[Any]) -> list[str]:
    saved: list[str] = []
    for uploaded in uploads:
        destination = ctx.run_dir / "inputs" / uploaded.name
        saved_path = save_uploaded_file(uploaded, destination)
        saved.append(str(saved_path.relative_to(ctx.run_dir)))
        if saved_path.suffix.lower() == ".zip":
            _unpack_zip(saved_path, saved_path.with_suffix(""))
    return saved


def _status_row() -> None:
    pairs = [
        ("Toolkit CLI", "calc"),
        ("Report", "report"),
        ("Picklists", "picklists"),
        ("Compare", "compare"),
        ("Portal", "portal"),
    ]
    columns = st.columns(len(pairs))
    for column, (label, command_name) in zip(columns, pairs, strict=True):
        with column:
            st.write(f"**{label}**")
            st.write("Ready" if command_available(command_name) else "Missing")


def _preview_table(path: Path) -> None:
    try:
        df = read_table(path)
    except Exception as exc:
        st.warning(str(exc))
        return
    st.write(f"{len(df):,} rows × {len(df.columns):,} columns")
    st.dataframe(df.head(25), use_container_width=True)


def _render_last_action(ctx: RunContext) -> None:
    payload = st.session_state.get("molscope_last_action")
    if not payload:
        return
    st.divider()
    st.subheader("Last run")
    st.write(payload.get("title", "MolScope"))
    if payload.get("summary"):
        st.write(payload["summary"])
    if payload.get("paths"):
        for label, value in payload["paths"]:
            st.write(f"{label}: `{value}`")
    if payload.get("tail"):
        st.text_area("Log tail", payload["tail"], height=220)
    if payload.get("html_path"):
        html_path = resolve_workspace_path(ctx, payload["html_path"])
        if html_path.exists():
            components.html(html_path.read_text(encoding="utf-8"), height=600, scrolling=True)


def _single_command_args(ctx: RunContext, command_name: str) -> tuple[list[str], str] | None:
    files = workspace_files(ctx)
    if not files:
        st.info("Add files to the workspace first.")
        return None
    selected = st.selectbox("Input file", files, key=f"{command_name}_input")
    output_override = st.text_input(
        "Output path",
        value="",
        key=f"{command_name}_output",
        placeholder="Leave blank to use the command default",
    )
    extra_args = st.text_input(
        "Extra arguments",
        value="",
        key=f"{command_name}_extra",
        placeholder="Optional",
    )
    args = [str(resolve_workspace_path(ctx, selected))]
    output_flag = OUTPUT_FLAGS.get(command_name)
    if output_override.strip() and output_flag:
        args.extend([output_flag, output_override.strip()])
    if command_name == "picklists":
        write_html = st.checkbox("Write HTML", value=True, key="picklists_html")
        if write_html:
            args.append("--html")
    args.extend(split_args(extra_args))
    return args, selected


def _pair_command_args(ctx: RunContext, command_name: str) -> tuple[list[str], str] | None:
    tables = workspace_tables(ctx)
    if len(tables) < 2:
        st.info("Add at least two tables to the workspace first.")
        return None
    first = st.selectbox("First table", tables, key=f"{command_name}_first")
    second_options = [table for table in tables if table != first]
    second = st.selectbox("Second table", second_options, key=f"{command_name}_second")
    output_override = st.text_input(
        "Output path",
        value="",
        key=f"{command_name}_output",
        placeholder="Leave blank to use the command default",
    )
    extra_args = st.text_input(
        "Extra arguments",
        value="",
        key=f"{command_name}_extra",
        placeholder="Optional",
    )
    args = [
        str(resolve_workspace_path(ctx, first)),
        str(resolve_workspace_path(ctx, second)),
    ]
    output_flag = OUTPUT_FLAGS.get(command_name)
    if output_override.strip() and output_flag:
        args.extend([output_flag, output_override.strip()])
    args.extend(split_args(extra_args))
    return args, f"{first} and {second}"


def _learnings_args(ctx: RunContext) -> tuple[list[str], str] | None:
    dirs = workspace_directories(ctx)
    if not dirs:
        st.info("Run compare, SAR, MMP, or picklists first, or unpack an artifact zip into the workspace.")
        return None
    compare_dir = st.selectbox("Compare directory", ["", *dirs], key="learnings_compare")
    sar_dir = st.selectbox("SAR directory", ["", *dirs], key="learnings_sar")
    mmp_dir = st.selectbox("MMP directory", ["", *dirs], key="learnings_mmp")
    picklists_dir = st.selectbox("Picklists directory", ["", *dirs], key="learnings_picklists")
    title = st.text_input("Title", value="", key="learnings_title")
    output_override = st.text_input(
        "Output path",
        value="",
        key="learnings_output",
        placeholder="Leave blank to use the command default",
    )
    args: list[str] = []
    if compare_dir:
        args.extend(["--compare-dir", str(resolve_workspace_path(ctx, compare_dir))])
    if sar_dir:
        args.extend(["--sar-dir", str(resolve_workspace_path(ctx, sar_dir))])
    if mmp_dir:
        args.extend(["--mmp-dir", str(resolve_workspace_path(ctx, mmp_dir))])
    if picklists_dir:
        args.extend(["--picklists-dir", str(resolve_workspace_path(ctx, picklists_dir))])
    if title.strip():
        args.extend(["--title", title.strip()])
    if output_override.strip():
        args.extend(["-o", output_override.strip()])
    if not args:
        st.info("Pick at least one artifact directory.")
        return None
    return args, "selected artifact directories"


def _dashboard_args(ctx: RunContext) -> tuple[list[str], str] | None:
    dirs = workspace_directories(ctx)
    if not dirs:
        st.info("Add or build at least one learnings directory first.")
        return None
    selected_dirs = st.multiselect("Learnings directories", dirs, key="dashboard_dirs")
    title = st.text_input("Title", value="", key="dashboard_title")
    output_override = st.text_input(
        "Output path",
        value="",
        key="dashboard_output",
        placeholder="Leave blank to use the command default",
    )
    args: list[str] = []
    for directory in selected_dirs:
        args.extend(["--learnings-dir", str(resolve_workspace_path(ctx, directory))])
    if title.strip():
        args.extend(["--title", title.strip()])
    if output_override.strip():
        args.extend(["-o", output_override.strip()])
    if not args:
        st.info("Pick at least one learnings directory.")
        return None
    return args, ", ".join(selected_dirs)


def _portal_args(ctx: RunContext) -> tuple[list[str], str] | None:
    dirs = workspace_directories(ctx)
    if not dirs:
        st.info("Add or build at least one artifact directory first.")
        return None
    mapping = {
        "Report directory": ("--report-dir", st.selectbox("Report directory", ["", *dirs], key="portal_report")),
        "Picklists directory": ("--picklists-dir", st.selectbox("Picklists directory", ["", *dirs], key="portal_picklists")),
        "Compare directory": ("--compare-dir", st.selectbox("Compare directory", ["", *dirs], key="portal_compare")),
        "Learnings directory": ("--learnings-dir", st.selectbox("Learnings directory", ["", *dirs], key="portal_learnings")),
        "Dashboard directory": ("--dashboard-dir", st.selectbox("Dashboard directory", ["", *dirs], key="portal_dashboard")),
        "SAR directory": ("--sar-dir", st.selectbox("SAR directory", ["", *dirs], key="portal_sar")),
        "MMP directory": ("--mmp-dir", st.selectbox("MMP directory", ["", *dirs], key="portal_mmp")),
        "Retro directory": ("--retro-dir", st.selectbox("Retro directory", ["", *dirs], key="portal_retro")),
    }
    title = st.text_input("Title", value="", key="portal_title")
    output_override = st.text_input(
        "Output path",
        value="",
        key="portal_output",
        placeholder="Leave blank to use the command default",
    )
    args: list[str] = []
    chosen: list[str] = []
    for label, (flag, selected) in mapping.items():
        if selected:
            args.extend([flag, str(resolve_workspace_path(ctx, selected))])
            chosen.append(label)
    if title.strip():
        args.extend(["--title", title.strip()])
    if output_override.strip():
        args.extend(["-o", output_override.strip()])
    if not chosen:
        st.info("Pick at least one artifact directory.")
        return None
    return args, ", ".join(chosen)


ctx = _current_workspace()

st.title("MolScope")
st.caption("Run the MolScope workflow from one workspace.")

with st.sidebar:
    st.subheader("Workspace")
    st.write(f"`{ctx.run_dir}`")
    if st.button("New workspace"):
        _new_workspace()
        st.rerun()
    st.download_button(
        "Download workspace",
        data=zip_run_directory(ctx),
        file_name=f"{ctx.run_dir.name}.zip",
        mime="application/zip",
    )

_status_row()

tab_workspace, tab_generate, tab_commands, tab_visualize, tab_about = st.tabs(
    ["Workspace", "Generate", "Commands", "Visualize", "About"]
)

with tab_workspace:
    uploads = st.file_uploader(
        "Add files",
        accept_multiple_files=True,
        type=["smi", "smiles", "csv", "tsv", "parquet", "json", "txt", "zip"],
    )
    if uploads:
        saved = _handle_uploads(ctx, list(uploads))
        if saved:
            st.success(f"Saved {len(saved)} file(s).")

    files = workspace_files(ctx)
    dirs = workspace_directories(ctx)

    left, right = st.columns([1, 1])
    with left:
        st.subheader("Files")
        if files:
            for rel in files:
                kind = detect_input_kind(resolve_workspace_path(ctx, rel))
                st.write(f"`{rel}` · {kind}")
        else:
            st.write("No files yet.")
    with right:
        st.subheader("Directories")
        if dirs:
            for rel in dirs:
                st.write(f"`{rel}`")
        else:
            st.write("No directories yet.")

    tables = workspace_tables(ctx)
    if tables:
        st.subheader("Preview")
        preview_target = st.selectbox("Table", tables, key="preview_table")
        _preview_table(resolve_workspace_path(ctx, preview_target))

with tab_generate:
    smiles_files = workspace_smiles(ctx)
    if not smiles_files:
        st.info("Add a SMILES file in the Workspace tab first.")
    else:
        smiles_input = st.selectbox("SMILES file", smiles_files, key="generate_smiles")
        profile = st.selectbox("Profile", ["extended", "baseline"], index=0)
        out_format = st.selectbox("Output format", ["parquet", "csv"], index=0)
        col1, col2, col3 = st.columns(3)
        with col1:
            build_report = st.checkbox("Build report", value=True)
        with col2:
            build_picklists = st.checkbox("Build picklists", value=False)
        with col3:
            build_viz = st.checkbox("Build quick projection", value=True)

        calc_extra = st.text_input("Calc extra arguments", value="", key="generate_calc_extra")
        report_extra = st.text_input("Report extra arguments", value="", key="generate_report_extra")
        picklists_extra = st.text_input(
            "Picklists extra arguments",
            value="",
            key="generate_picklists_extra",
        )

        if st.button("Run generate pipeline"):
            results = run_generate_pipeline(
                ctx,
                resolve_workspace_path(ctx, smiles_input),
                profile=profile,
                out_format=out_format,
                run_report=build_report,
                run_picklists=build_picklists,
                run_visualize=build_viz,
                extra_args={
                    "calc": calc_extra,
                    "report": report_extra,
                    "picklists": picklists_extra,
                },
            )
            paths: list[tuple[str, str]] = []
            if results.get("results_table"):
                paths.append(("Results table", str(results["results_table"])))
            viz_step = next(
                (step for step in results.get("steps", []) if step.get("name") == "visualize"),
                None,
            )
            html_path = ""
            if viz_step:
                paths.append(("Projection CSV", str(viz_step["projection_csv"])))
                paths.append(("Projection HTML", str(viz_step["projection_html"])))
                html_path = str(Path(viz_step["projection_html"]).relative_to(ctx.run_dir))
            tail = results.get("picklists_log_tail") or results.get("report_log_tail") or results.get("calc_log_tail") or ""
            _record_action(
                {
                    "title": "Generate pipeline",
                    "summary": f"Started from `{smiles_input}`.",
                    "paths": paths,
                    "tail": tail,
                    "html_path": html_path,
                }
            )
            st.success("Pipeline finished.")

with tab_commands:
    command_names = [spec.name for spec in COMMAND_SPECS]
    command_name = st.selectbox("Command", command_names, format_func=lambda name: COMMANDS_BY_NAME[name].title)
    spec = COMMANDS_BY_NAME[command_name]
    st.write(spec.summary)
    ready = command_available(command_name)
    if not ready:
        st.warning("This command is not available in the current environment.")
    args_result: tuple[list[str], str] | None
    if spec.mode == "single":
        args_result = _single_command_args(ctx, command_name)
    elif spec.mode == "pair":
        args_result = _pair_command_args(ctx, command_name)
    elif spec.mode == "learnings":
        args_result = _learnings_args(ctx)
    elif spec.mode == "dashboard":
        args_result = _dashboard_args(ctx)
    else:
        args_result = _portal_args(ctx)

    if ready and args_result and st.button("Run command"):
        args, subject = args_result
        result = run_toolkit_subcommand(ctx, command_name, args, log_name=f"{command_name}.log")
        write_run_metadata(
            ctx,
            {
                "mode": "command",
                "command": command_name,
                "args": args,
                "returncode": result.returncode,
            },
        )
        _record_action(
            {
                "title": f"molscope {command_name}",
                "summary": f"Ran on {subject}.",
                "paths": [("Log", str(result.log_path))],
                "tail": result.tail,
            }
        )
        if result.returncode == 0:
            st.success("Command finished.")
        else:
            st.error("Command failed.")

with tab_visualize:
    tables = workspace_tables(ctx)
    if not tables:
        st.info("Add a table to the workspace first.")
    else:
        table_rel = st.selectbox("Table", tables, key="visualize_table")
        method = st.selectbox("Method", ["pca", "umap"], index=0, key="visualize_method")
        id_col = st.text_input("ID column", value="Compound_ID", key="visualize_id")
        if st.button("Build projection"):
            projection = build_projection(
                resolve_workspace_path(ctx, table_rel),
                outdir=ctx.run_dir / "outputs" / "viz",
                method=method,
                id_col=id_col,
            )
            _record_action(
                {
                    "title": f"{method.upper()} projection",
                    "summary": f"Built from `{table_rel}`.",
                    "paths": [
                        ("Projection CSV", str(projection.projection_csv)),
                        ("Projection HTML", str(projection.projection_html)),
                    ],
                    "html_path": str(projection.projection_html.relative_to(ctx.run_dir)),
                }
            )
            st.success("Projection finished.")

with tab_about:
    st.subheader("How this server works")
    st.write("The server keeps one workspace open at a time.")
    st.write("You can upload inputs, run MolScope commands, inspect outputs, and download the full bundle when you are done.")
    st.write("When the toolkit is installed in the same environment, the server can run the full MolScope workflow from this one interface.")

_render_last_action(ctx)
