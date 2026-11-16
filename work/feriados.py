#!/usr/bin/env python3
# =====================================================================
# feriados.py — calendario da rotina (sem rede, sem tokens).
#
# Por que: ate 11/2026 a rotina nao conhecia feriado nenhum. Saiu edicao
# em 07/09, 12/10 e 02/11 e, no dia seguinte, o silencio normal do feriado
# (Planalto, Camara, STF/STJ) contou contra as fontes; o "gap" e o rodizio
# de concursos contavam o feriado como dia util.
#
# A edicao SAI em feriado (decisao do dono, 16/11/2026): o calendario so
# informa o julgamento (janela.json: feriado_hoje, feriados_na_janela) e
# corrige a contagem de dias uteis do TRABALHO DAS FONTES (rodizio,
# dormencia). Edicao faltante e gap contam dias de EDICAO (seg-sex, com
# feriado: dia_de_edicao / dias_de_edicao_entre / uteis_sem_registro).
#
# Tipos:
#   nacional          — feriado nacional por lei (fixos + Sexta-feira Santa).
#                       E o unico tipo que deixa de contar como dia util
#                       (mas segue dia de edicao).
#   ponto_facultativo — Carnaval (seg/ter) e Corpus Christi (federal).
#   justica_federal   — Lei 5.010/1966, art. 62 (Justica Federal e tribunais
#                       superiores): 20/12 a 06/01; quarta-feira santa a
#                       domingo de Pascoa; segunda e terca de Carnaval;
#                       11/08; 01 e 02/11; 08/12.
# Um mesmo dia pode ter mais de um tipo (ex.: 02/11 nacional + JF): vale o
# mais forte (nacional > justica_federal > ponto_facultativo), com os nomes
# juntos. Feriados estaduais/municipais ficam de fora (manutencao alta).
#
# USO avulso:  python3 work/feriados.py 2026            (lista o ano)
#              python3 work/feriados.py 2026-11-13 2026-11-20  (intervalo)
# =====================================================================

import sys
from datetime import date, timedelta

FIXOS = {(1, 1): "Confraternização Universal", (4, 21): "Tiradentes", (5, 1): "Dia do Trabalho",
         (9, 7): "Independência", (10, 12): "Nossa Senhora Aparecida", (11, 2): "Finados",
         (11, 15): "Proclamação da República", (11, 20): "Dia Nacional de Zumbi e da Consciência Negra",
         (12, 25): "Natal"}
JF_FIXOS = {(8, 11): "Fundação dos Cursos Jurídicos", (11, 1): "Todos os Santos", (11, 2): "Finados",
            (12, 8): "Dia da Justiça"}
RECESSO_JF = "Recesso da Justiça Federal (20/12 a 06/01)"
ROTULO_TIPO = {"nacional": "nacional", "justica_federal": "Justiça Federal, Lei 5.010/66 art. 62",
               "ponto_facultativo": "ponto facultativo"}
FORCA = {"nacional": 3, "justica_federal": 2, "ponto_facultativo": 1}
DIAS_CURTOS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]


def pascoa(ano):
    """Domingo de Pascoa (algoritmo de Meeus/Jones/Butcher, calendario gregoriano)."""
    a, b, c = ano % 19, ano // 100, ano % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = (h + l - 7 * m + 114) % 31 + 1
    return date(ano, mes, dia)


def _por_ano(ano):
    """{date: [(tipo, nome), ...]} do ano."""
    out = {}

    def add(d, tipo, nome):
        out.setdefault(d, []).append((tipo, nome))
    for (m, d), nome in FIXOS.items():
        add(date(ano, m, d), "nacional", nome)
    p = pascoa(ano)
    add(p - timedelta(days=2), "nacional", "Sexta-feira Santa")
    for n, nome in ((48, "Carnaval (segunda-feira)"), (47, "Carnaval (terça-feira)")):
        add(p - timedelta(days=n), "ponto_facultativo", nome)
        add(p - timedelta(days=n), "justica_federal", nome)
    add(p + timedelta(days=60), "ponto_facultativo", "Corpus Christi")
    for n in range(4, -1, -1):          # quarta-feira santa (P-4) a domingo de Pascoa (P)
        add(p - timedelta(days=n), "justica_federal", "Semana Santa")
    for (m, d), nome in JF_FIXOS.items():
        add(date(ano, m, d), "justica_federal", nome)
    d = date(ano, 1, 1)                  # recesso da JF: 20/12 a 06/01 (os dois lados do ano)
    while d <= date(ano, 1, 6):
        add(d, "justica_federal", RECESSO_JF)
        d += timedelta(days=1)
    d = date(ano, 12, 20)
    while d <= date(ano, 12, 31):
        add(d, "justica_federal", RECESSO_JF)
        d += timedelta(days=1)
    return out


