# Escopo ampliado de reconciliation (Fase J6)

## Problema anterior

Até a Fase H3, `experiments.runner._reconciliation_routing_strategy_name`
era a única lógica de decisão que reconciliation tinha: sempre tenta uma
estratégia de roteamento diferente, independentemente do tipo de
violação - documentado como limitação conhecida ("this planner version
has no logic that picks a strategy from a violation's category"). Isso
significa que o resultado de "100% de recuperação" da campanha `C04`
(Fase H3) era só um piloto: só existia UMA classe de cenário
(recuperável por troca de rota).

## A política de decisão (`assurance.reconciliation_policy`)

`decide_reconciliation_action` inspeciona a violação primária (a
primeira de `assurance.violations.classify_violations`) e escolhe entre
quatro ações, cada uma com uma verificação física explícita:

| Categoria de violação | Verificação | Ação |
|---|---|---|
| `FIDELITY` | existe rota alternativa cuja estimativa de fidelidade (com purificação, se permitida) atinge a meta? | `route_change` se sim, `no_action` se não (teto físico de fidelidade) |
| `THROUGHPUT`/`DELIVERED_PAIRS` | existe rota alternativa com perda óptica cumulativa menor? | `route_change` se sim |
| `THROUGHPUT`/`DELIVERED_PAIRS` (sem rota melhor) | `reserved_memory_slots` está abaixo de um limiar heurístico (4)? | `slot_increase` se sim, `duration_increase` se não |
| qualquer outra categoria | nenhuma regra cobre | `no_action` |

Cada `ReconciliationDecision` registra `constraints_checked` (o que foi
inspecionado) e `explanation` (por que essa ação, em português técnico
claro) - nunca apenas a ação em si.

**É uma heurística, não uma busca exaustiva**: inspeciona um conjunto
fixo e pequeno de fatos físicos (rotas candidatas de três estratégias já
existentes) e aplica regras simples - no mesmo espírito do próprio
`IntentPlanner` (também uma heurística, não um otimizador).

## Aplicando a decisão (`apply_reconciliation_decision`)

- `route_change`/`no_action`: retornam o intent inalterado - a estratégia
  de roteamento em si é o que muda (`decision.recommended_routing_strategy`,
  passado a `reconcile(routing_strategy=...)`).
- `duration_increase`/`slot_increase`: retornam uma cópia do intent com
  `duration_s`/`reserved_memory_slots` multiplicado por um fator fixo (2x
  por padrão) - não uma busca pelo valor mínimo suficiente.

`reconcile()` ganhou um parâmetro `intent_override` (Fase J6): quando
presente, o episódio 2 planeja/implanta/avalia contra ele em vez do
intent original (mesmo `id`, `requirements` diferentes) - todo chamador
existente continua funcionando sem mudança (`intent_override=None` por
padrão).

## Por que "irrecuperável" nem sempre é decidido de antemão

A política **não verifica se sua própria recomendação vai funcionar**
para `duration_increase`/`slot_increase` - ela apenas aplica a heurística
documentada uma vez (consistente com a limitação já conhecida:
"reconciliation tenta uma única vez, sem busca automática"). Isso
significa que um cenário "irrecuperável por perda severa" ou
"irrecuperável por falta de recursos" não é necessariamente RECUSADO de
antemão pela política (ela pode recomendar `duration_increase` mesmo que
dobrar a duração não seja suficiente) - a irrecuperabilidade só fica
confirmada depois de tentar de verdade e observar que o episódio 2
também terminou `VIOLATED`. Isso é ciência real, não uma limitação a
esconder: só a categoria `FIDELITY` com nenhuma rota alternativa viável é
classificada como `no_action` (irrecuperável) **antes** de tentar,
porque essa é a única verificação que este planejador consegue fazer sem
rodar a simulação.

## As seis classes de cenário

Validadas em `tests/integration/test_reconciliation_scenarios.py` (as
três recuperáveis, com uma recuperação REAL confirmada via simulação) e
`tests/unit/test_reconciliation_policy.py` (as classificações da
política, incluindo os dois casos de fidelidade):

1. **Recuperável por troca de rota** - diamante, `ShortestHopCountRouting`
   escolhe `bad` (VIOLATED), a política recomenda `route_change`,
   `LeastLossRouting` recupera para `SATISFIED`.
2. **Recuperável por aumento de duração** - `three_node_spec` de rota
   única, janela curta demais (VIOLATED), a política recomenda
   `duration_increase` (sem rota melhor, slots adequados), dobrar a
   duração recupera.
3. **Recuperável por aumento de slots** - `three_node_spec` de rota
   única, poucos slots reservados limitando gerações concorrentes
   (VIOLATED), a política recomenda `slot_increase` (sem rota melhor,
   slots escassos), dobrar os slots recupera.
4. **Irrecuperável por fidelidade física** - meta de fidelidade acima do
   que qualquer rota candidata (com purificação) consegue estimar -
   `no_action`, confirmado sem precisar rodar o episódio 2.
5/6. **Irrecuperável por perda severa / falta de recursos** - a política
   pode recomendar `duration_increase`/`slot_increase`, mas o episódio 2
   continua `VIOLATED` na prática - classificado corretamente como "não
   recuperado" pelas métricas abaixo, não como um erro da política.

## Métricas (`experiments.reconciliation_metrics.compute_reconciliation_metrics`)

`initial_violation_rate`, `recovery_attempt_rate`, `recovery_rate`,
`failed_recovery_rate`, `no_action_rate`, `route_change_rate`,
`duration_change_rate`, `slot_change_rate`, `additional_wall_time`,
`additional_episodes` - todas `None` (nunca `0`) quando o denominador
correspondente é zero. Opera sobre um DataFrame de tentativas de
reconciliation (`initial_status`, `reconciliation_attempted`, `action`,
`recovered`, `additional_wall_time_s`, `episodes`) - um formato
deliberadamente independente de `TrialRecord` (nenhuma campanha em escala
popula essas colunas ainda; isso é para a campanha `F05`, Fase J10).

## Resultados em escala (`F05_reconciliation`, Fase J10/K2)

5 classes de cenário × 20 seeds (`scripts/run_f05_reconciliation.py`,
dados em `results/raw/F05_reconciliation/trials.csv`, classificação de
tipo de recuperação em `results/processed/F05_reconciliation/
trials_with_recovery_type.csv` - ver "Tipos de recuperação" abaixo):

| Classe | Ação | Recuperação |
|---|---|---:|
| Recuperável por troca de rota | `route_change` | 15/15 (100%) |
| Recuperável por aumento de duração | `duration_increase` | 20/20 (100%) |
| Recuperável por aumento de slots | `slot_increase` | 19/20 (95%) |
| Irrecuperável por teto de fidelidade | `no_action` (nunca tentado) | não aplicável |
| Irrecuperável por perda severa (tentativa) | `duration_increase` | 0/20 (0%) |

**Formulação correta para o artigo** (nunca "recovers 100% of
intents"): a política **recuperou todos os casos de troca de rota e a
maioria dos casos de ajuste de recurso nos cenários avaliados; falhou
sob perda severa e corretamente evitou agir num teto de fidelidade**.
Figuras: `results/figures/final/Figure_Reconciliation_{BeforeAfter,
RecoveryRate,AdditionalCost}.png`.

## Tipos de recuperação (Fase K3, seção 8)

`scripts/classify_f05_recovery_types.py` classifica cada ação por
impacto contratual - nunca "recovered" sem qualificação:

- **`strict_recovery`** (`route_change`): mesmo SLA, mesmos recursos
  declarados - só o plano de execução interno (rota) muda.
- **`resource_adjusted_recovery`** (`slot_increase`): aumenta
  `reserved_memory_slots`, preserva o SLA (`min_delivered_pairs`,
  `duration_s`).
- **`sla_relaxed_recovery`** (`duration_increase`): altera `duration_s`,
  um elemento temporal/contratual do intent - aplica-se igualmente ao
  caso que recupera (`duration_increase_recoverable`) e ao que tenta e
  falha (`severe_loss_attempt`), já que a classificação descreve o TIPO
  de ação tomada, não se ela funcionou.
- **`not_applicable`**: nenhuma ação foi tomada (já `SATISFIED`/
  `REJECTED_OR_FAILED`, ou a política decidiu `no_action`).

## Limitações desta etapa

- `TrialRecord` (a campanha "de rotina", `execute_trial`) não ganhou
  campos novos para rastrear qual ação de reconciliation foi tomada -
  `compute_reconciliation_metrics`/F05 operam sobre um formato de dados
  separado (`case`, `initial_status`, `action`, `recovered`,
  `recovery_type`, ...), não `TrialRecord`.
- O limiar de "poucos slots" (4) é heurístico, não derivado de um modelo
  fechado de taxa de geração - documentado explicitamente como tal.
- A política tenta uma única vez, sem busca automática do multiplicador
  mínimo suficiente (sempre 2x fixo) - um multiplicador maior poderia
  recuperar `severe_loss_attempt`, mas isso não foi testado (ver
  `docs/future_work.md`).
