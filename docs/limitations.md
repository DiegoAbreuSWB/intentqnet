# Limitações conhecidas

Consolidação das limitações encontradas nas Fases 1–3 (auditoria, testes
básicos, arquitetura intent-based). Cada item indica origem, impacto e, onde
aplicável, o que seria necessário para superá-lo.

## Núcleo do SeQUeNCe (não modificável nesta versão)

| Limitação | Origem | Impacto | Como superar |
|---|---|---|---|
| Sem estimativa de fidelidade a priori na admissão da reserva | `RSVPProtocol.schedule()` só checa memória/tempo (`docs/sequence_code_analysis.md`, §4.7) | Uma reserva pode ser aceita e nunca atingir `target_fidelity` | Preenchido por `planning/feasibility.py` (Etapa E), fora do núcleo |
| Ordem de swap fixa (bisseção binária) | `ResourceManager.generate_load_rules` (§4.3/4.7) | Não é possível comparar estratégias de swap alternativas via a API pública de reserva | Exigiria construir `Rule`s manualmente, fora do escopo desta versão; estimativas de fidelidade continuam válidas pois são independentes de ordem (ver `docs/sequence_integration.md`) |
| Nº de rodadas de purificação não configurável | `Reservation.purification_mode` só suporta `'until_target'` (§4.4/4.7) | Nosso planner só modela analiticamente 1 rodada — subestima conservadoramente o que o SeQUeNCe pode realmente alcançar | Mesma observação acima; documentado em `ExecutionPlan.purification_rounds_estimate` |
| Sem reroteamento de reserva ativa | `Reservation.path` é fixado uma única vez (§4.7) | Reconciliação só é possível entre episódios (cancelar + nova reserva), nunca durante a mesma reserva | ✅ Implementado (Etapa G, `assurance/reconciliation.py`): novo `Timeline`/`SequenceAdapter`, mesmo `IntentRepository` |
| `requested_pairs` não é teto de entrega | Reciclagem de memória (`docs/sequence_integration.md`) | Uma reserva pode entregar muito mais pares que o pedido, dado tempo suficiente | `assurance/evaluator.py` trata `requested_pairs` como piso mínimo (`>=`), nunca como contagem exata |
| Um app por nó (`QuantumRouter.set_app`) | `docs/sequence_code_analysis.md`, §4.6 | Dois intents que compartilhassem um nó como origem/destino faziam o segundo app sobrescrever silenciosamente o primeiro, misturando `intent_id` nas transições de ciclo de vida (achado crítico, `docs/assurance_design.md` §4) | ✅ Detectado e barrado (Etapa G): `SequenceExecutor._check_no_node_conflict` levanta `ValueError` explícito em vez de corromper o estado; a limitação em si (não poder compartilhar o nó) permanece — não foi resolvida, só deixou de falhar silenciosamente |
| `RequestApp.get_memory` ignorava pares purificados | `sequence/app/request_app.py:133` (`if info.state != "ENTANGLED": return`) | Pares que terminam em `"PURIFIED"` nunca eram contados/entregues — confirmado empiricamente (318 `EP_SUCCESS` vs. 0 pares entregues antes da correção) | ✅ Corrigido (Etapa G): `IntentRequestApp._count_purified_delivery` espelha a lógica de casamento/contagem para o estado `"PURIFIED"` (`docs/assurance_design.md` §2) |
| `RequestApp.get_memory` só conta pares no lado iniciador | `sequence/app/request_app.py:133-143` | Telemetria de entrega (`EventTypes.DELIVERY`) só é emitida pelo app de origem, nunca pelo de destino | Não é um problema em si (evita contagem duplicada), mas documentado para não ser reintroduzido por engano |
| Contadores globais (`eg`/`ep`/`es`) não isolam por intent | `sequence.utils.metrics`, chaveado por `owner_name` (nó), nunca por `intent_id` | Confirmado empiricamente com dois intents compartilhando um nó interior de swap: 244 eventos `ES_SUCCESS` sem qualquer campo `intent_id`, somando a atividade de ambos | `assurance/telemetry.py` usa exclusivamente eventos `DELIVERY` (tagueados por nós) como prova por intent; contadores globais ficam só como diagnóstico (`docs/assurance_design.md` §3) |
| Sem estimativa de latência por par | Nenhum identificador liga uma tentativa de geração elementar ao par fim a fim que a consome via swap/purificação | `assurance/evaluator.py` não avalia `max_latency` como condição de sucesso — métrica não suportada, levanta `UnsupportedMetricError` em vez de aproximar |
| Reconciliation tenta uma única vez | `assurance/reconciliation.py` | Não há busca automática entre várias estratégias/rotas até encontrar uma satisfatória — o chamador fornece a estratégia alternativa | Extensão futura: um laço de reconciliation tentando múltiplas estratégias em sequência |

