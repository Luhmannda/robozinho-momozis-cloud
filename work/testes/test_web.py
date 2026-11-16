#!/usr/bin/env python3
# =====================================================================
# test_web.py — testes do grupo WEB (sem pytest, sem rede):
#   repeticao.py (identidade numerica, "-conteudo", datas/milhar; execucao de
#   16/11 contra o historico ate 13/11), coleta_web.py (nova tentativa, C7,
#   saida compacta, PROMO/REPETIDA?, SOURCE_STATUS), resolver_jota.py (saltos
#   sem -L, RECUSADO, JA_PUBLICADA, L<n>, BLOQUEADO), jota_extrair.py e
#   versiculo.py (sonda do YouVersion, linha unica, SOURCE_STATUS).
# USO: python3 work/testes/test_web.py   (imprime OK/FALHOU; sai != 0 em falha)
# Tudo roda numa pasta temporaria (ROBOZINHO_TMP proprio); a rede e simulada.
# =====================================================================

import contextlib
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import traceback
import unicodedata
from datetime import date, datetime
from zoneinfo import ZoneInfo

AQUI = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.dirname(AQUI)
FIX = os.path.join(AQUI, "fixtures", "web")
TMPDIR = tempfile.mkdtemp(prefix="robozinho-web-")
os.environ["ROBOZINHO_TMP"] = TMPDIR
sys.path.insert(0, WORK)

import repeticao        # noqa: E402
import coleta_web       # noqa: E402
import resolver_jota    # noqa: E402
import jota_extrair     # noqa: E402
import versiculo        # noqa: E402

TZ = ZoneInfo("America/Sao_Paulo")
RESULTADOS = []


def teste(f):
    RESULTADOS.append(f)
    return f


def ler(nome):
    with open(os.path.join(FIX, nome), encoding="utf-8") as f:
        return json.load(f)


def historico():
    return ler("historico-ate-1311.json")["executions"]


def saida_de(func, *a, **k):
    buf = io.StringIO()
    codigo = None
    with contextlib.redirect_stdout(buf):
        try:
            codigo = func(*a, **k)
        except SystemExit as e:
            codigo = e.code
    return codigo, buf.getvalue()


# ------------------------------------------------------------ repeticao
def checar_local(ex, execucoes):
    """Copia de Update-Historico.checar_repeticao (13/11), contando TODOS os pares."""
    chaves_anteriores = {it.get("chave") for e in execucoes for it in e.get("items") or [] if it.get("chave")}
    rep, dup, vistos = [], [], []
    idx = repeticao.indice(execucoes, ignorar_exec_id=ex.get("execution_id"))
    for it in ex.get("items") or []:
        ch = (it.get("chave") or "").lower()
        if not ch or repeticao.ignorar(it):
            continue
        tok = repeticao.tokens_item(ch, it.get("titulo"))
        if ch not in chaves_anteriores:
            m = repeticao.procurar(tok, idx, excluir=ch)
            if m:
                rep.append((ch, m))
        for ch2, t2 in vistos:
            if repeticao.parecidas(tok, t2):
                dup.append((ch, ch2))
        vistos.append((ch, tok))
    return rep, dup


JOTA_REPETIDOS = [
    {"categoria": "Mídia", "titulo": "STF rejeita recursos e manda encerrar ação sobre acordo dos planos econômicos",
     "chave": "jota|noticia|stf-rejeita-recursos-e-manda-encerrar-acao-sobre-acordo-dos|2026|2026-11-13"},
    {"categoria": "Mídia", "titulo": "Gilmar Mendes interrompe julgamento com maioria formada para derrubar lei "
                                     "que restringe cota racial",
     "chave": "jota|noticia|gilmar-mendes-interrompe-julgamento-com-maioria-formada-pa|2026|2026-11-13"}]


@teste
def repeticao_execucao_1611():
    ex = ler("execucao-1611.json")
    ex["items"] += JOTA_REPETIDOS
    rep, dup = checar_local(ex, historico())
    decretos = [p for p in dup if "decreto" in p[0]]
    assert not decretos, "pares falsos de decreto: %s" % decretos
    assert not dup, "duplicatas inesperadas: %s" % dup
    chaves = dict(rep)
    assert "stf|informativo|repercussao-geral-397-conteudo|2026|2026-11-09" not in chaves, "rg397-conteudo virou repetida"
    assert chaves.get(JOTA_REPETIDOS[0]["chave"]) == \
        "push-stf|noticia|stf-rejeita-recursos-contra-decisao-que-homologou-acordo|2026|2026-11-12", rep
    assert chaves.get(JOTA_REPETIDOS[1]["chave"]) == \
        "jota|noticia|gilmar-mendes-interrompe-julgamento-com-maioria-formada|2026|2026-11-12", rep
    assert len(rep) == 2, rep
    # o modulo antigo dava 10 pares de decreto: a fixture e a mesma
    toks = [repeticao.tokens_item(it["chave"], it["titulo"]) for it in ex["items"] if "decreto" in it["chave"]]
    assert len(toks) == 5 and all(t.ident and t.forte for t in toks)


@teste
def repeticao_update_historico_real():
    """O checar_repeticao do Update-Historico.py (grupo EST) com o modulo novo."""
    caminho = os.path.join(WORK, "Update-Historico.py")
    spec = importlib.util.spec_from_file_location("update_historico", caminho)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    ex = ler("execucao-1611.json")
    ex["items"] += JOTA_REPETIDOS
    h = historico()
    ca = {it.get("chave") for e in h for it in e.get("items") or [] if it.get("chave")}
    avisos = mod.checar_repeticao(ex, h, ca)
    assert not [a for a in avisos if a.startswith("POSSIVEL_DUPLICATA")], avisos
    rep = [a for a in avisos if a.startswith("POSSIVEL_REPETIDA")]
    assert len(rep) == 2 and all("jota|noticia" in a for a in rep), avisos


@teste
def repeticao_regras():
    ti = repeticao.tokens_item
    p = repeticao.parecidas
    # mesmo ato de duas fontes (PUSH escrito x ref do Congresso, datas diferentes na chave)
    assert p(ti("planalto|lei|15529|2026|2026-11-12", "Lei nº 15.529, de 12/11/2026"),
             ti("planalto|lei|15529|2026|2026-11-11", "Lei nº 15.529/2026 (herdada)"))
    # numeros diferentes do mesmo tipo nunca, nem com ementa igual
    assert not p(ti("planalto|lei|15530|2026|2026-11-17", "Lei nº 15.530, de 17/11/2026 — altera o CPC"),
                 ti("planalto|lei|15531|2026|2026-11-17", "Lei nº 15.531, de 17/11/2026 — altera o CPC"))
    # titulo que comeca pelo ato (identidade fraca): numero diferente nao casa
    assert not p(repeticao.tokens("Lei 15.531 altera o Código de Processo Civil e o prazo recursal"),
                 ti("planalto|lei|15530|2026|2026-11-17", "Lei 15.530 altera o Código de Processo Civil e o prazo recursal"))
    # X-conteudo ~ X nao e repeticao; edicoes diferentes tambem nao
    rg397c = ti("stf|informativo|repercussao-geral-397-conteudo|2026|2026-11-09", "Repercussão Geral em Pauta nº 397")
    rg397 = ti("stf|informativo|repercussao-geral-397|2026|2026-11-11", "Repercussão Geral em Pauta nº 397")
    rg398c = ti("stf|informativo|repercussao-geral-398-conteudo|2026|2026-11-20", "Repercussão Geral em Pauta nº 398")
    assert not p(rg397c, rg397) and not p(rg397c, rg398c) and p(rg397c, rg397c)
    assert not p(ti("stf|informativo|1236-conteudo|2026|2026-11-10", "Informativo STF nº 1236"),
                 ti("stf|informativo|1236|2026|2026-11-10", "Informativo STF nº 1236"))
    # excecao "-conteudo" tambem sem identidade numerica
    assert not p(ti("x|tipo|boletim-especial-conteudo|2026|2026-11-10", "Boletim especial de teses repetitivas"),
                 ti("x|tipo|boletim-especial|2026|2026-11-09", "Boletim especial de teses repetitivas"))
    # datas e milhar
    assert repeticao.tokens("Decreto nº 13.166, de 12/11/2026") == {"decreto", "13166"}
    assert "2026" not in repeticao.tokens("PLP 299/2026 dobra o aumento")
    assert "1484" in repeticao.tokens("Tema 1.484: quanto custa")
    # compatibilidade: set puro continua aceito
    assert p({"a1", "b1", "c1", "d1"}, {"a1", "b1", "c1", "d1", "e1"})
    # procurar: identidade igual vence a semelhanca de titulo
    idx = [("planalto|lei|15529|2026|2026-11-11", ti("planalto|lei|15529|2026|2026-11-11", "Lei nº 15.529")),
           ("planalto|lei|15528|2026|2026-11-11", ti("planalto|lei|15528|2026|2026-11-11", "Lei nº 15.528"))]
    assert repeticao.procurar(ti("planalto|lei|15529|2026|2026-11-12", "Lei nº 15.529, de 12/11/2026"), idx) == \
        "planalto|lei|15529|2026|2026-11-11"
    assert repeticao.normalizar_url("https://www.jota.info/a/b/?utm_source=x#c") == "jota.info/a/b"


