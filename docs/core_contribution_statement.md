# Declaração da contribuição central (Fase K4)

## Contribuição principal

**Uma arquitetura que transporta para redes de distribuição de
entrelaçamento quântico os elementos centrais de Intent-Based
Networking** (declaração declarativa de objetivos, separação WHAT/HOW,
validação formal, tradução em plano de execução, implantação real,
observação vinculada ao intent, assurance por critérios declarados,
classificação SATISFIED/VIOLATED/REJECTED, e reconciliation após
violação) - implementada como composição sobre o SeQUeNCe (nunca
modificando seu núcleo) e validada empiricamente em 8 topologias/
campanhas finais com 20 seeds cada. Ver `docs/ibn_principles_mapping.md`
para o mapeamento princípio-a-princípio com evidência.

**Não é** um novo algoritmo de roteamento, purificação ou swapping - os
três algoritmos usados (`ShortestHopCountRouting`/`LeastLossRouting`/
`HighestFidelityRouting`, `PurifyUntilTarget`, a árvore de swap por
bisseção binária nativa do SeQUeNCe) já existiam ou são heurísticas
simples deliberadamente não-otimizadas. Eles aparecem no projeto como
**mecanismos para demonstrar a generalidade e o ciclo operacional da
arquitetura** (mostrar que o planner pode trocar de estratégia, que a
assurance detecta violação independente de qual estratégia causou, que
a reconciliation reage a diferentes categorias de violação) - nunca como
resultado a ser comparado contra o estado da arte em roteamento/
purificação quântica.

## Contribuições secundárias

- **`LinkFidelityEstimator` plugável** (`ConservativeMinEstimator`/
  `SequenceConsistentEstimator`) - reproduz analiticamente o mecanismo
  real de fidelidade do SeQUeNCe (árvore de swap por bisseção),
  permitindo separar "erro de estimativa do planner" de "física do
  sistema" (`docs/fidelity_estimation_model.md`).
- **Separação `reserved_memory_slots`/`min_delivered_pairs`** - dois
  conceitos que o projeto originalmente conflava
  (`docs/intent_resource_semantics.md`), com migração automática de
  intents no formato legado.
- **Metodologia de baselines** (nativo, estático, oracle) que isola
  quantitativamente o benefício de escolha de rota, de assurance, e de
  reconciliation, e o custo da própria abstração intent-based
  (`docs/baselines.md`, F01).
- **Matriz planner-vs-operação com categorias oracle-testadas** -
  distingue "rejeitado e nunca testado" de "rejeitado e confirmado
  correto" de "rejeitado mas na verdade satisfazível" - achado central:
  o planner conservador rejeita sistematicamente algo que o sistema real
  consegue entregar, com causa raiz identificada por código (uma rodada
  de purificação estimada vs. múltiplas rodadas reais -
  `docs/false_rejection_root_cause.md`).
- **Metodologia estatística pareada end-to-end** (alinhamento por seed
  excluindo o fator comparado, teste de normalidade automático,
  correção de Holm, effect size, tratamento explícito de casos
  degenerados) - `docs/final_experimental_design.md`, seção "Bugs
  encontrados".

## O que não é contribuição

- Os algoritmos de roteamento/purificação/swapping em si (já existentes
  ou heurísticas simples, não otimizados nem comparados contra o estado
  da arte).
- Qualquer resultado de desempenho absoluto de rede quântica (os números
  de `delivered_pairs`/fidelidade são específicos das topologias e
  parâmetros físicos avaliados, `docs/threats_to_validity.md`).
- Suporte a concorrência real entre múltiplos intents, prioridade
  operacional, ou fairness (`docs/multi_intent_scope.md`).
- Qualquer forma de assurance online (dentro da mesma `Timeline`) ou
  reroteamento de uma reserva já ativa (`docs/future_work.md`).
- Interpretação de linguagem natural / LLM para intents (restrição de
  escopo deste projeto desde o início).

## Claims permitidas

- "Esta arquitetura demonstra que os princípios de IBN se aplicam a
  redes de distribuição de entrelaçamento, com evidência experimental
  em N topologias de repetidores representativas avaliadas no
  SeQUeNCe."
- "A assurance detecta e classifica violações independentemente da
  causa; a reconciliation reage de forma diferenciada por categoria de
  violação, recuperando todos os casos de troca de rota e a maioria dos
  casos de ajuste de recurso nos cenários avaliados."
- "O overhead de orquestração da camada IBQN ficou abaixo de 0.31% do
  tempo total de trial nas condições avaliadas."
- "Identificamos e explicamos por código a causa raiz de uma classe de
  falso-negativo do planner de fidelidade (estimativa de uma única
  rodada de purificação vs. múltiplas rodadas reais do SeQUeNCe)."

## Claims que devem ser evitadas

- "Este projeto melhora o roteamento/a purificação/o swapping em redes
  quânticas" (não é o que foi feito - ver "o que não é contribuição").
- "Assurance melhora o resultado físico da rede" (assurance detecta e
  classifica; quem muda o resultado é a reconciliation, ver
  `docs/ibn_principles_mapping.md`, linhas 7 e 9).
- "`SequenceConsistentEstimator` prediz perfeitamente redes quânticas
  reais" (reproduz o modelo do SeQUeNCe nas configurações avaliadas,
  `docs/fidelity_estimation_model.md`).
- "Overhead desprezível" sem qualificação de escopo (sempre "abaixo de
  X% no ambiente de simulação avaliado", `docs/overhead_methodology.md`).
- "Reconciliation recupera 100% dos intents" (recupera classes
  específicas de violação; falha sob perda severa;
  `docs/reconciliation_scope.md`).
- Qualquer alegação sobre "redes quânticas em geral" - sempre "topologias
  de repetidores representativas avaliadas no SeQUeNCe"
  (`docs/threats_to_validity.md`).
- Qualquer alegação de suporte a concorrência real entre intents,
  assurance online, ou reroteamento de reserva ativa (não implementados
  - `docs/future_work.md`, `docs/multi_intent_scope.md`).
