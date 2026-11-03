# Avaliação: qwen3-14b-com-raciocinio-g8-g9

Execução em 03/11/2026 13:27, com a data de referência relógio real.

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
| Asserções aprovadas | 128/130 (98.5%) |
| Casos aprovados | 30/32 (93.8%) |
| Correções do guardrail G2 | 2 |
| Respostas seguras (G1 ou G2) | 0 |
| Latência por turno, p50 | 14.9 s |
| Latência por turno, p95 | 26.4 s |

## Por categoria

| Categoria | Aprovados |
|---|---|
| catalogo | 10/11 |
| pagamento | 4/4 |
| politicas | 6/6 |
| pedidos | 6/7 |
| escopo | 4/4 |

## Falhas

### cat-05

- Pergunta: Vocês têm o Shelby SN-7C?
- Ferramentas no último turno: buscar_produtos
- faltou algum de ['descontinuad', 'não faz mais parte', 'fora de linha']
- Resposta obtida: O Shelby SN-7C 7 Cordas Nylon Natural está temporariamente indisponível na nossa loja. Mas temos outras opções da Shelby disponíveis, como o SN-100 Folk Aço Preto (R$549,00), o SU-21S Soprano Sunburst (R$159,90) e o SGD-195E Elétrico Aço Sunburst (R$799,00). Quer que eu te conte mais sobre alguma dessas opções? 🎸

### ped-04

- Pergunta: Me arrependi da compra, posso devolver? Pedido 7, leticia.rocha@jmail.com
- Ferramentas no último turno: consultar_pedido
- faltou '18/05/2026'
- Resposta obtida: Sinto muito, Letícia. O prazo para arrependimento da compra já expirou em 24 de fevereiro. Porém, ainda há opções: se o instrumento tiver defeito, você pode solicitar troca ou reparo até 5 de março (garantia legal vai até maio). Quer que eu encaminhe essa situação para a equipe?
