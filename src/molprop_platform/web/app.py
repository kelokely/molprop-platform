from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="MolProp Platform", layout="wide")

st.title("MolProp Platform")
st.caption("Web UI skeleton — will orchestrate molprop-toolkit workflows.")

st.markdown("""
This app is intentionally minimal in v1. The long-term plan is:

- Upload a SMILES/CSV/Parquet file
- Choose the structure-of-record SMILES column (defaults to MolProp priority)
- Run calc/analyze/report/picklists/similarity
- Download a report bundle

Install extras with `pip install -e '.[core,web]'`.
""")

uploaded = st.file_uploader(
    "Upload a results table (CSV/Parquet)", type=["csv", "parquet", "tsv"]
)
if uploaded is not None:
    st.success(f"Uploaded: {uploaded.name}")
    st.info("In the next iteration, this will preview the table and let you run tools.")
