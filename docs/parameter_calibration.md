# Calibração dos parâmetros físicos pelo estado da arte (levantamento de 2026-10-01)

Objetivo: fazer cada parâmetro da simulação (`NodeSpec`/`QuantumLinkSpec`,
`docs/physical_model.md`) corresponder a um valor **demonstrado em
experimento publicado em periódico**, com a fonte anotada, e registrar as
decisões de modelagem que a correspondência exige. Os valores entram no
código em `src/ibqn/network/platforms.py` (perfis de plataforma) - esta
página é a justificativa; o código é a fonte da verdade para o valor usado.

Convenções: "fidelidade de enlace" = fidelidade do par memória-memória
heraldado entre dois nós vizinhos (o `raw_fidelity` do SeQUeNCe);
"eficiência" = probabilidade, por tentativa e por fóton, de o fóton da
memória ser emitido, coletado, convertido para telecom e detectado,
**excluída** a atenuação da fibra (que o simulador aplica à parte).

## 1. Entrelaçamento heraldado entre memórias remotas (por plataforma)

| Plataforma / experimento | Distância | Fidelidade do enlace | Taxa | p(sucesso)/tentativa; ciclo | Fonte |
|---|---|---|---|---|---|
| NV em diamante, protocolo de um fóton (Delft) | 2 m | 0,60(2) em 39 Hz (α=0,3); 0,81(2) em 6 Hz (α=0,05) | 6–39 Hz | ≈2·p_det·α, p_det≈4·10⁻⁴; ciclo 5,5 µs | Humphreys et al., *Nature* 558, 268 (2018) |
| NV, rede de 3 nós (Delft) | laboratório | > 0,8 em ambos os enlaces | 9 Hz e 7 Hz | — | Pompili et al., *Science* 372, 259 (2021) |
| NV, pilha de protocolos (Delft) | laboratório | 0,783(7) (tomografia); 0,50–0,80 sob demanda | — | ≈5·10⁻⁵; ciclo 3,8 µs | Pompili et al., *npj Quantum Inf.* 8, 121 (2022) |
| NV, metropolitano, fibra instalada Delft–Haia | 25 km (10 km de separação) | 0,534(15) (α=0,25; máximo teórico 1−α) | 0,022 Hz heraldado (0,48 Hz pós-selecionado) | 7,2·10⁻⁶; ciclo 10 µs | Stolk et al., *Sci. Adv.* 10, eadp6442 (2024) |
| Íons ⁸⁸Sr⁺, dois fótons de 422 nm (Oxford) | 2 m | 0,940(5) | 182 Hz | 2,18·10⁻⁴ (⇒ ≈8·10⁵ tentativas/s) | Stephenson et al., *PRL* 124, 110501 (2020) |
| Íons ⁴⁰Ca⁺ em cavidade, prédios distintos (Innsbruck) | 230 m (520 m de fibra) | 0,882(+2,3/−6,0) | — | 4·10⁻⁵ | Krutyanskiy et al., *PRL* 130, 050803 (2023) |
| Íons Ca⁺, nó repetidor telecom (Innsbruck) | 2×25 km | ion–fóton 0,96(2); par final após swap 0,72(2) | 5,9 Hz (fim-a-fim) | P_link⁰=0,018(1) por nó (geração+detecção telecom) | Krutyanskiy et al., *PRL* 130, 213601 (2023) |
| SiV em cavidade nanofotônica (Harvard) | 20 m | 0,86(3) elétron–elétron | até 1 Hz | — | Knaut et al., *Nature* 629, 573 (2024) |
| SiV, laço urbano de Boston | 35 km (17 dB) | 0,69(7) memória nuclear–nuclear | — | conversão 33 % (ida) / 30 % (volta) | idem |
| Átomos ⁸⁷Rb únicos (Munique) | 6 / 11 / 23 / 33 km | 0,830(10) / 0,799(11) / 0,719(12) / 0,622(15) | 1/19 s⁻¹ (6 km) … 1/208 s⁻¹ (33 km) | 1,22·10⁻⁶; 9,7 kHz (33 km) | van Leent et al., *Nature* 607, 69 (2022) |
| Ensembles atômicos, fibra de campo (USTC) | 22 km | 0,708(37) / 0,732(38) | 1 evento/150 s (TPI) | P_her=1,46·10⁻⁶ | Yu et al., *Nature* 578, 240 (2020) |
| Ensembles atômicos, rede metropolitana de 3 nós (Hefei) | 7,9–12,5 km | 0,672(32) / 0,666(31) | 1,93 Hz e 0,83 Hz (2 nós); ≈1/3 disso com 3 enlaces simultâneos | 6,9–8,0·10⁻⁴; 1–2,8 kHz | Liu et al., *Nature* 629, 579 (2024) |
| Memórias AFC Pr:YSO (ICFO) | 50 m | 0,92(1) (efetiva) | 1,43 kHz heraldado | armazenamento até 25 µs | Lago-Rivera et al., *Nature* 594, 37 (2021) |

