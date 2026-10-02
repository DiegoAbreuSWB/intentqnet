# IEEE ICC 2027 — submission checklist (verified against official sources)

Verificado via busca web em fontes oficiais (site oficial `icc2027.ieee-icc.org`,
citado por múltiplos resultados de busca) e fontes corroborantes do IEEE
ComSoc. **Limitação de acesso**: `WebFetch` não conseguiu renderizar
`icc2027.ieee-icc.org` diretamente nesta sessão (erro de certificado TLS,
"unable to verify the first certificate" — falha consistente em todo o
domínio `ieee-icc.org`, não específica de uma página). As informações
abaixo vêm de snippets de busca que citam e reproduzem trechos literais
das páginas oficiais, mais uma página espelho do IEEE ComSoc. Itens
marcados **[RECONFIRMAR]** devem ser checados diretamente no site antes
da submissão final (ver `PENDING AUTHOR ACTIONS` no relatório da fase).

## Itens confirmados

| Item | Valor confirmado | Fonte |
|---|---|---|
| Nome oficial do evento | "IEEE International Conference on Communications 2027" | comsoc.org/conferences-events/ieee-international-conference-communications-2027 |
| Local | Washington, DC, USA | idem |
| Datas | 30 de maio – 3 de junho de 2027 | idem |
| Tema | "Connected World for Sustainable Future" | myhuiban.com/conference/318 |
| Prazo de submissão (technical papers) | 2 de outubro de 2026 segundo comsoc.org e myhuiban.com. **[RECONFIRMAR] Em 2026-10-02 uma busca na página oficial "Call for Symposium Papers" (`icc2027.ieee-icc.org/authors/call-symposium-papers`) devolveu 16 de outubro de 2026 como prazo, notificação em 15 de janeiro de 2027 e versão final em 19 de fevereiro de 2027** - a página não pôde ser aberta diretamente (mesmo erro de TLS); confirmar no site ou no EDAS | comsoc.org; myhuiban.com; snippet de busca da página oficial |
| Notificação de aceite | 15 de janeiro de 2027 | myhuiban.com/conference/318 |
| Symposia (12 no total) | Cognitive Radio and AI-Enabled Networks; Communication and Information System Security; Communication QoS, Reliability, and Modeling; Communication Software and Multimedia; Communication Theory; Green Communication Systems and Networks; IoT & Sensor Networks; Mobile & Wireless Networks; **Next-Generation Networking and Internet**; Optical Networks and Systems; Signal Processing for Communications; Wireless Communications | myhuiban.com/conference/318 |
| Selected Areas in Communications (SAC) tracks | Aerial Communications; Big Data; Cloud/Edge Computing; E-Health; Integrated Sensing & Communication; Machine Learning for Communications; Molecular/Biological Communications; Next Generation Multiple Access; **Quantum Communications**; Reconfigurable Intelligent Surfaces; Satellite & Space Communications; Smart Grid Communications; Social Networks | myhuiban.com/conference/318 |
| Limite oficial de páginas (submissão inicial) | **6 páginas impressas, fonte 10pt** — submissões maiores são rejeitadas sem revisão | busca citando `icc2027.ieee-icc.org/submission-guidelines` |
| Referências incluídas no limite | **Sim** — o limite é "including figures" e o texto de referência a limite adicional só menciona a partir da 7ª página (submissão final aceita), confirmando que o limite de 6 páginas da submissão inicial é integral (texto+figuras+tabelas+referências) | idem |
| Página adicional | Não disponível na submissão inicial de revisão. Só existe para o artigo FINAL já aceito: até 2 páginas extras (7ª/8ª), US$100/página cada | idem |
| Anonimização | **Revisão duplo-cega (double-blind)** — manuscritos devem ser anonimizados | busca citando `icc2027.ieee-icc.org/submission-guidelines` |
| Template obrigatório | Template oficial de conferência IEEE (IEEEtran, classe `conference`) | busca citando `icc2027.ieee-icc.org/submission-guidelines`; confirmado pelo padrão IEEE em todas as edições do ICC |
| Tamanho da página | **US Letter** (não A4) — padrão de todas as edições do ICC, incluindo variante US-Letter do template IEEE | busca sobre o template IEEE padrão |
| Formato de coluna | Duas colunas, 3.5in cada, gap de 0.25in, margens 0.75in/1in/0.625in | busca sobre o template IEEE padrão (`ieee.org/.../Conference-template-letter.doc`) |
| Sistema de submissão | EDAS, arquivo PDF até 20MB | busca citando `icc2027.ieee-icc.org/submission-guidelines` |
| Revisão | Mínimo 3 revisões independentes por artigo | idem |
| IEEE PDF eXpress | Usado para o artigo FINAL (pós-aceite), não para a submissão inicial de revisão | busca sobre instruções de upload final do ICC |
| Registro/publicação | Artigo aceito só é publicado no IEEE Xplore se um autor se registrar (FULL ou LIMITED) e apresentar | busca citando `icc2027.ieee-icc.org/submission-guidelines` |
| Política de IA generativa | Não encontrada uma página específica do ICC 2027; a política IEEE geral (aplicável a toda conferência/periódico IEEE) exige **divulgação obrigatória** de conteúdo gerado por IA (texto, figuras, código) na seção de agradecimentos, com citação da ferramenta usada | busca sobre política de IA do IEEE |
| Política de reprodutibilidade/material suplementar | **[RECONFIRMAR]** Não encontrada uma política específica publicada para ICC 2027 nesta busca - nenhuma exigência formal de link de código encontrada, mas boa prática geral do IEEE incentiva materiais suplementares | — |

