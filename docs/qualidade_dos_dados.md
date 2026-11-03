# Qualidade dos dados

Relatório gerado por `uv run emporio-etl`. Não edite à mão: a próxima execução o sobrescreve.

Data de referência usada nas verificações temporais (T10 e T13): 25/03/2026 10:30 (UTC-04).

## Volume carregado

| Tabela | Linhas |
|---|---|
| categories | 9 |
| products | 65 |
| promotions | 25 |
| customers | 50 |
| orders | 20 |
| order_items | 22 |

## Resumo

| ID | Inconsistência | Ocorrências | Tratamento |
|---|---|---|---|
| T1 | Categorias sem nenhum produto | 3 | Busca devolve `categoria_sem_itens`; o agente não inventa itens |
| T2 | Produto ativo com estoque zero | 1 | Classificado como esgotado; sugere alternativas |
| T3 | Produto descontinuado com estoque positivo | 1 | Descontinuado prevalece sobre o estoque |
| T4 | Produto em breve, com estoque e já vendido | 1 | Não é oferecido; pedidos históricos valem |
| T5 | Descrição que cita outra marca | 5 | Nome é canônico; descrição fora da busca e das respostas |
| T6 | Promoções repetidas e inativas | 3 | Só as 4 ativas valem; havendo mais de uma, a de maior desconto |
| T7 | Total do pedido diferente da soma dos itens | 2 | Prevalece o total do pedido |
| T8 | E-mail compartilhado por clientes | 1 | Consulta sem pedido exige e-mail e telefone |
| T9 | Parcela abaixo do mínimo vigente | 3 | Registro histórico, sem questionamento |
| T10 | Pedido enviado com previsão vencida | 1 | Sinalizado como atrasado |

## Detalhes

### T1. Categorias sem produtos

| Categoria | Nome |
|---|---|
| 6 | Instrumentos de Sopro (Madeiras) |
| 7 | Instrumentos de Sopro (Metais) |
| 8 | Cordas Orquestrais |

O manual afirma comercializar esses instrumentos, mas o catálogo não tem nenhum item neles.

### T2. Ativo com estoque zero

| Produto | Nome |
|---|---|
| 96 | Giannini GF-3D Dreadnought Sunburst |

### T3. Descontinuados

| Produto | Nome | Estoque |
|---|---|---|
| 113 | Shelby SN-7C 7 Cordas Nylon Natural | 0 |
| 136 | Ibanez Bass 2X Electric Bass | 13 |

O descontinuado com estoque positivo é tratado como fora do catálogo, conforme o manual (7.3).

### T4. Em breve

| Produto | Nome | Estoque | Pedidos que o incluem |
|---|---|---|---|
| 130 | Kala KA-ABP-CTG Barítono Cedar | 2 | 3,14 |

### T5. Descrição de outra marca

| Produto | Nome | Marca do nome | Marca na descrição |
|---|---|---|---|
| 135 | Music Man Bass 1X Electric Bass | Music Man | Fender |
| 137 | Yamaha Bass 3X Electric Bass | Yamaha | Ibanez |
| 139 | Bateria Acústica Yamaha Kit 1 Studio | Yamaha | Pearl |
| 142 | Teclado Sintetizador Korg Synth 1 Pro | Korg | Roland |
| 144 | Teclado Sintetizador Roland Synth 3 Pro | Roland | Yamaha |

### T6. Promoções

São 25 entradas, das quais 4 ativas.

| Promoção | Produto | Desconto | Descrição |
|---|---|---|---|
| 12 | 127 | 10% | Oferta Especial |
| 14 | 121 | 20% | Desconto Exclusivo |
| 19 | 90 | 18% | Desconto Exclusivo |
| 24 | 94 | 8% | Desconto Exclusivo |

Produtos com mais de uma entrada: 93 (promoções 6,23), 96 (promoções 8,22), 99 (promoções 9,25). Produtos com mais de uma promoção ativa: nenhum.

### T7. Total do pedido

| Pedido | Total do pedido | Soma dos itens | Diferença |
|---|---|---|---|
| 3 | R$ 3.450,00 | R$ 3.498,00 | -R$ 48,00 |
| 20 | R$ 1.400,00 | R$ 1.488,00 | -R$ 88,00 |

A soma dos itens usa os preços de tabela atuais.

### T8. E-mail compartilhado

| E-mail | Clientes |
|---|---|
| bruno.martins@jmail.com | 11,43 |

### T9. Parcelamento abaixo do mínimo

| Pedido | Situação | Total | Parcelas | Valor da parcela | Mínimo vigente |
|---|---|---|---|---|---|
| 9 | confirmed | R$ 349,90 | 6x | R$ 58,32 | R$ 80,00 |
| 16 | pending | R$ 429,90 | 6x | R$ 71,65 | R$ 80,00 |
| 18 | cancelled | R$ 459,90 | 12x | R$ 38,33 | R$ 100,00 |

### T10. Entrega atrasada

| Pedido | Rastreio | Previsão |
|---|---|---|
| 8 | BRJL5544332BR | 2026-02-28 |

## Inconsistências fora do alcance do ETL

T11 e T12 estão no manual (contatos divergentes e parcela mínima contraditória) e são resolvidas nas regras de domínio. T13: o último pedido é de 2026-03-22, 3 dias antes da data de referência; por isso o relógio do sistema é configurável.