Leitura: fidelidades de enlace demonstradas ficam em **0,53–0,94**; em
escala metropolitana (10–35 km) caem para **0,53–0,72**. As taxas
fim-a-fim demonstradas são de **Hz** (0,02–180 Hz por enlace).

## 2. Swapping e destilação demonstrados

| Operação | Resultado | Fonte |
|---|---|---|
| Swapping em nó NV (Bob) | par Alice–Charlie 0,587(28) (resultado selecionado) / 0,551(13) (média) | Pompili et al., *Science* 372, 259 (2021) |
| Swapping + memória, teleporte | par Alice–Charlie ≈0,61; teleporte 0,702(11) | Hermans et al., *Nature* 605, 663 (2022) |
| BSM determinística em íons (swap) | F_swap = 0,95(2); par final 0,72 após 50 km | Krutyanskiy et al., *PRL* 130, 213601 (2023) |
| Destilação (BBPSSW-like) entre nós NV | 0,65(3) após uma rodada; memória 13C decai em 273(5) tentativas | Kalb et al., *Science* 356, 928 (2017) |

## 3. Tempos de coerência de memória

| Sistema | Valor | Condição | Fonte |
|---|---|---|---|
| NV, spin eletrônico (qubit de comunicação) | T₂ = 0,29–0,68 s; par remoto 200(10) ms | desacoplamento dinâmico, ocioso | Humphreys et al., *Nature* 558, 268 (2018) |
| NV, spin eletrônico | > 1 s | DD sob medida | Abobeih et al., *Nat. Commun.* 9, 2552 (2018) |
| NV, memória nuclear ¹³C | T₂ até 63(2) s; estado protegido 75 s | ocioso | Bradley et al., *PRX* 9, 031045 (2019) |
| NV, memória ¹³C **sob tentativas de entrelaçamento** | N₁/e ≈ 1800 tentativas (T₂* 11,6 ms) | rede em operação | Pompili et al., *Science* 372, 259 (2021) |
| idem | N₁/e ≈ 5300 tentativas | desacoplamento ativo | Hermans et al., *Nature* 605, 663 (2022) |
| idem | 106 → 1097–1511 tentativas (7 µs cada) | antes/depois das correções de controle | Kalb et al., *PRA* 97, 062330 (2018) |
| Íons, memória durante protocolo de repetidor | τ = 62(3) ms | protocolo ativo | Krutyanskiy et al., *PRL* 130, 213601 (2023) |
| Íons ¹⁷¹Yb⁺, qubit hiperfino ocioso | > 10 min; estimado 5500 s | DD, resfriamento simpático | Wang et al., *Nat. Photon.* 11, 646 (2017); Wang et al., *Nat. Commun.* 12, 233 (2021) |
| SiV, memória nuclear ²⁹Si | T₂ = 2,1(1) s; elétron T₂ = 78 µs (0,1 K) | — | Stas et al., *Science* 378, 557 (2022); Knaut et al., *Nature* 629, 573 (2024) |
| SiV, spin eletrônico em cavidade | T₂ > 0,2 ms (DD) | — | Bhaskar et al., *Nature* 580, 60 (2020) |
| Átomo de Rb único | T₂ ≈ 330 µs | — | van Leent et al., *Nature* 607, 69 (2022) |
| Ensemble atômico | 107 µs (> RTT); até 560 µs; 70 µs (Yu) | — | Liu et al., *Nature* 629, 579 (2024); Yu et al., *Nature* 578, 240 (2020) |

Decisão de modelagem: o `coherence_time_s` da memória de um **nó repetidor**
é o tempo em que a metade armazenada do par sobrevive **enquanto o nó
continua a tentar o outro enlace** - para NV isso é N₁/e × ciclo (≈10–30 ms),
para íons 62–85 ms, para SiV ≈2 s. Os T₂ de minutos/horas valem para qubits
ociosos e não são usados aqui. O mecanismo dominante é **defasagem** (T₁ ≫ T₂
em todos os casos), então os perfis usam `decoherence_errors = (0, 0, 1)`
(canal de fase, erro Z) em vez do despolarizante.

## 4. Fidelidade de portas e medição em nós de rede

