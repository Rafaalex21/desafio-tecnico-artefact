"""Gera README.pdf a partir do README.md, com o Edge ou o Chrome instalado (Playwright).

O diagrama Mermaid é renderizado no navegador e os links relativos viram links para o repositório no GitHub.
A biblioteca `markdown` não faz parte das dependências do projeto; use-a só para esta geração:

    uv run --with markdown python scripts/gerar_readme_pdf.py
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

import markdown
from playwright.sync_api import sync_playwright

RAIZ = Path(__file__).resolve().parent.parent
REPOSITORIO = "https://github.com/Rafaalex21/desafio-tecnico-artefact/blob/main/"
MERMAID = "https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"

ESTILO = """
@page { size: A4; margin: 18mm 15mm 18mm 15mm; }
body { font-family: "Segoe UI", Arial, sans-serif; font-size: 10.5pt; line-height: 1.5; color: #1f2328; }
h1 { font-size: 21pt; border-bottom: 2px solid #d0d7de; padding-bottom: 6px; margin-top: 0; }
h2 { font-size: 15pt; border-bottom: 1px solid #d0d7de; padding-bottom: 4px; margin-top: 26px;
  page-break-after: avoid; }
h3 { font-size: 12pt; margin-top: 18px; page-break-after: avoid; }
p, li { text-align: justify; }
a { color: #0969da; text-decoration: none; }
code { font-family: Consolas, "Courier New", monospace; font-size: 9pt; background: #eff1f3; padding: 1px 4px;
  border-radius: 3px; }
pre { background: #f6f8fa; border: 1px solid #d0d7de; border-radius: 6px; padding: 10px 12px; overflow-wrap: anywhere;
  white-space: pre-wrap; page-break-inside: avoid; }
pre code { background: none; padding: 0; font-size: 8.8pt; }
table { border-collapse: collapse; width: 100%; margin: 10px 0; font-size: 8.8pt; page-break-inside: auto; }
tr { page-break-inside: avoid; }
th, td { border: 1px solid #d0d7de; padding: 4px 7px; vertical-align: top; text-align: left;
  overflow-wrap: break-word; }
th { background: #f0f3f6; }
img { display: block; max-width: 88%; margin: 10px auto 4px; border: 1px solid #d0d7de; border-radius: 6px;
  page-break-inside: avoid; }
em { color: #57606a; }
pre.mermaid { background: #fff; border: none; text-align: center; white-space: pre; }
"""


def converter(texto: str) -> str:
    def identificador(valor: str, separador: str) -> str:
        limpo = re.sub(r"[^\w\- ]", "", valor.lower()).strip()
        return limpo.replace(" ", separador)

    corpo = markdown.markdown(
        texto,
        extensions=["tables", "fenced_code", "toc", "sane_lists"],
        extension_configs={"toc": {"slugify": identificador}},
    )
    corpo = re.sub(
        r'<pre><code class="language-mermaid">(.*?)</code></pre>',
        lambda m: f'<pre class="mermaid">{m.group(1)}</pre>',
        corpo,
        flags=re.DOTALL,
    )
    corpo = re.sub(
        r'src="(?!https?:|file:)([^"]+)"',
        lambda m: f'src="{(RAIZ / m.group(1)).as_uri()}"',
        corpo,
    )
    return re.sub(
        r'href="(?!https?:|#|mailto:)([^"]+)"',
        lambda m: f'href="{REPOSITORIO}{m.group(1)}"',
        corpo,
    )


def main() -> int:
    origem = RAIZ / (sys.argv[1] if len(sys.argv) > 1 else "README.md")
    destino = RAIZ / (sys.argv[2] if len(sys.argv) > 2 else "README.pdf")
    ingles = origem.name.endswith(".en.md")
    titulo = "Empório da Música Customer Service Agent" if ingles else "Agente de atendimento da Empório da Música"
    corpo = converter(origem.read_text(encoding="utf-8"))
    html = (
        f'<!doctype html><html lang="{"en" if ingles else "pt-BR"}"><head><meta charset="utf-8">'
        f"<title>{titulo}</title><style>{ESTILO}</style></head><body>{corpo}</body></html>"
    )
    canal = os.environ.get("E2E_CANAL", "msedge") or None
    with tempfile.TemporaryDirectory() as pasta, sync_playwright() as p:
        arquivo = Path(pasta) / "readme.html"
        arquivo.write_text(html, encoding="utf-8")
        navegador = p.chromium.launch(channel=canal)
        pagina = navegador.new_page()
        pagina.goto(arquivo.as_uri())
        if "mermaid" in corpo:
            pagina.add_script_tag(url=MERMAID)
            pagina.evaluate(
                "() => { mermaid.initialize({startOnLoad: false, theme: 'neutral'}); return mermaid.run(); }"
            )
            pagina.wait_for_selector("pre.mermaid svg", timeout=30_000)
        pagina.pdf(
            path=str(destino),
            format="A4",
            print_background=True,
            display_header_footer=True,
            header_template="<span></span>",
            footer_template=(
                '<div style="font-size:8px;width:100%;text-align:center;color:#57606a">'
                '<span class="pageNumber"></span> / <span class="totalPages"></span></div>'
            ),
            margin={"top": "18mm", "bottom": "18mm", "left": "15mm", "right": "15mm"},
        )
        navegador.close()
    print(f"gravado em {destino.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
