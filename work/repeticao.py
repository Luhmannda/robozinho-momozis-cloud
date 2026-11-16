#!/usr/bin/env python3
# =====================================================================
# repeticao.py — deteccao de materia repetida ENTRE FONTES, por
# semelhanca de titulo, contra o que ja saiu nas ultimas edicoes.
#
# A chave (fonte|tipo|slug|ano|data) so pega a repeticao exata; a mesma
# historia vinda de outra fonte (ex.: ConJur republicando em 14/10 a
# noticia do STF sobre ICMS publicada em 07/10) tem chave diferente.
# Antes isso dependia de o orquestrador ler ~200 chaves a olho todo dia.
#
# Usado por coleta_web.py (marca [REPETIDA?~chave]), resolver_jota.py
# (JA_PUBLICADA) e Update-Historico.py --validar (avisos POSSIVEL_REPETIDA
# e POSSIVEL_DUPLICATA_NA_EDICAO). Concursos, versiculo e Munger ficam de
# fora: repetem-se por desenho.
#
# Ordem da comparacao (16/11/2026: 4 decretos distintos do mesmo dia
# viraram "duplicata" e o conteudo da RG 397 atrasada virou "repetida"):
#   1. IDENTIDADE NUMERICA. Ato normativo (planalto|decreto|13166|...) e
#      edicao de informativo (stf|informativo|1236|..., ...-repercussao-
#      geral-397) tem identidade (tipo, numero) tirada da CHAVE ("forte").
#      Dois itens com identidade forte: mesma identidade = mesma materia;
#      identidade diferente = materias diferentes, sem olhar o titulo (so o
#      mesmo numero com especie de ato diferente cai no titulo). O tipo da
#      chave e canonico (tipo_canonico: lc/lcp -> lei-complementar, ec/emc ->
#      emenda-constitucional, dl -> decreto-lei, mp -> mpv...).
#      Identidade tirada so do comeco do TITULO ("Lei 15.530 altera...",
#      "fraca"): numero diferente do mesmo tipo nunca e parecido; numero
#      igual cai na comparacao de titulo (noticia SOBRE a lei nao e a lei).
#   2. Excecao explicita: "X-conteudo" ~ "X" nao e repeticao (e o conteudo
#      da edicao ATRASADA cujo anuncio saiu antes; informativos.py).
#   3. So entao a semelhanca de titulo, com datas retiradas e o milhar
#      juntado ("13.166" -> 13166). Sem o passo 1, essa limpeza quebraria o
#      casamento legitimo do mesmo ato vindo do PUSH e de ref.
#
# API (compativel com a anterior; o que e novo tem padrao):
#   tokens(texto) -> Tokens       tokens_item(chave, titulo="") -> Tokens
#   parecidas(a, b, minimo=4, proporcao=0.7) -> bool
#   indice(execucoes, ignorar_exec_id=None) -> [(chave, Tokens)]
#   procurar(tok, idx, excluir=None) -> chave | None
#   ignorar(it)
# Novas: mesma_identidade(a, b) -> True|False|None, identidade(chave,
#   titulo="") -> (tipo, numero, forte) | None, tipo_canonico(tipo) -> str,
#   carregar_historico(caminho=None),
#   urls_publicadas(execucoes, ignorar_exec_id=None) -> {url_normalizada: chave},
#   normalizar_url(url).
# Tokens e um set comum (len, &, in funcionam como antes) com os atributos
# ident, forte, base e conteudo; um set puro continua aceito (sem identidade).
# =====================================================================

import json
import os
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit

AQUI = os.path.dirname(os.path.abspath(__file__))

IGNORAR_PREFIXOS = ("concurso|", "versiculo|", "munger|")
# Pela categoria, que nao depende do formato da chave (em 15/10 uma execucao
# gravou concursos como "pge-rj|concurso|...", que o prefixo nao pegava).
IGNORAR_CATEGORIAS = {"Concursos - Carreira", "Concursos - Apoio", "Versículo", "Munger"}


