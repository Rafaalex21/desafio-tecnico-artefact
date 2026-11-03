# Preço com promoção e parcelamento

Produto em promoção, com preço original, percentual e preço final, parcelamento no cartão e a regra de que o desconto do PIX não se soma à promoção.

| Parâmetro | Valor |
|---|---|
| Modelo | qwen3-14b |
| Parâmetros extras (`LLM_EXTRA_BODY`) | nenhum (raciocínio do modelo ligado) |
| Temperatura | 0.3 |
| Data de referência | 25/03/2026, quarta-feira, 10h30 (loja aberta) |
| Gerado em | 03/11/2026 16:24 |

Conversa gerada por `scripts/gerar_exemplos.py`, sem edição manual das respostas.

## Turno 1

Cliente:

> Quanto fica o Kalani KAL-700T parcelado?

Riff:

> O Kalani KAL-700T está com **desconto de 10%**: de **R$ 359,00** por **R$ 323,10**. Parcelado no cartão:  
> - 1x R$ 323,10  
> - 2x R$ 161,55  
> - 3x R$ 107,70  
> - 4x R$ 80,78  
>
> No PIX também fica por **R$ 323,10**. Quer que eu calcule o frete? É só me dizer a cidade 😎🎸

Ferramentas chamadas: `detalhes_produto({"produto": "Kalani KAL-700T"})`, `simular_compra({"produtos": [{"id": 127, "quantidade": 1}]})`.

Latência: 30.8 s. Correções automáticas da resposta: 1.

## Turno 2

Cliente:

> E se eu pagar no PIX, tem desconto?

Riff:

> O Kalani KAL-700T está com **desconto de 10%**: de **R$ 359,00** por **R$ 323,10**. O valor promocional já vale para pagamento no PIX ou cartão — não há desconto adicional nesse caso.  
>
> Se quiser, posso te ajudar a calcular o frete ou sugerir outras opções de ukulele 😎🎸

Ferramentas chamadas: nenhuma.

Latência: 14.4 s. Correções automáticas da resposta: 1.