def _update_historico():
    caminho = os.path.join(WORK, "Update-Historico.py")
    spec = importlib.util.spec_from_file_location("update_historico", caminho)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@teste
def repeticao_sinonimos_de_tipo():
    """17/11: lc/lcp/lei-complementar (historico real: lc|234, lc|235, lcp|238,
    lei-complementar|237), ec/emc, dl: a mesma especie com grafias diferentes na
    chave nao pode virar 'materias diferentes' (matava POSSIVEL_REPETIDA/DUPLICATA)."""
    ti, p = repeticao.tokens_item, repeticao.parecidas
    lc = ti("planalto|lc|239|2026|2026-11-14", "LC 239/2026 - regime de recuperação fiscal dos estados")
    lcc = ti("planalto|lei-complementar|239|2026|2026-11-14",
             "Lei Complementar nº 239, de 14/11/2026 — regime de recuperação fiscal dos estados")
    lcp = ti("planalto|lcp|239|2026|2026-11-14", "Lei Complementar nº 239/2026 (recuperação fiscal)")
    assert lc.ident == lcc.ident == lcp.ident == ("lei-complementar", "239")
    assert p(lc, lcc) and p(lcp, lcc) and p(lc, lcp)
    assert not p(lc, ti("planalto|lei-complementar|240|2026|2026-11-14",
                        "Lei Complementar nº 240 — regime de recuperação fiscal dos estados"))
    assert p(ti("planalto|ec|137|2026|2026-11-14", "EC 137"),
             ti("planalto|emenda-constitucional|137|2026|2026-11-14", "Emenda Constitucional nº 137"))
    assert p(ti("planalto|emc|137|2026|2026-11-14", "x"), ti("planalto|ec|137|2026|2026-11-13", "y"))
    assert p(ti("planalto|dl|3689|1941|1941-10-03", "a"), ti("planalto|decreto-lei|3689|1941|1941-10-03", "b"))
    assert p(ti("planalto|medida-provisoria|1401|2026|x", "a"), ti("planalto|mp|1401|2026|x", "b"))
    assert repeticao.tipo_canonico("LCP") == "lei-complementar" and repeticao.tipo_canonico("xyz") == "xyz"
    # grafia desconhecida, mesmo numero: o titulo decide (antes: False sem olhar o titulo)
    t = "Lei Complementar nº 239 regime de recuperação fiscal dos estados"
    assert repeticao.mesma_identidade(ti("planalto|lcomp|239|2026|x", t), lcc) is None
    assert p(ti("planalto|lcomp|239|2026|x", t), lcc)
    assert not p(ti("planalto|decreto|239|2026|x", "Decreto nº 239 dispõe sobre vigilância sanitária"), lcc)
    # edicoes de informativo continuam estritas (tipos gerados pelo codigo)
    assert repeticao.mesma_identidade(ti("stj|informativo|870|2026|x", "Informativo STJ nº 870"),
                                      ti("stf|informativo|870|2026|x", "Informativo STJ nº 870")) is False
    # titulo "LC 235/2026 - ..." ganha identidade fraca
    assert repeticao.tokens("LC 235/2026 - redução de tributos").ident == ("lei-complementar", "235")
    # o checar_repeticao real (Update-Historico --validar): repetida e duplicata voltam
    mod = _update_historico()
    h = [{"execution_id": "2026-11-14-7h", "items": [
        {"categoria": "Planalto/Legislação", "chave": "planalto|lc|239|2026|2026-11-14",
         "titulo": "LC 239/2026 - regime de recuperação fiscal dos estados"}]}]
    ex = {"execution_id": "2026-11-17-7h", "items": [
        {"categoria": "Planalto/Legislação", "chave": "planalto|lei-complementar|239|2026|2026-11-14",
         "titulo": "Lei Complementar nº 239, de 14/11/2026 — regime de recuperação fiscal dos estados"},
        {"categoria": "Planalto/Legislação", "chave": "planalto|lcp|239|2026|2026-11-14",
         "titulo": "Lei Complementar nº 239/2026 (recuperação fiscal)"}]}
    ca = {it["chave"] for e in h for it in e["items"]}
    avisos = mod.checar_repeticao(ex, h, ca)
    assert len([a for a in avisos if a.startswith("POSSIVEL_REPETIDA")]) == 2, avisos
    assert [a for a in avisos if a.startswith("POSSIVEL_DUPLICATA_NA_EDICAO: planalto|lcp|239")], avisos


# ------------------------------------------------------------ coleta_web
def coleta_fixture():
    """coleta_web.json de 16/11 com datas de volta a date/datetime."""
    res = ler("coleta_web-1611.json")
    for r in res:
        for i in r["itens"]:
            if isinstance(i.get("data"), str) and len(i["data"]) == 10:
                i["data"] = date.fromisoformat(i["data"])
            if isinstance(i.get("quando"), str) and i["quando"] not in ("None", ""):
                i["quando"] = datetime.fromisoformat(i["quando"])
            elif i.get("quando") == "None":
                i["quando"] = None
    return res


@teste
def coleta_marcar_promo_e_repetidas():
    res = coleta_fixture()
    for r in res:
        for i in r["itens"]:
            i.pop("repetida", None)
    res[2]["itens"].append({"tipo": "noticia", "situacao": "NOVA", "url": "https://conjur.com.br/2026-nov-15/x",
                            "titulo": "STF rejeita recursos e manda encerrar ação sobre acordo dos planos econômicos"})
    res[3]["itens"].append({"situacao": "NOVA", "url": "https://www.migalhas.com.br/quentes/1/x",
                            "titulo": "Sorteio de livros para leitores do Migalhas"})
    res[3]["itens"].append({"situacao": "NOVA", "url": "https://www.migalhas.com.br/quentes/2/y",
                            "titulo": "Decreto nº 13.150 regulamenta a Lei de Licitações"})
    coleta_web.marcar_promo_e_repetidas(res, historico())
    marcadas = [(i["titulo"], i["repetida"]) for r in res for i in r["itens"] if i.get("repetida")]
    assert marcadas == [("STF rejeita recursos e manda encerrar ação sobre acordo dos planos econômicos",
                         "push-stf|noticia|stf-rejeita-recursos-contra-decisao-que-homologou-acordo|2026|2026-11-12")], marcadas
    assert res[3]["itens"][-2]["situacao"] == "PROMO"