def ignorar(it):
    return ((it.get("chave") or "").lower().startswith(IGNORAR_PREFIXOS)
            or it.get("categoria") in IGNORAR_CATEGORIAS)


PARADAS = set("""
a o as os um uma uns umas de da do das dos em no na nos nas ao aos e ou para por pelo
pela pelos pelas com sem sobre contra entre que se sua seu suas seus apos ate como mais
menos nao ja diz dizem pode podem deve devem ser ter tem sao foi era vai via apos tambem
""".split())


class Tokens(set):
    """Conjunto de tokens com a identidade do item.
    ident    = (tipo, numero) de ato normativo ou edicao de informativo, ou None;
    forte    = a identidade veio da chave (o item E o ato/a edicao);
    base     = "fonte|tipo|slug" sem o sufixo "-conteudo" ("" sem chave);
    conteudo = a chave termina em "-conteudo" (conteudo de edicao atrasada)."""
    ident = None
    forte = False
    base = ""
    conteudo = False


def _sem_acento(texto):
    s = unicodedata.normalize("NFKD", str(texto or "").lower())
    return "".join(c for c in s if not unicodedata.combining(c))


# ------------------------------------------------------------ identidade
TIPOS_ATO = [("lei complementar", "lei-complementar"), ("decreto-lei", "decreto-lei"),
             ("decreto lei", "decreto-lei"), ("decreto legislativo", "decreto-legislativo"),
             ("emenda constitucional", "emenda-constitucional"), ("medida provisoria", "mpv"),
             ("lei", "lei"), ("decreto", "decreto"), ("mpv", "mpv"), ("mp", "mpv"),
             ("ec", "emenda-constitucional"), ("lcp", "lei-complementar"), ("lc", "lei-complementar")]
_ATO_TITULO = re.compile(r"^\W*(%s)\s*(?:n[o°.]*\s*)?(\d{1,3}(?:\.\d{3})+|\d+)\b"
                         % "|".join(re.escape(t) for t, _ in TIPOS_ATO))
# Tipo canonico do ato na CHAVE. O historico tem a mesma especie com varias
# grafias (planalto|lc|234, planalto|lcp|238, planalto|lei-complementar|237),
# e o coleta_web/montador gravam "lei-complementar": sem isso, a LC do PUSH
# ("lc") e a ref do Congresso ("lei-complementar") viravam "materias
# diferentes" e o --validar deixava de avisar a duplicata/repeticao.
TIPO_CANONICO = {
    "lc": "lei-complementar", "lcp": "lei-complementar", "lei-complementar": "lei-complementar",
    "ec": "emenda-constitucional", "emc": "emenda-constitucional", "emenda": "emenda-constitucional",
    "emenda-constitucional": "emenda-constitucional",
    "dl": "decreto-lei", "del": "decreto-lei", "decreto-lei": "decreto-lei",
    "dlg": "decreto-legislativo", "pdl": "decreto-legislativo", "decreto-legislativo": "decreto-legislativo",
    "lei-ordinaria": "lei", "lei": "lei", "decreto": "decreto", "dec": "decreto",
}
TIPOS_INFORMATIVO = {"stf-informativo", "stf-rg", "stj-informativo"}


def tipo_canonico(tipo):
    """Grafia unica do tipo de ato da chave ('lc'/'lcp' -> 'lei-complementar',
    'mp'/'medida-provisoria' -> 'mpv'...); tipo desconhecido volta como veio."""
    t = (tipo or "").strip().lower().replace("_", "-").replace(" ", "-")
    if t.startswith(("medida-prov", "mp")):
        return "mpv"
    return TIPO_CANONICO.get(t, t)


_INF_TITULO = re.compile(r"^\W*(?:informativo (stf|stj)|(repercussao geral em pauta))\s*"
                         r"(?:n[o°.]*\s*)?(\d+)\b")


