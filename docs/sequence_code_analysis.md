# Auditoria Técnica do SeQUeNCe

Documento produzido na Fase 1 (Etapa A) do projeto *Intent-Based Quantum Networking sobre SeQUeNCe*.
Todo o conteúdo abaixo foi verificado por leitura direta do código-fonte e/ou execução real de
simulações no ambiente clonado — nenhuma API foi presumida a partir de documentação externa ou
memória de treinamento. Citações no formato `arquivo:linha` referem-se ao commit identificado abaixo.

## 0. Metadados do repositório

| Item | Valor |
|---|---|
| Repositório | `https://github.com/sequence-toolbox/SeQUeNCe` |
| Caminho local | `SeQUeNCe/` (subpasta deste repositório) |
| Branch | `master` |
| Commit | `1f2680a5b9065e708a7497adc53a95b108029b98` (`chore: bump python-semantic-release/python-semantic-release from 10.5.3 to 10.6.1 (#405)`) |
| `git describe --tags` | `v1.0.0-26-g1f2680a5` (26 commits à frente da tag `v1.0.0`) |
| `pyproject.toml` `version` | `1.0.0` |
| Python exigido | `>=3.12, <3.15` (testado aqui com Python 3.13.14) |
| Build backend | `uv_build`, layout "flat" (`module-root=""`, `module-name="sequence"` — o pacote `sequence/` está na raiz do repo, não em `src/`) |
| Licença | ver `LICENSE` |

### Dependências principais (`pyproject.toml`)

`numpy`, `scipy`, `networkx`, `pandas`, `matplotlib`, `seaborn`, `plotly`, `pyyaml`, `tqdm`, `typer`,
`qutip` + `qutip-qip` (formalismos de estado quântico), `stim` (estabilizador), `gmpy2` (aritmética de
alta precisão usada em `optical_channel.py` para janelas de tempo), `dash` + `dash-cytoscape` (GUI),
`jupyterlab`/`ipywidgets` (notebooks). Grupo de desenvolvimento: `pytest`, `pytest-cov`, `ruff`, `ty`
(type checker), `coverage`.

**Nota de ambiente**: a instalação completa via `pip install -e .` falhou neste ambiente Windows por
causa de caminhos longos gerados pelos *labextensions* do JupyterLab (limitação do Windows, não do
SeQUeNCe — ver `docs/limitations.md`/seção 4.7). Contornado instalando o pacote em modo editável sem
dependências (`pip install -e . --no-deps`) seguido da instalação manual de todas as dependências de
execução exceto `jupyterlab`/`dash*`/`ipywidgets`. O ambiente resultante roda o simulador e a suíte de
testes normalmente.

### Estrutura de diretórios (raiz do clone)

```
SeQUeNCe/
├── sequence/                     # pacote principal (importado como "sequence")
│   ├── kernel/                   # motor de simulação por eventos discretos
│   │   ├── timeline.py, entity.py, event.py, process.py, eventlist.py
│   │   └── quantum_manager/, quantum_state/   # backends de estado quântico (ket, density matrix, BDS, stabilizer, Fock)
│   ├── components/                # hardware: memory.py, optical_channel.py, bsm.py, detector.py, photon.py, ...
│   ├── entanglement_management/
│   │   ├── entanglement_protocol.py
│   │   ├── generation/            # Barrett-Kok (barret_kok.py), single_heralded.py
│   │   ├── purification/          # BBPSSW (bbpssw_protocol.py, bbpssw_bds.py, bbpssw_circuit.py)
│   │   └── swapping/               # swapping_base.py, swapping_bds.py, swapping_circuit.py
│   ├── resource_management/       # resource_manager.py, memory_manager.py, rule_manager.py, action_condition_set.py
│   ├── network_management/        # network_manager.py, reservation.py, rsvp.py, memory_timecard.py, routing/, forwarding.py
│   ├── topology/                   # node.py, topology.py, router_net_topo.py, dqc_net_topo.py, qkd_topo.py
│   ├── app/                        # request_app.py, random_request.py, teleport_app.py
│   ├── qkd/                        # BB84, cascade (fora do escopo do projeto)
│   ├── utils/
│   │   ├── metrics/                # registry.py, event_types.py, metric_types.py, storage.py, builtins.py — TELEMETRIA NATIVA (ver §4.6)
│   │   ├── log.py, encoding.py, noise.py, config_generator_cli.py, draw_topo.py, nx_converter.py
│   ├── constants.py, message.py, protocol.py
│   └── gui/                        # dashboard Dash (fora do escopo)
├── example/                        # exemplos oficiais (ver §0.1)
├── tests/                          # suíte de testes oficial (ver §0.2)
└── docs/                           # Sphinx (RTD) — não confundir com o docs/ deste projeto
```

### 0.1 Exemplos oficiais executados

| Exemplo | Conteúdo | Executado? |
|---|---|---|
| `example/demo_for_beginners/two_node_eg.ipynb` | Geração de entrelaçamento (Barrett-Kok) entre 2 roteadores + 1 nó BSM, com regras (`Rule`) escritas manualmente | ✅ adaptado para script e executado |
| `example/demo_for_beginners/three_node_eg_ep_es.ipynb` | Cadeia de 3 roteadores: geração + purificação (BBPSSW) + swapping, via `network_manager.request(...)` (fluxo automático) | ✅ adaptado para script e executado, com e sem purificação forçada |
| `example/demo_for_beginners/random_request_network.ipynb` | Rede estrela de 5 nós carregada de `star_network.json`, aplicações `RandomRequestApp` em cada nó | ✅ código lido e JSON de topologia inspecionado; fluxo confirmado via `RequestApp` real (ver abaixo) |
| `example/demo_for_beginners/teleport_2node.ipynb` | Teleporte de estado usando `TeleportApp`/`DQCNode` | Lido (não executado — fora do escopo imediato de "distribuição de entrelaçamento") |
| `example/starlight/starlight_experiments.py` | Topologia realista (rede Starlight) com múltiplas reservas | Lido, não executado (fora do escopo da Fase 1) |
| `example/qkd/*`, `example/quantum_transduction/*`, `example/absorptive_memory/*` | QKD e variantes de hardware alternativas | Fora do escopo do projeto (entanglement distribution clássico é o alvo) |

