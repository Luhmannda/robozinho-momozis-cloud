#!/usr/bin/env python3
# =====================================================================
# resolver_jota.py — resolve os links-wrapper do JOTA (t.rdsv2.net) por
# curl e confere se o titulo da pagina final bate com o anunciado.
# Substitui ate 16 WebSearch por execucao QUANDO t.rdsv2.net e
# www.jota.info estiverem no allowlist do ambiente; senao imprime
# BLOQUEADO e sai com 3 (o coletor cai no fallback por WebSearch).
#
# SEGURANCA (16/11/2026): o rodape do e-mail traz "parar de receber esta
# newsletter" no mesmo wrapper t.rdsv2.net das materias. Nada aqui segue
# redirecionamento as cegas (antes: curl -L, um GET no destino que fosse):
#   - cada salto e resolvido SEM seguir (-o /dev/null -w redirect_url), no
#     maximo 5, e so em host de rastreio conhecido (t.rdsv2.net);
#   - antes de QUALQUER pedido, a URL e conferida: host www.jota.info (ou
#     jota.info) ou rastreio conhecido, e caminho/consulta sem sinal de
#     descadastro ou preferencias (unsubscribe, descadastr, optout, opt-out,
#     preferenc, manage, remover, cancelar). "preferenc", "manage", "remover"
#     e "cancelar" no slug final de uma materia do jota.info (>= 6 palavras,
#     ex.: .../nunes-marques-manda-remover-em-24h-...) nao contam; os demais
#     valem em qualquer parte, inclusive no slug;
#   - so o GET final, no jota.info, baixa a pagina (para conferir o titulo).
#   Destino proibido -> RECUSADO, sem pedido nenhum a ele.
#   Links que o work/jota_extrair.py reconheceu como descadastro nem entram
#   no indice $ROBOZINHO_TMP/jota_urls.tsv.
#
# HISTORICO (16/11: 2 materias ja publicadas em 12/11 sairam OK e so o
# montador as pegou): cada titulo e procurado no historico com
# work/repeticao.py (ignorar_execucao do janela.json vale para re-execucao);
# a URL final tambem e comparada com as URLs ja publicadas.
#
# USO:   python3 work/resolver_jota.py [$ROBOZINHO_TMP/jota_links.tsv]
#        [--urls $ROBOZINHO_TMP/jota_urls.tsv] [--janela $ROBOZINHO_TMP/janela.json]
#        [--historico work/resumo-legislativo-historico.json] [--sem-historico]
# ENTRADA (uma linha por item; vazia ou iniciada por # e ignorada):
#        titulo<TAB>url              (url do wrapper ou url direta do jota.info)
#        titulo<TAB>L<n>             (indice do jota_urls.tsv gravado pelo jota_extrair.py;
#                                     aceita tambem [L<n>])
#        titulo                      (sem link: so a checagem de historico; idem
#                                     titulo<TAB>sem link ou qualquer coisa que nao seja URL/L<n>)
# SAIDA (uma linha por item, na ordem da entrada, campos separados por TAB):
#        OK<TAB>titulo<TAB>url-final (sem utm_/rd_)
#        SEM_MATCH<TAB>titulo<TAB>titulo-da-pagina
#        ERRO<TAB>titulo<TAB>motivo
#        RECUSADO<TAB>titulo<TAB>motivo          (destino proibido: nenhum pedido a ele)
#        JA_PUBLICADA<TAB>titulo<TAB>chave-parecida-do-historico
#        SEM_LINK<TAB>titulo<TAB>nao publicada antes   (linha sem URL)
#        BLOQUEADO<TAB><host> http=<codigo> — usar o fallback por WebSearch
#              (primeira linha; depois so as JA_PUBLICADA/SEM_LINK; sai com 3)
#        AVISO<TAB>-<TAB>historico indisponivel: sem checagem JA_PUBLICADA
# =====================================================================

import argparse
import html
import json
import os
import re
import subprocess
import sys
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qsl, unquote, urlencode, urljoin, urlsplit, urlunsplit

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import repeticao  # noqa: E402

TMP = os.environ.get("ROBOZINHO_TMP", "/tmp")
UA = "Mozilla/5.0 (X11; Linux x86_64) Robozinho/1.0"
HOSTS_JOTA = {"www.jota.info", "jota.info"}
RASTREIO = {"t.rdsv2.net"}        # wrappers resolvidos salto a salto (sem baixar nada)
MAX_SALTOS = 5
REDIRECIONA = {301, 302, 303, 307, 308}
PROIBIDO = re.compile(r"unsub|descadastr|opt-?out|opt_out")              # em qualquer parte
PROIBIDO_FORA_DO_SLUG = re.compile(r"preferenc|manage|remover|cancelar")   # fora do slug de materia


