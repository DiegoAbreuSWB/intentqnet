# Catálogo de topologias (Fase J4)

## Motivação

Até o fim da Fase H3, todo achado deste projeto (divergência de
estratégias de roteamento, teto de purificação, reconciliation,
subestimativa de fidelidade heterogênea) foi demonstrado em no máximo
duas topologias: `three_node_spec` (uniforme, 1 repetidor) e
`demos.topologies.diamond_spec` (heterogênea, 2 rotas). Este catálogo
(`src/ibqn/experiments/topology_catalog.py`) adiciona as topologias
restantes para checar se esses achados generalizam ou eram artefato
dessas duas topologias específicas.

## T1 / T4 - `linear_chain_spec(n_repeaters)`

Um único builder paramétrico cobre tanto "uma cadeia linear" (T1,
contagem fixa de repetidores) quanto "uma cadeia de tamanho variável"
(T4, `n_repeaters` variando 0-4) - é a mesma forma, só muda quantos
repetidores existem entre os dois extremos.

- `n_repeaters=0`: link direto de 2 nós (mesma forma de
  `demos.topologies.two_node_spec`) - sem swap algum.
- `n_repeaters=1`: mesma forma de `demos.topologies.three_node_spec`.
- `n_repeaters=2..4`: cadeias mais longas, usadas para observar
  degradação por swaps sucessivos, viabilidade, custo de simulação
  (Fase J9/J10).

Todos os nós compartilham `raw_fidelity`/`swapping_degradation`
uniformes por padrão - diferente do diamante, que é deliberadamente
heterogêneo (T2).

## T2 - `demos.topologies.diamond_spec` (reusada, não duplicada)

A única topologia onde `ShortestHopCountRouting`/`HighestFidelityRouting`
(preferem `bad`, 2 saltos) e `LeastLossRouting` (prefere
`good1`/`good2`, 3 saltos) genuinamente divergem - usada extensivamente
nas Fases H3/J1/J3.

## T3 - `small_mesh_spec`

Uma grade 2x4 de 8 roteadores:

```text
a0 - a1 - a2 - a3
|    |    |    |
b0 - b1 - b2 - b3
```

Entre cantos opostos (`a0` a `b3`) existem múltiplos caminhos simples de
comprimentos diferentes (confirmado: pelo menos 2 candidatos de 4
saltos cada) - usada para testar a escalabilidade da enumeração de
caminhos do planner (`HighestFidelityRouting`, `docs/limitations.md`) e
divergência de estratégias além da escolha binária do diamante.

## T5 - `near_equivalent_paths_spec`

Duas rotas de 1 repetidor cada (`source-mid_a-dest`,
`source-mid_b-dest`) com custo **deliberadamente próximo, não
idêntico** - a atenuação de `mid_b` é maior que a de `mid_a` por uma
fração configurável (`cost_gap_fraction`, 5% por padrão), ao contrário
do diamante (T2), onde `bad` perde por ordens de grandeza. Usada para
verificar estabilidade de decisão (Fase J9): uma pequena diferença de
custo real ainda produz uma escolha determinística e correta
(`LeastLossRouting` sempre escolhe `mid_a`, confirmado em
`tests/experiments/test_topology_catalog.py`), mas a pergunta
interessante para a campanha de variabilidade é se o resultado
*operacional* (pares entregues, fidelidade) varia tanto quanto o custo
estimado varia - ou se pequenas diferenças de estimativa produzem
diferenças operacionais desproporcionalmente grandes ou pequenas.

## Validação (smoke tests)

`tests/experiments/test_topology_catalog.py` cobre, para cada uma das 5
topologias (T1 em 5 contagens de repetidores + T2 + T3 + T5 = 8 casos):

1. conectividade (nós existem no grafo, há pelo menos uma aresta);
2. rotas candidatas existem para as três `RoutingStrategy`s;
3. parâmetros físicos válidos (memórias > 0, fidelidade em (0.5, 1],
   atenuação/distância > 0);
4. um plano viável existe (com meta de fidelidade propositalmente baixa
   - 0.3 - já que este smoke test não visa explorar limites de
   viabilidade, isso já é feito pelas campanhas C02/C03);
5. a reserva realmente aceita pelo SeQUeNCe usa exatamente a rota
   planejada (mesma invariante de `execute_trial`);
6. o intent chega a `ACTIVE`.

## Limitações desta etapa

- Nenhuma campanha em escala usa este catálogo ainda - isso é para a
  campanha `F02` (Fase J10, "Routing", que varia topologia, estratégia,
  heterogeneidade, atenuação, seed).
- `small_mesh_spec` usa uma grade fixa, não uma topologia aleatória -
  suficiente para ter múltiplos candidatos sem introduzir uma fonte de
  variabilidade adicional não controlada.
- A classificação de conectividade clássica continua sendo sempre malha
  completa (`NetworkTopologySpec`'s limitação já documentada em
  `docs/limitations.md`) - nenhuma topologia aqui testa conectividade
  clássica esparsa.
