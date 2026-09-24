#!/usr/bin/env python3
# =====================================================================
# coleta_web.py — coleta deterministica das fontes web liberadas no
# allowlist: Congresso (leis e MPVs), ConJur e Migalhas. Substitui o
# curl+regex que o coletor Web improvisava a cada dia (e errava).
#
# - Data/hora exata por item: ConJur e Migalhas expoem
#   article:published_time na pagina da materia (confirmado em 24/09/2026);
#   so as materias cuja data de listagem nao decide sozinha sao abertas.
# - MPV: data oficial "Publicada no DOU de ..." da pagina de detalhe
#   (resolve a armadilha congresso_mpv sem WebSearch).
# - Dedupe: numero da lei/MPV contra as chaves do historico; URL das
#   materias contra as URLs ja publicadas.
#
# USO:   python3 work/coleta_web.py [--janela /tmp/janela.json]
#        (sem janela.json: inicio = window_end do estado, fim = agora)
# SAIDA: resumo compacto em stdout; JSON completo em /tmp/coleta_web.json.
#        Fonte com erro aparece como "ERRO ... usar WebSearch".
# =====================================================================

import argparse
import html
import json
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Sao_Paulo")
UA = "Mozilla/5.0 (X11; Linux x86_64) Robozinho/1.0"
AQUI = os.path.dirname(os.path.abspath(__file__))
MESES = {m: i + 1 for i, m in enumerate(
    "jan fev mar abr mai jun jul ago set out nov dez".split())}

URL_LEIS = "https://www.congressonacional.leg.br/materias/ultimas-leis-publicadas"
URL_MPV = "https://www.congressonacional.leg.br/materias/medidas-provisorias"
URLS_CONJUR = {"noticia": "https://conjur.com.br/noticias/",
               "artigo": "https://conjur.com.br/artigos/",
               "coluna": "https://conjur.com.br/colunas/"}
URL_MIGALHAS = "https://www.migalhas.com.br/quentes"


def fetch(url, timeout=20):
    try:
        r = subprocess.run(["curl", "-s", "-L", "-m", str(timeout), "-A", UA,
                            "-w", "\n%{http_code}", url],
                           capture_output=True, timeout=timeout + 5)
        out = r.stdout.decode("utf-8", "replace")
    except Exception:
        return 0, ""
    corpo, _, codigo = out.rpartition("\n")
    try:
        return int(codigo), corpo
    except ValueError:
        return 0, out


def fetch_many(urls):
    with ThreadPoolExecutor(max_workers=8) as ex:
        return dict(zip(urls, ex.map(fetch, urls)))


