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

1. confirma que os notebooks obrigatórios da Fase H1 existem;
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

Os notebooks das Fases H2 e H3 (arquitetura intent-based e campanhas do
artigo) serão adicionados a este documento conforme forem implementados.