def curl(url, corpo=False, timeout=20):
    """UM pedido, sem seguir redirecionamento. Devolve (codigo, redirect_url, html)."""
    cmd = ["curl", "-s", "-m", str(timeout), "-A", UA,
           "-w", "\n%{http_code} %{redirect_url}"]
    if not corpo:
        cmd += ["-o", "/dev/null"]
    try:
        r = subprocess.run(cmd + [url], capture_output=True, timeout=timeout + 5)
        out = r.stdout.decode("utf-8", "replace")
    except Exception:
        return 0, "", ""
    pagina, _, fim = out.rpartition("\n")
    codigo, _, prox = fim.partition(" ")
    return (int(codigo) if codigo.isdigit() else 0), prox.strip(), pagina


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


def motivo_proibido(url):
    """'' se a URL pode receber um pedido; senao o motivo da recusa."""
    u = urlsplit(url)
    host = (u.hostname or "").lower()
    if u.scheme not in ("http", "https"):
        return "esquema nao permitido: %s" % (u.scheme or "?")
    jota = host in HOSTS_JOTA
    caminho, consulta = unquote(u.path or "").lower(), unquote(u.query or "").lower()
    m = PROIBIDO.search(caminho + "?" + consulta)
    if m:
        return "caminho/consulta de descadastro ou preferencias (%s)" % m.group(0)
    segs = [s for s in caminho.split("/") if s]
    if jota and len(segs) >= 2 and segs[-1].count("-") >= 5:
        resto = "/".join(segs[:-1]) + "?" + consulta     # slug de materia: palavra do titulo
    else:
        resto = caminho + "?" + consulta
    m = PROIBIDO_FORA_DO_SLUG.search(resto)
    if m:
        return "caminho/consulta de descadastro ou preferencias (%s)" % m.group(0)
    if not jota and host not in RASTREIO:
        return "destino fora do jota.info: %s" % (host or "?")
    return ""


def seguir(url):
    """Resolve salto a salto. ("PAGINA", url_final, html) | ("RECUSADO"|"ERRO", motivo, "")."""
    atual = url.strip()
    for salto in range(MAX_SALTOS + 1):
        motivo = motivo_proibido(atual)
        if motivo:
            return "RECUSADO", motivo, ""
        jota = (urlsplit(atual).hostname or "").lower() in HOSTS_JOTA
        codigo, prox, pagina = curl(atual, corpo=jota)
        if codigo in REDIRECIONA and prox:
            if salto == MAX_SALTOS:
                break
            atual = urljoin(atual, prox)
            continue
        if not jota:
            return "ERRO", "http=%s sem redirecionamento em %s" % (codigo, urlsplit(atual).hostname), ""
        if codigo != 200:
            return "ERRO", "http=%s final=%s" % (codigo, sem_rastreio(atual)), ""
        return "PAGINA", sem_rastreio(atual), pagina
    return "RECUSADO", "mais de %d redirecionamentos" % MAX_SALTOS, ""


def titulo_pagina(corpo):
    m = re.search(r'property="og:title"\s+content="([^"]+)"', corpo) or \
        re.search(r"<title>(.*?)</title>", corpo, re.S)
    return html.unescape(m.group(1)).strip() if m else ""


def limpo(s):
    return re.sub(r"[\t\r\n]+", " ", s or "").strip()


MARCADOR = re.compile(r"^\[?L(\d+)\]?$", re.I)


def ler_linhas(caminho):
    """[(titulo, alvo)] — alvo = url, 'L<n>' ou ''."""
    out = []
    for bruta in open(caminho, encoding="utf-8"):
        linha = bruta.rstrip("\r\n")
        if not linha.strip() or linha.lstrip().startswith("#"):
            continue
        titulo, _, alvo = linha.partition("\t")
        titulo, alvo = titulo.strip(), alvo.strip()
        if not alvo:                          # "titulo [L12]" sem TAB
            m = re.search(r"\s*\[L(\d+)\]\s*$", titulo, re.I)
            if m:
                titulo, alvo = titulo[:m.start()].strip(), "L" + m.group(1)
        if alvo and not MARCADOR.match(alvo) and not re.match(r"https?://", alvo, re.I):
            alvo = ""                         # "sem link", "-" etc.: so a checagem de historico
        out.append((titulo, alvo))
    return out


