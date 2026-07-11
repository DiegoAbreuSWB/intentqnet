"""Ensures the Jupyter kernel these tests execute notebooks with is
registered under the *current* Python environment, so `pytest tests/notebooks`
works on a fresh clone without a separate manual setup step (see
docs/notebooks.md).
"""
import subprocess
import sys

import pytest
from jupyter_client.kernelspec import KernelSpecManager

KERNEL_NAME = "ibqn-venv"


@pytest.fixture(scope="session", autouse=True)
def ensure_notebook_kernel_registered():
    manager = KernelSpecManager()
    if KERNEL_NAME not in manager.find_kernel_specs():
        subprocess.run(
            [sys.executable, "-m", "ipykernel", "install", "--user", "--name", KERNEL_NAME,
             "--display-name", "Python (ibqn)"],
            check=True,
        )
    yield
