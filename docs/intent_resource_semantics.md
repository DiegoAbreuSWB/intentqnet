# Semântica de recursos e entrega no intent (Fase J2)

## O problema

Até a Fase H3, `IntentRequirements.requested_pairs` era usado para duas
coisas ao mesmo tempo:

1. o tamanho do pool de memórias reservado em cada nó da rota
   (`planning.resource_allocation.build_reservations`, e por baixo,
   `RSVPProtocol.schedule`);
2. o valor implícito de "quantos pares contam como sucesso" em vários
   lugares (`assurance.evaluator._completion_time`,
   `experiments.runner._delivery_metrics`'s antiga fórmula de
   `excess_delivery_pairs`/`delivery_ratio`).

Como as memórias são recicladas durante a janela da reserva (ver
`docs/metrics.md`), `delivered_pairs` rotineiramente excede
`requested_pairs` por uma ordem de grandeza - o que é o comportamento
correto do SeQUeNCe, mas o nome único fazia esse resultado parecer um bug
de contagem em vez da consequência esperada de reuso de memória.

## A separação

`IntentRequirements` (`src/ibqn/intent/models.py`) agora declara os dois
conceitos com nomes distintos:

| Campo | Significado | Obrigatório |
|---|---|---|
| `reserved_memory_slots` | tamanho do pool de memórias entregue ao `RSVPProtocol.schedule` - um **recurso** | sim |
| `min_delivered_pairs` | meta de entrega em nível de serviço, usada para `delivery_ratio`/`excess_delivery_pairs` | não (`None` por padrão) |
| `start_time_s` / `duration_s` | janela da reserva, em segundos | sim |

Deliberadamente **não** foram criados três modelos Pydantic separados
(`requirements`/`resources`/`time`, como o texto original do prompt
sugere como exemplo) - a ambiguidade real estava nos *nomes dos campos*,
não em qual sub-objeto YAML os contém. Um único `IntentRequirements` com
nomes de campo inequívocos atinge a mesma separação conceitual com uma
superfície de mudança muito menor (ver "Compatibilidade" abaixo). O
parser (`intent.parser._merge_resources_and_time_blocks`) ainda aceita a
forma literal do prompt (blocos `resources:`/`time:` como irmãos de
`requirements:` no YAML) por completude, dobrando-os em `requirements`
antes da validação.

`min_delivered_pairs` fica `None` a menos que o intent o declare
explicitamente - **nunca** é inferido de `reserved_memory_slots` nem de
`validation.success_conditions`. Intents que só declaram
`success_conditions: {delivered_pairs: ">= N"}` continuam funcionando
exatamente como antes: esse mecanismo (`assurance.evaluator`) é
independente e não foi alterado.

## Compatibilidade com intents antigos

`IntentRequirements` tem um `model_validator(mode="before")` que aceita os
nomes antigos (`requested_pairs`, `start_time`, `duration`) e os migra
para os novos (`reserved_memory_slots`, `start_time_s`, `duration_s`)
antes da validação de campos - com log explícito por campo migrado. Isso
vale tanto para construção direta em Python
(`IntentRequirements(requested_pairs=10, ...)`) quanto para YAML/JSON
carregado via `intent.parser`. Por isso:

- nenhum dos 18 notebooks de H1/H2 precisou ser alterado - todos
  constroem intents com os nomes antigos, que continuam funcionando;
- `demos.intents.simple_intent`/`diamond_intent` mantêm seus parâmetros
  Python (`requested_pairs=`, `start_time=`, `duration=`) inalterados -
  são apenas nomes de kwargs de uma função auxiliar, não o schema
  persistido;
- os arquivos `configs/campaigns/intents/*.yaml` foram atualizados para o
  novo schema explicitamente (ver abaixo), como demonstração real de uso,
  não apenas por necessidade.

Um valor antigo e um novo conflitantes (`requested_pairs=10,
reserved_memory_slots=5`) são rejeitados com `ValueError` - nunca
resolvidos silenciosamente escolhendo um dos dois.

## Novas métricas

Ver `docs/metrics.md` para as fórmulas de `excess_delivery_pairs`/
`delivery_ratio`/`deliveries_per_reserved_slot` e por que
`delivered_pairs` nunca é truncado.

`TrialRecord` (`experiments/records.py`) agora carrega ambos os campos
(`reserved_memory_slots`, `min_delivered_pairs`) explicitamente - nenhuma
tabela/figura desta arquitetura usa mais um campo `requested_pairs`
ambíguo.

## Campanhas C01-C04 (Fase H3)

Os dois intents reais usados nas quatro campanhas de validação
(`configs/campaigns/intents/diamond_intent.yaml`,
`three_node_intent.yaml`) foram migrados para o novo schema
explicitamente, com `min_delivered_pairs` igual ao limiar já declarado em
`validation.success_conditions.delivered_pairs` (10 em ambos) - isso não é
uma inferência automática: é uma decisão deliberada de espelhar um valor
que já existia, explícito, em outro campo do mesmo YAML. `trial_id` muda
para todos os trials dessas campanhas nesta fase (a string de
`TrialIdentity.strategy` agora inclui o nome do `fidelity_estimator`, Fase
J1) - as quatro campanhas foram reexecutadas do zero.

## O que NÃO mudou

- `validation.success_conditions` continua sendo a única fonte de verdade
  para SATISFIED/VIOLATED - `min_delivered_pairs` é puramente informativo/
  de relatório, nunca usado por `assurance.evaluator` para decidir
  sucesso.
- `planning.resource_allocation.build_reservations` continua reservando
  `reserved_memory_slots` (endpoints) / `reserved_memory_slots * 2`
  (interiores) - comportamento inalterado, só o nome do parâmetro mudou.
