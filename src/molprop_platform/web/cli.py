from __future__ import annotations

import argparse


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="molprop-web",
        description=(
            "Start the MolProp Platform Streamlit app. "
            "This is a v1 skeleton; the app will be expanded to orchestrate molprop-toolkit workflows."
        ),
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind host (Streamlit server.address)",
    )
    parser.add_argument(
        "--port",
        default="8501",
        help="Bind port (Streamlit server.port)",
    )
    args = parser.parse_args()

    try:
        import streamlit.web.bootstrap as bootstrap
    except Exception as e:
        raise SystemExit(
            "Install web dependencies with: pip install -e '.[web]'"
        ) from e

    # Run the app module.
    from pathlib import Path

    app_path = Path(__file__).with_name("app.py")

    bootstrap.run(
        str(app_path),
        "streamlit run",
        [],
        {
            "server.address": args.host,
            "server.port": int(args.port),
            "browser.gatherUsageStats": False,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
