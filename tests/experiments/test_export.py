"""Tests for `ibqn.experiments.export` (Fase H3.5)."""
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
import pytest

from ibqn.experiments.export import save_figure, save_table


@pytest.mark.unit
def test_save_figure_writes_pdf_and_png(tmp_path):
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    pdf_path, png_path = save_figure(fig, "my_figure", directory=tmp_path)
    assert pdf_path.exists() and pdf_path.suffix == ".pdf"
    assert png_path.exists() and png_path.suffix == ".png"
    plt.close(fig)


@pytest.mark.unit
def test_save_table_writes_csv(tmp_path):
    df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
    path = save_table(df, "my_table", directory=tmp_path)
    assert path.exists()
    reloaded = pd.read_csv(path)
    assert list(reloaded["a"]) == [1, 2]


@pytest.mark.unit
def test_save_figure_creates_missing_directory(tmp_path):
    fig, ax = plt.subplots()
    nested = tmp_path / "a" / "b" / "c"
    save_figure(fig, "fig", directory=nested)
    assert (nested / "fig.pdf").exists()
    plt.close(fig)
