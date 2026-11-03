# Avaliação: qwen3-14b-com-raciocinio-final

Execução em 03/11/2026 16:15, com a data de referência 2026-03-25T10:30:00-04:00.

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
| Acerto de roteamento | 23/24 (95.8%) |
| Asserções aprovadas | 128/130 (98.5%) |
| Casos aprovados | 31/32 (96.9%) |
| Correções do guardrail G2 | 0 |
| Respostas seguras (G1 ou G2) | 0 |
| Latência por turno, p50 | 14.0 s |
| Latência por turno, p95 | 28.1 s |

## Por categoria

| Categoria | Aprovados |
|---|---|
| catalogo | 11/11 |
| pagamento | 4/4 |
| politicas | 5/6 |
| pedidos | 7/7 |
| escopo | 4/4 |

## Falhas

### pol-03

- Pergunta: Produto com defeito, como funciona a troca?
- Ferramentas no último turno: encaminhar_atendente
- não chamou consultar_politicas
- faltou '30 dias'
- Resposta obtida: Sinto muito pelo transtorno, seu caso foi registrado com o protocolo **ATD-20260325-0001** e nossa equipe retornará em até 24 horas úteis. Como a loja está aberta agora, posso te atender diretamente se precisar de ajuda imediata. Precisa de algo mais?
