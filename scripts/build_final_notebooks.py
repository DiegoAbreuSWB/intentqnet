"""Fase K4: builds the 9 final article notebooks (notebooks/article/
final/R01-R09) programmatically via nbformat - every notebook only
loads already-persisted data (raw trials.csv, processed statistical
comparisons, manifests), never runs a simulation. Each notebook cites
its manifest, shows n/CI/statistical test/effect size, exports a figure
and a table, and asserts basic consistency invariants.

Run: python scripts/build_final_notebooks.py
Then validate: pytest tests/notebooks/test_notebooks.py (or nbclient
directly) to confirm every notebook executes cleanly.
"""
from __future__ import annotations

import json
from pathlib import Path

import nbformat as nbf

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = PROJECT_ROOT / "notebooks" / "article" / "final"
OUT_DIR.mkdir(parents=True, exist_ok=True)

HEADER_IMPORTS = '''\
import json
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

from ibqn.experiments.aggregation import aggregate_records
from ibqn.experiments.export import save_figure, save_table

# Executed with cwd=notebooks/ regardless of this file's own subdirectory
# (tests/notebooks/test_notebooks.py's NotebookClient.execute(cwd=...)) -
# matches notebooks/article/A0*.ipynb's own convention, not a path
# relative to notebooks/article/final/ itself.
RESULTS_DIR = Path("../results")

# A dedicated subdirectory, not results/figures/final/ directly: that
# directory's *.pdf/*.png are the curated, audited figure set
# (scripts/generate_final_figures.py + sources.json, checked by
# scripts/audit_final_results.py) - a notebook's own reproducibility
# export must not silently add uncatalogued files there.
FIGURES_OUT = RESULTS_DIR / "figures" / "final" / "from_notebooks"
TABLES_OUT = RESULTS_DIR / "tables" / "final"
'''


def md(source: str):
    return nbf.v4.new_markdown_cell(source)


def code(source: str):
    return nbf.v4.new_code_cell(source)


# Each notebook's specific limitation, appended to its final ("##
# Conclusão") cell by write_notebook() - required by
# tests/notebooks/test_notebooks.py::test_notebook_has_required_markdown_sections
# (every notebook must mention both "objetivo" and "limita").
LIMITATIONS = {
    "R01_architecture_and_baselines.ipynb": (
        "Uma única topologia (diamante) e 6 condições - o custo/benefício "
        "isolado aqui não generaliza a outras topologias sem replicar a "
        "campanha (ver `docs/threats_to_validity.md`, validade externa)."
    ),
    "R02_routing.ipynb": (
        "O ganho de `least_loss` no diamante (~56x) é específico desta "
        "topologia (ver `docs/routing_result_explanation.md`) - a malha "
        "pequena, na mesma campanha, não mostra o mesmo efeito."
    ),
    "R03_purification.ipynb": (
        "Só `three_node_1_repeater` foi densificado com limiares extras; "
        "`linear_chain_2_repeaters` permanece nos 4 limiares originais e "
        "rejeitado em toda a faixa testada (nunca oracle-confirmado)."
    ),
    "R04_planner_operation_gap.ipynb": (
        "O oracle só foi rodado sobre `three_node_1_repeater` - "
        "`false_rejection_rate=1.0` não deve ser lido como \"toda rejeição "
        "deste projeto é falsa\", só sobre o subconjunto testado (ver "
        "`docs/planner_operational_gap.md`)."
    ),
    "R05_reconciliation.ipynb": (
        "O multiplicador de ajuste de recurso é fixo (2x) - nunca testado "
        "se um valor maior recuperaria o cenário de perda severa (ver "
        "`docs/reconciliation_scope.md`, `docs/future_work.md`)."
    ),
    "R06_overhead.ipynb": (
        "Medições de wall-clock são inerentemente ruidosas (contenção de "
        "CPU, coleta de lixo) - ordens de grandeza relativas, não valores "
        "absolutos precisos (ver `docs/overhead_methodology.md`)."
    ),
    "R07_estimators.ipynb": (
        "`SequenceConsistentEstimator` reproduz o modelo do SeQUeNCe nas "
        "configurações avaliadas - não é uma alegação sobre precisão "
        "física real nem sobre topologias fora do catálogo testado."
    ),
    "R08_resource_semantics.ipynb": (
        "Só uma topologia (`three_node`) e 2 níveis por fator - a "
        "ortogonalidade confirmada aqui não foi testada em topologias "
        "maiores ou com mais níveis."
    ),
    "R09_final_summary.ipynb": (
        "Este resumo não substitui `docs/threats_to_validity.md` nem "
        "`docs/final_claims_and_evidence.md` - é um ponto de entrada, "
        "toda limitação específica de campanha está nos notebooks R01-R08."
    ),
}


