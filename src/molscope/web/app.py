from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from molscope.commands import COMMAND_SPECS, COMMANDS_BY_NAME
from molscope.core import read_table, write_table
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
    workspace_changes,
    workspace_directories,
    workspace_files,
    workspace_smiles,
    workspace_snapshot,
    workspace_tables,
    write_run_metadata,
    zip_run_directory,
)

st.set_page_config(page_title="MolScope", layout="wide")


@dataclass(frozen=True)
class PropertyFamily:
    key: str
    title: str
    summary: str
    categories: tuple[str, ...]


PROPERTY_FAMILIES: tuple[PropertyFamily, ...] = (
    PropertyFamily(
        "cns",
        "CNS and MPO",
        "CNS MPO, balance, and related ranking signals.",
        ("cns_mpo", "qed"),
    ),
    PropertyFamily(
        "oral",
        "Oral and rules",
        "Oral filters, Ro5 and Ro3, and practical screening rules.",
        ("oral_bioavailability", "rule_of_5", "rule_of_3"),
    ),
    PropertyFamily(
        "safety",
        "Safety and liabilities",
        "Med-chem flags, toxicity, metabolism, hERG, and CYP burden.",
        ("medchem_flags", "toxicity", "metabolism", "herg", "cyp"),
    ),
    PropertyFamily(
        "exposure",
        "Solubility, permeability, and PK",
        "Solubility, permeability, and PK-facing heuristics.",
        ("solubility", "permeability", "pk"),
    ),
    PropertyFamily(
        "lead",
        "Lead and developability",
        "Lead metrics, synthetic accessibility, and developability signals.",
        ("lead", "sa_complexity", "developability"),
    ),
    PropertyFamily(
        "series",
        "Series and shape",
        "Scaffolds, clustering, and optional 3D descriptors.",
        ("scaffolds", "clustering", "shape3d"),
    ),
)


BASE_COLUMNS: tuple[str, ...] = (
    "Compound_ID",
    "ID",
    "Name",
    "SMILES",
    "Input_Canonical_SMILES",
    "Canonical_SMILES",
    "Calc_Canonical_SMILES",
    "Calc_Base_SMILES",
    "Series_ID",
    "Scaffold_ID",
    "Cluster_ID",
    "MolWt",
    "LogP",
    "TPSA",
    "HeavyAtoms",
)


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
        ("Calc", "calc"),
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


def _preview_table(path: Path, *, rows: int = 25) -> None:
    try:
        df = read_table(path)
    except Exception as exc:
        st.warning(str(exc))
        return
    st.write(f"{len(df):,} rows × {len(df.columns):,} columns")
    st.dataframe(df.head(rows), use_container_width=True)


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
    download_paths = payload.get("download_paths") or []
    if download_paths:
        st.write("Downloads")
        for idx, rel in enumerate(download_paths):
            path = resolve_workspace_path(ctx, rel)
            if path.is_dir():
                _download_directory(
                    path,
                    label=f"Download {path.name}",
                    key=f"download_last_dir_{idx}_{path.name}",
                )
            elif path.is_file():
                _download_file(
                    path,
                    label=f"Download {path.name}",
                    key=f"download_last_file_{idx}_{path.name}",
                )
    if payload.get("tail"):
        st.text_area("Log tail", payload["tail"], height=220)
    if payload.get("html_path"):
        html_path = resolve_workspace_path(ctx, payload["html_path"])
        if html_path.exists():
            components.html(
                html_path.read_text(encoding="utf-8"),
                height=600,
                scrolling=True,
            )