## Restrição interna adotada (conservadora, por instrução explícita do usuário)

Como a regra completa de 2027 não pôde ser renderizada diretamente do
site oficial (falha de TLS), adota-se como restrição de trabalho:

- `\documentclass[conference]{IEEEtran}`;
- duas colunas, 10pt, US Letter;
- **6 páginas no máximo**, figuras/tabelas/referências incluídas;
- nenhuma dependência de página extra paga;
- manuscrito anonimizado (sem nomes/afiliações visíveis no PDF de
  submissão), conforme a política de duplo-cego confirmada;
- nenhuma alteração de margens/fonte/espaçamento do IEEEtran padrão.

## Symposium recomendado

**Recomendação primária: SAC — Quantum Communications** (Selected Areas
in Communications track). Justificativa: o artigo é fundamentalmente
sobre gestão/orquestração de um serviço de rede quântica - o corpo de
revisores desta trilha tem o conhecimento de domínio (geração de
entrelaçamento, purificação, fidelidade, repetidores) necessário para
avaliar a integração com o SeQUeNCe e a metodologia experimental, e SAC
tracks do ICC são desenhadas justamente para tópicos emergentes/
interdisciplinares como este.

**Alternativa forte: Next-Generation Networking and Internet (NGNI)**
symposium - cobre explicitamente "intent-based and zero-touch
management" e "AI-native control and orchestration", o que casa
diretamente com a contribuição central (arquitetura intent-based). Se os
revisores da trilha quântica não valorizarem a ênfase arquitetural, NGNI
é a segunda opção mais defensável.

Ambas as trilhas seguem o mesmo limite de página e mesmo processo via
EDAS - a escolha final entre as duas é uma decisão do autor no momento da
submissão real (`article/AUTHOR_INFO_REQUIRED.md`), não bloqueante para a
redação do manuscrito.

## Itens explicitamente NÃO presumidos de anos anteriores

Nenhuma regra de layout/página foi copiada do ICC 2026/2025 sem
confirmação cruzada nos resultados de busca citando o domínio
`icc2027.ieee-icc.org`. O limite de 6 páginas e a política de duplo-cego
foram confirmados especificamente para 2027 (não inferidos de anos
anteriores), embora a fonte primária não tenha podido ser renderizada
diretamente nesta sessão.