def _ident_titulo(titulo):
    """Identidade fraca: so quando o titulo COMECA pela designacao do ato ou da edicao."""
    s = _sem_acento(titulo)
    m = _ATO_TITULO.match(s)
    if m:
        tipo = dict(TIPOS_ATO)[m.group(1)]
        return (tipo, str(int(m.group(2).replace(".", ""))))
    m = _INF_TITULO.match(s)
    if m:
        return ("stf-rg" if m.group(2) else "%s-informativo" % m.group(1), str(int(m.group(3))))
    return None


def _partes(chave):
    """(fonte, tipo, slug_sem_conteudo, conteudo) da chave, ou None."""
    p = (chave or "").lower().split("|")
    if len(p) < 3:
        return None
    slug = p[2]
    conteudo = slug.endswith("-conteudo")
    return p[0], p[1], (slug[:-len("-conteudo")] if conteudo else slug), conteudo


def _ident_chave(chave):
    """Identidade forte, da chave: ato do Planalto com numero ou edicao de informativo."""
    pt = _partes(chave)
    if not pt:
        return None
    fonte, tipo, slug, _ = pt
    if tipo == "informativo":
        # so stf|informativo|... e stj|informativo|... (o legado "informativos|stj|908"
        # de 03/11 era o aviso "sem edicao nova", nao a edicao 908)
        m = re.fullmatch(r"(repercussao-geral-)?(\d+)", slug)
        if m and fonte in ("stf", "stj"):
            return ("stf-rg" if m.group(1) else "%s-informativo" % fonte, str(int(m.group(2))))
        return None
    if fonte == "planalto" and slug.isdigit():
        return (tipo_canonico(tipo), str(int(slug)))
    return None


def identidade(chave, titulo=""):
    """(tipo, numero, forte) ou None. forte=True quando vem da chave."""
    ident = _ident_chave(chave)
    if ident:
        return ident + (True,)
    pt = _partes(chave)
    ident = _ident_titulo(titulo or (pt[2].replace("-", " ") if pt else ""))
    return ident + (False,) if ident else None


def mesma_identidade(a, b):
    """True = mesma materia pela identidade; False = materias diferentes (nao
    comparar o titulo); None = a identidade nao decide (comparar o titulo)."""
    base_a, base_b = getattr(a, "base", ""), getattr(b, "base", "")
    cont_a, cont_b = getattr(a, "conteudo", False), getattr(b, "conteudo", False)
    if base_a and base_a == base_b and cont_a != cont_b:
        return False                       # "X-conteudo" ~ "X": publicacao esperada
    ia, ib = getattr(a, "ident", None), getattr(b, "ident", None)
    if not ia or not ib:
        # item sem identidade (ex.: noticia "Infracoes de notarios prescreverao em
        # 5 anos, define nova lei" x Lei 15.509, 23/09): decide o titulo
        return None
    if getattr(a, "forte", False) and getattr(b, "forte", False):
        if ia == ib:
            return cont_a == cont_b
        if ia[1] == ib[1] and not ({ia[0], ib[0]} & TIPOS_INFORMATIVO):
            # mesmo numero, tipo de ato diferente: grafia que o TIPO_CANONICO
            # ainda nao conhece (ex.: "planalto|lcomp|239") ou coincidencia
            # entre especies; decide o titulo, como antes da identidade
            return None
        return False
    if ia[0] == ib[0] and ia[1] != ib[1]:
        return False                       # mesmo tipo, numero diferente: nunca pelo titulo
    return None