def _zip_path(path: Path) -> bytes:
    if path.is_file():
        return path.read_bytes()
    buffer = zipfile.ZipFile
    import io

    handle = io.BytesIO()
    with buffer(handle, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for item in path.rglob("*"):
            if item.is_dir():
                continue
            archive.write(item, arcname=str(item.relative_to(path)))
    handle.seek(0)
    return handle.read()


def _download_file(path: Path, *, label: str, key: str) -> None:
    if path.exists():
        st.download_button(
            label,
            data=path.read_bytes(),
            file_name=path.name,
            mime="application/octet-stream",
            key=key,
        )


def _download_directory(path: Path, *, label: str, key: str) -> None:
    if path.exists() and path.is_dir():
        st.download_button(
            label,
            data=_zip_path(path),
            file_name=f"{path.name}.zip",
            mime="application/zip",
            key=key,
        )


def _normalize_smiles_filename(name: str, prefix: str) -> str:
    cleaned = name.strip() or f"{prefix}.smi"
    if not cleaned.endswith((".smi", ".smiles")):
        cleaned = f"{cleaned}.smi"
    return cleaned


def _save_smiles_text(ctx: RunContext, *, prefix: str, text: str, filename: str) -> str | None:
    body = text.strip()
    if not body:
        return None
    target = ctx.run_dir / "inputs" / _normalize_smiles_filename(filename, prefix)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body.rstrip() + "\n", encoding="utf-8")
    return str(target.relative_to(ctx.run_dir))


def _input_tools(ctx: RunContext, prefix: str) -> None:
    with st.expander("Add input here", expanded=False):
        uploads = st.file_uploader(
            "Upload files",
            accept_multiple_files=True,
            type=["smi", "smiles", "csv", "tsv", "parquet", "json", "txt", "zip"],
            key=f"{prefix}_uploads",
        )
        if st.button("Save uploaded files", key=f"{prefix}_save_uploads"):
            if uploads:
                saved = _handle_uploads(ctx, list(uploads))
                if saved:
                    st.success(f"Saved {len(saved)} file(s).")
            else:
                st.info("Choose at least one file first.")

        smiles_name = st.text_input(
            "SMILES filename",
            value=f"{prefix}.smi",
            key=f"{prefix}_smiles_name",
        )
        smiles_text = st.text_area(
            "Paste SMILES",
            value="",
            height=140,
            key=f"{prefix}_smiles_text",
        )
        if st.button("Save SMILES text", key=f"{prefix}_save_smiles"):
            saved = _save_smiles_text(
                ctx,
                prefix=prefix,
                text=smiles_text,
                filename=smiles_name,
            )
            if saved:
                st.success(f"Saved `{saved}`.")
            else:
                st.info("Paste at least one SMILES line first.")


def _single_command_args(
    ctx: RunContext,
    command_name: str,
) -> tuple[list[str], str] | None:
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


def _pair_command_args(
    ctx: RunContext,
    command_name: str,
) -> tuple[list[str], str] | None:
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
    compare_dir = st.selectbox(
        "Compare directory",
        ["", *dirs],
        key="learnings_compare",
    )
    sar_dir = st.selectbox("SAR directory", ["", *dirs], key="learnings_sar")
    mmp_dir = st.selectbox("MMP directory", ["", *dirs], key="learnings_mmp")
    picklists_dir = st.selectbox(
        "Picklists directory",
        ["", *dirs],
        key="learnings_picklists",
    )
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
    selected_dirs = st.multiselect(
        "Learnings directories",
        dirs,
        key="dashboard_dirs",
    )
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
        "Report directory": (
            "--report-dir",
            st.selectbox("Report directory", ["", *dirs], key="portal_report"),
        ),
        "Picklists directory": (
            "--picklists-dir",
            st.selectbox("Picklists directory", ["", *dirs], key="portal_picklists"),
        ),
        "Compare directory": (
            "--compare-dir",
            st.selectbox("Compare directory", ["", *dirs], key="portal_compare"),
        ),
        "Learnings directory": (
            "--learnings-dir",
            st.selectbox("Learnings directory", ["", *dirs], key="portal_learnings"),
        ),
        "Dashboard directory": (
            "--dashboard-dir",
            st.selectbox("Dashboard directory", ["", *dirs], key="portal_dashboard"),
        ),
        "SAR directory": (
            "--sar-dir",
            st.selectbox("SAR directory", ["", *dirs], key="portal_sar"),
        ),
        "MMP directory": (
            "--mmp-dir",
            st.selectbox("MMP directory", ["", *dirs], key="portal_mmp"),
        ),
        "Retro directory": (
            "--retro-dir",
            st.selectbox("Retro directory", ["", *dirs], key="portal_retro"),
        ),
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


def _category_specs() -> dict[str, Any]:
    try:
        from molprop_toolkit.core.registry import CATEGORY_SPECS
    except Exception:
        return {}
    return CATEGORY_SPECS


