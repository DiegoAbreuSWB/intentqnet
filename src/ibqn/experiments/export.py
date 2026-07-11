"""Figure/table export for `notebooks/article/*.ipynb` (Fase H3, section
32-33): every figure as both PDF and PNG, every table as CSV, under a
fixed, predictable path - never inline-computed values, always whatever
`aggregation`/`persistence` already produced.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from matplotlib.figure import Figure

DEFAULT_FIGURES_DIR = "results/figures/article"
DEFAULT_TABLES_DIR = "results/tables/article"


def save_figure(fig: Figure, name: str, *, directory: str | Path = DEFAULT_FIGURES_DIR) -> tuple[Path, Path]:
    """Saves `fig` as `<directory>/<name>.pdf` and `.png`, creating
    `directory` if needed. Returns `(pdf_path, png_path)`."""
    out_dir = Path(directory)
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = out_dir / f"{name}.pdf"
    png_path = out_dir / f"{name}.png"
    fig.savefig(pdf_path, bbox_inches="tight")
    fig.savefig(png_path, bbox_inches="tight", dpi=150)
    return pdf_path, png_path


def save_table(df: pd.DataFrame, name: str, *, directory: str | Path = DEFAULT_TABLES_DIR) -> Path:
    """Saves `df` as `<directory>/<name>.csv`, creating `directory` if
    needed. Returns the written path."""
    out_dir = Path(directory)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}.csv"
    df.to_csv(path, index=False)
    return path
