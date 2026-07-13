# Desenho experimental final e resultados (Fase J10/J11)

Consolida o desenho e os resultados REAIS das oito campanhas finais
(F01-F08), executadas via `experiments/programmatic_campaign.py` (F02,
F03, F07, F08) ou scripts dedicados que reusam os mesmos blocos
testados (F01, F05, F06), mais a análise de matriz planner-vs-operação
(F04) e a análise estatística pareada (`experiments/
statistical_analysis.py`) aplicada a todas elas. 20 seeds por condição em
todas as campanhas, conforme `docs/seed_justification.md`. Nenhum número
abaixo foi estimado ou simulado fora do SeQUeNCe - todos vêm de
`results/raw/F0X_*/trials.csv` e `results/processed/F0X_*/`.

## F01 - Arquitetura e baselines

**Desenho**: topologia diamante heterogênea, 20 seeds, 6 condições por
seed: `native_sequence`, `static_provisioning`, `ibqn_without_assurance`,
`ibqn_with_assurance` (via `execute_trial`, reconciliação desligada),
`ibqn_with_reconciliation` (reconciliação ligada), `offline_oracle`. 120
linhas em `results/raw/F01_architecture_baselines/trials.csv`.

**Resultados** (médias sobre 20 seeds):

| Condição | delivered_pairs | average_fidelity | satisfied | total_wall_time_s |
|---|---:|---:|---:|---:|
| `native_sequence` | 446.10 | 0.658 | 1.00 | 4.67 |
| `static_provisioning` | 7.85 | 0.770 | 0.25 | 1.84 |
| `ibqn_without_assurance` | *(não medido)* | *(não medido)* | *(não medido)* | 1.81 |
| `ibqn_with_assurance` | 7.85 | 0.770 | 0.25 | 1.79 |
| `ibqn_with_reconciliation` | 339.85 | 0.686 | 1.00 | 5.41 |
| `offline_oracle` | 446.10 | 0.658 | 1.00 | 6.50 |

**Achados** (todos com Holm-adjusted p < 0.05, ver
`results/processed/F01_architecture_baselines/statistical_comparisons.csv`):

- **Custo da abstração intent-based**: `ibqn_with_assurance` e
  `static_provisioning` são estatisticamente indistinguíveis em
  `delivered_pairs`/`average_fidelity`/`satisfied` (mesma rota
  `ShortestHopCountRouting`, mesmo resultado) - o overhead de orquestração
  não altera o resultado físico, só o tempo de parede (diferença de
  0.047s, `p=0.030`, ainda assim uma diferença real e mensurável).
- **Benefício da escolha de rota**: `native_sequence` entrega ~57x mais
  pares que `static_provisioning`/`ibqn_with_assurance` (438 pares de
  diferença, `p≈6.5e-31`) porque o roteamento nativo do SeQUeNCe é
  ponderado por distância física e por acaso escolhe a rota de baixa
  perda no diamante (achado da Fase J3) - `ShortestHopCountRouting`
  escolhe a rota "ruim".
- **Benefício da reconciliação**: `ibqn_with_reconciliation` recupera de
  0.25 para 1.00 de taxa de satisfação (`p=0.0016`) e de 7.85 para 339.85
  pares entregues (`p=0.0039`) trocando de rota automaticamente -
  confirma que a reconciliação isola e resolve exatamente o problema que
  a escolha de rota causou em `ibqn_with_assurance`.
- **Benefício da assurance por si só**: `ibqn_without_assurance` aceita
  100% das reservas mas não mede `satisfied`/`delivered_pairs` (por
  desenho - não coleta evidência) - demonstra concretamente que aceitar
  uma reserva não é o mesmo que saber se ela foi cumprida; esse é
  precisamente o valor que a camada de assurance adiciona.
- **Oracle como teto**: `offline_oracle` empata com `native_sequence`
  neste cenário (ambos encontram a mesma rota ótima), confirmando que a
  rota de baixa perda é de fato o ótimo global aqui, não uma coincidência
  do roteamento nativo.

