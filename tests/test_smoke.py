from __future__ import annotations

from molscope import __version__
from molscope.toolkit import resolve_toolkit_command


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
    assert resolve_toolkit_command("calc", ["--profile", "baseline", "input.smi"]) == [
        "/tmp/molprop-calc-v4",
        "input.smi",
    ]
