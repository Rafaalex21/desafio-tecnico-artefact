# Avaliação: gpt-oss-20b-raciocinio-baixo-final

Execução em 03/11/2026 16:22, com a data de referência 2026-03-25T10:30:00-04:00.

## Configuração

| Parâmetro | Valor |
|---|---|
| Modelo | gpt-oss-20b |
| LLM_EXTRA_BODY | {"reasoning_effort":"low"} |
| Temperatura | 0.3 |
| Casos | 32 |

## Resultados

| Métrica | Valor |
|---|---|
| Acerto de roteamento | 23/24 (95.8%) |
| Asserções aprovadas | 125/130 (96.2%) |
| Casos aprovados | 28/32 (87.5%) |
| Correções do guardrail G2 | 0 |
| Respostas seguras (G1 ou G2) | 0 |
| Latência por turno, p50 | 6.0 s |
| Latência por turno, p95 | 12.1 s |

## Por categoria

| Categoria | Aprovados |
|---|---|
| catalogo | 10/11 |
| pagamento | 3/4 |
| politicas | 5/6 |
| pedidos | 7/7 |
| escopo | 3/4 |

## Falhas

### cat-05

- Pergunta: Vocês têm o Shelby SN-7C?
- Ferramentas no último turno: buscar_produtos
- faltou algum de ['7 Cordas', 'RV-174', 'GWNE-7', 'Yamaha', 'Tagima', 'Rozini']
- Resposta obtida: Não temos mais o Shelby SN‑7C; ele está descontinuado.   Posso sugerir outros modelos da linha Shelby, como:  - **Shelby SN‑100 Folk Aço Preto** – violão de 6 cordas em aço (R$ 549,00)   - **Shelby SGD‑195E Elétrico Aço Sunburst** – violão elétrico de 6 cordas em aço (R$ 799,00)  Se quiser mais opções ou algo diferente, é só falar!

### pag-01

- Pergunta: Quanto fica o Kalani KAL-700T parcelado?
- Ferramentas no último turno: buscar_produtos, simular_compra
- faltou '10%'
- Resposta obtida: Kalani KAL‑700T Tenor Natural   Preço original: **R$ 359,00** – 10 % → **R$ 323,10**  Parcelamento no cartão:  - 1x: R$ 323,10   - 2x: R$ 161,55   - 3x: R$ 107,70   - 4x: R$ 80,78    Precisa de algo mais? 🤘

### pol-03

- Pergunta: Produto com defeito, como funciona a troca?
- Ferramentas no último turno: encaminhar_atendente
- não chamou consultar_politicas
- faltou '30 dias'
- Resposta obtida: Sinto muito pelo transtorno. Seu caso foi registrado com protocolo **ATD-20260325-0001** e a equipe retornará até 24 horas úteis. Poderia me informar o número do seu pedido para que eu possa acompanhar melhor?

### esc-04

- Pergunta: O violão chegou riscado, quero reclamar
- Ferramentas no último turno: encaminhar_atendente
- faltou '24 horas'
- Resposta obtida: Sinto muito pelo transtorno. Seu protocolo é **ATD‑20260325‑0001**; a equipe retornará até 24 h úteis.   Para localizar seu pedido, poderia me informar o número do pedido e seu contato (e‑mail ou telefone)?    Posso ajudar em mais alguma coisa?