## F02 - Roteamento

**Desenho**: `diamond_spec` + `small_mesh_spec` (grade 2x4) × 3
estratégias (`shortest_hop_count`, `least_loss`, `highest_fidelity`) × 20
seeds = 120 trials, `campaign_name="F02_routing"`. 0 falhas.

**Resultados**:

| Cenário | Estratégia | delivered_pairs | average_fidelity | satisfied |
|---|---|---:|---:|---:|
| `diamond_heterogeneous` | `highest_fidelity` | 7.85 | 0.770 | 0.25 |
| `diamond_heterogeneous` | `least_loss` | 446.10 | 0.658 | 1.00 |
| `diamond_heterogeneous` | `shortest_hop_count` | 7.85 | 0.770 | 0.25 |
| `small_mesh` | `highest_fidelity` | 697.20 | - | 1.00 |
| `small_mesh` | `least_loss` | 696.00 | - | 1.00 |
| `small_mesh` | `shortest_hop_count` | 697.20 | - | 1.00 |

**Achados**: no diamante, `least_loss` domina as outras duas por ~56x em
`delivered_pairs` (`p≈1.9e-31`) - `highest_fidelity` e
`shortest_hop_count` são estatisticamente idênticos entre si (mesma rota
escolhida por acaso nesta topologia, diferença exatamente zero em todo
seed - `test_used="identical"`, sem comparação espúria). Na malha
pequena, as três estratégias são equivalentes (múltiplos caminhos de
custo/fidelidade semelhante) - nenhuma diferença sobrevive à correção de
Holm. Confirma a tese central do projeto: o ganho de escolher a rota
certa é real, grande, e **depende inteiramente da topologia** - na malha
não há ganho porque não há uma rota claramente pior para se evitar.

## F03 - Purificação

**Desenho**: `three_node_spec` (1 repetidor) + `linear_chain_spec` (2
repetidores) × `min_fidelity ∈ {0.65, 0.70, 0.72, 0.75}` ×
`purification_policy ∈ {disabled, automatic}` × 20 seeds = 320 trials,
`campaign_name="F03_purification"`. 0 falhas.

**Taxa de satisfação** (`three_node_1_repeater`; `linear_chain_2_repeaters`
é 0% em toda combinação, ver F04 abaixo):

| min_fidelity | `automatic` | `disabled` |
|---:|---:|---:|
| 0.65 | 1.00 | 1.00 |
| 0.70 | 1.00 | **0.00** |
| 0.72 | 1.00 | **0.00** |
| 0.75 | 0.00 | 0.00 |

**Achados**: a purificação só faz diferença mensurável na fronteira
(0.70-0.72): abaixo (0.65) a fidelidade bruta já basta e as duas
políticas produzem resultados **idênticos bit-a-bit** (diferença
exatamente zero em todo seed - achado que expôs um caso degenerado do
`scipy.stats.wilcoxon`, ver seção "Bugs encontrados" abaixo); acima
(0.75) nenhuma das duas satisfaz (ver F04 - mas o oracle mostra que é uma
rejeição do *planner*, não do sistema físico). As únicas duas
comparações que sobrevivem à correção de Holm (`p=0.000008`) são
exatamente 0.70 e 0.72, confirmando que o benefício de purificação é real
mas estreito.

## F04 - Planner versus operação

**Desenho**: combina os 440 trials de F02+F03, classifica cada um em 5
categorias (`experiments/planner_operation_matrix.py`), e testa contra o
`offline_oracle` (J3) todo trial `INFEASIBLE_AND_REJECTED` reconstruível
de F03 (`three_node_1_repeater`, 80 trials rejeitados - os 160
rejeitados de `linear_chain_2_repeaters` não são testados por falta de
uma rota alternativa reconstruível de forma inequívoca, e permanecem
corretamente não-testados, não "confirmados verdadeiro-rejeitados").
Matriz e métricas em `results/processed/F04_planner_vs_operation/`.

