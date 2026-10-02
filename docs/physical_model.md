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
| `NeverPurify` | nenhuma | `never` | nenhuma regra de purificação dispara (as condições do SeQUeNCe caem no `else` para valores desconhecidos). Um par fim-a-fim abaixo do alvo nunca poderá ser entregue: a aplicação o libera e o contabiliza (ver "Pares que não podem ser entregues") |
| `PurifyOnce` (novo) | 1 rodada | `once` | modo nativo: cada par é purificado no máximo uma vez; um par que já teve sua rodada e continua abaixo do alvo é liberado |
| `PurifyUntilTarget` (L1) | 1 rodada | `until_target` | modo nativo padrão: purifica qualquer par abaixo do alvo, inclusive já purificados. A discrepância estimativa/execução é o fenômeno estudado em `false_rejection_root_cause.md`, preservado de propósito |
| `IterativeAnalyticalPurification` (L2) | n rodadas | `until_target` | idem |

Confirmado na sonda: `never` → 0 eventos EP e 0 entregas quando o alvo
(0,78) excede o swap (0,73); `once` → 0 entregas (uma rodada dá
0,767 < 0,78); `until_target` → 302 rodadas, 90 entregas ≥ 0,78.

**A política do intent prevalece sobre a do plano.** Um intent com
`policy.allow_purification = False` é executado com o modo `never`,
qualquer que seja a estratégia que planejou a rota
(`planning.purification.executed_purification_mode`, aplicado num único
ponto, `SequenceExecutor._deploy_plan`). O lado do planejamento sempre
respeitou a flag (`decide` não conta com purificação); o lado da execução
precisa respeitá-la separadamente desde que a fidelidade passou a ser lida
do estado: um par que atendia ao alvo no plano pode decoerir abaixo dele
em execução, e `until_target` o purificaria contra a política declarada.
O modo registrado nos resultados (`purification_mode`) é o executado.

### Pares que não podem ser entregues

Sob `never`, um par fim-a-fim abaixo do alvo nunca será entregue; sob
`once`, o mesmo vale para um par que já teve sua rodada. O `RequestApp`
original deixa esses pares ocupando as duas memórias até o corte
(`cutoff_ratio·T` = 1 s com a memória de SiV, mais que a janela inteira de
uma reserva de 0,3 s), o que esgota o pool e zera a geração - um artefato
da aplicação, não da política. `IntentRequestApp` libera a memória
(`_is_undeliverable` → `_discard`) e registra um evento `IBQN_DISCARD` por
par, do lado do iniciador; a contagem chega à evidência do intent
(`IntentEvidence.discarded_pairs`) e às tabelas (`discarded_pairs`). Sob
`until_target` nada é descartado: as regras de purificação ainda são donas
do par.

## Desvios em relação ao SeQUeNCe de fábrica

Há **dois** patches de runtime, em `network.sequence_patches`, ambos só
alcançáveis sob o formalismo BDS (sob `ket_vector` a execução é
byte-idêntica ao SeQUeNCe original). O código do submódulo não é alterado.

**Patch 1 - pareamento da purificação.**
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

**Patch 2 - decoerência quando metade do par já foi consumida.** Os dois
extremos de um par ficam sabendo do resultado de um protocolo em instantes
diferentes: na purificação, quem pede sabe um atraso clássico antes de quem
aguarda; num swap, cada extremo sabe depois do seu próprio atraso até o nó
que trocou. O extremo que sabe primeiro pode consumir sua metade (entregá-la
à aplicação, que reinicia a memória) enquanto o outro ainda guarda a sua.
Os protocolos BDS do SeQUeNCe, porém, atualizam **as duas** memórias do par
a partir de qualquer extremo (`self.memory.bds_decohere()` e
`remote_memory.bds_decohere()` em `BBPSSW_BDS.start`/`received_message`,
`EntanglementSwappingA_BDS.start`, `EntanglementSwappingB_BDS.received_message`),
e `Memory.bds_decohere` grava o estado decoerido sob as duas chaves. Com uma
metade já consumida, o SeQUeNCe original faz uma de duas coisas:

- (a) **aborta a simulação**: `Memory.reset` remove o estado da memória
  consumida e `Memory.excite` carimba `last_update_time` para a próxima
  tentativa antes de existir um estado novo; `bds_decohere` nessa memória
  levanta `KeyError`. Exige que a memória consumida seja reexcitada dentro
  da janela entre as atualizações dos dois extremos - impossível com atraso
  clássico uniforme (uma nova tentativa leva ao menos dois round-trips), mas
  não com atrasos que seguem a fibra: na rota de três saltos do diamante o
  respondedor está a 75 µs do iniciador e a 25 µs do vizinho, e reexcita
  50 µs depois de entregar;