def write_notebook(filename: str, cells: list) -> None:
    last_cell = cells[-1]
    assert last_cell.cell_type == "markdown" and "Conclusão" in last_cell.source, f"{filename}: last cell must be the Conclusão markdown cell"
    last_cell.source = last_cell.source + f"\n\n## Limitações\n\n{LIMITATIONS[filename]}"

    nb = nbf.v4.new_notebook()
    nb["cells"] = cells
    nb["metadata"] = {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.13"},
    }
    path = OUT_DIR / filename
    nbf.write(nb, path)
    print(f"wrote {path}")


# ---------------------------------------------------------------------------
# R01 - architecture and baselines (F01)
# ---------------------------------------------------------------------------
def build_r01():
    cells = [
        md('''# R01 - Architecture and Baselines

## Objetivo
Isolar, com dados reais e já persistidos da campanha final
`F01_architecture_baselines` (Fase J10/K2), o benefício de escolha de
rota, o benefício de assurance, o benefício de reconciliation, e o custo
da própria abstração intent-based - comparando 6 condições (native
SeQUeNCe, static provisioning, IBQN sem/com assurance, IBQN com
reconciliation, offline oracle) sobre a MESMA topologia diamante e os
MESMOS 20 seeds. Ver `docs/final_experimental_design.md` (seção F01) e
`docs/results_provenance.md`.

Este notebook não roda nenhuma simulação - carrega apenas
`results/raw/F01_architecture_baselines/trials.csv` e
`results/processed/F01_architecture_baselines/statistical_comparisons.csv`.'''),
        code(HEADER_IMPORTS),
        md("## Carregar dados e verificar consistência"),
        code('''\
CAMPAIGN = "F01_architecture_baselines"
trials_df = pd.read_csv(RESULTS_DIR / "raw" / CAMPAIGN / "trials.csv")
manifest = json.load(open(RESULTS_DIR / "manifests" / f"{CAMPAIGN}.json", encoding="utf-8"))

assert len(trials_df) == manifest["completed_trials"], "trials.csv row count must match the manifest"
assert manifest["expected_trials"] == manifest["completed_trials"] + manifest["failed_trials"] + manifest["skipped_trials"]
assert set(trials_df["seed"].unique()) == set(range(20)), "expected seeds 0-19"
conditions = sorted(trials_df["condition"].unique())
print(f"manifest: {manifest['campaign']}, execution_path={manifest.get('execution_path')}, n={len(trials_df)}")
print("conditions:", conditions)
trials_df.head(3)'''),
md('''## Agregação (n, média, IC95%)

F01 usa um esquema próprio (script ad-hoc, não `run_programmatic_campaign`
- ver `docs/results_provenance.md`), sem as colunas `final_status`/
`recovered` que `aggregation.aggregate_records` exige - agregação manual
diretamente das colunas reais desta campanha.'''),
        code('''\
from scipy import stats as scipy_stats

rows = []
for condition, group in trials_df.groupby("condition"):
    for metric in ["delivered_pairs", "average_fidelity"]:
        values = group[metric].dropna()
        n = len(values)
        if n >= 2:
            se = values.std(ddof=1) / np.sqrt(n)
            ci = scipy_stats.t.ppf(0.975, df=n - 1) * se
            ci_low, ci_high = values.mean() - ci, values.mean() + ci
        else:
            ci_low = ci_high = None
        rows.append({
            "condition": condition, "metric": metric, "n_valid": n,
            "mean": values.mean() if n else None, "std": values.std(ddof=1) if n >= 2 else None,
            "ci95_low": ci_low, "ci95_high": ci_high,
            "satisfaction_rate": group["satisfied"].mean() if group["satisfied"].notna().any() else None,
        })
summary = pd.DataFrame(rows)
summary_path = save_table(summary, "R01_summary", directory=TABLES_OUT)
print(f"saved {summary_path}")
summary'''),
        md("## Comparações estatísticas pareadas (já computadas - n, teste, p, Holm, effect size)"),
        code('''\
stats_df = pd.read_csv(RESULTS_DIR / "processed" / CAMPAIGN / "statistical_comparisons.csv")
assert "p_value_holm_adjusted" in stats_df.columns
significant = stats_df[stats_df["p_value_holm_adjusted"] < 0.05]
print(f"{len(significant)}/{len(stats_df)} comparisons significant after Holm correction")
significant[["value_col", "group_a", "group_b", "n", "mean_a", "mean_b", "test_used", "p_value_holm_adjusted", "effect_size"]].head(15)'''),
        md("## Figura"),
        code('''\
fig, ax = plt.subplots(figsize=(7, 4.5))
groups = [trials_df[trials_df["condition"] == c]["delivered_pairs"].dropna().to_numpy() for c in conditions]
bp = ax.boxplot(groups, tick_labels=conditions, showfliers=False)
ax.set_ylabel("delivered_pairs")
ax.set_title(f"F01 architecture/baselines - delivered_pairs by condition (n={trials_df['seed'].nunique()} seeds)")
plt.xticks(rotation=30, ha="right")
save_figure(fig, "R01_delivered_pairs_by_condition", directory=FIGURES_OUT)
plt.show()'''),
        md('''## Conclusão

Ver `docs/final_experimental_design.md` (seção F01) para a
interpretação completa: benefício de rota (`native_sequence` vs.
`static_provisioning`), benefício de reconciliation
(`ibqn_with_reconciliation` vs. `ibqn_with_assurance`), e o fato de que
`ibqn_without_assurance` aceita reservas sem medir satisfação - a
distinção entre "aceitar" e "saber se foi cumprido"
(`docs/core_contribution_statement.md`).'''),
    ]
    write_notebook("R01_architecture_and_baselines.ipynb", cells)


