# Semântica de `reserved_memory_slots` e métricas derivadas

> Atualizado na Fase J2: o campo antes chamado `requested_pairs` foi
> renomeado para `reserved_memory_slots` e um novo campo opcional,
> `min_delivered_pairs`, foi introduzido para representar separadamente a
> meta de entrega. Ver `docs/intent_resource_semantics.md` para a
> motivação completa e a migração de compatibilidade.

## `reserved_memory_slots` não é um teto de entrega

Observado repetidamente desde a Fase H1 (notebook 01) e quantificado em
campanha na Fase H3 (`C02`/`A06`): `EntanglementIntent.requirements.
reserved_memory_slots` dimensiona **o pool de memórias reservado** em cada
nó da rota (`RSVPProtocol.schedule`/`planning.resource_allocation.
required_memories_per_node` reservam exatamente `reserved_memory_slots`
memórias por nó extremo, `reserved_memory_slots * 2` por nó interior) - não
um limite de quantos pares fim a fim podem ser entregues durante a janela
da reserva.

Mecanismo real: assim que uma memória entrega um par (estado `ENTANGLED`/
`PURIFIED` casado com a reserva), `IntentRequestApp.get_memory`/
`_count_purified_delivery` resetam essa memória para `RAW`
(`resource_manager.update(None, memory, "RAW")`), liberando-a para uma
nova tentativa de geração - o SeQUeNCe não sabe, e não precisa saber,
quantos pares "já foram suficientes"; ele continua gerando entrelaçamento
até que a `Rule` instalada expire em `reservation.end_time`. Se a janela
(`duration_s`) for longa e a rota tiver perda baixa, o número de pares
entregues pode superar `reserved_memory_slots` por uma ordem de grandeza
ou mais (ver notebook 15 da Fase H2: rota `good1/good2`, 10 slots
reservados, 438 entregues).

## Métricas derivadas (nunca truncadas)

```python
excess_delivery_pairs = max(0, delivered_pairs - min_delivered_pairs)
delivery_ratio = delivered_pairs / min_delivered_pairs
deliveries_per_reserved_slot = delivered_pairs / reserved_memory_slots
```

`excess_delivery_pairs`/`delivery_ratio` são calculados contra
`min_delivered_pairs` (a **meta de serviço**, opcional) - `None` sempre que
o intent não declara uma. `deliveries_per_reserved_slot` é uma métrica
separada de **eficiência de recurso** (reuso de memória), sempre
calculável a partir de `reserved_memory_slots` (que é obrigatório).

`delivered_pairs` em si **nunca é truncado** para `reserved_memory_slots`
nem para `min_delivered_pairs` em nenhuma tabela/gráfico/registro desta
arquitetura - fazer isso esconderia exatamente o fenômeno que essas
métricas existem para quantificar. `TrialRecord.excess_delivery_pairs`/
`delivery_ratio`/`deliveries_per_reserved_slot` (`records.py`) são
calculados uma vez, na persistência do trial, a partir do
`delivered_pairs` real e dos campos declarados no intent - nunca
recalculados a partir de uma estimativa do planner.

## Por que isso importa para assurance

`assurance.evaluator._delivered_pairs` conta pares reais (`DELIVERY`
tagueados por `intent_id`), então uma condição como
`delivered_pairs >= 10` é satisfeita por 10, 223, ou 438 pares igualmente
- o "excesso" não é uma falha de nada, é esperado sempre que a rota tem
capacidade sobrando em relação à janela/fidelidade pedidas. `docs/
campaign_architecture.md` e o notebook `A06_delivery_overprovisioning`
tratam isso como um resultado a caracterizar (quando/quanto excesso
ocorre, em função de duração, memórias, estratégia), não como um bug a
corrigir.
