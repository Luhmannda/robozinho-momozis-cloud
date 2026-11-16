#!/usr/bin/env python3
# =====================================================================
# versiculo.py — versiculo do dia por leitura direta e deterministica,
# sem WebSearch nem WebFetch (custa ~zero tokens; 1 chamada de Bash).
#
# Ordem (decisao do usuario, 07/09/2026 — ver prompt mestre Secao 13):
#   1. YouVersion (bible.com) — fonte primaria, sondada so as segundas desde
#      04/11 (anti-bot persistente). Em 07/09 o site devolveu
#      desafio anti-bot ("Client Challenge") ao curl mesmo com o dominio
#      liberado; tentamos 1 vez e seguimos.
#   2. DailyVerses.net — primeira fonte paralela; pagina datada
#      /pt/AAAA/M/D com og:title (referencia - versao) e description
#      (texto). Confere que a data no <title> e a pedida.
# Sem cruzar nem desempatar: a primeira que responder com versiculo
# datado de hoje e publicada, rotulada com a fonte real.
#
# Sonda do YouVersion (segundas): a falha esperada (anti-bot: http 403/429/503,
# "Client Challenge", pagina vazia) NAO e falha da edicao — source_status
# youversion = nao_tentada, detalhe "sonda_falhou (esperado)", fora de errors e
# do rodape (16/11: "youversion: http 403 (anti-bot)" saiu no rodape).
#
# USO:  python3 work/versiculo.py            (data e dia do ano vem de $ROBOZINHO_TMP/janela.json)
#       python3 work/versiculo.py --data 2026-09-07 --dia 250
#       ROBOZINHO_TMP (padrao /tmp) e a pasta dos arquivos temporarios.
# SAIDA (stdout, 2 linhas):
#   VERSICULO ok | <referencia> (<versao>) | <texto> | fonte: <fonte> | <data_pagina>
#   ou VERSICULO ok=false | <tentativas> | fallback: ate 2 WebSearch (ROTINA, passo 2)
#   SOURCE_STATUS {"youversion": "...", "dailyverses": "..."}
# ARQUIVOS: $ROBOZINHO_TMP/versiculo.json ({"ok", "fonte", "referencia", "versao",
#   "texto", "data_pagina", "url", "tentativas", "source_status"} — lido pelo
#   montar_email.py) e o merge em $ROBOZINHO_TMP/fontes_status.json.
#   Exit 0 se ok, 1 se nao.
# =====================================================================

import argparse
import html
import json
import os
import re
import subprocess
import sys
import time

MESES = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "março": 3, "abril": 4,
    "maio": 5, "junho": 6, "julho": 7, "agosto": 8, "setembro": 9,
    "outubro": 10, "novembro": 11, "dezembro": 12,
}
UA = "Mozilla/5.0 (X11; Linux x86_64) Robozinho/1.0"
TMP = os.environ.get("ROBOZINHO_TMP", "/tmp")
PAUSA_REPETICAO = 3      # segundos antes da nova tentativa (http 0/429/5xx), so no DailyVerses
ANTI_BOT = {403, 429, 503}


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


def fetch_com_repeticao(url):
    """1 nova tentativa apos ~3 s em http 0/429/5xx (falha transitoria)."""
    codigo, t = fetch(url)
    if codigo == 0 or codigo == 429 or codigo >= 500:
        time.sleep(PAUSA_REPETICAO)
        codigo, t = fetch(url)
    return codigo, t


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
        # a sonda das segundas costuma bater no anti-bot: falha esperada, nao erro
        esperado = codigo in ANTI_BOT or "Client Challenge" in t or (codigo == 200 and len(t) < 5000)
        tentativas.append({"fonte": "YouVersion", "url": url, "http": codigo,
                           "motivo": "desafio anti-bot ou pagina vazia", "esperado": esperado})
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
    codigo, t = fetch_com_repeticao(url)
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


