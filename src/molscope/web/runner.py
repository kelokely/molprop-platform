from __future__ import annotations

import io
import json
import shutil
import subprocess
import sys
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

from molscope.toolkit import resolve_toolkit_command, split_args
from molscope.viz.core import build_projection


@dataclass(frozen=True)
class RunContext:
    run_dir: Path
    created_at: float


@dataclass(frozen=True)
class CommandResult:
    name: str
    command_line: tuple[str, ...]
    returncode: int
    log_path: Path
    tail: str


def make_run_dir(base_dir: str | Path = "runs") -> RunContext:
    base = Path(base_dir)
    base.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    run_dir = base / f"run_{ts}_{int(time.time())}"
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "inputs").mkdir()
    (run_dir / "outputs").mkdir()
    (run_dir / "logs").mkdir()
    return RunContext(run_dir=run_dir, created_at=time.time())


def save_uploaded_file(uploaded: Any, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = uploaded.getvalue() if hasattr(uploaded, "getvalue") else uploaded.read()
    if isinstance(data, str):
        data = data.encode("utf-8")
    dest.write_bytes(data)
    return dest


def which(cmd: str) -> Optional[str]:
    return shutil.which(cmd)


def run_command_capture(
    cmd: list[str],
    cwd: Path,
    log_path: Path,
    env: Optional[Dict[str, str]] = None,
) -> Tuple[int, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(proc.stdout, encoding="utf-8")
    tail = proc.stdout.splitlines()[-80:]
    return proc.returncode, "\n".join(tail)


def detect_input_kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".smi", ".smiles"}:
        return "smiles"
    if suffix in {".csv", ".tsv", ".parquet"}:
        return "table"
    return "other"


def resolve_workspace_path(ctx: RunContext, relative_path: str) -> Path:
    return ctx.run_dir / relative_path


def workspace_files(
    ctx: RunContext,
    *,
    suffixes: tuple[str, ...] | None = None,
) -> list[str]:
    items: list[str] = []
    for path in sorted(ctx.run_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(ctx.run_dir)
        if rel.parts and rel.parts[0] == "logs":
            continue
        if suffixes and path.suffix.lower() not in suffixes:
            continue
        items.append(str(rel))
    return items


def workspace_tables(ctx: RunContext) -> list[str]:
    return workspace_files(ctx, suffixes=(".csv", ".tsv", ".parquet"))


def workspace_smiles(ctx: RunContext) -> list[str]:
    return workspace_files(ctx, suffixes=(".smi", ".smiles"))


def workspace_directories(ctx: RunContext) -> list[str]:
    items: list[str] = []
    for path in sorted(ctx.run_dir.rglob("*")):
        if not path.is_dir():
            continue
        rel = path.relative_to(ctx.run_dir)
        if not rel.parts:
            continue
        if rel.parts[0] == "logs":
            continue
        items.append(str(rel))
    return items


def write_run_metadata(ctx: RunContext, payload: Dict[str, Any]) -> Path:
    meta = {
        "created_at": ctx.created_at,
        "python": sys.version,
        **payload,
    }
    out = ctx.run_dir / "run.json"
    out.write_text(json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8")
    return out


def zip_run_directory(ctx: RunContext) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in ctx.run_dir.rglob("*"):
            if path.is_dir():
                continue
            zf.write(path, arcname=str(path.relative_to(ctx.run_dir)))
    buf.seek(0)
    return buf.read()


def run_toolkit_subcommand(
    ctx: RunContext,
    command: str,
    args: list[str],
    *,
    log_name: str | None = None,
) -> CommandResult:
    resolved = resolve_toolkit_command(command, args)
    if resolved is None:
        raise RuntimeError("Install MolScope toolkit in this environment first.")
    log_path = ctx.run_dir / "logs" / (log_name or f"{command}_{int(time.time())}.log")
    returncode, tail = run_command_capture(resolved, cwd=ctx.run_dir, log_path=log_path)
    return CommandResult(
        name=command,
        command_line=tuple(resolved),
        returncode=returncode,
        log_path=log_path,
        tail=tail,
    )


def _command_result_payload(result: CommandResult) -> dict[str, Any]:
    return {
        "name": result.name,
        "command_line": list(result.command_line),
        "returncode": result.returncode,
        "log_path": str(result.log_path),
    }


def run_generate_pipeline(
    ctx: RunContext,
    smiles_path: Path,
    *,
    profile: str = "extended",
    out_format: str = "parquet",
    run_report: bool = True,
    run_picklists: bool = False,
    run_visualize: bool = False,
    extra_args: Mapping[str, str] | None = None,
) -> Dict[str, Any]:
    extra_args = extra_args or {}
    results: Dict[str, Any] = {"steps": []}
    out_path = ctx.run_dir / "outputs" / f"results.{out_format}"

    calc_args = [
        "--profile",
        profile,
        str(smiles_path),
        "-o",
        str(out_path),
        *split_args(extra_args.get("calc", "")),
    ]
    calc_result = run_toolkit_subcommand(ctx, "calc", calc_args, log_name="calc.log")
    results["steps"].append(_command_result_payload(calc_result))
    results["calc_log_tail"] = calc_result.tail
    if calc_result.returncode != 0:
        results["results_table"] = None
        return results

    results["results_table"] = str(out_path)

    if run_report:
        report_args = [str(out_path), *split_args(extra_args.get("report", ""))]
        report_result = run_toolkit_subcommand(
            ctx,
            "report",
            report_args,
            log_name="report.log",
        )
        results["steps"].append(_command_result_payload(report_result))
        results["report_log_tail"] = report_result.tail

    if run_picklists:
        picklists_args = [
            str(out_path),
            "--html",
            *split_args(extra_args.get("picklists", "")),
        ]
        picklists_result = run_toolkit_subcommand(
            ctx,
            "picklists",
            picklists_args,
            log_name="picklists.log",
        )
        results["steps"].append(_command_result_payload(picklists_result))
        results["picklists_log_tail"] = picklists_result.tail

    if run_visualize:
        viz_dir = ctx.run_dir / "outputs" / "viz"
        projection = build_projection(out_path, outdir=viz_dir, method="pca")
        results["steps"].append(
            {
                "name": "visualize",
                "projection_csv": str(projection.projection_csv),
                "projection_html": str(projection.projection_html),
                "rows": projection.rows,
                "features": projection.features,
            }
        )

    write_run_metadata(
        ctx,
        {
            "mode": "generate",
            "input": str(smiles_path),
            "pipeline_result": results,
        },
    )
    return results