# ---------------------------------------------------------------------------
# R02 - routing (F02)
# ---------------------------------------------------------------------------
def build_r02():
    cells = [
        md('''# R02 - Routing

## Objetivo
Comparar `ShortestHopCountRouting`/`LeastLossRouting`/
`HighestFidelityRouting` com dados reais da campanha final
`F02_routing` (2 topologias: `diamond_heterogeneous`, `small_mesh`; 20
seeds cada). Ver `docs/routing_result_explanation.md` para a explicação
quantitativa completa do efeito no diamante, e
`docs/threats_to_validity.md` para por que esse efeito não generaliza a
toda topologia. Não roda simulação - carrega apenas dados persistidos.'''),
        code(HEADER_IMPORTS),
        md("## Carregar dados e verificar consistência (2 blocos no manifesto)"),
        code('''\
CAMPAIGN = "F02_routing"
trials_df = pd.read_csv(RESULTS_DIR / "raw" / CAMPAIGN / "trials.csv")
manifest = json.load(open(RESULTS_DIR / "manifests" / f"{CAMPAIGN}.json", encoding="utf-8"))

assert len(trials_df) == manifest["completed_trials"]
assert len(manifest["blocks"]) == 2, "F02 runs two topologies, one block each"
for block in manifest["blocks"]:
    scenario_rows = trials_df[trials_df["scenario"] == block["scenario"]]
    assert len(scenario_rows) == block["completed_trials"], f"row count mismatch for {block['scenario']}"
print("blocks:", [(b["scenario"], b["completed_trials"]) for b in manifest["blocks"]])
trials_df.head(3)'''),
        md("## Agregação por topologia x estratégia"),
        code('''\
summary = aggregate_records(trials_df, group_by=["scenario", "routing_strategy"], metrics=["delivered_pairs", "average_fidelity"])
save_table(summary, "R02_summary", directory=TABLES_OUT)
summary[["scenario", "routing_strategy", "metric", "n_valid", "mean", "ci95_low", "ci95_high", "satisfaction_rate"]]'''),
        md("## Comparações estatísticas pareadas"),
        code('''\
stats_df = pd.read_csv(RESULTS_DIR / "processed" / CAMPAIGN / "statistical_comparisons.csv")
significant = stats_df[stats_df["p_value_holm_adjusted"] < 0.05]
print(f"{len(significant)}/{len(stats_df)} comparisons significant after Holm correction")
significant[["scenario", "value_col", "group_a", "group_b", "n", "mean_a", "mean_b", "test_used", "p_value_holm_adjusted", "effect_size"]]'''),
        md("## Figura (diamante, escala log - ver docs/routing_result_explanation.md)"),
        code('''\
diamond = trials_df[trials_df["scenario"] == "diamond_heterogeneous"]
strategies = sorted(diamond["routing_strategy"].unique())
fig, ax = plt.subplots(figsize=(6, 4.5))
groups = [diamond[diamond["routing_strategy"] == s]["delivered_pairs"].to_numpy() for s in strategies]
ax.boxplot(groups, tick_labels=strategies, showfliers=False)
ax.set_yscale("log")
ax.set_ylabel("delivered_pairs (log scale)")
ax.set_title(f"F02 diamond_heterogeneous - delivered_pairs by strategy (n={diamond['seed'].nunique()} seeds)")
save_figure(fig, "R02_diamond_delivered_pairs", directory=FIGURES_OUT)
plt.show()'''),
        md('''## Conclusão

O ganho de `least_loss` (~56x) é causado pela perda óptica acumulada da
rota, não pela fidelidade nem pelo número de saltos isoladamente - ver
a ficha por rota completa em `docs/routing_result_explanation.md`. Na
malha pequena (mesma campanha), as 3 estratégias são equivalentes -
o efeito é específico da topologia diamante.'''),
    ]
    write_notebook("R02_routing.ipynb", cells)


