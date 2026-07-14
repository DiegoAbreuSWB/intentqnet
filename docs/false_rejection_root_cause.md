# Causa raiz das rejeições falsas do planner (Fase K3, seção 10)

Audita a causa exata dos falsos negativos do planner encontrados em
`docs/planner_operational_gap.md`/F04 (`results/processed/
F04_planner_vs_operation/`) - **não** a heterogeneidade de topologia
(achado da Fase J1, que é sobre `diamond_heterogeneous` e a árvore de
swap), já que os trials rejeitados vêm de `three_node_1_repeater`, uma
topologia **uniforme** (um único par a-r-b, mesmo `raw_fidelity` nos três
nós). Um texto anterior em `docs/final_experimental_design.md`
atribuía incorretamente a causa à heterogeneidade - corrigido nesta
fase (ver "Texto corrigido" ao final).

## Ficha técnica

| Campo | Valor |
|---|---|
| Topologia | `three_node_1_repeater` (`demos.topologies.three_node_spec`) - uniforme, `a - r - b`, um único nó de swap (`r`) |
| `raw_fidelity` por nó | 0.85 em `a`, `r`, `b` (idêntico - não há heterogeneidade física aqui) |
| `swapping_degradation` (nó `r`) | 0.95 |
| `attenuation_db_per_m` | 1e-5 (perda óptica desprezível - cenário limitado por fidelidade, não por perda) |
| Estimador | `ConservativeMinEstimator` (padrão de F03/F04) |
| Política de purificação | `automatic` (`PurifyUntilTarget`, `src/ibqn/planning/purification.py`) |
| Número de rounds modelado pelo planner | **exatamente 1**, sempre - `rounds_estimate=1` hard-coded em `PurifyUntilTarget.decide()` (`src/ibqn/planning/purification.py:71`), nunca calculado a partir de quantos rounds seriam necessários |
| Comportamento real do SeQUeNCe | `Reservation.purification_mode='until_target'` - mecanismo instalado automaticamente por `ResourceManager.generate_load_rules`, que tenta purificar **repetidamente até atingir o alvo** (ou até um critério interno de parada do SeQUeNCe), não uma única vez |

## A cadeia de cálculo exata (verificada, não estimada)

1. **Fidelidade só-swap** (`planning.feasibility.estimate_swap_only_fidelity`):
   `raw_fidelity(a,r) x raw_fidelity(r,b) x swapping_degradation(r)`
   `= 0.85 x 0.85 x 0.95 = 0.686375` - bate exatamente com
   `estimated_fidelity` observado nos trials `purification_policy=disabled`
   e nos trials `automatic` com `min_fidelity<=0.65` (onde purificação
   nem chega a ser tentada, porque a fidelidade só-swap já atende).
2. **Uma rodada de purificação** (`PurifyUntilTarget.decide`, quando
   `swap_only_fidelity < target_fidelity` e `allow_purification=True`):
   `BBPSSWCircuit.improved_fidelity(0.686375) = 0.720252` - bate
   exatamente com `estimated_fidelity` observado em todos os trials
   `automatic` com `0.65 < min_fidelity <= 0.72`.
3. **Nunca uma segunda rodada**: `rounds_estimate` é literalmente
   `1` no único branch que tenta purificar - não existe um branch que
   calcule 2+ rounds. Qualquer `min_fidelity > 0.720252` é REJECTED
   pelo planner **de forma determinística**, independentemente de quão
   perto do limiar o valor esteja.

## Confirmação empírica (Fase K2, campanha de densificação)

Extensão de F03 com limiares mais densos entre 0.72 e 0.75 (0.73, 0.735,
0.74, 0.745, mesmos 20 seeds, mesma topologia -
`scripts/build_f04_planner_operation_matrix.py` /
`results/raw/F03_purification/trials.csv`) confirmou que a rejeição
**não é uma transição gradual** - é um degrau exato:

| `min_fidelity` | `automatic`: `final_status` | `estimated_fidelity` |
|---:|---|---:|
| 0.65 | SATISFIED (20/20) | 0.686375 |
| 0.70 | SATISFIED (20/20) | 0.720252 |
| 0.72 | SATISFIED (20/20) | 0.720252 |
| 0.73 | REJECTED (20/20) | *(nenhuma - rejeitado antes de simular)* |
| 0.735 | REJECTED (20/20) | *(idem)* |
| 0.74 | REJECTED (20/20) | *(idem)* |
| 0.745 | REJECTED (20/20) | *(idem)* |
| 0.75 | REJECTED (20/20) | *(idem)* |

Isso é uma consequência direta e esperada da cadeia de cálculo acima -
não uma descoberta nova, mas uma confirmação quantitativa de um
comportamento já previsível a partir do código.

## Resultado do oracle

`scripts/build_f04_planner_operation_matrix.py` (Fase K2) re-testa via
`run_offline_oracle_baseline` (simulação real, não a estimativa
estática) **todos** os trials `REJECTED` de `three_node_1_repeater`
(240 trials, após a densificação de F03 - eram 80 antes dela, cobrindo
`min_fidelity` de 0.70 a 0.75, ambas as políticas de purificação).

**Resultado: 240/240 (100%) confirmados satisfazíveis pelo oracle** -
`false_rejection_rate=1.0` sobre a amostra inteira, não apenas sobre os
80 trials originais em `min_fidelity=0.75` (`results/processed/
F04_planner_vs_operation/gap_metrics.json`). A densificação fortalece a
conclusão em vez de apenas replicá-la: o oracle confirma satisfazibilidade
uniformemente em TODO o intervalo rejeitado (0.70-0.75), não só no
extremo superior - consistente com a causa primária abaixo (o teto de
uma rodada é uma propriedade fixa do modelo, não um limite que varia
com a proximidade ao alvo).

## Causa primária

**O planner estima a fidelidade pós-purificação com exatamente UMA
rodada de `BBPSSWCircuit.improved_fidelity`, enquanto o SeQUeNCe real
usa `purification_mode='until_target'` (potencialmente múltiplas
rodadas)** - qualquer meta de fidelidade acima do teto de uma rodada é
rejeitada pelo planner mesmo quando o sistema real, aplicando mais de
uma rodada, consegue atingi-la. Confirmado por leitura direta do código
(`purification.py:69-74`, comentário do próprio autor já documentava
essa limitação) e pela mensagem de log emitida em tempo real durante a
campanha de densificação ("one-round static estimate...; SeQUeNCe's
'until_target' mode may run a different number of rounds at execution
time").

## Causas secundárias

- **Modelo de propagação single-round não é conservador da forma
  "sempre subestima com folga"**: para F03/`three_node_1_repeater`, o
  teto de uma rodada (0.720252) está bem abaixo do que o sistema real
  provavelmente atinge com múltiplas rodadas - mas o TAMANHO exato dessa
  folga não é modelado, só constatado empiricamente via oracle.
- **Nenhuma busca automática de round count**: mesmo se o planner
  quisesse estimar 2+ rodadas, `PurificationStrategy` não tem um método
  para isso - implementá-lo exigiria replicar a lógica interna de
  `until_target` do SeQUeNCe fora do próprio SeQUeNCe (o tipo de
  duplicação que este projeto evita por princípio, ver
  `docs/architecture.md`).
- **Este é um mecanismo diferente do achado da Fase J1**: a
  heterogeneidade de `diamond_heterogeneous` (Fase J1) afeta APENAS a
  ORDEM de swap em topologias com múltiplos saltos de swap - não tem
  relação com o número de rodadas de purificação, que é um eixo
  ortogonal e se aplica igualmente a topologias uniformes de um único
  swap, como `three_node_1_repeater`.

## Texto corrigido em `docs/final_experimental_design.md`

O parágrafo original ("é uma consequência direta e esperada do achado
da Fase J1... em topologias heterogêneas") foi substituído por uma
referência a este documento - ver a seção F04 daquele arquivo.
