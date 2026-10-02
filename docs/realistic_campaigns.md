# Suíte de campanhas calibradas (`results/realistic/`)

Substitui as campanhas F01–F08/P01–P17 do manuscrito V1, cujos números
vinham do modelo escalar legado (`ket_vector`, sem decoerência, hardware
idealizado). Mesmas perguntas, física calibrada
(`docs/physical_model.md`, `docs/parameter_calibration.md`).

```
python scripts/realistic/audit_generation_model.py [workers] [seeds]   # R00
python scripts/realistic/audit_state_integrity.py  [workers] [seeds]   # R00b
python scripts/realistic/run_suite.py <r01..r09|all> [--seeds N] [--workers N] [--out DIR]
python scripts/realistic/analyze_suite.py [--root DIR]                 # tabelas processadas
```

Toda campanha **retoma**: jobs cujas chaves já estão nos arquivos de saída
são pulados, então uma execução interrompida (ou estendida com mais
sementes) continua de onde parou. Um processo trabalhador morto pelo
sistema operacional não derruba a campanha (`experiments.parallel`).

## Duas condições de hardware

Cada campanha roda nas duas (`experiments.realistic_suite.HARDWARE`):

| Condição | Perfil | O que é |
|---|---|---|
| `literature` | `siv_2024` | todos os parâmetros demonstrados em laboratório (Knaut 2024, Stas 2022, Bhaskar 2020): par elementar 0,86; porta 0,937; medição 0,995; memória 2 s (defasagem); eficiência 0,14; fibra 0,3 dB/km |
| `theoretical_ops` | `siv_2024_theoretical_ops` | o mesmo hardware com operações locais **ideais** (porta = medição = 1). Não é um nó demonstrado: é a condição de referência em que a purificação BBPSSW se comporta como na teoria |

A diferença entre as duas isola o efeito do ruído de porta. Com as portas
demonstradas uma rodada de BBPSSW não eleva a fidelidade de um par já
trocado (0,709 → 0,697), então sob `literature` a purificação é um teto, não
um recurso; sob `theoretical_ops` cada rodada ganha ≈0,04 e custa pares.
Geração, perdas e swap (probabilidade de sucesso) são idênticos nas duas
condições - para a mesma semente a sequência de eventos de geração é a
mesma, só a fidelidade muda, enquanto nenhuma purificação for executada.

Pontos de referência de fidelidade (`ibqn.physics`, par elementar 0,86):

| | 1 swap | 2 swaps | 3 swaps | 1 swap + 1/2/3 rodadas | 2 swaps + 1/2/3 rodadas |
|---|---|---|---|---|---|
| `literature` | 0,709 | 0,595 | 0,509 | não melhora | não melhora |
| `theoretical_ops` | 0,746 | 0,654 | 0,578 | 0,784 / 0,823 / 0,860 | 0,683 / 0,717 / 0,753 |

## Topologias (`experiments.realistic_topologies`)

Enlaces de 5 km (escala das demonstrações em fibra instalada), 4 memórias
nos extremos e 8 nos repetidores, canais clássicos que seguem a fibra
(25 µs por enlace de 5 km).

| Nome | Forma | Uso |
|---|---|---|
| `chain1` | a – r1 – b | um swap; rota única |
| `chain2` | a – r1 – r2 – b | dois swaps |
| `diamond` | r1 → r3 por `bad` (2 enlaces de 20 km em fibra instalada, 0,49 dB/km: menos saltos, maior fidelidade, ~1 par/s) ou por `good1`–`good2` (3 enlaces de 5 km: menor fidelidade, ~150 pares/s) | divergência entre critérios de rota |
| `mesh` | grade 2×4; intent a0 → b2 (3 saltos, três rotas equivalentes) | diversidade de rotas com hardware uniforme |
| `star` | `center` com 6 memórias, 4 folhas | contenção multi-intent |

O canto oposto da malha (a0 → b3, 4 saltos) fica fora do alcance do
hardware da literatura: três swaps deixam F = 0,509, o limiar de
separabilidade. Por isso o intent da malha usa um par a três saltos e
nenhum alvo de fidelidade da suíte fica abaixo de 0,5.

## Campanhas

Janelas de reserva de 0,1–0,3 s (dezenas de pares fim-a-fim a ~150 pares/s);
o objetivo de entrega padrão é 10 pares.