# ------------------------------------------------------------ tokens
_DATA = re.compile(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b|\b\d{4}-\d{2}-\d{2}\b")
_ANO = re.compile(r"(?<![\d.,])(?:19|20)\d{2}(?!\d)(?!\.\d{3})")
_MILHAR = re.compile(r"(?<=\d)\.(?=\d{3}(?!\d))")


def _limpar(s):
    """Datas (12/11/2026, 12/11, 2026-11-12) e anos soltos saem; o milhar e juntado."""
    s = _DATA.sub(" ", s)
    s = _ANO.sub(" ", s)
    return _MILHAR.sub("", s)


def _tokens_puros(texto):
    s = _limpar(_sem_acento(texto))
    out = set()
    for p in re.split(r"[^a-z0-9]+", s):
        if not p or p in PARADAS or (len(p) < 3 and not p.isdigit()):
            continue
        if len(p) > 4 and p.endswith("s") and not p.isdigit():
            p = p[:-1]
        out.add(p)
    return out


def tokens(texto):
    t = Tokens(_tokens_puros(texto))
    t.ident = _ident_titulo(texto)
    return t


def tokens_item(chave, titulo=""):
    pt = _partes(chave)
    slug = pt[2] if pt else ""
    t = Tokens(_tokens_puros(slug.replace("-", " ") + " " + (titulo or "")))
    ident = identidade(chave, titulo)
    if ident:
        t.ident, t.forte = ident[:2], ident[2]
    if pt:
        t.base = "%s|%s|%s" % pt[:3]
        t.conteudo = pt[3]
    return t


def parecidas(a, b, minimo=4, proporcao=0.7):
    r = mesma_identidade(a, b)
    if r is not None:
        return r
    comum = len(a & b)
    return comum >= minimo and comum / max(1, min(len(a), len(b))) >= proporcao


# ------------------------------------------------------------ historico
def indice(execucoes, ignorar_exec_id=None):
    """[(chave, tokens)] dos itens de noticia ja publicados."""
    idx = []
    for e in execucoes:
        if e.get("execution_id") == ignorar_exec_id:
            continue
        for it in e.get("items") or []:
            ch = (it.get("chave") or "").lower()
            if not ch or ignorar(it):
                continue
            idx.append((ch, tokens_item(ch, it.get("titulo"))))
    return idx


def procurar(tok, idx, excluir=None):
    """Chave do indice mais parecida com `tok` (identidade igual vence a
    semelhanca de titulo; empate: a mais recente, pois o indice vem em ordem
    cronologica), ou None."""
    melhor, nota = None, 0.0
    for ch, t in idx:
        if ch == excluir:
            continue
        r = mesma_identidade(tok, t)
        if r is False:
            continue
        if r is True:
            n = 2.0
        elif parecidas(tok, t):
            n = len(tok & t) / max(1, min(len(tok), len(t)))
        else:
            continue
        if n >= nota:
            melhor, nota = ch, n
    return melhor


def carregar_historico(caminho=None):
    """Execucoes do historico principal (lista vazia se nao abrir)."""
    caminho = caminho or os.path.join(AQUI, "resumo-legislativo-historico.json")
    try:
        with open(caminho, encoding="utf-8") as f:
            return json.load(f).get("executions") or []
    except Exception:
        return []


def normalizar_url(url):
    """https://www.x/y/?utm_a=1#z -> x/y (para comparar URLs publicadas)."""
    u = urlsplit((url or "").strip())
    if not u.netloc:
        return (url or "").strip().rstrip("/").lower()
    host = u.netloc.lower()
    host = host[4:] if host.startswith("www.") else host
    q = [(k, v) for k, v in parse_qsl(u.query) if not k.lower().startswith(("utm_", "rd_"))]
    return host + u.path.rstrip("/") + ("?" + urlencode(q) if q else "")


def urls_publicadas(execucoes, ignorar_exec_id=None):
    """{url normalizada: chave} dos itens ja publicados (a ultima vence)."""
    out = {}
    for e in execucoes:
        if ignorar_exec_id and e.get("execution_id") == ignorar_exec_id:
            continue
        for it in e.get("items") or []:
            if it.get("url") and not ignorar(it):
                out[normalizar_url(it["url"])] = (it.get("chave") or "").lower()
    return out
