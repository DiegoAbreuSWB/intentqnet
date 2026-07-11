# Arquitetura de campanhas (Fase H3)

Este documento descreve a infraestrutura de campanhas experimentais
(`src/ibqn/experiments/campaigns.py`, `sweeps.py`, `records.py`, `runner.py`,
`persistence.py`, `manifests.py`, `validation.py`, `aggregation.py`,
`export.py`, `status.py`, `cli.py`), construída sobre o que já existia da
Etapa F (`Scenario`, `run_scenario`, `seeds_for_trials` —
`docs/experimental_methodology.md`).

## 1. Unidade experimental

Uma **campanha** (`CampaignSpec`) é a unidade experimental de mais alto
nível: um cenário base (topologia + intents), um conjunto de estratégias a
comparar, uma grade de parâmetros a varrer, e uma lista de seeds. Uma
campanha nunca modifica o arquivo de cenário no disco - ela reconstrói
`NetworkTopologySpec`/`EntanglementIntent` em memória a partir dele, uma
combinação de parâmetros por vez (`sweeps.apply_parameters`).

## 2. Unidade de repetição

A **seed** é a unidade de repetição: para a mesma combinação de
(cenário, parâmetros, estratégia), cada seed em `CampaignSpec.seeds` produz
um trial independente, usada tanto para `SequenceAdapter` quanto para
qualquer outro RNG do trial. `experiments.seeds.seeds_for_trials` continua
sendo a forma recomendada de gerar seeds espaçadas (`STRIDE=1000`) quando o
autor da campanha quer N repetições em vez de listar seeds à mão.

## 3. Definição de trial

Um **trial** é a unidade mínima executável:

```text
uma campanha × um cenário × uma combinação de parâmetros ×
uma estratégia × uma seed × um intent
```

Cada trial roda sobre um `SequenceAdapter`/`Timeline`/`IntentRepository`
**novos** (nunca reaproveitados de outro trial) e reseta
`sequence.utils.metrics` antes de rodar (via `demos.scenarios.ad_hoc_scenario`
+ `experiments.runner.run_scenario`, o mesmo mecanismo seguro já usado pelos
notebooks H2 - ver a lição do notebook 06 do H1 sobre contaminação de
métricas entre simulações no mesmo processo).

### `TrialIdentity` e `trial_id`

```python
TrialIdentity(
    campaign="...", scenario="...", parameter_hash="...",
    strategy="...", seed=42, intent_id="...",
)
```

`parameter_hash` é um hash SHA-256 (truncado a 16 hex chars) da
serialização **ordenada** (`json.dumps(..., sort_keys=True)`) da combinação
de parâmetros dessa iteração do grid - não da campanha inteira. `trial_id`
é a concatenação estável de todos os campos de `TrialIdentity`
(`campaign:scenario:parameter_hash:strategy:seed:intent_id`), nunca um
índice sequencial: a mesma configuração sempre produz o mesmo `trial_id`,
em qualquer ordem de execução, o que é o que torna `resume` possível.

## 4. Campos persistidos

Ver `TrialRecord` em `records.py` para a lista completa de campos (rota,
fidelidades, contagens, tempos, status, commit/versões). Duas regras
estritas:

- **nenhum campo numérico ausente é convertido para zero** - campos sem
  evidência real usam `None` (serializado como célula vazia no CSV / `null`
  no JSON), nunca `0`/`0.0`, para que agregação e validação possam
  distinguir "zero observado" de "não disponível".
- **métricas globais do SeQUeNCe nunca substituem evidência por intent** -
  `delivered_pairs`/`average_fidelity`/etc. vêm sempre de
  `assurance.telemetry.collect_intent_evidence`, nunca de
  `metrics.collect_trial_metrics` (que é só contexto diagnóstico, ver
  notebook 06 do H1 e notebook 13 do H2).

## 5. Derivação de seeds

`CampaignSpec.seeds` é uma lista explícita de inteiros (não um
`base_seed`/`n_trials` implícito) - o autor da campanha decide as seeds,
tipicamente chamando `seeds_for_trials` uma vez ao escrever o YAML. Isso
mantém `trial_id` estável mesmo que `seeds_for_trials`/`STRIDE` mudem no
futuro: o que importa para reprodutibilidade é a seed literal gravada no
`TrialRecord`, não a fórmula que a gerou.

## 6. Como a execução pode ser retomada

`CampaignRunner.run()`:

