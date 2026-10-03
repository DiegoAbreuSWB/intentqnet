# Proveniência dos resultados (Fase K1)

Rastreia cada artefato final até sua campanha, arquivo bruto, arquivo
processado, script/notebook gerador e uso final - conforme exigido pela
auditoria de rastreabilidade da Fase K1. Ver também
`results/audit/final_results_audit.md` (gerado por
`scripts/audit_final_results.py`) para a verificação programática destes
mesmos fatos.

**Hashes de commit.** As mensagens de commit do histórico foram reescritas
em 2026-10-03 (só as mensagens; árvores, autores e datas não mudaram). Os
hashes citados aqui, nos manifestos, nas colunas `project_git_commit` e nas
saídas dos notebooks são os anteriores; `docs/commit_hash_map.csv` dá o
commit atual de cada um.

## Piloto (Fase H3) versus final (Fase J10) - separação definitiva

Este projeto tem DOIS conjuntos de campanhas, que nunca devem ser
misturados em uma figura, tabela ou conclusão final:

- **`C01`-`C04`** (Fase H3): campanhas piloto de validação de pipeline,
  2-3 seeds. Usadas para provar que o pipeline funciona
  end-to-end, não para sustentar conclusões científicas.
- **`F01`-`F08`** (Fase J10): campanhas finais, 20 seeds cada
  (`docs/seed_justification.md`), com baselines, estimadores e
  reconciliação em escala. **Única base de evidência para o artigo.**

`notebooks/article/A00`-`A07` e `results/figures/article/*` (piloto,
`C01`-`C04`) agora têm um `README.md` próprio marcando-os explicitamente
como desenvolvimento/Fase H3.5 - ver
[`notebooks/article/README.md`](../notebooks/article/README.md) e
[`results/figures/article/README.md`](../results/figures/article/README.md).
As figuras/notebooks finais (Fase K2/K4) vivem em
`results/figures/final/` e `notebooks/article/final/`.

## Tabela de proveniência

