# Modelo físico (revisão de realismo físico)

Esta revisão remove três limitações do modelo físico que existiam desde a
Fase 3 e que o manuscrito ICC 2027 (V1/V1-updated) não declarava:

| Antes (formalismo `ket_vector`, padrão até esta revisão) | Depois (formalismo `bell_diagonal`, novo padrão) |
|---|---|
| A fidelidade era um **escalar contábil**: `raw_fidelity` na geração, `f1·f2·swapping_degradation` no swap, fórmula de Dür–Briegel na purificação. O estado quântico armazenado era sempre um par de Bell perfeito - a fidelidade reportada não era uma propriedade do estado. | A fidelidade é **lida do estado** (`Memory.get_bds_fidelity()` = primeiro elemento diagonal do estado Bell-diagonal). Swap e purificação são composições analíticas de canais de Pauli que dependem de `gate_fidelity`/`measurement_fidelity` de cada nó (`swapping_bds.py`, `bbpssw_bds.py`). |
| O sucesso da purificação era decidido por medição de pares de Bell ideais - taxa de falha sem relação com a probabilidade física p(F) do BBPSSW. | O sucesso segue a probabilidade analítica exata do BBPSSW (`BBPSSW_BDS.purification_res`), p = ab + (1-a)(1-b) para portas ideais. Medido: 29% de falhas em F≈0.73; teoria: 29,5%. |
| **Sem decoerência**: `coherence_time_s = -1` (infinito) por padrão e em todas as campanhas. | **Decoerência contínua** (canal de Pauli despolarizante a taxa 1/T, `Memory.bds_decohere`) enquanto a memória espera, mais um **corte duro** em `cutoff_ratio·T`. Padrão: T = 1 s, `cutoff_ratio` = 0,5. |
| A política de purificação (`NeverPurify`/`PurifyUntilTarget`) afetava **só o planejador**; o SeQUeNCe sempre executava `until_target`. | A estratégia declara um `execution_mode` (`never` / `once` / `until_target`) que o executor instala na `Reservation` real - a decisão do plano **é executada**. |

O modelo legado continua disponível (`formalism: ket_vector`) para
reprodutibilidade dos resultados antigos, byte-a-byte idêntico ao anterior
quando os novos parâmetros ficam nos defaults.

## O que o SeQUeNCe 1.0 oferece e o que a IBQN precisou fazer

O formalismo Bell-diagonal (BDS) é suportado nativamente pelo SeQUeNCe, mas
ativá-lo de fato exige quatro chaves globais independentes (só a primeira é
setada por `Timeline(formalism=...)`):

1. `QuantumManager` (representação do estado);
2. `EntanglementGenerationA/B.set_global_type(SINGLE_HERALDED)` - a geração
   Barrett-Kok é baseada em circuito e não escreve estados BDS; o protocolo
   *single-heralded* é o único que os escreve, e exige um `SingleHeraldedBSM`
   no nó intermediário (`encoding_type: single_heralded` no template do BSM);
3. `EntanglementSwappingA/B.set_formalism('bell_diagonal')`;
4. `BBPSSWProtocol.set_formalism('bell_diagonal')`.

Sem 3 e 4, um `Timeline` BDS ainda rodaria swap/purificação por circuito e
falharia no primeiro swap. `network.sequence_adapter.configure_sequence_globals`
seta as quatro de forma consistente, na construção e em `init()` (os
protocolos são criados preguiçosamente durante a simulação).

Além disso:

- **Parâmetros de hardware viajam por `templates` do `RouterNetTopo`**
  (um template por roteador, um por enlace), não por `update_memory_params`
  após a construção: `Memory.__init__` deriva `decoherence_rate = 1/T` uma
  única vez, então setar `coherence_time` depois deixava a decoerência
  contínua silenciosamente desligada.
- **`gate_fidelity`/`measurement_fidelity` são setados diretamente nos
  roteadores** (`Node.gate_fid`/`meas_fid`): o `RouterNetTopo` 1.0 define
  as chaves de configuração mas nunca as repassa ao construtor.
- **`swapping_degradation` não pode ser passado sob BDS**:
  `es_rule_action_A` o repassa como kwarg `degradation=` que só a classe de
  circuito aceita. O ruído de swap sob BDS vem de `gate_fidelity`/
  `measurement_fidelity`.

## Parâmetros por nó (`NodeSpec`) e por enlace (`QuantumLinkSpec`)