**Matriz** (`n=440`):

| Categoria | Contagem | Interpretação |
|---|---:|---|
| `FEASIBLE_AND_SATISFIED` | 170 | previsão correta |
| `FEASIBLE_BUT_VIOLATED` | 30 | falsa viabilidade operacional |
| `INFEASIBLE_AND_REJECTED` | 160 | rejeição prevista, nunca testada contra oracle |
| `INFEASIBLE_BUT_POTENTIALLY_SATISFIABLE` | 80 | falso negativo do planner (oracle confirma satisfazível) |
| `EXECUTION_FAILED` | 0 | reserva rejeitada pelo próprio SeQUeNCe apesar do planner achar viável |

**Métricas do gap**:

| Métrica | Valor |
|---|---:|
| `operational_success_rate` | 0.386 |
| `false_feasibility_rate` | 0.150 |
| `false_rejection_rate` (sobre os 80 testados) | **1.000** |
| `fidelity_prediction_error` (MAE) | 0.0219 |
| `delivery_deficit` | 0.0 |
| `throughput_deficit` | 0.0 |

**Achado central - o mais forte da fase**: os 80 trials rejeitados de
`three_node_1_repeater` (`min_fidelity=0.75`, mesma
`reserved_memory_slots=10`/`min_delivered_pairs=10`/`duration_s=0.1` de
F03, re-testados com os mesmos parâmetros via `run_offline_oracle_baseline`)
são **100% falsos negativos**: o `ConservativeMinEstimator` do planner
rejeita a priori algo que o oracle (testando de fato via simulação, com
purificação e busca de rota real) confirma ser alcançável. Isso não é uma
falha aleatória - é uma consequência direta e esperada do achado da Fase
J1 (o estimador conservador subestima o ganho real da purificação em
topologias heterogêneas). `false_feasibility_rate=0.15` mostra que o erro
oposto (aceitar algo que depois viola) também existe, mas é
proporcionalmente menor que a rejeição falsa neste conjunto de cenários.
`fidelity_prediction_error` de 0.022 (2.2 pontos percentuais) confirma
que quando o planner *aceita*, a estimativa de fidelidade é geralmente
próxima da observada.

## F05 - Reconciliação em escala

**Desenho**: 5 casos × 20 seeds = 100 trials, script dedicado
(`metrics.configure()` corrigido - ver "Bugs encontrados"). Dados em
`results/raw/F05_reconciliation/trials.csv`.

| Caso | `initial_status` | Ação recomendada | Taxa de recuperação |
|---|---|---|---:|
| `route_change_recoverable` | 15 VIOLATED / 5 SATISFIED | `route_change` | 1.00 (15/15) |
| `duration_increase_recoverable` | 20 VIOLATED | `duration_increase` | 1.00 (20/20) |
| `slot_increase_recoverable` | 20 VIOLATED | `slot_increase` | 0.95 (19/20) |
| `fidelity_ceiling_unrecoverable` | 20 REJECTED_OR_FAILED | nenhuma (`no_action`) | - (nunca chega a tentar) |
| `severe_loss_attempt` | 20 VIOLATED | `duration_increase` (tentativa) | **0.00 (0/20)** |

**Achados**: os três casos desenhados como recuperáveis se recuperam
quase sempre (95-100%); o caso de teto físico de fidelidade nunca chega
a ser tentado (a política corretamente reconhece `no_action` quando
nenhuma rota alternativa nem ajuste de recurso resolveria uma violação de
*fidelidade*); o caso de perda severa demonstra o limite honesto da
política atual - ela tenta (`duration_increase`, a única ação disponível
para violação de throughput/entrega sem rota alternativa) mas **nunca
recupera**, porque dobrar a duração não compensa uma atenuação alta o
suficiente. Isso é o comportamento correto e esperado, não um bug: a
política de reconciliação não promete recuperar tudo, só tentar as ações
plausíveis e reportar quando falham (`recovered=False`).

## F06 - Overhead em escala

