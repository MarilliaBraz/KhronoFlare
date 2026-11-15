"""Gera uma versão de arquivo único do painel (para publicar como página estática simples).

Junta index.html, style.css, app.js e data.json num só HTML. A aba "Real phone" vira um aviso,
porque essa parte depende do ntfy.sh e só funciona na versão em pasta (web/).

Uso:  python tools/build_single.py saida.html
"""
import re
import sys
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent


def main(out: str) -> None:
    html = (WEB / "index.html").read_text(encoding="utf-8")
    css = (WEB / "style.css").read_text(encoding="utf-8")
    js = (WEB / "app.js").read_text(encoding="utf-8")
    data = (WEB / "data.json").read_text(encoding="utf-8")

    # Dados embutidos no lugar do fetch.
    start = js.index("fetch('data.json')")
    js = js[:start] + "main(" + data + ");\n"

    head_fonts = "\n".join(re.findall(r'<link rel="(?:preconnect|stylesheet)" href="https://fonts[^>]*>', html))
    body = html[html.index("<body>") + 6: html.index("<script")]
    note = ('<p class="note">The real-phone link uses ntfy.sh and works in the folder version of this project '
            '(run it locally or on GitHub Pages). Here, use the Phone preview tab.</p>')
    body = re.sub(r'(<div class="pane" id="pane-real"[^>]*>).*?(\n  </div>\n\n  <div class="pane" id="pane-log")',
                  lambda m: m.group(1) + "\n    " + note + m.group(2), body, flags=re.S)
    title = re.search(r"<title>.*?</title>", html).group(0)

    page = (f"{title}\n<meta name=\"claude:viewport-fit-sides\" content=\"cover\">\n{head_fonts}\n"
            f"<style>\n{css}</style>\n{body.strip()}\n<script>\n{js}</script>\n")
    Path(out).write_text(page, encoding="utf-8")
    print("ok", out, len(page))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "painel-alertas.html")
