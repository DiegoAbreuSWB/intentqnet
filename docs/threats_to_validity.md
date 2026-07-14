# Ameaças à validade (Fase J10/J12, reestruturada na Fase K3)

Consolidação das limitações metodológicas já documentadas ao longo do
projeto (`docs/limitations.md`, `docs/campaign_architecture.md`,
`docs/seed_justification.md`, `docs/results_provenance.md`,
`docs/false_rejection_root_cause.md`, etc.) na estrutura padrão de
ameaças à validade - para que a seção de metodologia do artigo tenha um
único lugar que enumere o que pode e o que não pode ser concluído a
partir dos dados deste projeto. Ordem: interna, construto, externa,
conclusão estatística.

## 1. Validade interna (o efeito observado é mesmo causado pelo que dizemos)

- **Contaminação de métricas entre episódios** (encontrado e corrigido
  na Fase H3, e de novo de forma independente na Fase J10):
  `assurance.reconciliation.reconcile()` e, separadamente,
  `experiments.overhead.run_instrumented_trial()` não resetavam
  `sequence.utils.metrics` (um singleton de processo) antes de um novo
  episódio/trial, misturando evidência entre execuções que
  compartilhavam `intent_id`. Corrigido nos dois pontos, cada um com
  teste de regressão dedicado
  (`tests/integration/test_reconciliation.py`,
  `tests/experiments/test_overhead.py`).
- **Roteamento nativo do SeQUeNCe não é o que a documentação original
  deste projeto afirmava** (achado da Fase J3): a tabela de roteamento
  estática auto-gerada pondera por distância física, não por número de
  saltos - a baseline "Native SeQUeNCe" não é diretamente comparável a
  `ShortestHopCountRouting` como se pensava antes de medir. Ver
  `docs/routing_result_explanation.md` para a explicação quantitativa
  completa do efeito que isso causa em `diamond_heterogeneous`.
- **A ordem de swap afeta o resultado real de fidelidade em topologias
  heterogêneas** (achado da Fase J1) - a suposição original de que
  "multiplicação é associativa, ordem não importa" só vale para o
  estimador conservador, não para o mecanismo real do SeQUeNCe. Qualquer
  conclusão sobre fidelidade em topologias heterogêneas deve declarar
  qual estimador foi usado.
- **O planner estima purificação com exatamente uma rodada, o SeQUeNCe
  real pode rodar várias** (achado da Fase J10/K2,
  `docs/false_rejection_root_cause.md`) - causa raiz verificada por
  código (`purification.py:69-74`) e confirmada empiricamente (240/240
  trials rejeitados pelo planner em `three_node_1_repeater`, oracle
  confirma satisfazíveis). Independente da heterogeneidade de topologia
  (Fase J1) - ocorre mesmo em topologia uniforme.
- **Bugs de bookkeeping de manifesto** (Fase K1,
  `docs/results_provenance.md`): manifestos de campanhas com múltiplos
  blocos (múltiplas topologias, ou grade estendida em sessão posterior)
  sobrescreviam em vez de acumular `completed_trials`/`scenario_files`/
  `swept_factors` - os dados brutos (`trials.csv`) sempre estiveram
  corretos, só o registro de metadados estava. Corrigido com testes de
  regressão dedicados; não afeta nenhuma conclusão científica já
  publicada, apenas a rastreabilidade dos metadados.

## 2. Validade de construto (as métricas medem o que dizem medir)

- **`reserved_memory_slots` vs. `min_delivered_pairs`** (Fase J2): antes
  da separação, `requested_pairs` conflava recurso reservado com meta de
  entrega - qualquer conclusão de trabalho anterior a essa correção que
  usasse "requested_pairs" precisa ser reinterpretada à luz de qual dos
  dois conceitos realmente se aplicava.
- **`ConservativeMinEstimator` vs. `SequenceConsistentEstimator`** (Fase
  J1): a estimativa de fidelidade pré-simulação depende de qual
  estimador está ativo - "erro de previsão do planner" não é uma
  constante única deste sistema, é uma propriedade do par
  (estimador, topologia). `SequenceConsistentEstimator` "reproduz o
  modelo de fidelidade implementado pelo SeQUeNCe nas configurações
  avaliadas" (nunca "prediz perfeitamente redes reais") -
  `docs/fidelity_estimation_model.md`.
- **Recuperação de reconciliation não é um conceito único** (Fase K3,
  `docs/reconciliation_scope.md`): "recovered" mistura três tipos de
  impacto contratual diferentes (`strict_recovery`,
  `resource_adjusted_recovery`, `sla_relaxed_recovery`) - agregar os
  três sob uma única taxa de recuperação esconderia que alguns "sucessos"
  na verdade alteraram o contrato do intent (`duration_s`).
- **Overhead medido separadamente da simulação** (Fase J7): tempos de
  parede (`time.perf_counter()`) são inerentemente ruidosos (contenção
  de CPU, coleta de lixo do Python) - nenhuma conclusão de overhead
  desta fase deve ser lida como uma medição de laboratório controlada;
  são ordens de grandeza relativas, não valores absolutos precisos.
  "Abaixo de X%" refere-se à média por condição; a distribuição completa
  (incluindo outliers) está sempre em `results/figures/final/
  Figure_Overhead_Ratio.png`.