@teste
def coleta_nova_tentativa():
    chamadas = []
    roteiro = {}

    def falso(url, timeout):
        chamadas.append(url)
        return roteiro[url].pop(0)
    antigo, pausa = coleta_web._fetch1, coleta_web.PAUSA_REPETICAO
    coleta_web._fetch1, coleta_web.PAUSA_REPETICAO = falso, 0
    try:
        roteiro.update({"a": [(0, "", False), (200, "ok", False)], "b": [(404, "", False)],
                        "c": [(503, "", False), (503, "", False)], "d": [(0, "", True), (200, "x", False)],
                        "e": [(0, "", True), (200, "y", False)], "f": [(429, "", False), (200, "z", False)]})
        assert coleta_web.fetch("a") == (200, "ok")
        assert coleta_web.fetch("b") == (404, "")
        assert coleta_web.fetch("c") == (503, "")
        assert coleta_web.fetch("d") == (200, "x")                         # listagem: tenta de novo
        assert coleta_web.fetch("e", repetir_timeout=False) == (0, "")     # pagina de materia: nao
        assert coleta_web.fetch_many(["f"]) == {"f": (200, "z")}
        assert chamadas.count("a") == 2 and chamadas.count("b") == 1 and chamadas.count("e") == 1
    finally:
        coleta_web._fetch1, coleta_web.PAUSA_REPETICAO = antigo, pausa


@teste
def coleta_tentativas_reais():
    """Rodada 2: o texto dizia sempre '(2 tentativas)', mas 403/404 nao tenta de
    novo. Agora o numero e o real (campo "tentativas" no bloco do coleta_web.json)."""
    roteiro = {coleta_web.URL_LEIS: [(0, "", False), (0, "", False)], coleta_web.URL_MPV: [(403, "", False)],
               coleta_web.URL_MIGALHAS: [(404, "", False)]}
    pedidos = []

    def falso(url, timeout):
        pedidos.append(url)
        return roteiro[url].pop(0)
    antigo, pausa = coleta_web._fetch1, coleta_web.PAUSA_REPETICAO
    coleta_web._fetch1, coleta_web.PAUSA_REPETICAO = falso, 0
    try:
        z = datetime(2026, 11, 17, 7, 0, tzinfo=TZ)
        res = [coleta_web.leis(z, z, z, set()), coleta_web.mpvs(z, z, z, set()), coleta_web.migalhas(z, z, z, set())]
        roteiro.update({"a": [(503, "", False), (200, "ok", False)], "b": [(404, "", False)],
                        "c": [(0, "", True)]})
        assert coleta_web.fetch_n("a") == (200, "ok", 2) and coleta_web.fetch_n("b") == (404, "", 1)
        assert coleta_web.fetch_n("c", repetir_timeout=False) == (0, "", 1)
    finally:
        coleta_web._fetch1, coleta_web.PAUSA_REPETICAO = antigo, pausa
    assert [r["tentativas"] for r in res] == [2, 1, 1] and pedidos.count(coleta_web.URL_MPV) == 1, res
    st = coleta_web.status_fontes(res)
    assert st["congresso_ultimas_leis"] == ("falha", "http=0 (2 tentativas)"), st
    assert st["congresso_mpvs"] == ("falha", "http=403 (1 tentativa); conferir PLANALTO_ATO"), st
    assert st["migalhas"] == ("falha", "http=404 (1 tentativa)"), st
    linhas = coleta_web.imprimir(res, z, z, z)
    erro = [l for l in linhas if l.startswith("ERRO: congresso_mpv")]
    assert erro and erro[0].startswith("ERRO: congresso_mpv indisponivel (http=403, 1 tentativa) — antes de gastar"), erro
    assert "2 tentativas" not in "\n".join(l for l in linhas if "congresso_mpv" in l.lower())
    # coleta_web.json antigo (sem "tentativas"): nao inventa numero
    velho = [{"fonte": "congresso_mpv", "http": 0, "itens": [], "listadas": 0}]
    assert coleta_web.status_fontes(velho)["congresso_mpvs"] == ("falha", "http=0; conferir PLANALTO_ATO")
    assert any(l.startswith("ERRO: congresso_mpv indisponivel (http=0) — ") for l in coleta_web.imprimir(velho, z, z, z))


@teste
def coleta_conjur_pelo_dia():
    """C7: janela de 72h (13/11 07:05 -> 16/11 07:07; recorte 15/11 07:07)."""
    def h2(url, t):
        return '<h2 class="conjur-posts-tipo-titulo"><a href="%s">%s</a></h2>' % (url, t)
    base = "https://conjur.com.br/2026-nov-%02d/%s"
    lista = {"noticia": [(12, "a-antes", None), (13, "b-cedo", "2026-11-13T06:00:00-03:00"),
                         (13, "c-tarde", "2026-11-13T10:00:00-03:00"), (14, "d-meio", None),
                         (15, "e-cedo", "2026-11-15T06:00:00-03:00"), (15, "f-tarde", "2026-11-15T09:00:00-03:00"),
                         (16, "g-hoje", "2026-11-16T05:00:00-03:00")],
             "artigo": [(14, "h-artigo-meio", None)], "coluna": []}
    paginas = {}
    for tipo, u in coleta_web.URLS_CONJUR.items():
        paginas[u] = (200, "".join(h2(base % (d, s), "Titulo " + s) for d, s, _ in lista[tipo]))
        for d, s, q in lista[tipo]:
            meta = '<meta property="og:description" content="linha fina %s">' % s
            if q:
                meta += '<meta property="article:published_time" content="%s">' % q
            paginas[base % (d, s)] = (200, meta)
    antigo = coleta_web.fetch_many
    coleta_web.fetch_many = lambda urls: {u: paginas[u] for u in urls}
    try:
        inicio = datetime.fromisoformat("2026-11-13T07:05:50-03:00")
        fim = datetime.fromisoformat("2026-11-16T07:07:30-03:00")
        out = coleta_web.conjur(inicio, fim, fim.replace(day=15), set())
    finally:
        coleta_web.fetch_many = antigo
    sit = {i["url"].rsplit("/", 1)[1]: i["situacao"] for i in out["itens"]}
    assert sit == {"a-antes": "FORA", "b-cedo": "FORA", "c-tarde": "HERDADA", "d-meio": "HERDADA",
                   "e-cedo": "HERDADA", "f-tarde": "NOVA", "g-hoje": "NOVA", "h-artigo-meio": "HERDADA"}, sit


@teste
def coleta_ato_ja_publicado_com_outra_grafia():
    """planalto|lc|239 no historico = 'Lei Complementar nº 239' da listagem do Congresso."""
    h = [{"execution_id": "2026-11-14-7h", "items": [
        {"chave": "planalto|lc|239|2026|2026-11-14", "titulo": "LC 239/2026"},
        {"chave": "planalto|medida-provisoria|1401|2026|2026-11-14", "titulo": "MPV 1401"}]}]
    atos, _ = coleta_web.carregar_publicados(h)
    assert ("lei-complementar", "239") in atos and ("mpv", "1401") in atos, atos
    bloco = ('<div class="sf-lista-resumos__resumo"><dt>Norma:</dt><dd><a href="https://x/lcp239">'
             'Lei Complementar nº 239 de 14/11/2026</a> (<a href="#">DOU de 14/11/2026</a>)</dd>'
             '<dt>Ementa:</dt><dd>Regime de recuperação fiscal.</dd></div>'
             '<div class="sf-lista-resumos__resumo"><dt>Norma:</dt><dd><a href="https://x/l15540">'
             'Lei nº 15.540 de 14/11/2026</a> (<a href="#">DOU de 17/11/2026</a>)</dd></div>')
    antigo = coleta_web.fetch_n
    coleta_web.fetch_n = lambda url, *a, **k: (200, bloco, 1)
    try:
        inicio = datetime.fromisoformat("2026-11-14T07:05:00-03:00")
        fim = datetime.fromisoformat("2026-11-17T07:05:00-03:00")
        out = coleta_web.leis(inicio, fim, fim.replace(day=16), atos)
    finally:
        coleta_web.fetch_n = antigo
    sit = {i["numero"]: i["situacao"] for i in out["itens"]}
    assert sit == {"239": "JA_PUBLICADA", "15540": "NOVA"}, sit


