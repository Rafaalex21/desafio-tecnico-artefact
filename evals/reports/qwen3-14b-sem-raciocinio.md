# Avaliação: qwen3-14b-sem-raciocinio

Execução em 03/11/2026 11:32, com a data de referência relógio real.

## Configuração

| Parâmetro | Valor |
|---|---|
| Modelo | qwen3-14b |
| LLM_EXTRA_BODY | {"reasoning_effort": "none"} |
| Temperatura | 0.3 |
| Casos | 32 |

## Resultados

| Métrica | Valor |
|---|---|
| Acerto de roteamento | 18/24 (75.0%) |
| Asserções aprovadas | 117/130 (90.0%) |
| Casos aprovados | 25/32 (78.1%) |
| Correções do guardrail G2 | 1 |
| Respostas seguras (G1 ou G2) | 0 |
| Latência por turno, p50 | 4.6 s |
| Latência por turno, p95 | 9.0 s |

## Por categoria

| Categoria | Aprovados |
|---|---|
| catalogo | 10/11 |
| pagamento | 2/4 |
| politicas | 3/6 |
| pedidos | 7/7 |
| escopo | 3/4 |

## Falhas

### cat-05

- Pergunta: Vocês têm o Shelby SN-7C?
- Ferramentas no último turno: buscar_produtos
- faltou algum de ['descontinuad', 'não faz mais parte', 'fora de linha']
- faltou algum de ['7 Cordas', 'RV-174', 'GWNE-7', 'Yamaha', 'Tagima', 'Rozini']
- Resposta obtida: O Shelby SN-7C que você perguntou está temporariamente indisponível na loja. Porém, temos algumas opções de violões da marca Shelby disponíveis:  - **Shelby SN-100 Folk Aço Preto** – R$ 549,00   - **Shelby SGD-195E Elétrico Aço Sunburst** – R$ 799,00    Se quiser mais informações sobre alguma dessas opções ou outras alternativas, é só dizer! 🎸

### pag-01

- Pergunta: Quanto fica o Kalani KAL-700T parcelado?
- Ferramentas no último turno: detalhes_produto
- não chamou nenhuma de simular_compra
- faltou algum de ['4x', '4 vezes', '4 parcelas', 'quatro']
- Resposta obtida: O Kalani KAL-700T está à venda por **R$ 323,10** (com desconto de 10% no preço original de R$ 359,00). Se quiser parcelar, posso simular o valor com base na cidade de entrega. Em que cidade você mora?

### pag-04

- Pergunta: Em quantas vezes consigo parcelar o Takamine GD20?
- Ferramentas no último turno: detalhes_produto
- não chamou nenhuma de simular_compra
- faltou 'R$ 183,25'
- Resposta obtida: O Takamine GD20 pode ser parcelado em até 12x no cartão. O preço do produto é R$ 2.199,00 e, se preferir pagar via PIX, o valor será R$ 2.089,05. Deseja que eu te ajude com algo mais? 🎸

### pol-03

- Pergunta: Produto com defeito, como funciona a troca?
- Ferramentas no último turno: nenhuma
- não chamou consultar_politicas
- faltou '30 dias'
- Resposta obtida: Vou te explicar como funciona a troca de um produto com defeito. Primeiro, precisamos verificar se o seu pedido está elegível para troca. Posso ajudar com isso? Me informe o número do pedido e o e-mail ou telefone cadastrado na compra.

### pol-04

- Pergunta: Qual o prazo do SEDEX?
- Ferramentas no último turno: nenhuma
- não chamou consultar_politicas
- faltou '2 a 5'
- Resposta obtida: Para informar o prazo do SEDEX, preciso saber a cidade de entrega. Pode me dizer em qual cidade você mora ou para onde deseja que enviamos o produto?

### pol-05

- Pergunta: Vocês seguram o preço da promoção se o produto esgotar?
- Ferramentas no último turno: nenhuma
- não chamou consultar_politicas
- Resposta obtida: A gente mantém o preço promocional mesmo se o produto esgotar, mas só enquanto houver estoque. Se ele sair do catálogo ou ficar indisponível, a promoção não será renovada automaticamente. Quer que eu verifique se há algum item em promoção disponível?

### esc-04

- Pergunta: O violão chegou riscado, quero reclamar
- Ferramentas no último turno: nenhuma
- não chamou encaminhar_atendente
- faltou '24 horas'
- Resposta obtida: Sinto muito pelo transtorno. Vamos encaminhar o seu caso à nossa equipe de atendimento para que possamos resolver isso o mais rápido possível. Por favor, me informe o número do pedido e o contato que você utilizou na compra.