_CACHE = {}


def feriado(d):
    """None ou {"data": "AAAA-MM-DD", "tipo": <mais forte>, "nome": "<nomes juntos>",
    "tipos": [...], "nacional": bool}."""
    if d.year not in _CACHE:
        _CACHE[d.year] = _por_ano(d.year)
    lst = _CACHE[d.year].get(d)
    if not lst:
        return None
    tipos = sorted({t for t, _ in lst}, key=lambda t: -FORCA[t])
    nomes = []
    for t in tipos:                       # nome do tipo mais forte primeiro, sem repetir o mesmo nome
        for tt, n in lst:
            if tt == t and n not in nomes:
                nomes.append(n)
    return {"data": d.isoformat(), "tipo": tipos[0], "nome": "; ".join(nomes), "tipos": tipos,
            "nacional": "nacional" in tipos}


def eh_feriado_nacional(d):
    f = feriado(d)
    return bool(f and f["nacional"])


def dia_util(d):
    """Segunda a sexta, fora feriado nacional (ponto facultativo e feriado so da JF contam como uteis)."""
    return d.weekday() < 5 and not eh_feriado_nacional(d)


def dias_uteis_entre(a, b):
    """Dias uteis em (a, b], datas — a mesma semantica do antigo inicio.dias_uteis_entre,
    agora sem os feriados nacionais."""
    n, d = 0, a
    while d < b:
        d += timedelta(days=1)
        if dia_util(d):
            n += 1
    return n


def dia_de_edicao(d):
    """Segunda a sexta, INCLUSIVE feriado: a edicao sai em feriado (decisao 10; saiu em 12/10 e 02/11).
    Para contar edicoes (dia sem registro, gap); dia_util (sem feriado nacional) mede trabalho das fontes."""
    return d.weekday() < 5


def dias_de_edicao_entre(a, b):
    """Dias de edicao (seg-sex, feriado incluido) em (a, b], datas."""
    n, d = 0, a
    while d < b:
        d += timedelta(days=1)
        if dia_de_edicao(d):
            n += 1
    return n


def uteis_sem_registro(ultima, hoje):
    """Dias de EDICAO (seg-sex, feriado incluido) estritamente entre `ultima` e `hoje`: edicoes que
    deveriam existir. Antes pulava o feriado nacional, e uma edicao de feriado enviada sem registro
    (queda, PUSH: FALHOU) passava calada e era repetida no dia seguinte (20/11/2026, sexta)."""
    out, d = [], ultima + timedelta(days=1)
    while d < hoje:
        if dia_de_edicao(d):
            out.append(d)
        d += timedelta(days=1)
    return out


def no_intervalo(a, b):
    """Feriados (qualquer tipo) com data em [a, b], datas."""
    out, d = [], a
    while d <= b:
        f = feriado(d)
        if f:
            out.append(f)
        d += timedelta(days=1)
    return out


def rotulo(f):
    """'15/11 (dom) Proclamação da República [nacional]'."""
    d = date.fromisoformat(f["data"])
    return "%s (%s) %s [%s]" % (d.strftime("%d/%m"), DIAS_CURTOS[d.weekday()], f["nome"],
                                "; ".join(ROTULO_TIPO[t] for t in f["tipos"]))


def agrupar(fs):
    """Rotulos com as sequencias longas (recesso da JF, Semana Santa) num trecho so."""
    out, i = [], 0
    while i < len(fs):
        j = i
        while (j + 1 < len(fs) and fs[j + 1]["nome"] == fs[i]["nome"]
               and date.fromisoformat(fs[j + 1]["data"]) - date.fromisoformat(fs[j]["data"]) == timedelta(days=1)):
            j += 1
        if j - i >= 2:
            a, b = date.fromisoformat(fs[i]["data"]), date.fromisoformat(fs[j]["data"])
            out.append("%s a %s %s [%s]" % (a.strftime("%d/%m"), b.strftime("%d/%m"), fs[i]["nome"],
                                            "; ".join(ROTULO_TIPO[t] for t in fs[i]["tipos"])))
        else:
            out += [rotulo(f) for f in fs[i:j + 1]]
        i = j + 1
    return out


def main():
    args = sys.argv[1:]
    if len(args) == 1 and len(args[0]) == 4:
        a, b = date(int(args[0]), 1, 1), date(int(args[0]), 12, 31)
    elif len(args) == 2:
        a, b = date.fromisoformat(args[0]), date.fromisoformat(args[1])
    else:
        sys.exit("uso: feriados.py AAAA | AAAA-MM-DD AAAA-MM-DD")
    for x in agrupar(no_intervalo(a, b)):
        print(x)


if __name__ == "__main__":
    main()