@teste
def coleta_saida_compacta():
    res = coleta_fixture()
    ids_antes = {i["url"]: i.get("id") for r in res for i in r["itens"] if i.get("id")}
    for r in res:
        for i in r["itens"]:
            i.pop("id", None)
    inicio = datetime.fromisoformat("2026-11-13T07:05:50-03:00")
    fim = datetime.fromisoformat("2026-11-16T07:07:30-03:00")
    linhas = coleta_web.imprimir(res, inicio, fim, fim.replace(day=15))
    # os ids nao mudam (refs do orquestrador)
    ids_depois = {i["url"]: i.get("id") for r in res for i in r["itens"] if i.get("id")}
    assert ids_antes == ids_depois
    opin = [l for l in linhas if l.startswith(("[NOVA|ART]", "[NOVA|COL]", "[HERDADA|ART]", "[HERDADA|COL]"))]
    assert len(opin) == 10, len(opin)
    for l in opin:
        assert len(l.split(" | ", 2)[2]) <= 90, l
    escolhidas = {l.split(" | ")[0].split("] ")[1] for l in opin}
    assert {"c18", "c24", "c27", "c34", "c35", "c25"} <= escolhidas, escolhidas   # as usadas em 16/11 + Tema 118
    noticias = [l for l in linhas if "|NOT] c" in l]
    assert len(noticias) == 15 and any("Sentença julgou" in l or " — " in l for l in noticias)
    assert any(l.startswith("(+10 artigos/colunas fora do indice") for l in linhas)
    # MPV com http 0: erro aponta para PLANALTO_ATO antes do WebSearch
    erro = [l for l in linhas if l.startswith("ERRO: congresso_mpv")]
    assert erro and "PLANALTO_ATO" in erro[0], erro
    st = coleta_web.status_fontes(res)
    assert {k: v[0] for k, v in st.items()} == {"congresso_ultimas_leis": "ok", "congresso_mpvs": "falha",
                                                "conjur": "ok", "migalhas": "ok"}, st
    linha = coleta_web.linha_status(st)
    assert linha.startswith("SOURCE_STATUS {") and json.loads(linha[len("SOURCE_STATUS "):])["congresso_mpvs"] == "falha"


@teste
def fontes_status_merge():
    caminho = os.path.join(TMPDIR, "fontes_status.json")
    if os.path.exists(caminho):
        os.remove(caminho)
    with open(os.path.join(TMPDIR, "janela.json"), "w", encoding="utf-8") as f:
        json.dump({"execution_id": "2026-11-16-7h", "data": "2026-11-16", "doy": 320}, f)
    coleta_web.gravar_status({"conjur": ("ok", "35 publicaveis"), "migalhas": ("falha", "http=0")},
                             "coleta_web.py", caminho)
    versiculo.gravar_status({"youversion": ("nao_tentada", "sonda_falhou (esperado)")}, caminho=caminho)
    coleta_web.gravar_status({"migalhas": ("ok", "10 publicaveis")}, "coleta_web.py", caminho)
    d = json.load(open(caminho, encoding="utf-8"))
    assert set(d) == {"conjur", "migalhas", "youversion"}
    assert d["migalhas"] == {"status": "ok", "detalhe": "10 publicaveis", "script": "coleta_web.py",
                             "execution_id": "2026-11-16-7h"}
    assert d["youversion"]["script"] == "versiculo.py"


# ------------------------------------------------------------ resolver_jota
class RedeFalsa:
    """URL -> (codigo, redirect_url, html); registra todo pedido."""
    def __init__(self, mapa):
        self.mapa, self.pedidos = mapa, []

    def __call__(self, url, corpo=False, timeout=20):
        self.pedidos.append(url)
        return self.mapa.get(url, (404, "", ""))


def pagina(titulo):
    return '<meta property="og:title" content="%s">' % titulo


def rodar_resolver(linhas, mapa, extra=(), urls=None, janela=None):
    tsv = os.path.join(TMPDIR, "jota_links.tsv")
    with open(tsv, "w", encoding="utf-8") as f:
        f.write("\n".join(linhas) + "\n")
    if urls is not None:
        with open(os.path.join(TMPDIR, "jota_urls.tsv"), "w", encoding="utf-8") as f:
            f.write("".join("%d\t%s\n" % kv for kv in urls.items()))
    with open(os.path.join(TMPDIR, "janela.json"), "w", encoding="utf-8") as f:
        json.dump(janela or {"ignorar_execucao": ""}, f)
    rede = RedeFalsa(mapa)
    antigo_c, antigo_s = resolver_jota.curl, resolver_jota.sondar
    resolver_jota.curl, resolver_jota.sondar = rede, (lambda: None)
    try:
        codigo, out = saida_de(resolver_jota.main, [tsv, "--urls", os.path.join(TMPDIR, "jota_urls.tsv"),
                                                    "--janela", os.path.join(TMPDIR, "janela.json"),
                                                    "--historico", os.path.join(FIX, "historico-ate-1311.json")]
                               + list(extra))
    finally:
        resolver_jota.curl, resolver_jota.sondar = antigo_c, antigo_s
    return codigo, out.splitlines(), rede


W = "https://t.rdsv2.net/ls/click?upn=u001.FIXTURE-%02d"
J = "https://www.jota.info/justica/%s"


@teste
def resolver_seguranca():
    mapa = {
        W % 1: (302, J % "materia-boa-sobre-o-stf-e-o-cnj-hoje?utm_source=rd", ""),
        J % "materia-boa-sobre-o-stf-e-o-cnj-hoje?utm_source=rd": (200, "", pagina("Matéria boa sobre o STF e o CNJ hoje")),
        W % 2: (302, "https://click.rdstation.com.br/unsubscribe?email=x", ""),
        W % 3: (302, "https://www.jota.info/newsletter/descadastrar?id=1", ""),
        W % 4: (302, "https://www.jota.info/preferencias", ""),
        W % 5: (302, "https://evil.example.com/a", ""),
        W % 6: (302, W % 7, ""), W % 7: (302, W % 8, ""), W % 8: (302, W % 9, ""), W % 9: (302, W % 10, ""),
        W % 10: (302, W % 11, ""), W % 11: (302, J % "longe-demais-para-seguir-aqui", ""),
        W % 12: (302, J % "outra-materia-de-verdade-do-jota-com-slug", ""),
        J % "outra-materia-de-verdade-do-jota-com-slug": (200, "", pagina("Título que não tem nada a ver")),
        W % 13: (302, "https://www.jota.info/eleicoes/nunes-marques-manda-remover-em-24h-postagens-oficiais", ""),
        "https://www.jota.info/eleicoes/nunes-marques-manda-remover-em-24h-postagens-oficiais":
            (200, "", pagina("Nunes Marques manda remover em 24h postagens oficiais")),
        W % 14: (200, "", ""),
    }
    linhas = ["Matéria boa sobre o STF e o CNJ hoje\t" + W % 1,
              "Link do rodapé\t" + W % 2, "Outro rodapé\t" + W % 3, "Preferências\t" + W % 4,
              "Fora do JOTA\t" + W % 5, "Muitos saltos\t" + W % 6, "Título anunciado diferente\t" + W % 12,
              "Nunes Marques manda remover em 24h postagens oficiais\t" + W % 13, "Wrapper sem destino\t" + W % 14,
              "# comentario", ""]
    codigo, out, rede = rodar_resolver(linhas, mapa, ["--sem-historico"])
    assert codigo == 0, out
    est = [l.split("\t")[0] for l in out]
    assert est == ["OK", "RECUSADO", "RECUSADO", "RECUSADO", "RECUSADO", "RECUSADO", "SEM_MATCH", "OK", "ERRO"], out
    assert out[0].split("\t")[2] == J % "materia-boa-sobre-o-stf-e-o-cnj-hoje"          # sem utm_
    proibidos = ("unsubscribe", "descadastrar", "preferencias", "evil.example.com", "longe-demais")
    assert not [p for p in rede.pedidos if any(x in p for x in proibidos)], rede.pedidos
    assert "descadastro" in out[1] and "fora do jota.info" in out[4] and "redirecionamentos" in out[5]
    assert len([p for p in rede.pedidos if "FIXTURE-0" in p or "FIXTURE-1" in p]) >= 6