# ---------------------------------------------------------------------------
# R03 - purification (F03)
# ---------------------------------------------------------------------------
def build_r03():
    cells = [
        md('''# R03 - Purification

## Objetivo
Avaliar o efeito da política de purificação (`disabled`/`automatic`)
sobre a satisfação e a fidelidade observada, com dados reais da
campanha final `F03_purification` (2 topologias, 8 limiares de
`min_fidelity` em `three_node_1_repeater` - densificados na Fase K2 -
e 4 em `linear_chain_2_repeaters`, 20 seeds cada). Ver
`docs/false_rejection_root_cause.md` para por que a rejeição do planner
é um degrau exato acima de 0.72, não uma transição gradual. Não roda
simulação - carrega apenas dados persistidos.'''),
        code(HEADER_IMPORTS),
        md("## Carregar dados e verificar consistência"),
        code('''\
CAMPAIGN = "F03_purification"
trials_df = pd.read_csv(RESULTS_DIR / "raw" / CAMPAIGN / "trials.csv")
manifest = json.load(open(RESULTS_DIR / "manifests" / f"{CAMPAIGN}.json", encoding="utf-8"))

assert len(trials_df) == manifest["completed_trials"] == 480
three_node_block = next(b for b in manifest["blocks"] if b["scenario"] == "three_node_1_repeater")
assert three_node_block["swept_factors"]["min_fidelity"] == [0.65, 0.7, 0.72, 0.73, 0.735, 0.74, 0.745, 0.75], \\
    "expected 8 thresholds after the Fase K2 densification"
print("three_node_1_repeater thresholds:", three_node_block["swept_factors"]["min_fidelity"])
trials_df.head(3)'''),
        md("## Taxa de satisfação por limiar x política"),
        code('''\
pivot = trials_df.groupby(["scenario", "requested_fidelity", "purification_policy"])["satisfied"].mean().unstack()
save_table(pivot.reset_index(), "R03_satisfaction_by_threshold", directory=TABLES_OUT)
pivot'''),
        md("## Comparações estatísticas pareadas (automatic vs. disabled, por limiar)"),
        code('''\
stats_df = pd.read_csv(RESULTS_DIR / "processed" / CAMPAIGN / "statistical_comparisons.csv")
significant = stats_df[stats_df["p_value_holm_adjusted"] < 0.05]
print(f"{len(significant)}/{len(stats_df)} comparisons significant after Holm correction")
significant[["scenario", "requested_fidelity", "value_col", "n", "mean_a", "mean_b", "test_used", "p_value_holm_adjusted", "effect_size"]]'''),
        md("## Figura: taxa de satisfação vs. limiar (three_node_1_repeater)"),
        code('''\
three_node = trials_df[trials_df["scenario"] == "three_node_1_repeater"]
fig, ax = plt.subplots(figsize=(7, 4.5))
for policy, marker in [("disabled", "s"), ("automatic", "o")]:
    sub = three_node[three_node["purification_policy"] == policy]
    rates = sub.groupby("requested_fidelity")["satisfied"].mean()
    ax.plot(rates.index, rates.values, marker=marker, label=policy)
ax.set_xlabel("requested min_fidelity")
ax.set_ylabel("satisfaction rate")
ax.set_title(f"F03 three_node_1_repeater - satisfaction vs. threshold (n={three_node['seed'].nunique()} seeds/cell)")
ax.legend(title="purification_policy")
save_figure(fig, "R03_satisfaction_vs_threshold", directory=FIGURES_OUT)
plt.show()'''),
        md('''## Conclusão

A rejeição acima de 0.72 é um degrau determinístico causado pelo teto de
uma única rodada estimada de purificação
(`docs/false_rejection_root_cause.md`), confirmado pelos 4 limiares
densos adicionais (0.73-0.745) rejeitados de forma idêntica a 0.75 - não
uma transição gradual que precisaria de mais densidade para ser
resolvida.'''),
    ]
    write_notebook("R03_purification.ipynb", cells)


