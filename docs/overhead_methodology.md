# Metodologia de medição de overhead (Fase J7)

## Objetivo

Medir quanto a camada IBQN custa, **independentemente** do custo da
própria simulação SeQUeNCe - implementado em
`src/ibqn/experiments/overhead.py`.

## Por que um caminho de execução separado

Adicionar temporizadores por etapa a `runner.execute_trial` exigiria mais
uma mudança de schema em `TrialRecord` (como a Fase J1/J2 exigiu) e mais
uma regeneração das campanhas C01-C04, para uma medição que só é
necessária na granularidade de uma campanha dedicada de overhead (`F06`,
Fase J10) - não em todo trial rotineiro. Por isso,
`run_instrumented_trial` é um ponto de entrada **paralelo**, que chama
exatamente a mesma sequência de operações que `runner.execute_trial` usa
(mesmo planner, mesmo `SequenceExecutor`, mesma avaliação de assurance),
só que envolta em `time.perf_counter()` a cada etapa.

## As doze medidas (`TrialTiming`)

**Formulação exata a usar em qualquer texto sobre esta instrumentação**:
"a instrumentação define doze campos de tempo; dez são observáveis no
caminho instrumentado atual" ("the instrumentation defines twelve
timing fields; ten are observable in the current instrumented path")
- nunca "12 medidas completas", já que `route_application_wall_time_s`
e `persistence_wall_time_s` são sempre `None` nesta versão (ver a
tabela abaixo e "Limitações desta etapa").

| Campo | O que mede | Como |
|---|---|---|
| `intent_parsing_wall_time_s` | leitura do arquivo + parsing YAML/JSON + normalização de forma | `intent.parser.load_intent_file_with_timing` - `0.0` quando o intent já é passado como objeto Python (não houve parsing nesta chamada, uma medição real, não uma omissão) |
| `intent_validation_wall_time_s` | validação de campos do Pydantic (`EntanglementIntent.model_validate`) | mesmo helper, medido separadamente do parsing |
| `capability_extraction_wall_time_s` | construção de `NetworkCapabilities` a partir da topologia | |
| `planning_wall_time_s` | `IntentPlanner.plan(intent)` | |
| `route_application_wall_time_s` | aplicação da rota (`execution.compiler.apply_route`) | **sempre `None`** nesta versão - `_deploy_plan` aplica a rota como parte do próprio `executor.deploy()`; separar exigiria adicionar temporizadores dentro de `execution/sequence_executor.py`, fora do escopo desta fase |
| `deployment_wall_time_s` | `executor.deploy(intent, plan)` inteiro (inclui aplicação de rota) | |
| `assurance_wall_time_s` | `collect_intent_evidence` + `evaluate_intent` | |
| `reconciliation_decision_wall_time_s` | `decide_reconciliation_action` (Fase J6) | só medido quando `reconciliation_enabled=True` **e** o intent terminou `VIOLATED`; `None` caso contrário |
| `persistence_wall_time_s` | escrita do `TrialRecord` | **sempre `None`** - `run_instrumented_trial` nunca persiste em disco (isso é trabalho de `runner.execute_trial`) |
| `simulation_wall_time_s` | `executor.run()` - o `Timeline.run()` real do SeQUeNCe | |
| `total_orchestration_wall_time_s` (propriedade) | soma de tudo acima, exceto `simulation_wall_time_s` | o custo da camada IBQN em si |
| `total_trial_wall_time_s` (propriedade) | `total_orchestration_wall_time_s + simulation_wall_time_s` | |

## Não misturar tempos

- **Tempo simulado na `Timeline`** (picossegundos internos do SeQUeNCe) é
  uma medida completamente diferente de qualquer campo aqui - nenhum
  campo desta fase mede tempo simulado, todos medem `time.perf_counter()`
  real (wall-clock).
- **Wall time de controle** (`total_orchestration_wall_time_s`) vs.
  **wall time de simulação** (`simulation_wall_time_s`) vs. **wall time
  total** (`total_trial_wall_time_s`) - as três métricas nunca são
  somadas incorretamente: a propriedade `total_trial_wall_time_s` é a
  única soma "oficial", e as duas partes que a compõem nunca aparecem
  fundidas em um único campo.

## Métricas derivadas

```python
orchestration_overhead_ratio = total_orchestration_wall_time_s / total_trial_wall_time_s
planning_overhead_ratio = planning_wall_time_s / total_trial_wall_time_s
```

Ambas como propriedades de `TrialTiming`, `0.0` (nunca erro de divisão)
quando `total_trial_wall_time_s` é zero (só ocorreria num objeto
`TrialTiming` construído artificialmente, nunca por
`run_instrumented_trial`).

## Comparação com baselines (Fase J3)

`experiments.baselines.BaselineResult` já expõe `planning_wall_time_s`/
`simulation_wall_time_s`/`total_wall_time_s` - confirmado
(`test_ibqn_orchestration_overhead_is_measurable_against_the_native_baseline`):
a baseline nativa (`run_native_sequence_baseline`) tem
`planning_wall_time_s == 0.0` por construção (não existe etapa de
planejamento nessa baseline), enquanto a instrumentação IBQN sempre
reporta um `planning_wall_time_s` real e mensurável - a mesma
decomposição de overhead se aplica a ambos os caminhos, permitindo
comparar diretamente "quanto custa ter QUALQUER camada de planejamento"
(Fase J10, campanha `F06`).

## Validação

`tests/experiments/test_overhead.py` cobre: toda medição é não-negativa;
a soma total é consistente; parsing/validação são genuinamente zero
quando o intent já é um objeto Python, e genuinamente positivos quando
vêm de um arquivo real; um plano inviável interrompe a cadeia com
`deployment`/`assurance`/`simulation` em zero mas `planning` positivo
(o planejamento em si aconteceu); o tempo de decisão de reconciliation só
é registrado quando há violação e reconciliation está habilitada;
comparação direta com a baseline nativa.

## Limitações desta etapa

- `route_application_wall_time_s`/`persistence_wall_time_s` são sempre
  `None` nesta versão - ver a tabela acima para o motivo específico de
  cada um. Nunca descrever a instrumentação como "12 medidas completas".
- `F06_overhead` (Fase J10, 20 seeds x 3 condições,
  `scripts/run_f06_overhead.py`) usa `run_instrumented_trial` em escala -
  resultados e figuras em `docs/final_experimental_design.md` e
  `results/figures/final/Figure_Overhead_*`. O overhead médio de
  orquestração ficou abaixo de 0.31% do tempo total de trial nas
  condições avaliadas (nunca descrito como "desprezível" sem esse
  escopo) - achado adicional não previsto: `native_sequence` levou ~2.5x
  mais tempo de SIMULAÇÃO (não de orquestração) que as outras condições,
  porque a rota que escolhe processa muito mais eventos de
  entrelaçamento por unidade de tempo simulado.
- Medições de wall-clock são inerentemente ruidosas (contenção de CPU,
  garbage collection, etc.) - os testes desta fase verificam
  propriedades estruturais (não-negatividade, consistência de somas,
  zero vs. positivo), nunca magnitudes absolutas específicas. Ao
  reportar overhead como resultado (não apenas como teste), sempre
  mostrar a distribuição completa (`Figure_Overhead_Ratio.png`), nunca
  só a média.