| Artifact | Campaign | Raw source | Processed source | Notebook/script | Final use |
|---|---|---|---|---|---|
| F01 results | F01_architecture_baselines | `results/raw/F01_architecture_baselines/trials.csv` (120 rows) | `results/processed/F01_architecture_baselines/statistical_comparisons.csv` | `scripts/run_f01_architecture_baselines.py` (data) + `scripts/build_adhoc_campaign_manifests.py` (manifest) | Baseline comparison (route/assurance/reconciliation benefit) |
| F02 results | F02_routing | `results/raw/F02_routing/trials.csv` (120 rows: 60 diamond + 60 small_mesh) | `results/processed/F02_routing/statistical_comparisons.csv` | `scripts/run_f02_routing.py` (two calls, one per topology - see manifest `blocks`) | Routing strategy comparison |
| F03 results | F03_purification | `results/raw/F03_purification/trials.csv` (480 rows: 320 three_node_1_repeater [8 thresholds, densified Fase K2] + 160 linear_chain_2_repeaters [4 thresholds]) | `results/processed/F03_purification/statistical_comparisons.csv` | `scripts/run_f03_purification.py` (original 4 thresholds) + `scripts/run_f03_purification_density.py` (Fase K2, 4 denser thresholds, three_node_1_repeater only) | Purification policy comparison |
| F04 matrix/metrics | F04_planner_vs_operation (derived, no seeds of its own) | Combines F02 (120) + F03 (480) = **600** rows | `results/processed/F04_planner_vs_operation/{matrix.csv,gap_metrics.json,combined_trials_with_categories.csv}` | `scripts/build_f04_planner_operation_matrix.py` (F02+F03 trial_id union, oracle re-test of F03's 240 reconstructible REJECTED rows in `three_node_1_repeater`) | Planner-vs-operation gap matrix; root cause in `docs/false_rejection_root_cause.md` |
| F05 results | F05_reconciliation | `results/raw/F05_reconciliation/trials.csv` (100 rows: 5 cases x 20 seeds; per-episode delivered_pairs/fidelity/route/slots/duration added Fase K2) | `results/processed/F05_reconciliation/trials_with_recovery_type.csv` (`scripts/classify_f05_recovery_types.py`) | `scripts/run_f05_reconciliation.py`, not `run_programmatic_campaign`/`CampaignRunner` | Reconciliation recovery rates, recovery-type classification |
| F06 results | F06_overhead | `results/raw/F06_overhead/trials.csv` (60 rows: 3 conditions x 20 seeds) | (none - consumed directly) | `scripts/run_f06_overhead.py` | Overhead decomposition |
| F07 results | F07_estimators | `results/raw/F07_estimators/trials.csv` (120 rows) | `results/processed/F07_estimators/statistical_comparisons.csv` | `scripts/run_f07_estimators.py` | Estimator comparison |
| F08 results | F08_resource_semantics | `results/raw/F08_resource_semantics/trials.csv` (80 rows) | `results/processed/F08_resource_semantics/statistical_comparisons.csv` | `scripts/run_f08_resource_semantics.py` | Resource semantics factorial |
| Final figures | F01/F02/F03/F04/F05/F06/F07/F08 | (see each row above) | `results/figures/final/*.{pdf,png}` + `sources.json` | `scripts/generate_final_figures.py` | Article figures (Fase K2) |
| P00 pilot | P00_variability_study | `results/raw/P00_variability_study/pilot_trials.csv` (210 rows) | `results/processed/P00_variability_study/variability_report.json` | `experiments.variability_study` | Seed-count justification only (`docs/seed_justification.md`) - not cited as a result in its own right |
| `A00`-`A07` notebooks/figures | `C01`-`C04` | `results/raw/C0[1-4]_*/trials.csv` | `results/processed/C0[1-4]_*/` | `notebooks/article/A0*.ipynb` | **pilot_only** - regression check on the pipeline, never cited in the article |

All nine campaign-generating scripts above (`run_f0*.py`) and every
derived-analysis script (`build_f04_*`, `classify_f05_*`,
`generate_final_figures.py`, `audit_final_results.py`) live in
`scripts/` with portable paths (`Path(__file__).resolve().parents[1]`)
- re-running any of them against the current `trials.csv` files
completes in seconds with 0 new trials (every trial_id already known),
confirming they reproduce exactly what is committed.

## Campanhas executadas programaticamente sem `campaign_file` YAML

Nenhuma das oito campanhas finais usa um arquivo YAML de campanha
(`CampaignSpec`) - todas rodam com `campaign_file: null` no manifesto:

- **F02, F03, F07, F08**: via `experiments.programmatic_campaign.
  run_programmatic_campaign` (topologias/intents vêm direto de
  `demos.topologies`/`experiments.topology_catalog`, não de YAML).
- **F01, F05, F06**: via script ad-hoc dedicado (não reusa
  `run_programmatic_campaign`/`CampaignRunner` - ver
  `execution_path: "ad_hoc_script"` no manifesto de cada um). F01 mistura
  `execute_trial` (2 das 6 condições) com chamadas diretas às funções de
  baseline (`baselines.py`) e um helper local para a condição
  `ibqn_without_assurance`.

## Execuções em múltiplos blocos (F02, F03)

F02 e F03 rodam **duas topologias cada**, uma por chamada de
`run_programmatic_campaign` sob o mesmo `campaign_name`:

- F02: `diamond_heterogeneous` (60 trials) + `small_mesh` (60 trials) = 120.
- F03: `three_node_1_repeater` (160 trials, original 4 thresholds) +
  `linear_chain_2_repeaters` (160 trials) = 320 originally; Fase K2
  extended `three_node_1_repeater` with 160 more trials (4 denser
  thresholds, `scripts/run_f03_purification_density.py`) via a THIRD
  call to `run_programmatic_campaign` for the SAME scenario name - the
  manifest's grid-merge logic (not just cross-scenario accumulation)
  correctly unions `swept_factors["min_fidelity"]` into all 8 values
  instead of overwriting it with just the 4 new ones (see "Inconsistências"
  below). Current total: 480.

O manifesto consolida essas execuções em uma lista `blocks` (um por
topologia), com os totais de nível superior (`scenario_files`,
`expected_trials`, `completed_trials` etc.) recalculados como
união/soma sobre todos os blocos - ver "Inconsistências encontradas e
corrigidas" abaixo.

## Inconsistências encontradas e corrigidas (Fase K1)

1. **Bug de acumulação de manifesto em campanhas multi-bloco** (F02,
   F03): `run_programmatic_campaign` só escrevia o manifesto na
   PRIMEIRA chamada; a segunda chamada (segunda topologia) sobrescrevia
   `completed_trials`/`scenario_files` com apenas os valores da SUA
   PRÓPRIA execução, perdendo o registro da primeira. F02 relatava
   `scenario_files: ["diamond_heterogeneous"]` e `completed_trials: 60`
   quando o real eram 2 topologias e 120 trials (os dados brutos em
   `trials.csv` sempre estiveram corretos - o bug era só de
   bookkeeping). Corrigido reescrevendo a lógica de manifesto para
   `blocks` (um por `scenario_name`, acumulado via upsert) com testes de
   regressão dedicados
   (`tests/experiments/test_programmatic_campaign.py`). Manifestos
   regenerados via replay dos scripts originais contra o `trials.csv` já
   completo (checksum idêntico confirmado antes/depois - **zero
   simulações novas executadas**, apenas reparo de bookkeeping).
2. **Campo `strategies` ambíguo**: o manifesto original registrava
   `strategies.routing: ["shortest_hop_count"]` (o valor default do
   argumento) mesmo quando `routing_strategy` era o próprio fator
   varrido em `parameter_grid` (com os 3 valores reais) -
   contraditório. Substituído por `base_configuration` (parâmetros
   FIXOS neste bloco) e `swept_factors` (exatamente o que é varrido),
   nunca sobrepostos.
3. **Manifestos ausentes** (F01, F05, F06): essas três campanhas nunca
   escreveram manifesto algum (rodaram via script ad-hoc antes de
   `run_programmatic_campaign` existir). Criados retroativamente por
   `scripts/build_adhoc_campaign_manifests.py`, com `expected_trials`/
   `completed_trials` derivados diretamente da contagem real de linhas
   em `trials.csv` (nunca assumidos).
4. **Arquivos processados de F04 com nome malformado**: encontrado
   durante a auditoria K1 que `results/processed/F04_planner_vs_operation/`
   continha `matrixF04_planner_vs_operation.csv` (e análogos para
   `gap_metrics`/`combined_trials_with_categories`) em vez dos nomes
   corretos (`matrix.csv` etc.) - os arquivos com o nome CORRETO, já
   commitados em `5dfb42f`, haviam desaparecido da árvore de trabalho
   (confirmado via `git status`/`git diff`, que os mostravam como
   deletados). O conteúdo dos arquivos malformados foi verificado
   byte-a-byte equivalente ao que já estava documentado em
   `docs/final_experimental_design.md` (440 linhas, mesma matriz de
   categorias, mesmas `gap_metrics` - incluindo `false_rejection_rate:
   1.0`) antes de simplesmente renomeá-los de volta - nenhum dado foi
   recalculado ou alterado, apenas o nome do arquivo no disco foi
   corrigido para bater com o que o Git já rastreava.
5. **`skipped_trials` como contador de sessão, não campo persistido**:
   `run_programmatic_campaign` originalmente passava a contagem local
   de "pulados nesta chamada" direto para o manifesto: em uma campanha
   com múltiplos blocos, isso somava incorretamente contra
   `completed_trials` (que já é a verdade fundamental, incluindo
   trials completados em sessões anteriores), quebrando a identidade
   `expected == completed + failed + skipped`. Corrigido: `skipped_trials`
   agora é sempre derivado (`expected - completed - failed`, nunca
   negativo) em vez de repassado - a identidade vale por construção, não
   por convenção. Testado em
   `test_manifest_skipped_trials_is_derived_not_double_counted_on_replay`.
6. **Grid não acumulava ao estender o MESMO bloco** (F03, Fase K2):
   descoberto ao desenhar a campanha de densificação de purificação -
   uma segunda chamada a `run_programmatic_campaign` para o mesmo
   `(campaign_name, scenario_name)` mas com um `parameter_grid` diferente
   (limiares novos) sobrescrevia `swept_factors`/`expected_trials` do
   bloco com os valores da SEGUNDA chamada, perdendo o registro dos 4
   limiares originais - o mesmo bug de "acumulação" do item 1, mas
   dentro de um único bloco em vez de entre blocos. Corrigido fazendo
   `_upsert_campaign_manifest_block` unir (`set` union, não sobrescrever)
   `swept_factors`/`seeds`/`intent_files` do bloco existente com os da
   nova chamada, recalculando `expected_trials` a partir da grade unida.
   Testado em
   `test_manifest_merges_grid_when_extending_an_existing_scenario_block`.
7. **Commit único por campanha nem sempre é o esperado**: ao estender
   F03 na Fase K2, as 320 linhas originais mantiveram
   `project_git_commit=f4343c3...` (commit real de quando rodaram) e as
   160 novas linhas corretamente registraram o commit ATUAL (`346d13d...`
   ou posterior) - `execute_trial` já faz isso certo automaticamente. O
   `audit_final_results.py`'s `commit_consistency` check foi ajustado de
   FAIL para WARN quando há múltiplos commits (uma campanha
   legitimamente estendida em sessões diferentes vai ter mais de um,
   por design - não é um erro).

## Lacuna de rastreabilidade conhecida (não corrigida - não requer nova campanha)

`F01`, `F05` e `F06` **não têm coluna `project_git_commit`/
`sequence_git_commit` por linha** em `trials.csv` (script ad-hoc, nunca
passou por `execute_trial`'s persistence completo para todas as
condições - a própria F01 chama `execute_trial(..., project_commit=None,
sequence_commit=None)` explicitamente para as 2 condições que usam essa
função). O commit do projeto/SeQUeNCe para essas três campanhas está
documentado apenas no NÍVEL DO MANIFESTO (`project_git_commit:
f4343c3...`), **inferido** (não gravado) a partir do fato de que essas
três campanhas rodaram na mesma sessão de trabalho ininterrupta que
F02/F03/F07/F08 (que registraram esse commit), estritamente antes de
qualquer commit da Fase J10. Esta é uma lacuna real e divulgada, não uma
lacuna corrigida por re-execução: os dados em si (delivered_pairs,
fidelidade, tempos, taxas de recuperação) são válidos e já foram
cruzados contra o piloto P00 e contra achados de campanhas irmãs; a
única informação que falta é a granularidade por linha do commit, que
não afeta nenhuma conclusão científica deste projeto. Refazer essas
campanhas somente para popular uma coluna de commit violaria a
instrução desta etapa de não rodar novas campanhas salvo necessidade
comprovada - marcado aqui como limitação conhecida
(`docs/threats_to_validity.md`), não como pendência.

## Verificação programática

`scripts/audit_final_results.py` confirma automaticamente, para cada
campanha final: aritmética do manifesto (`expected == completed +
failed + skipped`), contagem de linhas de `trials.csv` batendo com o
manifesto, unicidade de `trial_id` (ou da chave lógica
`condition`/`case` + `seed` para F01/F05/F06), seeds completas por
bloco, todas as combinações do grid presentes exatamente uma vez, e
(quando a coluna existe) commit único por campanha. Resultado
persistido em `results/audit/final_results_audit.{json,md}` - ver esse
arquivo para o status PASS/WARN/FAIL mais atual.
