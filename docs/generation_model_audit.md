# Auditoria do modelo de geração (protocolo single-heralded, hardware calibrado)

Os planejadores cientes de recursos precisam saber quantos pares fim-a-fim
uma rota produz por segundo. O modelo que eles usavam
(`docs/l3_attempt_rate_audit.md`) foi ajustado ao protocolo Barrett-Kok do
formalismo legado e a um hardware em que metade das tentativas tinha
sucesso. Sob o formalismo Bell-diagonal a geração é *single-heralded*, com
sucesso por tentativa de ~5·10⁻³ no hardware calibrado, e três coisas mudam:
a probabilidade por tentativa, a duração do ciclo e - a mais importante - a
lei que leva de enlaces a pares fim-a-fim. Esta auditoria mede as três no
simulador e as compara com `planning.planners.generation_models`.

```
python scripts/realistic/audit_generation_model.py [workers] [seeds]
```

Dados: `results/realistic/audit/generation_model_audit.csv` (uma linha por
execução) e `generation_model_audit_summary.csv` (uma por célula).

## Desenho

Cadeias lineares `a – r1 – … – rN – b` com N ∈ {0, 1, 2, 3} repetidores,
enlaces de 2, 5 e 10 km, 2 ou 4 memórias reservadas, perfil `siv_2024`,
janela de 0,3 s, purificação desligada e alvo de fidelidade abaixo da saída
de três swaps (todo swap prossegue). 12 sementes por célula (288 execuções)
mais 24 execuções do enlace direto com a reserva no sentido contrário
(`b → a`): 312 no total.

## 1. Ciclo de tentativa: 4 ou 5 atrasos clássicos

Num enlace direto nenhum par espera (é entregue ao ser heraldado), então as
memórias tentam o tempo todo e `tentativas × ciclo = memórias × janela`:

| Sentido da reserva | 2 km | 5 km | 10 km | Modelo |
|---|---|---|---|---|
| `a → b` (quem pede o pareamento **não** é o primário) | 4,0016 | 4,0013 | 4,0027 | 4 |
| `b → a` (quem pede **é** o primário) | 4,9874 | 4,9898 | 4,9938 | 5 |

(em atrasos clássicos de ida do enlace; desvio-padrão entre execuções
≤ 0,002). A causa está nos dois handshakes que precedem cada tentativa no
SeQUeNCe:

1. os *resource managers* pareiam as duas instâncias do protocolo: REQUEST
   do nó anterior na rota (`eg_rule_action2`), RESPONSE de volta;
2. o nó **primário** do protocolo - o de nome lexicograficamente maior
   (`EntanglementGenerationA.primary`) - abre a negociação do instante de
   emissão (NEGOTIATE / NEGOTIATE_ACK).

Se o primário é quem recebeu o REQUEST, ele negocia assim que aprova e os
handshakes se sobrepõem: REQUEST, NEGOTIATE, ACK, resultado = 4 atrasos. Se
o primário é quem pediu, precisa esperar o RESPONSE antes de negociar:
5 atrasos. O mesmo enlace físico é 20% mais lento num sentido da rota. Numa
cadeia `a, r1, …, rN, b` isso afeta só o último enlace (`rN` > `b`); no
diamante, o primeiro do desvio (`r1` > `good1`); na malha, nenhum dos
enlaces da rota usada. `single_heralded_cycle_factor` reproduz a regra.

## 2. Probabilidade de sucesso por tentativa

`p = ½ · (ε·η)² · 10^(−αL/10)`: os dois fótons precisam ser emitidos,
sobreviver à fibra e ser detectados, e a BSM linear acerta metade das vezes.

| Enlace | Tentativas | Sucessos | p do modelo | Medido / modelo | 1σ |
|---|---|---|---|---|---|
| 2 km | 1.722.681 | 11.982 | 6,91·10⁻³ | 1,006 | 0,009 |
| 5 km | 692.421 | 3.880 | 5,62·10⁻³ | 0,997 | 0,016 |
| 10 km | 351.093 | 1.447 | 3,98·10⁻³ | 1,036 | 0,026 |

A fórmula fechada vale dentro de ~1σ nos três comprimentos.

## 3. De enlaces a pares fim-a-fim

### A lei antiga ("mesmo ciclo") não serve

L2-R e L3 supõem que um par fim-a-fim existe quando **todos** os enlaces têm
sucesso na mesma tentativa: `taxa = (memórias/ciclo) · ∏ p`. Com p ≈ 0,5
(hardware idealizado) isso erra por um fator pequeno; com p ≈ 5·10⁻³ a
rede entrega **115–233× mais** que a previsão com um repetidor, ~10⁴× com
dois e ~10⁶–10⁷× com três, porque os enlaces não precisam coincidir: cada um
tem sucesso quando tem e **espera na memória** pelo parceiro de swap.

### A lei com buffer: uma fila de casamento por swap

Um swap junta dois fluxos de pares, cada um guardado em `s` memórias. Um par
que chega e não encontra parceiro espera, e a memória que o guarda **para de
tentar**; com `d` pares esperando, o lado produz a `(s − d)/s` da sua taxa.
A diferença entre os pares esperando dos dois lados é uma cadeia de
nascimento e morte em `−s..s`, e ocorre um swap sempre que chega um par no
lado que está atrás. Com taxas `R_e` e `R_d` (todas as memórias tentando):

```
w(d+1)/w(d)   = ((s − d)/s) · R_e/R_d      (d ≥ 0: pares à esquerda esperando)
w(−d−1)/w(−d) = ((s − d)/s) · R_d/R_e      (pares à direita esperando)
vazão = [ Σ_{d>0} w(d) · R_d + Σ_{d<0} w(d) · R_e ] / Σ_d w(d)
```

