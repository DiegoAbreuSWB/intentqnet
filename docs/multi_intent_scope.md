# Escopo de múltiplos intents (Fase J8)

## Decisão: Opção A - escopo de intent individual por endpoint

Este projeto adota, formalmente, o escopo de **um intent ativo por
endpoint** (`QuantumRouter`) - a mesma restrição que já existia
implicitamente desde a Etapa G, agora declarada explicitamente como
decisão de escopo, não apenas como limitação técnica incidental.

## Por que não a Opção B (multiplexador de aplicações)

`QuantumRouter.set_app(app)` (`sequence/topology/node.py`) armazena
exatamente **uma** referência de app por nó - não há um mecanismo nativo
do SeQUeNCe para múltiplas aplicações concorrentes no mesmo roteador. Um
`IntentApplicationDispatcher` que multiplexasse várias intents por trás
de um único app registrado seria tecnicamente possível **sem** modificar
arquivos do núcleo do SeQUeNCe (a restrição deste projeto de "nunca
modificar o núcleo" permite composição/subclasses/adapters) - mas
exigiria:

- mapear `Reservation`/`MemoryInfo` de volta para `intent_id` sem
  nenhuma chave nativa que já faça isso (`Reservation` não carrega um
  `intent_id` - só `identity`, `initiator`, `responder`);
- separar sessões de lifecycle completamente (nenhuma mistura de
  callbacks entre reservas concorrentes no mesmo nó);
- isolar evidência por intent quando duas reservas competem pelas MESMAS
  memórias físicas do nó compartilhado;
- testar exaustivamente contenção real de recursos entre intents
  concorrentes no mesmo nó (não apenas nós disjuntos, que já funciona -
  ver abaixo).

Essa é uma extensão de escopo substancial, não uma limpeza incremental -
exatamente o critério da seção 10.5 do prompt original ("caso a
multiplexação exija alteração invasiva... escolha a Opção A"). A
recomendação explícita do prompt original é seguida aqui.

## O que já funciona (e continua funcionando) na Opção A

Múltiplos intents **já são suportados quando não compartilham nenhum nó
como origem/destino** - confirmado desde a Etapa G/Fase H2:

- `tests/integration/test_assurance_pipeline.py::
  test_multi_intent_metric_isolation_end_to_end`: dois intents em pares
  de nós disjuntos rodam simultaneamente na mesma `Timeline`, cada um com
  evidência (`DELIVERY`) isolada por `intent_id`.
- notebook 18 da Fase H2 (`star_spec`): dois intents que **compartilham
  um nó interior de swap** (nunca como origem/destino) coexistem
  corretamente - o compartilhamento problemático é especificamente
  origem/destino, não qualquer nó da rota.
- `SequenceExecutor._check_no_node_conflict` levanta `ValueError`
  explícito (nunca sobrescreve silenciosamente) quando dois intents
  tentariam compartilhar um nó como origem/destino -
  `tests/integration/test_assurance_pipeline.py::
  test_conflicting_node_usage_raises_instead_of_misrouting_callbacks`
  cobre origem/destino compartilhados E o caso "cruzado" (intent A:
  r1->r3, intent B: r3->r1 - mesmos dois nós, papéis invertidos).

## Não afirmar suporte a concorrência

Este projeto **não afirma** suporte a:

- justiça (fairness) entre intents concorrentes;
- prioridade operacional real entre intents;
- preempção de reservas por prioridade;
- contenção de recursos arbitrada entre múltiplos intents no mesmo nó.

Nenhum experimento de justiça/prioridade/contenção existe neste projeto,
e nenhum será adicionado nesta fase.

## `IntentPolicy.priority` existe no schema, mas não é aplicado

`IntentPolicy.priority` (`Literal["low", "normal", "high"]`, padrão
`"normal"`) é um campo declarado desde a Etapa C, mas **nunca** foi lido
por nenhum código de planejamento, execução ou reconciliation - grep
confirma seu único uso é puramente de exibição
(`demos.tables.intent_table`, uma tabela de leitura humana). Isso
significa: declarar `priority: high` num intent **não tem efeito algum**
no comportamento do sistema.

Isso não é um bug a corrigir nesta fase - é uma decisão de escopo
explícita, agora documentada para nunca ser mal interpretada como suporte
a prioridade real só porque o campo existe no YAML (ver seção 10.4 do
prompt original: "não simular prioridade fictícia").

## Consequência para as campanhas futuras (Fase J10)

Nenhuma campanha desta fase (ou da Fase J10) deve incluir cenários de
múltiplos intents concorrentes no MESMO nó como origem/destino - isso
está fora do escopo declarado. Cenários com múltiplos intents em nós
disjuntos (como o notebook 18) continuam válidos e podem ser usados
livremente.

## Trabalho futuro

Ver `docs/future_work.md`: "suporte completo a múltiplos intents
concorrentes" é listado explicitamente como trabalho futuro, não como
algo pendente desta fase.
