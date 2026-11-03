"""Ferramentas do agente (seção 7): modelos Pydantic de entrada, JSON Schemas para o LLM e execução.

Toda saída é JSON compacto com `ensure_ascii=False`. Erros de negócio e argumentos inválidos voltam como
`{"erro": ..., "mensagem": ...}`, nunca como exceção, para o modelo poder se corrigir ou explicar ao cliente.
"""

from __future__ import annotations

import json
import sqlite3
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError, model_validator

from emporio.clock import agora
from emporio.config import Settings, get_settings
from emporio.db import abrir_banco
from emporio.domain import busca, handoff, orders, policies
from emporio.domain.compra import simular_compra
from emporio.domain.errors import ErroFerramenta


def _como_texto(valor: Any) -> Any:
    return str(valor) if isinstance(valor, int) and not isinstance(valor, bool) else valor


class _Entrada(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    @model_validator(mode="before")
    @classmethod
    def _descartar_vazios(cls, dados: Any) -> Any:
        """Modelos locais preenchem opcionais com "", null ou 0; isso vale como campo ausente."""
        if not isinstance(dados, dict):
            return dados
        return {
            chave: valor
            for chave, valor in dados.items()
            if valor is not None and valor != "" and not (chave == "numero_pedido" and valor == 0)
        }


class BuscarProdutos(_Entrada):
    """Procura produtos no catálogo por termo, categoria, faixa de preço ou promoção.

    Por padrão só lista itens disponíveis.
    """

    termo: str | None = Field(None, description="Palavras da busca: marca, modelo, tipo de instrumento, detalhe.")
    categoria: str | None = Field(None, description="Nome exato de uma categoria do catálogo.")
    preco_min: float | None = Field(None, description="Preço mínimo em reais, considerando a promoção.")
    preco_max: float | None = Field(None, description="Preço máximo em reais, considerando a promoção.")
    apenas_em_promocao: bool = Field(False, description="Só produtos com promoção ativa.")
    incluir_indisponiveis: bool = Field(False, description="Incluir esgotados, descontinuados e em breve.")
    ordenar_por: Literal["relevancia", "menor_preco", "maior_preco"] | None = Field(
        None, description="Padrão: relevância se houver termo, senão menor preço."
    )
    limite: int = Field(15, description="Quantidade máxima de resultados (padrão 15, máximo 30).")


class DetalhesProduto(_Entrada):
    """Preço, disponibilidade, promoção, especificações e alternativas de um produto específico."""

    produto: Annotated[str, BeforeValidator(_como_texto)] = Field(..., description="Id numérico ou nome do produto.")


class ItemCompra(_Entrada):
    id: int = Field(..., description="Id do produto.")
    quantidade: int = Field(1, description="Quantidade desejada.")


class SimularCompra(_Entrada):
    """Calcula total no PIX, parcelamento no cartão, combinação de pagamentos e frete para produtos específicos."""

    produtos: list[ItemCompra] = Field(..., description="Produtos e quantidades.")
    cidade_entrega: str | None = Field(None, description="Cidade de entrega, para calcular o frete.")


class ConsultarPedido(_Entrada):
    """Status, rastreio, itens e elegibilidade de troca, devolução e garantia de um pedido.

    Exige verificação de identidade.
    """

    numero_pedido: int | None = Field(None, description="Número do pedido. Com ele basta e-mail ou telefone.")
    email: str | None = Field(None, description="E-mail cadastrado na compra.")
    telefone: str | None = Field(None, description="Telefone cadastrado na compra.")


class ConsultarPoliticas(_Entrada):
    """Texto oficial das políticas da loja: trocas, devoluções, pagamento, frete, garantia, promoções e privacidade."""

    topicos: list[Literal[tuple(policies.TOPICOS)]] = Field(  # type: ignore[valid-type]
        ..., description="De 1 a 3 tópicos."
    )


class EncaminharAtendente(_Entrada):
    """Registra o caso para a equipe humana e devolve o protocolo e o prazo de retorno.

    Use em reclamação, pedido atrasado, pedido de falar com uma pessoa ou caso que as regras não cobrem.
    """

    motivo: Literal["reclamacao", "pedido_atrasado", "solicitacao_do_cliente", "fora_das_regras", "outro"]
    resumo: str = Field(..., description="Resumo do caso em poucas frases, para o atendente não repetir perguntas.")
    numero_pedido: int | None = Field(None, description="Pedido relacionado, se houver.")
    contato: str | None = Field(None, description="Contato que o próprio cliente informou, se houver.")


MODELOS: dict[str, type[_Entrada]] = {
    "buscar_produtos": BuscarProdutos,
    "detalhes_produto": DetalhesProduto,
    "simular_compra": SimularCompra,
    "consultar_pedido": ConsultarPedido,
    "consultar_politicas": ConsultarPoliticas,
    "encaminhar_atendente": EncaminharAtendente,
}


def _limpar(esquema: Any) -> Any:
    """Tira títulos e `anyOf` com null: o esquema fica menor e mais fácil para modelos locais."""
    if isinstance(esquema, list):
        return [_limpar(item) for item in esquema]
    if not isinstance(esquema, dict):
        return esquema
    if "anyOf" in esquema:
        opcoes = [o for o in esquema["anyOf"] if o.get("type") != "null"]
        if len(opcoes) == 1:
            restante = {k: v for k, v in esquema.items() if k != "anyOf"}
            return _limpar({**opcoes[0], **restante})
    return {chave: _limpar(valor) for chave, valor in esquema.items() if chave not in ("title", "default")}


def json_schema(nome: str, categorias: list[str] | None = None) -> dict[str, Any]:
    """Definição da ferramenta no formato `tools` da API compatível com OpenAI."""
    modelo = MODELOS[nome]
    esquema = _limpar(modelo.model_json_schema())
    esquema.pop("description", None)
    definicoes = esquema.pop("$defs", {})
    if definicoes:
        esquema["$defs"] = definicoes
    if nome == "buscar_produtos" and categorias:
        esquema["properties"]["categoria"]["enum"] = categorias
    return {
        "type": "function",
        "function": {
            "name": nome,
            "description": " ".join((modelo.__doc__ or "").split()),
            "parameters": esquema,
        },
    }


def _json(dados: dict[str, Any]) -> str:
    return json.dumps(dados, ensure_ascii=False, separators=(",", ":"), default=str)


def _decimal(valor: float | None) -> Decimal | None:
    return None if valor is None else Decimal(str(valor))


class Ferramentas:
    """Conjunto de ferramentas de uma sessão: banco, políticas e estado de verificação de identidade."""

    def __init__(
        self,
        conexao: sqlite3.Connection,
        politicas: dict[str, Any],
        handoff_path: Path,
        session_id: str,
        config: Settings | None = None,
    ) -> None:
        self.conexao = conexao
        self.politicas = politicas
        self.handoff_path = handoff_path
        self.session_id = session_id
        self.config = config
        self.verificacao = orders.Verificacao()

    @classmethod
    def da_configuracao(cls, session_id: str, config: Settings | None = None) -> Ferramentas:
        config = config or get_settings()
        return cls(
            abrir_banco(config.caminho(config.db_path)),
            policies.carregar_politicas(config.caminho(config.politicas_path)),
            config.caminho(config.handoff_path),
            session_id,
            config,
        )

    def schemas(self) -> list[dict[str, Any]]:
        categorias = busca.categorias(self.conexao)
        return [json_schema(nome, categorias) for nome in MODELOS]

    def executar(self, nome: str, argumentos: str | dict[str, Any] | None) -> str:
        """Roda uma ferramenta e devolve o JSON da resposta. Nunca levanta exceção."""
        if nome not in MODELOS:
            return _json({"erro": "ferramenta_desconhecida", "mensagem": f"Não existe a ferramenta {nome!r}."})
        try:
            if isinstance(argumentos, str):
                argumentos = json.loads(argumentos) if argumentos.strip() else {}
            entrada = MODELOS[nome].model_validate(argumentos or {})
            return _json(getattr(self, f"_{nome}")(entrada))
        except ErroFerramenta as erro:
            return _json(erro.como_dict())
        except json.JSONDecodeError:
            return _json({"erro": "argumentos_invalidos", "mensagem": "Os argumentos não são um JSON válido."})
        except ValidationError as erro:
            detalhes = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in erro.errors())
            return _json({"erro": "argumentos_invalidos", "mensagem": detalhes})

    def _buscar_produtos(self, e: BuscarProdutos) -> dict[str, Any]:
        return busca.buscar_produtos(
            self.conexao,
            termo=e.termo,
            categoria=e.categoria,
            preco_min=_decimal(e.preco_min),
            preco_max=_decimal(e.preco_max),
            apenas_em_promocao=e.apenas_em_promocao,
            incluir_indisponiveis=e.incluir_indisponiveis,
            ordenar_por=e.ordenar_por,
            limite=e.limite,
        )

    def _detalhes_produto(self, e: DetalhesProduto) -> dict[str, Any]:
        return busca.detalhes_produto(self.conexao, e.produto)

    def _simular_compra(self, e: SimularCompra) -> dict[str, Any]:
        return simular_compra(self.conexao, [(i.id, i.quantidade) for i in e.produtos], e.cidade_entrega)

    def _consultar_pedido(self, e: ConsultarPedido) -> dict[str, Any]:
        return orders.consultar_pedido(
            self.conexao, self.verificacao, agora(self.config), e.numero_pedido, e.email, e.telefone
        )

    def _consultar_politicas(self, e: ConsultarPoliticas) -> dict[str, Any]:
        return policies.consultar_politicas(self.politicas, list(e.topicos))

    def _encaminhar_atendente(self, e: EncaminharAtendente) -> dict[str, Any]:
        return handoff.registrar_encaminhamento(
            self.handoff_path, agora(self.config), self.session_id, e.motivo, e.resumo, e.numero_pedido, e.contato
        )
