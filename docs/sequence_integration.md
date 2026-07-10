# Integração com o SeQUeNCe

Este documento registra as decisões de design e as descobertas feitas ao
implementar `src/ibqn/network/sequence_adapter.py` e
`src/ibqn/execution/sequence_executor.py` (Etapa D) — o que funcionou de
primeira, o que exigiu depuração, e por quê.

## `SequenceAdapter` reaproveita `RouterNetTopo`, não constrói nós manualmente

A Fase 2 (`tests/sequence_basics/`) construiu topologias nó-a-nó
manualmente (como os exemplos oficiais `two_node_eg`/`three_node_eg_ep_es`),
inclusive chamando `update_forwarding_rule` explicitamente. O adaptador da
Fase 3 usa `sequence.topology.router_net_topo.RouterNetTopo(config: dict)`
diretamente, porque:

1. `RouterNetTopo._generate_forwarding_table` já computa a tabela de
   roteamento estática via Dijkstra automaticamente a partir dos
   `qconnections` — chamar `update_forwarding_rule` manualmente seria
   duplicar um mecanismo que o próprio simulador já oferece.
2. `RouterNetTopo._add_qconnections` já cria o nó BSM intermediário e os
   canais quântico/clássico para cada link `meet_in_the_middle`.
3. `Topology.__init__` aceita um `dict` diretamente (não apenas um caminho de
   arquivo), então não há necessidade de escrever um JSON temporário em disco.

**Restrição descoberta**: `RouterNetTopo._add_qconnections` **exige** que já
exista uma conexão clássica (`cconnections`/`cchannels`) direta entre os dois
roteadores de todo `qconnection`, falhando com `assert 0, q_connect` caso
contrário. Por isso `NetworkTopologySpec` gera automaticamente uma malha
completa de conexões clássicas entre todos os roteadores — topologias
clássicas esparsas não são suportadas nesta versão (ver `docs/limitations.md`).

**Restrição descoberta**: cada entrada de nó no dicionário de configuração
exige a chave `"seed"` (`node[Topo.SEED]`, sem `.get`, portanto levanta
`KeyError` se ausente); cada `qconnection` aceita uma chave `"seed"` opcional
para o nó BSM auto-gerado, mas o padrão é `0` se omitida — o que faria todos
os nós BSM compartilharem a mesma seed. `NetworkTopologySpec.to_router_net_topo_config`
atribui seeds distintas e determinísticas (`seed_base + índice`) tanto para
roteadores quanto para cada `qconnection`, evitando essa colisão silenciosa.

## `IntentRequestApp`: por que dois apps, e por que um deles nunca conta pares

`SequenceExecutor.submit` anexa um `IntentRequestApp` tanto no roteador de
origem quanto no de destino do intent. Isso não é redundante: sem *nenhum*
app anexado a um nó, `Node.get_idle_memory` nunca é encaminhado a
`app.get_memory`, e memórias entregues nunca voltam a `RAW` — o que impediria
a reciclagem de memórias para reservas que pedem mais pares do que memórias
físicas disponíveis.

Descoberta ao ler `sequence/app/request_app.py:119-143`: `RequestApp.get_memory`
só incrementa `memory_counter` no lado do **iniciador** da reserva
(`info.remote_node == reservation.responder`); no lado do respondente, o
mesmo método apenas reseta a memória para `RAW`, sem contar nada. Por isso
`IntentRequestApp._delivered_pairs`/o evento `EventTypes.DELIVERY` só são
emitidos pelo app anexado ao nó de **origem** do intent — o app do destino
existe apenas para permitir a reciclagem de memórias, nunca produz telemetria
própria (documentado no docstring de `IntentRequestApp`).

## Bug real encontrado e corrigido: fidelidade sempre `0` no evento DELIVERY

Primeira versão de `IntentRequestApp.get_memory`:

```python
def get_memory(self, info):
    pairs_before = self.memory_counter
    super().get_memory(info)          # BUG: já reseta info.fidelity para 0
    if self.memory_counter > pairs_before:
        metrics.record(..., fidelity=info.fidelity, ...)   # sempre lê 0
```

`RequestApp.get_memory` (chamado via `super()`) reseta a memória entregue
para `RAW` como efeito colateral de uma entrega bem-sucedida
(`MemoryInfo.to_raw()` zera `fidelity` no mesmo objeto `info`, que é
mutável). Ler `info.fidelity` **depois** de chamar `super().get_memory(info)`
sempre observa `0`, não o valor real no momento da entrega. Confirmado
empiricamente (script de fumaça) antes de virar teste automatizado: com o bug,
`test_delivery_metrics_are_recorded_with_correct_fidelity` teria passado
mesmo estando errado, pois a asserção só checava presença de registros, não
seu valor — a correção foi capturar `info.fidelity` **antes** da chamada a
`super()`.

## Escolha de `min_fidelity` no teste de integração feliz

`tests/integration/test_intent_to_execution.py` usa `min_fidelity=0.65`
deliberadamente **abaixo** de `raw_fidelity² × swapping_degradation`
(0.85² × 0.95 ≈ 0.686, os padrões do SeQUeNCe quando nenhum template de
hardware é fornecido). Uma primeira tentativa com `min_fidelity=0.8` (acima
desse limite) forçou rodadas de purificação que nunca convergiam a tempo
dentro da janela de simulação usada no teste — não por bug, mas porque
0.8 é fisicamente inatingível com esses parâmetros em poucas rodadas. Isso
**confirma na prática** a limitação já registrada em
`docs/sequence_code_analysis.md` (seção 4.7): o núcleo do SeQUeNCe não estima
a priori se um `target_fidelity` é alcançável — só se descobre observando a
simulação rodar. É exatamente essa lacuna que `planning/feasibility.py`
(Etapa E) precisa preencher.

## `requested_pairs` não é um teto de entrega

Com memórias reginmisáveis, `NetworkManager.request(..., memory_size=10, ...)`
não limita quantos pares serão entregues ao longo da janela de reserva — é só
o tamanho do pool de memórias, que se recicla continuamente. Em um teste de
fumaça inicial (janela de 0.8s, mesma topologia), uma reserva de 10 memórias
entregou 4402 pares. O `assurance.evaluator` (Etapa G) deve comparar
`delivered_pairs` observado contra `requested_pairs` como um piso mínimo, não
como uma contagem exata esperada.