def _family_columns(df: pd.DataFrame, family: PropertyFamily) -> list[str]:
    specs = _category_specs()
    selected: list[str] = []
    for column in BASE_COLUMNS:
        if column in df.columns and column not in selected:
            selected.append(column)
    for category in family.categories:
        spec = specs.get(category)
        if spec is None:
            continue
        for column in spec.columns:
            if column in df.columns and column not in selected:
                selected.append(column)
        prefix = getattr(spec, "prefix", None)
        if prefix:
            for column in df.columns:
                if column.startswith(prefix) and column not in selected:
                    selected.append(column)
    return selected


def _property_payload_key(family: PropertyFamily) -> str:
    return f"property_bundle_{family.key}"


def _build_property_bundle(
    ctx: RunContext,
    family: PropertyFamily,
    *,
    source_mode: str,
    selected_rel: str,
    profile: str,
    build_report: bool,
    calc_extra: str,
) -> dict[str, Any]:
    bundle_dir = ctx.run_dir / "outputs" / "properties" / family.key
    bundle_dir.mkdir(parents=True, exist_ok=True)

    log_tails: list[str] = []
    generated_table = False

    if source_mode == "Workspace SMILES":
        generated = run_generate_pipeline(
            ctx,
            resolve_workspace_path(ctx, selected_rel),
            profile=profile,
            out_format="parquet",
            output_relative=str(
                Path("outputs") / "properties" / family.key / f"{family.key}_results.parquet"
            ),
            run_report=False,
            run_picklists=False,
            run_visualize=False,
            extra_args={"calc": calc_extra},
        )
        if not generated.get("results_table"):
            raise RuntimeError("MolScope could not build the results table for this property bundle.")
        results_path = Path(str(generated["results_table"]))
        generated_table = True
        if generated.get("calc_log_tail"):
            log_tails.append(str(generated["calc_log_tail"]))
    else:
        results_path = resolve_workspace_path(ctx, selected_rel)

    df = read_table(results_path)
    columns = _family_columns(df, family)
    subset = df.loc[:, columns] if columns else pd.DataFrame()
    subset_path = bundle_dir / f"{family.key}_subset.csv"
    write_table(subset, subset_path)

    report_html = None
    report_result = None
    if build_report and command_available("report"):
        report_dir = bundle_dir / "report"
        report_args = [
            str(results_path),
            "--categories",
            ",".join(family.categories),
            "--outdir",
            str(report_dir),
            "--title",
            family.title,
        ]
        report_result = run_toolkit_subcommand(
            ctx,
            "report",
            report_args,
            log_name=f"{family.key}_report.log",
        )
        if report_result.tail:
            log_tails.append(report_result.tail)
        candidate_html = report_dir / "report.html"
        if candidate_html.exists():
            report_html = str(candidate_html.relative_to(ctx.run_dir))

    payload = {
        "title": family.title,
        "bundle_dir": str(bundle_dir.relative_to(ctx.run_dir)),
        "source": selected_rel,
        "source_mode": source_mode,
        "results_path": str(results_path.relative_to(ctx.run_dir)),
        "subset_path": str(subset_path.relative_to(ctx.run_dir)),
        "rows": int(len(subset)),
        "columns": list(subset.columns),
        "generated_table": generated_table,
        "report_html": report_html,
        "tail": "\n\n".join(part for part in log_tails if part.strip()),
    }
    summary_path = bundle_dir / "summary.json"
    summary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["summary_path"] = str(summary_path.relative_to(ctx.run_dir))
    return payload


def _render_property_result(ctx: RunContext, family: PropertyFamily) -> None:
    payload = st.session_state.get(_property_payload_key(family))
    if not payload:
        return
    st.subheader(family.title)
    st.write(f"Source: `{payload['source']}`")
    st.write(f"Rows: {payload['rows']:,}")
    subset_path = resolve_workspace_path(ctx, payload["subset_path"])
    if subset_path.exists():
        _preview_table(subset_path, rows=15)
        left, right, third = st.columns(3)
        with left:
            _download_file(
                subset_path,
                label="Download subset CSV",
                key=f"download_subset_{family.key}",
            )
        with right:
            _download_directory(
                resolve_workspace_path(ctx, payload["bundle_dir"]),
                label="Download bundle",
                key=f"download_bundle_{family.key}",
            )
        with third:
            _download_file(
                resolve_workspace_path(ctx, payload["summary_path"]),
                label="Download summary",
                key=f"download_summary_{family.key}",
            )
    if payload.get("tail"):
        st.text_area(
            "Run log tail",
            payload["tail"],
            height=180,
            key=f"tail_{family.key}",
        )
    if payload.get("report_html"):
        html_path = resolve_workspace_path(ctx, payload["report_html"])
        if html_path.exists():
            components.html(
                html_path.read_text(encoding="utf-8"),
                height=600,
                scrolling=True,
            )