| Operação | Valor | Fonte |
|---|---|---|
| Íons, porta de dois qubits | 99,9(1) % | Ballance et al., *PRL* 117, 060504 (2016) |
| Íons, leitura | 99,991(1) % | Myerson et al., *PRL* 100, 200502 (2008) |
| Íons, BSM determinística em nó de rede (swap) | 0,95(2) | Krutyanskiy et al., *PRL* 130, 213601 (2023) |
| NV, porta elétron–núcleo | 0,97 (baseline de Avis et al.); 94–99 % (Bradley) | Kalb et al., *Science* 356, 928 (2017); Bradley et al., *PRX* 9, 031045 (2019) |
| NV, leitura da memória (BARR) | 99,2(4) % / 98,1(4) % | Hermans et al., *Nature* 605, 663 (2022) |
| SiV, CeNOTₙ desacoplada / CₙNOTₑ | 93,7(7) % / 99,9(1) % | Stas et al., *Science* 378, 557 (2022) |
| SiV, leitura do elétron | 99,5(1) %; 0,9998 (não destrutiva) | Stas et al. (2022); Bhaskar et al., *Nature* 580, 60 (2020) |

## 5. Eficiências ópticas, conversão e detecção

| Grandeza | Valor | Fonte |
|---|---|---|
| NV: p_det (excluída atenuação) | 5,1·10⁻⁴ (baseline); ≈4·10⁻⁴–10⁻³ | Avis et al., *npj Quantum Inf.* 9, 100 (2023) [citando Hermans 2022]; Humphreys 2018; Kalb 2017 |
| Íons em cavidade: p_det (excluída atenuação) | 0,111 | Avis et al. (2023) [citando Schupp et al., *PRX Quantum* 2, 020331 (2021)] |
| Íons, telecom (geração+conversão+detecção) | 0,018(1) por nó | Krutyanskiy et al., *PRL* 130, 213601 (2023) |
| SiV em cavidade: eficiência de heraldagem | 0,423(4) (C = 105) | Bhaskar et al., *Nature* 580, 60 (2020) |
| Conversão de frequência para telecom | NV 17 % (Dréau), 48–50 % (Stolk); Rb 57 % (van Leent); ensembles 33 % (Yu), 46 % (Liu); SiV 33 %/30 % (Knaut) | Dréau et al., *Phys. Rev. Applied* 9, 064031 (2018); Stolk 2024; van Leent 2022; Yu 2020; Liu 2024; Knaut 2024 |
| Detectores SNSPD | 93 % (2013), 98,0(5) % (2020), 99,5 % (2021); 60 % no experimento de campo de Stolk | Marsili et al., *Nat. Photon.* 7, 210 (2013); Reddy et al., *Optica* 7, 1649 (2020); Chang et al., *APL Photon.* 6, 036114 (2021); Stolk 2024 |
| Probabilidade de contagem escura por janela | 1,5·10⁻⁷ (NV), 1,4·10⁻⁵ (íons) | Avis et al. (2023) |

## 6. Fibra óptica

| Grandeza | Valor | Fonte |
|---|---|---|
| Banda C (1550 nm), fibra padrão, medido | 0,22 dB/km | van Leent et al., *Nature* 607, 69 (2022) |
| Banda O (1342–1350 nm) | 0,18 dB/km (campo, 22 km); 0,3 dB/km | Yu et al., *Nature* 578, 240 (2020); Liu et al., *Nature* 629, 579 (2024) |
| Fibra **instalada** com emendas/conectores | 0,39 e 0,51 dB/km (5,6 dB/15 km; 5,2 dB/10 km); 17 dB/35 km (0,49 dB/km) | Stolk et al., *Sci. Adv.* 10 (2024); Knaut et al., *Nature* 629 (2024) |
| Recorde de fibra de sílica | 0,1419 dB/km a 1560 nm | Tamura et al., *J. Lightwave Technol.* 36, 44 (2018) |
| Sem conversão: 637 nm (NV) / 795 nm (Rb) | ≈8 dB/km / 3,5 dB/km | Dréau et al., *Phys. Rev. Applied* 9, 064031 (2018); Yu et al. (2020) |
| Velocidade de grupo (atraso clássico) | c/n ≈ 2·10⁸ m/s ⇒ 5 µs/km | constante do SeQUeNCe (`SPEED_OF_LIGHT`), consistente com n≈1,47 |

## 7. Como a literatura entra no simulador

