# Notebooks

## Regras gerais

Todo notebook em `notebooks/` (fora de `notebooks/article/`, que terá sua
própria infraestrutura de campanha na Fase H3):

- importa `ibqn` e (quando necessário) módulos de `ibqn.demos` — nunca
  reimplementa lógica que já existe em `src/ibqn/`;
- não depende de estado deixado por outro notebook (cada um constrói sua
  própria `Timeline`/`SequenceAdapter` do zero);
- fixa seeds explicitamente em toda célula que constrói uma simulação;
- expressa unidades em toda tabela/gráfico (segundos, pares, adimensional
  para fidelidade);
- indica explicitamente a origem de cada resultado (SeQUeNCe real via
  `ibqn.execution`/`ibqn.assurance`, nunca um valor calculado à parte) e
  diferencia estimativa do `IntentPlanner` de valor observado na simulação;
- documenta limitações conhecidas (linkando `docs/limitations.md` quando
  aplicável);
- não usa `%pip install`/`!pip install` — dependências são responsabilidade
  do ambiente (`pyproject.toml`), não do notebook;
- não usa widgets interativos (`ipywidgets.interact`) como mecanismo
  principal de reprodução — todo parâmetro relevante é uma variável Python
  explícita em uma célula de configuração, para que `nbconvert`/`nbclient`
  consigam executar o notebook do início ao fim sem intervenção humana.

Estrutura mínima de cada notebook (células Markdown): objetivo, conceitos,
configuração, execução, resultados, interpretação, limitações, conclusão.

## Validação automática

`tests/notebooks/test_notebooks.py` descobre todo `.ipynb` em `notebooks/`
(não recursivo em `notebooks/article/`) e, para cada um:

1. confirma que os notebooks obrigatórios das Fases H1 e H2 existem;
2. executa cada notebook do início ao fim em kernel limpo (`nbclient`,
   `NotebookClient.execute`) — qualquer exceção em qualquer célula
   (`CellExecutionError`) falha o teste imediatamente;
3. impõe timeout de 180s por célula;
4. confirma que ao menos uma célula de código produziu saída visível
   (stream/display), não apenas execução silenciosa;
5. confirma que nenhuma célula referencia caminhos de arquivo temporário
   externos ao repositório (`AppData\Local\Temp`, `/tmp/`, `tempfile`);
6. confirma que, se o notebook constrói uma simulação real
   (`SequenceAdapter(`/`run_scenario(`), existe uma seed explícita
   (`seed=`) em algum lugar do notebook;
7. confirma a presença de seções Markdown mínimas (objetivo, limitações).

Além disso, checks específicos por notebook (Fase H2): `11` mostra
`SATISFIED`; `14` mostra os três status terminais
(`SATISFIED`/`VIOLATED`/`REJECTED`); `15` mostra os dois episódios e a
recuperação (`VIOLATED` -> `SATISFIED`); `18` mostra o `ValueError` real
de conflito de nó; `19` mostra o ciclo completo
(`VIOLATED` -> `RECONCILING` -> ... -> `SATISFIED`).

### Pré-requisito: kernel Jupyter

Os notebooks e os testes usam um kernel Jupyter nomeado `ibqn-venv`, que
aponta para o mesmo Python do ambiente virtual do projeto (`.venv`).
`tests/notebooks/conftest.py` registra esse kernel automaticamente na
primeira execução dos testes (via `python -m ipykernel install --user
--name ibqn-venv`) caso ele ainda não exista — não é necessário nenhum
passo manual antes de rodar os testes.

Para registrar manualmente (ou após recriar o `.venv`):

```bash
python -m ipykernel install --user --name ibqn-venv --display-name "Python (ibqn)"
```

### Rodando a validação

```bash
python -m pytest tests/notebooks -v
```

Para executar (e regravar) um notebook manualmente fora dos testes:

```bash
jupyter nbconvert --execute --to notebook --inplace notebooks/01_sequence_two_node_entanglement.ipynb
```

(usa o kernel padrão registrado no próprio notebook — `ibqn-venv`).

## Notebooks da Fase H1 (SeQUeNCe básico)

| Notebook | Objetivo |
|---|---|
| `00_environment_validation.ipynb` | Versões (Python, SeQUeNCe, commit do submódulo, `ibqn`), formalismo padrão, disponibilidade de dependências, smoke test |
| `01_sequence_two_node_entanglement.ipynb` | Geração elementar entre 2 roteadores via `SequenceExecutor`, tabela de pares entregues |
| `02_sequence_three_node_swapping.ipynb` | Cadeia `a - r - b`: geração + swapping, fidelidade elementar vs. fim a fim, estimativa do planner vs. observado |
| `03_sequence_purification.ipynb` | Caso sem purificação vs. caso com purificação (estado `PURIFIED`), demonstrando a correção de contagem de pares purificados |
| `04_sequence_reservation_and_resources.ipynb` | Ciclo de uma reserva: janela, memórias, caminho, aceitação/rejeição, timecards, regras instaladas |
| `05_sequence_memory_lifecycle.ipynb` | Transições reais de estado de memória (via `ibqn.demos.instrumentation.MemoryLifecycleRecorder`), com protocolo responsável por cada transição |
| `06_sequence_metrics_and_callbacks.ipynb` | Métricas nativas do SeQUeNCe vs. eventos `DELIVERY` tagueados por intent; por que métricas globais não bastam para assurance por intent |

## Notebooks da Fase H2 (arquitetura intent-based)

| Notebook | Objetivo |
|---|---|
| `10_intent_schema_and_validation.ipynb` | Carga de um intent YAML real, modelo tipado, conversão de condições, nove exceções reais de validação, transições de lifecycle válidas/inválidas |
| `11_single_intent_end_to_end.ipynb` | Ciclo completo Intent → Validation → Planning → ExecutionPlan → Deployment → Reservation → Simulation → Assurance → `SATISFIED`, confirmando que a rota aceita pelo SeQUeNCe é a rota planejada |
| `12_execution_plan_and_strategy_selection.ipynb` | `ShortestHopCountRouting`/`LeastLossRouting`/`HighestFidelityRouting` numa topologia em diamante onde realmente divergem; confirmação por execução real |
| `13_intent_assurance.ipynb` | Quatro casos isolados de assurance (tudo passa; pares insuficientes; fidelidade insuficiente; zero pares), com `evidence_source` por condição |
| `14_satisfied_violated_rejected.ipynb` | `SATISFIED`/`VIOLATED`/`REJECTED` lado a lado, com a distinção entre inviabilidade de planejamento e violação observada |
| `15_reconciliation_between_episodes.ipynb` | Reconciliation real entre dois episódios (`VIOLATED` → `SATISFIED`) na topologia em diamante, com classificação da violação |
| `16_routing_strategy_comparison.ipynb` | As três estratégias de roteamento comparadas em poucas seeds (descritivo, não uma campanha estatística) |
| `17_purification_policy_comparison.ipynb` | `NeverPurify` vs. `PurifyUntilTarget` em quatro requisitos de fidelidade, incluindo o teto real de um round de purificação |
| `18_multiple_intents_and_constraints.ipynb` | `ValueError` real de conflito de nó, caso suportado de intents em nós disjuntos, e alternativas arquiteturais documentadas (não implementadas) |
| `19_complete_ibqn_demonstration.ipynb` | Demonstração de ponta a ponta da arquitetura completa, incluindo reconciliation, com diagrama de arquitetura |

Os notebooks da Fase H3 (infraestrutura de campanhas e notebooks do
artigo) serão adicionados a este documento conforme forem implementados.