@teste
def resolver_lista_de_permitidos():
    """17/11: lista de PERMITIDOS no lugar da lista de palavras; titulo de
    descadastro recusado antes de qualquer pedido (via inline titulo<TAB>wrapper)."""
    mp = resolver_jota.motivo_proibido
    furos = ["https://www.jota.info/newsletter/cancelar-inscricao-em-todas-as-newsletters",
             "https://www.jota.info/conta/preferencias-de-envio-de-newsletters-do-jota",
             "https://www.jota.info/newsletter/remover-meu-email-de-todas-as-listas",
             "https://www.jota.info/newsletter/cancelamento", "https://www.jota.info/newsletter/sair-da-lista",
             "https://www.jota.info/minha-conta/newsletters", "https://www.jota.info/newsletters/cancelar",
             "https://www.jota.info/newsletters/jota-principal/cancelar-inscricao-em-todas-as-newsletters",
             "https://www.jota.info/justica/cancelar-inscricao-em-todas-as-newsletters-do-jota",
             "https://www.jota.info/justica/materia-qualquer?email=a@b.c",
             "https://www.jota.info/justica/preferencias", "https://www.jota.info/stf/conta/x-y-z-w",
             "https://www.jota.info/justica/sair-da-lista", "https://www.jota.info/justica/index.php",
             "https://t.rdsv2.net/wf/unsubscribe?upn=x", "https://t.rdsv2.net/wf/open?upn=x",
             "https://conta.jota.info/x", "https://www.jota.info/", "https://www.jota.info/tudo-sobre/stf"]
    assert not [u for u in furos if not mp(u)], [u for u in furos if not mp(u)]
    # as URLs reais de materia do historico continuam permitidas (176 em 16/11; amostra)
    reais = ["https://t.rdsv2.net/ls/click?upn=u001.abc",
             "https://www.jota.info/eleicoes/eleicoes-2026/nunes-marques-manda-remover-em-24h-postagens-oficiais-"
             "que-destaquem-figura-de-lula",
             "https://www.jota.info/newsletters/jota-principal/moraes-deve-definir-criterios-para-uso-da-imagem-de-"
             "bolsonaro",
             "https://www.jota.info/opiniao-e-analise/colunas/defensor-legis/a-psv-150-e-seus-efeitos-no-"
             "comportamento-do-legislativo-e-do-stf",
             "https://www.jota.info/executivo/perfil-da-polymarket-no-instagram-sai-do-ar-apos-atuacao-do-governo-lula",
             "https://www.jota.info/coberturas-especiais/contas-publicas/tcu-aprova-contas-do-governo",
             "https://www.jota.info/justica/materia-boa-sobre-o-stf?utm_source=newsletter&utm_medium=email"
             "&utm_campaign=principal"]
    assert not [u for u in reais if mp(u)], [(u, mp(u)) for u in reais if mp(u)]
    # destino proibido nao recebe pedido nenhum (nem sem corpo)
    mapa = {W % (30 + i): (302, u, "") for i, u in enumerate(furos[:5])}
    codigo, out, rede = rodar_resolver(["Matéria %d qualquer com título\t%s" % (i, W % (30 + i)) for i in range(5)],
                                       mapa, ["--sem-historico"])
    assert [l.split("\t")[0] for l in out] == ["RECUSADO"] * 5, out
    assert not [p for p in rede.pedidos if "jota.info" in p], rede.pedidos
    # titulo de rodape (inline): RECUSADO sem tocar o wrapper; manchete parecida passa
    rodapes = ["Caso não queira mais receber estes e-mails, cancele sua inscrição",
               "Caso não queira mais receber estes e-mails, clique aqui",
               "Se quer parar de receber esta newsletter, clique aqui", "Sair da lista", "Preferências"]
    destino = J % "aposentados-podem-deixar-de-receber-beneficio-apos-revisao"
    manchete = "Aposentados podem deixar de receber benefício após revisão"
    mapa = {W % 40: (302, destino, ""), destino: (200, "", pagina(manchete))}
    linhas = ["%s\t%s" % (t, W % (41 + i)) for i, t in enumerate(rodapes)] + ["%s\t%s" % (manchete, W % 40)]
    codigo, out, rede = rodar_resolver(linhas, mapa, ["--sem-historico"])
    assert [l.split("\t")[0] for l in out] == ["RECUSADO"] * 5 + ["OK"], out
    assert all("titulo de descadastro" in l for l in out[:5]), out
    assert rede.pedidos == [W % 40, destino], rede.pedidos
    # so rodape com link: nem a sondagem de bloqueio roda; com BLOQUEADO, o RECUSADO ainda sai
    sondou = []
    antigo = resolver_jota.sondar
    tsv = os.path.join(TMPDIR, "jota_links.tsv")
    with open(tsv, "w", encoding="utf-8") as f:
        f.write("%s\n" % linhas[0])
    resolver_jota.sondar = lambda: sondou.append(1) or ("https://t.rdsv2.net/", "000")
    try:
        codigo, saida = saida_de(resolver_jota.main, [tsv, "--sem-historico"])
        assert codigo == 0 and not sondou and saida.startswith("RECUSADO\tCaso não queira"), saida
        with open(tsv, "w", encoding="utf-8") as f:
            f.write("%s\n%s\t%s\n" % (linhas[0], manchete, W % 40))
        codigo, saida = saida_de(resolver_jota.main, [tsv, "--sem-historico"])
    finally:
        resolver_jota.sondar = antigo
    assert codigo == 3 and sondou and saida.splitlines()[1].startswith("RECUSADO\tCaso não queira"), saida


@teste
def resolver_historico_e_indice():
    titulos = [l.split("\t")[0] for l in open(os.path.join(FIX, "jota_links.tsv"), encoding="utf-8")]
    mapa = {}
    linhas = []
    urls = {}
    for n, t in enumerate(titulos, 1):
        destino = J % ("materia-%02d-com-slug-longo-de-verdade" % n)
        mapa[W % n] = (302, destino, "")
        mapa[destino] = (200, "", pagina(t))
        urls[n] = W % n
        linhas.append("%s\tL%d" % (t, n) if n % 2 else "%s\t[L%d]" % (t, n))
    linhas.append("Gilmar Mendes interrompe julgamento com maioria formada para derrubar lei que restringe cota racial")
    linhas.append("Título sem link e inédito para o teste")
    linhas.append("Índice que não existe\tL99")
    codigo, out, rede = rodar_resolver(linhas, mapa, urls=urls)
    ja = [l for l in out if l.startswith("JA_PUBLICADA")]
    assert len([l for l in ja if "\tL" not in l]) == 3, out          # 2 do TSV + a linha sem URL
    assert sum(1 for l in out[:19] if l.startswith("JA_PUBLICADA")) == 2, out[:19]
    assert sum(1 for l in out[:19] if l.startswith("OK")) == 17, out[:19]
    assert out[19].startswith("JA_PUBLICADA") and out[20].startswith("SEM_LINK") and out[21].startswith("ERRO"), out[19:]
    # JA_PUBLICADA pelo titulo nao faz pedido nenhum
    assert W % 10 not in rede.pedidos and W % 18 not in rede.pedidos
    # URL final ja publicada
    mapa2 = {W % 1: (302, "https://www.jota.info/stf/do-supremo/fux-suspende-processos-sobre-fim-das-bets", ""),
             "https://www.jota.info/stf/do-supremo/fux-suspende-processos-sobre-fim-das-bets":
                 (200, "", pagina("Título novo qualquer da matéria das bets"))}
    h = historico()
    h[-1]["items"].append({"chave": "jota|noticia|fux-bets|2026|2026-11-13", "titulo": "Outra coisa",
                           "url": "https://www.jota.info/stf/do-supremo/fux-suspende-processos-sobre-fim-das-bets"})
    caminho = os.path.join(TMPDIR, "hist.json")
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump({"executions": h}, f)
    codigo, out, _ = rodar_resolver(["Título novo qualquer da matéria das bets\t" + W % 1], mapa2,
                                    ["--historico", caminho])
    assert out == ["JA_PUBLICADA\tTítulo novo qualquer da matéria das bets\tjota|noticia|fux-bets|2026|2026-11-13"], out