def limpa(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def publicado_em(pagina):
    m = re.search(r'property="article:published_time"\s+content="([^"]+)"', pagina)
    if not m:
        return None
    try:
        return datetime.fromisoformat(m.group(1).replace("Z", "+00:00")).astimezone(TZ)
    except ValueError:
        return None


def dmy(s):
    return datetime.strptime(s, "%d/%m/%Y").date()


def carregar_janela(caminho):
    if caminho and os.path.exists(caminho):
        j = json.load(open(caminho, encoding="utf-8"))
        return datetime.fromisoformat(j["inicio"]), datetime.fromisoformat(j["fim"])
    est = json.load(open(os.path.join(AQUI, "robozinho-estado.json"), encoding="utf-8"))
    return (datetime.fromisoformat(est["ultima_execucao"]["window_end"]),
            datetime.now(TZ).replace(microsecond=0))


def chave_url(url):
    m = re.search(r"migalhas\.com\.br/\w+/(\d+)", url or "")
    return "migalhas:" + m.group(1) if m else (url or "").rstrip("/")


def carregar_publicados():
    try:
        h = json.load(open(os.path.join(AQUI, "resumo-legislativo-historico.json"),
                           encoding="utf-8"))["executions"]
    except Exception:
        return set(), set()
    chaves, urls = set(), set()
    for e in h:
        for it in e.get("items") or []:
            chaves.add((it.get("chave") or "").lower())
            if it.get("url"):
                urls.add(chave_url(it["url"]))
    atos = set()
    for k in chaves:
        p = k.split("|")
        if len(p) >= 4 and p[0] == "planalto" and p[2].isdigit():
            atos.add((p[1], p[2]))
    return atos, urls


def classifica(quando, inicio, fim, recorte):
    """NOVA (na janela, ultimas 24h), HERDADA (na janela, antes de 24h),
    FORA (antes do inicio), DEPOIS (apos o fim: entra na proxima edicao)."""
    if quando is None:
        return "SEM_DATA"
    if isinstance(quando, datetime):
        if quando < inicio:
            return "FORA"
        if quando > fim:
            return "DEPOIS"
        return "NOVA" if quando >= recorte else "HERDADA"
    if quando < inicio.date():
        return "FORA"
    return "NOVA" if quando >= recorte.date() else "HERDADA"


# ------------------------------------------------------------ Congresso
def leis(inicio, fim, recorte, atos_pub):
    cod, t = fetch(URL_LEIS)
    out = {"fonte": "congresso_leis", "http": cod, "itens": []}
    for bloco in t.split('<div class="sf-lista-resumos__resumo">')[1:]:
        m = re.search(r'<dt>Norma:</dt>\s*<dd>\s*<a href="([^"]+)">([^<]+)</a>\s*'
                      r'\(<a[^>]*>DOU de (\d\d/\d\d/\d{4})</a>\)', bloco)
        if not m:
            continue
        url, norma, dou = m.group(1), limpa(m.group(2)), dmy(m.group(3))
        n = re.match(r"(.+?) n[ºo°.]*\s*([\d.]+)\s+de\s+(\d\d/\d\d/\d{4})", norma)
        if not n:
            continue
        tipo, numero, data_ato = n.group(1).strip(), n.group(2).replace(".", ""), n.group(3)
        slug = re.sub(r"\s+", "-", tipo.lower())
        ementa = re.search(r"<dt>Ementa:</dt>\s*<dd>(.*?)</dd>", bloco, re.S)
        materia = re.search(r"<dt>Mat[ée]ria:</dt>\s*<dd>\s*<a[^>]*>([^<]+)</a>", bloco)
        veto = re.search(r"<dt>Veto aposto:</dt>\s*<dd>\s*<a[^>]*>([^<]+)</a>", bloco)
        if (slug, numero) in atos_pub:
            sit = "JA_PUBLICADA"
        elif dou < inicio.date() - timedelta(days=7):
            continue
        else:
            # DOU de D sai de madrugada: ato com DOU no dia do inicio da
            # janela so nao foi publicado ontem se a pagina atrasou.
            sit = "NOVA" if dou >= inicio.date() else "HERDADA"
        out["itens"].append({
            "situacao": sit, "tipo": tipo, "numero": numero, "data_ato": data_ato,
            "dou": dou.strftime("%d/%m/%Y"), "ementa": limpa(ementa.group(1)) if ementa else "",
            "materia": limpa(materia.group(1)) if materia else "",
            "veto": limpa(veto.group(1)) if veto else "", "url": url,
            "chave": "planalto|%s|%s|%s|%s" % (slug, numero, data_ato[-4:],
                                               dmy(data_ato).isoformat())})
    return out


def mpvs(inicio, fim, recorte, atos_pub):
    cod, t = fetch(URL_MPV)
    out = {"fonte": "congresso_mpv", "http": cod, "itens": []}
    candidatos = []
    for bloco in t.split('<div class="sf-lista-resumos__resumo">')[1:]:
        m = re.search(r'href="(https://www\.congressonacional\.leg\.br/materias/medidas-provisorias/-/mpv/\d+)"'
                      r'.*?MPV (\d+)/(\d{4})', bloco, re.S)
        dia = re.search(r"Dia de tramita[çc][ãa]o</dt>\s*<dd><span>(\d+)</span>", bloco)
        if not m or not dia or int(dia.group(1)) > 10:
            continue
        ementa = re.search(r"<dt>Ementa</dt>\s*<dd>(.*?)</dd>", bloco, re.S)
        candidatos.append((m.group(1), m.group(2), m.group(3),
                           limpa(ementa.group(1)) if ementa else ""))
    paginas = fetch_many([c[0] for c in candidatos])
    for url, numero, ano, ementa in candidatos:
        c2, p = paginas[url]
        d = re.search(r"Publicada no DOU de (\d\d/\d\d/\d{4})", p)
        dou = dmy(d.group(1)) if d else None
        if ("mpv", numero) in atos_pub:
            sit = "JA_PUBLICADA"
        else:
            sit = classifica(dou, inicio, fim, recorte) if dou else "SEM_DATA_OFICIAL"
        out["itens"].append({
            "situacao": sit, "numero": numero, "ano": ano, "ementa": ementa,
            "dou": dou.strftime("%d/%m/%Y") if dou else "", "http_detalhe": c2, "url": url,
            "chave": "planalto|mpv|%s|%s|%s" % (numero, ano, dou.isoformat() if dou else "")})
    return out


# ------------------------------------------------------------ Midia
def conjur(inicio, fim, recorte, urls_pub):
    pags = fetch_many(list(URLS_CONJUR.values()))
    out = {"fonte": "conjur", "http": {k: pags[u][0] for k, u in URLS_CONJUR.items()},
           "itens": []}
    vistos, abrir = {}, []
    padrao = re.compile(r'<h2 class="conjur-posts-tipo-titulo"[^>]*>\s*<a href="'
                        r'(https://conjur\.com\.br/(\d{4})-([a-z]{3})-(\d{2})/[^"]+)"[^>]*>(.*?)</a>', re.S)
    for tipo, u in URLS_CONJUR.items():
        for url, a, mes, d, tit in padrao.findall(pags[u][1]):
            if url in vistos or mes not in MESES:
                continue
            dia = date(int(a), MESES[mes], int(d))
            it = {"tipo": tipo, "titulo": limpa(tit), "url": url, "data": dia}
            vistos[url] = it
            if dia < inicio.date():
                it["situacao"] = "FORA"
            elif dia in (inicio.date(), recorte.date(), fim.date()):
                abrir.append(url)          # so a hora decide
            else:
                it["situacao"] = "NOVA"
    for url, (c, p) in fetch_many(abrir).items():
        quando = publicado_em(p)
        it = vistos[url]
        it["quando"] = quando
        it["situacao"] = classifica(quando, inicio, fim, recorte) if quando else "HERDADA"
    for it in vistos.values():
        if chave_url(it["url"]) in urls_pub:
            it["situacao"] = "JA_PUBLICADA"
        out["itens"].append(it)
    return out


def migalhas(inicio, fim, recorte, urls_pub):
    cod, t = fetch(URL_MIGALHAS)
    out = {"fonte": "migalhas", "http": cod, "itens": []}
    lista = []
    for art in t.split("<article")[1:]:
        m = re.search(r'href="(https://www\.migalhas\.com\.br/quentes/\d+/[^"]+)"', art)
        h2 = re.search(r'class="topico__header">(.*?)</h2>', art, re.S)
        if not m or not h2:
            continue
        h3 = re.search(r'class="topico__body">(.*?)</h3>', art, re.S)
        badge = re.search(r'class="badge badge--\w+">([^<]+)<', art)
        lista.append({"titulo": limpa(h2.group(1)), "resumo": limpa(h3.group(1)) if h3 else "",
                      "badge": limpa(badge.group(1)) if badge else "", "url": m.group(1)})
    unicos = {i["url"]: i for i in lista}
    paginas = fetch_many(list(unicos))
    for url, it in unicos.items():
        quando = publicado_em(paginas[url][1])
        it["quando"] = quando
        it["situacao"] = ("JA_PUBLICADA" if chave_url(url) in urls_pub
                          else classifica(quando, inicio, fim, recorte))
        out["itens"].append(it)
    return out


# ------------------------------------------------------------ saida
def hm(it):
    q = it.get("quando")
    if isinstance(q, datetime):
        return q.strftime("%d/%m %H:%M")
    d = it.get("data")
    return d.strftime("%d/%m") if d else "?"


def ok(http):
    vals = http.values() if isinstance(http, dict) else [http]
    return all(v == 200 for v in vals)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--janela", default="/tmp/janela.json")
    ap.add_argument("--saida", default="/tmp/coleta_web.json")
    a = ap.parse_args()
    inicio, fim = carregar_janela(a.janela)
    recorte = fim - timedelta(hours=24)
    atos_pub, urls_pub = carregar_publicados()

    with ThreadPoolExecutor(max_workers=4) as ex:
        fl = ex.submit(leis, inicio, fim, recorte, atos_pub)
        fm = ex.submit(mpvs, inicio, fim, recorte, atos_pub)
        fc = ex.submit(conjur, inicio, fim, recorte, urls_pub)
        fg = ex.submit(migalhas, inicio, fim, recorte, urls_pub)
        res = [fl.result(), fm.result(), fc.result(), fg.result()]

    print("JANELA %s -> %s (herdada = antes de %s)" % (
        inicio.isoformat(), fim.isoformat(), recorte.strftime("%d/%m %H:%M")))
    for r in res:
        itens = r["itens"]
        cont = {}
        for i in itens:
            cont[i["situacao"]] = cont.get(i["situacao"], 0) + 1
        print("\n== %s http=%s %s" % (r["fonte"].upper(), r["http"],
                                      " ".join("%s=%d" % kv for kv in sorted(cont.items()))))
        if not ok(r["http"]) or (not itens and r["fonte"] != "congresso_mpv"):
            print("ERRO: fonte indisponivel ou 0 itens extraidos — usar WebSearch (fallback)")
        for i in itens:
            s = i["situacao"]
            if r["fonte"] == "congresso_leis" and s != "JA_PUBLICADA":
                print("[%s] %s nº %s de %s (DOU %s) — %s%s | %s | %s | chave=%s" % (
                    s, i["tipo"], i["numero"], i["data_ato"], i["dou"], i["ementa"],
                    " | veto: " + i["veto"] if i["veto"] else "", i["materia"], i["url"], i["chave"]))
            elif r["fonte"] == "congresso_mpv":
                print("[%s] MPV %s/%s — DOU %s (detalhe oficial, http %s) — %s | %s%s" % (
                    s, i["numero"], i["ano"], i["dou"] or "?", i["http_detalhe"],
                    i["ementa"][:160], i["url"], " | chave=" + i["chave"] if i["dou"] else ""))
            elif s in ("NOVA", "HERDADA", "SEM_DATA"):
                extra = (" — " + i["resumo"][:150]) if i.get("resumo") else ""
                tag = i.get("tipo", "noticia")[:3].upper()
                print("[%s|%s] %s | %s%s | %s" % (s, tag, hm(i), i["titulo"], extra, i["url"]))

    def ser(o):
        return o.isoformat() if isinstance(o, (datetime, date)) else str(o)
    with open(a.saida, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1, default=ser)
    print("\n(JSON completo: %s)" % a.saida)


if __name__ == "__main__":
    main()