| Parâmetro | Padrão | Usado por | Efeito |
|---|---|---|---|
| `raw_fidelity` | 0,85 | ambos | fidelidade do par elementar recém-gerado |
| `gate_fidelity` | 1,0 | BDS | ruído de porta de dois qubits em swap e purificação |
| `measurement_fidelity` | 1,0 | BDS | ruído de medição em swap e purificação |
| `swapping_success_prob` | 1,0 | ambos | probabilidade de a BSM do swap ter sucesso |
| `swapping_degradation` | 0,95 | **só ket** | fator multiplicativo por swap (legado) |
| `coherence_time_s` | 1,0 | ambos | BDS: decoerência contínua + corte; ket: só corte. Negativo = infinito |
| `cutoff_ratio` | 0,5 | ambos | memória expira (volta a RAW) em `cutoff_ratio·T` |
| `decoherence_errors` | `None` → [1/3,1/3,1/3] | BDS | distribuição dos erros X/Y/Z |
| `memory_efficiency`, `memory_frequency_hz` | 1,0 / 80 MHz | ambos | emissão e taxa máxima de excitação |
| `detector_efficiency` (enlace) | `None` → 0,9 | ambos | eficiência dos dois detectores da BSM intermediária |

Por que `cutoff_ratio = 0,5`: sob decoerência despolarizante, um par com
F₀ = 0,85 cai para F = 0,41 em t = T (abaixo do limiar 0,5 em que o BBPSSW
deixa de funcionar e o `BBPSSWProtocol.start` aborta a simulação); em
t = 0,5·T ainda está em F ≈ 0,65. O corte em 0,5·T mantém pares frescos
purificáveis durante toda a vida útil.

## Fidelidade como propriedade do estado: o que muda nos resultados

Na sonda de validação (cadeia de 3 nós, T = 1 s, janela de 0,1 s):

- 665 pares entregues com fidelidade média 0,7288 e **147 valores distintos**
  (antes: todos exatamente 0,6864). O valor fechado do swap de dois pares
  Werner 0,85 é 0,73; a diferença é a decoerência durante a espera pelo
  segundo enlace.
- 0 divergências entre o escalar reportado (`MemoryInfo.fidelity`) e o
  estado armazenado, em 665 pares.
- Com T = 10 ms a média cai para 0,64; com T = 2 ms nenhum par atinge o alvo
  0,6 (resultado VIOLATED, não erro de simulação).
- Com `gate_fidelity = measurement_fidelity = 0,98`: média 0,6945; a fórmula
  fechada prevê 0,6956.

O acerto do planejador deixa de ser tautológico: a estimativa usa as mesmas
fórmulas fechadas, mas o resultado real depende de tempos de espera
estocásticos.

## Política de purificação executada

`planning.purification.PurificationStrategy.execution_mode` →
`ExecutionPlan.purification_mode` → `IntentRequestApp.start_intent` seta
`Reservation.purification_mode`. O objeto `Reservation` é criado
sincronamente dentro de `RequestApp.start` e relatado por **referência** a
todos os nós do caminho (`ClassicalChannel.transmit` agenda o próprio objeto
de mensagem); cada nó lê o modo só quando o APPROVE volta e
`generate_load_rules` monta as regras. (`RSVPProtocol.set_purification_mode`
existe, mas o valor nunca é copiado para a reserva no SeQUeNCe 1.0.)

| Estratégia | Estimativa | `execution_mode` | Semântica na execução |
|---|---|---|---|
| `NeverPurify` | nenhuma | `never` | nenhuma regra de purificação dispara (as condições do SeQUeNCe caem no `else` para valores desconhecidos). Pares abaixo do alvo ficam presos até expirar - as regras de swap exigem ambas as entradas ≥ alvo |
| `PurifyOnce` (novo) | 1 rodada | `once` | modo nativo: cada par é purificado no máximo uma vez |
| `PurifyUntilTarget` (L1) | 1 rodada | `until_target` | modo nativo padrão: purifica qualquer par abaixo do alvo, inclusive já purificados. A discrepância estimativa/execução é o fenômeno estudado em `false_rejection_root_cause.md`, preservado de propósito |
| `IterativeAnalyticalPurification` (L2) | n rodadas | `until_target` | idem |

Confirmado na sonda: `never` → 0 eventos EP e 0 entregas quando o alvo
(0,78) excede o swap (0,73); `once` → 9 rodadas, 0 entregas (uma rodada dá
0,767 < 0,78); `until_target` → 302 rodadas, 90 entregas ≥ 0,78.

## Desvios em relação ao SeQUeNCe de fábrica

Há **um** patch de runtime, em `network.sequence_patches`, ativo apenas
enquanto o formalismo BDS está ativo (sob `ket_vector` delega à função
original, byte-idêntico):