@teste
def resolver_reexecucao_e_bloqueio():
    # re-execucao: a edicao ignorada nao conta como publicada
    t = "Gilmar Mendes interrompe julgamento com maioria formada para derrubar lei que restringe cota racial"
    _, out, rede = rodar_resolver([t, "Clipping da Folha sem matéria própria\tsem link"], {},
                                  janela={"ignorar_execucao": "2026-11-13-7h"})   # a edicao que a publicou
    assert out[0].startswith("SEM_LINK") and out[1].startswith("SEM_LINK\tClipping da Folha"), out
    assert not rede.pedidos
    # BLOQUEADO: primeira linha, sai com 3, os ja publicados continuam marcados
    tsv = os.path.join(TMPDIR, "jota_links.tsv")
    with open(tsv, "w", encoding="utf-8") as f:
        f.write("%s\t%s\nTítulo inédito qualquer\t%s\n" % (t, W % 1, W % 2))
    antigo = resolver_jota.sondar
    resolver_jota.sondar = lambda: ("https://t.rdsv2.net/", "000")
    try:
        codigo, saida = saida_de(resolver_jota.main, [tsv, "--historico", os.path.join(FIX, "historico-ate-1311.json"),
                                                      "--janela", os.path.join(TMPDIR, "nao-existe.json")])
    finally:
        resolver_jota.sondar = antigo
    linhas = saida.splitlines()
    assert codigo == 3 and linhas[0].startswith("BLOQUEADO\thttps://t.rdsv2.net/ http=000"), linhas
    assert len(linhas) == 2 and linhas[1].startswith("JA_PUBLICADA"), linhas


# ------------------------------------------------------------ jota_extrair
@teste
def jota_extrair_formatos():
    urls = os.path.join(TMPDIR, "jota_urls_ext.tsv")
    codigo, out = saida_de(jota_extrair.main, ["--novo", "--urls", urls, os.path.join(FIX, "jota_thread_ultimas.json")])
    assert codigo == 0, out
    assert "rdsv2" not in out and "http" not in out.split("\n", 1)[1].rsplit("(links", 1)[0], out
    indice = [l.rstrip("\n").split("\t") for l in open(urls, encoding="utf-8")]
    assert len(indice) == 6, indice
    nums = [u.split("TESTE-")[1][:2] for _, u in indice]
    assert nums == ["04", "07", "11", "13", "15", "16"], nums       # titulos; sem rodape/propaganda/imagem
    assert "21" not in nums                                          # descadastro nunca entra
    assert "Fim da 6x1: Dino mira em lacunas, faz ajustes, mas não muda principais pontos da emenda [L1]" in out
    assert "Fuga do Brasil tem impacto negativo na imagem de Flávio, diz AtlasIntel [L3] | Por Daniel Marcelino" in out
    assert "Título sem link próprio no bloco | Por Fulano | Leia mais [L5]" in out
    assert "| Leia mais [L" not in out.replace("Leia mais [L5]", "")
    assert "=== Fim da 6x1: Dino mira em lacunas | 13/11/2026 16:37 | JOTA | Últimas Notícias ===" in out
    assert "1 descadastro/preferencias" in out.splitlines()[0]
    # mesmo e-mail em blocos de conteudo, com texto antes: mesma numeracao (indice continuado)
    codigo, out2 = saida_de(jota_extrair.main, ["--urls", urls, os.path.join(FIX, "jota_thread_blocos.txt"),
                                                os.path.join(FIX, "jota_principal.txt")])
    assert codigo == 0
    assert "[L1]" in out2 and "nenhum link novo" not in out2.splitlines()[0]
    indice2 = [l.rstrip("\n").split("\t") for l in open(urls, encoding="utf-8")]
    assert indice2[:6] == indice and len(indice2) == 10, indice2   # +3 wrappers da prosa +1 materia direta
    assert "Leia mais. [L8]" in out2 and "TESTE-36" not in open(urls).read() and "TESTE-99" not in open(urls).read()
    assert "Matéria direta: [L10]" in out2


@teste
def jota_extrair_rodape_clique_aqui():
    """'Caso nao queira mais receber estes e-mails, clique aqui [url]': antes o
    link entrava no indice (so 'cancele sua inscri' era reconhecido)."""
    arq = os.path.join(TMPDIR, "rodape.txt")
    with open(arq, "w", encoding="utf-8") as f:
        f.write("STF | Matéria boa sobre o STF [ https://t.rdsv2.net/ls/click?upn=u001.MATERIA ]\n\n"
                "Caso não queira mais receber estes e-mails, clique aqui "
                "[ https://t.rdsv2.net/ls/click?upn=u001.RODAPE ]\n"
                "Se não quiser mais receber, toque aqui [ https://t.rdsv2.net/ls/click?upn=u001.RODAPE2 ]\n")
    urls = os.path.join(TMPDIR, "jota_urls_rodape.tsv")
    codigo, out = saida_de(jota_extrair.main, ["--novo", "--urls", urls, arq])
    assert codigo == 0 and "2 descadastro/preferencias" in out.splitlines()[0], out
    assert open(urls, encoding="utf-8").read() == "1\thttps://t.rdsv2.net/ls/click?upn=u001.MATERIA\n"


RODAPE_REAL = "Caso não queira mais receber estes e-mails,  cancele sua inscrição"     # 16/11, RD Station