Para dois fluxos iguais a vazão é 0,75 da taxa com 2 memórias, 0,82 com 4, e
tende a 1 com buffer grande (`matched_stream_rate`). Uma rota é a composição
dessas filas **na ordem em que o SeQUeNCe troca**
(`ResourceManager.generate_load_rules`: primeiro os nós de índice ímpar,
depois os ímpares do que restou, …), tratando cada segmento já trocado como
um novo fluxo (`buffered_end_to_end_rate`); um swap probabilístico
multiplica a vazão do seu nível pela probabilidade de sucesso. Não há
constante ajustada: entram só `p`, o ciclo (4 ou 5 atrasos) e o número de
memórias.

### Comparação com o simulador (18 células com repetidor, 12 sementes cada)

| Repetidores | Enlace | Memórias | Medido (pares/s) | Modelo | Medido / modelo | 1σ |
|---|---|---|---|---|---|---|
| 1 | 2 km | 2 / 4 | 219,4 / 485,3 | 228,6 / 494,7 | 0,960 / 0,981 | 0,036 / 0,024 |
| 1 | 5 km | 2 / 4 | 72,2 / 153,9 | 74,3 / 160,8 | 0,972 / 0,957 | 0,062 / 0,043 |
| 1 | 10 km | 2 / 4 | 26,7 / 58,9 | 26,3 / 56,9 | 1,014 / 1,034 | 0,102 / 0,069 |
| 2 | 2 km | 2 / 4 | 193,6 / 456,1 | 200,6 / 455,8 | 0,965 / 1,001 | 0,038 / 0,025 |
| 2 | 5 km | 2 / 4 | 58,6 / 138,3 | 65,2 / 148,2 | 0,899 / 0,933 | 0,069 / 0,045 |
| 2 | 10 km | 2 / 4 | 20,6 / 48,6 | 23,1 / 52,5 | 0,890 / 0,927 | 0,116 / 0,076 |
| 3 | 2 km | 2 / 4 | 184,2 / 447,2 | 181,7 / 428,1 | 1,013 / 1,045 | 0,039 / 0,025 |
| 3 | 5 km | 2 / 4 | 54,7 / 136,1 | 59,1 / 139,2 | 0,926 / 0,978 | 0,071 / 0,045 |
| 3 | 10 km | 2 / 4 | 18,6 / 47,8 | 20,9 / 49,3 | 0,890 / 0,970 | 0,122 / 0,076 |

- razão medido/modelo: média 0,964 (0,890–1,045), erro absoluto médio 4,8%;
  somando todos os pares, **0,984**;
- o desvio é compatível com ruído estatístico: χ²/gl = 0,89 contra a
  incerteza de contagem de cada célula;
- contando só a **segunda metade** da janela, a razão agregada é **1,005**:
  a taxa estacionária do modelo é a do simulador, e os ~2% que faltam na
  janela inteira são o transiente de partida (a janela abre com as memórias
  vazias; a primeira entrega leva 3–60 ms conforme o enlace).

Subtrair da janela o tempo esperado até a primeira entrega (o máximo de
exponenciais das taxas dos enlaces, que prevê bem a primeira entrega medida)
não melhora o ajuste (χ²/gl 0,90; razão agregada 1,010; pior nos enlaces
lentos, porque no instante da primeira entrega os buffers já não estão
vazios), então os planejadores usam a taxa estacionária sem correção.

Nos enlaces diretos a razão é 0,99–1,05 no sentido `a → b` e 1,00–1,15 no
sentido contrário (4 sementes, 1σ de 4–15%).

## 4. O que os planejadores usam

| Planejador | Lei de geração | Consequência no hardware calibrado |
|---|---|---|
| L2-R, L3-R | mesmo ciclo, com o ciclo de 4/5 atrasos | prevê ~1 par/s na cadeia de um repetidor a 5 km (o simulador entrega ~154): rejeita tudo (L2-R) ou atribui probabilidade ~0 (L3-R) |
| L3 | mesmo ciclo, taxa de tentativa ingênua | idem |
| **L2-RB**, **L3-RB** | com buffer (filas de casamento) | previsão a ~5% do simulador |

L2-RB admite quando a entrega **esperada** atinge o objetivo, sem margem: um
intent cujo objetivo coincide com a expectativa é admitido e cumprido em
cerca de metade das vezes. L3-RB põe uma distribuição de Poisson em torno
da mesma expectativa. A entrega simulada é sub-dispersa em relação a
Poisson (na campanha de roteamento, desvio-padrão de 4–5 pares para médias
de 43–49), o que torna a probabilidade de L3-RB conservadora perto do
objetivo.

O modelo não inclui: decoerência (pares que caem abaixo do alvo e são
descartados ou purificados), o transiente de partida, nem a regra de
escolha por índice do swap do SeQUeNCe (que não altera a vazão, só quais
pares esperam).

## Nota sobre sementes

A primeira execução desta auditoria usava a derivação antiga de sementes
(`semente + posição`), em que ensaios consecutivos compartilham geradores
aleatórios. O sintoma foi uma probabilidade por tentativa 5–14% abaixo da
fórmula nas cadeias longas, com o mesmo sinal nos três comprimentos de
enlace - o que nenhuma causa física explicava e que desapareceu com
geradores independentes por ensaio (`seed_derivation="independent"`, usado
por todas as topologias calibradas). Estatísticas sobre sementes só são
válidas nessa derivação.