**Desenho**: diamante, 20 seeds, 3 condições: `ibqn_instrumented`
(`run_instrumented_trial`, reconciliação ligada), `native_sequence`,
`static_provisioning`. Dados em `results/raw/F06_overhead/trials.csv`.

| Condição | `planning_wall_time_s` | `simulation_wall_time_s` | `total_trial_wall_time_s` | `orchestration_overhead_ratio` |
|---|---:|---:|---:|---:|
| `ibqn_instrumented` | 0.00092 | 7.248 | 7.259 | 0.148% |
| `native_sequence` | 0.0 | 18.025 | 18.035 | 0.058% |
| `static_provisioning` | 0.00039 | 7.152 | 7.173 | 0.303% |

**Achados**: o overhead de orquestração do IBQN é **desprezível em
termos absolutos** (< 0.31% do tempo total de qualquer condição) -
`planning_wall_time_s` da ordem de menos de 1 milissegundo. O achado mais
interessante não é o overhead em si, mas que `native_sequence` leva **2.5x
mais tempo de simulação** que as outras duas condições (18.0s vs. 7.2s):
a rota que o roteamento nativo escolhe no diamante (baixa perda) processa
muito mais eventos de entrelaçamento bem-sucedidos por unidade de tempo
simulado (446 pares entregues vs. 7.85) - **tempo de parede de simulação
escala com o volume de eventos processados, não com o tamanho ou
"qualidade" da topologia** - uma rota melhor pode ser mais lenta de
simular, não mais rápida, porque há mais trabalho real para o simulador
de eventos discretos fazer.

## F07 - Estimadores de fidelidade

**Desenho**: `diamond_spec` × 3 estratégias × 2 estimadores
(`conservative_min`, `sequence_consistent`) × 20 seeds = 120 trials. 0
falhas.

**Erro absoluto de fidelidade** (`|estimated - observed|`):

| Estratégia | `conservative_min` | `sequence_consistent` |
|---|---:|---:|
| `highest_fidelity` | 0.0831 | **0.0000** |
| `least_loss` | 0.0532 | **0.0000** (~1e-17) |
| `shortest_hop_count` | 0.0831 | **0.0000** |

**Achados**: `SequenceConsistentEstimator` reproduz a fidelidade real com
erro numericamente nulo em toda estratégia/seed (diferença sobrevive à
correção de Holm em todos os 3 casos, `p≤0.00002`) - confirma
empiricamente, em escala, o que a Fase J1 derivou analiticamente: o
mecanismo de árvore de swap balanceada é reproduzido exatamente. O
estimador conservador erra sistematicamente (~5-8 pontos percentuais),
sempre para o mesmo lado (subestima), consistente com o achado de F04
(a maioria dos falsos negativos do planner vem do uso do estimador
conservador). Nenhuma diferença em `delivered_pairs`/`accepted`/
`satisfied` entre estimadores neste cenário - ambos aceitam as mesmas
rotas aqui, a diferença é só na precisão da estimativa, não na decisão
final (não haveria motivo para esperar diferença na decisão, já que
`min_fidelity=0.6` neste cenário é folgado o bastante para ambos
aceitarem apesar do erro do estimador conservador).

## F08 - Semântica de recursos/entrega

**Desenho**: `three_node_spec` × `reserved_memory_slots ∈ {2, 10}` ×
`duration_s ∈ {0.02, 0.05}` × 20 seeds = 80 trials, desenho fatorial 2x2.

| `reserved_memory_slots` | `duration_s` | `delivered_pairs` | `delivery_ratio` | `deliveries_per_reserved_slot` | `satisfied` |
|---:|---:|---:|---:|---:|---:|
| 2 | 0.02 | 2.55 | 0.085 | 1.28 | 0.00 |
| 2 | 0.05 | 5.95 | 0.198 | 2.98 | 0.00 |
| 10 | 0.02 | 12.65 | 0.422 | 1.27 | 0.00 |
| 10 | 0.05 | 35.10 | 1.170 | 3.51 | **0.90** |

