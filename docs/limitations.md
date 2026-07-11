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
| Sem reroteamento de reserva ativa | `Reservation.path` é fixado uma única vez (§4.7) | Reconciliação só é possível entre episódios (cancelar + nova reserva), nunca durante a mesma reserva | Planejado para Etapa G |
| `requested_pairs` não é teto de entrega | Reciclagem de memória (`docs/sequence_integration.md`) | Uma reserva pode entregar muito mais pares que o pedido, dado tempo suficiente | Assurance deve tratar `requested_pairs` como piso mínimo, não contagem exata |
| Um app por nó (`QuantumRouter.set_app`) | `docs/sequence_code_analysis.md`, §4.6 | `SequenceExecutor` não suporta dois intents simultâneos compartilhando nó de origem/destino nesta versão | Exigiria um app "roteador" compartilhado, distribuindo callbacks por reserva — não implementado |
| `RequestApp.get_memory` só conta pares no lado iniciador | `sequence/app/request_app.py:133-143` | Telemetria de entrega (`EventTypes.DELIVERY`) só é emitida pelo app de origem, nunca pelo de destino | Não é um problema em si (evita contagem duplicada), mas documentado para não ser reintroduzido por engano |

## Camada `ibqn` (decisões desta versão, não limitações do SeQUeNCe)

| Limitação | Módulo | Motivo |
|---|---|---|
| Topologia clássica sempre malha completa | `network/topology.py` | `RouterNetTopo._add_qconnections` exige conexão clássica direta entre todo par de roteadores com link quântico; topologias esparsas ainda não foram validadas |
| `HighestFidelityRouting` enumera caminhos simples (`nx.all_simple_paths`) | `planning/routing.py` | Não escalável para malhas grandes/densas — adequado à "rede linear + poucos caminhos candidatos" prevista para a primeira versão do planner (seção 9 do prompt original); otimização (ex. poda, limite de profundidade) fica para quando redes em malha maiores forem exercitadas |
| Sem estimativa de throughput | `planning/models.py::EstimatedMetrics` | Taxa de geração depende de frequência de memória, atraso de round-trip clássico e dinâmica de retentativas — nenhuma fórmula fechada simples é honesta o suficiente; deixado `None`/omitido em vez de inventado |
| `AdmissionStrategy`/`ReconciliationStrategy` (seção 10 do prompt original) ainda não existem como classes próprias | `planning/` | Nesta versão (múltiplos intents em um cenário, mas sem arbitragem entre eles), a decisão de admissão não difere da checagem de viabilidade já feita por `feasibility.evaluate_route`; uma estratégia de admissão distinta (ex. preempção por prioridade) só se justifica quando houver contenção real de recursos entre intents concorrentes com prioridades diferentes |
| `IntentRepository` é em memória, um por execução | `intent/repository.py` | Favorece reprodutibilidade por seed em vez de persistência entre execuções — decisão deliberada, não uma limitação técnica |
| Sem agregação estatística entre trials, sem gravação em disco de resultados brutos/processados, sem `experiments/sweeps.py` | `experiments/runner.py` | `run_scenario` produz um `ScenarioResult` por chamada; `sequence.utils.metrics.aggregate_trial_metrics` já existe e é o ponto de partida natural, mas nenhum módulo `ibqn` ainda o invoca sobre uma lista de execuções, nem grava `results/raw`/`results/processed`/manifestos (seção 22 do prompt original) — planejado para as campanhas experimentais do artigo |

## Ambiente

| Limitação | Detalhe |
|---|---|
| Instalação completa via pip/uv falha no Windows | Caminhos longos gerados pelos labextensions do JupyterLab; contornado instalando sem essas dependências nesta fase. Relevante apenas para a Fase H (notebooks) |
| Suíte de testes oficial do SeQUeNCe tem isolamento imperfeito | Um teste usa `random` sem seed própria; testes de `tests/topology` alteram o formalismo global do `QuantumManager` sem restaurá-lo, contaminando módulos executados depois. Não afeta nosso trabalho, mas motivou a fixture de reset em `tests/sequence_basics/test_memory_decoherence.py` |
