# Modelo de estimativa de fidelidade (Fase J1)

## O problema original

`planning.feasibility.estimate_swap_only_fidelity` (até a Fase H3)
estimava a fidelidade de cada salto como `min(raw_fidelity(a),
raw_fidelity(b))`, multiplicada pela `swapping_degradation` de cada nó
interior. Essa estimativa é **exata** em topologias com `raw_fidelity`
uniforme (todo nó igual) - mas **subestima sistematicamente** em
topologias heterogêneas (nós com `raw_fidelity` diferentes), confirmado
empiricamente na Fase H3 (`notebooks/article/
A05_planner_estimation_error.ipynb`, campanha `C01_routing_strategy`, erro
de até 0.083 / 12% relativo).

## O mecanismo real do SeQUeNCe

Dois fatos, confirmados lendo o código-fonte do SeQUeNCe (não inferidos):

1. **Geração elementar é por memória, não por par.**
   `sequence/entanglement_management/generation/barret_kok.py:228`:
   `self.memory.fidelity = self.memory.raw_fidelity`. Cada lado de um par
   recém-gerado recebe a `raw_fidelity` do **seu próprio nó** - nunca uma
   função do nó remoto. Duas memórias do mesmo par físico podem carregar
   valores diferentes se os dois nós tiverem `raw_fidelity` diferentes.

2. **Um swap combina as DUAS memórias do próprio nó que faz o swap.**
   `sequence/entanglement_management/swapping/swapping_circuit.py:135-146`
   (`EntanglementSwappingA_Circuit.updated_fidelity`): `f1 * f2 *
   degradation`, onde `f1`/`f2` são as fidelidades de `left_memo`/
   `right_memo` - ambas memórias pertencentes ao nó que executa o swap
   (`EntanglementSwappingA_Circuit` "should be instantiated on the middle
   node"). Se nenhuma delas foi tocada por um swap anterior, ambas valem
   `raw_fidelity` do nó do swap - o resultado depende **apenas** da
   fidelidade própria do nó que fez o swap, nunca da fidelidade dos nós
   geograficamente vizinhos no salto.

3. **A ordem dos swaps não é arbitrária.** `sequence/resource_management/
   resource_manager.py:229-238` (`generate_load_rules`) calcula, para cada
   nó interior, um par `(left, right)` fixo via bisseção balanceada do
   caminho (mantém índices pares + o último, repetidamente, até o próprio
   nó cair em posição ímpar). `action_condition_set.py:396-406`
   (`es_rule_condition_A`) só permite o swap disparar quando o
   `remote_node` atual da memória **já é igual** a esse `left`/`right`
   pré-calculado - ou seja, um nó "mais profundo" na árvore de bisseção só
   pode disparar depois que o nó vizinho mais raso já disparou o seu.
   Isso é uma árvore de combinação bem definida, não uma cadeia simples
   esquerda-para-direita.

Consequência: ao contrário do modelo conservador (onde a multiplicação é
comutativa e a ordem dos swaps não importa), no mecanismo real **a ordem
importa**: um nó "folha" da árvore de bisseção contribui sua própria
`raw_fidelity` ao quadrado (ambos os lados frescos); um nó "raiz"/interior
mais profundo pode não contribuir sua própria `raw_fidelity` nenhuma vez
(ambos os lados já vieram de swaps anteriores) - só sua
`swapping_degradation` entra na conta.

## Os dois estimadores (`src/ibqn/planning/fidelity_estimation.py`)

### `ConservativeMinEstimator`

Preserva o comportamento original byte a byte: `hop_fidelity(a,b) =
min(raw_fidelity(a), raw_fidelity(b))`, produto dos saltos vezes produto
das degradações interiores. É o estimador **padrão** em todo o código
(`evaluate_route`/`IntentPlanner` continuam se comportando exatamente como
antes da Fase J1 a menos que um estimador diferente seja passado
explicitamente).

### `SequenceConsistentEstimator`

Reproduz o mecanismo real: para uma rota com >= 1 nó interior, resolve a
fidelidade via `_swap_tree_fidelity`, que:

1. replica o mesmo algoritmo de bisseção de `generate_load_rules`
   (`_bisection_partners`, um port literal do laço `while
   _path.index(owner) % 2 == 0: ...`);
2. para cada nó interior, decide recursivamente se cada lado é "fresco"
   (usa a própria `raw_fidelity` do nó) ou "propagado" (usa o resultado do
   swap do nó vizinho físico, resolvido primeiro).

Para um link direto de 2 nós (sem swap), usa a `raw_fidelity` do nó
**de origem** apenas - `RequestApp.get_memory` só reporta evidência de
entrega do lado iniciador da reserva (`docs/limitations.md`), então o
valor do destino nunca é observado.

## Validação

`tests/unit/test_fidelity_estimation.py` cobre a matriz completa pedida
(enlace uniforme/heterogêneo de 2 nós, cadeia uniforme/heterogênea de 3
nós, diamante uniforme/heterogênea, com/sem purificação), e:

- os dois casos do diamante heterogêneo são conferidos contra os valores
  **já observados empiricamente** na campanha `C01` da Fase H3 (0.7695 na
  rota `bad`, 0.657922 na rota `good1/good2`);
- um caso adicional de 5 nós/3 swaps interiores
  (`test_swap_tree_fidelity_matches_real_simulation_on_a_three_interior_node_chain`)
  roda a simulação real do SeQUeNCe (não apenas outra fórmula
  independente) e confirma correspondência exata (`0.62018328564`) entre
  a previsão do estimador e a fidelidade média observada - a mesma
  disciplina de "valide contra o simulador real" usada em toda a Fase H.

## Integração

`evaluate_route`/`IntentPlanner` aceitam um `fidelity_estimator`
opcional (`ConservativeMinEstimator` por padrão). Campanhas podem varrer
`fidelity_estimator: [conservative_min, sequence_consistent]` via
`strategies.fidelity_estimator` no YAML (mesmo mecanismo de
`strategies.routing`/`strategies.purification`). `TrialIdentity.strategy`
agora inclui o nome do estimador
(`f"{routing}__{purification}__{fidelity_estimator}"`), então trocar de
estimador sempre produz um `trial_id` diferente.

`TrialRecord` ganhou `fidelity_estimator`, `observed_fidelity`,
`absolute_fidelity_error`, `relative_fidelity_error` - todos `None`
sempre que `estimated_fidelity`/`observed_fidelity` (que é uma cópia
nomeada de `average_fidelity`) não estiverem disponíveis (trial
REJECTED/FAILED, ou nenhum par entregue).

## Critério de aceite

Confirmado: em toda topologia heterogênea testada, `SequenceConsistentEstimator`
produz um `pre_swap_fidelity` estritamente maior que
`ConservativeMinEstimator` (nunca subestima), e em toda topologia uniforme
os dois coincidem exatamente - sem quebrar nenhum teste/campanha que já
usava o estimador conservador como padrão implícito.
