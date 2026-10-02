# Resultados da suíte calibrada (2026-10-02)

Resumo do que as campanhas de `docs/realistic_campaigns.md` mostraram. Os
números vêm de `results/realistic/processed/*.csv` (gerados por
`scripts/realistic/analyze_suite.py`); o manuscrito (`paper_ibqn_v2/`) os lê
por macros geradas, nunca digitadas. Aqui eles estão transcritos para
leitura - em caso de divergência, vale o CSV.

Duas condições de hardware em tudo: **literatura** (nó SiV com valores
demonstrados) e **operações ideais** (mesmo hardware, portas e medição
perfeitas). 20 sementes por célula, salvo indicação.

## 0. A rede simulada está correta? (auditorias)

- **Integridade** (39 reservas): todas as 4.656 entradas de swap e 3.704 de
  purificação eram pares que os dois extremos ainda guardavam; nenhuma
  simulação abortou; nenhum estado pendurado. A corrida de "meio par já
  consumido" ocorreu em 584 de 34.906 atualizações de decoerência, sempre
  no caminho de entrega.
- **Modelo de geração** (312 execuções): ciclo de tentativa de 4,00 ou 4,99
  atrasos clássicos conforme o sentido da reserva (modelo: 4 e 5);
  probabilidade por tentativa dentro de ~1σ da fórmula; o simulador
  entrega 0,984 do que a lei com buffer prevê no agregado (1,005 na
  segunda metade da janela; erro médio de 4,8% por célula). A lei "mesmo
  ciclo" subestima a taxa por 115–233× com um repetidor (133× no
  agregado) e por 10⁴–10⁷× com dois e três.
- **Garantia**: 4.100 intents executados, 0 divergências entre o veredito e
  a evidência de entrega; nenhum dos 1.680 rejeitados recebeu avaliação.
- A fidelidade entregue fica abaixo da estimada pelo tempo de espera na
  memória: 0,587 contra 0,595 na rota de três enlaces de 5 km do diamante;
  0,672 contra 0,709 na rota de dois enlaces de 20 km.

## 1. Roteamento (R02) e semântica de recursos (R08)

- Diamante: "menos saltos" e "maior fidelidade" escolhem a rota de dois
  enlaces de 20 km e entregam 1,15 par por janela (0% satisfeito); "menor
  perda" escolhe a rota de três saltos e entrega 43,45 pares (100%; 44,30
  com operações ideais). Na malha as três estratégias escolhem a mesma
  rota (48,65 pares).
- Cadeia de um repetidor, meta de 20 pares: 2 memórias × 0,15 s → 10,7
  pares (0% satisfeito); 2 × 0,3 s → 21,7 (65%); 4 × 0,15 s → 23,25 (80%);
  4 × 0,3 s → 47,2 (100%). A entrega segue memórias × duração (36–39 pares
  por memória-segundo).

## 2. Políticas de purificação (R03)

- **Literatura**: acima da saída do swap (0,709 com um repetidor; 0,595 com
  dois) toda política rejeita - corretamente. Logo abaixo, não purificar é
  melhor: a 0,70 (um repetidor) 37,70 pares sem purificar contra 30,95
  purificando até o alvo (maior em 18 de 20 sementes, menor em 1; Wilcoxon
  p < 10⁻³); a 0,58 (dois repetidores) 36,15 contra 29,65 (19 de 20).
  Com as portas demonstradas uma rodada não eleva a fidelidade (a
  estimativa cai de 0,709 para 0,697): a saída do swap é o teto e a
  purificação só consome pares.
- **Operações ideais**: uma rodada leva um repetidor a 0,76 com 13,6–14,0
  pares por janela (contra ~43–46 a 0,72); duas rodadas (0,80) entregam
  4,15 pares - abaixo da meta de 10 - e três (0,84) nenhum. Com dois
  repetidores nem uma rodada cabe: a 0,67 saem 6,9 pares e 16 de 20
  intents são violados, porque os pares defasam enquanto esperam parceiro
  e precisam ser purificados de novo.
- Mesmo com operações ideais, para alvos abaixo da saída do swap não
  purificar entrega mais (0,72 com um repetidor: 46,10 contra 43,15,
  p = 0,003).

## 3. Evolução do modelo de planejamento (R04, R04b, R05)

22 intents × 10 sementes por condição (220 por modelo). Falsa viabilidade =
violados / admitidos que executaram; falsa rejeição = satisfazíveis segundo
o oráculo / rejeitados.

| Modelo | Literatura: FV | Literatura: FR | Ideal: FV | Ideal: FR |
|---|---|---|---|---|
| L1 (uma rodada) | 53/160 (33%) | 0/60 | 68/190 (36%) | 8/30 (27%) |
| L2 (iterativo) | 53/160 (33%) | 0/60 | 89/220 (40%) | — (nada rejeitado) |
| L2-R (recursos, lei "mesmo ciclo") | — (nada admitido) | 122/220 (55%) | — | 168/220 (76%) |
| **L2-RB (recursos, lei com buffer)** | **6/120 (5%)** | **5/100 (5%)** | **18/170 (11%)** | **5/50 (10%)** |
| L3-RB (probabilístico, limiar 0,5) | 6/120 (5%) | 3/100 (3%)† | 18/170 (11%) | 3/50 (6%)† |

