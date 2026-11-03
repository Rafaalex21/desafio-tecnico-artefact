"""Gera os payloads JSON que abastecem o painel de acompanhamento a partir do ARCHITECTURE.md.

Saída (em --saida):
    spec_arquitetura.json  -> documento spec/arquitetura  {markdown, versao, atualizado_em, fonte}
    etapa_E0.json ...      -> documentos etapas/E0 ...    {spec_md, spec_refs_md, spec_refs}

spec_md é a subseção da etapa na seção 15; spec_refs_md junta o texto das seções citadas
na linha "Seções:" da etapa, para que cada etapa seja legível sozinha no painel.

Uso:
    python scripts/painel_payload.py --saida .painel
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def extrair_etapas(markdown: str) -> dict[str, str]:
    inicio = re.search(r"^## 15\. .*$", markdown, flags=re.MULTILINE)
    if not inicio:
        raise SystemExit("Seção 15 não encontrada no ARCHITECTURE.md")
    fim = re.search(r"^## 16\. .*$", markdown[inicio.end():], flags=re.MULTILINE)
    secao = markdown[inicio.end(): inicio.end() + fim.start()] if fim else markdown[inicio.end():]

    etapas: dict[str, str] = {}
    blocos = re.split(r"^(?=### E\d+\. )", secao, flags=re.MULTILINE)
    for bloco in blocos:
        cabecalho = re.match(r"### (E\d+)\. ", bloco)
        if cabecalho:
            etapas[cabecalho.group(1)] = bloco.strip() + "\n"
    if not etapas:
        raise SystemExit("Nenhuma etapa '### EN.' encontrada na seção 15")
    return etapas


def indexar_secoes(markdown: str) -> dict[str, str]:
    """Mapeia '5' e '5.3' para o texto da seção (## N.) ou subseção (### N.M)."""
    cabecalhos = list(re.finditer(r"^(##|###) (\d+(?:\.\d+)?)\.? ", markdown, flags=re.MULTILINE))
    secoes: dict[str, str] = {}
    for i, cab in enumerate(cabecalhos):
        nivel = cab.group(1)
        fim = len(markdown)
        for prox in cabecalhos[i + 1:]:
            if len(prox.group(1)) <= len(nivel):
                fim = prox.start()
                break
        else:
            proxima_secao = re.search(r"^## ", markdown[cab.end():], flags=re.MULTILINE)
            if proxima_secao:
                fim = cab.end() + proxima_secao.start()
        secoes[cab.group(2)] = markdown[cab.start():fim].strip()
    return secoes


def referencias(texto_etapa: str) -> list[str]:
    linha = re.search(r"^Seç(?:ão|ões): (.*)$", texto_etapa, flags=re.MULTILINE)
    if not linha:
        return []
    numeros = re.findall(r"(?<![A-Za-z\d.])(\d+(?:\.\d+)?)", linha.group(1))
    # Uma subseção já contida em uma seção citada inteira é descartada.
    return [n for n in dict.fromkeys(numeros) if not ("." in n and n.split(".")[0] in numeros)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--arquivo", type=Path, default=RAIZ / "ARCHITECTURE.md")
    parser.add_argument("--saida", type=Path, default=RAIZ / ".painel")
    args = parser.parse_args()

    markdown = args.arquivo.read_text(encoding="utf-8")
    versao = re.search(r"^Versão ([^,\n]+)", markdown, flags=re.MULTILINE)
    agora = datetime.now().astimezone().isoformat(timespec="seconds")

    args.saida.mkdir(parents=True, exist_ok=True)
    escrever = lambda nome, corpo: (args.saida / nome).write_text(  # noqa: E731
        json.dumps(corpo, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    escrever("spec_arquitetura.json", {
        "markdown": markdown,
        "versao": versao.group(1).strip() if versao else "",
        "atualizado_em": agora,
        "fonte": "ARCHITECTURE.md",
    })
    etapas = extrair_etapas(markdown)
    secoes = indexar_secoes(markdown)
    for codigo, texto in etapas.items():
        refs = [n for n in referencias(texto) if n in secoes]
        escrever(f"etapa_{codigo}.json", {
            "spec_md": texto,
            "spec_refs": refs,
            "spec_refs_md": "\n\n".join(secoes[n] for n in refs) + ("\n" if refs else ""),
        })

    print(f"{len(etapas) + 1} payloads em {args.saida}: spec_arquitetura.json, " + ", ".join(f"etapa_{c}.json" for c in etapas))


if __name__ == "__main__":
    main()