- (b) **grava um estado fantasma**: decoerir a metade ainda guardada
  regrava o estado do par antigo também sob a chave da memória consumida.
  Raramente danoso (o próximo reset ou o próximo par heraldado o
  substitui), mas é um estado que o simulador não deveria conter, e se a
  memória consumida já tivesse sido reentrelaçada ele sobrescreveria o par
  novo.

`ibqn_bds_decohere` mantém o canal de Pauli original e muda só o alcance:
não faz nada numa memória sem estado, e a regravação nunca toca uma chave
parceira que não se refere mais ao mesmo par. É também a contabilidade
física correta: a metade consumida parou de decoerir ao ser consumida, a
metade guardada continua decoerindo até o seu nó consumi-la, e é essa a
fidelidade que o nó registra.

A auditoria de integridade (`scripts/realistic/audit_state_integrity.py` →
`results/realistic/audit/state_integrity_audit.csv`; 39 reservas em cadeias,
diamante e malha, três modos de purificação, coerência de 2 s a 5 ms)
classifica cada chamada: de 34.076 chamadas de decoerência, 34 eram o caso
(a) e 549 o caso (b), nenhuma sobre uma memória reentrelaçada; **todas as
4.548 entradas de swap e 3.608 entradas de purificação eram pares que os
dois extremos ainda guardavam**, nenhuma simulação abortou e nenhuma
terminou com estado pendurado. Ou seja: a corrida existe só no caminho de
entrega (a metade do par já entregue), nunca alimenta um swap ou uma
purificação com um par inexistente.

Tudo isso está testado em `tests/unit/test_sequence_patches.py`; os patches
são reversíveis (`remove_sequence_patches`).

## Canais clássicos que seguem a fibra

`NetworkTopologySpec.classical_delay_model = "fiber"` (usado por todas as
topologias calibradas, `experiments.realistic_topologies`) dá a cada par de
nós o atraso do menor caminho em fibra entre eles, a 2·10⁸ m/s (5 µs/km),
em vez de um único atraso para todos os pares. Um enlace de 5 km tem
25 µs de ida; os extremos de uma rota de três saltos, 75 µs. O modo
`"uniform"` (padrão, legado) mantém o comportamento anterior.

Consequência medida no ciclo de tentativa de geração (protocolo
single-heralded; `docs/generation_model_audit.md`): cada tentativa é
precedida de dois handshakes - o pareamento dos protocolos pelos resource
managers (REQUEST do nó anterior na rota, RESPONSE de volta) e a negociação
do instante de emissão, aberta pelo nó *primário* (o de nome
lexicograficamente maior). Se o primário é quem recebeu o REQUEST, os dois
handshakes se sobrepõem e a tentativa leva **4 atrasos** de ida; se o
primário é quem pediu, ele precisa esperar o RESPONSE e a tentativa leva
**5 atrasos**. O mesmo enlace físico é 20% mais lento num sentido da rota
que no outro - um artefato do simulador que o modelo de geração dos
planejadores reproduz (`generation_models.single_heralded_cycle_factor`).

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

- Sob `once`/`never`, o `RequestApp` original deixaria pares que não
  atingem o alvo **presos** nas memórias até o corte, esgotando o pool
  (76 EG_SUCCESS vs. 1944 em `until_target` na sonda, antes da correção).
  `IntentRequestApp` os libera e contabiliza - ver "Pares que não podem ser
  entregues".
- A regra de swap do SeQUeNCe escolhe o parceiro pela **ordem de índice**
  das memórias, não pela idade do par. Quando há mais de um par esperando
  no mesmo nó, os de índice alto podem esperar dezenas de milissegundos
  (até 130 ms numa janela de 0,3 s na cadeia de dois repetidores) e
  decoerem nesse tempo. É o comportamento real do simulador e uma fonte
  física da dispersão de fidelidade entregue.
- Os dois extremos de um par fim-a-fim avaliam a fidelidade em instantes
  diferentes (cada um ao receber o resultado do último swap). A diferença é
  a decoerência de dezenas de microssegundos (ΔF ~ 10⁻⁵ com T = 2 s); um
  alvo dentro dessa faixa faria um extremo entregar e o outro não. Não foi
  observado nas campanhas e não é tratado.
- A taxa de geração muda em relação ao ket: o single-heralded exige a
  chegada dos dois fótons e tem sucesso de BSM 1/2 por tentativa.
- Sob `ket_vector`, a sonda mostra que o estado armazenado é sempre um par
  de Bell puro (overlap 1,0) - motivo pelo qual esse modelo não deve mais
  ser usado para afirmações sobre fidelidade.
