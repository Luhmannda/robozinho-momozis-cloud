#!/usr/bin/env python3
# =====================================================================
# paginas_oficiais.py — leitura deterministica da PAGINA OFICIAL de cada
# concurso que tem `url_oficial` no registro (link profundo: pagina do
# concurso ou listagem de editais do orgao), sem tokens. Chamado pelo
# inicio.py para os concursos em foco.
#
# Por que (B10): o coletor recebia "pagina oficial <dominio> acessivel: leia
# por curl" e lia a RAIZ do dominio; nada se confirmava e a leitura se
# repetia (pendencias com 26 a 55 execucoes). Cebraspe devolve 200 com 116
# caracteres (pagina so JavaScript).
#
# Para cada url_oficial: baixa a pagina, tira o HTML, guarda so os TRECHOS com
# palavras-chave de concurso (concurso, edital, inscri, resultado, prova,
# homolog, convoca, retifica, nomea) e compara o hash deles com o da ultima
# leitura registrada (work/concursos-estado.json, secao "paginas", gravada
# pelo helper quando a execucao e registrada). Hash so dos trechos: data do
# dia, carrossel e menu nao viram "MUDOU".
#   MUDOU  — trechos novos impressos (ate 5);
#   IGUAL  — desde DD/MM (ultima mudanca vista);
#   NOVA   — 1a leitura (sem estado): trechos impressos;
#   SEM_TEXTO — pagina so JavaScript (texto util < 300 caracteres): sai da lista "acessivel";
#   HTTP nnn — nao abriu.
#
# USO avulso: python3 work/paginas_oficiais.py   (todos os concursos com url_oficial)
# SAIDA: linhas "PAGINA OFICIAL ..." e $ROBOZINHO_TMP/paginas_oficiais.json.
# =====================================================================

import hashlib
import html
import json
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import date

AQUI = os.path.dirname(os.path.abspath(__file__))
UA = "Mozilla/5.0 (X11; Linux x86_64) Robozinho/1.0"
CHAVE = re.compile(r"concurso|edital|inscri[çc]|resultado|prova|homolog|convoca|retifica|nomea", re.I)
MIN_TEXTO = 300
MAX_TRECHOS = 60
MAX_IMPRESSOS = 5


def tmp(nome):
    return os.path.join(os.environ.get("ROBOZINHO_TMP", "/tmp"), nome)


def baixar(url, timeout=20):
    try:
        r = subprocess.run(["curl", "-sL", "-m", str(timeout), "-A", UA, "-w", "\n%{http_code}", url],
                           capture_output=True, timeout=timeout + 5)
        corpo, _, codigo = r.stdout.decode("utf-8", "replace").rpartition("\n")
        return int(codigo or 0), corpo
    except Exception:  # noqa: BLE001
        return 0, ""


def texto_util(pagina):
    t = re.sub(r"(?is)<(script|style|noscript|svg|nav|footer|header)\b.*?</\1>", " ", pagina or "")
    t = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</tr>|</h\d>|</a>|</td>", "\n", t)
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    return [l for l in (re.sub(r"\s+", " ", x).strip() for x in t.split("\n")) if l]


def trechos(linhas):
    """Linhas com palavra-chave, sem repetir, ate MAX_TRECHOS (ordem da pagina)."""
    out = []
    for l in linhas:
        if CHAVE.search(l) and 12 <= len(l) <= 400 and l not in out:
            out.append(l[:300])
        if len(out) >= MAX_TRECHOS:
            break
    return out


def sha(s):
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:12]


def analisar(ident, url, http, pagina, anterior, hoje):
    """Resultado de uma pagina. `anterior` = estado["paginas"][ident] (ou None)."""
    r = {"id": ident, "url": url, "http": http}
    if http != 200:
        r["situacao"] = "HTTP"
        return r
    linhas = texto_util(pagina)
    if sum(len(l) for l in linhas) < MIN_TEXTO:
        r["situacao"] = "SEM_TEXTO"
        return r
    tr = trechos(linhas)
    r["hash"] = sha("\n".join(tr))
    r["trechos_hash"] = [sha(t) for t in tr]
    if not anterior or anterior.get("url") != url:
        r.update(situacao="NOVA", novos=tr[:MAX_IMPRESSOS], desde=hoje)
    elif anterior.get("hash") == r["hash"]:
        r.update(situacao="IGUAL", desde=anterior.get("desde") or hoje)
    else:
        vistos = set(anterior.get("trechos_hash") or [])
        r.update(situacao="MUDOU", novos=[t for t in tr if sha(t) not in vistos][:MAX_IMPRESSOS], desde=hoje)
    return r


def verificar(concursos, estado, hoje, ids=None):
    """Lista de resultados para os concursos com url_oficial (so os `ids`, se dado)."""
    alvos = [(c["id"], c["url_oficial"]) for c in concursos
             if c.get("url_oficial") and (ids is None or c["id"] in ids)]
    pags = (estado or {}).get("paginas") or {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        baixadas = list(ex.map(lambda a: baixar(a[1]), alvos))
    return [analisar(i, u, http, corpo, pags.get(i), hoje) for (i, u), (http, corpo) in zip(alvos, baixadas)]


def linhas_saida(res):
    out = []
    for r in res:
        sit = r["situacao"]
        if sit == "IGUAL":
            out.append("PAGINA OFICIAL %s IGUAL desde %s | %s" % (r["id"], r["desde"][8:10] + "/" + r["desde"][5:7], r["url"]))
        elif sit in ("MUDOU", "NOVA"):
            out.append("PAGINA OFICIAL %s %s | %s%s" % (r["id"], "MUDOU" if sit == "MUDOU" else "LIDA (1ª vez)", r["url"],
                                                         "".join("\n  · " + t for t in r.get("novos") or [])))
        elif sit == "SEM_TEXTO":
            out.append("PAGINA OFICIAL %s SEM TEXTO (página só JavaScript): fora do 'acessível' | %s" % (r["id"], r["url"]))
        else:
            out.append("PAGINA OFICIAL %s HTTP %s | %s" % (r["id"], r["http"], r["url"]))
    return out


def atualizar_estado(estado, res, hoje):
    """Usado pelo helper: grava hash/trechos/desde das paginas lidas (nao mexe nas que nao abriram)."""
    pags = estado.setdefault("paginas", {})
    n = 0
    for r in res or []:
        if r.get("situacao") in ("IGUAL", "MUDOU", "NOVA"):
            ant = pags.get(r["id"]) or {}
            pags[r["id"]] = {"url": r["url"], "hash": r["hash"], "trechos_hash": r["trechos_hash"],
                             "desde": r.get("desde") or ant.get("desde") or hoje, "lido_em": hoje}
            n += r["situacao"] != "IGUAL"
    return n


def main():
    import bancas
    hoje = date.today().isoformat()
    try:
        hoje = json.load(open(tmp("janela.json"), encoding="utf-8"))["data"]
    except Exception:  # noqa: BLE001
        pass
    led = json.load(open(os.path.join(AQUI, "robozinho-aprendizado.json"), encoding="utf-8"))
    res = verificar(led.get("concursos") or [], bancas.carregar_estado(), hoje)
    with open(tmp("paginas_oficiais.json"), "w", encoding="utf-8") as f:
        json.dump({"data": hoje, "paginas": res}, f, ensure_ascii=False, indent=1)
    print("\n".join(linhas_saida(res)) or "PAGINA OFICIAL: nenhum concurso com url_oficial no registro")


if __name__ == "__main__":
    main()