@teste
def jota_extrair_rodapes_reais():
    """Rodada 2: rodapes reais do JOTA de 16/11 (Direito na Midia/JOTA PRO e JOTA
    Principal; texto real, tokens falsos) e as variacoes que a ancora pode ter:
    'clique aqui' depois de quebra de linha ou de espacos de diagramacao, sem
    acento, NFD, caixa alta, 'caso nao queira', 'deixar de receber', 'cancelar
    inscricao', 'gerenciar preferencias'. Nenhum entra no indice."""
    urls = os.path.join(TMPDIR, "jota_urls_rodapes.tsv")
    assert os.path.exists(os.path.join(FIX, "jota_rodapes_reais.json")), \
        "fixture ausente: git add work/testes/fixtures/web/jota_rodapes_reais.json"
    codigo, out = saida_de(jota_extrair.main, ["--novo", "--urls", urls, os.path.join(FIX, "jota_rodapes_reais.json")])
    assert codigo == 0, out
    nums = [l.split("TESTE-R")[1][:2] for l in open(urls, encoding="utf-8")]
    assert nums == ["01", "02", "03", "04"], nums      # Visualizar, "Conheça o melhor...", a materia, JOTA PRO
    cab = out.splitlines()[0]
    assert "2 descadastro/preferencias" in cab and "1 propaganda" in cab and "7 sem texto" in cab, cab
    assert "Caso não queira mais receber estes e-mails, cancele sua inscrição ." in out, out
    import unicodedata
    variacoes = [
        "Caso não queira mais receber estes e-mails, clique aqui",
        "Caso não queira mais receber estes e-mails,\n clique aqui",
        "Caso não queira mais receber estes e-mails,   clique aqui",          # espacos de diagramacao
        "Caso nao queira mais receber estes e-mails,  cancele sua inscricao",
        unicodedata.normalize("NFD", RODAPE_REAL),
        RODAPE_REAL.upper(),
        "Caso não\u00a0queira mais receber estes e-mails,\u200b clique aqui",      # nbsp e zero-width
        "Caso não queira, clique aqui", "Caso nao queira,\n aqui",
        "Caso não queira receber mais nossos e-mails,\n Clique neste link",
        "Para não receber mais nossas newsletters,\n clique aqui",
        "Se quer deixar de receber esta newsletter,\n aqui", "Deixe de receber estes e-mails",
        "Cancelar inscrição", "Cancelar a sua inscrição", "cancelamento da inscricao", "CANCELAR INSCRIÇÃO",
        "Gerenciar preferências", "Gerenciar preferencias", "Gerencie sua preferência de envio",
        "Gerenciar newsletters", "Caso não queira mais receber estes e-mails,\n Sair",
        "Caso não queira mais receber estes e-mails:\n ",                     # imagem/botao depois da frase
        "Remova seu e-mail da lista", "Para sair da nossa lista, clique aqui"]
    bons = ["JUSTIÇA | Lei garante preferência a idosos no pagamento de precatórios",
            "STF | Matéria boa sobre o STF e o CNJ hoje"]
    partes = []
    for i, v in enumerate(variacoes):
        partes.append("%s [ https://t.rdsv2.net/ls/click?upn=u001.VAR-%02d ]." % (v, i))
        partes.append("%s [ https://t.rdsv2.net/ls/click?upn=u001.BOM-%02d ]" % (bons[i % 2], i))
    arq = os.path.join(TMPDIR, "variacoes.txt")
    with open(arq, "w", encoding="utf-8") as f:
        f.write("\n\n".join(partes) + "\n")
    codigo, out = saida_de(jota_extrair.main, ["--novo", "--urls", urls, arq])
    indice = open(urls, encoding="utf-8").read()
    assert codigo == 0 and "VAR-" not in indice, [l for l in indice.splitlines() if "VAR-" in l]
    assert indice.count("BOM-") == len(variacoes), indice
    assert "%d descadastro/preferencias" % len(variacoes) in out.splitlines()[0], out.splitlines()[0]
    # a funcao usada pelo resolver
    assert jota_extrair.trecho_descadastro("clique aqui", "Caso nao queira mais receber estes e-mails,") == \
        "Caso nao queira"
    assert jota_extrair.trecho_descadastro("clique aqui", "Para não receber mais nossas newsletters,") == \
        "não receber mais"
    assert jota_extrair.trecho_descadastro("Matéria direta:", "Gerencie suas preferências de e-mail:") == ""


@teste
def resolver_descadastro_variacoes():
    """Rodada 2: titulo de rodape com ou sem acento, NFD, 'caso nao queira',
    'deixar de receber', 'cancelar inscricao', 'gerenciar preferencias' e titulo
    que nao diz nada ('clique aqui', 'Sair'): RECUSADO sem nenhum pedido.
    Manchetes parecidas passam; URL com acento codificado e recusada."""
    import unicodedata
    titulos = [RODAPE_REAL, "Caso nao queira mais receber estes e-mails, cancele sua inscricao",
               unicodedata.normalize("NFD", RODAPE_REAL), RODAPE_REAL.upper(), "Caso não queira, clique aqui",
               "Caso não queira mais receber, toque aqui", "Para não receber mais nossas newsletters",
               "Deixe de receber estes e-mails", "Cancelar inscricao", "Cancelar a sua inscrição",
               "cancelamento da inscrição", "Gerenciar preferencias", "Gerencie sua preferência de envio",
               "GERENCIAR PREFERÊNCIAS", "Se quer parar de receber esta newsletter, clique aqui",
               "clique aqui", "Aqui", "Clique neste link", "Sair", "Remova seu e-mail"]
    linhas = ["%s\t%s" % (t, W % (60 + i)) for i, t in enumerate(titulos)]
    codigo, out, rede = rodar_resolver(linhas, {}, ["--sem-historico"])
    assert codigo == 0 and [l.split("\t")[0] for l in out] == ["RECUSADO"] * len(titulos), out
    assert all("\ttitulo de descadastro ou preferencias (" in l for l in out), out
    assert not rede.pedidos, rede.pedidos
    assert out[-5].endswith("(titulo generico: clique aqui)") and out[-2].endswith("(titulo generico: Sair)"), out
    for manchete in ["Aposentados podem deixar de receber benefício após revisão",
                     "Brasil pode sair da lista suja do trabalho escravo",
                     "TSE manda cancelar inscrição de candidato por fraude em domicílio eleitoral",
                     "Lei garante preferência a idosos no pagamento de precatórios",
                     "STF decide que contribuinte não precisa mais receber notificação por carta",
                     "Caso não queira depor, Bolsonaro pode ser conduzido pela PF"]:
        assert resolver_jota.titulo_de_descadastro(manchete) == "", manchete
    mp = resolver_jota.motivo_proibido
    for u in ["https://www.jota.info/justica/materia-boa-sobre-o-stf?gerenciar=prefer%C3%AAncias",
              "https://www.jota.info/justica/materia-boa-sobre-o-stf?x=n%C3%A3o-queira-mais-receber",
              "https://www.jota.info/justica/inscri%C3%A7%C3%A3o/materia-com-slug-longo",
              "https://www.jota.info/justica/caso-nao-queira-receber"]:
        assert mp(u), u
    assert mp("https://www.jota.info/stf/do-supremo/stf-decide-que-contribuinte-nao-precisa-mais-receber-carta") == ""