1. expande o grid de parâmetros (`sweeps.expand_parameter_grid`) e gera a
   lista completa de `TrialIdentity` esperados (produto cartesiano de
   parâmetros × estratégias × seeds × intents do cenário);
2. lê `results/raw/<campaign>/trials.csv` (se existir) e coleta o conjunto
   de `trial_id` já presentes - esses são **pulados** (`skipped_trials`);
3. para cada trial restante, executa isoladamente, grava a linha
   imediatamente (append, não buffer em memória) e atualiza o manifesto;
4. se um trial levanta uma exceção, grava um registro de erro em
   `errors.jsonl` (nunca no `trials.csv`) e, conforme
   `CampaignSpec.continue_on_error`, continua ou aborta.

`resume` é literalmente rodar `run()` de novo: como o crivo é "já existe
esse `trial_id` em `trials.csv`?", não há estado adicional de "campanha em
andamento" para gerenciar - a idempotência vem inteiramente do `trial_id`
determinístico.

## 7. Como falhas são registradas

Toda falha (exceção Python durante `deploy`/`run`/avaliação) vira uma linha
em `results/raw/<campaign>/errors.jsonl`: `trial_id`, `error_type`,
`error_message` (via `traceback.format_exception_only`), e o `TrialIdentity`
completo - suficiente para reproduzir e depurar sem re-executar a campanha
inteira. Falhas nunca aparecem como linhas de `trials.csv` com campos
zerados.

## 8. Como resultados são agregados

`aggregation.aggregate_records(records, group_by=[...])` agrupa por
qualquer subconjunto de colunas categóricas do `TrialRecord` (estratégia,
valores do sweep, status) e calcula, por métrica numérica: `n_total`,
`n_valid` (não-`None`/não-`NaN`), `n_missing`, `mean`, `std`, `median`,
`min`, `max`, `ci95_low`/`ci95_high` (intervalo t de Student,
`scipy.stats.t`, só quando `n_valid >= 2` - caso contrário `None`, nunca
`0`), e taxas (`acceptance_rate`, `satisfaction_rate`, `violation_rate`,
`rejection_rate`, `recovery_rate`) sobre `n_total` do grupo.

`aggregation.align_paired_trials(records, pair_on=[...], compare=...)`
alinha trials que compartilham cenário/parâmetros/seed mas diferem em
`compare` (tipicamente `strategy` ou `reconciliation_enabled`), calcula
diferenças por seed, e reporta pares ausentes explicitamente em vez de
descartá-los silenciosamente.

## 9. Como notebooks localizam dados

Convenção fixa, nunca configurável por notebook:

```text
results/raw/<campaign>/trials.csv       # um TrialRecord por linha
results/raw/<campaign>/errors.jsonl     # um erro por linha
results/manifests/<campaign>.json       # metadata + progresso
results/processed/<campaign>/aggregated.csv
results/processed/<campaign>/paired.csv
results/figures/article/*.{pdf,png}
results/tables/article/*.csv
```

Os notebooks `notebooks/article/A00`-`A07` **nunca chamam
`CampaignRunner`** - apenas leem esses arquivos (ver `docs/notebooks.md`).

## 10. Limitações metodológicas

- Amostras iniciais (C01-C04) são deliberadamente pequenas (poucas seeds,
  grids pequenos) para validar a infraestrutura - não sustentam conclusões
  estatísticas fortes por si mesmas (ver `docs/experimental_methodology.md`
  sobre o mesmo cuidado já tomado no notebook 16 da Fase H2).
- IC95 usa a aproximação t de Student (`scipy.stats.t.ppf`), que assume
  aproximadamente normalidade da métrica agregada - razoável para médias de
  contagens grandes (pares entregues), mais frágil para métricas com poucas
  observações ou distribuições muito assimétricas.
- `parameter_hash` cobre apenas os parâmetros declarados no
  `parameter_grid` da campanha - mudanças em código (`src/ibqn`) ou no
  próprio SeQUeNCe não mudam o `trial_id`; `project_git_commit`/
  `sequence_git_commit` gravados em cada `TrialRecord` existem exatamente
  para tornar essa diferença auditável a posteriori.
- Reconciliation em campanha usa o mesmo mecanismo de dois episódios já
  validado no notebook 15 (Fase H2) - `reconciliation_enabled=True` tenta
  no máximo um episódio de reconciliação por trial, não converge
  iterativamente.
- `requested_pairs` continua sem ser um teto de entrega (ver
  `docs/metrics.md`) - `excess_delivery_pairs`/`delivery_ratio` documentam
  isso quantitativamente, mas não mudam o comportamento do simulador.
