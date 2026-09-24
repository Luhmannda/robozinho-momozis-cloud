#!/usr/bin/env python3
# =====================================================================
# resolver_jota.py — resolve os links-wrapper do JOTA (t.rdsv2.net) por
# curl e confere se o titulo da pagina final bate com o anunciado.
# Substitui ate 16 WebSearch por execucao QUANDO t.rdsv2.net e
# www.jota.info estiverem no allowlist do ambiente; senao imprime
# BLOQUEADO e sai com 3 (o coletor cai no fallback por WebSearch).
#
# USO:   python3 work/resolver_jota.py /tmp/jota_links.tsv
#        (uma linha por item: titulo<TAB>url-do-wrapper)
# SAIDA: OK<TAB>titulo<TAB>url-final | SEM_MATCH<TAB>titulo<TAB>titulo-da-pagina
#        | ERRO<TAB>titulo<TAB>motivo
# =====================================================================

import html
import re
import subprocess
import sys
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

UA = "Mozilla/5.0 (X11; Linux x86_64) Robozinho/1.0"


def curl(url, timeout=20):
    try:
        r = subprocess.run(["curl", "-s", "-L", "-m", str(timeout), "-A", UA,
                            "-w", "\n%{http_code} %{url_effective}", url],
                           capture_output=True, timeout=timeout + 5)
        out = r.stdout.decode("utf-8", "replace")
    except Exception:
        return 0, "", ""
    corpo, _, fim = out.rpartition("\n")
    codigo, _, final = fim.partition(" ")
    return (int(codigo) if codigo.isdigit() else 0), final, corpo


def palavras(s):
    s = unicodedata.normalize("NFKD", html.unescape(s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return {w for w in re.findall(r"[a-z0-9]+", s) if len(w) > 2}


def bate(anunciado, pagina):
    a, p = palavras(anunciado), palavras(pagina)
    return bool(a) and len(a & p) / len(a) >= 0.6


def sem_rastreio(url):
    u = urlsplit(url)
    q = [(k, v) for k, v in parse_qsl(u.query) if not k.lower().startswith(("utm_", "rd_"))]
    return urlunsplit((u.scheme, u.netloc, u.path, urlencode(q), ""))


def resolve(linha):
    titulo, _, wrapper = linha.partition("\t")
    codigo, final, corpo = curl(wrapper.strip())
    if codigo != 200 or "jota.info" not in final:
        return "ERRO\t%s\thttp=%s final=%s" % (titulo, codigo, final)
    m = re.search(r'property="og:title"\s+content="([^"]+)"', corpo) or \
        re.search(r"<title>(.*?)</title>", corpo, re.S)
    tit_pag = html.unescape(m.group(1)).strip() if m else ""
    if bate(titulo, tit_pag):
        return "OK\t%s\t%s" % (titulo, sem_rastreio(final))
    return "SEM_MATCH\t%s\t%s" % (titulo, tit_pag)


def main():
    if len(sys.argv) != 2:
        sys.exit("uso: resolver_jota.py arquivo.tsv")
    for host in ("https://t.rdsv2.net/", "https://www.jota.info/"):
        codigo = subprocess.run(["curl", "-s", "-o", "/dev/null", "-m", "8", "-w", "%{http_code}", host],
                                capture_output=True, text=True).stdout.strip()
        if codigo in ("000", "403", ""):
            print("BLOQUEADO\t%s http=%s — usar o fallback por WebSearch" % (host, codigo or "000"))
            sys.exit(3)
    linhas = [l.rstrip("\n") for l in open(sys.argv[1], encoding="utf-8") if "\t" in l]
    with ThreadPoolExecutor(max_workers=6) as ex:
        for r in ex.map(resolve, linhas):
            print(r)


if __name__ == "__main__":
    main()