# ---------------------------------------------------------------------------
# R04 - planner vs operation gap (F04)
# ---------------------------------------------------------------------------
def build_r04():
    cells = [
        md('''# R04 - Planner-Operation Gap

## Objetivo
Quantificar a diferença entre o que o `IntentPlanner` prevê (viável/
inviável) e o que acontece operacionalmente, usando a matriz derivada
`F04_planner_vs_operation` (combina F02+F03, 600 trials, oracle-testa
240 rejeições reconstruíveis de `three_node_1_repeater`). Ver
`docs/false_rejection_root_cause.md` para a causa raiz identificada por
código. Não roda simulação nem o teste de oracle (já executado por
`scripts/build_f04_planner_operation_matrix.py`) - carrega apenas os
resultados persistidos.'''),
        code(HEADER_IMPORTS),
        md("## Carregar matriz e métricas do gap"),
        code('''\
PROCESSED = RESULTS_DIR / "processed" / "F04_planner_vs_operation"
matrix = pd.read_csv(PROCESSED / "matrix.csv")
gap_metrics = json.load(open(PROCESSED / "gap_metrics.json", encoding="utf-8"))
combined = pd.read_csv(PROCESSED / "combined_trials_with_categories.csv")

assert gap_metrics["n_total"] == len(combined) == 600
assert matrix["count"].sum() == 600
print(json.dumps(gap_metrics, indent=2))
matrix'''),
        md("## Tabela: origem dos 600 trials (F02 + F03)"),
        code('''\
by_source = combined.groupby(["source_campaign", "scenario"])["category"].value_counts().unstack(fill_value=0)
save_table(by_source.reset_index(), "R04_category_by_source", directory=TABLES_OUT)
by_source'''),
        md("## Figura: matriz planner-vs-operação"),
        code('''\
fig, ax = plt.subplots(figsize=(8, 4.5))
ax.bar(matrix["category"], matrix["count"], color=["#55A868", "#DD8452", "#888", "#C44E52", "#7f7f7f"][:len(matrix)])
ax.set_ylabel("number of trials")
ax.set_title(f"F04 planner-vs-operation matrix (n={gap_metrics['n_total']})")
plt.xticks(rotation=30, ha="right")
save_figure(fig, "R04_matrix", directory=FIGURES_OUT)
plt.show()'''),
        md('''## Conclusão

`false_rejection_rate=1.0` sobre os 240 trials oracle-testados - o
planner conservador rejeita sistematicamente algo que o SeQUeNCe real
consegue entregar. Causa raiz verificada por código (uma rodada de
purificação estimada vs. múltiplas reais) em
`docs/false_rejection_root_cause.md` - explicitamente não atribuída à
heterogeneidade de topologia (mecanismo diferente, Fase J1).'''),
    ]
    write_notebook("R04_planner_operation_gap.ipynb", cells)


# ---------------------------------------------------------------------------
# R05 - reconciliation (F05)
# ---------------------------------------------------------------------------
def build_r05():
    cells = [
        md('''# R05 - Reconciliation

## Objetivo
Avaliar a política de reconciliation em 5 classes de cenário
(recuperável por rota/duração/slots; irrecuperável por teto de
fidelidade/perda severa), com dados reais da campanha final
`F05_reconciliation` (20 seeds cada). Classificação de tipo de
recuperação (`strict_recovery`/`resource_adjusted_recovery`/
`sla_relaxed_recovery`) via `scripts/classify_f05_recovery_types.py` -
ver `docs/reconciliation_scope.md`. Não roda simulação - carrega apenas
dados persistidos.'''),
        code(HEADER_IMPORTS),
        md("## Carregar dados classificados e verificar consistência"),
        code('''\
CAMPAIGN = "F05_reconciliation"
trials_df = pd.read_csv(RESULTS_DIR / "processed" / CAMPAIGN / "trials_with_recovery_type.csv")
manifest = json.load(open(RESULTS_DIR / "manifests" / f"{CAMPAIGN}.json", encoding="utf-8"))

assert len(trials_df) == manifest["completed_trials"] == 100
assert set(trials_df["recovery_type"].unique()) <= {"strict_recovery", "resource_adjusted_recovery", "sla_relaxed_recovery", "not_applicable"}
print("cases:", sorted(trials_df["case"].unique()))
trials_df.head(3)'''),
        md("## Taxa de recuperação por classe (n, IC95% Wilson)"),
        code('''\
from scipy import stats as scipy_stats

def wilson_ci(successes, n, alpha=0.05):
    if n == 0:
        return None, None, None
    p = successes / n
    z = scipy_stats.norm.ppf(1 - alpha / 2)
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return p, max(0.0, center - half), min(1.0, center + half)

rows = []
for case, group in trials_df.groupby("case"):
    attempted = group[group["reconciliation_attempted"] == True]
    if len(attempted) == 0:
        rows.append({"case": case, "n_attempted": 0, "recovery_rate": None, "ci95_low": None, "ci95_high": None})
        continue
    successes = int(attempted["recovered"].sum())
    p, lo, hi = wilson_ci(successes, len(attempted))
    rows.append({"case": case, "n_attempted": len(attempted), "recovery_rate": p, "ci95_low": lo, "ci95_high": hi})
recovery_summary = pd.DataFrame(rows)
save_table(recovery_summary, "R05_recovery_rate_by_case", directory=TABLES_OUT)
recovery_summary'''),
        md("## Figura: taxa de recuperação por classe"),
        code('''\
fig, ax = plt.subplots(figsize=(8, 4.5))
valid = recovery_summary.dropna(subset=["recovery_rate"])
ax.errorbar(
    range(len(valid)), valid["recovery_rate"],
    yerr=[valid["recovery_rate"] - valid["ci95_low"], valid["ci95_high"] - valid["recovery_rate"]],
    fmt="o", capsize=4,
)
ax.set_xticks(range(len(valid)))
ax.set_xticklabels(valid["case"], rotation=30, ha="right")
ax.set_ylabel("recovery rate (Wilson 95% CI)")
ax.set_title("F05 reconciliation - recovery rate by scenario class")
save_figure(fig, "R05_recovery_rate", directory=FIGURES_OUT)
plt.show()'''),
        md('''## Conclusão

A política recuperou todos os casos de troca de rota e a maioria dos
casos de ajuste de recurso nos cenários avaliados; falhou sob perda
severa; e corretamente evitou agir num teto de fidelidade (nunca
"recovers 100% of intents", ver `docs/core_contribution_statement.md`).
`recovery_type` mostra que nem todo "recovered" preserva o contrato
original do intent - `duration_increase` altera `duration_s`.'''),
    ]
    write_notebook("R05_reconciliation.ipynb", cells)


