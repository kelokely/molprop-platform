from __future__ import annotations

import sys
from pathlib import Path

from molscope import __version__
from molscope.toolkit import resolve_toolkit_command
from molscope.web.runner import make_run_dir


def test_version_import() -> None:
    assert isinstance(__version__, str)
    assert __version__


def test_resolve_toolkit_command_prefers_molscope(monkeypatch) -> None:
    monkeypatch.setattr(
        "molscope.toolkit.which",
        lambda command: "/tmp/molscope" if command == "molscope" else None,
    )
    assert resolve_toolkit_command("compare", ["a.csv", "b.csv"]) == [
        "/tmp/molscope",
        "compare",
        "a.csv",
        "b.csv",
    ]


def test_resolve_toolkit_command_falls_back_for_calc(monkeypatch) -> None:
    def fake_which(command: str) -> str | None:
        if command == "molprop-calc-v4":
            return "/tmp/molprop-calc-v4"
        return None

    monkeypatch.setattr("molscope.toolkit.which", fake_which)
    monkeypatch.setattr("molscope.toolkit._toolkit_module_available", lambda: False)
    assert resolve_toolkit_command("calc", ["--profile", "baseline", "input.smi"]) == [
        "/tmp/molprop-calc-v4",
        "input.smi",
    ]


def test_resolve_toolkit_command_falls_back_to_module(monkeypatch) -> None:
    monkeypatch.setattr("molscope.toolkit.which", lambda command: None)
    monkeypatch.setattr("importlib.util.find_spec", lambda name: object())
    assert resolve_toolkit_command("report", ["results.csv"]) == [
        sys.executable,
        "-m",
        "molprop_toolkit.cli",
        "report",
        "results.csv",
    ]


def test_make_run_dir_returns_absolute_path(tmp_path: Path) -> None:
    ctx = make_run_dir(tmp_path / "runs")
    assert ctx.run_dir.is_absolute()
