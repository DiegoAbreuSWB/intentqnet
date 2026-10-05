# results/realistic - calibrated campaign suite

Raw and processed outputs of the campaigns described in
`docs/realistic_campaigns.md`, run on 2026-10-01/02. These replace the
frozen legacy results under `results/` (scalar-fidelity model) as the
evidence base of the manuscript (`paper_ibqn_v2/`).

## Contents

| Path | Campaign | Rows |
|---|---|---|
| `audit/generation_model_audit.csv` (+ `_summary.csv`) | R00 generation-model audit | 312 runs / 30 cells |
| `audit/state_integrity_audit.csv` | R00b state-integrity audit | 39 runs |
| `baselines/R01_architecture_baselines/trials.csv` | R01 | 280 |
| `raw/R02_routing/trials.csv` | R02 | 240 |
| `raw/R03_purification/trials.csv` | R03 | 2,240 |
| `planner_study/R04_planner_evolution/trials.csv` | R04 | 3,080 |
| `planner_study/R04b_simulation_planner/trials.csv` | R04b | 60 |
| `oracle/R05_oracle_by_planner/oracle_cases.csv`, `oracle_by_planner.csv` | R05 | 440 cases / 740 planner rejections |
| `reconciliation/R06_reconciliation/trials.csv` | R06 | 240 |
| `overhead/R07_overhead/trials.csv` | R07 | 120 |
| `raw/R08_resource_semantics/trials.csv` | R08 | 160 |
| `multi_intent/R09_multi_intent/{jobs,groups,intents}.csv` | R09 | 120 groups / 240 intents |
| `baselines/R10_application_layer/trials.csv` | R10 stock SeQUeNCe vs IBQN, same route and seed | 200 (100 per path) |
| `manifests/*.json` | campaign manifests of R02, R03, R08 | |
| `processed/*.csv`, `processed/SUMMARY.md` | tables computed by `scripts/realistic/analyze_suite.py` | |
| `figures/*.pdf`, `*.png` | figures drawn by `scripts/realistic/generate_figures.py` | |

Every campaign ran under both hardware conditions (`literature`,
`theoretical_ops`); the `hardware` column (or the `<topology>@<hardware>`
scenario name) identifies it.

## Provenance

- Commit hashes: the repository history was rewritten on 2026-10-03 and
  2026-10-04: commit messages were edited and the manuscript sources were
  removed from every commit; code, data, authors and dates are otherwise
  unchanged. The `project_git_commit` columns, the manifests and the text
  below name the earlier hashes, as the rows do; `docs/commit_hash_map.csv`
  gives the current commit of each, and the `git diff` command below uses
  the current ones. Those named here are now `aab2fed` -> `36ff401`,
  `c68f9e1` -> `80f6f00`, `0a4f18a` -> `8ff7385`, `85b7553` -> `f976e8c`,
  `1014042` -> `fe5677d`, `11e8444` -> `11547f4`.
- Simulator: SeQUeNCe submodule, source unmodified (commit in the
  `sequence_git_commit` column where recorded).
- Project code: rows carry the commit that was checked out when their
  campaign process started - `aab2fed`, `c68f9e1`, `0a4f18a`, `85b7553` or
  `1014042`, because campaigns were resumed after interruptions. Between
  `aab2fed` and `1014042` the only source changes under `src/` are campaign
  infrastructure (`experiments/manifests.py`: retry on a locked file;
  `experiments/realistic_suite.py`: checkpoint frequency and atomic writes;
  `utils/power.py`: keep the machine awake). Nothing that affects a
  simulation, a planning decision or an evaluation changed, so the rows are
  mutually consistent (`git diff 36ff401 fe5677d -- src`).
- R10 ran later, at `11e8444`, the commit that makes the intent's policy
  bound reconciliation (`policy.max_resource_scale`, `allow_rerouting`).
  That change touches only the reconciliation decision, and R06 declares
  the permission it uses (`max_resource_scale = 2`): rerunning three seeds
  of every R06 case with `11e8444` reproduced the committed rows field by
  field (36 jobs, 0 mismatching fields).
- Seeds: every (trial, node) pair has its own random generator
  (`seed_derivation="independent"`); the oracle and the second
  reconciliation episode use seeds offset from the trial's.
- A resumed campaign reruns nothing: a job whose key is already in the
  output file is skipped, and a rerun of the same job reproduces the same
  row (same seed, same simulation).

## Regenerating

```
python scripts/realistic/audit_generation_model.py 8 12
python scripts/realistic/audit_state_integrity.py 4 3
python scripts/realistic/run_suite.py all --workers 8
python scripts/realistic/analyze_suite.py
python scripts/realistic/generate_figures.py
python scripts/realistic/build_manuscript_inputs.py
```

About 7 hours of wall time with 8 worker processes. Wall-clock columns
(`*_wall_time_s`, `planning_time_s`) depend on the machine and on what else
it was running; the overhead campaign (R07) ran last, with no other
campaign running.