Além dos notebooks, foi escrito e executado um script próprio (`scripts` de verificação, fora do
repositório SeQUeNCe) instanciando `RequestApp` diretamente em uma topologia de 3 nós para confirmar
empiricamente os callbacks `get_reservation_result` e `get_memory` (ver §4.2).

### 0.2 Suíte de testes oficial

Executada com `pytest` sobre o ambiente instalado:

```
tests/kernel, tests/entanglement_management, tests/resource_management, tests/network_management  → 154 passed, 1 failed
tests/components, tests/topology, tests/utils, tests/app, tests/qkd                                → 167 passed (isolado), mas 80 falhas de test_teleport.py quando executado *depois* de tests/topology
```

Duas descobertas relevantes para a Fase 2 (e para os requisitos de reprodutibilidade do projeto,
seção 2 do prompt original):

1. **`tests/network_management/test_reservation.py::TestRSVPProtocol::test_RSVPProtocol_schedule`**
   usa `random.randint(...)` **sem seed fixa** dentro do teste (não usa o gerador do `Entity`/`Node`).
   É um teste estatístico mal isolado: falhou uma vez em ~1000 iterações aleatórias por uma asserção
   de contagem exata (`assert counter == memory_size * 2`). Não é falha do nosso ambiente — é uma
   fragilidade pré-existente do teste upstream. **Lição para a Fase 2**: nunca escrever testes que
   dependem de `random`/`numpy.random` globais sem seed; usar sempre o gerador por nó (`get_generator()`).
2. **Poluição de estado global entre módulos de teste**: rodar `tests/topology` antes de
   `tests/app/test_teleport.py` faz 80 dos 80 testes de teleporte falharem; isolados, todos passam.
   Causa raiz: `tests/topology/test_node.py` e `tests/topology/test_dqc_node.py` alteram uma seed/estado
   aleatório global (`numpy.random.seed`/similar) sem restaurá-lo. Isso **confirma experimentalmente**
   a necessidade dos requisitos do projeto (seção 2): todo experimento da nossa camada deve fixar sua
   própria seed por `Timeline`/`Node` e não confiar em estado aleatório ambiente herdado de execuções
   anteriores.

---

## 4.1 Arquitetura do simulador

SeQUeNCe é organizado em 5 camadas sobre um núcleo de simulação a eventos discretos, exatamente como
descrito no paper original e confirmado no código:

```
Kernel (Timeline / Entity / Event / Process / EventList / QuantumManager)
   │
   ▼
Hardware (components/: Memory, MemoryArray, OpticalChannel, BSM, Detector, Photon, Circuit)
   │
   ▼
Entanglement Management (entanglement_management/: generation, purification, swapping — protocolos ponto-a-ponto entre nós)
   │
   ▼
Resource Management (resource_management/: ResourceManager, MemoryManager, RuleManager, action_condition_set)
   │
   ▼
Network Management (network_management/: NetworkManager, RSVPProtocol/Reservation, routing/, ForwardingProtocol)
   │
   ▼
Application (app/: RequestApp, RandomRequestApp, TeleportApp)
```

### Kernel (`sequence/kernel/`)

- **`Timeline`** (`kernel/timeline.py:31`): mantém uma `EventList` (heap min-ordenado por `(time, priority)`,
  `kernel/eventlist.py:13`), um dicionário `entities` e um `QuantumManager`. `init()` (`timeline.py:93`)
  chama `entity.init()` em todas as entidades registradas; `run()` (`timeline.py:99`) laça
  `events.pop()` → `event.process.run()` até a fila esvaziar ou `event.time >= stop_time`. Tempo é
  medido em **picossegundos** (`self.time: int`). `Timeline.seed(seed)` (`:163`, `@staticmethod`) ajusta
  `numpy.random.seed` **global** — mas o padrão recomendado (usado por todo hardware) é
  `Entity.get_generator()` (`kernel/entity.py:92`), que devolve o gerador **por nó**
  (`numpy.random.default_rng(seed)`, ver `topology/node.py:63`, `Node.set_seed`/`get_generator`), isto
  é o mecanismo real de reprodutibilidade por reserva/experimento.
- **`Entity`** (`kernel/entity.py:16`, `ABC`): toda peça de hardware simulável (`Memory`, canais, BSM,
  Photon) herda daqui. Padrão *observer*: `attach/detach/notify` (`:59-71`) — usado por `Memory` para
  avisar expiração, por `BSM`/`Detector` para propagar resultados de medição.
- **`Event`/`Process`** (`kernel/event.py`, `kernel/process.py`): `Event(time, process, priority)` é
  comparável por `(time, priority)` (heap); `Process(owner, activation_method, args, kwargs)` encapsula
  uma chamada de método adiada — `Process.run()` = `getattr(owner, activation)(*args, **kwargs)`. Esse
  par é o mecanismo universal de "agendar algo no futuro" em toda a base de código.
- **`QuantumManager`** (`kernel/quantum_manager/`): backend plugável do estado quântico. Formalismos
  registrados em `constants.py:46-55`: `ket_vector` (padrão), `density_matrix`, `bell_diagonal` (BDS —
  usado nos exemplos de 3 nós, mais barato computacionalmente para redes grandes), `stabilizer`,
  `fock_density`. Selecionado via `Timeline(formalism=...)`.

### Hardware (`sequence/components/`)

