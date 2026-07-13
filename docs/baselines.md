# Baselines (Fase J3)

## Objetivo

Quantificar o benefício real do IBQN comparando-o contra três
alternativas deliberadamente mais simples, todas compartilhando a mesma
topologia, seed, parâmetros físicos, janela de reserva e requisitos
declarados do intent - qualquer diferença de resultado é atribuível à
**arquitetura**, não a uma variável de confusão. Implementado em
`src/ibqn/experiments/baselines.py`.

## As três baselines

### Baseline A - Native SeQUeNCe Request

`run_native_sequence_baseline(topology_spec, intent, *, seed)`: usa
`sequence.app.request_app.RequestApp` (stock, não modificado) diretamente
contra `NetworkManager`/a tabela de roteamento estática auto-gerada da
topologia - sem `EntanglementIntent`-based planning, sem assurance, sem
reconciliation, sem `IntentRequestApp`.

Como `RequestApp.get_memory` reseta a fidelidade da memória para 0 ao
processar uma entrega (`MemoryInfo.to_raw()`), não há telemetria nativa
de fidelidade por par. Para tornar a comparação de fidelidade possível
sem inventar um número, `_FidelityProbeRequestApp` (uma subclasse
mínima) grava `info.fidelity` **antes** de chamar
`super().get_memory(info)` - uma sonda passiva de medição, não uma
mudança de comportamento: `memory_counter` continua exatamente igual ao
`RequestApp` de fábrica, incluindo sua subcontagem conhecida de pares em
estado `"PURIFIED"` (`docs/limitations.md`) - essa é uma característica
genuína da baseline nativa, não um bug a esconder.

**Achado empírico (Fase J3)**: `RouterNetTopo._generate_forwarding_table`
pondera cada aresta pela **distância física somada** dos dois
meios-enlaces do BSM (`router_net_topo.py:192-208`,
`graph.add_weighted_edges_from(costs)`), não por número de saltos -
`dijkstra_path` roda ponderado por distância. Isso significa que a
alegação anterior deste projeto (`planning.routing.
ShortestHopCountRouting`'s docstring original) de que a tabela de
roteamento nativa do SeQUeNCe usa "Dijkstra não ponderado" estava
**incorreta**. Confirmado na topologia diamante
(`tests/experiments/test_baselines.py`): a rota nativa escolhe o desvio
de 3 saltos `good1`/`good2` (1500 m total) em vez do link de 2 saltos
`bad` (2000 m total), porque a distância total é menor - algo que
`ShortestHopCountRouting` (que ignora distância) nunca escolheria. A
correção foi propagada ao docstring de `ShortestHopCountRouting`.

### Baseline B - Static Provisioning

`run_static_provisioning_baseline(topology_spec, intent, *, seed,
routing_strategy=None)`: uma rota é escolhida **uma única vez**, sem
NENHUMA checagem de viabilidade (pula `IntentPlanner.plan()`
inteiramente - nenhuma estimativa de memória/fidelidade, nenhuma
possibilidade de rejeição antes de implantar) - apenas o primeiro
candidato que `routing_strategy` propõe - depois implantada e executada
exatamente uma vez. Nenhuma reação, nenhuma reconciliation. O sucesso é
avaliado **somente depois** da execução, puramente para comparação
científica - essa avaliação não influencia em nada o que a baseline "faz".

Confirmado (`test_static_provisioning_baseline_never_rejects_upfront`):
com uma meta de fidelidade inatingível (0.999999), esta baseline ainda
**tenta** a reserva (RSVP só checa memória/tempo, nunca fidelidade) e só
falha depois, em `satisfied=False` - nunca em `REJECTED` antes de rodar,
ao contrário do `IntentPlanner`.

### Baseline C - Offline Oracle

`run_offline_oracle_baseline(topology_spec, intent, *, seed,
max_candidates=10)`: enumera todo caminho simples entre os endpoints do
intent, executa **cada um** (mesma seed, mesmo intent, `Timeline`
isolada por candidato), e reporta o melhor resultado depois de conhecer
todos os resultados - um limite superior **apenas em retrospecto**, não
uma estratégia implementável online (um planejador real não pode ver o
futuro). Levanta `ValueError` em vez de amostrar um subconjunto quando a
topologia tem mais que `max_candidates` caminhos simples - o oracle é
deliberadamente restrito a topologias pequenas o bastante para
enumeração exaustiva.

## Métricas de comparação

`BaselineResult` (mesmo espírito de `experiments.records.TrialRecord`):
`route`, `accepted`, `satisfied`, `delivered_pairs`, `average_fidelity`,
`minimum_fidelity`, `throughput_active_window`, `planning_wall_time_s`,
`simulation_wall_time_s`, `total_wall_time_s`, `episodes`,
`candidates_evaluated`.

## Comparação justa

Todas as três funções aceitam exatamente `(topology_spec, intent, seed)`
- nenhuma varia a topologia, os parâmetros físicos, a janela de reserva
ou os requisitos declarados por conta própria
(`test_all_three_baselines_share_the_same_seed_topology_and_intent`).

## O que cada baseline isola

| Comparação | O que ela mede |
|---|---|
| IBQN vs. Native SeQUeNCe (A) | benefício de ter QUALQUER planejamento/assurance, vs. delegar tudo ao mecanismo de reserva padrão |
| IBQN vs. Static Provisioning (B) | benefício específico de checar viabilidade antes de implantar (rejeitar cedo em vez de falhar tarde) |
| IBQN vs. Offline Oracle (C) | o quão perto do limite superior teórico (impossível de implementar online) o IBQN chega |
| IBQN com reconciliation vs. sem (já existente, `reconciliation_enabled`) | benefício específico de reconciliation |

A campanha final (`F01`, Fase J10) usará estas quatro comparações para
decompor separadamente: benefício da escolha de rota, benefício do
assurance, benefício da reconciliation, custo da abstração intent-based -
exatamente como pedido no critério de aceite original.

## Limitações desta etapa

- Nenhuma campanha em escala usa estas baselines ainda - `baselines.py`
  fornece as funções e uma suíte de testes unitários confirmando
  comportamento correto em pequena escala (topologia diamante); a
  campanha `F01` (Fase J10) as executa em escala com múltiplas seeds.
- O oracle e a baseline estática reusam `SequenceExecutor`/
  `IntentRepository`/`assurance.evaluator` do IBQN para telemetria e
  avaliação (não haveria como obter evidência de entrega por par sem
  isso) - apenas a DECISÃO de rota/estratégia é isolada da camada IBQN,
  não a coleta de evidência.
