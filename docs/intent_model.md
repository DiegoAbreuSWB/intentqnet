# Modelo de Intent

Este documento descreve o modelo de dados de `src/ibqn/intent/` — a representação
declarativa do que uma aplicação deseja, sem especificar como a rede deve entregar.

## Esquema

```yaml
intent:
  id: intent-001
  service: entanglement_distribution   # único valor suportado nesta v1

  endpoints:
    source: node_a
    destination: node_b

  requirements:
    min_fidelity: 0.90        # adimensional, em [0, 1]
    min_throughput: 10        # pares entrelaçados por segundo
    max_latency: 0.5          # segundos, orçamento de latência fim-a-fim por par
    min_delivered_pairs: 100  # opcional: meta de pares entregues
    reserved_memory_slots: 10 # orçamento: memórias reservadas por par de nós
    start_time_s: 0           # segundos, relativo ao início do cenário/simulação
    duration_s: 10            # orçamento: duração da janela de reserva, em segundos

  policy:
    priority: normal          # low | normal | high
    allow_rerouting: true     # a reconciliação pode mudar a rota num novo episódio
    allow_purification: true  # a rede pode purificar
    allow_multiple_paths: false
    max_resource_scale: 1.0   # quanto um novo episódio pode ampliar o orçamento (1 = nunca)

  validation:
    metrics:
      - delivered_pairs
      - average_fidelity
      - throughput
      - completion_time
    success_conditions:
      delivered_pairs: ">= 100"
      average_fidelity: ">= 0.90"
      throughput: ">= 10"
```

Os nomes antigos `requested_pairs`, `start_time` e `duration` continuam aceitos na
entrada e são migrados para `reserved_memory_slots`, `start_time_s` e `duration_s`
(`docs/intent_resource_semantics.md`).

**Orçamento e permissões.** `reserved_memory_slots` e `duration_s` são o orçamento de
recursos que o intent concede à rede: o planejamento reserva exatamente esse orçamento
na rota escolhida e verifica se ele basta. A política diz o que a rede pode fazer além
disso: `allow_purification` decide se alguma purificação é executada;
`allow_rerouting`, se a reconciliação pode levar o intent a outra rota num novo
episódio; `max_resource_scale`, até quanto esse episódio pode ampliar memórias e
duração (o padrão, 1, não permite ampliar). A reconciliação só escolhe alavancas
permitidas e recusa um episódio acima do orçamento (`assurance.reconciliation_policy`,
`docs/reconciliation_scope.md`).

Todos os campos de tempo (`start_time`, `duration`, `max_latency`) são expressos em
**segundos** na camada de intent, independentemente da convenção interna de
picossegundos do `Timeline` do SeQUeNCe — a conversão de unidades é responsabilidade
exclusiva do futuro `network.sequence_adapter` (Etapa D), nunca destes modelos.

## Classes (`src/ibqn/intent/models.py`)

| Classe | Papel |
|---|---|
| `IntentEndpoints` | origem/destino; valida `source != destination` |
| `IntentRequirements` | requisitos mensuráveis, cada campo com unidade documentada |
| `IntentPolicy` | permissões (não instruções) para a rede — prioridade e o que ela pode fazer |
| `SuccessCondition` | uma condição mensurável (`metric operator expected`); `SuccessCondition.parse("fid", ">= 0.9")` converte a notação do YAML |
| `IntentValidation` | métricas a observar + condições de sucesso; valida que toda condição referencia uma métrica declarada |
| `EntanglementIntent` | o intent completo |
| `IntentStatus` | enum com os 13 estados do ciclo de vida |
| `IntentResult` | resumo do estado terminal (o detalhamento por condição fica em `assurance.evaluator.IntentEvaluation`) |

Todos os modelos são `pydantic.BaseModel` com `frozen=True` — um intent, uma vez
validado, é imutável; qualquer "alteração" é sempre a criação de um novo objeto
(a mesma decisão vale para `StatusTransition` no módulo de lifecycle).

## Parser (`src/ibqn/intent/parser.py`)

`parse_intent_dict`/`parse_intent_yaml`/`parse_intent_json`/`load_intent_file` aceitam
tanto um mapeamento já "achatado" (objeto Python) quanto o formato com chave raiz
`intent:` usado nos arquivos de exemplo. Nenhuma interpretação de linguagem natural é
realizada — conforme a restrição da v1, o intent chega pronto como dict/YAML/JSON.

## Ciclo de vida (`src/ibqn/intent/lifecycle.py`)

```
RECEIVED → VALIDATED → PLANNING → PLANNED → DEPLOYING → ACTIVE → SATISFIED → COMPLETED
              ↘ REJECTED         ↘ REJECTED         ↘ FAILED       ↘ VIOLATED
                                                                       ↘ RECONCILING → PLANNING (novo plano)
                                                                                    ↘ FAILED
(qualquer estado não-terminal) → CANCELLED
```

Estados terminais (não permitem mais transições): `REJECTED`, `FAILED`, `COMPLETED`,
`CANCELLED`. Toda transição é validada contra o grafo `ALLOWED_TRANSITIONS`, recebe um
`reason` obrigatório e um `sim_time` opcional (tempo de simulação, em segundos), e é
apensada ao histórico imutável (`IntentLifecycle.history: list[StatusTransition]`) —
nunca sobrescrita. `IntentLifecycle.transition(...)` lança `InvalidTransitionError` para
qualquer aresta não permitida, incluindo qualquer tentativa a partir de um estado
terminal.

`IntentRepository` (`src/ibqn/intent/repository.py`) associa cada `EntanglementIntent`
ao seu `IntentLifecycle` e, ao atingir um estado terminal, popula um `IntentResult`
automaticamente. É deliberadamente em memória nesta v1 — cada execução de experimento
cria seu próprio repositório, para preservar a reprodutibilidade por seed (ver
`docs/experimental_methodology.md`, a ser escrito na Etapa F).
