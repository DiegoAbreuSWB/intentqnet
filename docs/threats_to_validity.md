# Ameaças à validade (Fase J10/J12)

Consolidação das limitações metodológicas já documentadas ao longo do
projeto (`docs/limitations.md`, `docs/campaign_architecture.md`,
`docs/seed_justification.md`, etc.) na estrutura padrão de ameaças à
validade - para que a seção de metodologia do artigo tenha um único
lugar que enumere o que pode e o que não pode ser concluído a partir dos
dados deste projeto.

## Validade interna (o efeito observado é mesmo causado pelo que dizemos)

- **Contaminação de métricas entre episódios** (encontrado e corrigido
  na Fase H3): `assurance.reconciliation.reconcile()` não resetava
  `sequence.utils.metrics` antes do episódio 2, misturando evidência do
  episódio 1 na do episódio 2 por colisão de `pair_number`. Corrigido
  com um teste de regressão dedicado
  (`tests/integration/test_reconciliation.py`).
- **Roteamento nativo do SeQUeNCe não é o que a documentação original
  deste projeto afirmava** (achado da Fase J3): a tabela de roteamento
  estática auto-gerada pondera por distância física, não por número de
  saltos - a baseline "Native SeQUeNCe" não é diretamente comparável a
  `ShortestHopCountRouting` como se pensava antes de medir.
- **A ordem de swap afeta o resultado real de fidelidade em topologias
  heterogêneas** (achado da Fase J1) - a suposição original de que
  "multiplicação é associativa, ordem não importa" só vale para o
  estimador conservador, não para o mecanismo real do SeQUeNCe. Qualquer
  conclusão sobre fidelidade em topologias heterogêneas deve declarar
  qual estimador foi usado.

## Validade externa (os resultados generalizam além do que foi testado)

- **Amostra de topologias ainda pequena**: 5 formas no catálogo (Fase
  J4) - linear (0-4 repetidores), diamante heterogênea, malha 2x4,
  caminhos quase-equivalentes. Nenhuma topologia com mais de 8
  roteadores, nenhuma com conectividade clássica esparsa (a malha
  clássica completa é uma limitação estrutural de
  `NetworkTopologySpec`, não testável nesta versão).
- **Conectividade clássica sempre malha completa** - toda topologia
  testada usa uma malha clássica completa; nenhum resultado deste
  projeto se aplica a redes com conectividade clássica esparsa.
- **Um único formalismo quântico** (`ket_vector`, o padrão de
  `NetworkTopologySpec`) - nenhum resultado foi comparado contra o
  formalismo `density_matrix`.
- **Parâmetros físicos majoritariamente na faixa já calibrada em H1-H3**
  - `raw_fidelity` em torno de 0.85-0.9, atenuação entre 1e-6 e 0.03
  dB/m. Extrapolação para faixas muito diferentes não foi testada.

## Validade de construto (as métricas medem o que dizem medir)

- **`reserved_memory_slots` vs. `min_delivered_pairs`** (Fase J2): antes
  da separação, `requested_pairs` conflava recurso reservado com meta de
  entrega - qualquer conclusão de trabalho anterior a essa correção que
  usasse "requested_pairs" precisa ser reinterpretada à luz de qual dos
  dois conceitos realmente se aplicava.
- **`ConservativeMinEstimator` vs. `SequenceConsistentEstimator`** (Fase
  J1): a estimativa de fidelidade pré-simulação depende de qual
  estimador está ativo - "erro de previsão do planner" não é uma
  constante única deste sistema, é uma propriedade do par
  (estimador, topologia).
- **Overhead medido separadamente da simulação** (Fase J7): tempos de
  parede (`time.perf_counter()`) são inerentemente ruidosos (contenção
  de CPU, coleta de lixo do Python) - nenhuma conclusão de overhead
  desta fase deve ser lida como uma medição de laboratório controlada;
  são ordens de grandeza relativas, não valores absolutos precisos.
- **Prioridade declarada mas não aplicada** (Fase J8):
  `IntentPolicy.priority` existe no schema mas não influencia nenhuma
  decisão - confirmado por teste direto de código-fonte
  (`tests/unit/test_multi_intent_scope.py`), não apenas por inspeção.

## Validade de conclusão estatística (as conclusões estatísticas são
defensáveis)

- **Seeds**: 20 como padrão (Fase J9, `docs/seed_justification.md`), com
  exceção documentada para cenários marginais/contagem-baixa que
  precisam de mais - qualquer campanha que use menos de 20 seeds sem
  justificativa explícita deve ser tratada como preliminar.
- **Comparações pareadas nunca incluem o próprio fator comparado na
  chave de pareamento** (achado da Fase H3,
  `aggregation.align_paired_trials`, reforçado na Fase J10,
  `statistical_analysis.compare_groups_pairwise`) - includir o fator
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
- **Efeito grande nem sempre precisa de muitas seeds, efeito marginal
  sempre precisa** (achado empírico da Fase J9): a estabilidade de
  ranking do diamante já era clara em `n=5`; a taxa de satisfação de um
  cenário deliberadamente limítrofe ainda mudava entre `n=20` e `n=30`.
  Nenhuma regra fixa de "seeds suficientes" se aplica igualmente a toda
  métrica.

## O que este projeto explicitamente NÃO afirma

Ver `docs/multi_intent_scope.md` e `docs/future_work.md`: nenhuma
alegação de suporte a concorrência real entre intents, prioridade
operacional, justiça (fairness), ou qualquer item da lista de trabalhos
futuros.
