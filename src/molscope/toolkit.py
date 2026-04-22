from __future__ import annotations

import shlex
import shutil
import subprocess
import sys
from typing import Sequence

LEGACY_COMMANDS: dict[str, str] = {
    "prep": "molprop-prep",
    "analyze": "molprop-analyze",
    "report": "molprop-report",
    "picklists": "molprop-picklists",
    "integrate": "molprop-integrate",
    "compare": "molprop-compare",
    "sar": "molprop-sar",
    "mmp": "molprop-mmp",
    "search": "molprop-search",
    "series": "molprop-series",
    "similarity": "molprop-similarity",
    "featurize": "molprop-featurize",
    "retro": "molprop-retro",
    "portal": "molprop-portal",
    "learnings": "molprop-learnings",
    "dashboard": "molprop-dashboard",
    "schema": "python tools/validate_csv_schema.py",
}


def which(command: str) -> str | None:
    return shutil.which(command)


def split_args(value: str) -> list[str]:
    return shlex.split(value) if value.strip() else []


def _parse_calc_profile(argv: Sequence[str]) -> tuple[str, list[str]]:
    profile = "extended"
    forwarded: list[str] = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--profile":
            if i + 1 >= len(argv):
                raise SystemExit("molscope calc: expected a value after --profile")
            profile = argv[i + 1].strip().lower()
            i += 2
            continue
        if arg.startswith("--profile="):
            profile = arg.split("=", 1)[1].strip().lower()
            i += 1
            continue
        forwarded.append(arg)
        i += 1
    if profile not in {"baseline", "extended"}:
        raise SystemExit("molscope calc: --profile must be baseline or extended")
    return profile, forwarded


def resolve_toolkit_command(command: str, argv: Sequence[str] = ()) -> list[str] | None:
    forwarded = list(argv)
    molscope_cli = which("molscope")
    if command == "calc":
        profile, forwarded = _parse_calc_profile(forwarded)
        if molscope_cli:
            return [molscope_cli, "calc", "--profile", profile, *forwarded]
        legacy = "molprop-calc-v4" if profile == "baseline" else "molprop-calc-v5"
        legacy_cli = which(legacy)
        if legacy_cli:
            return [legacy_cli, *forwarded]
        return None

    if molscope_cli:
        return [molscope_cli, command, *forwarded]

    legacy = LEGACY_COMMANDS.get(command)
    if not legacy:
        return None
    if legacy.startswith("python "):
        return shlex.split(legacy) + forwarded
    legacy_cli = which(legacy)
    if legacy_cli:
        return [legacy_cli, *forwarded]
    return None


def command_available(command: str) -> bool:
    return resolve_toolkit_command(command, ()) is not None


def forward_to_toolkit(command: str, argv: Sequence[str] | None = None) -> int:
    resolved = resolve_toolkit_command(command, argv or sys.argv[1:])
    if resolved is None:
        raise SystemExit("Install MolScope toolkit in this environment first.")
    proc = subprocess.run(resolved, check=False)
    return int(proc.returncode)
