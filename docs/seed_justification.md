# Justificativa do número de seeds (Fase J9)

## Metodologia

Campanha piloto `P00_variability_study` (`src/ibqn/experiments/
variability_study.py`), executada uma vez para valer (não simulada nem
estimada): cinco cenários representativos, cada um com 30 seeds reais
(`0..29`), reavaliados em `n ∈ {5, 10, 20, 30}` para observar como cada
estatística se estabiliza conforme o número de seeds cresce. Dados brutos
em `results/raw/P00_variability_study/pilot_trials.csv` (210 trials
reais), resumo em `results/processed/P00_variability_study/
variability_report.json`.

## Os cinco cenários

| Cenário | Topologia | Calibração | O que testa |
|---|---|---|---|
| `linear_favoravel` | `three_node_spec`, atenuação 1e-6 | folgado, fácil de satisfazer | variabilidade num caso "fácil" |
| `linear_intermediario` | `three_node_spec`, atenuação 0.01 | meta de entrega moderada (20) | variabilidade num caso moderado |
| `diamante_divergencia` | `diamond_spec` | 3 estratégias de roteamento | estabilidade de ranking entre estratégias |
| `com_purificacao` | `three_node_spec`, atenuação 1e-5 | `min_fidelity=0.70` (exige purificação) | variabilidade com purificação ativa |
| `proximo_violacao` | `three_node_spec`, atenuação 0.01 | meta de entrega calibrada para ficar na fronteira (15) | estabilidade da taxa de satisfação perto do limiar |

## Resultados (dados reais, `delivered_pairs`)

`relative_ci95_width` = largura do IC95%/média - a métrica central para
decidir "quantas seeds bastam":

| Cenário/estratégia | n=5 | n=10 | n=20 | n=30 |
|---|---:|---:|---:|---:|
| `linear_favoravel` | 5.1% | 3.8% | 2.3% | **1.9%** |
| `linear_intermediario` | 28.4% | 19.4% | 11.4% | **8.1%** |
| `diamante` (`least_loss`) | 4.8% | 3.1% | 2.2% | **1.6%** |
| `diamante` (`shortest_hop_count`/`highest_fidelity`) | 108.2% | 70.1% | 35.9% | **26.1%** |
| `com_purificacao` | 12.1% | 8.3% | 4.4% | **3.5%** |
| `proximo_violacao` | 42.3% | 20.9% | 16.6% | **11.7%** |

`satisfaction_rate` por `n` (fração de seeds `SATISFIED`):

| Cenário/estratégia | n=5 | n=10 | n=20 | n=30 |
|---|---:|---:|---:|---:|
| `linear_favoravel` | 1.00 | 1.00 | 1.00 | 1.00 |
| `linear_intermediario` | 1.00 | 1.00 | 1.00 | 1.00 |
| `diamante` (`shortest_hop_count`/`highest_fidelity`) | 0.40 | 0.20 | 0.25 | 0.20 |
| `diamante` (`least_loss`) | 1.00 | 1.00 | 1.00 | 1.00 |
| `com_purificacao` | 1.00 | 1.00 | 1.00 | 1.00 |
| `proximo_violacao` | 0.80 | 0.90 | 0.95 | **0.967** |

## Estabilidade de ranking (`diamante_divergencia`)

Ranking por média de `delivered_pairs` (melhor primeiro), em `n =
5, 10, 20, 30`:

```
n=5:  least_loss > shortest_hop_count > highest_fidelity
n=10: least_loss > shortest_hop_count > highest_fidelity
n=20: least_loss > shortest_hop_count > highest_fidelity
n=30: least_loss > shortest_hop_count > highest_fidelity
```

**Estável em todo `n` testado** - `least_loss` (~446 pares) domina
`shortest_hop_count`/`highest_fidelity` (~7-9 pares, estatisticamente
idênticos entre si nesta topologia, já que ambos escolhem exatamente a
mesma rota `bad`) por uma margem tão grande que até 5 seeds já a detecta
corretamente. Isso justifica por que a Fase H3 (`C01_routing_strategy`,
apenas 3 seeds) já produziu uma conclusão de ranking correta - o efeito
ali é grande o bastante para não precisar de muitas seeds.

## Achado central: nem toda métrica se comporta igual

Duas classes de comportamento bem distintas:

1. **Cenários "fáceis" ou de efeito grande** (`linear_favoravel`,
   `com_purificacao`, `diamante` via `least_loss`): `relative_ci95_width`
   já fica abaixo de ~5% em `n=20`, e a taxa de satisfação é
   perfeitamente estável (0 ou 1) desde `n=5`. **20 seeds bastam**.
2. **Cenários marginais ou de contagem absoluta baixa**
   (`proximo_violacao`, `diamante` via `shortest_hop_count`/
   `highest_fidelity`): `relative_ci95_width` continua **acima de 10%**
   mesmo em `n=30`, e a taxa de satisfação de `proximo_violacao` ainda
   está mudando entre `n=20` (0.95) e `n=30` (0.967) - **30 seeds não é
   claramente suficiente** para esses casos; a estimativa continua
   convergindo.

Isso não é uma falha do estudo - é exatamente o resultado que
`docs/campaign_architecture.md` já previa (contagens absolutas baixas
têm variância relativa alta por construção, já que
`coefficient_of_variation` de uma contagem de Poisson-like escala com
`1/sqrt(mean)`).

## Número escolhido

**20 seeds como padrão** para as campanhas finais (Fase J10) - onde a
Fase H3 usou apenas 2-3. Justificativa: a maioria dos cenários deste
piloto já atinge `relative_ci95_width < 12%` em `n=20`, e toda
comparação de RANKING (o tipo de conclusão mais comum neste projeto -
"estratégia X entrega mais que Y") já está estável desde `n=5`.

## Exceção documentada por campanha

- **Cenários com contagem de pares absoluta baixa** (ex.: a rota `bad`
  do diamante, que entrega ~7-9 pares) devem usar **30+ seeds** quando a
  pergunta de pesquisa depende do valor absoluto (não apenas do
  ranking) - `relative_ci95_width` continua alto mesmo em `n=30` para
  esses casos.
- **Cenários deliberadamente próximos ao limiar de satisfação** (como
  `C03_assurance_outcomes`, que já existe, e qualquer campanha futura
  estudando a fronteira SATISFIED/VIOLATED) devem reportar
  `relative_ci95_width` da `satisfaction_rate` explicitamente e
  considerar 30+ seeds - a taxa de satisfação ainda estava convergindo
  em `n=30` no piloto (`proximo_violacao`).
- **Comparações de ranking com efeito grande** (como `C01`, onde
  `least_loss` supera as outras estratégias por ~50x) podem
  legitimamente usar menos seeds (confirmado: 5 já bastam) - mas ainda
  assim, 20 seeds é o padrão recomendado para manter uma metodologia
  única e não justificar reduções caso a caso sem necessidade real.

## Reprodutibilidade

`results/raw/P00_variability_study/pilot_trials.csv` (210 trials reais,
5 cenários x até 3 estratégias x 30 seeds) e `results/processed/
P00_variability_study/variability_report.json` (estatísticas por `n`)
preservam os dados completos usados para este documento - nenhum número
acima foi calculado fora dessa cadeia.
