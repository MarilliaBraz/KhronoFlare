"""Gera uma versão de arquivo único do painel (para mandar por e-mail ou publicar como página simples).

Junta index.html, style.css, i18n.js, prefs.js, live.js, app.js, data.json, cities.json e o relevo de reserva
(fallback-relief.jpg, como data URI) num só HTML. O Leaflet e as imagens do NASA GIBS continuam vindo
da internet. A aba "Real phone" vira um aviso, porque depende do ntfy.sh e da página phone.html, que só
funcionam na versão em pasta (web/).

Uso:  python3 web/tools/build_single.py saida.html
"""
from __future__ import annotations

import base64
import re
import sys
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent
BOOT_MARKER = "const getJson ="          # início do carregamento por fetch no fim de app.js
FALLBACK = "'fallback-relief.jpg'"


def read(name: str) -> str:
    return (WEB / name).read_text(encoding="utf-8")


def inline_safe(code: str) -> str:
    """Impede que um '</script' dentro do código ou dos dados feche a tag antes da hora."""
    return code.replace("</script", "<\\/script").replace("</SCRIPT", "<\\/SCRIPT")


def app_js() -> str:
    js = read("app.js")
    if BOOT_MARKER not in js or FALLBACK not in js:
        raise SystemExit("app.js mudou: não achei o carregamento por fetch ou o relevo de reserva")
    image = base64.b64encode((WEB / "fallback-relief.jpg").read_bytes()).decode("ascii")
    js = js.replace(FALLBACK, f"'data:image/jpeg;base64,{image}'")
    boot = f"main({read('data.json')}, {read('cities.json')});\n"
    return js[: js.index(BOOT_MARKER)] + boot


def body_html(html: str) -> str:
    body = html[html.index("<body>") + 6: html.index("<script")]
    note = ('<p class="note" data-i18n="single.note">The real-phone link uses ntfy.sh and works in the folder '
            'version of this project (run it locally or on GitHub Pages). Here, use the Phone preview tab.</p>')
    body, n = re.subn(r'(<div class="pane" id="pane-real"[^>]*>).*?(\n  </div>\n\n  <div class="pane" id="pane-log")',
                      lambda m: m.group(1) + "\n    " + note + m.group(2), body, flags=re.S)
    if n != 1:
        raise SystemExit("index.html mudou: não achei a aba do celular de verdade")
    return body.strip()


def main(out: str) -> None:
    html = read("index.html")
    title = re.search(r"<title>.*?</title>", html).group(0)
    links = "\n".join(re.findall(r'<link rel="(?:preconnect|stylesheet)" href="https://[^>]*>', html))
    leaflet = re.search(r'<script src="https://cdnjs\.cloudflare\.com/ajax/libs/leaflet/[^>]*></script>', html).group(0)
    scripts = "\n".join(f"<script>\n{inline_safe(code)}</script>" for code in (read("i18n.js"), read("prefs.js"), read("live.js"), app_js()))
    page = (f"<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
            f"<meta name=\"viewport\" content=\"width=device-width, initial-scale=1, viewport-fit=cover\">\n"
            f"{title}\n{links}\n<style>\n{read('style.css')}</style>\n</head>\n<body>\n{body_html(html)}\n"
            f"{leaflet}\n{scripts}\n</body>\n</html>\n")
    Path(out).write_text(page, encoding="utf-8")
    print(f"ok {out}: {len(page.encode('utf-8')) // 1024} KB")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "painel-alertas.html")
