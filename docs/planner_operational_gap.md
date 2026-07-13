# Planner versus operação (Fase J5)

## Objetivo

Medir sistematicamente a diferença entre o que o `IntentPlanner` prevê
(viável/inviável, antes de qualquer simulação) e o que realmente
acontece operacionalmente (SATISFIED/VIOLATED/REJECTED/FAILED, depois de
simular) - implementado em
`src/ibqn/experiments/planner_operation_matrix.py`, um módulo de análise
puro sobre `TrialRecord`s já persistidos (no mesmo espírito de
`validation.py`/`aggregation.py`).

## Por que nenhum campo novo foi necessário no `TrialRecord`

`runner.execute_trial` só produz `final_status="REJECTED"` a partir da
checagem de viabilidade do `IntentPlanner`, **antes** de qualquer
simulação. `final_status="FAILED"` só ocorre quando o próprio SeQUeNCe
rejeita a reserva (`IntentRequestApp.get_reservation_result(result=False)`)
- ou seja, quando o planner achou o plano viável, mas o mecanismo de
admissão do SeQUeNCe (RSVP) discordou. Essas são semanticamente
diferentes: `REJECTED` = planner disse não; `FAILED` = planner disse sim,
SeQUeNCe disse não. Como essa distinção já está codificada em
`final_status`, `planner_feasible`/`reservation_accepted` são
inteiramente derivados dele - nenhum campo novo foi adicionado.

## As cinco categorias (`classify_trials`)

| `final_status` | Categoria | Interpretação |
|---|---|---|
| `SATISFIED` | `FEASIBLE_AND_SATISFIED` | previsão correta |
| `VIOLATED` | `FEASIBLE_BUT_VIOLATED` | falsa viabilidade operacional |
| `REJECTED` | `INFEASIBLE_AND_REJECTED` | rejeição prevista (até ser testada contra oracle) |
| `REJECTED` + oracle satisfatório | `INFEASIBLE_BUT_POTENTIALLY_SATISFIABLE` | falso negativo do planner |
| `FAILED` | `EXECUTION_FAILED` | reserva rejeitada pelo próprio SeQUeNCe, apesar do planner achar viável |

A quinta categoria (`INFEASIBLE_BUT_POTENTIALLY_SATISFIABLE`) exige
comparação com um oracle (`experiments.baselines.
run_offline_oracle_baseline`, Fase J3) - `upgrade_rejected_with_oracle`
recebe um mapeamento `trial_id -> oracle_satisfied` (nunca inferido,
sempre fornecido explicitamente por quem rodou o oracle) e promove
apenas os `REJECTED` cujo oracle correspondente teve sucesso.

## Achado importante: ambiguidade entre "não testado" e "testado, confirmado rejeição"

Depois de `upgrade_rejected_with_oracle`, uma linha que continua
`INFEASIBLE_AND_REJECTED` pode significar duas coisas completamente
diferentes: (a) nenhum oracle foi rodado para ela, ou (b) um oracle FOI
rodado e confirmou que a rejeição era mesmo correta. As categorias
sozinhas não distinguem os dois casos - por isso `compute_gap_metrics`
exige `oracle_tested_trial_ids` explicitamente para calcular
`false_rejection_rate`; sem esse argumento, a métrica é `None`, nunca
`0.0` por omissão (confirmado em
`test_false_rejection_rate_distinguishes_untested_from_all_true_rejections`).

## Métricas (`compute_gap_metrics`)

- `operational_success_rate = SATISFIED / total de trials` - de todo
  pedido submetido ao sistema (incluindo os que o próprio planner
  rejeitou), quantos foram realmente satisfeitos fim a fim.
- `false_feasibility_rate = FEASIBLE_BUT_VIOLATED / (SATISFIED + VIOLATED + FAILED)`
  - entre os planos que o planner considerou viáveis, quantos na
  verdade não entregaram o suficiente.
- `false_rejection_rate = INFEASIBLE_BUT_POTENTIALLY_SATISFIABLE / |oracle_tested_trial_ids|`
  - apenas sobre o subconjunto de rejeições genuinamente testado contra
  oracle.
- `fidelity_prediction_error` - erro absoluto médio de fidelidade
  (reusa `TrialRecord.absolute_fidelity_error`, Fase J1).
- `delivery_deficit` - déficit médio de entrega
  (`max(0, min_delivered_pairs - delivered_pairs)`) entre trials com meta
  declarada e evidência de entrega.
- `throughput_deficit` - déficit médio na taxa implícita
  (`max(0, min_delivered_pairs/duration_s - throughput_active_window)`).

Toda métrica retorna `None` (nunca `0`) quando o denominador
correspondente é zero - nenhuma taxa é fabricada a partir de dados
inexistentes.

## Validação

`tests/experiments/test_planner_operation_matrix.py` cobre: classificação
de cada status; rejeição de status desconhecido; upgrade seletivo via
oracle (só toca `REJECTED` mapeados, nunca infere); tabela de contingência
com contagens corretas; métricas nunca fabricadas com denominador vazio;
a ambiguidade "não testado" vs. "testado, confirmado" descrita acima;
déficits de entrega/throughput corretos quando a meta é atingida
(zero) e quando não é (positivo); e um teste sobre os dados reais e já
persistidos da campanha `C03_assurance_outcomes` (que produz
naturalmente SATISFIED/VIOLATED/REJECTED).

## Limitações desta etapa

- Nenhuma campanha em escala roda oracle sistematicamente sobre seus
  `REJECTED` ainda - isso é parte da campanha `F04` (Fase J10, "Planner
  versus operação: gerar matriz de viabilidade e resultado").
- `EXECUTION_FAILED` nunca foi observado em nenhuma campanha até agora
  (C01-C04) - o mecanismo de admissão do RSVP e a checagem de
  viabilidade do planner parecem estar bem alinhados nas condições
  testadas; isso é uma observação empírica desta fase, não uma garantia
  estrutural.