`ep_rule_condition_request` (qual par de memórias uma rodada de BBPSSW
consome, no lado que pede) é substituída porque a versão original exige
**igualdade exata** de fidelidade entre as duas memórias. Isso é um proxy
para "pares da mesma geração" que vale trivialmente no modelo escalar, mas
sob BDS com decoerência as fidelidades são lidas do estado decoerido e
praticamente nunca coincidem bit a bit após um swap ou uma rodada - o que
desligava silenciosamente (a) toda rodada após a primeira num enlace e (b)
toda purificação fim-a-fim. `BBPSSW_BDS.purification_res` trata entradas
desiguais exatamente, então a igualdade nunca foi exigência física.

A substituição: (1) pareia com o candidato de fidelidade **mais próxima**
(iguais continuam preferidos → reproduz a escolha original quando ela
existe); (2) exige que **ambos** os pares estejam abaixo do alvo (nunca
sacrifica um par que já serve); (3) exige que a fidelidade **viva** do
estado (com a decoerência de ambas as memórias aplicada até agora - o mesmo
que o protocolo faz primeiro em `start`) seja > 1/2, porque o snapshot
escalar do outro extremo pode já estar < 1/2 e derrubar a simulação
(observado com T = 10 ms). Aplicar o canal antes é fisicamente neutro: o
canal de Pauli é markoviano. Modos, escopo de memórias e a divisão
pede/aguarda entre os extremos são preservados.

Tudo isso está testado em `tests/unit/test_sequence_patches.py`; o patch é
reversível (`remove_sequence_patches`).

## Fórmulas fechadas usadas pelo planejador (`ibqn.physics`)

Portes literais do código do SeQUeNCe, fixados por
`tests/unit/test_physics.py` contra os métodos reais avaliados em objetos
reais do simulador:

- `bds_swap_fidelity(F₁, F₂, g, m)` ← `EntanglementSwappingA_BDS.swapping_res`
  (ramo *twirled*). Para g = m = 1 o parâmetro de Werner w = (4F-1)/3
  multiplica: 0,85 ⊗ 0,85 → 0,73.
- `bds_purification_step(F_k, F_m, g_o, m_o, g_r, m_r)` →
  (p_sucesso, F') ← `BBPSSW_BDS.purification_res`. Para portas ideais
  reduz-se a Dür–Briegel (`BBPSSWCircuit.improved_fidelity`), por isso
  `IDEAL_BBPSSW` reproduz exatamente todos os números pré-revisão.
- `bds_decohered_fidelity(F, t, T, erros)` ← `Memory.bds_decohere`
  (linha I da matriz de transformação sobre elementos Werner).
- `ket_swap_fidelity`, `ket_purification_step`: o modelo legado.

`NetworkCapabilities.physics` (`PhysicsModel`) despacha pelo formalismo; os
estimadores (`ConservativeMinEstimator`, `SequenceConsistentEstimator`),
`feasibility.estimate_swap_only_fidelity` e todos os planejadores L1–L4
passam a usá-lo. A decoerência **não** entra na estimativa (o planejador
não modela tempos de espera) - é uma fonte física, documentada, de erro
planejador-vs-realidade.

Limitações do modelo do planejador que permanecem (e agora são físicas, não
tautológicas): o SeQUeNCe purifica **cada estágio** até ≥ alvo antes do
próximo swap (enlaces, depois o par intermediário, depois o fim-a-fim),
enquanto os estimadores modelam "swap, depois purificação fim-a-fim"; sob
enlaces heterogêneos (`raw_fidelity` diferente nos dois extremos) o estado
BDS do par recebe a `raw_fidelity` do extremo cujo protocolo roda primeiro,
e cada extremo reporta a sua própria - o estimador usa o mínimo.

## Efeitos colaterais conhecidos do modo BDS

- Sob `once`/`never`, pares que não atingem o alvo ficam **presos** nas
  memórias até o corte (`cutoff_ratio·T`) - com T = 1 s e janelas de 0,1 s,
  isso esgota o pool e zera a taxa de geração (76 EG_SUCCESS vs. 1944 em
  `until_target` na sonda). É a semântica do SeQUeNCe e uma consequência
  real da política, não um bug.
- A taxa de geração muda em relação ao ket: o single-heralded exige a
  chegada dos dois fótons e tem sucesso de BSM 1/2 por tentativa.
- Sob `ket_vector`, a sonda mostra que o estado armazenado é sempre um par
  de Bell puro (overlap 1,0) - motivo pelo qual esse modelo não deve mais
  ser usado para afirmações sobre fidelidade.
