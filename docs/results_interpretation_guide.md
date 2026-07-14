# Guia de interpretação dos resultados (Fase K4)

Ponto de entrada único para quem for escrever ou revisar o artigo a
partir dos resultados deste projeto - responde "onde eu olho para
responder X" e lista os erros de interpretação mais fáceis de cometer
com estes dados específicos.

## Por onde começar, dependendo da pergunta

| Pergunta | Documento/figura |
|---|---|
| Qual é a contribuição central deste projeto? | `docs/core_contribution_statement.md`, `docs/ibn_principles_mapping.md` |
| Que campanha gerou este número? | `docs/results_provenance.md` (tabela completa) |
| Por que `least_loss` entrega 57x mais pares no diamante? | `docs/routing_result_explanation.md` |
| Por que o planner rejeita coisas que deveriam funcionar? | `docs/false_rejection_root_cause.md` |
| A reconciliation "funciona"? | `docs/reconciliation_scope.md` - depende da classe de cenário, nunca uma taxa única |
| Posso citar o número X no artigo? | `docs/final_claims_and_evidence.md` - se não está na tabela, não cite sem adicionar a linha |
| Isso generaliza para outras topologias/redes reais? | `docs/threats_to_validity.md`, seção de validade externa |
| Uma figura específica - de onde vêm os dados? | `results/figures/final/sources.json` |

## Erros de interpretação fáceis de cometer com estes dados

1. **Misturar C01-C04 (piloto) com F01-F08 (final)**. São conjuntos de
   dados diferentes, com propósitos diferentes - ver
   `docs/results_provenance.md`. Nenhum número de `notebooks/article/
   A0*.ipynb` deve aparecer no artigo.
2. **Ler `false_rejection_rate=1.0` como "o planner sempre erra"**. É
   `1.0` sobre os 240 trials TESTADOS de UMA topologia
   (`three_node_1_repeater`) - `linear_chain_2_repeaters` nunca foi
   oracle-testado e permanece `INFEASIBLE_AND_REJECTED` (não confirmado
   nem refutado). Ver `docs/planner_operational_gap.md`.
3. **Atribuir a rejeição falsa à heterogeneidade de topologia**. É um
   mecanismo diferente (uma rodada de purificação estimada vs. múltiplas
   reais) - ocorre em topologia UNIFORME. Ver
   `docs/false_rejection_root_cause.md`.
4. **Reportar uma média de overhead sem a distribuição**. Sempre citar
   `Figure_Overhead_Ratio.png` (ou a figura equivalente) junto de
   qualquer número médio - há um outlier de ~0.49% que uma média sozinha
   esconde.
5. **Tratar "recovered" como um conceito único em F05**. Um `recovered`
   por `duration_increase` alterou o contrato do intent
   (`duration_s`); um `recovered` por `route_change` não alterou nada
   declarado. Ver `recovery_type` em
   `results/processed/F05_reconciliation/trials_with_recovery_type.csv`.
6. **Comparar médias sem `n`, IC, teste e effect size juntos**. Todo
   número em `docs/final_claims_and_evidence.md` já vem com isso: nunca
   reduzir para só a média ao escrever o artigo.
7. **Assumir que 20 seeds bastam igualmente para toda métrica**. Para
   rankings de efeito grande (ex.: `least_loss` vs. as outras
   estratégias), 5 já bastam; para taxas de satisfação perto de um
   limiar, 20 pode não ser suficiente - ver
   `docs/seed_justification.md` e a seção de validade estatística de
   `docs/threats_to_validity.md`.
8. **Ler os algoritmos de roteamento/purificação como a contribuição do
   projeto**. Eles são mecanismos para demonstrar a arquitetura - ver
   `docs/core_contribution_statement.md`, "o que não é contribuição".

## Cadeia de reprodutibilidade

Todo número final remonta a: campanha (`docs/results_provenance.md`) →
script (`scripts/run_f0*.py` ou `scripts/build_*`/`classify_*`) →
`results/raw/*/trials.csv` → `results/processed/*/` → figura
(`results/figures/final/*.{pdf,png}` + `sources.json`) ou tabela
estatística (`*/statistical_comparisons.csv`). `scripts/
audit_final_results.py` verifica essa cadeia automaticamente
(`results/audit/final_results_audit.md`).
