# Avaliação: qwen3-14b-sem-raciocinio-final

Execução em 03/11/2026 16:18, com a data de referência 2026-03-25T10:30:00-04:00.

## Configuração

| Parâmetro | Valor |
|---|---|
| Modelo | qwen3-14b |
| LLM_EXTRA_BODY | {"reasoning_effort":"none"} |
| Temperatura | 0.3 |
| Casos | 32 |

## Resultados

| Métrica | Valor |
|---|---|
| Acerto de roteamento | 21/24 (87.5%) |
| Asserções aprovadas | 123/130 (94.6%) |
| Casos aprovados | 28/32 (87.5%) |
| Correções do guardrail G2 | 1 |
| Respostas seguras (G1 ou G2) | 0 |
| Latência por turno, p50 | 4.4 s |
| Latência por turno, p95 | 9.5 s |

## Por categoria

| Categoria | Aprovados |
|---|---|
| catalogo | 11/11 |
| pagamento | 3/4 |
| politicas | 4/6 |
| pedidos | 7/7 |
| escopo | 3/4 |

## Falhas

### pag-01

- Pergunta: Quanto fica o Kalani KAL-700T parcelado?
- Ferramentas no último turno: detalhes_produto, simular_compra
- faltou 'R$ 359,00'
- faltou '10%'
- Resposta obtida: O Kalani KAL-700T pode ser parcelado em até **4x** no cartão, com o valor de cada parcela sendo:  - 1x: R$ 323,10   - 2x: R$ 161,55   - 3x: R$ 107,70   - 4x: R$ 80,78    Se quiser, posso te ajudar a simular o frete. Basta me dizer a cidade onde você quer que enviamos o produto. 🎸

### pol-04

- Pergunta: Qual o prazo do SEDEX?
- Ferramentas no último turno: nenhuma
- não chamou consultar_politicas
- faltou '2 a 5'
- Resposta obtida: Vou verificar as políticas de frete para você. Um instante!

### pol-05

- Pergunta: Vocês seguram o preço da promoção se o produto esgotar?
- Ferramentas no último turno: nenhuma
- não chamou consultar_politicas
- Resposta obtida: A gente mantém o preço promocional mesmo se o produto esgotar, mas só enquanto houver disponibilidade. Se ele sair do estoque, a promoção pode ser encerrada ou não renovada. Para garantir o melhor desconto, recomendo aproveitar as ofertas enquanto estão disponíveis! 🎸

### esc-04

- Pergunta: O violão chegou riscado, quero reclamar
- Ferramentas no último turno: nenhuma
- não chamou encaminhar_atendente
- faltou '24 horas'
- Resposta obtida: Sinto muito pelo transtorno. Vamos encaminhar o seu caso à nossa equipe para que possamos resolver isso o mais breve possível. Poderia me informar o número do pedido e o contato que você utilizou na compra?
