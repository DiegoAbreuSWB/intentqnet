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
    requested_pairs: 100      # número de pares fim-a-fim solicitados
    start_time: 0             # segundos, relativo ao início do cenário/simulação
    duration: 10              # segundos, duração da janela de reserva

  policy:
    priority: normal          # low | normal | high
    allow_rerouting: true
    allow_purification: true
    allow_multiple_paths: false

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
