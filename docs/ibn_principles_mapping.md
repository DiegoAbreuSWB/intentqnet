# Mapeamento de princípios de Intent-Based Networking (Fase K4)

Mapeia cada princípio clássico de IBN à sua implementação concreta neste
projeto, à evidência experimental que o sustenta, e à limitação atual -
para deixar inequívoco que a contribuição central é a arquitetura
intent-based aplicada a redes de distribuição de entrelaçamento, não
qualquer algoritmo isolado de roteamento/purificação/swapping (ver
`docs/core_contribution_statement.md`).

| # | Princípio IBN | Implementação | Evidência experimental | Limitação atual |
|---|---|---|---|---|
| 1 | Declaração declarativa de objetivos | `intent.models.EntanglementIntent` - usuário declara `min_fidelity`/`reserved_memory_slots`/`min_delivered_pairs`/`duration_s`, nunca uma rota ou protocolo | Todas as campanhas F01-F08 constroem intents declarativamente; `docs/intent_resource_semantics.md` | Vocabulário de requisitos ainda limitado a fidelidade/entrega/tempo - sem QoS mais rico (prioridade declarada mas não usada, ver linha 8) |
| 2 | Separação WHAT vs. HOW | `intent.requirements` (WHAT) vs. `planning.planner.IntentPlanner` + `ExecutionPlan` (HOW: rota, política de purificação, estimador) | F02: o MESMO intent (WHAT) produz `delivered_pairs` de 7.85 a 446.10 dependendo só do HOW (estratégia de roteamento) - `docs/routing_result_explanation.md` | Nem toda dimensão de HOW é controlável pelo usuário - ordem de swap e número de rounds de purificação são fixos pelo SeQUeNCe (`docs/future_work.md`) |
| 3 | Validação formal do intent | Validação Pydantic (`EntanglementIntent.model_validate`), migração de campos legados (`_migrate_legacy_field_names`) | `docs/intent_resource_semantics.md`; F06 mede `intent_validation_wall_time_s` separadamente de parsing | Validação é de schema/tipos, não de viabilidade física - viabilidade é responsabilidade do planner (linha 4), uma separação de responsabilidades deliberada |
| 4 | Tradução em plano de execução | `IntentPlanner.plan(intent) -> ExecutionPlan` (rota, `fidelity_estimator`, `purification_strategy`) | F02/F03/F07 exercitam esta tradução em 3 topologias; `docs/fidelity_estimation_model.md` | Heurística, não um otimizador - escolhe entre um conjunto fixo de estratégias, não busca no espaço de todas as rotas/políticas possíveis |
| 5 | Implantação real na rede | `execution.sequence_executor.SequenceExecutor.deploy()` - reserva real via `NetworkManager.request()` do SeQUeNCe | Toda campanha; F01's `native_sequence` vs. condições IBQN confirmam que a MESMA infraestrutura de reserva do SeQUeNCe é usada em ambos os casos | Nenhuma - implantação sempre passa pelo mecanismo real do SeQUeNCe, nunca simulada/mockada (princípio do projeto desde a Fase H) |
| 6 | Observação vinculada ao intent | `assurance.telemetry.collect_intent_evidence` - eventos `DELIVERY` do SeQUeNCe filtrados por `intent_id` | `docs/assurance_design.md`; toda campanha final coleta evidência real, nunca fabricada | Telemetria só do lado iniciador da reserva (`EventTypes.DELIVERY` é assimétrico) - telemetria destrutiva mais completa é trabalho futuro |
| 7 | Assurance baseado em critérios declarados | `assurance.evaluator.evaluate_intent` - avalia exatamente `intent.validation.success_conditions`, nunca um critério genérico | F01 isola o valor da assurance: `ibqn_without_assurance` aceita 100% das reservas mas não mede satisfação nenhuma - `docs/final_experimental_design.md` | Assurance só avalia ao FINAL de um episódio (depois que `Timeline.run()` termina) - nunca online, durante a mesma simulação (`docs/future_work.md`) |
| 8 | Classificação SATISFIED/VIOLATED/REJECTED | `intent.models.IntentStatus`; estendida por `experiments.planner_operation_matrix` (REJECTED untested/oracle-satisfiable/oracle-infeasible) | `Figure_AssuranceOutcomes.png` (F02+F03): os três estados surgem naturalmente, sem serem forçados; `Figure_PlannerOperation_Matrix.png` | `EXECUTION_FAILED` (reserva aceita pelo planner mas recusada pelo SeQUeNCe) nunca foi observado empiricamente - não é uma garantia estrutural, só uma observação |
| 9 | Reconciliation após violação | `assurance.reconciliation.reconcile()` + `assurance.reconciliation_policy.decide_reconciliation_action` | F05: 5 classes de cenário, recuperou todos os casos de troca de rota e a maioria dos casos de ajuste de recurso; falhou sob perda severa; evitou agir corretamente num teto de fidelidade - `docs/reconciliation_scope.md` | Uma única tentativa, sem busca automática do ajuste mínimo suficiente (multiplicador fixo 2x); nunca reroteia uma reserva ATIVA, sempre cria um novo episódio (`docs/future_work.md`) |

## O que este mapeamento não afirma

Nenhuma linha acima implica suporte a concorrência real entre múltiplos
intents simultâneos (Opção A, `docs/multi_intent_scope.md`), assurance
online dentro da mesma `Timeline`, ou reroteamento de uma reserva já
ativa - esses permanecem em `docs/future_work.md`, nunca implementados
nem simulados neste projeto.
