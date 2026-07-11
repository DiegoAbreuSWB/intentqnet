# Design do Assurance (Etapa G)

Este documento antecede a implementação (conforme exigido) e registra o que
foi verificado por leitura de código e execução real antes de qualquer linha
de `src/ibqn/assurance/` ser escrita. Três descobertas abaixo mudaram o
design em relação ao que uma leitura superficial do código sugeriria — todas
confirmadas por scripts de investigação reproduzíveis antes de virarem
código de produção.

## 1. Quais evidências são realmente fornecidas pelo SeQUeNCe

| Evidência | Fonte real | Observação |
|---|---|---|
| Par entregue (fim a fim) | `IntentRequestApp.get_memory` (nosso subclass de `RequestApp`) → `metrics.record(EventTypes.DELIVERY, ...)` | **Não** é um evento nativo do núcleo — o núcleo define `EventTypes.DELIVERY` mas nunca o dispara (auditoria, §4.7); é a própria aplicação que precisa reconhecer e reportar a entrega |
| Fidelidade de um par entregue | `MemoryInfo.fidelity` no momento da entrega, capturada **antes** de `RequestApp.get_memory` resetar a memória (ver achado crítico #2 abaixo) | Nunca a fidelidade "solicitada" no intent — sempre a observada na `MemoryInfo` real |
| Aprovação/rejeição de reserva | `IntentRequestApp.get_reservation_result(reservation, bool)` | Só o **iniciador** recebe este callback (auditoria, §4.2) |
| Caminho realmente usado | `Reservation.path` (populado pelo RSVP durante o handshake) | Pode divergir do `ExecutionPlan.route` apenas se `execution.compiler.apply_route` não tiver sido aplicado (Etapa E já garante isso) |
| Contadores globais de geração/purificação/swapping | `sequence.utils.metrics.get_counter("eg"|"ep"|"es")`, chaveados por `owner_name` (o nó que executa a ação) | **Nunca** carregam `intent_id` — ver achado crítico #3 abaixo |
| Timestamp de um evento | `record["sim_time"]`, populado automaticamente por `metrics.record()` a partir do `Timeline` corrente | Em picossegundos internamente; convertido para segundos na evidência |

## 2. Achado crítico: pares purificados nunca eram contados (bug corrigido)

`RequestApp.get_memory` (`sequence/app/request_app.py:133`) começa com
`if info.state != "ENTANGLED": return`. Um par que passa por purificação
bem-sucedida termina no estado `"PURIFIED"`, não `"ENTANGLED"`
(`MemoryInfo.to_purified()` popula os mesmos campos `remote_node`/
`fidelity`/`index` que `to_entangled()` — auditoria, §4.5) — portanto o
`RequestApp` padrão **nunca** conta, nunca reseta para `RAW`, e nunca reporta
como entregue um par purificado.

Confirmado empiricamente antes da correção: um cenário forçando purificação
(fidelidade bruta 0.85, alvo 0.72) produziu 318 eventos `EP_SUCCESS`
enquanto `memory_counter` permaneceu em **0** durante toda a simulação.
Corrigido em `IntentRequestApp.get_memory`
(`src/ibqn/execution/sequence_executor.py`): o estado `"PURIFIED"` agora é
tratado por `_count_purified_delivery`, que espelha deliberadamente a mesma
lógica de casamento/contagem/reset que `RequestApp.get_memory` já aplica a
`"ENTANGLED"` — não há como reaproveitar o método original sem duplicar essas
poucas linhas, já que ele descarta o estado `"PURIFIED"` antes de qualquer
outra checagem. Após a correção, o mesmo cenário produziu 318 eventos
`DELIVERY`, em correspondência 1:1 com `EP_SUCCESS`.

## 3. Achado crítico: métricas globais não isolam por intent

Confirmado com dois intents concorrentes (`leaf1→leaf2` e `leaf3→leaf4`)
compartilhando `center` como nó interior de swap: os 244 eventos
`ES_SUCCESS` registrados em `center` **não têm campo `intent_id`** — são a
soma indistinta da atividade de swap de ambos os intents
(`sequence/entanglement_management/swapping/*.py` chama
`metrics.record(EventTypes.ES_SUCCESS, self.owner.name, ...)`, nunca com
qualquer identificador de intent). Já os 124 + 119 eventos `DELIVERY`
apareceram corretamente separados por `intent_id` (só porque **nós**
adicionamos essa tag em `IntentRequestApp.get_memory`).

**Consequência de design**: `assurance.telemetry.collect_intent_evidence`
usa **exclusivamente** eventos `DELIVERY` filtrados por `intent_id` como
prova de entrega/fidelidade de um intent específico. Contadores globais
(`eg`/`ep`/`es`) são expostos separadamente como `global_simulation_counters`
— diagnóstico da simulação como um todo, nunca usados para decidir
`satisfied`/`violated` de um intent.

## 4. Achado crítico: um nó só pode hospedar o app de um intent por vez

Ao testar dois intents onde um nó era origem de um e destino de outro
(`leaf1→leaf2` e `leaf3→leaf1`), o segundo `IntentRequestApp` construído
sobre `leaf1` **sobrescreveu silenciosamente** `leaf1.app` (via
`QuantumRouter.set_app`, auditoria §4.6). O resultado observado foi um
`InvalidTransitionError`: a aprovação da reserva do primeiro intent foi
entregue ao app do segundo intent, que tentou transicionar `intent-B` de
`ACTIVE` para `ACTIVE` novamente — ou seja, o vínculo reserva→intent
**quebra silenciosamente** quando dois intents compartilham um nó como
origem/destino, misturando o `intent_id` das transições.

Corrigido com uma guarda explícita em
`SequenceExecutor._check_no_node_conflict`: agora um `ValueError` claro é
levantado *antes* de qualquer app ser sobrescrito, em vez de deixar o
`intent_id` errado se propagar silenciosamente pelas transições de ciclo de
vida. Isso está documentado como limitação (não solucionada, apenas
detectada) em `docs/limitations.md`.

## 5. Como cada reserva é vinculada ao seu intent

Não existe (nem poderia existir sem modificar o núcleo) um campo `intent_id`
no objeto `Reservation` do SeQUeNCe. O vínculo é inteiramente da nossa
camada: `SequenceExecutor._start_reservation` cria um `IntentRequestApp`
**dedicado** (carregando `self.intent_id`) por nó de origem/destino, e o
guard do item 4 garante que essa dedicação nunca seja violada. Toda
mensagem de callback que o `IntentRequestApp` recebe (`get_reservation_result`,
`get_memory`) necessariamente pertence à única reserva que ele mesmo
iniciou/aceitou — o vínculo é por constução do objeto, não por inspeção do
conteúdo da mensagem.

## 6. Como um par fim a fim entregue é identificado (sem `entangle_time > 0`)

Critério usado: `MemoryInfo.state in {"ENTANGLED", "PURIFIED"}` **e**
casamento de reserva confirmado pela própria lógica de
`RequestApp.get_memory`/`_count_purified_delivery` (índice de memória
mapeado para a reserva via `memo_to_reservation`, `remote_node` igual ao
respondente, fidelidade observada ≥ fidelidade da reserva). `entangle_time`
não é usado como critério — ele só indica que a memória *já esteve*
entrelaçada em algum momento, não que a entrega foi *confirmada* para esta
reserva especificamente (uma memória pode reportar `entangle_time > 0` e
ainda assim estar, no momento da inspeção, em qualquer estado, inclusive
`RAW` após reciclagem).

### Deduplicação

Cada entrega genuína incrementa `IntentRequestApp._delivered_pairs` (contador
monotônico local ao app) **antes** de `metrics.record(DELIVERY, ...,
pair_number=...)` ser chamado — logo, cada `pair_number` é único por
`intent_id` por construção. `assurance.telemetry.collect_intent_evidence`
ainda assim deduplica defensivamente por `(intent_id, pair_number)` ao
montar a evidência (registrando um aviso caso alguma duplicata apareça),
em vez de simplesmente confiar que isso nunca pode acontecer.

## 7. Como throughput, fidelidade, latência e quantidade de pares são calculados

Todos a partir exclusivamente dos eventos `DELIVERY` do próprio `intent_id`
(nunca de contadores globais, nunca de valores solicitados no intent):

| Métrica | Cálculo | Fonte |
|---|---|---|
| `delivered_pairs` | `len(evidence.delivered_pairs)` | contagem de eventos `DELIVERY` deduplicados |
| `average_fidelity` | média de `fidelity` sobre `evidence.delivered_pairs` | idem |
| `min_fidelity` (observado) | mínimo de `fidelity` sobre `evidence.delivered_pairs` | idem |
| `throughput` | `delivered_pairs / intent.requirements.duration` | mesma definição usada por `RequestApp.get_throughput()` (pares por segundo, sobre a janela **solicitada**, não sobre o tempo até a última entrega) |
| `completion_time` | `sim_time` (em segundos, relativo a `intent.requirements.start_time`) do evento `DELIVERY` de número `requested_pairs`, ou indisponível (`None`) se menos pares que o solicitado foram entregues | mesmo conceito de `sequence.utils.metrics.DeliveryTimeMetric`, recalculado aqui filtrando por `intent_id` em vez de `owner_name` |

**Latência por par não é calculada.** Não existe, no SeQUeNCe, um
identificador que amarre uma tentativa de geração elementar específica ao
par fim a fim que eventualmente a consome (via swap e/ou purificação) — não
há como reconstruir "quanto tempo este par específico levou para ser
produzido" a partir da telemetria disponível sem inventar uma aproximação
não rastreável. `max_latency` continua sendo usado pelo *planner*
(estimativa a priori, `planning/feasibility.py`), mas não é reavaliado pelo
assurance como uma condição de sucesso mensurável — se um cenário declarar
uma `success_condition` para uma métrica não suportada (fora de
`delivered_pairs`, `average_fidelity`, `min_fidelity`, `throughput`,
`completion_time`), `assurance.evaluator` levanta `UnsupportedMetricError`
em vez de silenciosamente inventar um valor.

## 8. Interpretação das condições do YAML (sem `eval()`)

`SuccessCondition.operator` já é um `Literal[">=","<=",">","<","==","!="]`
validado pelo pydantic desde a Fase 3 (`intent/models.py`). O avaliador mapeia
esses seis operadores diretamente para funções do módulo padrão `operator`
(`operator.ge`, `operator.le`, `operator.gt`, `operator.lt`, `operator.eq`,
`operator.ne`) — nenhuma string é executada como código Python.

## 9. Transições de ciclo de vida

```
ACTIVE --(todas as success_conditions passam)--> SATISFIED
ACTIVE --(alguma condição falha)--> VIOLATED
VIOLATED --(reconciliation tentada)--> RECONCILING --> PLANNING --> ... --> ACTIVE --> SATISFIED | VIOLATED
PLANNING --(nenhuma rota viável no replanejamento)--> REJECTED
```

`run_scenario` agora força essa avaliação para **todo** intent que chegou a
`ACTIVE` ao final da simulação — nenhum intent termina mais em `ACTIVE` com
`satisfied=None`. Intents que nunca saíram de `PLANNING`/`DEPLOYING`
(rejeitados ou com reserva recusada) mantêm `REJECTED`/`FAILED` sem
avaliação de condições (não há evidência de entrega para julgar).

## 10. Reconciliation entre episódios

Confirmado na Fase 1 (auditoria, §4.7) e reforçado aqui: o SeQUeNCe não
permite reroteamento de uma reserva ativa. `assurance.reconciliation.reconcile`
portanto:

1. transiciona o intent (no `IntentRepository` **original**, preservando o
   histórico) de `VIOLATED` → `RECONCILING` → `PLANNING`;
2. constrói uma `NetworkCapabilities`/`IntentPlanner` **novos** e replaneja o
   mesmo intent, opcionalmente com estratégias diferentes;
3. constrói um `SequenceAdapter`/`Timeline` **inteiramente novo** (novo
   episódio — mesma topologia, tempo de simulação reiniciado em zero) e um
   novo `SequenceExecutor` apontando para o `IntentRepository` original;
4. usa `SequenceExecutor.redeploy` (não `deploy`) para continuar o ciclo de
   vida do mesmo intent em vez de reiniciá-lo;
5. roda a nova simulação, coleta evidência e avalia novamente, transicionando
   para `SATISFIED`/`VIOLATED`/`REJECTED` conforme o resultado.

## 11. Limitações que permanecem

- Nenhuma estimativa de latência por par (item 7).
- Métricas globais (`eg`/`ep`/`es`) continuam sem isolamento por intent no
  próprio SeQUeNCe — nossa camada só consegue contornar isso para o que
  **nós mesmos** instrumentamos (`DELIVERY`).
- Um nó não pode hospedar apps de dois intents diferentes simultaneamente
  (detectado e barrado explicitamente, não resolvido).
- `throughput`/`completion_time` calculados aqui não coincidem
  necessariamente com `sequence.utils.metrics.collect_trial_metrics(...)`
  quando múltiplos intents compartilham um nó — são cálculos independentes,
  por design (ver item 3).
- Reconciliation nesta versão só tenta **uma vez** com uma estratégia
  alternativa fornecida pelo chamador; não há busca automática entre várias
  estratégias/rotas até encontrar uma que satisfaça o intent.
