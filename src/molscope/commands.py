from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CommandSpec:
    name: str
    title: str
    summary: str
    mode: str


COMMAND_SPECS: tuple[CommandSpec, ...] = (
    CommandSpec("calc", "Calc", "Build a MolScope results table from SMILES.", "single"),
    CommandSpec("prep", "Prep", "Apply the MolScope preparation workflow to a structure file.", "single"),
    CommandSpec("analyze", "Analyze", "Inspect a MolScope table and export focused slices.", "single"),
    CommandSpec("report", "Report", "Build the report bundle for a MolScope table.", "single"),
    CommandSpec("picklists", "Picklists", "Generate decision queues from a MolScope table.", "single"),
    CommandSpec("integrate", "Integrate", "Merge measured assay data into a MolScope table.", "pair"),
    CommandSpec("compare", "Compare", "Compare two MolScope tables.", "pair"),
    CommandSpec("sar", "SAR", "Build a scaffold-centric SAR bundle.", "single"),
    CommandSpec("mmp", "MMP", "Build a matched-pair bundle.", "single"),
    CommandSpec("search", "Search", "Search a MolScope table by exact SMILES, SMARTS, or motif panel.", "single"),
    CommandSpec("series", "Series", "Annotate scaffold and similarity series.", "single"),
    CommandSpec("similarity", "Similarity", "Run similarity search and clustering tools.", "single"),
    CommandSpec("featurize", "Featurize", "Export ML-ready feature packs.", "single"),
    CommandSpec("retro", "Retro", "Run route-aware retrosynthesis workflows.", "single"),
    CommandSpec("schema", "Schema", "Validate a MolScope table against the schema.", "single"),
    CommandSpec("learnings", "Learnings", "Build a learnings bundle from compare, SAR, MMP, and picklists outputs.", "learnings"),
    CommandSpec("dashboard", "Dashboard", "Build a persistent dashboard from learnings bundles.", "dashboard"),
    CommandSpec("portal", "Portal", "Assemble report, compare, picklists, learnings, and related bundles into one workspace.", "portal"),
)


COMMANDS_BY_NAME = {spec.name: spec for spec in COMMAND_SPECS}
