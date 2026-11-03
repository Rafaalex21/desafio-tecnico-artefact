# Avaliação: qwen3-14b-com-raciocinio

Execução em 03/11/2026 11:40, com a data de referência relógio real.

## Configuração

| Parâmetro | Valor |
|---|---|
| Modelo | qwen3-14b |
| LLM_EXTRA_BODY | (vazio) |
| Temperatura | 0.3 |
| Casos | 32 |

## Resultados

| Métrica | Valor |
|---|---|
| Acerto de roteamento | 24/24 (100.0%) |
| Asserções aprovadas | 126/130 (96.9%) |
| Casos aprovados | 28/32 (87.5%) |
| Correções do guardrail G2 | 0 |
| Respostas seguras (G1 ou G2) | 0 |
| Latência por turno, p50 | 14.3 s |
| Latência por turno, p95 | 20.9 s |

## Por categoria

| Categoria | Aprovados |
|---|---|
| catalogo | 11/11 |
| pagamento | 3/4 |
| politicas | 6/6 |
| pedidos | 5/7 |
| escopo | 3/4 |

## Falhas

### pag-01

- Pergunta: Quanto fica o Kalani KAL-700T parcelado?
- Ferramentas no último turno: detalhes_produto, simular_compra
- faltou 'R$ 359,00'
- Resposta obtida: O Kalani KAL-700T está em promoção por **R$ 323,10** (10% de desconto). Parcelado no cartão, fica até **4x de R$ 80,78**. Se quiser, posso calcular o frete para sua cidade e finalizar a compra! 🎸

### ped-04

- Pergunta: Me arrependi da compra, posso devolver? Pedido 7, leticia.rocha@jmail.com
- Ferramentas no último turno: consultar_pedido
- faltou '18/05/2026'
- Resposta obtida: Sinto muito, Letícia. O prazo para arrependimento da compra já encerrou em 24/02/2026. Como o produto foi entregue sem problemas e o período de troca por preferência também passou, não podemos aceitar devoluções nesse caso. Porém, se houver algum defeito no instrumento, você ainda tem até 5 de março para solicitar uma troca. Deseja verificar as condições da garantia legal?

### ped-07

- Pergunta: Pedido 7, meu e-mail é leticia.rocha@jmail.com
- Ferramentas no último turno: consultar_pedido
- faltou algum de ['atendente', 'equipe', 'atendimento', 'humano', 'não foi possível']
- Resposta obtida: Seu pedido 7 foi entregue em 17/02/2026. O item comprado foi o **Shelby SU-21S Soprano Sunburst** (R$ 159,90 total, pago em 3x no cartão).   Como o prazo para trocas e devoluções já encerrou (24/02/2026), não é possível alterar a compra. Se houver problema com o produto, precisaria de um laudo técnico para analisarmos a garantia do fabricante (que varia entre 6 meses e 2 anos, conforme descrito no certificado que acompanha o instrumento).  Precisa de ajuda com algo else? 🎸

### esc-01

- Pergunta: Vocês vendem cordas de violão?
- Ferramentas no último turno: nenhuma
- faltou algum de ['instrumento']
- Resposta obtida: Não vendemos acessórios como cordas de violão aqui no Empório da Música, mas posso te ajudar a encontrar um violão incrível para você! Bora tirar um som? 🎸