def _property_source_panel(ctx: RunContext, family: PropertyFamily) -> None:
    _input_tools(ctx, f"property_{family.key}")

    source_mode = st.radio(
        "Start from",
        ["Workspace table", "Workspace SMILES"],
        key=f"{family.key}_source_mode",
        horizontal=True,
    )

    if source_mode == "Workspace table":
        options = workspace_tables(ctx)
        if not options:
            st.info("Add a table first.")
            return
        selected = st.selectbox(
            "Table",
            options,
            key=f"{family.key}_table",
        )
        profile = "extended"
        calc_extra = ""
    else:
        options = workspace_smiles(ctx)
        if not options:
            st.info("Add a SMILES file first.")
            return
        selected = st.selectbox(
            "SMILES file",
            options,
            key=f"{family.key}_smiles",
        )
        profile = st.selectbox(
            "Calc profile",
            ["extended", "baseline"],
            index=0,
            key=f"{family.key}_profile",
        )
        calc_extra = st.text_input(
            "Calc extra arguments",
            value="",
            key=f"{family.key}_calc_extra",
        )

    build_report = st.checkbox(
        "Build property report",
        value=command_available("report"),
        disabled=not command_available("report"),
        key=f"{family.key}_build_report",
    )

    if st.button(f"Build {family.title}", key=f"{family.key}_run"):
        try:
            payload = _build_property_bundle(
                ctx,
                family,
                source_mode=source_mode,
                selected_rel=selected,
                profile=profile,
                build_report=build_report,
                calc_extra=calc_extra,
            )
        except Exception as exc:
            st.error(str(exc))
        else:
            st.session_state[_property_payload_key(family)] = payload
            _record_action(
                {
                    "title": family.title,
                    "summary": f"Built from `{selected}`.",
                    "paths": [
                        ("Subset", payload["subset_path"]),
                        ("Bundle", payload["bundle_dir"]),
                    ],
                    "tail": payload.get("tail", ""),
                    "html_path": payload.get("report_html") or "",
                }
            )
            st.success("Bundle finished.")

    _render_property_result(ctx, family)


def _artifact_paths(ctx: RunContext, before: dict[str, tuple[str, int]]) -> list[str]:
    return workspace_changes(ctx, before)


def _artifact_html_path(paths: list[str]) -> str:
    for rel in paths:
        if rel.endswith(".html"):
            return rel
    return ""


def _record_command_action(
    ctx: RunContext,
    *,
    title: str,
    summary: str,
    before: dict[str, tuple[str, int]],
    tail: str,
    log_rel: str,
) -> None:
    artifact_paths = _artifact_paths(ctx, before)
    html_path = _artifact_html_path(artifact_paths)
    paths = [("Output", rel) for rel in artifact_paths]
    paths.append(("Log", log_rel))
    _record_action(
        {
            "title": title,
            "summary": summary,
            "paths": paths,
            "download_paths": artifact_paths,
            "tail": tail,
            "html_path": html_path,
        }
    )


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

tab_inputs, tab_core, tab_properties, tab_advanced, tab_visualize, tab_about = st.tabs(
    [
        "Inputs",
        "Core workflow",
        "Properties",
        "Advanced workflows",
        "Visualize",
        "About",
    ]
)

with tab_inputs:
    _input_tools(ctx, "workspace")

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

