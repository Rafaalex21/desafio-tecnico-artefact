# Preço com promoção e parcelamento

Produto em promoção, com preço original, percentual e preço final, parcelamento no cartão e a regra de que o desconto do PIX não se soma à promoção.

| Parâmetro | Valor |
|---|---|
| Modelo | qwen3-14b |
| Parâmetros extras (`LLM_EXTRA_BODY`) | nenhum (raciocínio do modelo ligado) |
| Temperatura | 0.3 |
| Data de referência | 25/03/2026, quarta-feira, 10h30 (loja aberta) |
| Gerado em | 03/11/2026 12:24 |

Conversa gerada por `scripts/gerar_exemplos.py`, sem edição manual das respostas.

## Turno 1

Cliente:

> Quanto fica o Kalani KAL-700T parcelado?

Riff:

> O Kalani KAL-700T está com **10% de desconto** (R$ 359,00 → R$ 323,10).  
> Parcelado no cartão, fica até **4x de R$ 80,78**.  
>
> Para calcular o frete, me diz a cidade onde você quer receber? 🎸

Ferramentas chamadas: `detalhes_produto({"produto": "Kalani KAL-700T"})`, `simular_compra({"produtos": [{"id": 127, "quantidade": 1}]})`.

Latência: 27.4 s.

## Turno 2

Cliente:

> E se eu pagar no PIX, tem desconto?

Riff:

> O Kalani KAL-700T está com **R$ 359,00 (10% de desconto)** no preço promocional de **R$ 323,10**. O PIX não oferece desconto adicional nesse caso, mas você pode pagar com PIX normalmente. Quer que eu ajude a finalizar a compra? 🎸

Ferramentas chamadas: nenhuma.

Latência: 12.7 s. Correções automáticas da resposta: 1.
