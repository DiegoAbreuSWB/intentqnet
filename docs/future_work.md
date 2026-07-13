# Trabalhos futuros

Itens explicitamente fora do escopo das Fases H/J - nenhum foi
implementado nesta versão, por decisão deliberada de escopo (não por
esquecimento). Ver a seção correspondente de cada item para o raciocínio
completo por trás da exclusão.

## Assurance online na mesma Timeline

SeQUeNCe não expõe reroteamento de uma reserva já ativa
(`Reservation.path` é fixado uma única vez -
`docs/sequence_code_analysis.md`, `docs/limitations.md`). Assurance
"online" (avaliar e reagir a violações **durante** a mesma `Timeline`,
não apenas entre episódios) exigiria instrumentar o próprio mecanismo de
reserva do SeQUeNCe - fora do princípio deste projeto de nunca modificar
o núcleo.

## Reroteamento de reserva ativa

Mesma limitação acima - `assurance.reconciliation.reconcile()` sempre
cria uma nova `Timeline`/`SequenceAdapter` (um novo episódio), nunca
modifica a reserva em andamento.

## Ajuste online de recursos

Análogo ao reroteamento: aumentar `reserved_memory_slots`/duração de uma
reserva **já aceita** pelo SeQUeNCe não é uma operação exposta pela API
de reserva - `assurance.reconciliation_policy.apply_reconciliation_decision`
(Fase J6) só ajusta recursos para um **novo** episódio, nunca em tempo
real durante o episódio 1.

## Número configurável de rodadas de purificação

`Reservation.purification_mode` só suporta `'until_target'`
(`docs/limitations.md`) - forçar um número específico de rodadas exigiria
construir `Rule`s manualmente, contornando `NetworkManager.request`.

## Múltiplos protocolos de purificação

Apenas `BBPSSWCircuit` (o único que `sequence.entanglement_management.
purification` disponibiliza no formalismo usado por este projeto) foi
usado - nenhuma comparação entre protocolos de purificação alternativos
foi implementada.

## Controle da ordem e estratégia de swapping

Ordem de swap fixa por bisseção binária
(`ResourceManager.generate_load_rules`) - `planning.swapping.
SwappingStrategy` documenta essa ordem, mas não a controla (ver
`docs/limitations.md`). Confirmado na Fase J1
(`docs/fidelity_estimation_model.md`) que a ordem de swap genuinamente
afeta o resultado real de fidelidade quando a topologia é heterogênea -
controlar essa ordem permitiria uma estratégia adicional de otimização,
não implementada aqui.

## Suporte completo a múltiplos intents concorrentes

Decisão formal da Fase J8 (`docs/multi_intent_scope.md`): Opção A (um
intent ativo por endpoint). Um `IntentApplicationDispatcher`
multiplexando várias intents por trás de um único app de
`QuantumRouter` foi considerado e descartado por exigir mapeamento
reserva->intent_id sem chave nativa, isolamento de evidência sob
contenção real de recursos, e testes extensivos de contenção - escopo
desproporcional para esta fase.

## Hardware heterogêneo físico completo

Este projeto varia parâmetros físicos (`raw_fidelity`,
`swapping_degradation`, `coherence_time_s`, atenuação, distância) por nó/
enlace, mas nunca modela hardware genuinamente diferente (memórias com
tecnologias distintas, protocolos de geração alternativos ao
Barrett-Kohler, etc.) - permanece no modelo físico que o SeQUeNCe já
implementa nativamente.

## Interpretação por linguagem natural / LLM

Restrição de escopo declarada desde o início do projeto: intents chegam
como objetos Python/JSON/YAML, nunca como texto em linguagem natural
interpretado por um LLM.

## Integração com testbed físico

Todo resultado deste projeto vem exclusivamente da simulação SeQUeNCe -
nenhuma integração com hardware quântico real foi implementada ou
planejada.

## Controle multidomínio

Todas as topologias deste projeto são de domínio administrativo único
(uma única `NetworkTopologySpec`, um único `IntentRepository`) - nenhum
mecanismo de negociação entre múltiplos domínios/operadores foi
implementado.

## Telemetria destrutiva mais realista

A telemetria de entrega (`assurance.telemetry.collect_intent_evidence`)
depende de `EventTypes.DELIVERY`, emitido apenas do lado iniciador da
reserva (`docs/limitations.md`) - um modelo mais completo de telemetria
(ex.: contabilizar decoerência/perda de memórias não entregues) não foi
implementado.

## Estimação online de fidelidade por amostragem

`planning.fidelity_estimation` (Fase J1) sempre estima fidelidade
analiticamente, antes de qualquer simulação - nenhum mecanismo de
reestimar a fidelidade a partir de amostras observadas durante a própria
execução (aprendizado online) foi implementado.
