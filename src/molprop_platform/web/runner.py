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
from typing import Any, Dict, Optional, Tuple


@dataclass(frozen=True)
class RunContext:
    run_dir: Path
    created_at: float


def make_run_dir(base_dir: str | Path = "runs") -> RunContext:
    base = Path(base_dir)
    base.mkdir(parents=True, exist_ok=True)

    ts = time.strftime("%Y%m%d_%H%M%S")
    # Keep folder names short and filesystem-safe.
    run_dir = base / f"run_{ts}_{int(time.time())}"
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "inputs").mkdir()
    (run_dir / "outputs").mkdir()
    (run_dir / "logs").mkdir()

    return RunContext(run_dir=run_dir, created_at=time.time())


def save_uploaded_file(uploaded: Any, dest: Path) -> Path:
    """Save a Streamlit UploadedFile-like object to disk."""
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
    """Run a command and capture combined stdout/stderr to a file.

    Returns (returncode, tail_text) where tail_text is a short excerpt for UI.
    """

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
    log_path.write_text(proc.stdout)

    tail = proc.stdout.splitlines()[-80:]
    return proc.returncode, "\n".join(tail)


def detect_input_kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in (".smi", ".smiles"):
        return "smiles"
    if suffix in (".csv", ".tsv", ".parquet"):
        return "table"
    return "unknown"


def write_run_metadata(ctx: RunContext, payload: Dict[str, Any]) -> Path:
    meta = {
        "created_at": ctx.created_at,
        "python": sys.version,
        **payload,
    }
    out = ctx.run_dir / "run.json"
    out.write_text(json.dumps(meta, indent=2, sort_keys=True))
    return out


def zip_run_directory(ctx: RunContext) -> bytes:
    """Return a ZIP archive (bytes) for the run directory."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in ctx.run_dir.rglob("*"):
            if path.is_dir():
                continue
            zf.write(path, arcname=str(path.relative_to(ctx.run_dir)))
    buf.seek(0)
    return buf.read()


def try_run_toolkit_pipeline(
    ctx: RunContext,
    smiles_path: Path,
    *,
    out_format: str = "parquet",
    run_report: bool = True,
    run_picklists: bool = False,
    run_visualize: bool = False,
) -> Dict[str, Any]:
    """Run a simple "SMILES -> results table -> optional report" pipeline.

    This intentionally uses subprocess to call molprop-toolkit console scripts.
    It keeps molprop-platform independent from molprop-toolkit internal APIs.

    The UI should only enable this when the commands are available.
    """

    results: Dict[str, Any] = {"steps": []}

    calc_cmd = which("molprop-calc-v5")
    if calc_cmd is None:
        raise RuntimeError(
            "molprop-calc-v5 not found. Install molprop-toolkit in this environment "
            "(e.g., pip install -e '.[core]' in molprop-platform)."
        )

    out_path = ctx.run_dir / "outputs" / f"results.{out_format}"
    cmd = ["molprop-calc-v5", str(smiles_path), "-o", str(out_path)]
    rc, tail = run_command_capture(
        cmd,
        cwd=ctx.run_dir,
        log_path=ctx.run_dir / "logs" / "calc_v5.log",
    )
    results["steps"].append({"name": "calc_v5", "cmd": cmd, "returncode": rc})
    results["calc_log_tail"] = tail

    if rc != 0:
        results["results_table"] = None
        return results

    results["results_table"] = str(out_path)

    if run_report:
        report_cmd = which("molprop-report")
        if report_cmd is None:
            results["steps"].append(
                {
                    "name": "report",
                    "skipped": True,
                    "reason": "molprop-report not found",
                }
            )
        else:
            cmd = ["molprop-report", str(out_path)]
            rc, tail = run_command_capture(
                cmd,
                cwd=ctx.run_dir,
                log_path=ctx.run_dir / "logs" / "report.log",
            )
            results["steps"].append({"name": "report", "cmd": cmd, "returncode": rc})
            results["report_log_tail"] = tail

    if run_picklists:
        pick_cmd = which("molprop-picklists")
        if pick_cmd is None:
            results["steps"].append(
                {
                    "name": "picklists",
                    "skipped": True,
                    "reason": "molprop-picklists not found",
                }
            )
        else:
            cmd = ["molprop-picklists", str(out_path), "--html"]
            rc, tail = run_command_capture(
                cmd,
                cwd=ctx.run_dir,
                log_path=ctx.run_dir / "logs" / "picklists.log",
            )
            results["steps"].append({"name": "picklists", "cmd": cmd, "returncode": rc})
            results["picklists_log_tail"] = tail

    if run_visualize:
        try:
            from molprop_platform.viz.core import build_projection

            outdir = ctx.run_dir / "outputs" / "viz"
            proj = build_projection(out_path, outdir=outdir, method="pca")
            results["steps"].append(
                {
                    "name": "visualize",
                    "method": proj.method,
                    "projection_csv": str(proj.projection_csv),
                    "projection_html": str(proj.projection_html),
                }
            )
        except Exception as e:
            results["steps"].append(
                {
                    "name": "visualize",
                    "skipped": True,
                    "reason": f"Visualization failed: {e}",
                }
            )

    return results
