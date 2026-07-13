# Arquivo: dados da Fase H3 (pré-Fase J1/J2)

Este diretório preserva os resultados das quatro campanhas piloto de
validação (`C01_routing_strategy`, `C02_fidelity_throughput`,
`C03_assurance_outcomes`, `C04_reconciliation_effectiveness`) e os
artefatos do artigo (`A00`-`A07`) exatamente como produzidos na **Fase
H3** (`campanhas`, `notebooks/article`), antes das mudanças de schema da
**Fase J1** (estimadores de fidelidade) e **Fase J2** (separação
recurso/meta de entrega).

## Por que este arquivo existe

`TrialRecord` (`src/ibqn/experiments/records.py`) mudou de forma
incompatível com o formato abaixo:

- **Fase J1**: adicionados `fidelity_estimator`, `observed_fidelity`,
  `absolute_fidelity_error`, `relative_fidelity_error`;
  `TrialIdentity.strategy` passou a incluir o nome do estimador
  (`f"{routing}__{purification}__{fidelity_estimator}"`), mudando
  `trial_id` para todo trial.
- **Fase J2**: `requested_pairs` foi renomeado para
  `reserved_memory_slots`; `min_delivered_pairs` foi adicionado (novo,
  opcional); `delivery_ratio`/`excess_delivery_pairs` passaram a ser
  calculados contra `min_delivered_pairs` (antes eram contra
  `requested_pairs`); `deliveries_per_reserved_slot` foi adicionado.

Anexar novos trials a um `trials.csv` com o cabeçalho antigo corromperia o
alinhamento de colunas - por isso as quatro campanhas foram
reexecutadas do zero com o novo schema (ver `results/raw/`,
`results/processed/`, `results/manifests/` no diretório ativo do
projeto), e este diretório preserva a versão anterior para referência e
para permitir comparar as duas gerações de resultados sem perder nenhum
dado.

## Proveniência (da geração original, Fase H3)

| Campo | Valor |
|---|---|
| Commit do projeto (na 1ª criação das campanhas) | `4adf848c8adfbaff901f8ec6a5b1cbac31ae3768` (`feat: add and validate campaigns C01-C04 at small scale (Fase H3.4)`) |
| Commit do SeQUeNCe (submódulo) | `1f2680a5b9065e708a7497adc53a95b108029b98` |
| Python | 3.13.14 |
| Plataforma | Windows-11-10.0.26200-SP0 |
| Datas de criação dos manifestos (UTC) | C01: 2026-07-11T23:18:09Z · C02: 2026-07-11T23:18:37Z · C03: 2026-07-11T23:18:53Z · C04: 2026-07-11T23:19:01Z |
| Data deste arquivamento (Fase J1/J2) | 2026-07-13 |

## Schema antigo (`trials.csv`, antes da Fase J1/J2)

```
campaign,trial_id,scenario,parameter_hash,seed,intent_id,routing_strategy,
purification_policy,reconciliation_enabled,route,hop_count,requested_pairs,
requested_fidelity,estimated_fidelity,duration_s,attenuation_db_per_m,
distance_m,coherence_time_s,accepted,satisfied,recovered,final_status,
delivered_pairs,excess_delivery_pairs,delivery_ratio,average_fidelity,
minimum_fidelity,throughput_active_window,throughput_delivery_interval,
first_pair_latency_s,completion_time_s,planning_time_s,
simulation_wall_time_s,eg_attempts,eg_success,ep_attempts,ep_success,
es_attempts,es_success,violations,error_type,error_message,
project_git_commit,sequence_git_commit,python_version,timestamp
```

Note a ausência de `fidelity_estimator`/`observed_fidelity`/
`absolute_fidelity_error`/`relative_fidelity_error` (Fase J1) e de
`min_delivered_pairs`/`deliveries_per_reserved_slot` (Fase J2); `requested_pairs`
aqui tem o papel que `reserved_memory_slots` tem no schema atual, e
`excess_delivery_pairs`/`delivery_ratio` foram calculados contra esse
mesmo campo (não contra uma meta de entrega separada).

## Escopo

Estes dados são exclusivamente das **campanhas piloto de validação da
Fase H3** (poucas seeds, poucas combinações de parâmetros - ver
`docs/campaign_architecture.md`), destinadas a comprovar que a
infraestrutura de campanhas funciona corretamente, não a sustentar
conclusões científicas finais do artigo. Não é a campanha final da Fase
J10 (ainda não executada nesta etapa).

## Não misturar

Não copie nem anexe nenhum arquivo deste diretório aos diretórios ativos
(`results/raw/`, `results/processed/`, `results/manifests/`,
`results/figures/`, `results/tables/`) - os schemas são incompatíveis.
Este diretório é somente para consulta/comparação histórica.