def ler_indice(caminho):
    """{n: url} do jota_urls.tsv (n<TAB>url[<TAB>...])."""
    idx = {}
    try:
        for linha in open(caminho, encoding="utf-8"):
            p = linha.rstrip("\r\n").split("\t")
            if len(p) >= 2 and p[0].strip().isdigit():
                idx[int(p[0])] = p[1].strip()
    except OSError:
        pass
    return idx


class Contexto:
    def __init__(self, historico=None, urls=None):
        self.idx_hist = historico[0] if historico else None      # repeticao.indice
        self.urls_pub = historico[1] if historico else {}         # {url normalizada: chave}
        self.indice = urls or {}

    def repetida(self, titulo):
        if self.idx_hist is None:
            return None
        return repeticao.procurar(repeticao.tokens(titulo), self.idx_hist)


def resolve(item, ctx):
    titulo, alvo = item
    t = limpo(titulo)
    ja = ctx.repetida(titulo)
    if ja:
        return "JA_PUBLICADA\t%s\t%s" % (t, ja)
    if not alvo:
        return "SEM_LINK\t%s\tnao publicada antes" % t
    m = MARCADOR.match(alvo)
    if m:
        url = ctx.indice.get(int(m.group(1)))
        if not url:
            return "ERRO\t%s\tindice L%s inexistente no jota_urls.tsv" % (t, m.group(1))
    else:
        url = alvo
    estado, detalhe, corpo = seguir(url)
    if estado != "PAGINA":
        return "%s\t%s\t%s" % (estado, t, limpo(detalhe))
    tit_pag = titulo_pagina(corpo)
    if not bate(titulo, tit_pag):
        return "SEM_MATCH\t%s\t%s" % (t, limpo(tit_pag))
    chave = ctx.urls_pub.get(repeticao.normalizar_url(detalhe))
    if chave:
        return "JA_PUBLICADA\t%s\t%s" % (t, chave)
    return "OK\t%s\t%s" % (t, detalhe)


def sondar():
    """(host, codigo) do primeiro host bloqueado, ou None."""
    for host in ("https://t.rdsv2.net/", "https://www.jota.info/"):
        codigo = subprocess.run(["curl", "-s", "-o", "/dev/null", "-m", "8", "-w", "%{http_code}", host],
                                capture_output=True, text=True).stdout.strip()
        if codigo in ("000", "403", ""):
            return host, codigo or "000"
    return None


def carregar_contexto(a):
    hist = None
    avisos = []
    if not a.sem_historico:
        ignorar = ""
        try:
            ignorar = json.load(open(a.janela, encoding="utf-8")).get("ignorar_execucao") or ""
        except Exception:
            pass
        execs = repeticao.carregar_historico(a.historico)
        if execs:
            hist = (repeticao.indice(execs, ignorar_exec_id=ignorar or None),
                    repeticao.urls_publicadas(execs, ignorar_exec_id=ignorar or None))
        else:
            avisos.append("AVISO\t-\thistorico indisponivel: sem checagem JA_PUBLICADA")
    return Contexto(hist, ler_indice(a.urls)), avisos


def main(argv=None):
    ap = argparse.ArgumentParser(description="Resolve os links do JOTA com seguranca e marca os ja publicados.")
    ap.add_argument("tsv", nargs="?", default=os.path.join(TMP, "jota_links.tsv"))
    ap.add_argument("--urls", default=os.path.join(TMP, "jota_urls.tsv"),
                    help="indice n<TAB>url do jota_extrair.py (para linhas titulo<TAB>L<n>)")
    ap.add_argument("--janela", default=os.path.join(TMP, "janela.json"))
    ap.add_argument("--historico", default=os.path.join(AQUI, "resumo-legislativo-historico.json"))
    ap.add_argument("--sem-historico", action="store_true", help="nao procura JA_PUBLICADA")
    a = ap.parse_args(argv)
    try:
        itens = ler_linhas(a.tsv)
    except OSError as e:
        print("uso: resolver_jota.py arquivo.tsv (%s)" % e, file=sys.stderr)
        return 2
    ctx, avisos = carregar_contexto(a)
    for av in avisos:
        print(av)
    precisa_rede = [it for it in itens if it[1] and not ctx.repetida(it[0])]
    bloqueio = sondar() if precisa_rede else None
    if bloqueio:
        print("BLOQUEADO\t%s http=%s — usar o fallback por WebSearch" % bloqueio)
        for it in itens:
            if it not in precisa_rede:
                print(resolve(it, ctx))
        return 3
    with ThreadPoolExecutor(max_workers=6) as ex:
        for r in ex.map(lambda it: resolve(it, ctx), itens):
            print(r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
