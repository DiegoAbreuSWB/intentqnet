"""Figure/table export for `notebooks/article/*.ipynb` (Fase H3, section
32-33): every figure as both PDF and PNG, every table as CSV, under a
fixed, predictable path - never inline-computed values, always whatever
`aggregation`/`persistence` already produced.

Writes go through a temp file + `os.replace` (Fase K4) - found
empirically that a repository-wide set of processed files
(`results/processed/*/{aggregated,paired,statistical_comparisons}.csv`,
across both H3's pilot campaigns and J10's final ones) ended up on disk
under a corrupted name (the campaign name appended to the base name,
e.g. `aggregated_C01_routing_strategy.csv` instead of `aggregated.csv`)
while the correctly-named, git-tracked file simultaneously vanished
from the working tree - see docs/results_provenance.md. The exact
external cause (this environment's sandboxing/file-watching layer, not
this project's own code - no code path here ever constructs a
campaign-suffixed name) could not be pinned down, but a direct,
non-atomic `df.to_csv(path)`/`fig.savefig(path)` is more exposed to
whatever mid-write interference caused it than a temp-file-then-rename,
which is atomic at the filesystem level (matches the pattern
`experiments.manifests.write_manifest` already used safely).
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
from matplotlib.figure import Figure

DEFAULT_FIGURES_DIR = "results/figures/article"
DEFAULT_TABLES_DIR = "results/tables/article"


def _atomic_write(path: Path, write_fn) -> None:
    """Calls `write_fn(tmp_path)` (which must write the file at
    `tmp_path`), then atomically renames it to `path` via `os.replace` -
    a reader never observes a partially-written or wrongly-named file."""
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    write_fn(tmp_path)
    os.replace(tmp_path, path)


def save_figure(fig: Figure, name: str, *, directory: str | Path = DEFAULT_FIGURES_DIR) -> tuple[Path, Path]:
    """Saves `fig` as `<directory>/<name>.pdf` and `.png`, creating
    `directory` if needed. Returns `(pdf_path, png_path)`."""
    out_dir = Path(directory)
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = out_dir / f"{name}.pdf"
    png_path = out_dir / f"{name}.png"
    # format= is explicit because the temp file's own extension (.tmp) is
    # not a format savefig() recognizes - it would otherwise infer the
    # format from tmp_path's suffix and fail with "Format 'tmp' is not
    # supported" (found while adding the atomic-write fix, Fase K4).
    _atomic_write(pdf_path, lambda tmp: fig.savefig(tmp, format="pdf", bbox_inches="tight"))
    _atomic_write(png_path, lambda tmp: fig.savefig(tmp, format="png", bbox_inches="tight", dpi=150))
    return pdf_path, png_path


def save_table(df: pd.DataFrame, name: str, *, directory: str | Path = DEFAULT_TABLES_DIR) -> Path:
    """Saves `df` as `<directory>/<name>.csv`, creating `directory` if
    needed. Returns the written path."""
    out_dir = Path(directory)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}.csv"
    _atomic_write(path, lambda tmp: df.to_csv(tmp, index=False))
    return path