def status_das_fontes(r, tentativas, sondou):
    """{id: (status, detalhe)} de youversion e dailyverses."""
    yv = next((t for t in tentativas if t.get("fonte") == "YouVersion"), None)
    dv = next((t for t in tentativas if t.get("fonte") == "DailyVerses.net"), None)
    st = {}
    if r and r.get("fonte", "").startswith("YouVersion"):
        st["youversion"] = ("ok", "sonda das segundas respondeu")
        st["dailyverses"] = ("nao_tentada", "YouVersion respondeu")
        return st
    if not sondou:
        st["youversion"] = ("nao_tentada", "sonda semanal (so as segundas)")
    elif yv and yv.get("esperado", True):
        st["youversion"] = ("nao_tentada", "sonda_falhou (esperado): http %s, %s" % (yv.get("http"), yv.get("motivo")))
    else:
        st["youversion"] = ("nao_tentada", "sonda_falhou (inesperado): http %s, %s"
                            % ((yv or {}).get("http"), (yv or {}).get("motivo")))
    if r:
        st["dailyverses"] = ("ok", "versiculo de %s" % r.get("data_pagina"))
    else:
        st["dailyverses"] = ("falha", "http %s, %s" % ((dv or {}).get("http"), (dv or {}).get("motivo")))
    return st


def gravar_status(st, script="versiculo.py", caminho=None):
    """Merge em $ROBOZINHO_TMP/fontes_status.json ({id: {status, detalhe, script,
    execution_id}}), com trava (os scripts do passo 2 rodam em paralelo)."""
    caminho = caminho or os.path.join(TMP, "fontes_status.json")
    exec_id = ""
    try:
        exec_id = json.load(open(os.path.join(TMP, "janela.json"), encoding="utf-8")).get("execution_id") or ""
    except Exception:
        pass
    try:
        import fcntl
    except ImportError:
        fcntl = None
    with open(caminho + ".lock", "w") as trava:
        if fcntl:
            fcntl.flock(trava, fcntl.LOCK_EX)
        try:
            atual = json.load(open(caminho, encoding="utf-8"))
            if not isinstance(atual, dict):
                atual = {}
        except Exception:
            atual = {}
        for ident, (status, detalhe) in st.items():
            atual[ident] = {"status": status, "detalhe": detalhe, "script": script,
                            "execution_id": exec_id}
        tmp = caminho + ".%d.tmp" % os.getpid()
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(atual, f, ensure_ascii=False, indent=1)
        os.replace(tmp, caminho)


def linha(r):
    """O versiculo numa linha (o JSON completo fica no arquivo)."""
    if r.get("ok"):
        ver = " (%s)" % r["versao"] if r.get("versao") else ""
        return "VERSICULO ok | %s%s | %s | fonte: %s | %s" % (
            r["referencia"], ver, re.sub(r"\s+", " ", r["texto"]).strip(), r["fonte"], r.get("data_pagina") or "")
    tent = "; ".join("%s: http %s, %s" % (t.get("fonte"), t.get("http", "-"), t.get("motivo"))
                     for t in r.get("tentativas") or [])
    return "VERSICULO ok=false | %s | fallback: ate 2 WebSearch (ROTINA, passo 2)" % tent


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", help="AAAA-MM-DD (padrao: a ancora do passo 1, em $ROBOZINHO_TMP/janela.json)")
    p.add_argument("--dia", type=int, help="dia do ano (padrao: doy do $ROBOZINHO_TMP/janela.json)")
    a = p.parse_args()
    if not a.data or not a.dia:
        j = json.load(open(os.path.join(TMP, "janela.json"), encoding="utf-8"))
        a.data, a.dia = a.data or j["data"], a.dia or j["doy"]

    def sair(r, codigo, st):
        r["source_status"] = {k: v[0] for k, v in st.items()}
        # $ROBOZINHO_TMP/versiculo.json: lido pelo work/montar_email.py (o texto nao e redigitado)
        with open(os.path.join(TMP, "versiculo.json"), "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, indent=1)
        try:
            gravar_status(st)
        except Exception as e:
            print("AVISO: fontes_status.json nao gravado (%s)" % e)
        print(linha(r))
        print("SOURCE_STATUS " + json.dumps(r["source_status"], ensure_ascii=False))
        sys.exit(codigo)

    tentativas = []
    # YouVersion devolve desafio anti-bot desde 07/09 (13 falhas em 15 execucoes ate 04/11):
    # vira sonda semanal (segundas). Se voltar a responder, volta a ser a fonte do dia.
    from datetime import date
    sondou = date.fromisoformat(a.data).weekday() == 0
    if sondou:
        r = youversion(a.dia, a.data, tentativas)
    else:
        r = None
        tentativas.append({"fonte": "YouVersion", "motivo": "nao_tentada (sonda semanal, so as segundas)"})
    r = r or dailyverses(a.data, tentativas)
    st = status_das_fontes(r, tentativas, sondou)
    if r:
        r["tentativas"] = tentativas
        sair(r, 0, st)
    sair({"ok": False, "tentativas": tentativas}, 1, st)


if __name__ == "__main__":
    main()