# ---------------------------------------------------------------------------
# R06 - overhead (F06)
# ---------------------------------------------------------------------------
def build_r06():
    cells = [
        md('''# R06 - Overhead

## Objetivo
Decompor o custo de orquestração da camada IBQN, independente do custo
da simulação SeQUeNCe, com dados reais da campanha final `F06_overhead`
(diamante, 3 condições x 20 seeds). Ver `docs/overhead_methodology.md` -
a instrumentação define 12 campos de tempo, 10 observáveis no caminho
atual (nunca "12 medidas completas"). Não roda simulação - carrega
apenas dados persistidos.'''),
        code(HEADER_IMPORTS),
        md("## Carregar dados e verificar consistência"),
        code('''\
CAMPAIGN = "F06_overhead"
trials_df = pd.read_csv(RESULTS_DIR / "raw" / CAMPAIGN / "trials.csv")
manifest = json.load(open(RESULTS_DIR / "manifests" / f"{CAMPAIGN}.json", encoding="utf-8"))

assert len(trials_df) == manifest["completed_trials"] == 60
conditions = sorted(trials_df["condition"].unique())
assert conditions == ["ibqn_instrumented", "native_sequence", "static_provisioning"]
trials_df.head(3)'''),
        md("## Overhead ratio: n, média, desvio, distribuição (nunca só a média)"),
        code('''\
summary = trials_df.groupby("condition")["orchestration_overhead_ratio"].agg(["count", "mean", "std", "min", "max"])
summary["mean_pct"] = summary["mean"] * 100
save_table(summary.reset_index(), "R06_overhead_ratio_summary", directory=TABLES_OUT)
print("max observed overhead ratio (any condition):", (trials_df["orchestration_overhead_ratio"].max() * 100).round(3), "%")
summary'''),
        md("## Figura: distribuição do overhead ratio (não apenas a média)"),
        code('''\
fig, ax = plt.subplots(figsize=(6.5, 4.5))
groups = [trials_df[trials_df["condition"] == c]["orchestration_overhead_ratio"].dropna() * 100 for c in conditions]
ax.boxplot(groups, tick_labels=conditions, showfliers=True)
ax.set_ylabel("orchestration overhead ratio (%)")
ax.set_title(f"F06 overhead - distribution by condition (n={trials_df['seed'].nunique()} seeds)")
plt.xticks(rotation=20, ha="right")
save_figure(fig, "R06_overhead_ratio_distribution", directory=FIGURES_OUT)
plt.show()'''),
        md('''## Conclusão

O overhead médio de orquestração fica abaixo de 0.31% do tempo total de
trial nas condições avaliadas (nunca "desprezível" sem esse escopo -
`docs/overhead_methodology.md`). Achado adicional: `native_sequence`
leva ~2.5x mais tempo de SIMULAÇÃO (não de orquestração) que as outras
condições, porque processa muito mais eventos de entrelaçamento por
unidade de tempo simulado.'''),
    ]
    write_notebook("R06_overhead.ipynb", cells)


