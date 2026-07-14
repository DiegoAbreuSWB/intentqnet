# Explicação causal do resultado extremo de roteamento (Fase K3)

Explica quantitativamente a diferença de ~446 vs. ~7.85 pares entregues
entre `least_loss` e `shortest_hop_count`/`highest_fidelity` na topologia
diamante (`F02_routing`, `results/raw/F02_routing/trials.csv`), e
confirma que o efeito é uma propriedade desta topologia específica, não
uma vantagem universal de uma estratégia sobre outra.

## Nota metodológica: `TrialRecord.attenuation_db_per_m`/`distance_m` não são por rota

Esses dois campos (`runner.py:294-295`) registram apenas
`topology_spec.quantum_links[0]` - o PRIMEIRO enlace declarado na
topologia, não uma agregação da rota realmente usada. Por isso os
números abaixo vêm da **construção da topologia**
(`demos/topologies.py::diamond_spec`), não de `trials.csv` diretamente -
única forma de obter os parâmetros físicos reais por rota.

## Ficha por rota (`diamond_heterogeneous`)

| | `bad` (r1→bad→r3) | `good1`/`good2` (r1→good1→good2→r3) |
|---|---:|---:|
| Saltos | 2 | 3 |
| Distância por enlace | 1000 m | 500 m |
| Distância total | 2000 m | 1500 m |
| Atenuação | 0.02 dB/m | 1e-5 dB/m |
| Perda óptica por enlace | 1000×0.02 = 20 dB | 500×1e-5 = 0.005 dB |
| Perda óptica total (soma) | 40 dB | 0.015 dB |
| `raw_fidelity` (todos os nós) | 0.9 | 0.9 |
| `swapping_degradation` por nó-swap | 0.95 (1 nó: `bad`) | 0.95 (2 nós: `good1`, `good2`) |
| Nós de swap (fidelidade só conta nós interiores - achado Fase J1) | 1 | 2 |

## Fidelidade estimada (`ConservativeMinEstimator`) - verificada exatamente

- `bad`: `0.9 × 0.9 × 0.95 = 0.7695` - bate exatamente com
  `average_fidelity` observado (`highest_fidelity`/`shortest_hop_count`:
  0.7695).
- `good1`/`good2`: `0.9³ × 0.95² = 0.729 × 0.9025 = 0.657923` - bate
  exatamente com `average_fidelity` observado (`least_loss`: 0.657922,
  diferença de arredondamento).

Menos saltos de swap (rota `bad`) preserva mais fidelidade - consistente
com o mecanismo já documentado em `docs/fidelity_estimation_model.md`
(só nós de swap interiores degradam fidelidade).

## Eventos e entrega (por que a rota de baixa perda entrega ~57x mais)

| Métrica (média, n=20 seeds) | `bad` | `good1`/`good2` |
|---|---:|---:|
| `eg_attempts` (tentativas de geração elementar) | 2014.35 | 1185.00 |
| `eg_success` (gerações bem-sucedidas) | 8.7 | 449.5 |
| Taxa de sucesso por tentativa | ~0.43% | ~37.9% |
| `delivered_pairs` | 7.85 | 446.10 |
| `throughput_active_window` | 78.5 | 4461.0 |
| `first_pair_latency_s` (média) | 0.0189 s | 0.0013 s |

A rota `bad` tenta MAIS vezes (2014 vs. 1185) mas com uma taxa de
sucesso ~88x menor (perda de 40 dB é catastrófica: transmissão
≈10^(-40/10) = 0.0001 por fóton) - o sistema insiste em tentar dentro da
mesma janela de simulação, mas a perda domina completamente o resultado.
A rota `good1`/`good2`, apesar de ter mais saltos e portanto perder mais
fidelidade por swap, tem perda óptica total 2667x menor (40 dB vs. 0.015
dB) - a taxa de sucesso por tentativa é ~88x maior, dominando o efeito
do maior número de saltos.

**Conclusão quantitativa**: a diferença de ~57x em `delivered_pairs` é
inteiramente explicada pela perda óptica acumulada (dB) da rota, não
pela fidelidade nem pelo número de saltos isoladamente - fidelidade e
throughput são otimizados por critérios diferentes e podem apontar para
rotas opostas nesta topologia (por isso ela foi desenhada assim,
`demos/topologies.py::diamond_spec`'s docstring).

## Verificações de integridade (nenhuma duplicação, mesma janela/seed, rota aplicada = rota planejada)

- **Sem duplicação de pares**: `delivered_pairs` vem de
  `len(evidence.delivered_pairs)`, uma lista de eventos `DELIVERY` reais
  do SeQUeNCe (`assurance/telemetry.py`) - nunca inferido ou multiplicado.
  Confirmado indiretamente pela auditoria K1
  (`scripts/audit_final_results.py`: unicidade de `trial_id`, nenhuma
  linha duplicada).
- **Mesmo pool de memória**: todas as 3 estratégias usam a MESMA
  `diamond_spec()` (mesmas `NodeSpec.memories=20` em todo nó) - a
  diferença de resultado não vem de capacidade de memória diferente
  entre estratégias.
- **Mesma janela e seed**: `stop_time_s=0.2` idêntico nas 3 estratégias;
  seeds `0..19` idênticas e pareadas (`scripts/generate_final_figures.py`
  usa a mesma base para todas as comparações estatísticas de F02).
- **Rota aplicada é a rota planejada**: `TrialRecord.route` registra a
  rota realmente usada por `SequenceExecutor.deploy` - confirmado que
  `shortest_hop_count`/`highest_fidelity` sempre aplicam `r1 -> bad ->
  r3` e `least_loss` sempre aplica `r1 -> good1 -> good2 -> r3`, sem
  exceção em nenhum dos 20 seeds (nenhuma variação de rota entre seeds
  nesta topologia - a topologia e as métricas de custo de cada
  estratégia são determinísticas, só a simulação de eventos discretos é
  estocástica).

## O efeito depende da topologia - comparação com `small_mesh`

Na malha pequena (`small_mesh`, mesma campanha F02), as três estratégias
entregam praticamente o mesmo número de pares:

| Estratégia | Rota | `delivered_pairs` (média) |
|---|---|---:|
| `highest_fidelity` | `a0→a1→a2→a3→b3` | 697.2 |
| `shortest_hop_count` | `a0→a1→a2→a3→b3` | 697.2 |
| `least_loss` | `a0→a1→b1→b2→b3` | 696.0 |

Nenhuma diferença estatisticamente significativa sobrevive à correção
de Holm para `delivered_pairs`/`average_fidelity` nesta topologia
(`results/processed/F02_routing/statistical_comparisons.csv`) - a malha
tem múltiplos caminhos de custo/perda semelhantes, então não há uma
rota "claramente pior" para se evitar. **O ganho de ~57x observado no
diamante não é uma propriedade geral de nenhuma estratégia de
roteamento - é uma propriedade desta topologia específica**, desenhada
deliberadamente para que fidelidade e perda ótica apontem para rotas
diferentes (`docs/topology_catalog.md`). Alegações no artigo devem se
referir a "esta topologia diamante avaliada", nunca a "roteamento por
menor perda em geral" (ver `docs/threats_to_validity.md`, seção de
validade externa).
