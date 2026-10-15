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
# Usado por coleta_web.py (marca [REPETIDA?~chave]) e por
# Update-Historico.py --validar (avisos POSSIVEL_REPETIDA e
# POSSIVEL_DUPLICATA_NA_EDICAO). Concursos, versiculo e Munger ficam de
# fora: repetem-se por desenho.
# =====================================================================

import re
import unicodedata

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


def tokens(texto):
    s = unicodedata.normalize("NFKD", str(texto or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    out = set()
    for p in re.split(r"[^a-z0-9]+", s):
        if not p or p in PARADAS or (len(p) < 3 and not p.isdigit()):
            continue
        if len(p) > 4 and p.endswith("s") and not p.isdigit():
            p = p[:-1]
        out.add(p)
    return out


def tokens_item(chave, titulo=""):
    partes = (chave or "").split("|")
    slug = partes[2] if len(partes) > 2 else ""
    return tokens(slug.replace("-", " ") + " " + (titulo or ""))


def parecidas(a, b, minimo=4, proporcao=0.7):
    comum = len(a & b)
    return comum >= minimo and comum / max(1, min(len(a), len(b))) >= proporcao


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
    """Chave do indice mais parecida com `tok` (empate: a mais recente,
    pois o indice vem em ordem cronologica), ou None."""
    melhor, nota = None, 0.0
    for ch, t in idx:
        if ch == excluir or not parecidas(tok, t):
            continue
        n = len(tok & t) / max(1, min(len(tok), len(t)))
        if n >= nota:
            melhor, nota = ch, n
    return melhor