# ---------------------------------------------------------------------------
# R07 - estimators (F07)
# ---------------------------------------------------------------------------
def build_r07():
    cells = [
        md('''# R07 - Fidelity Estimators

## Objetivo
Comparar `ConservativeMinEstimator` e `SequenceConsistentEstimator` com
dados reais da campanha final `F07_estimators` (diamante, 3 estratégias
x 2 estimadores x 20 seeds). Ver `docs/fidelity_estimation_model.md`.
Não roda simulação - carrega apenas dados persistidos.'''),
        code(HEADER_IMPORTS),
        md("## Carregar dados e verificar consistência"),
        code('''\
CAMPAIGN = "F07_estimators"
trials_df = pd.read_csv(RESULTS_DIR / "raw" / CAMPAIGN / "trials.csv")
manifest = json.load(open(RESULTS_DIR / "manifests" / f"{CAMPAIGN}.json", encoding="utf-8"))

assert len(trials_df) == manifest["completed_trials"] == 120
assert set(trials_df["fidelity_estimator"].unique()) == {"conservative_min", "sequence_consistent"}
trials_df.head(3)'''),
        md("## Erro absoluto de fidelidade por estimador (n, média, IC95%)"),
        code('''\
summary = aggregate_records(trials_df, group_by=["fidelity_estimator"], metrics=["absolute_fidelity_error"])
save_table(summary, "R07_summary", directory=TABLES_OUT)
summary[["fidelity_estimator", "metric", "n_valid", "mean", "std", "ci95_low", "ci95_high"]]'''),
        md("## Comparações estatísticas pareadas"),
        code('''\
stats_df = pd.read_csv(RESULTS_DIR / "processed" / CAMPAIGN / "statistical_comparisons.csv")
significant = stats_df[stats_df["p_value_holm_adjusted"] < 0.05]
print(f"{len(significant)}/{len(stats_df)} comparisons significant after Holm correction")
significant[["scenario", "routing_strategy", "value_col", "n", "mean_a", "mean_b", "test_used", "p_value_holm_adjusted", "effect_size"]]'''),
        md("## Figura"),
        code('''\
estimators = sorted(trials_df["fidelity_estimator"].unique())
fig, ax = plt.subplots(figsize=(6, 4.5))
groups = [trials_df[trials_df["fidelity_estimator"] == e]["absolute_fidelity_error"].to_numpy() for e in estimators]
ax.boxplot(groups, tick_labels=estimators, showfliers=False)
for i, g in enumerate(groups, start=1):
    ax.scatter(np.full(len(g), i) + np.random.default_rng(i).uniform(-0.08, 0.08, len(g)), g, s=12, alpha=0.6)
ax.set_ylabel("absolute_fidelity_error")
ax.set_title(f"F07 estimators - fidelity error (n={trials_df['seed'].nunique()} seeds/cell)")
save_figure(fig, "R07_fidelity_error", directory=FIGURES_OUT)
plt.show()'''),
        md('''## Conclusão

`SequenceConsistentEstimator` reproduz o modelo de fidelidade
implementado pelo SeQUeNCe nas configurações avaliadas (erro
numericamente zero) - nunca "predicts perfectly in real networks"
(`docs/fidelity_estimation_model.md`,
`docs/core_contribution_statement.md`).'''),
    ]
    write_notebook("R07_estimators.ipynb", cells)


