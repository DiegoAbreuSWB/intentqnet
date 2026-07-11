# Semântica de `requested_pairs` e métricas derivadas

## `requested_pairs` não é um teto de entrega

Observado repetidamente desde a Fase H1 (notebook 01) e quantificado em
campanha na Fase H3 (`C02`/`A06`): `EntanglementIntent.requirements.
requested_pairs` dimensiona **o pool de memórias reservado** em cada nó da
rota (`RSVPProtocol.schedule`/`planning.resource_allocation.
required_memories_per_node` reservam exatamente `requested_pairs`
memórias por nó extremo, `requested_pairs * 2` por nó interior) - não um
limite de quantos pares fim a fim podem ser entregues durante a janela da
reserva.

Mecanismo real: assim que uma memória entrega um par (estado `ENTANGLED`/
`PURIFIED` casado com a reserva), `IntentRequestApp.get_memory`/
`_count_purified_delivery` resetam essa memória para `RAW`
(`resource_manager.update(None, memory, "RAW")`), liberando-a para uma
nova tentativa de geração - o SeQUeNCe não sabe, e não precisa saber,
quantos pares "já foram suficientes"; ele continua gerando entrelaçamento
até que a `Rule` instalada expire em `reservation.end_time`. Se a janela
(`duration`) for longa e a rota tiver perda baixa, o número de pares
entregues pode superar `requested_pairs` por uma ordem de grandeza ou mais
(ver notebook 15 da Fase H2: rota `good1/good2`, 10 pares pedidos, 438
entregues).

## Métricas derivadas (nunca truncadas)

```python
excess_delivery_pairs = max(0, delivered_pairs - requested_pairs)
delivery_ratio = delivered_pairs / requested_pairs
```

`delivered_pairs` em si **nunca é truncado** para `requested_pairs` em
nenhuma tabela/gráfico/registro desta arquitetura - fazer isso esconderia
exatamente o fenômeno que essas duas métricas existem para quantificar.
`TrialRecord.excess_delivery_pairs`/`delivery_ratio` (`records.py`) são
calculados uma vez, na persistência do trial, a partir do
`delivered_pairs` real e do `requested_pairs` declarado no intent - nunca
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