† medido na própria execução (a família L3 foi coletada com admissão
desligada). L3 e L3-R, sobre a lei "mesmo ciclo", atribuem probabilidade ~0
a todo intent, embora 49–70% sejam satisfeitos quando executados (Brier
0,49–0,70); L3-RB tem Brier 0,032 (literatura) e 0,084 (ideal).

- Os erros de L1/L2 são de **recursos**: admitem intents de 2 memórias e
  0,1 s (27 de 30 violados) e, no diamante, seguem a rota de menos saltos
  (26 de 30 violados). Com operações ideais L1 rejeita os alvos de duas
  rodadas, inclusive a meta de 3 pares que a rede cumpre; L2 os admite
  todos e viola os de meta 10.
- L2-R tem as verificações certas e a lei de geração errada: rejeita os 220
  intents nas duas condições.
- L2-RB troca só a lei de geração. Erros restantes: todos os falsos
  rejeitados são intents de 2 memórias e 0,1 s cuja entrega esperada fica
  abaixo da meta; todas as violações na literatura são a meta de 1 par a
  0,65 na rota de enlaces de 20 km do diamante, cuja entrega esperada é
  de 1 par: a janela terminou sem nenhum par na fidelidade pedida (em 4
  das 6 sementes nenhum par fim-a-fim se formou; em 2 o único par tinha
  defasado para 0,636 e 0,643 - as mesmas sementes na campanha R02, com
  alvo 0,55, mostram esses pares). É admissão pelo valor esperado, sem
  margem. Com operações ideais, 17 das 18 violações são alvos a uma
  rodada de purificação em rotas de dois swaps (decoerência durante a
  espera, que nenhum planejador modela).
- L4 (simulação no laço), na grade reduzida de 60 ensaios: mesma decisão
  de admissão que L2-RB em 60 de 60, a ~110–120 s de planejamento por
  intent (três simulações internas, máquina compartilhada) contra ~1 ms
  dos modelos determinísticos e ~10 ms dos probabilísticos.

## 4. Reconciliação (R06) e baselines (R01)

- Literatura: 79 de 99 intents violados recuperados no segundo episódio -
  troca de rota 20/20, mais memórias 20/20, mais duração 39/59 (inclui os
  20 casos de enlaces de 10 km, dos quais nenhum se recupera: dobrar a
  janela ainda entrega 15,6 dos 30 pares). Alvo acima do teto: rejeitado
  no planejamento em 20/20. Alvo 0,705 (logo abaixo do swap): violado em
  20/20 na literatura (pares defasados são liberados) e recuperado com
  mais duração; satisfeito em 20/20 com operações ideais.
- Diamante, mesma intent em cada camada: provisionamento estático e IBQN
  com garantia entregam 1,15 par (a garantia classifica VIOLATED em 20/20);
  com reconciliação, 100% satisfeitos em dois episódios; com o planejador
  L2-RB, 100% em um episódio, igual ao oráculo. O SeQUeNCe nativo também
  entrega 43,45 pares porque seu roteamento por distância prefere a rota
  de três saltos - mas não conhece a meta nem reporta desfecho.

## 5. Multi-intent (R09) e overhead (R07)

- Sem conflito (malha): 20/20 satisfeitos. Contenção no centro da estrela:
  os dois intents são admitidos pelos planejadores e, em toda semente, um
  é satisfeito e o outro tem a reserva recusada pelo protocolo de reserva
  do SeQUeNCe e termina FAILED (10/10). Em episódios sequenciais: 20/20.
  Igual para L1 e L2-RB e nas duas condições: nenhum planejador raciocina
  sobre recursos entre intents.
- Orquestração (validação, planejamento, implantação, observação, garantia,
  decisão de reconciliação): mediana de 0,47% do tempo de parede do ensaio
  (máximo 0,61%) na literatura e 0,42% (máximo 0,51%) com operações
  ideais; o planejamento em si, 0,004%.

## O que isso muda no artigo

1. O teto de purificação com portas demonstradas e a falha da lei "mesmo
   ciclo" são achados que só aparecem com hardware calibrado; o artigo V1
   (hardware idealizado) não os tinha.
2. A história "L1 → L2 → L2-R → …" continua, mas o papel de cada modelo
   mudou: o problema dominante é recursos, não fidelidade; L2-R deixa de
   ser "conservador" e passa a ser "errado na lei de geração"; L2-RB é o
   modelo novo, escrito nesta revisão em resposta ao oráculo e à auditoria.
3. Limitação honesta que fica: nenhum planejador modela decoerência nem
   margem estocástica.

O manuscrito (`paper_ibqn_v2/`) tem duas versões construídas das mesmas
macros: a de conferência, de 6 páginas (`main.tex`), e a estendida, de 11
(`main_extended.tex`); ver `paper_ibqn_v2/README.md`.
