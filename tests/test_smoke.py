from __future__ import annotations


def test_version_import() -> None:
    import molprop_platform

    assert isinstance(molprop_platform.__version__, str)