with tab_core:
    _input_tools(ctx, "core")
    smiles_files = workspace_smiles(ctx)
    tables = workspace_tables(ctx)

    sub_generate, sub_followup = st.tabs(["Generate table", "Follow up on a table"])

    with sub_generate:
        if not smiles_files:
            st.info("Add a SMILES file first.")
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

            calc_extra = st.text_input(
                "Calc extra arguments",
                value="",
                key="generate_calc_extra",
            )
            report_extra = st.text_input(
                "Report extra arguments",
                value="",
                key="generate_report_extra",
            )
            picklists_extra = st.text_input(
                "Picklists extra arguments",
                value="",
                key="generate_picklists_extra",
            )

            if st.button("Run generate pipeline"):
                before = workspace_snapshot(ctx)
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
                    results_path = Path(str(results["results_table"]))
                    paths.append(("Results table", str(results_path.relative_to(ctx.run_dir))))
                    _download_file(
                        results_path,
                        label="Download results table",
                        key="download_core_results",
                    )
                viz_step = next(
                    (
                        step
                        for step in results.get("steps", [])
                        if step.get("name") == "visualize"
                    ),
                    None,
                )
                html_path = ""
                if viz_step:
                    projection_html = Path(str(viz_step["projection_html"]))
                    html_path = str(projection_html.relative_to(ctx.run_dir))
                    paths.append(("Projection HTML", html_path))
                artifact_paths = _artifact_paths(ctx, before)
                tail = (
                    results.get("picklists_log_tail")
                    or results.get("report_log_tail")
                    or results.get("calc_log_tail")
                    or ""
                )
                _record_action(
                    {
                        "title": "Generate pipeline",
                        "summary": f"Started from `{smiles_input}`.",
                        "paths": paths,
                        "download_paths": artifact_paths,
                        "tail": tail,
                        "html_path": html_path or _artifact_html_path(artifact_paths),
                    }
                )
                st.success("Pipeline finished.")

    with sub_followup:
        if not tables:
            st.info("Add a table first.")
        else:
            followup_tabs = st.tabs(["Analyze", "Report", "Picklists"])

            with followup_tabs[0]:
                selected = st.selectbox("Table", tables, key="analyze_table")
                category = st.text_input("Category", value="", key="analyze_category")
                extra = st.text_input("Extra arguments", value="", key="analyze_extra")
                if st.button("Run analyze"):
                    before = workspace_snapshot(ctx)
                    args = [str(resolve_workspace_path(ctx, selected))]
                    if category.strip():
                        args.extend(["--category", category.strip()])
                    args.extend(split_args(extra))
                    result = run_toolkit_subcommand(ctx, "analyze", args, log_name="analyze.log")
                    _record_command_action(
                        ctx,
                        title="Analyze",
                        summary=f"Ran on `{selected}`.",
                        before=before,
                        tail=result.tail,
                        log_rel=str(result.log_path.relative_to(ctx.run_dir)),
                    )
                    if result.returncode == 0:
                        st.success("Analyze finished.")
                    else:
                        st.error("Analyze failed.")

            with followup_tabs[1]:
                selected = st.selectbox("Table", tables, key="report_table")
                extra = st.text_input("Extra arguments", value="", key="report_extra")
                if st.button("Run report"):
                    before = workspace_snapshot(ctx)
                    args = [str(resolve_workspace_path(ctx, selected)), *split_args(extra)]
                    result = run_toolkit_subcommand(ctx, "report", args, log_name="report.log")
                    _record_command_action(
                        ctx,
                        title="Report",
                        summary=f"Ran on `{selected}`.",
                        before=before,
                        tail=result.tail,
                        log_rel=str(result.log_path.relative_to(ctx.run_dir)),
                    )
                    if result.returncode == 0:
                        st.success("Report finished.")
                    else:
                        st.error("Report failed.")

            with followup_tabs[2]:
                selected = st.selectbox("Table", tables, key="picklists_table")
                extra = st.text_input("Extra arguments", value="", key="picklists_extra")
                html = st.checkbox("Write HTML", value=True, key="picklists_write_html")
                if st.button("Run picklists"):
                    before = workspace_snapshot(ctx)
                    args = [str(resolve_workspace_path(ctx, selected))]
                    if html:
                        args.append("--html")
                    args.extend(split_args(extra))
                    result = run_toolkit_subcommand(
                        ctx,
                        "picklists",
                        args,
                        log_name="picklists.log",
                    )
                    _record_command_action(
                        ctx,
                        title="Picklists",
                        summary=f"Ran on `{selected}`.",
                        before=before,
                        tail=result.tail,
                        log_rel=str(result.log_path.relative_to(ctx.run_dir)),
                    )
                    if result.returncode == 0:
                        st.success("Picklists finished.")
                    else:
                        st.error("Picklists failed.")

