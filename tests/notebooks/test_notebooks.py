"""Automatic notebook validation (see docs/notebooks.md and the project
brief's Fase H, section 2).

Discovers every `.ipynb` file directly under `notebooks/` (not recursing
into `notebooks/article/`, which holds long-running campaign-consuming
notebooks validated separately once Fase H3 exists), executes each one in
a clean kernel, and checks:

- it runs end to end without raising (`nbclient` surfaces any cell
  exception as `CellExecutionError`, which fails the test);
- a per-cell timeout is enforced, so a hung cell fails the test instead of
  the suite;
- executed code cells produced *some* visible output (stream/display data),
  not just silent success;
- no cell references a temp-file/scratch path external to the repo;
- if a cell builds a real topology/adapter (`SequenceAdapter(`,
  `run_scenario(`), an explicit `seed=` appears somewhere in the notebook.
"""
from __future__ import annotations

import re
from pathlib import Path

import nbformat
import pytest
from nbclient import NotebookClient
from nbclient.exceptions import CellExecutionError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
NOTEBOOKS_DIR = PROJECT_ROOT / "notebooks"
CELL_TIMEOUT_S = 180
KERNEL_NAME = "ibqn-venv"  # registered by tests/notebooks/conftest.py::ensure_notebook_kernel_registered

REQUIRED_H1_NOTEBOOKS = [
    "00_environment_validation.ipynb",
    "01_sequence_two_node_entanglement.ipynb",
    "02_sequence_three_node_swapping.ipynb",
    "03_sequence_purification.ipynb",
    "04_sequence_reservation_and_resources.ipynb",
    "05_sequence_memory_lifecycle.ipynb",
    "06_sequence_metrics_and_callbacks.ipynb",
]

_EXTERNAL_TEMP_PATTERNS = [
    re.compile(r"AppData[\\/]Local[\\/]Temp", re.IGNORECASE),
    re.compile(r"(?<![\w./\\])/tmp/"),
    re.compile(r"\bimport tempfile\b"),
    re.compile(r"\btempfile\."),
]
_SIMULATION_TRIGGERS = ("SequenceAdapter(", "run_scenario(")


def _discovered_notebooks() -> list[Path]:
    return sorted(NOTEBOOKS_DIR.glob("*.ipynb"))


def _code_cells(notebook) -> list:
    return [cell for cell in notebook.cells if cell.cell_type == "code"]


def _markdown_text(notebook) -> str:
    return "\n".join(cell.source for cell in notebook.cells if cell.cell_type == "markdown")


def _code_text(notebook) -> str:
    return "\n".join(cell.source for cell in _code_cells(notebook))


@pytest.fixture(scope="module")
def executed_notebooks():
    """Executes every discovered notebook once, returning
    `{path: executed_notebook}` for the other tests to inspect (executing
    each notebook only once per test session, not once per assertion)."""
    executed = {}
    for path in _discovered_notebooks():
        notebook = nbformat.read(path, as_version=4)
        client = NotebookClient(notebook, timeout=CELL_TIMEOUT_S, kernel_name=KERNEL_NAME)
        try:
            client.execute(cwd=str(NOTEBOOKS_DIR))
        except CellExecutionError as exc:
            pytest.fail(f"{path.name} raised during execution:\n{exc}")
        executed[path] = notebook
    return executed


@pytest.mark.parametrize("required_name", REQUIRED_H1_NOTEBOOKS)
def test_required_h1_notebook_exists(required_name):
    assert (NOTEBOOKS_DIR / required_name).exists(), f"missing required notebook: {required_name}"


def test_at_least_the_required_h1_notebooks_are_discovered():
    discovered_names = {path.name for path in _discovered_notebooks()}
    missing = set(REQUIRED_H1_NOTEBOOKS) - discovered_names
    assert not missing, f"required notebooks not found under notebooks/: {missing}"


def test_all_notebooks_execute_without_exception(executed_notebooks):
    # the `executed_notebooks` fixture already raises via pytest.fail on
    # any CellExecutionError; reaching this point means every notebook ran
    assert len(executed_notebooks) >= len(REQUIRED_H1_NOTEBOOKS)


@pytest.mark.parametrize("notebook_name", REQUIRED_H1_NOTEBOOKS)
def test_notebook_produced_visible_output(executed_notebooks, notebook_name):
    path = NOTEBOOKS_DIR / notebook_name
    notebook = executed_notebooks[path]
    code_cells = _code_cells(notebook)
    cells_with_output = [cell for cell in code_cells if cell.get("outputs")]
    assert cells_with_output, f"{notebook_name} produced no visible output in any code cell"


@pytest.mark.parametrize("notebook_name", REQUIRED_H1_NOTEBOOKS)
def test_notebook_does_not_reference_external_temp_paths(notebook_name):
    notebook = nbformat.read(NOTEBOOKS_DIR / notebook_name, as_version=4)
    code = _code_text(notebook)
    for pattern in _EXTERNAL_TEMP_PATTERNS:
        assert not pattern.search(code), f"{notebook_name} references an external temp path ({pattern.pattern})"


@pytest.mark.parametrize("notebook_name", REQUIRED_H1_NOTEBOOKS)
def test_notebook_uses_an_explicit_seed_when_it_simulates(notebook_name):
    notebook = nbformat.read(NOTEBOOKS_DIR / notebook_name, as_version=4)
    code = _code_text(notebook)
    if any(trigger in code for trigger in _SIMULATION_TRIGGERS):
        assert "seed=" in code or "seed =" in code, (
            f"{notebook_name} runs a simulation but never sets an explicit seed"
        )


@pytest.mark.parametrize("notebook_name", REQUIRED_H1_NOTEBOOKS)
def test_notebook_has_required_markdown_sections(notebook_name):
    """Each notebook must at least mention its objective and limitations in
    Markdown (see the project brief's per-notebook structure requirement)."""
    notebook = nbformat.read(NOTEBOOKS_DIR / notebook_name, as_version=4)
    text = _markdown_text(notebook).lower()
    for required_word in ("objetivo", "limita"):
        assert required_word in text, f"{notebook_name} is missing a Markdown section mentioning '{required_word}'"
