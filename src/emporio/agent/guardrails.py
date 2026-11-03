"""Guardrails de entrada e saída (seção 9.2): G2 valores rastreáveis, G4 entrada, G5 raciocínio vazado,
G6 promoção completa, G7 parcelamento simulado, G8 pedido sem consulta, G9 atraso sem oferta,
G10 situação do produto, G11 datas rastreáveis e G12 encaminhamento registrado."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from emporio.domain.money import fmt_brl

MAX_ENTRADA = 2000
TOLERANCIA = Decimal("0.01")

RESPOSTA_SEGURA = (
    "Opa, me enrolei aqui pra confirmar essa informação. Pode reformular a pergunta, "
    "ou prefere que eu chame alguém da equipe?"
)

_VALOR = re.compile(r"R\$\s*(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{1,2}))?")
_RACIOCINIO = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_RACIOCINIO_ABERTO = re.compile(r"<think>.*", re.DOTALL | re.IGNORECASE)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_TELEFONE = re.compile(r"(?:\+?55\s*)?\(?\d{2}\)?\s*9?\d{4}[-\s]?\d{4}")
_MESES = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)  # fmt: skip
_DATA_NUMERICA = re.compile(r"(?<![\d/])(?:(\d{1,2})/(\d{1,2})/\d{4}|(\d{2})/(\d{2}))(?![\d/])")
_DATA_POR_EXTENSO = re.compile(rf"(?<!\d)(\d{{1,2}})\s+de\s+({'|'.join(_MESES)})", re.IGNORECASE)
_PROTOCOLO = re.compile(r"protocolo\W{0,6}(?:(?:é|e|n[º°o]\.?)\W{0,4})?([\w-]*\d[\w-]*)", re.IGNORECASE)
_ENCAMINHOU = re.compile(
    r"encaminhei|encaminhamos|\bregistrei\b|vou encaminhar|estou encaminhando|j[aá] (?:foi |est[aá] )?encaminhad",
    re.IGNORECASE,
)
_PARCELAMENTO = re.compile(r"(?i:parcel|prest[aã]|\bvezes\b|cart[aã]o)|\b\d{1,2}\s*x\b")


def limpar_entrada(texto: str) -> str:
    """G4: tira caracteres de controle (menos quebra de linha e tabulação), apara e limita a 2.000 caracteres."""
    limpo = "".join(c for c in texto if c in "\n\t" or unicodedata.category(c) != "Cc")
    return limpo.strip()[:MAX_ENTRADA].strip()


def remover_raciocinio(texto: str) -> str:
    """G5: remove blocos `<think>...</think>`, inclusive o bloco que ficou aberto ou sem a tag de abertura."""
    if "</think>" in texto.lower() and "<think>" not in texto.lower():
        texto = re.split(r"</think>", texto, flags=re.IGNORECASE)[-1]
    texto = _RACIOCINIO.sub("", texto)
    return _RACIOCINIO_ABERTO.sub("", texto).strip()


def valores_em_reais(texto: str) -> list[Decimal]:
    """Todos os valores `R$` do texto, em Decimal."""
    valores = []
    for inteiro, centavos in _VALOR.findall(texto):
        fracao = (centavos or "0").ljust(2, "0")
        valores.append(Decimal(f"{inteiro.replace('.', '')}.{fracao}"))
    return valores


def valores_permitidos(mensagens: list[dict[str, Any]]) -> list[Decimal]:
    """Valores `R$` que o agente pode citar: resultados de ferramenta e mensagens do próprio cliente."""
    permitidos: list[Decimal] = []
    for mensagem in mensagens:
        if mensagem.get("role") in ("tool", "user"):
            permitidos.extend(valores_em_reais(str(mensagem.get("content") or "")))
    return permitidos


def valores_nao_rastreaveis(texto: str, permitidos: list[Decimal]) -> list[Decimal]:
    """G2: valores da resposta sem correspondente (tolerância de 1 centavo) entre os permitidos."""
    return [
        valor
        for valor in dict.fromkeys(valores_em_reais(texto))
        if not any(abs(valor - p) <= TOLERANCIA for p in permitidos)
    ]


def aviso_de_correcao(invalidos: list[Decimal], permitidos: list[Decimal]) -> str:
    citados = ", ".join(fmt_brl(v) for v in invalidos)
    disponiveis = ", ".join(fmt_brl(v) for v in dict.fromkeys(permitidos)) or "nenhum"
    return (
        f"[aviso do sistema] Sua resposta citou valores que não vieram das ferramentas: {citados}. "
        f"Os únicos valores que você pode citar são: {disponiveis}. Se faltar algum valor, chame a ferramenta "
        "adequada. Reescreva a resposta ao cliente sem mencionar este aviso."
    )


@dataclass(frozen=True)
class Promocao:
    original: Decimal
    percentual: Decimal
    final: Decimal


def _percentual(valor: Any) -> Decimal | None:
    try:
        return Decimal(str(valor))
    except ArithmeticError:
        return None


def _promocoes_em(dado: Any) -> list[Promocao]:
    """Promoções de um resultado: `promocao` na busca e nos detalhes, `promocao_percentual` na simulação."""
    achadas: list[Promocao] = []
    if isinstance(dado, dict):
        promocao = dado.get("promocao")
        if isinstance(promocao, dict) and dado.get("preco") and promocao.get("preco_promocional"):
            original = valores_em_reais(str(dado["preco"]))
            final = valores_em_reais(str(promocao["preco_promocional"]))
            percentual = _percentual(promocao.get("percentual"))
            if original and final and percentual is not None:
                achadas.append(Promocao(original[0], percentual, final[0]))
        if dado.get("promocao_percentual") is not None and dado.get("preco_tabela") and dado.get("preco_unitario"):
            original = valores_em_reais(str(dado["preco_tabela"]))
            final = valores_em_reais(str(dado["preco_unitario"]))
            percentual = _percentual(dado["promocao_percentual"])
            if original and final and percentual is not None:
                achadas.append(Promocao(original[0], percentual, final[0]))
        for valor in dado.values():
            achadas.extend(_promocoes_em(valor))
    elif isinstance(dado, list):
        for valor in dado:
            achadas.extend(_promocoes_em(valor))
    return achadas


def promocoes_nas_ferramentas(mensagens: list[dict[str, Any]]) -> list[Promocao]:
    achadas: list[Promocao] = []
    for mensagem in mensagens:
        if mensagem.get("role") != "tool":
            continue
        try:
            achadas.extend(_promocoes_em(json.loads(str(mensagem.get("content") or ""))))
        except json.JSONDecodeError:
            continue
    return achadas


def _cita_percentual(texto: str, percentual: Decimal) -> bool:
    exato = percentual == percentual.to_integral_value()
    inteiro = str(int(percentual)) if exato else str(percentual).replace(".", ",")
    return bool(re.search(rf"(?<![\d,.]){re.escape(inteiro)}(?:[.,]0+)?\s*%", texto))


def promocao_incompleta(texto: str, promocoes: list[Promocao]) -> list[str]:
    """G6: para cada promoção cujo preço final aparece na resposta, o que falta citar (preço original e percentual)."""
    citados = valores_em_reais(texto)
    faltas: list[str] = []
    for promocao in promocoes:
        if not any(abs(valor - promocao.final) <= TOLERANCIA for valor in citados):
            continue
        if not any(abs(valor - promocao.original) <= TOLERANCIA for valor in citados):
            faltas.append(f"o preço original {fmt_brl(promocao.original)} (promocional {fmt_brl(promocao.final)})")
        if not _cita_percentual(texto, promocao.percentual):
            desconto = f"{promocao.percentual.normalize():f}%"
            faltas.append(f"o percentual de desconto {desconto} (promocional {fmt_brl(promocao.final)})")
    return list(dict.fromkeys(faltas))


def aviso_de_promocao(faltas: list[str]) -> str:
    return (
        "[aviso do sistema] Ao citar um produto em promoção, a resposta precisa trazer juntos o preço original, "
        f"o percentual de desconto e o preço promocional. Faltou citar: {'; '.join(faltas)}. "
        "Reescreva a resposta ao cliente sem mencionar este aviso."
    )


def parcelamento_sem_simulacao(turno: list[dict[str, Any]]) -> bool:
    """G7: o cliente falou de parcelas ou cartão, o agente consultou um produto e não chamou `simular_compra`."""
    if not turno or not _PARCELAMENTO.search(str(turno[0].get("content") or "")):
        return False
    chamadas = {c["function"]["name"] for m in turno for c in m.get("tool_calls") or []}
    return bool(chamadas & {"detalhes_produto", "buscar_produtos"}) and "simular_compra" not in chamadas


AVISO_DE_PARCELAMENTO = (
    "[aviso do sistema] O cliente perguntou sobre parcelas ou cartão. Chame `simular_compra` com o produto de que "
    "ele falou (sem pedir cidade nem CEP) e responda com o número de parcelas e o valor de cada uma. "
    "Não mencione este aviso."
)


def pedido_sem_consulta(turno: list[dict[str, Any]]) -> bool:
    """G8: o cliente deu número do pedido e e-mail ou telefone e o agente respondeu sem chamar `consultar_pedido`."""
    if not turno:
        return False
    fala = str(turno[0].get("content") or "")
    if not re.search(r"pedido|compra", fala, re.IGNORECASE):
        return False
    contato = _EMAIL.search(fala) or _TELEFONE.search(fala)
    numero = re.search(r"(?<![\d-])\d{1,6}(?![\d-])", _TELEFONE.sub(" ", _EMAIL.sub(" ", fala)))
    chamadas = {c["function"]["name"] for m in turno for c in m.get("tool_calls") or []}
    return bool(contato and numero) and "consultar_pedido" not in chamadas


AVISO_DE_PEDIDO = (
    "[aviso do sistema] O cliente já informou o número do pedido e um contato (e-mail ou telefone), o que basta. "
    "Chame `consultar_pedido` agora, com os dados exatamente como ele escreveu, sem pedir mais nada, e responda "
    "com base no resultado. Não mencione este aviso."
)


def entrega_atrasada_em(mensagens: list[dict[str, Any]]) -> bool:
    def atrasado(dado: Any) -> bool:
        if isinstance(dado, dict):
            return dado.get("entrega_atrasada") is True or any(atrasado(v) for v in dado.values())
        return isinstance(dado, list) and any(atrasado(v) for v in dado)

    for mensagem in mensagens:
        if mensagem.get("role") == "tool":
            try:
                if atrasado(json.loads(str(mensagem.get("content") or ""))):
                    return True
            except json.JSONDecodeError:
                continue
    return False


def atraso_sem_oferta(texto: str, turno: list[dict[str, Any]]) -> bool:
    """G9: pedido com entrega atrasada e a resposta não oferece encaminhar o caso à equipe."""
    return entrega_atrasada_em(turno) and not re.search(r"encaminh|equipe|atendente", texto, re.IGNORECASE)


AVISO_DE_ATRASO = (
    "[aviso do sistema] O pedido está com a entrega atrasada. Reescreva a resposta mantendo o pedido de desculpas e "
    "o rastreio, e pergunte se o cliente quer que você encaminhe o caso à equipe. Não mencione este aviso."
)


def datas_em(texto: str) -> set[tuple[int, int]]:
    """Datas (dia, mês) escritas como 24/02/2026, 24/02 ou 24 de fevereiro."""
    achadas: set[tuple[int, int]] = set()
    for m in _DATA_NUMERICA.finditer(texto):
        dia, mes = (int(m[1]), int(m[2])) if m[1] else (int(m[3]), int(m[4]))
        if 1 <= dia <= 31 and 1 <= mes <= 12:
            achadas.add((dia, mes))
    for m in _DATA_POR_EXTENSO.finditer(texto):
        achadas.add((int(m[1]), _MESES.index(m[2].lower()) + 1))
    return achadas


def datas_nao_rastreaveis(texto: str, mensagens: list[dict[str, Any]]) -> list[str]:
    """G11: datas da resposta que não aparecem no prompt, nas ferramentas nem nas falas do cliente."""
    permitidas: set[tuple[int, int]] = set()
    for mensagem in mensagens:
        if mensagem.get("role") in ("system", "tool", "user"):
            permitidas |= datas_em(str(mensagem.get("content") or ""))
    return [f"{dia:02d}/{mes:02d}" for dia, mes in sorted(datas_em(texto) - permitidas, key=lambda d: (d[1], d[0]))]


def aviso_de_datas(invalidas: list[str]) -> str:
    return (
        f"[aviso do sistema] Sua resposta citou datas que não vieram das ferramentas: {', '.join(invalidas)}. "
        "Nunca calcule prazos nem datas. Reescreva usando apenas as datas devolvidas pela ferramenta, no formato "
        "dd/mm/aaaa em que ela as devolveu. Não mencione este aviso."
    )


_SITUACOES = {
    "descontinuado": (
        re.compile(
            r"descontinuad|n[ãa]o faz mais parte|fora de linha|(?:sa[ií]d[oa]|saiu) d[oea] (?:cat[aá]logo|linha)", re.I
        ),
        "descontinuado (não faz mais parte do catálogo)",
    ),
    "esgotado": (re.compile(r"esgotad|sem estoque|acabou", re.I), "esgotado"),
    "em_breve": (re.compile(r"em breve|chegar|chegada|previs|lan[çc]amento", re.I), "em breve (ainda não chegou)"),
}


_HESITACAO = re.compile(r"temporariamente|talvez|pode ser que|ou esteja|ou tenha", re.IGNORECASE)


def _produtos_indisponiveis(dado: Any) -> list[tuple[str, str]]:
    achados: list[tuple[str, str]] = []
    if isinstance(dado, dict):
        if dado.get("nome") and dado.get("disponibilidade") in _SITUACOES:
            achados.append((str(dado["nome"]), str(dado["disponibilidade"])))
        for valor in dado.values():
            achados.extend(_produtos_indisponiveis(valor))
    elif isinstance(dado, list):
        for valor in dado:
            achados.extend(_produtos_indisponiveis(valor))
    return achados


def _menciona(texto: str, nome: str) -> bool:
    """O texto cita o produto pelo nome ou por um código dele (token com dígito ou hífen, como SN-7C)."""
    normal = re.sub("[‐-―−]", "-", texto).casefold()
    nome = re.sub("[‐-―−]", "-", nome).casefold()
    if nome in normal:
        return True
    return any(len(token) >= 4 and re.search(r"[\d-]", token) and token in normal for token in nome.split())


def situacao_imprecisa(texto: str, mensagens: list[dict[str, Any]]) -> list[str]:
    """G10: produto esgotado, descontinuado ou em breve citado sem dizer qual é a situação."""
    faltas: list[str] = []
    for mensagem in mensagens:
        if mensagem.get("role") != "tool":
            continue
        try:
            produtos = _produtos_indisponiveis(json.loads(str(mensagem.get("content") or "")))
        except json.JSONDecodeError:
            continue
        for nome, situacao in produtos:
            padrao, rotulo = _SITUACOES[situacao]
            vago = situacao == "descontinuado" and _HESITACAO.search(texto)
            if _menciona(texto, nome) and (not padrao.search(texto) or vago):
                faltas.append(f"{nome} está {rotulo}")
    return list(dict.fromkeys(faltas))


def aviso_de_situacao(faltas: list[str]) -> str:
    return (
        f"[aviso do sistema] A ferramenta informa: {'; '.join(faltas)}. Diga a situação exata, sem sugerir outra "
        "(não escreva 'temporariamente indisponível' nem hesite entre esgotado e descontinuado). "
        "Reescreva a resposta corrigindo só isso e mantendo o restante, inclusive as alternativas e a pergunta final. "
        "Não mencione este aviso."
    )


def encaminhamento_sem_registro(texto: str, mensagens: list[dict[str, Any]]) -> bool:
    """G12: a resposta diz que encaminhou o caso ou cita um protocolo que `encaminhar_atendente` não devolveu."""
    chamou = any(
        c["function"]["name"] == "encaminhar_atendente" for m in mensagens for c in m.get("tool_calls") or []
    )
    devolvido = " ".join(str(m.get("content") or "") for m in mensagens if m.get("role") == "tool")
    protocolos = [m[1] for m in _PROTOCOLO.finditer(texto)]
    if any(protocolo not in devolvido for protocolo in protocolos):
        return True
    return not chamou and bool(_ENCAMINHOU.search(texto))


AVISO_DE_ENCAMINHAMENTO = (
    "[aviso do sistema] Você disse que encaminhou o caso, ou citou um protocolo, sem que `encaminhar_atendente` "
    "tenha devolvido um. Chame `encaminhar_atendente` agora (motivo `reclamacao` quando o cliente relata problema "
    "no produto) e informe apenas o protocolo e o prazo de retorno que ela devolver. Não mencione este aviso."
)


def reforco_de_resposta(texto: str, mensagens: list[dict[str, Any]], inicio_turno: int) -> str | None:
    """G6 a G12: devolve o aviso de correção quando a resposta é válida mas incompleta, ou None se está boa."""
    if encaminhamento_sem_registro(texto, mensagens):
        return AVISO_DE_ENCAMINHAMENTO
    if pedido_sem_consulta(mensagens[inicio_turno:]):
        return AVISO_DE_PEDIDO
    if parcelamento_sem_simulacao(mensagens[inicio_turno:]):
        return AVISO_DE_PARCELAMENTO
    if atraso_sem_oferta(texto, mensagens[inicio_turno:]):
        return AVISO_DE_ATRASO
    if invalidas := datas_nao_rastreaveis(texto, mensagens):
        return aviso_de_datas(invalidas)
    if faltas := situacao_imprecisa(texto, mensagens[inicio_turno:]):
        return aviso_de_situacao(faltas)
    faltas = promocao_incompleta(texto, promocoes_nas_ferramentas(mensagens))
    return aviso_de_promocao(faltas) if faltas else None