O protocolo de geração do SeQUeNCe sob BDS (`single_heralded`) exige a
chegada **dos dois** fótons no nó intermediário (BSM linear com sucesso 1/2),
logo p(sucesso/tentativa) = ½·(ε·η·t)², com ε = `memory_efficiency`,
η = `detector_efficiency`, t = transmissão de cada meio-enlace. Isso tem
duas consequências que o manuscrito deve declarar:

1. **Plataformas de baixa eficiência (NV, ε≈5·10⁻⁴) só atingem Hz com o
   protocolo de um fóton** (p ∝ ε·α, Humphreys 2018), que o SeQUeNCe não
   implementa. Com o protocolo de dois fótons, ε_NV dá ≈10⁻⁷ por tentativa -
   inviável em qualquer janela simulável. Por isso o perfil baseline das
   campanhas é uma plataforma com **acoplamento por cavidade** (íons ou SiV),
   em que o protocolo de dois fótons é o efetivamente usado em laboratório
   (Stephenson 2020; Krutyanskiy 2023) e as taxas demonstradas são de
   dezenas a centenas de Hz por enlace.
2. O ciclo de tentativa no SeQUeNCe é limitado pela negociação clássica
   entre vizinhos (≈2× o atraso clássico) e por `memory_frequency_hz`; com
   atraso de 5 µs/km e enlaces de 1–10 km isso dá 10–100 kHz, dentro da
   faixa real (NV 100–260 kHz; íons ≈0,8 MHz; Rb 9,7 kHz).

Mapeamento adotado (ver `platforms.py`):

| Parâmetro IBQN | Íons aprisionados (baseline, 2023) | SiV (2024) | NV (2022) | Ensembles atômicos (2024) |
|---|---|---|---|---|
| `raw_fidelity` | 0,88 (230 m, telecom) | 0,86 | 0,80 | 0,67 |
| `gate_fidelity` | 0,95 (BSM de swap) | 0,937 | 0,97 | n/a (BSM fotônica) → 1,0 |
| `measurement_fidelity` | 0,999 | 0,995 | 0,98 | 0,99 |
| `swapping_success_prob` | 1,0 (determinística) | 1,0 | 1,0 | 0,5 (BSM linear) |
| `coherence_time_s` | 0,062 | 2,0 | 0,02 (≈3600 tentativas × 5,5 µs) | 1·10⁻⁴ |
| `decoherence_errors` | (0,0,1) | (0,0,1) | (0,0,1) | (⅓,⅓,⅓) |
| `memory_efficiency` (ε, c/ conversão) | 0,018 (telecom) / 0,111 (sem conversão) | 0,14 (0,423×0,33) | 5·10⁻⁴ | 0,15 (0,33×0,46) |
| `memory_frequency_hz` (ciclo) | 8·10⁵ | 1,2·10⁶ | 1,8·10⁵ (5,5 µs) | 2,8·10³ |
| `detector_efficiency` | 0,9 | 0,9 | 0,9 | 0,9 |
| `attenuation_db_per_m` (telecom) | 2,2·10⁻⁴ | 2,2·10⁻⁴ (O: 3·10⁻⁴; instalada: 4,9·10⁻⁴) | 2,2·10⁻⁴ (637 nm sem conversão: 8·10⁻³) | 3·10⁻⁴ (banda O) |

Valores "idealizados" anteriores do projeto, para contraste: atenuação
1·10⁻⁵ dB/m (0,01 dB/km - 14× abaixo do recorde mundial), ε = 1, g = m = 1,
coerência infinita, 80 MHz de excitação. Nenhum deles tem respaldo
experimental e todos foram substituídos pelos perfis acima nas campanhas.

## 8. Verificação de viabilidade no simulador (1 s simulado, 4 memórias por nó, cadeia a–r–b)

| Perfil | Enlace | Pares fim-a-fim | Pares elementares/enlace | p(sucesso)/tentativa medido vs. ½(εηt)² | Custo de parede |
|---|---|---|---|---|---|
| Íons (ε=0,018) | 1 km | 6/s, F=0,696 (estimativa 0,751) | ≈39 Hz | 1,2·10⁻⁴ vs. 1,25·10⁻⁴ | 387 s (3,3 M eventos) |
| Íons | 5 km / 10 km | 0 em 1 s (10 e 6 pares elementares) | 5–10 Hz | — | 40 s |
| **SiV (ε=0,14)** | 5 km | **172/s, F=0,703 (estimativa 0,709)** | ≈350 Hz | 6,3·10⁻³ vs. 6,4·10⁻³ | 118 s (0,56 M eventos) |
| NV (ε=5·10⁻⁴) | 1 km | 0 (0 sucessos em 7,2·10⁵ tentativas) | — | ≈10⁻⁷ | 560 s |
| Ensembles (F=0,67) | 5 km | 0 (swap de dois pares 0,67 → 0,48 < ½) | 284 Hz | — | 20 s |

