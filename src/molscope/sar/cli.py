from __future__ import annotations

from molscope.toolkit import forward_to_toolkit


def main() -> int:
    return forward_to_toolkit("sar")


if __name__ == "__main__":
    raise SystemExit(main())