- **Prioridade declarada mas não aplicada** (Fase J8):
  `IntentPolicy.priority` existe no schema mas não influencia nenhuma
  decisão - confirmado por teste direto de código-fonte
  (`tests/unit/test_multi_intent_scope.py`), não apenas por inspeção.

## 3. Validade externa (os resultados generalizam além do que foi testado)

- **Amostra de topologias ainda pequena**: 5 formas no catálogo (Fase
  J4) - linear (0-4 repetidores), diamante heterogênea, malha 2x4,
  caminhos quase-equivalentes. Nenhuma topologia com mais de 8
  roteadores, nenhuma com conectividade clássica esparsa (a malha
  clássica completa é uma limitação estrutural de
  `NetworkTopologySpec`, não testável nesta versão). Toda alegação deste
  projeto deve se referir a "topologias de repetidores representativas
  avaliadas no SeQUeNCe" - nunca a "redes quânticas em geral".
- **Conectividade clássica sempre malha completa** - toda topologia
  testada usa uma malha clássica completa; nenhum resultado deste
  projeto se aplica a redes com conectividade clássica esparsa.
- **Um único formalismo quântico** (`ket_vector`, o padrão de
  `NetworkTopologySpec`) - nenhum resultado foi comparado contra o
  formalismo `density_matrix`.
- **Parâmetros físicos majoritariamente na faixa já calibrada em H1-H3**
  - `raw_fidelity` em torno de 0.85-0.9, atenuação entre 1e-6 e 0.03
  dB/m. Extrapolação para faixas muito diferentes não foi testada.
- **O achado "rota nativa entrega mais" é específico da topologia
  diamante avaliada** (`docs/routing_result_explanation.md`) - o menor
  caminho por distância coincidir com o menor caminho por perda não é
  uma propriedade geral de roteamento, é uma propriedade desta
  topologia; `small_mesh`/caminhos quase-equivalentes não mostram o
  mesmo efeito.

## 4. Validade de conclusão estatística (as conclusões estatísticas são defensáveis)

- **Seeds**: 20 como padrão (Fase J9, `docs/seed_justification.md`), com
  exceção documentada para cenários marginais/contagem-baixa que
  precisam de mais - qualquer campanha que use menos de 20 seeds sem
  justificativa explícita deve ser tratada como preliminar.
- **Efeito grande nem sempre precisa de muitas seeds, efeito marginal
  sempre precisa** (achado empírico da Fase J9, reconfirmado na Fase K2
  com a densificação de F03): a estabilidade de ranking do diamante já
  era clara em `n=5`; a taxa de satisfação de um cenário deliberadamente
  limítrofe ainda mudava entre `n=20` e `n=30` no piloto P00. Já a
  rejeição do planner acima do teto de uma rodada de purificação
  (Fase K2) é um degrau **determinístico** - 20 seeds em 4 limiares
  densos adicionais (0.73-0.745) bastaram para confirmá-lo com certeza,
  porque a variação entre seeds não afeta um resultado que é decidido
  antes da simulação rodar. Nenhuma regra fixa de "seeds suficientes" se
  aplica igualmente a toda métrica - depende de a métrica ter
  variabilidade genuína entre seeds ou ser determinística dado o
  cenário.
- **Comparações pareadas nunca incluem o próprio fator comparado na
  chave de pareamento** (achado da Fase H3,
  `aggregation.align_paired_trials`, reforçado na Fase J10,
  `statistical_analysis.compare_groups_pairwise`) - incluir o fator
  comparado na chave de pareamento (ex.: `parameter_hash` quando o fator
  comparado contribui para esse hash) quebra o pareamento silenciosamente
  (confirmado empiricamente, testado com um teste de regressão
  dedicado).
- **Correção de Holm aplicada por família de comparação, não
  globalmente** - uma campanha com múltiplas perguntas de pesquisa
  distintas (ex.: F02 e F03) tem suas próprias famílias de comparação;
  não há correção cruzada entre campanhas diferentes nesta versão.
- **Teste de normalidade das diferenças pareadas decide t-pareado vs.
  Wilcoxon automaticamente** (`statistical_analysis.paired_comparison`)
  - com `n` pequeno (< 3), o teste de Shapiro-Wilk não é executado e o
  t-pareado é usado por padrão; resultados com `n` muito pequeno devem
  ser interpretados com cautela adicional independentemente do teste
  escolhido.
- **Diferenças pareadas degeneradas (todas zero, ou pares com `NaN`)
  exigem tratamento explícito, não a saída padrão do `scipy`** (achado
  da Fase K2, `docs/results_provenance.md`): `scipy.stats.wilcoxon`
  retorna `nan` silenciosamente (não levanta exceção) para diferenças
  todas zero quando `n` é grande, e não tem uma noção nativa de "par
  ausente porque um lado nunca rodou" - `statistical_analysis.py` trata
  os dois casos explicitamente (`test_used="identical"`, descarte de
  pares com `NaN`) para nunca reportar `p≈0` espúrio nesses casos.

## O que este projeto explicitamente NÃO afirma

Ver `docs/multi_intent_scope.md`, `docs/future_work.md` e
`docs/core_contribution_statement.md`: nenhuma alegação de suporte a
concorrência real entre intents, prioridade operacional, justiça
(fairness), assurance online, reroteamento de reserva ativa, ou
qualquer item da lista de trabalhos futuros. Nenhuma alegação de
generalização a "redes quânticas em geral" - sempre "topologias de
repetidores representativas avaliadas no SeQUeNCe" (seção 3 acima).