Verificação de realismo: a taxa simulada por enlace de íons (≈39 Hz a 1 km)
fica entre os 182 Hz demonstrados a 2 m (Stephenson 2020) e os 5,9 Hz do
repetidor de 2×25 km (Krutyanskiy 2023). A diferença de 0,055 entre a
fidelidade estimada (0,751) e a observada (0,696) para íons é o efeito da
decoerência (T = 62 ms) enquanto a metade armazenada espera o segundo enlace
a ≈39 Hz - um erro planejador-vs-realidade agora físico.

**Decisão: `DEFAULT_PLATFORM = SIV_2024`.** É a única plataforma demonstrada
em que o protocolo de dois fótons do simulador produz taxas fim-a-fim de
~10²/s em enlaces de 5 km (janelas de 0,1–0,5 s são suficientes para dez
pares), com a memória de repetidor mais longa demonstrada (2 s) e uma
demonstração em fibra instalada de 35 km. O perfil de íons é o caso de
sensibilidade "limitado por taxa"; o NV não é representável sem o protocolo
de um fóton; ensembles não suportam um swap (F < ½ após o swap).

## 9. Teto de purificação com portas imperfeitas (consequência direta da calibração)

Com as fidelidades de porta/medição demonstradas, uma rodada de BBPSSW sobre
o par **já trocado** não melhora - frequentemente piora - a fidelidade;
sobre o par elementar ela ainda ganha pouco ou nada. Valores pela fórmula
exata do SeQUeNCe (`bds_purification_step`, portas de ambos os nós):

| Perfil (raw, g, m) | swap¹ | swap² | swap³ | 1 rodada sobre swap¹ | 1 rodada sobre o par elementar |
|---|---|---|---|---|---|
| SiV (0,86; 0,937; 0,995) | 0,709 | 0,595 | 0,509 | 0,697 (↓) | 0,842 (↓) |
| Íons (0,88; 0,95; 0,999) | 0,751 | 0,649 | 0,568 | 0,752 (≈) | 0,870 (↓) |
| NV (0,80; 0,97; 0,98) | 0,621 | 0,500 | 0,418 | 0,617 (↓) | 0,808 (↑ 0,008) |
| Curto prazo (0,90; 0,99; 0,999) | 0,806 | 0,726 | 0,657 | 0,836 (↑) | 0,918 (↑) |
| Ideal legado (0,85; 1; 1) | 0,730 | 0,634 | 0,557 | 0,768 (↑) | 0,884 (↑) |

Isso é coerente com a única destilação demonstrada entre nós de rede (0,65
após uma rodada a partir de pares ≈0,6; Kalb et al. 2017) e com a análise de
requisitos de Avis et al. (2023). Implicações para as campanhas:

- Sob tecnologia atual, alvos acima da fidelidade do swap são inalcançáveis
  por purificação; o regime informativo é alvo ≤ swap, onde dominam
  decoerência e taxa. O planejador, usando as mesmas fórmulas com ruído de
  porta (`NetworkCapabilities.physics`), prevê isso e rejeita; L2 para no
  ponto fixo ("no further gain").
- A execução `until_target` com portas ruidosas consome pares sem convergir
  (cada rodada reduz a fidelidade) - um modo de falha real que a política
  `never`/`once` evita. A comparação de políticas de purificação passa a ser
  informativa justamente por isso.
- O perfil `near_term_target` (g = 0,99, m = 0,999, ε = 0,30; requisitos
  mínimos de Avis et al. 2023 com as melhores operações locais demonstradas)
  é o eixo "quanto a tecnologia precisa melhorar para a purificação valer a
  pena" - a varredura de `gate_fidelity` ∈ {0,937; 0,95; 0,97; 0,99; 1,0}
  responde isso diretamente.

## 10. Lacunas reconhecidas

- Contagens escuras e visibilidade de interferência (0,89–0,9 em Avis et
  al.) não são modeladas pelo `SingleHeraldedBSM` do SeQUeNCe; a
  infidelidade correspondente está absorvida em `raw_fidelity`.
- O número de memórias por nó nas demonstrações é 1–2 (NV, SiV) a poucos
  íons; as campanhas usam 4–10 por nó como premissa de multiplexação de
  curto prazo e varrem esse valor (`memory_size`).
- Imperfeições de porta/medição entram em swap e purificação, mas não na
  geração (o SeQUeNCe fixa a fidelidade do par gerado em `raw_fidelity`).