## Camada `ibqn` (decisões desta versão, não limitações do SeQUeNCe)

| Limitação | Módulo | Motivo |
|---|---|---|
| Topologia clássica sempre malha completa | `network/topology.py` | `RouterNetTopo._add_qconnections` exige conexão clássica direta entre todo par de roteadores com link quântico; topologias esparsas ainda não foram validadas |
| `HighestFidelityRouting` enumera caminhos simples (`nx.all_simple_paths`) | `planning/routing.py` | Não escalável para malhas grandes/densas — adequado à "rede linear + poucos caminhos candidatos" prevista para a primeira versão do planner (seção 9 do prompt original); otimização (ex. poda, limite de profundidade) fica para quando redes em malha maiores forem exercitadas |
| Sem estimativa de throughput | `planning/models.py::EstimatedMetrics` | Taxa de geração depende de frequência de memória, atraso de round-trip clássico e dinâmica de retentativas — nenhuma fórmula fechada simples é honesta o suficiente; deixado `None`/omitido em vez de inventado |
| `AdmissionStrategy`/`ReconciliationStrategy` (seção 10 do prompt original) ainda não existem como classes próprias | `planning/` | Nesta versão (múltiplos intents em um cenário, mas sem arbitragem entre eles), a decisão de admissão não difere da checagem de viabilidade já feita por `feasibility.evaluate_route`; uma estratégia de admissão distinta (ex. preempção por prioridade) só se justifica quando houver contenção real de recursos entre intents concorrentes com prioridades diferentes |
| `IntentRepository` é em memória, um por execução | `intent/repository.py` | Favorece reprodutibilidade por seed em vez de persistência entre execuções — decisão deliberada, não uma limitação técnica |
| `estimate_swap_only_fidelity`/`capabilities.hop_fidelity` subestimam fidelidade em topologias heterogêneas | `planning/feasibility.py`, `network/capabilities.py` | `hop_fidelity` estima cada salto como `min(raw_fidelity(nó_a), raw_fidelity(nó_b))`, mas `BarretKokA._entanglement_succeed` atribui a cada memória a fidelidade do **seu próprio nó** - quando o swap acontece no nó interior, as duas memórias envolvidas já são desse mesmo nó, então o resultado depende da fidelidade *dele*, não do mínimo geográfico do salto. Confirmado empiricamente na campanha `C01_routing_strategy` (topologia em diamante, nós com `raw_fidelity` diferentes): erro de até 0.083 (12% relativo), zero em topologias uniformes (`C02`/`C03`) - ver `notebooks/article/A05_planner_estimation_error.ipynb` | Refinar `hop_fidelity` para considerar qual nó realmente realiza o swap, não apenas os dois extremos do salto - não implementado nesta versão |

## Ambiente

| Limitação | Detalhe |
|---|---|
| Instalação completa via pip/uv falha no Windows | Caminhos longos gerados pelos labextensions do JupyterLab; contornado instalando sem essas dependências nesta fase. Relevante apenas para a Fase H (notebooks) |
| Suíte de testes oficial do SeQUeNCe tem isolamento imperfeito | Um teste usa `random` sem seed própria; testes de `tests/topology` alteram o formalismo global do `QuantumManager` sem restaurá-lo, contaminando módulos executados depois. Não afeta nosso trabalho, mas motivou a fixture de reset em `tests/sequence_basics/test_memory_decoherence.py` |
