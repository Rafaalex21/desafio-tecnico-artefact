# Avaliação: gpt-oss-20b-raciocinio-baixo

Execução em 03/11/2026 11:29, com a data de referência relógio real.

## Configuração

| Parâmetro | Valor |
|---|---|
| Modelo | gpt-oss-20b |
| LLM_EXTRA_BODY | {"reasoning_effort": "low"} |
| Temperatura | 0.3 |
| Casos | 32 |

## Resultados

| Métrica | Valor |
|---|---|
| Acerto de roteamento | 23/24 (95.8%) |
| Asserções aprovadas | 123/130 (94.6%) |
| Casos aprovados | 26/32 (81.2%) |
| Correções do guardrail G2 | 0 |
| Respostas seguras (G1 ou G2) | 0 |
| Latência por turno, p50 | 6.3 s |
| Latência por turno, p95 | 11.2 s |

## Por categoria

| Categoria | Aprovados |
|---|---|
| catalogo | 10/11 |
| pagamento | 2/4 |
| politicas | 4/6 |
| pedidos | 6/7 |
| escopo | 4/4 |

## Falhas

### cat-05

- Pergunta: Vocês têm o Shelby SN-7C?
- Ferramentas no último turno: buscar_produtos
- faltou algum de ['7 Cordas', 'RV-174', 'GWNE-7', 'Yamaha', 'Tagima', 'Rozini']
- Resposta obtida: O Shelby SN‑7C está **descontinuado** e não temos em estoque.   Se procura violão Shelby, temos:  - **Shelby SN‑100 Folk Aço Preto** – R$ 549,00   - **Shelby SGD‑195E Elétrico Aço Sunburst** – R$ 799,00    Também oferecemos um ukulele Shelby SU‑21S Soprano Sunburst por R$ 159,90, caso queira algo mais compacto.    Posso te ajudar a escolher o modelo ideal?

### pag-01

- Pergunta: Quanto fica o Kalani KAL-700T parcelado?
- Ferramentas no último turno: buscar_produtos, simular_compra
- faltou 'R$ 359,00'
- Resposta obtida: O Kalani KAL‑700T Tenor Natural sai por **R$ 323,10** (promoção de 10%).   Parcelamento no cartão:  - 1x: R$ 323,10   - 2x: R$ 161,55   - 3x: R$ 107,70   - 4x: R$ 80,78    Qualquer dúvida ou quer fazer a compra? Estou por aqui! 🤘

### pag-04

- Pergunta: Em quantas vezes consigo parcelar o Takamine GD20?
- Ferramentas no último turno: buscar_produtos, simular_compra
- faltou '12x'
- Resposta obtida: Você pode parcelar o **Takamine GD20** em até **12 vezes** no cartão, com a parcela mínima de R$ 183,25.    Posso ajudar em mais alguma coisa?

### pol-02

- Pergunta: Vocês abrem domingo?
- Ferramentas no último turno: nenhuma
- faltou algum de ['fechad', 'não abrimos', 'não funcionamos', 'não abre']
- Resposta obtida: Não, fechamos aos domingos e feriados. Se precisar de algo ou quiser marcar um horário durante a semana, é só chamar! Posso ajudar em mais alguma coisa?

### pol-03

- Pergunta: Produto com defeito, como funciona a troca?
- Ferramentas no último turno: encaminhar_atendente
- não chamou consultar_politicas
- faltou '30 dias'
- Resposta obtida: Sinto muito pelo transtorno.   Protocolo: **ATD-20261103-0001** – retorno em até 24 h úteis.    Para que possamos dar andamento à troca, preciso do número do seu pedido e de um contato (telefone ou e‑mail). Você pode me passar esses dados?    Posso ajudar com mais alguma coisa?

### ped-04

- Pergunta: Me arrependi da compra, posso devolver? Pedido 7, leticia.rocha@jmail.com
- Ferramentas no último turno: consultar_pedido
- faltou '18/05/2026'
- Resposta obtida: Não, infelizmente o prazo para arrependimento já expirou (24/02/2026). O pedido foi entregue em 17/02/2026 e agora não está mais elegível para devolução por arrependimento.  Se quiser trocar pelo mesmo modelo ou verificar se há algum defeito que ainda esteja dentro do prazo de garantia, posso ajudar a checar. Posso fazer isso pra você?
