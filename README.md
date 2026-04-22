# MolScope

MolScope gives the MolScope toolkit a server workspace.

You can keep one run open, upload files, run the toolkit commands, inspect the outputs, and download the full bundle when you are done.

Documentation site: https://kelokely.github.io/molprop-platform/

## What lives here

MolScope Toolkit stays responsible for the chemistry table, schema, and command line workflow.

This repo adds:

- a Streamlit server workspace
- quick PCA and UMAP views
- a simple way to run the current MolScope commands from one place

## Install

```bash
git clone https://github.com/kelokely/molprop-platform.git
cd molprop-platform

pip install -e ".[dev,web,viz]"
```

To run the full toolkit workflow from the server, install the toolkit in the same environment:

```bash
pip install -e ".[core]"
```

## Start the server

```bash
molscope-server
```

Inside the app you can:

- upload SMILES files and build a results table
- upload existing results tables and run report, picklists, compare, SAR, MMP, search, similarity, featurize, retro, learnings, dashboard, and portal workflows
- preview tables, inspect logs, and download the full run workspace

## Quick visualization

```bash
molscope-visualize results.parquet -o viz --method umap
```

## Toolkit wrappers

The repo also ships:

- `molscope-mmp`
- `molscope-sar`

These forward to the toolkit commands when the toolkit is installed in the same environment.

## License

MIT