with tab_properties:
    property_tabs = st.tabs([family.title for family in PROPERTY_FAMILIES])
    for property_tab, family in zip(property_tabs, PROPERTY_FAMILIES, strict=True):
        with property_tab:
            st.write(family.summary)
            _property_source_panel(ctx, family)

with tab_advanced:
    advanced_tabs = st.tabs(
        [
            "Integrate and compare",
            "SAR and MMP",
            "Search, series, similarity",
            "Learnings, dashboard, portal",
            "Generic command",
        ]
    )

    with advanced_tabs[0]:
        if command_available("integrate"):
            st.subheader("Integrate")
            pair = _pair_command_args(ctx, "integrate")
            if pair and st.button("Run integrate", key="run_integrate"):
                before = workspace_snapshot(ctx)
                args, subject = pair
                result = run_toolkit_subcommand(
                    ctx,
                    "integrate",
                    args,
                    log_name="integrate.log",
                )
                _record_command_action(
                    ctx,
                    title="Integrate",
                    summary=f"Ran on {subject}.",
                    before=before,
                    tail=result.tail,
                    log_rel=str(result.log_path.relative_to(ctx.run_dir)),
                )
                st.success("Integrate finished." if result.returncode == 0 else "Integrate failed.")

        if command_available("compare"):
            st.subheader("Compare")
            pair = _pair_command_args(ctx, "compare")
            if pair and st.button("Run compare", key="run_compare"):
                before = workspace_snapshot(ctx)
                args, subject = pair
                result = run_toolkit_subcommand(
                    ctx,
                    "compare",
                    args,
                    log_name="compare.log",
                )
                _record_command_action(
                    ctx,
                    title="Compare",
                    summary=f"Ran on {subject}.",
                    before=before,
                    tail=result.tail,
                    log_rel=str(result.log_path.relative_to(ctx.run_dir)),
                )
                st.success("Compare finished." if result.returncode == 0 else "Compare failed.")

    with advanced_tabs[1]:
        if command_available("sar"):
            st.subheader("SAR")
            single = _single_command_args(ctx, "sar")
            if single and st.button("Run SAR", key="run_sar"):
                before = workspace_snapshot(ctx)
                args, subject = single
                result = run_toolkit_subcommand(ctx, "sar", args, log_name="sar.log")
                _record_command_action(
                    ctx,
                    title="SAR",
                    summary=f"Ran on `{subject}`.",
                    before=before,
                    tail=result.tail,
                    log_rel=str(result.log_path.relative_to(ctx.run_dir)),
                )
                st.success("SAR finished." if result.returncode == 0 else "SAR failed.")

        if command_available("mmp"):
            st.subheader("MMP")
            single = _single_command_args(ctx, "mmp")
            if single and st.button("Run MMP", key="run_mmp"):
                before = workspace_snapshot(ctx)
                args, subject = single
                result = run_toolkit_subcommand(ctx, "mmp", args, log_name="mmp.log")
                _record_command_action(
                    ctx,
                    title="MMP",
                    summary=f"Ran on `{subject}`.",
                    before=before,
                    tail=result.tail,
                    log_rel=str(result.log_path.relative_to(ctx.run_dir)),
                )
                st.success("MMP finished." if result.returncode == 0 else "MMP failed.")

    with advanced_tabs[2]:
        for command_name in ("search", "series", "similarity"):
            if command_available(command_name):
                st.subheader(COMMANDS_BY_NAME[command_name].title)
                single = _single_command_args(ctx, command_name)
                if single and st.button(
                    f"Run {COMMANDS_BY_NAME[command_name].title}",
                    key=f"run_{command_name}",
                ):
                    before = workspace_snapshot(ctx)
                    args, subject = single
                    result = run_toolkit_subcommand(
                        ctx,
                        command_name,
                        args,
                        log_name=f"{command_name}.log",
                    )
                    _record_command_action(
                        ctx,
                        title=COMMANDS_BY_NAME[command_name].title,
                        summary=f"Ran on `{subject}`.",
                        before=before,
                        tail=result.tail,
                        log_rel=str(result.log_path.relative_to(ctx.run_dir)),
                    )
                    st.success(
                        f"{COMMANDS_BY_NAME[command_name].title} finished."
                        if result.returncode == 0
                        else f"{COMMANDS_BY_NAME[command_name].title} failed."
                    )

    with advanced_tabs[3]:
        if command_available("learnings"):
            st.subheader("Learnings")
            args_result = _learnings_args(ctx)
            if args_result and st.button("Run learnings", key="run_learnings"):
                before = workspace_snapshot(ctx)
                args, subject = args_result
                result = run_toolkit_subcommand(
                    ctx,
                    "learnings",
                    args,
                    log_name="learnings.log",
                )
                _record_command_action(
                    ctx,
                    title="Learnings",
                    summary=f"Ran on {subject}.",
                    before=before,
                    tail=result.tail,
                    log_rel=str(result.log_path.relative_to(ctx.run_dir)),
                )
                st.success("Learnings finished." if result.returncode == 0 else "Learnings failed.")

        if command_available("dashboard"):
            st.subheader("Dashboard")
            args_result = _dashboard_args(ctx)
            if args_result and st.button("Run dashboard", key="run_dashboard"):
                before = workspace_snapshot(ctx)
                args, subject = args_result
                result = run_toolkit_subcommand(
                    ctx,
                    "dashboard",
                    args,
                    log_name="dashboard.log",
                )
                _record_command_action(
                    ctx,
                    title="Dashboard",
                    summary=f"Ran on {subject}.",
                    before=before,
                    tail=result.tail,
                    log_rel=str(result.log_path.relative_to(ctx.run_dir)),
                )
                st.success("Dashboard finished." if result.returncode == 0 else "Dashboard failed.")

        if command_available("portal"):
            st.subheader("Portal")
            args_result = _portal_args(ctx)
            if args_result and st.button("Run portal", key="run_portal"):
                before = workspace_snapshot(ctx)
                args, subject = args_result
                result = run_toolkit_subcommand(
                    ctx,
                    "portal",
                    args,
                    log_name="portal.log",
                )
                _record_command_action(
                    ctx,
                    title="Portal",
                    summary=f"Ran on {subject}.",
                    before=before,
                    tail=result.tail,
                    log_rel=str(result.log_path.relative_to(ctx.run_dir)),
                )
                st.success("Portal finished." if result.returncode == 0 else "Portal failed.")

    with advanced_tabs[4]:
        command_names = [spec.name for spec in COMMAND_SPECS]
        command_name = st.selectbox(
            "Command",
            command_names,
            format_func=lambda name: COMMANDS_BY_NAME[name].title,
        )
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
            before = workspace_snapshot(ctx)
            args, subject = args_result
            result = run_toolkit_subcommand(
                ctx,
                command_name,
                args,
                log_name=f"{command_name}.log",
            )
            write_run_metadata(
                ctx,
                {
                    "mode": "command",
                    "command": command_name,
                    "args": args,
                    "returncode": result.returncode,
                },
            )
            _record_command_action(
                ctx,
                title=f"molscope {command_name}",
                summary=f"Ran on {subject}.",
                before=before,
                tail=result.tail,
                log_rel=str(result.log_path.relative_to(ctx.run_dir)),
            )
            if result.returncode == 0:
                st.success("Command finished.")
            else:
                st.error("Command failed.")

with tab_visualize:
    _input_tools(ctx, "visualize")
    tables = workspace_tables(ctx)
    if not tables:
        st.info("Add a table first.")
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
                        ("Projection CSV", str(projection.projection_csv.relative_to(ctx.run_dir))),
                        ("Projection HTML", str(projection.projection_html.relative_to(ctx.run_dir))),
                    ],
                    "html_path": str(projection.projection_html.relative_to(ctx.run_dir)),
                }
            )
            _download_file(
                projection.projection_csv,
                label="Download projection CSV",
                key="download_projection_csv",
            )
            _download_file(
                projection.projection_html,
                label="Download projection HTML",
                key="download_projection_html",
            )
            st.success("Projection finished.")

with tab_about:
    st.subheader("How this server works")
    st.write("The server keeps one workspace open at a time.")
    st.write("You can add files, paste SMILES, run MolScope commands, inspect outputs, and download the run bundle.")
    st.write("The property tabs write focused bundles for the main MolScope property families.")

_render_last_action(ctx)