- **`Memory`**/**`MemoryArray`** (`components/memory.py`): memória de um único átomo. Parâmetros:
  `frequency, efficiency, coherence_time, raw_fidelity, wavelength, decoherence_errors, cutoff_ratio,
  cutoff_flag`. **Não guarda estado lógico RAW/OCCUPIED/ENTANGLED** — isso é responsabilidade de
  `MemoryInfo` na camada de resource management (fonte da verdade é `Memory.entangled_memory =
  {'node_id':..., 'memo_id':...}` e `Memory.fidelity`). Dois mecanismos de decoerência coexistem:
  expiração dura por *cutoff* (`_schedule_expiration`, agenda `Event("expire")`) e decaimento contínuo
  do estado Bell-diagonal (`bds_decohere()`), aplicado sob demanda antes de qualquer operação
  (purificação/swapping) que leia o estado. `update_memory_params(nome, valor)` é o *hook* público de
  configuração em massa (usado pelos notebooks oficiais).
- **`OpticalChannel`**/**`QuantumChannel`**/**`ClassicalChannel`** (`components/optical_channel.py`):
  perda por atenuação convertida em probabilidade linear (`loss = 1 - 10**(distance*attenuation/-10)`,
  calculado em `init()`); a decisão de "fóton perdido" é uma jogada de moeda com o gerador do **nó
  remetente** (`sender.get_generator().random() > self.loss`) — portanto reprodutível por seed do nó.
  `ClassicalChannel` é sem perdas, apenas atraso (`distance/velocidade` ou `delay` explícito).
- **`BSM`** (`components/bsm.py`): há implementações para diferentes hardwares/encodings
  (`SingleAtomBSM` — usada pelo protocolo Barrett-Kok padrão dos exemplos; `PolarizationBSM`/
  `TimeBinBSM`; `SingleHeraldedBSM`; `AbsorptiveBSM`), escolhidas por `make_bsm(encoding_type, ...)`.
  Todas convergem para `notify({'info_type':'BSM_res', 'res':..., 'time':...})`, que aciona
  `bsm_update` no protocolo de geração de entrelaçamento do lado do nó BSM.

### Entanglement Management (`sequence/entanglement_management/`)

Ver §4.3 (swapping) e §4.4 (purificação) para detalhes; geração é descrita no fluxo §4.2.
Todos os protocolos seguem o mesmo padrão de **registro por formalismo/tipo** (`@Protocolo.register(nome)`
+ `Protocolo.create(...)` fábrica lendo um `_global_type`/`_global_formalism`), o que já é, por si só,
um ponto de extensão *first-class*: novas variantes podem se registrar sem tocar o núcleo.

### Resource Management (`sequence/resource_management/`)

`ResourceManager` (um por `QuantumRouter`) mantém um `MemoryManager` (estado lógico de cada memória) e
um `RuleManager` (lista ordenada por prioridade de `Rule`). Uma `Rule(priority, action, condition,
action_args, condition_args)` é reavaliada contra cada `MemoryInfo` sempre que o estado de uma memória
muda (`ResourceManager.update`); a primeira regra cujo `condition(...)` retorna uma lista não-vazia
tem seu `action(...)` executado, instanciando um protocolo de entrelaçamento. `action_condition_set.py`
é a biblioteca das funções `eg_*`/`ep_*`/`es_*` (ação/condição/match) usadas por
`ResourceManager.generate_load_rules` para construir automaticamente as regras de uma reserva aceita.

### Network Management (`sequence/network_management/`)

`NetworkManager` (concretamente `DistributedNetworkManager`) monta uma pilha de dois protocolos —
`[ForwardingProtocol, RSVPProtocol]` (`network_manager.py:187-198`, confirmado empiricamente) — e expõe
`request(responder, start_time, end_time, memory_size, target_fidelity)` como a **API pública real**
de reserva usada por aplicações. `RSVPProtocol` (`rsvp.py`) implementa o handshake
REQUEST→APPROVE/REJECT salto-a-salto, consultando `MemoryTimeCard`s (`memory_timecard.py`) para admissão
por disponibilidade de memória/janela de tempo (sem qualquer estimativa de fidelidade — ver §4.7).
`routing/` contém duas estratégias reais: `StaticRoutingProtocol` (tabela populada manualmente via
`update_forwarding_rule`) e `DistributedRoutingProtocol` (protocolo *link-state* estilo OSPF, com FSM de
vizinhos, LSAs e **Dijkstra real** via `run_spf()`) — a segunda é uma implementação completa, não um
stub, e é um candidato natural para nossas estratégias de roteamento alternativas.

### Application (`sequence/app/`)

`RequestApp` é a classe-base de aplicação. Uma aplicação define o que quer via
`node.reserve_net_resource(...)` (→ `network_manager.request(...)`) e recebe **dois callbacks**
distintos do núcleo (nunca chamados diretamente pela aplicação): `get_reservation_result(reservation,
result: bool)` (admissão aprovada/rejeitada) e `get_memory(info: MemoryInfo)` (cada memória que se
torna `ENTANGLED`, chamado uma vez por par entregue). Confirmado experimentalmente (ver §4.2).

### Telemetria nativa (achado importante, não previsto no prompt original)

`sequence/utils/metrics/` é um **subsistema de métricas de primeira classe já existente no núcleo**,
desabilitado por padrão (`_enabled = False`). Define `EventTypes` (`EG_SUCCESS/FAILURE`,
`EP_SUCCESS/FAILURE`, `ES_SUCCESS/FAILURE`, `DELIVERY`), uma função global `metrics.record(event_type,
owner_name, **kwargs)` — já chamada dentro de `barret_kok.py`, `bbpssw_bds.py`/`bbpssw_circuit.py`,
`swapping_bds.py`/`swapping_circuit.py` (confirmado por grep, ver tabela §4.6) —, um `InMemoryStorage`,
métricas agregadas (`CounterMetric`, `FidelityMetric`, `RateMetric`, `DeliveryTimeMetric`) e funções
`collect_trial_metrics(...)`/`aggregate_trial_metrics(...)` que **já calculam média/desvio-padrão por
trial**, exatamente o que a seção 22 do prompt original pede. Ponto crítico: **`EventTypes.DELIVERY`
está definido e testado (`tests/utils/test_metrics.py`) mas nenhum protocolo do núcleo o dispara** —
é responsabilidade da camada de aplicação chamar `metrics.record(EventTypes.DELIVERY, ...)` quando um
par fim-a-fim é confirmado. Isso é exatamente o papel do nosso `SequenceExecutor`/`RequestApp`
customizado (ver §4.6 e §4.8). **Decisão de design recomendada**: nosso `ibqn/metrics/` deve envolver
(*wrap*) `sequence.utils.metrics`, não reimplementá-lo.

---

## 4.2 Fluxo de uma requisição (confirmado por execução real)

Fluxo real, verificado tanto lendo o código quanto executando um script com `RequestApp` instrumentado
em uma topologia de 3 nós (`r1—m1—r2—m2—r3`, `r1` iniciador, `r3` respondente):

```
1. Application
   RequestApp.start(responder, start_time, end_time, memory_size, target_fidelity)
     → node.reserve_net_resource(...)  (topology/node.py:453)
     → network_manager.request(...)     (network_management/network_manager.py:248)

2. request/reservation
   NetworkManager.request() delega para RSVPProtocol.push(...) (network_manager.py:248-261)
   RSVPProtocol.push cria o objeto Reservation(initiator, responder, start, end, size, fidelity)
     (network_management/reservation.py:10) e chama self.schedule(reservation)
   RSVPProtocol.schedule() consulta MemoryTimeCard.add() para cada memória livre — SOMENTE
     disponibilidade de memória/janela de tempo, sem estimar fidelidade alcançável (ver §4.7)
   REQUEST é propagado salto-a-salto (ForwardingProtocol usa a tabela de roteamento estática ou
     distribuída); cada nó intermediário também roda schedule() localmente
   No respondente, sucesso → Reservation.set_path(path) e envio de APPROVE de volta salto-a-salto
     (rastreamento reverso via lista de QCap acumulada); falha em qualquer salto → REJECT

3. rule creation
   Ao receber APPROVE, TODO nó no caminho (não só iniciador/respondente) chama
     NetworkManager.generate_rules(reservation) → resource_manager.generate_load_rules(path,
     reservation, timecards, memory_array_name)  (resource_management/resource_manager.py:155)
   generate_load_rules constrói até 5 Rule(priority=10, action, condition, action_args, condition_args)
     por nó: geração (eg_*), purificação (ep_*) e swapping (es_*) — variando conforme a posição do nó
     no caminho (extremidade vs. interior). Cada Rule é agendada para instalação em start_time e
     expiração em end_time via Event/Process na Timeline (não instalada imediatamente!)
   Apenas iniciador e respondente recebem callback de aplicação:
     Node.get_reservation_result(reservation, True) → RequestApp.get_reservation_result(...)
     (CONFIRMADO: disparado ~0.4ms após t=0 no teste, muito antes de start_time=100ms — é só a
     confirmação de ADMISSÃO, não de entrega de pares)

4. entanglement generation
   No horário start_time, ResourceManager.load(rule) instala a regra; se uma memória já satisfizer a
   condição, a ação roda imediatamente. eg_rule_action cria EntanglementGenerationA (Barrett-Kok)
   ligada à memória local e envia NEGOTIATE ao par remoto; troca de NEGOTIATE/NEGOTIATE_ACK define
   horário de emissão de fóton (excite()); fótons via QuantumChannel chegam ao BSMNode; SingleAtomBSM
   mede e notifica MEAS_RES às duas pontas; após 2 rodadas de Barrett-Kok bem-sucedidas,
   Memory.entangled_memory é preenchido e MemoryInfo passa para ENTANGLED

5. purification
   Se target_fidelity > raw_fidelity após swapping esperado, a regra ep_* (BBPSSW) consome DUAS
   memórias ENTANGLED (kept + meas) do mesmo par lógico e produz UMA com fidelidade maior
   (kept → PURIFIED; meas → RAW); probabilidade de sucesso calculada analiticamente (ver §4.4)

6. swapping
   Em nós interiores, es_rule_action_A mede o par esquerdo/direito e envia SWAP_RES às pontas;
   es_rule_action_B nas pontas atualiza Memory.entangled_memory para apontar para a nova ponta distante

7. memory update
   A cada mudança de estado, ResourceManager.update(...) reavalia todas as regras instaladas
   (permitindo cadeias eg→ep→es sem intervenção externa) e chama Node.get_idle_memory(info)
   quando nenhuma regra casa

8. delivery to application
   Sempre que uma memória se torna ENTANGLED, Node.get_idle_memory(info) → RequestApp.get_memory(info)
   (CONFIRMADO experimentalmente: dispara uma vez por par entregue, com info.state="ENTANGLED",
   info.remote_node, info.fidelity já populados — este é o ÚNICO ponto onde a aplicação aprende a
   fidelidade real observada de um par)
```

Evidência empírica (script de verificação, topologia 3 nós, `target_fidelity=0.8`, `raw_fidelity=0.95`):

```
[400000000] get_reservation_result called: result=True reservation.path=['r1','r2','r3']
[101010075010] get_memory called: index=5 state=ENTANGLED remote_node=r1 fidelity=0.857375
... (50 pares entregues, fidelidade uniforme ~0.8574 sem necessidade de purificação)
```

Com `target_fidelity=0.9` (mesma topologia), memórias aparecem em estado `PURIFIED` com fidelidade
`0.9187`, e uma segunda memória fica temporariamente em `OCCUPIED` (a memória de medição consumida pela
purificação) — confirmando consumo de pares pela BBPSSW.

---

## 4.3 Swapping

**Classes**: `EntanglementSwappingA`/`EntanglementSwappingB`
(`entanglement_management/swapping/swapping_base.py:69,266`) são abstratas, com duas implementações
registradas por formalismo: `EntanglementSwappingA_BDS`/`EntanglementSwappingB_BDS`
(`swapping_bds.py`, formalismo `bell_diagonal`) e `EntanglementSwappingA_Circuit`/`..._Circuit`
(`swapping_circuit.py`, formalismos `ket_vector`/`density_matrix`). `A` roda no nó **interior** que
possui as duas metades a serem trocadas; `B` roda em cada nó **extremidade** que possui uma ponta.

**Condições de disparo**: instaladas via `es_rule_condition_A`/`es_rule_condition_B`/
`es_rule_condition_B_end` (`resource_management/action_condition_set.py`, consumidas por
`generate_load_rules`, `resource_manager.py:229-238`). A ordem de swapping segue uma **redução binária
balanceada do caminho** (bisseção repetida da lista `path`), não um swapping sequencial ponta-a-ponta —
isso é *hardcoded* em `generate_load_rules` e não é parametrizável sem reescrever essa função (ver §4.7).

**Mensagens**: `EntanglementSwappingMessage(SwappingMsgType.SWAP_RES, ...)` carrega `fidelity`,
`remote_node`, `remote_memo`, `expire_time` (`swapping_base.py:38-61`). `A` mede localmente e envia uma
mensagem para cada ponta (`msg_l`, `msg_r`) informando a nova ponta distante.

**Probabilidades**: `success_prob` é parâmetro do protocolo (`success_probability()` retorna esse valor
fixo — não há modelo físico interno de sucesso de BSM, é um número configurado externamente via
`QuantumRouter`, propagado por `swapping_success_prob`/`action_args["swapping_success_prob"]`). A jogada
de sucesso usa `self.owner.get_generator().random() < self.success_probability()` — reprodutível por
seed do nó.

**Alteração de fidelidade**: dois modelos coexistem, conforme formalismo:
- **BDS** (`swapping_bds.py:133-173`, `swapping_res()`): calcula os 4 elementos diagonais do novo
  Bell-Diagonal State a partir dos elementos dos dois pares de entrada e de `gate_fid`/`meas_fid` do
  nó (parâmetros de fidelidade de porta/medição do `Node`), com fórmula fechada envolvendo
  `c_I, c_X, c_Y, c_Z` (produtos cruzados dos elementos). Não há "degradação" simples — é uma
  composição analítica de canais.
- **Circuit** (`swapping_circuit.py`): usa um parâmetro `degradation` (default `0.95`) multiplicado
  diretamente na fidelidade resultante — modelo mais simples, correspondente ao "swapping degradation"
  citado no notebook `random_request_network.ipynb` (`set_swapping_degradation`, comentado no exemplo).

**Uso de memórias**: `left_memo`/`right_memo` (as duas metades no nó interior); ambas voltam a `RAW`
após o swap no nó interior (memórias já não guardam entrelaçamento útil ali). Nas pontas, a mesma
memória física é mantida, apenas `entangled_memory` é atualizado para a nova ponta distante — sem
troca de índice de memória.

**Eventos gerados**: nenhum `Event`/`Process` de novo agendamento direto no `start()` do swapping em si
(a operação é "instantânea" do ponto de vista da Timeline); os `Event`s relevantes já foram agendados
anteriormente por `generate_load_rules` (load/expire da regra) e pela troca de mensagens clássicas
(delay do `ClassicalChannel`).

**Tratamento de falhas**: se a jogada de sucesso falhar, `fidelity=0` é enviado nas mensagens; ao
receber, `EntanglementSwappingB.received_message` (`swapping_bds.py:221,231`) verifica
`msg.fidelity > 0 and now < msg.expire_time` — se falso, a memória volta para `RAW` em vez de
`ENTANGLED`. Expiração de memória durante espera de swapping (`memory_expire`, `swapping_base.py:230`)
libera protocolos remotos via mensagens `RELEASE_PROTOCOL`/`RELEASE_MEMORY` ao `ResourceManager`.

---

## 4.4 Purificação

**Protocolo implementado**: BBPSSW (Bennett–Brassard–Popescu–Schumacher–Smolin–Wootters), **não**
DEJMPS "puro" — mas a implementação BDS (`bbpssw_bds.py`) suporta uma flag `is_twirled` que, quando
`False`, comporta-se como DEJMPS (sem *twirl* para forma de Werner); `is_twirled=True` (padrão) é o
BBPSSW clássico. Duas implementações por formalismo: `BBPSSW_BDS` (`purification/bbpssw_bds.py`,
formalismo `bell_diagonal`) e uma variante `bbpssw_circuit.py` (formalismo `ket_vector`/`density_matrix`,
baseada em circuito quântico explícito via `Circuit`).

**Pares consumidos**: exatamente **2 pares entrelaçados → 1 par de maior fidelidade** por rodada
(`kept_memo` + `meas_memo` → `kept_memo` purificado; `meas_memo` volta a `RAW`). Não há suporte nativo
a esquemas hierárquicos com mais de 2 pares por rodada (ex.: purificação com múltiplos pares
simultâneos) — apenas rodadas sucessivas de purificação 2-para-1 encadeadas pela reinstalação da regra
`ep_*` (`purification_mode='until_target'`, atributo de `Reservation`, reservation.py:~30).

**Cálculo de fidelidade**: fórmula fechada em `purification_res()`
(`purification/bbpssw_bds.py:156-244`) usando os elementos diagonais BDS de ambos os pares e as
fidelidades de porta/medição (`gate_fid`, `meas_fid`) dos dois nós envolvidos (próprio e remoto). O
novo estado é normalizado pela probabilidade de sucesso (`new_fid = new_elem_1 / p_success`).

**Probabilidade de sucesso**: também calculada analiticamente pela mesma função —
`p_succ = 1/2 + termos que dependem de gate_fid, meas_fid e dos elementos das duas BDS de entrada`
(garantida `>= 0.5` por `assert`). Não é um número fixo configurável como no swapping — é derivada da
física do protocolo e da fidelidade de entrada.

**Coordenação clássica**: `BBPSSWMessage(BBPSSWMsgType.PURIFICATION_RES, receiver, meas_res)`
(`bbpssw_protocol.py:19-42`). Cada lado faz uma "moeda enviesada" local (`meas_res ∈ {0,1}`) com
probabilidade calibrada para reproduzir `p_success`; ambos os lados comparam `meas_res` recebido via
mensagem — sucesso ⟺ `self.meas_res == msg.meas_res` (`bbpssw_bds.py:127-128`). Truque estatístico
documentado no próprio código (comentário longo em `bbpssw_bds.py:84-92`) para simular corretamente a
probabilidade de sucesso sem simular o circuito completo em ambos os lados de forma correlacionada.

**Condições para aplicação**: `start()` (`bbpssw_protocol.py:180-198`) valida via `assert`: protocolo
pronto (`is_ready()`), ambas as memórias entrelaçadas com o **mesmo** nó remoto, e fidelidade de ambas
`> 0.5`. A decisão de *quando* purificar é externa ao protocolo — vem da regra `ep_rule_condition_*`
instalada por `generate_load_rules`, que compara `memory_info.fidelity` contra
`reservation.fidelity` e o `purification_mode`.

**Tratamento de falhas**: se `meas_res` dos dois lados não coincidir, `meas_memo` volta a `RAW` e
`kept_memo` também volta a `RAW` (falha total — **não preserva o estado original**, diferente de alguns
esquemas de purificação onde a falha ao menos preserva um dos pares). Isso é um dado físico relevante
para os experimentos de trade-off fidelidade × throughput × consumo (seção E4 do prompt original).

---

## 4.5 Gerenciamento de recursos

**Seleção de memórias**: não há um "seletor" explícito e sofisticado — `ResourceManager.update(...)`
(`resource_manager.py:322-365`) é chamado toda vez que o estado de UMA memória muda e reavalia **todas**
as `Rule`s instaladas, em ordem de prioridade, contra aquela `MemoryInfo`; a primeira regra cuja
`condition()` aceitar a memória "vence". Não há como uma segunda regra de prioridade igual competir pela
mesma memória — é resolução determinística por ordem de prioridade/inserção, não uma negociação.

**Reserva de memórias no tempo**: feita **antes** de qualquer regra existir, em
`RSVPProtocol.schedule()` → `MemoryTimeCard.schedule_reservation()`
(`network_management/memory_timecard.py:59-85`) — busca binária sobre a lista de reservas já agendadas
naquele índice de memória, testando sobreposição de intervalo `[start_time, end_time]`. **Sobreposição
nas bordas conta como conflito** (`<=`/`>=`, não `<`/`>`), i.e. duas reservas não podem ser
"encostadas" no tempo na mesma memória. Nós intermediários reservam **o dobro** de memórias
(`counter = reservation.memory_size * 2`, `rsvp.py`) porque cada swap consome uma memória de cada lado.

**Instalação de regras**: `ResourceManager.generate_load_rules` monta as `Rule`s e agenda dois `Event`s
por regra (`Process(resource_manager,"load",[rule])` em `start_time`;
`Process(resource_manager,"expire",[rule])` em `end_time`) — a regra só existe de fato entre esses dois
instantes de simulação. `ResourceManager.load(rule)` insere no `RuleManager` (lista ordenada por
prioridade via busca binária) e testa imediatamente contra todas as `MemoryInfo` correntes.

**Tratamento de conflitos**: **não há mecanismo de lock/transação** dentro de `resource_management/` —
o único ponto de prevenção de conflito é a checagem de sobreposição temporal em `MemoryTimeCard` (acima),
que acontece *antes* de qualquer regra ser criada. Duas reservas para janelas de tempo não sobrepostas
na mesma memória convivem sem problema; duas reservas sobrepostas são simplesmente rejeitadas
(`REJECT` propagado de volta) na fase de admissão.

**Liberação de recursos**: ao expirar (`ResourceManager.expire(rule)`), os protocolos vivos daquela
regra são removidos de `waiting_protocols`/`pending_protocols`/`owner.protocols`, e cada memória
associada volta para `RAW` via `update(protocol, memory, MemoryInfo.RAW)`. Há também expiração
"antecipada" via mensagem `EARLY_EXPIRE` (`expire_rules_by_reservation`/`expire_remote_rules`,
`resource_manager.py:510-544`), usável quando o número de pares desejado já foi atingido antes do fim
da janela reservada.

**Requisições simultâneas**: interagem exclusivamente através do `MemoryTimeCard` (admissão) — uma vez
admitidas, requisições concorrentes não têm nenhuma forma de negociar recursos entre si em tempo de
execução; a prioridade das `Rule`s (todas criadas com prioridade fixa `10` pelo núcleo) determina apenas
a ordem de avaliação em uma mesma memória, não uma política de justiça (*fairness*) entre reservas.
Não há suporte nativo a preempção de uma reserva ativa por outra de prioridade mais alta.

---

## 4.6 Pontos de extensão

| Necessidade da arquitetura | Classe/módulo do SeQUeNCe | Forma de integração | Alteração no núcleo necessária? |
|---|---|---|---|
| Construir topologia a partir de config declarativa | `topology.RouterNetTopo` (`topology/router_net_topo.py:12`) | Instanciar com dict/JSON; subclassear e sobrescrever `_generate_forwarding_table` para roteamento customizado | Não |
| Emitir uma reserva de entrelaçamento | `NetworkManager.request(...)` (`network_management/network_manager.py:248`) via `Node.reserve_net_resource` | Chamar diretamente a partir do nosso `SequenceExecutor`, um nó por vez | Não |
| Saber se a reserva foi admitida | `RequestApp.get_reservation_result(reservation, bool)` | Subclassear `RequestApp` (`app/request_app.py:70`) | Não |
| Saber quando um par é entregue e sua fidelidade real | `RequestApp.get_memory(info: MemoryInfo)` | Subclassear `RequestApp` (`app/request_app.py:119`) | Não |
| Registrar métricas por evento (EG/EP/ES) | `sequence.utils.metrics` (`utils/metrics/__init__.py`) | Chamar `metrics.enable([...])` antes de `tl.run()`; consumir `collect_trial_metrics`/`aggregate_trial_metrics`; registrar `EventTypes.DELIVERY` a partir do nosso `RequestApp.get_memory` | Não |
| Roteamento alternativo (múltiplos caminhos, custo por perda) | `network_management/routing/routing_base.py:23` (`RoutingProtocol`, registrável por nome) | Nova subclasse registrada via `RoutingProtocol.register(nome)`; ou pós-processar `_generate_forwarding_table` | Não, desde que a estratégia só precise popular a tabela de encaminhamento |
| Roteamento ciente de fidelidade real (peso de enlace = fidelidade estimada) | `DistributedRoutingProtocol` (`routing/routing_distributed.py`) calcula Dijkstra sobre `link_cost` | Nosso planner pode calcular os "custos" externamente (fora do `Timeline`, antes da simulação) e popular `update_forwarding_rule` diretamente — mais simples que estender o OSPF-like em runtime | Não, se o custo for pré-computado estaticamente |
| Controlar decisão de purificar/não purificar e nº de rodadas | `Reservation.purification_mode` + `ep_rule_condition_*` (`resource_management/action_condition_set.py`) via `generate_load_rules` | **Bypass**: construir as `Rule`s manualmente (como no exemplo `two_node_eg`) em vez de usar `network_manager.request(...)`, dando controle total sobre quando/quantas rodadas de purificação instalar | Não, mas exige reimplementar a lógica equivalente a `generate_load_rules` na nossa camada (documentar isso como decisão arquitetural) |
| Controlar a ordem de swapping | `generate_load_rules` (`resource_manager.py:229-238`, bisseção binária fixa do caminho) | Mesmo caminho do item anterior: **não há parâmetro** para mudar a ordem via API pública — só construindo as regras/protocolos manualmente | **Não** modifica o núcleo, mas exige reimplementar a orquestração de regras nós-a-nós fora de `generate_load_rules` |
| Hardware customizado (perda, ruído, coerência estocástica) | `Memory`/`OpticalChannel`/`BSM` — hooks de subclasse documentados no próprio código (`MemoryWithRandomCoherenceTime`, `memory.py:871`) | Subclassear e usar `component_templates` na topologia | Não |
| Falha de nó/enlace controlada externamente | `QuantumRouter.set_down(bool)` (`topology/node.py:400`) | Chamar do nosso runtime/experimento em um `Event` agendado | Não |
| Admissão consciente de fidelidade alcançável (a priori) | **Não existe** — `RSVPProtocol.schedule()` só checa memória/tempo (`network_management/rsvp.py`) | Nossa camada de *feasibility* deve calcular isso **antes** de chamar `network_manager.request(...)` e decidir rejeitar o intent preventivamente | Não (a estimativa vive inteiramente na nossa camada) |

---

## 4.7 Limitações encontradas

- **Múltiplas estratégias de swapping**: a ordem de swap é fixada por bisseção binária do caminho
  dentro de `ResourceManager.generate_load_rules` (`resource_manager.py:229-238`); não há parâmetro
  público para trocar essa ordem quando se usa o fluxo automático (`network_manager.request`). Uma
  estratégia de swapping "sequencial" ou "por prioridade de fidelidade" exigiria a nossa camada
  construir e instalar as `Rule`s diretamente (via `ResourceManager.load`), replicando parte da lógica
  hoje interna a `generate_load_rules`, sem alterar o arquivo original.
- **Múltiplas estratégias de purificação**: o número de rodadas e a decisão de purificar são
  controlados apenas pelo `purification_mode` da `Reservation` (hoje só `'until_target'` foi observado
  em uso) e pelas condições `ep_rule_condition_*`. Não há um parâmetro de "número fixo de rodadas"
  exposto publicamente — de novo, controle fino exige regras manuais.
- **Telemetria**: o subsistema `sequence.utils.metrics` cobre EG/EP/ES (sucesso/falha/fidelidade) mas
  **não é acionado automaticamente para `DELIVERY`, ocupação de memória, ou pares expirados por
  decoerência** — nada no núcleo chama `metrics.record` nesses casos. A nossa camada de telemetria
  precisa instrumentar isso a partir de `RequestApp.get_memory` (para `DELIVERY`) e de observação direta
  de `MemoryManager`/`Memory.expire` (para expiração por decoerência, que hoje só notifica observers,
  sem registro central).
- **Estimativa de fidelidade a priori**: confirmado em `rsvp.py` — a admissão de uma reserva **não**
  estima a fidelidade alcançável dado o caminho, o número de swaps e a fidelidade bruta dos enlaces.
  Uma reserva pode ser aceita por disponibilidade de memória e nunca atingir `target_fidelity` durante
  toda a janela — só se descobre isso observando os pares realmente entregues. Nosso *feasibility
  analyzer* precisa implementar essa estimativa de forma independente (fora do núcleo), antes de emitir
  a reserva real.
- **Reroteamento em tempo real**: não há suporte a alterar o caminho de uma reserva já aprovada (`path`
  é fixado uma única vez em `Reservation.set_path`, nunca mutado depois). Reconciliação, portanto, só
  pode ser feita **entre episódios** (cancelar/deixar expirar a reserva atual e emitir uma nova reserva
  com outro caminho) — exatamente como o prompt original antecipa (seção 14). Reconciliação *durante* a
  mesma `Timeline` exigiria, no mínimo, orquestrar uma nova `Reservation` concorrente à antiga.
- **Alteração de uma reserva ativa**: não existe API para mutar `memory_size`, `end_time` ou `fidelity`
  de uma `Reservation` já aceita. `EARLY_EXPIRE` permite encerrá-la antes do previsto, mas não editá-la.
- **Requisições concorrentes**: coexistem de forma segura via `MemoryTimeCard` (sem *double booking*),
  mas sem qualquer política de justiça/prioridade além da ordem de admissão — condições de
  *starvation* sob alta carga (seção E6 do prompt) são plausíveis e precisam ser medidas
  empiricamente, não presumidas.
- **Redes heterogêneas**: os formalismos de estado quântico (`ket_vector`, `bell_diagonal`, etc.) são
  globais por `Timeline` (setados uma vez na construção) — não observamos suporte a diferentes nós da
  mesma simulação usando formalismos diferentes simultaneamente. Hardware heterogêneo (parâmetros de
  memória/canal por nó) é plenamente suportado via `update_memory_params`/`component_templates`.
- **Reprodutibilidade da suíte de testes upstream**: identificados dois problemas de isolamento (teste
  probabilístico sem seed própria; poluição de estado global entre módulos de teste) — ver §0.2. Não
  bloqueiam nosso trabalho, mas reforçam que a nossa própria suíte (Fase 2) deve seguir rigorosamente
  os requisitos de seed/determinismo do prompt original.
- **Ambiente Windows**: instalação completa via `pip`/`uv` falha por causa de caminhos longos do
  JupyterLab (não é uma limitação do SeQUeNCe em si, mas afeta a Fase H — notebooks). Documentar a
  necessidade de habilitar *long path support* do Windows ou usar WSL/Linux para a fase de notebooks.

---

## 4.8 Plano de implementação revisado

**Pode ser implementado imediatamente, sem qualquer alteração no núcleo:**
- Adaptador (`network/sequence_adapter.py`) que constrói `Timeline` + `RouterNetTopo` a partir de uma
  configuração declarativa própria (YAML do projeto → dict aceito por `RouterNetTopo`).
  Fonte real: `topology/router_net_topo.py`, schema JSON confirmado em `example/demo_for_beginners/star_network.json`.
- Compilação de um `EntanglementIntent` para uma chamada real `network_manager.request(...)` em um nó
  real (`QuantumRouter`), reutilizando 100% o mecanismo de reserva/regras do SeQUeNCe.
- `RequestApp` customizado (`execution/sequence_executor.py`) que implementa
  `get_reservation_result`/`get_memory`, e que também registra eventos `metrics.record(EventTypes.DELIVERY,
  ...)` — reaproveitando `sequence.utils.metrics` como backend de telemetria.
- Feasibility analyzer e planner de primeira versão (roteamento shortest-path/menor perda,
  decisão de purificação, estimativa de fidelidade) — tudo isso vive **fora** do `Timeline`, calculado
  antes de emitir a reserva; usa `Topology.qchannels`/`get_nodes_by_type` para introspecção de rede.
  A estimativa de fidelidade pós-swap pode replicar (fora do núcleo) a fórmula de `swapping_bds.py`
  usando os mesmos `gate_fid`/`meas_fid`, sem duplicar lógica de simulação — apenas seu equivalente
  determinístico "esperado".
- Assurance/avaliação pós-execução comparando requisitos do intent com métricas coletadas via
  `RequestApp` + `metrics.collect_trial_metrics`.
- Reconciliação **entre episódios** (nova simulação/reserva após detectar violação).
- Estratégias de roteamento alternativas como funções puras que populam a tabela de encaminhamento
  (`update_forwarding_rule`) antes de `tl.init()` — sem necessidade de tocar `DistributedRoutingProtocol`.

**Exige extensão cuidadosa (mas ainda sem tocar o núcleo), documentar como decisão de design:**
- Controle fino de ordem de swapping e número de rodadas de purificação: implica **não usar**
  `network_manager.request(...)` para o caminho de entrega, e sim construir e instalar `Rule`s
  manualmente (como no `two_node_eg` oficial), reimplementando na nossa camada uma lógica equivalente
  (mas configurável) à de `generate_load_rules`. Isso deve ser uma estratégia *opcional*
  (`SwappingStrategy`/`PurificationStrategy` "avançada"), com a estratégia "padrão" simplesmente
  delegando para o fluxo automático do núcleo.
- Reroteamento durante a mesma `Timeline`: exigiria orquestrar uma segunda `Reservation` concorrente e
  liberar a antiga via `EARLY_EXPIRE`; não implementar na primeira versão — documentar como trabalho
  futuro (seção 14 do prompt original já antecipa isso).

**Item explicitamente fora do escopo da primeira versão** (conforme restrições do prompt): qualquer
cálculo de resultado quântico fora do simulador para "forçar" uma demonstração — toda métrica de
fidelidade/pares entregues nesta auditoria veio de execução real do `Timeline` (`Memory.fidelity`,
`MemoryInfo`, `metrics.record`), nunca de valores calculados independentemente pela nossa camada.

---

## Resumo executivo (para referência rápida)

- **Como uma requisição é criada**: `RequestApp.start(...)` → `Node.reserve_net_resource(...)` →
  `NetworkManager.request(responder, start_time, end_time, memory_size, target_fidelity)`
  (`network_management/network_manager.py:248`).
- **Como a rota é selecionada**: por uma tabela de encaminhamento pré-computada
  (`StaticRoutingProtocol.update_forwarding_rule` manual, ou `DistributedRoutingProtocol` com Dijkstra
  real sobre custos de enlace) — **não** há escolha de rota dinâmica por fidelidade dentro do núcleo.
- **Como as regras são instaladas**: `ResourceManager.generate_load_rules` monta `Rule`s de
  geração/purificação/swapping a partir de uma `Reservation` aprovada e as agenda (`load`/`expire`) via
  `Event`/`Process` na `Timeline`.
- **Como a geração é iniciada**: protocolo Barrett-Kok (`EntanglementGenerationA`/`B`), negociação
  NEGOTIATE/NEGOTIATE_ACK, emissão de fóton, medição BSM (`SingleAtomBSM`), 2 rodadas até `ENTANGLED`.
- **Como a purificação funciona**: BBPSSW 2-para-1, fidelidade e probabilidade de sucesso calculadas
  analiticamente a partir de `gate_fid`/`meas_fid` e do estado BDS de entrada; falha devolve ambas as
  memórias a `RAW`.
- **Como o swapping funciona**: `EntanglementSwappingA` (nó interior) mede par esquerdo+direito,
  `EntanglementSwappingB` (pontas) atualiza a ponta remota; ordem determinada por bisseção binária do
  caminho; fidelidade resultante por fórmula analítica (BDS) ou fator de degradação fixo (circuito).
- **Como a aplicação recebe os resultados**: dois callbacks do núcleo,
  `get_reservation_result(reservation, bool)` (admissão) e `get_memory(MemoryInfo)` (entrega real,
  com fidelidade observada) — nunca hooks que precisem ser inventados por nós.
- **Quais pontos podem ser usados pela camada intent-based**: ver tabela completa em §4.6; destaque
  para `sequence.utils.metrics` (telemetria nativa reaproveitável) e para o padrão de registro por
  formalismo/tipo já usado em todos os protocolos de entrelaçamento.
- **Quais limitações precisam ser consideradas**: sem estimativa de fidelidade a priori na admissão
  (§4.7); ordem de swap e nº de rodadas de purificação não parametrizáveis sem regras manuais; sem
  reroteamento de reserva ativa; telemetria de entrega/decoerência precisa ser instrumentada pela
  nossa camada.

## Menor implementação funcional seguinte

Um único `EntanglementIntent` (par origem/destino, fidelidade mínima, nº de pares, janela de tempo) em
uma topologia **linear de 3 nós** (`r1—m1—r2—m2—r3`, replicando exatamente a topologia já validada em
`example/demo_for_beginners/three_node_eg_ep_es.ipynb`), compilado para uma única chamada real
`network_manager.request(...)` em `r1`, com:
- planner "ingênuo" fixo (único caminho possível, decide purificar apenas se
  `raw_fidelity_pós_swap_estimada < target_fidelity`),
- `RequestApp` customizado coletando `get_reservation_result`/`get_memory` e alimentando
  `sequence.utils.metrics`,
- avaliação pós-execução comparando `delivered_pairs`/`average_fidelity` observados (não presumidos)
  contra as `success_conditions` do intent.

Esse é o menor corte vertical que exercita reserva real, geração real, decisão real de purificação,
swapping real e avaliação real — sem tocar o núcleo do SeQUeNCe e sem nenhum roteamento não-trivial
(que só entraria na próxima iteração, com topologia em malha).
