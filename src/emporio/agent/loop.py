"""Loop de function calling (seção 9.1): uma mensagem do cliente vira uma resposta validada."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from emporio.agent import guardrails
from emporio.agent.llm import ClienteLLM, ErroLLM, LLMOpenAI
from emporio.agent.memory import Memoria, recortar
from emporio.agent.prompt import montar_system
from emporio.agent.tools import Ferramentas
from emporio.clock import agora, estado_loja
from emporio.config import Settings, get_settings

log = logging.getLogger("emporio.agente")

MAX_ITERACOES = 6
RESPOSTA_VAZIA = "Pode me contar o que você procura ou qual pedido quer acompanhar?"
RESPOSTA_SEM_MODELO = "Opa, fiquei sem sinal aqui por um instante. Tenta de novo daqui a pouco?"

ROTULOS = {
    "buscar_produtos": "Consultando o catálogo",
    "detalhes_produto": "Conferindo o produto",
    "simular_compra": "Calculando valores",
    "consultar_pedido": "Verificando o pedido",
    "consultar_politicas": "Consultando as políticas da loja",
    "encaminhar_atendente": "Acionando a equipe",
}


@dataclass
class ChamadaFerramenta:
    nome: str
    argumentos: str
    resultado: str


@dataclass
class Resultado:
    texto: str
    ferramentas: list[ChamadaFerramenta] = field(default_factory=list)
    latencia_ms: int = 0
    iteracoes: int = 0
    correcoes_g2: int = 0
    reforcos: int = 0
    resposta_segura: bool = False
    erro: bool = False


Status = Callable[[dict[str, str]], None]
FabricaFerramentas = Callable[[str], Ferramentas]


class Agente:
    def __init__(
        self,
        llm: ClienteLLM | None = None,
        memoria: Memoria | None = None,
        config: Settings | None = None,
        fabrica_ferramentas: FabricaFerramentas | None = None,
    ) -> None:
        self.config = config or get_settings()
        self.llm = llm or LLMOpenAI(self.config)
        self.memoria = memoria or Memoria(self.config.caminho(self.config.conversas_db_path))
        self.fabrica_ferramentas = fabrica_ferramentas or (
            lambda session_id: Ferramentas.da_configuracao(session_id, self.config)
        )

    def responder(self, session_id: str, mensagem: str, ao_status: Status | None = None) -> Resultado:
        inicio = time.perf_counter()
        resultado = self._turno(session_id, mensagem, ao_status)
        resultado.latencia_ms = int((time.perf_counter() - inicio) * 1000)
        return resultado

    def _turno(self, session_id: str, mensagem: str, ao_status: Status | None) -> Resultado:
        entrada = guardrails.limpar_entrada(mensagem)
        if not entrada:
            return Resultado(RESPOSTA_VAZIA)

        momento = agora(self.config)
        ferramentas = self.fabrica_ferramentas(session_id)
        ferramentas.verificacao = self.memoria.verificacao(session_id)
        esquemas = ferramentas.schemas()

        historico = recortar(self.memoria.carregar(session_id), self.config.history_max_tokens)
        usuario = {"role": "user", "content": entrada}
        mensagens: list[dict[str, Any]] = [
            {"role": "system", "content": montar_system(momento, estado_loja(momento))},
            *historico,
            usuario,
        ]
        novas: list[dict[str, Any]] = [usuario]
        inicio_turno = len(mensagens) - 1
        resultado = Resultado("")
        corrigido = False
        reforcado = False

        try:
            for iteracao in range(1, MAX_ITERACOES + 1):
                resultado.iteracoes = iteracao
                resposta = self.llm.completar(mensagens, esquemas)
                chamadas = resposta.get("tool_calls")
                if chamadas:
                    mensagens.append(resposta)
                    novas.append(resposta)
                    for chamada in chamadas:
                        nome = chamada["function"]["name"]
                        if ao_status:
                            ao_status({"ferramenta": nome, "rotulo": ROTULOS.get(nome, "Consultando")})
                        argumentos = chamada["function"]["arguments"]
                        if nome == "consultar_pedido":
                            argumentos = guardrails.credenciais_do_cliente(argumentos, mensagens)
                        saida = ferramentas.executar(nome, argumentos)
                        resultado.ferramentas.append(ChamadaFerramenta(nome, argumentos, saida))
                        retorno = {"role": "tool", "tool_call_id": chamada["id"], "content": saida}
                        mensagens.append(retorno)
                        novas.append(retorno)
                    continue

                texto = guardrails.remover_raciocinio(resposta.get("content") or "")
                permitidos = guardrails.valores_permitidos(mensagens)
                invalidos = guardrails.valores_nao_rastreaveis(texto, permitidos)
                if texto and not invalidos:
                    ajuste = None if reforcado else guardrails.reforco_de_resposta(texto, mensagens, inicio_turno)
                    if ajuste is None:
                        resultado.texto = texto
                        break
                    reforcado = True
                    resultado.reforcos += 1
                    mensagens += [{"role": "assistant", "content": texto}, {"role": "user", "content": ajuste}]
                    continue
                if corrigido:
                    log.warning("G2: resposta segura em %s; valores %s; texto %r", session_id, invalidos, texto)
                    resultado.texto, resultado.resposta_segura = guardrails.RESPOSTA_SEGURA, True
                    break
                corrigido = True
                resultado.correcoes_g2 += 1
                aviso = (
                    guardrails.aviso_de_correcao(invalidos, permitidos)
                    if invalidos
                    else "[aviso do sistema] Sua resposta veio vazia. Responda ao cliente."
                )
                mensagens += [{"role": "assistant", "content": texto}, {"role": "user", "content": aviso}]
            else:
                log.warning("G1: limite de iterações em %s", session_id)
                resultado.texto, resultado.resposta_segura = guardrails.RESPOSTA_SEGURA, True
        except ErroLLM as erro:
            log.error("LLM indisponível em %s: %s", session_id, erro)
            return Resultado(RESPOSTA_SEM_MODELO, resultado.ferramentas, erro=True, iteracoes=resultado.iteracoes)

        if not resultado.resposta_segura:
            resultado.texto = guardrails.ajustar_redacao(resultado.texto, mensagens[inicio_turno:])
        novas.append({"role": "assistant", "content": resultado.texto})
        self.memoria.anexar(session_id, novas, momento)
        self.memoria.salvar_verificacao(session_id, ferramentas.verificacao, momento)
        return resultado
