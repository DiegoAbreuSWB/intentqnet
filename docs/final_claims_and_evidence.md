# Claims finais e evidência (Fase K4)

Toda alegação candidata ao artigo, rastreada até sua evidência,
campanha, suporte estatístico e limitação - nenhuma conclusão deste
projeto deve aparecer no texto do artigo sem uma linha correspondente
aqui. Ver `docs/core_contribution_statement.md` para claims permitidas/
evitadas em nível de enquadramento geral.

| Claim | Evidence | Campaign | Statistical support | Limitation |
|---|---|---|---|---|
| A arquitetura implementa os 9 princípios centrais de IBN sobre redes de distribuição de entrelaçamento | `docs/ibn_principles_mapping.md` (mapeamento princípio-a-princípio) | Todas (F01-F08) | N/A (claim arquitetural, não estatística) | Não cobre concorrência real entre intents nem assurance online |
| O benefício de escolha de rota é real e pode ser isolado quantitativamente | `native_sequence` entrega 438 pares a mais que `static_provisioning`/`ibqn_with_assurance` | F01 | `p≈6.5e-31` (paired t), Holm-adjusted, effect size (Cohen's d)=39.0 | Efeito específico da topologia diamante - ver `docs/routing_result_explanation.md` |
| A reconciliation recupera intents que a assurance sozinha não recupera | `ibqn_with_reconciliation`: satisfação 0.25→1.00, entrega 7.85→339.85 pares | F01 | `p=0.0016` (satisfied), `p=0.0039` (delivered_pairs), Wilcoxon, Holm-adjusted | Um único cenário (diamante); ver F05 para 5 classes mais amplas |
| Assurance detecta e mede satisfação; não altera o resultado físico sozinha | `ibqn_without_assurance` aceita 100% mas não mede satisfação (por desenho) | F01 | N/A (comparação categórica, não estatística) | `ibqn_without_assurance` não é uma condição "pior" fisicamente, só não mede |
| O ganho de rota depende da topologia, não é universal | `least_loss` domina no diamante (~56x); as 3 estratégias são equivalentes na malha pequena | F02 | Diamante: `p≈1.9e-31`; malha: nenhuma comparação sobrevive a Holm | Só 2 topologias testadas para este contraste especificamente |
| A purificação só produz efeito mensurável numa faixa estreita de `min_fidelity` | Diferença significativa só em 0.70/0.72; idêntica em 0.65; rejeitada por igual de 0.73 a 0.75 | F03 (8 limiares, densificado na Fase K2) | `p=0.000008` (0.70 e 0.72), Wilcoxon, Holm-adjusted | Só `three_node_1_repeater`; `linear_chain_2_repeaters` rejeitado em toda faixa testada |
| O planner de fidelidade conservador comete falsos negativos sistemáticos, não aleatórios | 240/240 trials rejeitados oracle-confirmados satisfazíveis; causa raiz: 1 rodada de purificação estimada vs. múltiplas reais | F04 (deriva de F02+F03) | `false_rejection_rate=1.0` sobre 240 testados (não é um teste de hipótese, é uma auditoria exaustiva do subconjunto testável) | Só testado em `three_node_1_repeater`; `linear_chain_2_repeaters` nunca oracle-testado |
| `SequenceConsistentEstimator` reproduz o modelo de fidelidade do SeQUeNCe nas configurações avaliadas | Erro absoluto de fidelidade numericamente zero (vs. ~0.05-0.08 do conservador) | F07 | `p≤0.00002` (Wilcoxon, Holm-adjusted) em 3 comparações (estratégia × estimador) | Não é uma alegação sobre precisão física do SeQUeNCe nem sobre redes reais |
| `reserved_memory_slots` e `duration_s` são dimensões ortogonais de controle | Ambos os fatores têm efeito independente e significativo sobre `delivered_pairs`/`delivery_ratio` | F08 | `p≤4.4e-12` (slots) e `p≤2e-17` (duração), paired t, Holm-adjusted | Só uma topologia (`three_node`), 2 níveis por fator |
| A reconciliation recupera todos os casos de troca de rota e a maioria dos de ajuste de recurso; falha sob perda severa; evita agir corretamente num teto de fidelidade | 15/15, 20/20, 19/20 recuperados; 0/20 sob perda severa; 0 tentativas sob teto de fidelidade | F05 | Wilson 95% CI por classe (`Figure_Reconciliation_RecoveryRate.png`) | Multiplicador de ajuste fixo (2x) - nunca testado se um multiplicador maior recuperaria a perda severa |
| O overhead de orquestração do IBQN é pequeno frente à simulação, mas não universalmente "desprezível" | Média por condição abaixo de 0.31% do tempo total de trial (máximo observado ~0.49% em `static_provisioning`) | F06 | Distribuição completa em `Figure_Overhead_Ratio.png` (não é teste de hipótese - descritivo) | Wall-clock é ruidoso (contenção de CPU); ordens de grandeza relativas, não valores absolutos precisos |
| Tempo de parede de simulação escala com volume de eventos processados, não com "qualidade" da topologia | `native_sequence` leva 2.5x mais tempo de simulação que outras condições, apesar de entregar mais pares | F06 | Achado descritivo, não testado formalmente (n=20, comparação direta de médias) | Não generalizado além desta topologia/faixa de parâmetros |

## Como usar esta tabela

Toda frase do artigo que faça uma alegação quantitativa ou causal deve
corresponder a exatamente uma linha acima (ou ser reformulada até
corresponder). Se uma alegação não tem linha correspondente, ela não
deve aparecer no artigo sem antes ser adicionada aqui com sua evidência
completa (campanha, arquivo bruto, arquivo processado, teste
estatístico, limitação).
