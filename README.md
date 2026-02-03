# MolProp Platform

MolProp Platform is the **expanded, batteries-included** companion to **MolProp Toolkit**. The toolkit remains the stable
“table compiler” and schema authority; the platform adds interactive workflows and higher-level analysis modules that
consume those tables. The design goal is that existing MolProp Toolkit pipelines keep working unchanged while the
platform can iterate quickly on new user-facing features.

## Relationship to MolProp Toolkit

MolProp Toolkit produces analysis-ready CSV/TSV/Parquet tables with reproducible column definitions and provenance.
MolProp Platform reads those tables and produces additional artifacts such as interactive Plotly dashboards, Pareto
front viewers, SAR/MMP summaries, and optional web apps.

## Install

Because RDKit is best installed via conda-forge, most users should create a conda environment first.

```bash
git clone https://github.com/kelokely/molprop-platform.git
cd molprop-platform

# optional but recommended for chem work: create/activate your RDKit environment first
# conda env create -f environment.yml
# conda activate molprop-toolkit

pip install -e ".[dev]"
```

To install the core dependency from GitHub (until core is published on PyPI):

```bash
pip install -e ".[core]"
```

To enable visualization and web UI extras:

```bash
pip install -e ".[core,viz,web]"
```

## Commands (v1 skeleton)

This repo ships CLI entrypoints early so you can build docs and workflows while implementing features incrementally.

- `molprop-visualize`: create PCA/UMAP plots from a results table (CSV/Parquet)
- `molprop-web`: start a Streamlit UI (placeholder)
- `molprop-pareto`, `molprop-mmp`, `molprop-sar`, `molprop-lookup`, `molprop-bioisostere`: placeholders

## License

MIT