| Id | Pergunta | Grade | Sementes | Saída |
|---|---|---|---|---|
| R00 | O modelo de geração dos planejadores reproduz o simulador? | cadeias de 0–3 repetidores × {2, 5, 10} km × {2, 4} memórias | 12 | `audit/generation_model_audit*.csv` |
| R00b | Swaps e purificações só consomem pares íntegros? | 13 reservas representativas | 3 | `audit/state_integrity_audit.csv` |
| R01 | O que cada camada da arquitetura acrescenta? | diamante; SeQUeNCe nativo, provisionamento estático, IBQN sem/com garantia, com reconciliação, com planejador ciente de recursos, oráculo offline | 20 | `baselines/R01_architecture_baselines/` |
| R02 | O critério de rota importa? | diamante e malha × {menos saltos, menor perda, maior fidelidade} | 20 | `raw/R02_routing/` |
| R03 | O que cada política de purificação entrega? | chain1 e chain2 × 7 alvos × {desligada, uma rodada, automática, iterativa} | 20 | `raw/R03_purification/` |
| R04 | Como evolui a qualidade de decisão do planejador? | 22 intents (4 topologias; regimes generoso, recursos marginais, fidelidade marginal, 1 e 2 rodadas) × {L1, L2, L2-R, L3, L3-R, L2-RB, L3-RB} | 10 | `planner_study/R04_planner_evolution/` |
| R04b | Planejador com simulação no laço (L4) | 3 intents em chain1 | 10 | `planner_study/R04b_simulation_planner/` |
| R05 | As rejeições de R04 eram corretas? | oráculo offline sobre cada caso rejeitado (todas as rotas simples, semente disjunta) | as de R04 | `oracle/R05_oracle_by_planner/` |
| R06 | A reconciliação recupera intents violados? | 6 casos: troca de rota, mais duração, mais memórias, margem de decoerência, perda severa, teto de fidelidade | 20 | `reconciliation/R06_reconciliation/` |
| R07 | Quanto custa a orquestração? | chain1 (rota única); IBQN instrumentado, SeQUeNCe nativo, estático | 20 | `overhead/R07_overhead/` |
| R08 | O que significam memórias reservadas e duração? | chain1 × {2, 4} memórias × {0,15; 0,3} s | 20 | `raw/R08_resource_semantics/` |
| R09 | Vários intents sobre recursos compartilhados | não conflitante (malha), contenção e admissão sequencial (estrela) × {L1, L2-RB} | 10 | `multi_intent/R09_multi_intent/` |

Decisões de desenho que diferem das campanhas antigas:

- **Condições de sucesso = objetivos declarados** (`build_intent`): pares
  entregues ≥ objetivo e fidelidade média ≥ alvo. As campanhas antigas
  herdavam a comparação com o número de memórias reservadas.
- **R04 roda todos os níveis sobre o mesmo caso num único job**
  (`run_planner_case_job`): o que a rede faz com um plano admitido depende
  só de topologia, intent, semente, rota e modo de purificação executado,
  então níveis que escolhem o mesmo plano compartilham uma simulação. Os
  registros são idênticos aos de execuções separadas
  (`tests/experiments/test_planner_execution_cache.py`).
- **Família L3 coletada com limiar de admissão 0**: todo ensaio carrega a
  probabilidade prevista e o desfecho real; limiares são aplicados na
  análise, nunca ajustados nas sementes de teste.
- **R07 numa topologia de rota única**: no diamante as condições escolhem
  rotas diferentes e seus tempos de simulação não são comparáveis.
- **L2-R é mantido como está** (lei de geração "mesmo ciclo", calibrada
  para o hardware idealizado): sob hardware calibrado ele rejeita tudo, e
  é esse resultado que motiva o modelo com buffer (L2-RB/L3-RB,
  `docs/generation_model_audit.md`).

## Estatística (`scripts/realistic/analyze_suite.py`)

- proporções (satisfação, recuperação, falsa viabilidade, falsa rejeição):
  intervalo de Wilson, 95%;
- médias (pares entregues, fidelidade): intervalo t de Student, 95%, sobre
  sementes;
- **falsa viabilidade** = VIOLATED / (SATISFIED + VIOLATED) entre os intents
  admitidos que executaram; **falsa rejeição** = satisfazíveis segundo o
  oráculo / testados pelo oráculo, entre os rejeitados. Populações
  diferentes, nunca combinadas num único número.

As sementes são pareadas entre condições (a semente *k* de cada célula usa
o mesmo gerador), e o oráculo e a reconciliação usam sementes disjuntas das
do ensaio que avaliam (`ORACLE_SEED_OFFSET`, `RECONCILIATION_SEED_OFFSET`).

## Custo

Um ensaio de 0,3 s simulados custa 10–90 s de parede (≈0,5 M eventos por
segundo simulado numa cadeia de 5 km). A suíte completa leva ~7 h com 8
processos. Cada processo trabalhador carrega numpy/scipy com BLAS de uma
thread (`experiments.parallel.limit_worker_numeric_threads`): com BLAS
multi-thread cada processo reserva ~1,1 GB de memória comprometida numa
máquina de 16 threads (contra ~0,2 GB), o suficiente para o sistema matar
trabalhadores numa máquina de 16 GB.