@teste
def jota_rodape_frase_e_ultima_oracao():
    """Volta 2: 'Você recebeu este e-mail porque se cadastrou no JOTA. Para sair,
    clique aqui [url]' entrava no indice (o texto do link nao era generico nem
    so de saida) e, copiado como titulo, o wrapper recebia 1 pedido. Agora a
    frase de rodape (RODAPE) e a ultima oracao so de saida contam, no extrator e
    no resolver. Manchetes com pergunta, ponto ou 'sair' no meio passam."""
    rodapes = [
        "Você recebeu este e-mail porque se cadastrou no JOTA. Para sair, clique aqui",
        "Voce recebeu este email porque se cadastrou no JOTA. Para sair, clique aqui",
        unicodedata.normalize("NFD", "Você está recebendo este e-mail porque se inscreveu. Clique aqui"),
        "VOCÊ RECEBEU ESTA NEWSLETTER PORQUE É ASSINANTE. GERENCIE AQUI",
        "Este e-mail foi enviado para leitor@exemplo.invalid. Clique aqui",
        "Obrigado pela leitura. Para sair, clique aqui", "Obrigado pela leitura! Sair",
        "Atenção: para sair, clique aqui", "Boa leitura; cancelar aqui"]
    manchetes = [
        "Você recebeu este e-mail? Golpe usa nome do STF para roubar dados",
        "STF manda remover posts. Entenda", "Min. Fux vota para cancelar multa bilionária",
        "Moraes nega pedido de Bolsonaro para sair do país", "Câmara aprova; Senado deve cancelar sessão",
        "TRIBUTOS | Receita manda cancelar CNPJ de empresas inativas", "Leia a íntegra da decisão. Clique aqui"]
    # extrator: os rodapes ficam fora do indice (mesma linha e com a frase na linha anterior)
    partes = []
    for i, r in enumerate(rodapes):
        partes.append("%s [ https://t.rdsv2.net/ls/click?upn=u001.ROD-%02d ]." % (r, i))
        partes.append("%s [ https://t.rdsv2.net/ls/click?upn=u001.MAN-%02d ]" % (manchetes[i % len(manchetes)], i))
    partes.append("Você recebeu este e-mail porque se cadastrou no JOTA.\n Clique aqui "
                  "[ https://t.rdsv2.net/ls/click?upn=u001.ROD-90 ]")
    partes.append("Obrigado pela leitura. Para sair,\n clique aqui [ https://t.rdsv2.net/ls/click?upn=u001.ROD-91 ]")
    arq = os.path.join(TMPDIR, "rodape_v2.txt")
    with open(arq, "w", encoding="utf-8") as f:
        f.write("\n\n".join(partes) + "\n")
    urls = os.path.join(TMPDIR, "jota_urls_v2.tsv")
    codigo, out = saida_de(jota_extrair.main, ["--novo", "--urls", urls, arq])
    indice = open(urls, encoding="utf-8").read()
    assert codigo == 0 and "ROD-" not in indice, [l for l in indice.splitlines() if "ROD-" in l]
    assert indice.count("MAN-") == len(rodapes), indice
    assert "%d descadastro/preferencias" % (len(rodapes) + 2) in out.splitlines()[0], out.splitlines()[0]
    assert jota_extrair.trecho_descadastro(rodapes[0]) == "Você recebeu este e-mail"
    assert jota_extrair.trecho_descadastro(rodapes[5]) == "Para sair, clique aqui"
    assert jota_extrair.ultima_oracao("Lei 15.123 garante. Sair.") == ("Lei 15.123 garante.", " Sair.")
    assert jota_extrair.ultima_oracao("e-mail:x 15.123") == ("", "e-mail:x 15.123")
    # resolver: titulo de rodape com o wrapper -> RECUSADO sem nenhum pedido; manchetes passam
    linhas = ["%s\t%s" % (t, W % (80 + i)) for i, t in enumerate(rodapes)]
    codigo, out, rede = rodar_resolver(linhas, {}, ["--sem-historico"])
    assert codigo == 0 and [l.split("\t")[0] for l in out] == ["RECUSADO"] * len(rodapes), out
    assert all("\ttitulo de descadastro ou preferencias (" in l for l in out), out
    assert out[0].endswith("(Você recebeu este e-mail)") and out[5].endswith("(Para sair, clique aqui)"), out
    assert not rede.pedidos, rede.pedidos
    for t in manchetes:
        assert resolver_jota.titulo_de_descadastro(t) == "", t
        assert jota_extrair.trecho_descadastro(t) == "", t


@teste
def jota_extrair_e_resolver_juntos():
    """L<n> do extrator resolvido pelo resolver (indice do proprio extrator)."""
    urls = os.path.join(TMPDIR, "jota_urls.tsv")
    saida_de(jota_extrair.main, ["--novo", "--urls", urls, os.path.join(FIX, "jota_thread_ultimas.json")])
    w4 = open(urls, encoding="utf-8").readline().split("\t")[1].strip()
    destino = "https://www.jota.info/trabalho/fim-da-6x1-dino-mira-em-lacunas-faz-ajustes"
    mapa = {w4: (302, destino, ""), destino: (200, "", pagina("Fim da 6x1: Dino mira em lacunas, faz ajustes, mas "
                                                               "não muda principais pontos da emenda"))}
    _, out, _ = rodar_resolver(["Fim da 6x1: Dino mira em lacunas, faz ajustes, mas não muda principais pontos da "
                                "emenda [L1]"], mapa, ["--sem-historico"])
    assert out == ["OK\tFim da 6x1: Dino mira em lacunas, faz ajustes, mas não muda principais pontos da emenda\t"
                   + destino], out


# ------------------------------------------------------------ versiculo
def rodar_versiculo(data, respostas):
    antigo_f, antigo_p, antigo_t, antigo_argv = versiculo.fetch, versiculo.PAUSA_REPETICAO, versiculo.TMP, sys.argv
    pedidos = []

    def falso(url, timeout=15):
        pedidos.append(url)
        for chave, r in respostas.items():
            if chave in url:
                return r.pop(0) if isinstance(r, list) else r
        return 0, ""
    versiculo.fetch, versiculo.PAUSA_REPETICAO, versiculo.TMP = falso, 0, TMPDIR
    sys.argv = ["versiculo.py", "--data", data, "--dia", "320"]
    try:
        codigo, out = saida_de(versiculo.main)
    finally:
        versiculo.fetch, versiculo.PAUSA_REPETICAO, versiculo.TMP, sys.argv = antigo_f, antigo_p, antigo_t, antigo_argv
    return codigo, out.splitlines(), pedidos


DV = ('<title>Versículo do dia 16 de novembro de 2026</title><meta property="og:title" content="João 16:28 - ARC">'
      '<meta name="description" content="Saí do Pai e vim ao mundo; outra vez, deixo o mundo e vou para o Pai.">'
      + " " * 2100)


@teste
def versiculo_sonda_e_linha():
    # segunda-feira, YouVersion com anti-bot: nao_tentada (esperado), DailyVerses ok
    codigo, out, _ = rodar_versiculo("2026-11-16", {"bible.com": (403, "Client Challenge"), "dailyverses": (200, DV)})
    assert codigo == 0 and len(out) == 2, out
    assert out[0] == ("VERSICULO ok | João 16:28 (ARC) | Saí do Pai e vim ao mundo; outra vez, deixo o mundo e vou "
                      "para o Pai. | fonte: DailyVerses.net | 2026-11-16"), out[0]
    assert json.loads(out[1][len("SOURCE_STATUS "):]) == {"youversion": "nao_tentada", "dailyverses": "ok"}
    v = json.load(open(os.path.join(TMPDIR, "versiculo.json"), encoding="utf-8"))
    for k in ("ok", "fonte", "referencia", "versao", "texto", "data_pagina", "url", "tentativas"):
        assert k in v, k
    fs = json.load(open(os.path.join(TMPDIR, "fontes_status.json"), encoding="utf-8"))
    assert fs["youversion"]["status"] == "nao_tentada" and fs["youversion"]["detalhe"].startswith("sonda_falhou (esperado)")
    # terca: sem sonda; DailyVerses com http 0 transitorio -> nova tentativa
    codigo, out, pedidos = rodar_versiculo("2026-11-17", {"dailyverses": [(0, ""), (200, DV.replace("16 de", "17 de"))]})
    assert codigo == 0 and not [p for p in pedidos if "bible.com" in p] and len(pedidos) == 2, pedidos
    fs = json.load(open(os.path.join(TMPDIR, "fontes_status.json"), encoding="utf-8"))
    assert fs["youversion"]["detalhe"] == "sonda semanal (so as segundas)"
    # tudo falhou: uma linha ok=false e dailyverses falha
    codigo, out, _ = rodar_versiculo("2026-11-18", {"dailyverses": (500, "")})
    assert codigo == 1 and out[0].startswith("VERSICULO ok=false | ") and "WebSearch" in out[0], out
    assert json.loads(out[1][len("SOURCE_STATUS "):]) == {"youversion": "nao_tentada", "dailyverses": "falha"}


def main():
    falhas = 0
    for f in RESULTADOS:
        try:
            f()
            print("OK      %s" % f.__name__)
        except Exception:
            falhas += 1
            print("FALHOU  %s\n%s" % (f.__name__, traceback.format_exc()))
    shutil.rmtree(TMPDIR, ignore_errors=True)
    print("\n%s (%d testes, %d falha(s))" % ("OK" if not falhas else "FALHOU", len(RESULTADOS), falhas))
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
