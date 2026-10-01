"""Project-wide pytest fixtures.

SeQUeNCe keeps several *process-wide* switches as class attributes:

- `QuantumManager._global_formalism` (set by `Timeline(formalism=...)`)
- `EntanglementGenerationA/B._global_type` (Barrett-Kok vs single-heralded)
- `EntanglementSwappingA/B._global_formalism` and
  `BBPSSWProtocol._global_formalism` (circuit vs Bell-diagonal variants)

`ibqn.network.sequence_adapter.SequenceAdapter` sets all of them
consistently for the formalism a `NetworkTopologySpec` declares (see
docs/physical_model.md). Without a reset between tests, a `bell_diagonal`
test would leak its switches into a later `ket_vector` test (or vice
versa) - the same class of cross-test pollution documented for SeQUeNCe's
own suite in docs/sequence_code_analysis.md, section 0.2. This autouse
fixture restores SeQUeNCe's defaults after every test.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_sequence_global_switches():
    yield
    from ibqn.network.sequence_adapter import reset_sequence_globals

    reset_sequence_globals()