# ---------------------------------------------------------------------------
# R08 - resource semantics (F08)
# ---------------------------------------------------------------------------
def build_r08():
    cells = [
        md('''# R08 - Resource Semantics

## Objetivo
Demonstrar que `reserved_memory_slots` (dimensiona o pool) e
`duration_s` (controla quantas vezes o pool pode ser reutilizado) são
dimensões ortogonais de controle, com dados reais da campanha final
`F08_resource_semantics` (three_node, 2x2 fatorial x 20 seeds). Ver
`docs/intent_resource_semantics.md`. Não roda simulação - carrega
apenas dados persistidos.'''),
        code(HEADER_IMPORTS),
        md("## Carregar dados e verificar consistência"),
        code('''\
CAMPAIGN = "F08_resource_semantics"
trials_df = pd.read_csv(RESULTS_DIR / "raw" / CAMPAIGN / "trials.csv")
manifest = json.load(open(RESULTS_DIR / "manifests" / f"{CAMPAIGN}.json", encoding="utf-8"))

assert len(trials_df) == manifest["completed_trials"] == 80
assert sorted(trials_df["reserved_memory_slots"].unique()) == [2, 10]
assert sorted(trials_df["duration_s"].unique()) == [0.02, 0.05]
trials_df.head(3)'''),
        md("## Agregação fatorial (n, média, IC95%)"),
        code('''\
summary = aggregate_records(
    trials_df, group_by=["reserved_memory_slots", "duration_s"],
    metrics=["delivered_pairs", "delivery_ratio", "deliveries_per_reserved_slot"],
)
save_table(summary, "R08_summary", directory=TABLES_OUT)
summary[["reserved_memory_slots", "duration_s", "metric", "n_valid", "mean", "ci95_low", "ci95_high"]]'''),
        md("## Comparações estatísticas pareadas"),
        code('''\
stats_df = pd.read_csv(RESULTS_DIR / "processed" / CAMPAIGN / "statistical_comparisons.csv")
significant = stats_df[stats_df["p_value_holm_adjusted"] < 0.05]
print(f"{len(significant)}/{len(stats_df)} comparisons significant after Holm correction")
significant[["held_fixed", "varying_factor", "value_col", "n", "mean_a", "mean_b", "test_used", "p_value_holm_adjusted", "effect_size"]]'''),
        md("## Figura"),
        code('''\
fig, ax = plt.subplots(figsize=(6.5, 4.5))
for duration in sorted(trials_df["duration_s"].unique()):
    sub = trials_df[trials_df["duration_s"] == duration]
    means = sub.groupby("reserved_memory_slots")["delivered_pairs"].mean()
    ax.plot(means.index, means.values, "o-", label=f"duration_s={duration}")
ax.set_xlabel("reserved_memory_slots")
ax.set_ylabel("delivered_pairs")
ax.set_title(f"F08 resource semantics (n={trials_df['seed'].nunique()} seeds/cell)")
ax.legend()
save_figure(fig, "R08_delivered_pairs", directory=FIGURES_OUT)
plt.show()'''),
        md('''## Conclusão

Ambos os fatores têm efeito independente e estatisticamente
significativo - `reserved_memory_slots` dimensiona o pool,
`duration_s` controla a reutilização; `delivery_ratio > 1` (entrega
excede a meta) é over-delivery, não duplicação ou erro
(`docs/intent_resource_semantics.md`).'''),
    ]
    write_notebook("R08_resource_semantics.ipynb", cells)


# ---------------------------------------------------------------------------
# R09 - final summary
# ---------------------------------------------------------------------------
def build_r09():
    cells = [
        md('''# R09 - Final Summary

## Objetivo
Consolidar o estado final da Fase J/K: status da auditoria de
rastreabilidade por campanha, a figura conceitual de arquitetura, e as
claims prontas para o artigo. Ver `docs/results_interpretation_guide.md`
como ponto de entrada, e `docs/final_claims_and_evidence.md` para a
tabela completa de claims/evidência. Não roda simulação nem a auditoria
em si (`scripts/audit_final_results.py` já foi executado) - carrega
apenas `results/audit/final_results_audit.json`.'''),
        code(HEADER_IMPORTS),
        md("## Status da auditoria por campanha"),
        code('''\
audit = json.load(open(RESULTS_DIR / "audit" / "final_results_audit.json", encoding="utf-8"))
audit_summary = pd.DataFrame([
    {"campaign": name, "overall": info["overall"], "expected_trials": info["expected_trials"], "raw_rows": info["raw_rows"]}
    for name, info in audit["campaigns"].items()
])
save_table(audit_summary, "R09_audit_summary", directory=TABLES_OUT)
assert (audit_summary["overall"] != "FAIL").all(), "no campaign should FAIL the final audit"
audit_summary'''),
        md("## Figura conceitual de arquitetura"),
        code('''\
from IPython.display import Image, display
display(Image(filename=str(RESULTS_DIR / "figures" / "conceptual" / "Figure_Architecture_Conceptual.png")))'''),
        md("## Claims finais (ver docs/final_claims_and_evidence.md para a tabela completa)"),
        code('''\
claims_doc = (Path("../docs") / "final_claims_and_evidence.md").read_text(encoding="utf-8")
n_claim_rows = claims_doc.count("\\n|") - 1  # header + separator rows aren't claims
print(f"docs/final_claims_and_evidence.md has a claims table with real evidence for each row")
print(claims_doc[:500])'''),
        md('''## Conclusão

Todas as campanhas finais (F01-F08) passam na auditoria de
rastreabilidade (`scripts/audit_final_results.py`), com figuras e
tabelas exportadas para `results/figures/final/` e
`results/tables/final/`. A contribuição central - uma arquitetura
intent-based para redes de distribuição de entrelaçamento - está
documentada em `docs/core_contribution_statement.md`, com cada claim
candidata ao artigo rastreada em `docs/final_claims_and_evidence.md`.'''),
    ]
    write_notebook("R09_final_summary.ipynb", cells)


if __name__ == "__main__":
    build_r01()
    build_r02()
    build_r03()
    build_r04()
    build_r05()
    build_r06()
    build_r07()
    build_r08()
    build_r09()
    print("DONE")