**Achados**: ambos os fatores têm efeito real e independente
(`delivered_pairs` aumenta com `reserved_memory_slots` mantendo
`duration_s` fixo, `p≤4.4e-12`, e aumenta com `duration_s` mantendo
`reserved_memory_slots` fixo, `p≤2e-17`) - confirma que
`reserved_memory_slots` (recurso reservado) e `duration_s` (janela de
tempo) são dimensões ortogonais de controle, exatamente a separação que
a Fase J2 introduziu. `deliveries_per_reserved_slot` cresce com
`duration_s` em ambos os níveis de slots (mais tempo por slot reservado =
mais entregas por slot), mas só a combinação de MAIS slots E MAIS tempo
(10, 0.05) atinge `min_delivered_pairs` (`satisfied=0.90`) - nenhuma
combinação com um único fator no nível baixo satisfaz.

## Bugs encontrados e corrigidos durante a análise (Fase J10)

Além do bug de contaminação do `sequence.utils.metrics` (documentado em
`docs/threats_to_validity.md`), a aplicação da análise estatística a
dados reais (não sintéticos) encontrou dois problemas genuínos em
`experiments/statistical_analysis.py`, ambos **na própria biblioteca**,
não apenas nos scripts de campanha - porque dados reais de campanha têm
duas propriedades que os testes unitários (com dados sintéticos gerados
por `numpy.random`) nunca exercitavam:

1. **Pares com valor ausente** (`NaN`): um trial `REJECTED` nunca roda a
   simulação, então `delivered_pairs`/`average_fidelity` são `NaN` no
   registro. Comparar "REJECTED" vs. "REJECTED" nessas colunas fazia
   `compare_groups_pairwise` alinhar um vetor todo `NaN` contra outro
   todo `NaN` - `scipy.stats.wilcoxon` retornava `nan` silenciosamente
   (sem levantar exceção), e o passo de running-max do
   `holm_correction` mascarava esse `nan` como um `p≈0.0`
   aparentemente "significativo". Corrigido descartando pares com `NaN`
   de qualquer lado antes de comparar (teste de regressão:
   `test_compare_groups_pairwise_drops_nan_pairs_instead_of_reporting_bogus_significance`).
2. **Diferenças pareadas idênticas (zero) em `n` grande**: quando um
   fator genuinely não produz NENHUMA diferença (ex.: purificação
   `automatic` vs. `disabled` quando a purificação nunca é de fato
   acionada), `scipy.stats.wilcoxon` num vetor de diferenças todo zero
   retorna `p=1.0` corretamente para `n=5` mas **`p=nan` para `n=20`**
   (mesmo padrão de entrada, comportamento interno diferente por
   tamanho de amostra - confirmado por experimentação direta) - de novo
   mascarado pelo `holm_correction` em um falso "significativo".
   Corrigido tratando esse caso explicitamente em `paired_comparison`
   antes de chamar o scipy (`test_used="identical"`, `p=1.0`,
   `effect_size=0.0`), sem depender do comportamento de exceção do
   scipy (teste de regressão:
   `test_paired_comparison_handles_all_zero_differences_at_larger_n_without_nan`).

Ambos os bugs teriam produzido conclusões estatísticas **erradas na
direção oposta à cautela** (falsos positivos de significância), o oposto
do que a Seção 13 exige ("nunca declarar superioridade a partir de uma
média isolada"). Corrigidos antes de qualquer número deste documento ser
escrito - todas as tabelas acima já refletem a versão corrigida.

## Reprodutibilidade

Toda tabela deste documento vem de `results/raw/F0X_*/trials.csv` (dados
brutos, um por trial) e `results/processed/F0X_*/` (matrizes e
comparações estatísticas derivadas) - nenhum número foi calculado fora
dessa cadeia. Comandos de reexecução completos em
`docs/campaign_architecture.md` e nos scripts de campanha referenciados
em cada seção acima.
