#!/usr/bin/env python3
# =====================================================================
# versiculo.py — versiculo do dia por leitura direta e deterministica,
# sem WebSearch nem WebFetch (custa ~zero tokens; 1 chamada de Bash).
#
# Ordem (decisao do usuario, 07/09/2026 — ver prompt mestre Secao 13):
#   1. YouVersion (bible.com) — fonte primaria. Em 07/09 o site devolveu
#      desafio anti-bot ("Client Challenge") ao curl mesmo com o dominio
#      liberado; tentamos 1 vez e seguimos.
#   2. DailyVerses.net — primeira fonte paralela; pagina datada
#      /pt/AAAA/M/D com og:title (referencia - versao) e description
#      (texto). Confere que a data no <title> e a pedida.
# Sem cruzar nem desempatar: a primeira que responder com versiculo
# datado de hoje e publicada, rotulada com a fonte real.
#
# USO:  python3 work/versiculo.py --data 2026-09-07 --dia 250
# SAIDA: JSON em stdout ({"ok": true, "fonte": ..., "referencia": ...,
#        "versao": ..., "texto": ..., "data_pagina": ..., "url": ...})
#        ou {"ok": false, "tentativas": [...]} — ai vale o fallback por
#        WebSearch da ROTINA (passo 6). Exit 0 se ok, 1 se nao.
# =====================================================================

import argparse
import html
import json
import re
import subprocess
import sys

MESES = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "março": 3, "abril": 4,
    "maio": 5, "junho": 6, "julho": 7, "agosto": 8, "setembro": 9,
    "outubro": 10, "novembro": 11, "dezembro": 12,
}
UA = "Mozilla/5.0 (X11; Linux x86_64) Robozinho/1.0"


def fetch(url, timeout=15):
    """curl pelo proxy da sessao. Devolve (codigo_http, html) ou (0, '')."""
    try:
        r = subprocess.run(
            ["curl", "-s", "-L", "-m", str(timeout), "-A", UA,
             "-w", "\n%{http_code}", url],
            capture_output=True, text=True, timeout=timeout + 5,
        )
    except Exception:
        return 0, ""
    out = r.stdout or ""
    codigo = out.rsplit("\n", 1)[-1].strip()
    corpo = out[: -len(codigo) - 1] if codigo else out
    try:
        return int(codigo), corpo
    except ValueError:
        return 0, corpo


def meta(t, prop, attr="property"):
    m = re.search(r'<meta\s+%s="%s"\s+content="(.*?)"' % (attr, re.escape(prop)), t, re.S)
    return html.unescape(m.group(1)).strip() if m else ""


def titulo(t):
    m = re.search(r"<title>(.*?)</title>", t, re.S)
    return html.unescape(m.group(1)).strip() if m else ""


def data_pt(texto):
    """'7 de setembro de 2026' -> '2026-09-07' (ou '')."""
    m = re.search(r"(\d{1,2}) de ([a-zç]+) de (20\d\d)", texto.lower())
    if not m or m.group(2) not in MESES:
        return ""
    return "%s-%02d-%02d" % (m.group(3), MESES[m.group(2)], int(m.group(1)))


def youversion(dia, data, tentativas):
    url = "https://www.bible.com/pt/verse-of-the-day?day=%d" % dia
    codigo, t = fetch(url)
    if codigo != 200 or "Client Challenge" in t or len(t) < 5000:
        tentativas.append({"fonte": "YouVersion", "url": url, "http": codigo,
                           "motivo": "desafio anti-bot ou pagina vazia"})
        return None
    ref = meta(t, "og:title") or titulo(t)
    txt = meta(t, "og:description") or meta(t, "description", "name")
    ref = re.sub(r"^(Vers[ií]culo do Dia|Verse of the Day)\s*[-–|]\s*", "", ref).strip()
    if not ref or not txt:
        tentativas.append({"fonte": "YouVersion", "url": url, "http": codigo,
                           "motivo": "sem og:title/description no HTML"})
        return None
    # A pagina do YouVersion nao imprime a data; o parametro day=N e a ancora.
    return {"ok": True, "fonte": "YouVersion (bible.com)", "referencia": ref,
            "versao": "", "texto": txt, "data_pagina": "day=%d" % dia, "url": url}


def dailyverses(data, tentativas):
    ano, mes, dia = data.split("-")
    url = "https://dailyverses.net/pt/%s/%d/%d" % (ano, int(mes), int(dia))
    codigo, t = fetch(url)
    if codigo != 200 or len(t) < 2000:
        tentativas.append({"fonte": "DailyVerses.net", "url": url, "http": codigo,
                           "motivo": "sem resposta util"})
        return None
    tit = titulo(t)
    data_pag = data_pt(tit)
    if data_pag != data:
        tentativas.append({"fonte": "DailyVerses.net", "url": url, "http": codigo,
                           "motivo": "data da pagina (%s) != pedida (%s)" % (data_pag or tit, data)})
        return None
    og = meta(t, "og:title")           # ex.: "Tiago 4:10 - ARC"
    txt = meta(t, "description", "name") or meta(t, "og:description")
    ref, _, versao = og.partition(" - ")
    if not ref or not txt:
        tentativas.append({"fonte": "DailyVerses.net", "url": url, "http": codigo,
                           "motivo": "sem og:title/description no HTML"})
        return None
    return {"ok": True, "fonte": "DailyVerses.net", "referencia": ref.strip(),
            "versao": versao.strip(), "texto": txt, "data_pagina": data_pag, "url": url}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", required=True, help="AAAA-MM-DD (ancora do passo 1)")
    p.add_argument("--dia", required=True, type=int, help="dia do ano (doy do passo 1)")
    a = p.parse_args()

    tentativas = []
    r = youversion(a.dia, a.data, tentativas) or dailyverses(a.data, tentativas)
    if r:
        r["tentativas"] = tentativas
        print(json.dumps(r, ensure_ascii=False, indent=1))
        sys.exit(0)
    print(json.dumps({"ok": False, "tentativas": tentativas}, ensure_ascii=False, indent=1))
    sys.exit(1)


if __name__ == "__main__":
    main()
