# Metodologia experimental

Este documento descreve como um cenário declarativo (seção 15 do prompt
original) é executado de forma reprodutível nesta fase do projeto
(`src/ibqn/experiments/`, Etapa F). A infraestrutura de campanhas completas
do artigo (múltiplos cenários, `results/raw|processed|figures|tables`,
manifestos JSON — seções 19–22 do prompt original) ainda não foi construída;
este documento cobre apenas o que existe hoje: executar UM cenário, com UMA
ou VÁRIAS seeds, e ler os resultados de volta do próprio SeQUeNCe.

## Um cenário = topologia + parâmetros de simulação + intents

Um arquivo de cenário (`scenarios/linear_three_nodes.yaml` é o exemplo real
usado nos testes) declara:

```yaml
scenario:
  name: linear_three_nodes
  simulation:
    duration_s: 0.1   # segundos, tempo total de parada da simulação
    seed: 42
  nodes: [...]         # ibqn.network.topology.NodeSpec
  quantum_links: [...] # ibqn.network.topology.QuantumLinkSpec
  classical_delay_s: 0.0001
  intents:
    - file: intents/intent_001.yaml   # caminho relativo ao arquivo do cenário
```

`ibqn.experiments.scenarios.Scenario.load(caminho)` carrega o YAML/JSON,
resolve cada `intents[].file` **relativo ao diretório do próprio arquivo de
cenário** (não ao diretório de trabalho atual), e devolve os
`EntanglementIntent` já validados.

## Executando um cenário

`ibqn.experiments.runner.run_scenario(scenario, seed=None, routing_strategy=None, ...)`:

1. reseta `sequence.utils.metrics` (é um singleton global por processo —
   ver `docs/sequence_code_analysis.md`, seção 4.1);
2. constrói `NetworkCapabilities` + `SequenceAdapter` a partir da topologia
   do cenário, usando `seed` (ou `scenario.spec.simulation.seed` se `seed`
   não for passado);
3. planeja e implanta (`IntentPlanner.plan` + `SequenceExecutor.deploy`)
   **todos** os intents do cenário sobre o mesmo `Timeline`, antes de rodar
   a simulação uma única vez;
4. para cada intent, lê o status final do `IntentRepository` e as métricas
   nativas do SeQUeNCe (`metrics.collect_trial_metrics`) do nó de origem do
   intent.

O resultado (`ScenarioResult`) contém, por intent: status final do ciclo de
vida, `ExecutionPlan` usado, e o dicionário de métricas coletado. Nenhum
valor é calculado independentemente da simulação — tudo vem de
`IntentRepository`/`sequence.utils.metrics`.

## Seeds e repetição

`ibqn.experiments.seeds.seeds_for_trials(base_seed, n_trials)` gera `n_trials`
seeds espaçadas por `STRIDE=1000`. O espaçamento existe porque
`NetworkTopologySpec.to_router_net_topo_config` deriva seeds por nó/enlace
como `seed_base + índice` — seeds de trials consecutivos muito próximas
poderiam sobrepor os intervalos derivados e correlacionar trials que deveriam
ser independentes.

```python
from ibqn.experiments.seeds import seeds_for_trials
from ibqn.experiments.runner import run_scenario

trials = [run_scenario(scenario, seed=s) for s in seeds_for_trials(base_seed=42, n_trials=10)]
```

Cada chamada a `run_scenario` constrói um `SequenceAdapter`/`Timeline` novo e
reseta as métricas — trials são isolados entre si por construção, não por
disciplina do chamador.

## O que ainda não existe

- Agregação estatística entre trials (média, desvio-padrão, IC) — o próprio
  `sequence.utils.metrics.aggregate_trial_metrics` já faz isso
  (ver `docs/sequence_code_analysis.md`, seção 4.1) e será o ponto de
  partida natural, mas ainda não há um módulo `ibqn` que chame essa função
  sobre uma lista de `ScenarioResult`.
- Escrita de resultados brutos/processados em disco (`results/raw`,
  `results/processed`, manifestos JSON com commit/seeds/parâmetros —
  seção 22 do prompt original).
- Varredura de parâmetros (`experiments/sweeps.py`, citado na árvore de
  diretórios da seção 6, mas fora do escopo desta etapa).
