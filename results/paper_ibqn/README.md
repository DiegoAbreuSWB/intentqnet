# IBQN paper artifacts (P-IBQN2, P-IBQN3)

Processed manuscript data, tables, and figures for the IBQN architecture
paper. Everything here is mechanically generated from frozen raw/processed
campaign files and Validation-A/B outputs — nothing is hand-transcribed.
No new simulations were run to produce any of it.

## Regenerating

Run in order (each is idempotent and safe to re-run):

```
python scripts/paper_ibqn/generate_processed_data.py   # writes processed/*.csv
python scripts/paper_ibqn/generate_tables.py            # writes tables/*.tex (reads processed/*.csv)
python scripts/paper_ibqn/generate_figures.py            # writes figures/*.{pdf,png} (reads processed/*.csv + 2 frozen raw files, see below)
python -m pytest tests/paper_ibqn/test_manuscript_artifacts.py -v
```

None of these scripts run a SeQUeNCe simulation, touch a planner, or write
to any frozen `results/` path outside `results/paper_ibqn/` and
`results/ibqn_paper/`.

## Directory structure

- `processed/` — 12 CSVs, one per table, each row carrying explicit
  `campaign`, `source_file`, `claim_id`, and `note` provenance columns.
  Ambiguous cells use one of three literal markers, never a blank cell:
  `NA_NOT_APPLICABLE` (doesn't apply by design), `NA_NOT_MEASURED`
  (could apply, wasn't instrumented), `NA_NOT_COMPARABLE` (a real number
  exists but must not be combined with the other rows in that table).
- `tables/` — 12 `.tex` tables, each generated directly from its
  processed CSV, each with a header comment citing its source file and
  claim ID(s).
- `figures/` — 14 figures (28 files: PDF vector + PNG raster each),
  matplotlib only (no seaborn), no pie charts, no 3D, never a
  color-only distinction (hatches/markers used throughout).

## Frozen sources these artifacts draw from

All read-only; none modified by any script in `scripts/paper_ibqn/`:

- `results/planner_study/raw/P02b_resource_aware_planners/trials.csv` (L1-L3-R)
- `results/planner_study/raw/P03_l4_cost/trials.csv` + `results/predictability_m10/raw/P13_l4_boundary_reference/trials.csv` (L4)
- `results/processed/F04_planner_vs_operation/{matrix.csv,gap_metrics.json}` (F04)
- `results/raw/F05_reconciliation/trials.csv` (F05)
- `results/raw/F06_overhead/trials.csv` (F06)
- `results/ibqn_validation_b/P16_oracle_by_planner/oracle_results.csv` (B2)
- `results/ibqn_validation_b/P17_concurrent_intents/{intents,groups}.csv` (B3/B4)
- `src/ibqn/intent/models.py`, `src/ibqn/intent/lifecycle.py` (schema/lifecycle, code inspection)

## F04 vs. P02b/B2 — kept separate everywhere, on purpose

Two oracle experiments appear in these artifacts. They are **never**
merged, summed, or presented as replications of each other:

- **F04 (`oracle_purification_boundary.csv`/`.tex`)**: the generic
  `planning.planner.IntentPlanner` wrapper (not any L1-L6 policy),
  `three_node_1_repeater` only, fidelity thresholds deliberately
  densified around the one-round purification ceiling. 240/240
  oracle-tested rejections confirmed satisfiable. Not used to rank
  planners.
- **P02b/B2 (`oracle_by_planner.csv`/`.tex`)**: the real L1/L2/L2-R
  `IntentPlannerPolicy` classes, a broader multi-topology combo grid not
  targeted at any one ceiling. L1 0/110, L2 0/40, L2-R 28/150.

See `docs/paper_ibqn_validation/oracle_result_reconciliation.md` for the
full reconciliation of why these numbers differ. `tests/paper_ibqn/
test_manuscript_artifacts.py` mechanically enforces the separation
(different column schemas, F04 never appears in the by-planner table,
the generic `IntentPlanner` is never relabeled "L1").

## Known, disclosed limitations of this artifact set

- **No LaTeX compiler was available in this environment** (no
  `pdflatex`/`latexmk`/`tectonic` found). "Compile in isolation" is
  therefore checked *structurally* — balanced `\begin`/`\end`, balanced
  braces, consistent column counts per table — not by an actual PDF
  compile. This is disclosed here and in the test file's docstring, not
  presented as a real compile-PASS.
- `overhead_results.csv`'s `reconciliation` and `persistence`/`route_application`
  rows are `NA_NOT_MEASURED` — P17 produced 0 VIOLATED outcomes (nothing
  to time for reconciliation) and a disclosed instrumentation defect
  left true persistence cost unisolated (see `docs/paper_ibqn_validation/
  overhead_measurement.md`). Neither is estimated or imputed.
- `planner_error_results.csv`'s false-feasibility rate uses a
  **corrected** denominator (admitted AND operationally executed,
  excluding SIMULATION_ERROR/TIMEOUT trials) that differs from
  Validation-A's original `architectural_validation_matrix.md` Table 2
  (which used admitted alone). L3/L3-R's rate changes from 55.8% to
  67.0% under the corrected denominator. An erratum note was added to
  `architectural_validation_matrix.md` pointing here — the original
  Validation-A text is preserved, not silently rewritten.
- L4 is not on the same matched seed/intent grid as L1-L3-R in any table
  here (`planner_error_results.csv`, `planner_capabilities.csv`) —
  marked `NA_NOT_COMPARABLE` where relevant, never silently averaged in.
