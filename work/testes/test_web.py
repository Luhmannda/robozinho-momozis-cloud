#!/usr/bin/env python3
# =====================================================================
# test_web.py — testes do grupo WEB (sem pytest, sem rede):
#   repeticao.py (identidade numerica, "-conteudo", datas/milhar; execucao de
#   16/11 contra o historico ate 13/11), coleta_web.py (nova tentativa, C7,
#   saida compacta, PROMO/REPETIDA?, SOURCE_STATUS; linha-fina cortada ou com
#   propaganda -> resumo_truncado, volta 3), resolver_jota.py (saltos sem -L,
#   RECUSADO, JA_PUBLICADA, L<n>, BLOQUEADO), jota_extrair.py (descadastro x
#   manchete: regra unica com o resolver, volta 3) e versiculo.py (sonda do
#   YouVersion, linha unica, SOURCE_STATUS).
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
# sem rede: pedido que o teste nao simulou vira http 0 sem pausa (a API do ConJur cai no fallback HTML)
coleta_web._fetch1 = lambda url, timeout: (0, "", False)
coleta_web.PAUSA_REPETICAO = 0
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


@teste
def repeticao_falsos_positivos_e_ja_saiu():
    """(21/11, achados 40/41) Pares reais do historico. 18/11: 'Camara aprova credito de R$ 6,5 bi...' (MP 1.397)
    era 'repetida' do credito de 18,5 bi de 11/11 ('6,5' e '18,5' viravam '5'; o slug 'credito-18-5-bi' somava
    numeros). Agora: decimal num token so, numeros so do titulo, valor diferente veta, MP em qualquer posicao e
    identidade fraca; '6×1' = '6x1'. Os pares que nao sao a mesma materia continuam sem casar."""
    ti, t, p = repeticao.tokens_item, repeticao.tokens, repeticao.parecidas
    credito_1111 = ti("camara|plenario|credito-18-5-bi-exportadores|2026|2026-11-11",
                      "Câmara aprova crédito de 18,5 bi para exportadores afetados por novo tarifaço dos EUA")
    credito_1811 = t("Câmara aprova crédito de R$ 6,5 bi para ajudar exportadores atingidos pelo tarifaço dos EUA")
    assert not p(credito_1111, credito_1811) and repeticao.procurar(credito_1811, [("x", credito_1111)]) is None
    assert credito_1111.valores == {"18v5bi"} and credito_1811.valores == {"6v5bi"}
    # o mesmo valor (outra redacao) continua casando
    assert p(credito_1111, t("Câmara aprova crédito de 18,5 bilhões para exportadores afetados pelo tarifaço dos EUA"))
    assert repeticao.valores("R$ 300 milhões e R$ 1.200 mi; 6,50 bi") == {"300mi", "1200mi", "6v5bi"}
    assert repeticao.valores("R$ 2 tri, 1 trilhão, R$ 1 milhão e 3 bilhões") == {"2tr", "1tr", "1mi", "3bi"}
    # (rev2 R5) a unidade e a palavra inteira: titulos reais do historico que viravam valor ("mi" de minutos/militares,
    # "tr" de tribunais, "mi" do "mil" de milhar) e vetavam a semelhanca com outra redacao do mesmo fato
    for s in ("Limite de 30 minutos para comunicação de sinistro é abusivo, decide STJ",
              "STM mantém condenação de 7 militares por 'chá de manta' que fez soldado perder baço",
              "Quatro ministros do STF mandam devolucao de penduricalhos por juizes de 7 tribunais",
              "STJ multa advogados em R$ 20 mil por uso de prompt injection em petição", "5 ministros", "3 trimestres"):
        assert repeticao.valores(s) == frozenset(), s
    assert p(t("Limite de 30 minutos para comunicação de sinistro é abusivo, decide STJ"),
             t("STJ decide que limite de 30 minutos para comunicar sinistro é abusivo"))
    # MP em qualquer posicao: identidade fraca (numero diferente nunca casa)
    assert t("Câmara aprova crédito de R$ 6,5 bi (MP 1.397/26)").ident == ("mpv", "1397")
    assert not p(t("Senado aprova MP 1.397 sobre crédito a exportadores do tarifaço"),
                 t("Senado aprova MP 1.399 sobre crédito a exportadores do tarifaço"))
    # 6×1 = 6x1; decimal = um token
    assert "6x1" in t("STF vai reiniciar julgamento sobre fim da escala 6×1") and "6x1" in t("escala 6 x 1")
    assert "6v5" in t("crédito de 6,5") and not {"6", "5"} & t("crédito de 6,5")
    # pares negativos do historico (opiniao x noticia do 6x1; dois julgados distintos de ICMS/PIS/Cofins)
    assert not p(ti("jota|opiniao|fim-da-escala-6x1-sera-mesmo|2026|2026-11-18", "Fim da escala 6X1: será mesmo?"),
                 ti("conjur|noticia|stf-vai-reiniciar-julgamento-sobre-fim-da-escala-6|2026|2026-11-15",
                    "STF vai reiniciar julgamento sobre fim da escala 6×1 em plenário presencial"))
    assert not p(ti("migalhas|noticia|stj-nega-excluir-icms-pis-cofins-volume|2026|2026-10-13",
                    "STJ nega excluir ICMS do PIS e da Cofins calculados por volume"),
                 ti("migalhas|noticia|stj-icms-pis-cofins|2026|2026-10-14",
                    "STJ: ICMS não gera créditos de PIS e Cofins no regime não cumulativo"))
    # a execucao de 16/11 continua com as mesmas 2 repetidas (nenhum falso positivo novo)
    rep, dup = checar_local(dict(ler("execucao-1611.json"), items=ler("execucao-1611.json")["items"] + JOTA_REPETIDOS),
                            historico())
    assert len(rep) == 2 and not dup, (rep, dup)
    # JA SAIU: Midia e Fofoquinha das 2 ultimas edicoes, a mais recente primeiro, uma linha por edicao
    h = [{"execution_id": "2026-11-18-7h", "date": "2026-11-18", "items": [
            {"categoria": "Mídia", "titulo": "Fim da 6x1: Dino dá mais prazo para manifestações", "fonte": "JOTA"}]},
         {"execution_id": "2026-11-19-7h", "date": "2026-11-19", "items": [
            {"categoria": "Mídia", "titulo": "CNJ lança painel de precatórios", "fonte": "JOTA"},
            {"categoria": "Planalto/Legislação", "titulo": "Lei nº 15.530"},
            {"categoria": "Fofoquinha", "titulo": "Diretor da PF entrega a Fachin relatórios " + "x" * 90,
             "fonte": "Folha de S.Paulo (via JOTA)"}]},
         {"execution_id": "2026-11-20-7h", "date": "2026-11-20", "items": [
            {"categoria": "Mídia", "titulo": "Hoje", "fonte": "ConJur"}]}]
    linhas = repeticao.ja_saiu(h, ignorar_exec_id="2026-11-20-7h")
    assert len(linhas) == 2 and linhas[0].startswith("JA SAIU 19/11 — Mídia: CNJ lança painel de precatórios [JOTA]"), linhas
    assert "| Fofoquinha: Diretor da PF entrega a Fachin relatórios" in linhas[0] and "[Folha de S.Paulo]" in linhas[0]
    assert "…" in linhas[0] and "Lei nº 15.530" not in linhas[0] and linhas[1].startswith("JA SAIU 18/11 — Mídia: Fim")


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


def pagina_fixture(nome):
    assert os.path.exists(os.path.join(FIX, nome)), "fixture ausente: git add work/testes/fixtures/web/%s" % nome
    with open(os.path.join(FIX, nome), encoding="utf-8") as f:
        return f.read()


C1_URL = "https://conjur.com.br/2026-nov-16/stj-busca-esclarecer-limites-para-invasao-de-domicilio-por-guardas-municipais/"
C1_TIT = "STJ busca esclarecer limites para invasão de domicílio por guardas municipais"
C15_URL = "https://conjur.com.br/2026-nov-16/varas-das-garantias-ja-alcancam-todo-o-estado-de-sao-paulo/"
C15_TIT = "Varas das Garantias já alcançam todo o estado de São Paulo"


@teste
def coleta_resumo_truncado_e_propaganda():
    """Volta 3 (P5): a linha-fina do ConJur (og:description da propria materia)
    veio cortada no meio da palavra (c1 de 17/11: '... fazem a invasão de
    domic', e o e-mail saiu com 'domic.') ou com propaganda e o '[…]' do
    WordPress (c15: '... (clique aqui para garantir o seu exemplar). Capa da
    edição ... das […]'). Agora: propaganda fora; resumo cortado completado pela
    propria pagina (ja baixada; nenhum pedido a mais) ou, sem como completar,
    marcado com resumo_truncado (e sem o pedaco de palavra)."""
    rp = coleta_web.resumo_da_pagina
    # c1 real: a pagina nao tem o texto completo -> sem o pedaco "domic", marcado
    r, trunc = rp(pagina_fixture("conjur-c1-1711.html"), C1_TIT, C1_URL)
    assert trunc is True, (r, trunc)
    assert r == ("STJ vai avaliar quais limites devem ser observados para casos em que guardas municipais "
                 "fazem a invasão de"), r
    # c15 real: propaganda e legenda fora; a frase cortada e completada pelo paragrafo da pagina
    r, trunc = rp(pagina_fixture("conjur-c15-1711.html"), C15_TIT, C15_URL)
    assert (r, trunc) == ("Em pouco mais de um ano, o Judiciário paulista criou 13 varas regionais das garantias, "
                          "distribuídas pelas dez regiões administrativas judiciárias (RAJs).", False), (r, trunc)

    def pag(desc, *pars):
        return ('<meta property="og:description" content="%s" />' % desc
                + "".join("<p>%s</p>" % p for p in pars))
    # linha-fina normal do ConJur (sem ponto final, palavra inteira): nao muda
    for desc, tit in [("TST reconheceu que a atividade do agente de inspeção não se enquadra nas funções de "
                       "segurança patrimonial ou pessoal da NR-16", "Agente de inspeção não tem direito a adicional"),
                      ("Ministro viu atividade política e proibiu visitas de senadores Rogério Marinho (PL-RN)",
                       "Alexandre nega pedido de Bolsonaro"),
                      ("STF decidiu que lei de Nova Serrana (MG) é inconstitucional", "STF anula lei"),
                      ("Tribunal avalia se benefícios fiscais valem quando o voto de qualidade decidiu decadência",
                       "STJ julga alcance de benefício do Carf em voto de qualidade sobre decadência")]:
        assert rp(pag(desc, "Corpo da matéria com decadências e pagamentos diversos."), tit,
                  "https://conjur.com.br/2026-nov-16/x/") == (desc, False), desc
    # palavra cortada que a pagina completa (o paragrafo comeca com a linha-fina)
    assert rp(pag("O STF decidiu que a lei é inconstitucional e mandou o caso de volta ao tribu",
                  "O STF decidiu que a lei é inconstitucional e mandou o caso de volta ao tribunal de origem. "
                  "Outro trecho."), "STF anula lei", "https://conjur.com.br/2026-nov-16/stf-anula-lei-municipal/") \
        == ("O STF decidiu que a lei é inconstitucional e mandou o caso de volta ao tribunal de origem.", False)
    # "[…]", "[...]", "..." do fim sem paragrafo que complete: marcado, sem o marcador
    for fim in (" […]", " [&hellip;]", " [...]", "...", "…"):
        r, trunc = rp(pag("Tribunal manteve a condenação dos réus pelos crimes de" + fim), "Tribunal mantém",
                      "https://conjur.com.br/2026-nov-16/tribunal-mantem-condenacao/")
        assert (r, trunc) == ("Tribunal manteve a condenação dos réus pelos crimes de", True), (fim, r, trunc)
    # propaganda conhecida no meio da linha-fina: sai
    r, trunc = rp(pag("Livro analisa a reforma tributária (clique aqui para garantir o seu exemplar). "
                      "Autores debatem o IBS"), "Livro analisa reforma", "https://conjur.com.br/2026-nov-16/livro/")
    assert (r, trunc) == ("Livro analisa a reforma tributária. Autores debatem o IBS", False), (r, trunc)
    # sem pagina (ou sem og:description): vazio, como antes; so propaganda/marcador: vazio
    assert rp("", "Qualquer", "https://conjur.com.br/2026-nov-16/q/") == ("", False)
    assert rp(pag("[…]", "Primeiro parágrafo da matéria. Outro."), "Q", "https://conjur.com.br/2026-nov-16/q/") == ("", False)
    assert rp(pag("A versão impressa está à venda na Livraria ConJur (clique aqui para garantir o seu exemplar)."),
              "Q", "https://conjur.com.br/2026-nov-16/q/") == ("", False)
    # pela coleta: o c1 e o c15 no JSON e no indice
    paginas = {u: (200, "") for u in coleta_web.URLS_CONJUR.values()}
    paginas[coleta_web.URLS_CONJUR["noticia"]] = (200, "".join(
        '<h2 class="conjur-posts-tipo-titulo"><a href="%s">%s</a></h2>' % x
        for x in ((C1_URL, C1_TIT), (C15_URL, C15_TIT))))
    paginas[C1_URL] = (200, pagina_fixture("conjur-c1-1711.html"))
    paginas[C15_URL] = (200, pagina_fixture("conjur-c15-1711.html"))
    # 2a pagina da listagem (21/11: paginada ate o dia anterior ao inicio da janela): so uma noticia de 15/11
    pg2 = coleta_web.URL_CONJUR_PG % 2
    paginas[pg2] = (200, '<h2 class="conjur-posts-tipo-titulo"><a href="https://conjur.com.br/2026-nov-15/velha/">'
                         'Velha</a></h2>')
    pedidos = []
    antigo = coleta_web.fetch_many

    def falso(urls):
        pedidos.extend(urls)
        return {u: paginas[u] for u in urls}
    coleta_web.fetch_many = falso
    try:
        inicio = datetime.fromisoformat("2026-11-16T07:05:00-03:00")
        fim = datetime.fromisoformat("2026-11-17T07:05:00-03:00")
        out = coleta_web.conjur(inicio, fim, fim.replace(day=16, hour=7), set())
    finally:
        coleta_web.fetch_many = antigo
    assert sorted(pedidos) == sorted(list(coleta_web.URLS_CONJUR.values()) + [pg2, C1_URL, C15_URL]), pedidos
    assert out["via"] == "html" and out["completa"] and out["paginas"] == 2, out
    it = {i["url"]: i for i in out["itens"]}
    # (21/11) a linha-fina cortada ("... fazem a invasao de") sem paragrafo que a complete vira o lead da materia
    # (verbatim, ate o fim de frase): 3a Secao e HC 967.966 estavam na pagina ja baixada
    assert "resumo_truncado" not in it[C1_URL] and it[C1_URL]["resumo_origem"] == "lead", it[C1_URL]
    assert it[C1_URL]["resumo"].startswith("A 3ª Seção do Superior Tribunal de Justiça precisa estabelecer") \
        and it[C1_URL]["resumo"].endswith(".") and len(it[C1_URL]["resumo"]) <= coleta_web.MAX_COMPLEMENTO
    assert "HC 967.966" in it[C1_URL]["lead"] and it[C1_URL]["ficha"] == "STJ · 3ª Seção · HC 967.966", it[C1_URL]
    assert "resumo_truncado" not in it[C15_URL] and "clique aqui" not in it[C15_URL]["resumo"]
    linhas = coleta_web.imprimir([out], inicio, fim, fim.replace(day=16, hour=7))
    c1 = [l for l in linhas if C1_TIT in l]
    assert c1 and "[STJ · 3ª Seção · HC 967.966]" in c1[0] and "fazem a invasão de…" not in c1[0], c1
    # sem o lead (pagina sem paragrafo): a marca de corte de sempre, e o indice termina em "…"
    sem_corpo = pagina_fixture("conjur-c1-1711.html").split("<p>")[0]
    it2 = {"tipo": "noticia", "titulo": C1_TIT, "url": C1_URL}
    it2["resumo"], it2["resumo_truncado"] = coleta_web.resumo_da_pagina(sem_corpo, C1_TIT, C1_URL)
    coleta_web.enriquecer(it2, sem_corpo, "conjur")
    assert it2["resumo_truncado"] is True and it2["resumo"].endswith("fazem a invasão de") and "lead" not in it2
    # Migalhas: a linha-fina da listagem passa pela mesma limpeza (pagina ja baixada)
    mu = "https://www.migalhas.com.br/quentes/445566/stj-julga-tema"
    mu2 = "https://www.migalhas.com.br/quentes/445567/tst-mantem-multa"
    listagem = "".join('<article><a href="%s"></a><h2 class="topico__header">%s</h2><h3 class="topico__body">%s</h3>'
                       '</article>' % x for x in (
                           (mu, "STJ julga tema", "A 2ª seção do STJ decidiu que o prazo prescricional conta da..."),
                           (mu2, "TST mantém multa", "Para o colegiado, a multa é devida.")))
    pag_m = ('<meta property="article:published_time" content="2026-11-16T10:00:00-03:00">'
             "<p>A 2ª seção do STJ decidiu que o prazo prescricional conta da ciência do dano. Outro parágrafo.</p>")
    antigo_n, antigo_m = coleta_web.fetch_n, coleta_web.fetch_many
    coleta_web.fetch_n = lambda url, *a, **k: (200, listagem, 1)
    coleta_web.fetch_many = lambda urls: {u: (200, pag_m) for u in urls}
    try:
        out = coleta_web.migalhas(inicio, fim, fim.replace(day=16, hour=7), set())
    finally:
        coleta_web.fetch_n, coleta_web.fetch_many = antigo_n, antigo_m
    it = {i["url"]: i for i in out["itens"]}
    assert it[mu]["resumo"] == "A 2ª seção do STJ decidiu que o prazo prescricional conta da ciência do dano." \
        and "resumo_truncado" not in it[mu], it[mu]
    assert it[mu2]["resumo"] == "Para o colegiado, a multa é devida." and "resumo_truncado" not in it[mu2], it[mu2]


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


# ------------------------------------------------------------ cobertura de ConJur/Migalhas, LEGIN e indice (21/11)
J2011 = (datetime.fromisoformat("2026-11-19T07:07:20-03:00"), datetime.fromisoformat("2026-11-20T07:07:04-03:00"))


def _janela(inicio, fim):
    from datetime import timedelta
    return inicio, fim, fim - timedelta(hours=24)


class Rede:
    """fetch_n/fetch_many falsos: url -> (codigo, corpo) por funcao; registra os pedidos."""
    def __init__(self, resposta):
        self.resposta, self.pedidos = resposta, []

    def __enter__(self):
        self.antigos = coleta_web.fetch_n, coleta_web.fetch_many
        coleta_web.fetch_n = lambda url, *a, **k: self._um(url) + (1,)
        coleta_web.fetch_many = lambda urls: {u: self._um(u) for u in urls}
        return self

    def _um(self, url):
        self.pedidos.append(url)
        r = self.resposta(url)
        return r if r else (404, "")

    def __exit__(self, *a):
        coleta_web.fetch_n, coleta_web.fetch_many = self.antigos


@teste
def coleta_conjur_pela_api():
    """(21/11, achado 10/13A) ConJur pela WP REST API do dominio: a janela inteira numa requisicao (41 posts em 20/11
    contra 30 lidos), hora exata (date_gmt), tipo pelo class_list (estudio = PROMO), linha-fina (yoast), lead, ficha e
    nota oficial do corpo — sem abrir pagina de materia; so as paginas das opinioes do indice, para o autor (o meta
    author e o editor). Fixture: recorte real da resposta de 20/11."""
    api = open(os.path.join(FIX, "conjur-api-2011.json"), encoding="utf-8").read()
    art = pagina_fixture("conjur-artigo-c19-2011.html")
    inicio, fim = J2011[0], datetime.fromisoformat("2026-11-20T16:00:00-03:00")   # inclui o post do Estudio
    with Rede(lambda u: (200, api) if "/wp-json/" in u else (200, art)) as rede:
        out = coleta_web.conjur(*_janela(inicio, fim), set())
    api_ped = [p for p in rede.pedidos if "/wp-json/" in p]
    assert len(api_ped) == 1 and "after=2026-11-19T01:07:20" in api_ped[0] and "_fields=" in api_ped[0], api_ped
    assert len(rede.pedidos) == 3 and all("/wp-json/" in p or "sequestro-de-bens" in p or "tema-222" in p
                                          for p in rede.pedidos), rede.pedidos       # so as 2 opinioes
    assert out["via"] == "api" and out["http"] == {"api": 200} and out["cobertura"] == "completa", out
    it = {i["titulo"][:20]: i for i in out["itens"]}
    assert [i["tipo"] for i in out["itens"]][-2:] == ["artigo", "coluna"]
    assert it["Livros sobre advocac"]["situacao"] == "PROMO" and it["Livros sobre advocac"]["promo"] == "estudio"
    stf = it["Supremo vai julgar v"]
    assert stf["quando"] == datetime.fromisoformat("2026-11-19T21:18:47-03:00") and stf["situacao"] == "NOVA"
    assert stf["ficha"] == "STF · Plenário virtual · Tema 1.499 · vinculante" and stf["nota_oficial"] == "STF", stf
    assert stf["resumo"].startswith("Controvérsia sobre") and stf["lead"].startswith("O Supremo Tribunal Federal vai")
    assert it["Com empate, STJ mant"]["ficha"] == "STJ · 6ª Turma"
    assert it["Presidente assina de"]["nota_oficial"] == "Presidência"
    assert it["Sequestro de bens: o"]["autor"] == "Murilo Marques"            # nunca "Marcos Pereira" (editor)
    # API fora (http 404): a listagem HTML, e o motivo vai ao cabecalho e ao detalhe do status
    listagem = '<h2 class="conjur-posts-tipo-titulo"><a href="https://conjur.com.br/2026-nov-18/velha/">V</a></h2>'
    with Rede(lambda u: (404, "") if "/wp-json/" in u else (200, listagem)) as rede:
        out2 = coleta_web.conjur(*_janela(*J2011), set())
    assert out2["via"] == "html" and out2["api"] == {"http": 404, "motivo": "http=404"}, out2
    assert "via listagem HTML (API: http=404)" in coleta_web.status_fontes([out2])["conjur"][1]
    # resposta 200 que nao e lista de posts (pagina de bloqueio): tambem cai no HTML
    with Rede(lambda u: (200, "<html>bloqueado</html>") if "/wp-json/" in u else (200, listagem)):
        assert coleta_web.conjur(*_janela(*J2011), set())["via"] == "html"


@teste
def coleta_conjur_api_class_list_objeto():
    """(rev2 R7) O WordPress serializa o class_list com buracos (array_unique/filter) como objeto {"0": ..., "3": ...}:
    o tipo sai dos valores — antes todo post virava noticia (artigo/coluna no meio das noticias, Estudio sem PROMO)."""
    posts = json.load(open(os.path.join(FIX, "conjur-api-2011.json"), encoding="utf-8"))
    for p in posts:
        p["class_list"] = {str(n * 2): c for n, c in enumerate(p["class_list"])}
    api, art = json.dumps(posts), pagina_fixture("conjur-artigo-c19-2011.html")
    inicio, fim = J2011[0], datetime.fromisoformat("2026-11-20T16:00:00-03:00")
    with Rede(lambda u: (200, api) if "/wp-json/" in u else (200, art)):
        out = coleta_web.conjur(*_janela(inicio, fim), set())
    tipos = {i["titulo"][:20]: (i["tipo"], i["situacao"]) for i in out["itens"]}
    assert tipos["Sequestro de bens: o"] == ("artigo", "NOVA") and tipos["Tema 222 do TST: nem"][0] == "coluna", tipos
    assert tipos["Livros sobre advocac"] == ("noticia", "PROMO"), tipos           # tipos-estudio
    assert [i["tipo"] for i in out["itens"]][-2:] == ["artigo", "coluna"]
    # valor que nao e texto no class_list nao derruba o item
    posts[0]["class_list"] = {"0": None, "1": 7, "2": "tipos-artigos"}
    with Rede(lambda u: (200, json.dumps(posts[:1])) if "/wp-json/" in u else (200, art)):
        assert coleta_web.conjur(*_janela(inicio, fim), set())["itens"][0]["tipo"] == "artigo"


@teste
def coleta_conjur_api_sem_posts_utilizaveis():
    """(rev2 R2) API 200 com lista vazia ou so posts sem link/date_gmt (campo renomeado, _fields ignorado): antes 0
    itens sem fallback e o ConJur 'falha' no dia; agora a listagem HTML, com o motivo no cabecalho e no status."""
    posts = json.load(open(os.path.join(FIX, "conjur-api-2011.json"), encoding="utf-8"))
    art = pagina_fixture("conjur-artigo-c19-2011.html")
    inicio, fim = J2011[0], datetime.fromisoformat("2026-11-20T16:00:00-03:00")
    listagem = _h2("2026-nov-19/b/", "Notícia da listagem")
    meta = '<meta property="article:published_time" content="2026-11-19T12:00:00-03:00">'
    sem_campos = [{k: v for k, v in p.items() if k not in ("link", "date_gmt")} for p in posts]
    for resposta in ("[]", json.dumps(sem_campos), json.dumps([dict(p, date_gmt=None) for p in posts])):
        with Rede(lambda u: (200, resposta) if "/wp-json/" in u else (200, listagem if u.endswith("/noticias/")
                                                                       else meta)) as rede:
            out = coleta_web.conjur(*_janela(*J2011), set())
        assert out["via"] == "html" and out["api"] == {"http": 200, "motivo": "API sem posts utilizáveis"}, out
        assert [i["titulo"] for i in out["itens"]] == ["Notícia da listagem"] and out["itens"][0]["situacao"] == "NOVA"
        assert any(coleta_web.URLS_CONJUR["noticia"] == p for p in rede.pedidos)
        assert "via listagem HTML (API: API sem posts utilizáveis)" in coleta_web.status_fontes([out])["conjur"][1]
        assert any("via html (API: API sem posts utilizáveis)" in l for l in coleta_web.imprimir([out],
                                                                                                 *_janela(*J2011)))
    # parte dos posts sem link: os outros valem (via API), e a contagem fica no JSON
    with Rede(lambda u: (200, json.dumps(sem_campos[:2] + posts[2:])) if "/wp-json/" in u else (200, art)):
        out = coleta_web.conjur(*_janela(inicio, fim), set())
    assert out["via"] == "api" and out["api_descartados"] == 2 and len(out["itens"]) == len(posts) - 2, out


def _h2(url, tit="T"):
    return '<h2 class="conjur-posts-tipo-titulo"><a href="https://conjur.com.br/%s">%s</a></h2>' % (url, tit)


@teste
def coleta_conjur_html_paginado():
    """Fallback HTML (achado 10): noticias paginadas ate o dia anterior ao inicio da janela; a 3a pagina nao e pedida
    quando a 2a ja cruza o inicio; pagina repetida (armadilha /page/N/) para o laco com cobertura parcial; teto e
    http != 200 tambem; o AVISO vai ao indice e o detalhe ao status."""
    vazio = {coleta_web.URLS_CONJUR["artigo"]: (200, ""), coleta_web.URLS_CONJUR["coluna"]: (200, "")}
    pg = coleta_web.URL_CONJUR_PG
    p1 = _h2("2026-nov-20/a/") + _h2("2026-nov-19/b/")
    p2 = _h2("2026-nov-19/c/") + _h2("2026-nov-18/d/")
    paginas = dict(vazio, **{coleta_web.URLS_CONJUR["noticia"]: (200, p1), pg % 2: (200, p2),
                             pg % 3: (200, _h2("2026-nov-17/e/"))})
    meta = '<meta property="article:published_time" content="2026-11-19T12:00:00-03:00">'
    with Rede(lambda u: paginas.get(u) or (200, meta)) as rede:
        out = coleta_web.conjur_html(*_janela(*J2011), set())
    assert pg % 2 in rede.pedidos and pg % 3 not in rede.pedidos, rede.pedidos
    assert out["completa"] and out["cobertura"] == "completa" and out["paginas"] == 2, out
    sit = {i["url"].split("/")[-2]: (i["situacao"], i.get("pagina")) for i in out["itens"]}
    assert sit["c"] == ("NOVA", 2) and sit["d"] == ("FORA", 2), sit
    # a 2a pagina devolve a 1a (formato de URL mudou): para, parcial, AVISO
    paginas[pg % 2] = (200, p1.replace("nov-19/b", "nov-19/b"))
    with Rede(lambda u: paginas.get(u) or (200, meta)):
        out = coleta_web.conjur_html(*_janela(*J2011), set())
    assert out["cobertura"] == "parcial" and out["sem_url_nova"] == 2, out
    linhas = coleta_web.imprimir([out], *_janela(*J2011))
    aviso = [l for l in linhas if l.startswith("AVISO: cobertura parcial do ConJur")]
    assert aviso and "a página 2 repetiu a anterior" in aviso[0] and "verification_notes" in aviso[0], linhas
    assert "parcial: leitura incompleta" in coleta_web.status_fontes([out])["conjur"][1]
    assert coleta_web.status_fontes([out])["conjur"][0] == "ok"     # a lista fechada do source_status nao tem "parcial"
    # teto: todas as paginas na janela
    antigo = coleta_web.MAX_PAGINAS_CONJUR
    coleta_web.MAX_PAGINAS_CONJUR = 2
    paginas[pg % 2] = (200, _h2("2026-nov-19/x/"))
    try:
        with Rede(lambda u: paginas.get(u) or (200, meta)) as rede:
            out = coleta_web.conjur_html(*_janela(*J2011), set())
    finally:
        coleta_web.MAX_PAGINAS_CONJUR = antigo
    assert out["cobertura"] == "parcial" and pg % 3 not in rede.pedidos and out["paginas"] == 2, out
    assert any("teto de 2 página(s)" in l for l in coleta_web.imprimir([out], *_janela(*J2011)))
    # http 500 na 2a pagina: as lidas valem, parcial
    paginas[pg % 2] = (500, "")
    with Rede(lambda u: paginas.get(u) or (200, meta)):
        out = coleta_web.conjur_html(*_janela(*J2011), set())
    assert out["http_pagina"] == {"pagina": 2, "http": 500} and out["cobertura"] == "parcial"
    assert any("http=500 na página 2" in l for l in coleta_web.imprimir([out], *_janela(*J2011)))


@teste
def coleta_migalhas_paginado():
    """(achado 10) Migalhas ?pagina=N: para no selo de data anterior ao dia do inicio da janela (a p. 4 nao e pedida);
    selo anterior = FORA sem abrir a materia; PROMO e 'Especialista aponta' so contados. Fixture: recorte real das
    paginas 1, 2 e 7 de 20/11."""
    pags = ler("migalhas-listagem-2011.json")["paginas"]
    abertas = []

    def resp(u):
        if "/quentes?pagina=" in u or u.endswith("/quentes"):
            n = u.rsplit("=", 1)[1] if "=" in u else "1"
            return (200, pags[n]) if n in pags else (200, "")
        abertas.append(u)
        return 200, '<meta property="article:published_time" content="2026-11-19T15:00:00-03:00">'
    with Rede(resp) as rede:
        out = coleta_web.migalhas(*_janela(*J2011), set())
    assert not [p for p in rede.pedidos if "pagina=4" in p] and out["paginas"] == 3 and out["completa"], out
    sit = {i["url"].split("/")[4]: i["situacao"] for i in out["itens"]}
    fora = [k for k, v in sit.items() if v == "FORA"]
    assert len(fora) == 3 and not [a for a in abertas if a.split("/")[4] in fora], (sit, abertas)   # selo 18/11
    assert len(abertas) == 6 and out["cobertura"] == "completa", abertas     # 2 + 4 (as de 18/11 nao)
    coleta_web.marcar_promo_e_repetidas([out], [])
    promo = sorted(i["titulo"][:25] for i in out["itens"] if i["situacao"] == "PROMO")
    assert promo == ["Aula ao vivo organiza a r"], promo                 # 'Especialista aponta' e de 18/11 (FORA)
    for t in ("Especialista aponta condições para regularidade do stablecoin sandwich",
              "Especialista: GTA 6 amplia debate", "Advogada alerta escolas sobre bullying",
              "Nova jornada amplia disputas por horas extras e folgas, alerta advogado"):
        assert coleta_web.OPINIAO_DISFARCADA.search(t), t
    for t in ("Aula ao vivo organiza a reta final de estudos para 1ª Fase 48º Exame",
              'OAB/RJ realiza "Feira de Estágios de 2026"', "AJER promove debate sobre a reforma",
              'Ingo Wolfgang participa do "XXVI Congresso de Direito"', "CropLife Brasil aborda defensivos em videocast",
              "Livros sobre advocacia criminal contemporânea e na literatura serão lançados em 26/11"):
        assert coleta_web.PROMO.search(t), t
    for t in ("Juiz decide na sexta-feira de manhã sobre prisão", "TJ-SP realiza mutirão na segunda-feira",
              "STF realiza audiência pública sobre a escala 6x1", "Advogado é preso suspeito de sequestrar namorada",
              "Professor é condenado por assédio"):
        assert not coleta_web.PROMO.search(t) and not coleta_web.OPINIAO_DISFARCADA.search(t), t
    for t in ("Juiz decide na sexta-feira de manhã sobre prisão", "TJ-SP realiza mutirão na segunda-feira",
              "STF realiza audiência pública sobre a escala 6x1", "Advogado é preso suspeito de sequestrar namorada",
              "Professor é condenado por assédio"):
        assert not coleta_web.eh_promo(t) and not coleta_web.eh_opiniao_disfarcada(t), t
    # pagina 2 sem URL nova (o site ignorou ?pagina=): para, parcial
    with Rede(lambda u: (200, pags["1"]) if "quentes" in u and "/quentes/" not in u else resp(u)):
        out = coleta_web.migalhas(*_janela(*J2011), set())
    assert out["sem_url_nova"] == 2 and out["cobertura"] == "parcial", out
    # site lento: o orcamento de tempo para as paginas seguintes (o aguardar_coleta espera ~90 s pelos 3 scripts)
    antigo = coleta_web.ORCAMENTO_PAGINACAO
    coleta_web.ORCAMENTO_PAGINACAO = -1
    try:
        with Rede(resp) as rede:
            out = coleta_web.migalhas(*_janela(*J2011), set())
    finally:
        coleta_web.ORCAMENTO_PAGINACAO = antigo
    assert out["orcamento"] == 2 and out["paginas"] == 1 and out["cobertura"] == "parcial", out
    assert any("site lento: parou antes da página 2" in l for l in coleta_web.imprimir([out], *_janela(*J2011)))


@teste
def coleta_promo_nao_esconde_julgado():
    """(rev2 R3) PROMO e opiniao disfarcada tiram o item do indice: nunca um julgado. live/podcast/videocast/webinario
    e feira so no inicio do titulo ou com verbo de evento; opiniao so com o verbo logo depois do sujeito no inicio (ou
    ', alerta advogado' no fim); nada com verbo de decisao, tribunal ou julgador. Os 991 titulos publicados ate 20/11
    (Midia, STJ/STF Noticias, Fofoquinha, Opiniao) nao viram PROMO nem opiniao; a propaganda real continua so contada."""
    julgados = ["Advogado pagará custas após Justiça apontar litigância predatória",
                "TSE: live de Bolsonaro no Alvorada configurou abuso de poder político",
                "Live de Bolsonaro foi abuso de poder, diz TSE", "Juiz anula prova obtida em podcast",
                "Advogado não pode ser preso por defender cliente em podcast, avalia STJ",
                "Feira de rua sem licença deve ser fechada, decide TJ-SP", "Justiça anula sorteio de vagas em creche",
                "Especialista: STF errou ao modular efeitos", "Advogado apontado como chefe de facção é condenado",
                "Advogados alertam que decisão do STJ muda cálculo de honorários",
                "Desembargador participa de live e é alvo de reclamação no CNJ"]
    for t in julgados:
        assert not coleta_web.eh_promo(t) and not coleta_web.eh_opiniao_disfarcada(t), t
    assert coleta_web.OPINIAO_DISFARCADA.search(julgados[0]) is None             # antes: "Advogado ... apontar"
    propaganda = ["Sorteio de livros para leitores do Migalhas", "Live debate a reforma tributária nesta quinta",
                  "Podcast do Migalhas conversa com tributarista", "Webinário gratuito discute LGPD",
                  "CropLife Brasil aborda endividamento do agro em episódio do videocast \"Caminhos do Agro\"",
                  "Escritório transmite ao vivo podcast sobre compliance",
                  "OAB/RJ realiza \"Feira de Estágios de 2026\" no dia 25/11", "Feira do livro jurídico abre inscrições",
                  "Biografia do criminalista Nélio Machado será lançada em 1º/12, no Rio",
                  "AJER promove debate sobre inclusão racial e ascensão de negros no Direito"]
    for t in propaganda:
        assert coleta_web.eh_promo(t), t
    opiniao = ["Advogado aponta impactos de inspeções do CNJ no mercado de precatórios",
               "Especialistas apontam riscos da tokenização de imóveis", "Professora avalia a nova lei de alimentos",
               "Pena maior pode equiparar homicídios culposo e doloso, alerta advogado",
               "Especialista: GTA 6 amplia debate sobre licenciamento digital e direitos dos gamers"]
    for t in opiniao:
        assert coleta_web.eh_opiniao_disfarcada(t), t
    # live/podcast/feira no meio do titulo, sem verbo de evento: nao e PROMO
    for t in ("Influenciador é investigado por declarações em live", "Município regula feira de artesanato"):
        assert not coleta_web.eh_promo(t), t
    # o historico publicado: nenhum titulo escondido
    pub = ler("titulos-publicados-ate-2011.json")["titulos"]
    assert sum(len(v) for v in pub.values()) == 991 and len(pub["Mídia"]) == 438
    escondidos = [(c, t) for c, ts in pub.items() for t in ts
                  if coleta_web.eh_promo(t) or coleta_web.eh_opiniao_disfarcada(t)]
    assert not escondidos, escondidos
    # de ponta a ponta: o julgado fica NOVA (com id no indice), a propaganda vira PROMO
    r = {"fonte": "migalhas", "itens": [{"situacao": "NOVA", "titulo": t, "url": "https://www.migalhas.com.br/quentes/"
                                         "%d/x" % n} for n, t in enumerate(julgados + propaganda + opiniao)]}
    coleta_web.marcar_promo_e_repetidas([r], [])
    sit = {i["titulo"]: i["situacao"] for i in r["itens"]}
    assert all(sit[t] == "NOVA" for t in julgados) and all(sit[t] == "PROMO" for t in propaganda + opiniao), sit


@teste
def coleta_lead_ficha_nota_autor():
    """(achado 16, 13B, lows 10) Das paginas ja baixadas: lead verbatim (2 paragrafos, fim de frase), ficha curta e
    segura (tribunal · orgao · processo/tema · vinculante; sem placar nem relator por regex), a nota oficial
    reproduzida ('Com informacoes da assessoria...', 'Informacoes: STF.') e o autor do artigo. Paginas reais."""
    lead, pars = coleta_web.lead_da_pagina(pagina_fixture("conjur-c1-1711.html"), "conjur")
    assert len(pars) == 2 and lead.startswith("A 3ª Seção do Superior Tribunal de Justiça") and lead.endswith(".")
    assert len(lead) <= coleta_web.MAX_LEAD and coleta_web.ficha_do_lead(C1_TIT, pars) == "STJ · 3ª Seção · HC 967.966"
    # Migalhas: so o corpo (div topico__materia), nao "Patrocinadores/Apoiadores" nem o CSS; "ADIn" vira ADI
    m = pagina_fixture("migalhas-468718-1711.html")
    lead, pars = coleta_web.lead_da_pagina(m, "migalhas")
    assert lead.startswith("Por unanimidade, o STF julgou constitucional") and "Apoiadores" not in lead, lead
    assert coleta_web.ficha_do_lead("STF valida lei que protege dados em ocorrências policiais", pars) == \
        "STF · Plenário · ADI 4.188"
    assert coleta_web.nota_oficial(m) == "STF"
    # negativos reais: o "empate" e do Carf (17/11 c12) e a 2a Turma e a do precedente (19/11 c9): fora da ficha
    _, pars = coleta_web.lead_da_pagina(pagina_fixture("conjur-c12-1711.html"), "conjur")
    f = coleta_web.ficha_do_lead("STJ julga alcance de benefício do Carf em voto de qualidade sobre decadência", pars)
    assert f == "STJ · 1ª Turma" and "empate" not in f.lower(), f
    _, pars = coleta_web.lead_da_pagina(pagina_fixture("conjur-c9-1911.html"), "conjur")
    assert coleta_web.ficha_do_lead("Execução de honorários deve aguardar compensação tributária, decide STJ",
                                    pars) == "STJ · 1ª Turma"
    # tribunal por extenso, Turma Recursal, Tema com repetitivo no paragrafo do tema
    pars = ["Com essa premissa, a 2ª Turma Recursal do Tribunal de Justiça de Santa Catarina absolveu uma indústria.",
            "A questão está em análise no Tema 1.422 dos recursos repetitivos, para formação de tese vinculante."]
    assert coleta_web.ficha_do_lead("Indústria é absolvida de crime ambiental", pars) == \
        "TJ-SC · 2ª Turma Recursal · Tema 1.422 · vinculante"
    assert coleta_web.ficha_do_lead("Lei nova", ["Texto sem tribunal nenhum, com mais de quarenta caracteres."]) == ""
    assert coleta_web.nota_oficial("<p>Com informações da assessoria de imprensa do TRF-3.</p>") == "TRF-3"
    assert coleta_web.nota_oficial("<p>Com informações da Agência Brasil.</p>") == ""
    art = pagina_fixture("conjur-artigo-c19-2011.html")
    assert 'name="author" content="Marcos Pereira"' in art and coleta_web.autor_da_pagina(art) == "Murilo Marques"
    assert coleta_web.autor_da_pagina('<p class="assinante-title"><a>A B</a></p><p class="assinante-title">C D</p>') \
        == "A B e C D"


def _res_indice():
    """coleta_web.json real de 20/11 (fixture recortada) com o que o indice novo usa."""
    res = ler("coleta_web-2011.json")
    for r in res:
        for i in r["itens"]:
            if isinstance(i.get("data"), str) and len(i["data"]) == 10:
                i["data"] = date.fromisoformat(i["data"])
            if isinstance(i.get("quando"), str) and i["quando"] not in ("None", ""):
                i["quando"] = datetime.fromisoformat(i["quando"])
    return res


@teste
def coleta_indice_relevancia_marcas_e_ruido():
    """(achado 11a, 40, 21/11) Indice de 20/11 (dados reais): concurso primeiro ([CONC]), [STJ], ficha e
    [ASSESSORIA X]; a mesma historia do dia numa linha (c3 + m10); fala/evento sem linha-fina; as 16 leis do PLN
    (creditos, LOA e LDO) numa linha de rotina (o e-mail nao muda: cada ref e citado); paginas seguintes so com titulo e so com termo
    de prova (o resto contado, o id continua valendo); JA SAIU no fim. E nao cresce: menos linhas que o de 20/11."""
    res = _res_indice()
    linhas = coleta_web.imprimir(res, *_janela(*J2011), ja_saiu=["JA SAIU 19/11 — Mídia: X [JOTA]"])
    txt = "\n".join(linhas)
    cj = linhas[linhas.index(next(l for l in linhas if l.startswith("\n== CONJUR"))) + 1:]
    nots = [l for l in cj if "|NOT] c" in l]
    assert nots[0].startswith("[NOVA|NOT] c1 |") and "[CONC]" in nots[0] and "[CONC]" in nots[1], nots[:2]
    assert any("Com empate, STJ mantém" in l and "[STJ]" in l for l in nots)
    c3 = next(l for l in nots if "] c3 |" in l)
    assert "(mesma história: m10 «Dino critica jornalismo" in c3 and "] m10 |" not in txt, c3
    c10 = next(l for l in nots if "] c10 |" in l)
    assert c10.endswith("Salomão defende papel da democracia para o desenvolvimento"), c10      # fala: sem linha-fina
    rot = [l for l in linhas if l.startswith("[NOVA] rotina — 16 lei(s)")]
    assert rot and "lei15531" in rot[0] and "lei15545" in rot[0] and "(DOU 19/11)" in rot[0], rot
    # (rev2 R9) altera a LOA/LDO (materia PLN): rotina, como no montador (antes: linha propria no indice)
    assert "lei15541" in rot[0] and "lei15534" in rot[0] and "] lei15541 |" not in txt and "] lei15531 |" not in txt
    ids = {i["id"] for r in res for i in r["itens"] if i.get("id")}
    assert {"lei%d" % n for n in range(15530, 15546)} <= ids                     # todos citaveis
    assert linhas[-2].startswith("\n== JA SAIU") and linhas[-1] == "JA SAIU 19/11 — Mídia: X [JOTA]"
    # paginas seguintes: so titulo, so com termo de prova, ate MAX_SEGUINTES_NO_INDICE; o resto contado
    mig = next(r for r in res if r["fonte"] == "migalhas")
    assuntos = ["usucapião", "alimentos", "falência", "tributos", "consumidor", "servidores", "licitação", "família",
                "improbidade", "execução", "trabalho"]
    for n in range(12):
        mig["itens"].append({"situacao": "NOVA", "pagina": 2, "url": "https://www.migalhas.com.br/quentes/9%d/x" % n,
                             "titulo": ("STJ define prescrição em ação de %s" % assuntos[n]) if n < 11
                             else "Gemidos e colchonete: juiz é afastado",
                             "quando": datetime(2026, 11, 19, 9, n, tzinfo=TZ)})
    for r in res:
        for i in r["itens"]:
            i.pop("id", None)
    linhas = coleta_web.imprimir(res, *_janela(*J2011))
    seg = [l for l in linhas if "STJ define prescrição em ação de" in l]
    assert len(seg) == coleta_web.MAX_SEGUINTES_NO_INDICE and not [l for l in seg if " — " in l], seg
    assert any(l.startswith("(+%d notícia(s) das páginas seguintes fora do índice" % (12 - coleta_web.MAX_SEGUINTES_NO_INDICE))
               for l in linhas), linhas[-6:]
    # tamanho: o indice de 20/11 (69 linhas, 13.255 bytes) nao cresce com o formato novo
    base = coleta_web.imprimir(_res_indice(), *_janela(*J2011))
    assert len(base) < 69 and len("\n".join(base).encode()) < 13255, (len(base), len("\n".join(base).encode()))


@teste
def coleta_rotina_igual_ao_montador():
    """(rev2 R9) O indice agrupa como rotina exatamente os atos que o montador poe no fim da secao: o item que o
    montar_email.resolver monta do ref (titulo + ementa) passa pelo montar_email.eh_rotina, e materia PLN e rotina. Antes
    a copia do padrao no coleta_web divergia: LOA/LDO (lei15530/15534/15541 de 20/11), credito de R$ e cargos em
    comissao ficavam numa linha propria no indice e iam ao fim no e-mail."""
    import montar_email
    res = _res_indice()
    leg = {"fonte": "legin", "http": 200, "listadas": 4, "itens": []}
    for n, ementa in enumerate(["Remaneja cargos em comissão e funções de confiança no Ministério da Fazenda.",
                                "Estima a receita e fixa a despesa da União para o exercício financeiro de 2027.",
                                "Promulga o Acordo de Cooperação Jurídica em Matéria Penal entre o Brasil e a Itália.",
                                "Dispõe sobre a duração normal do trabalho e o repouso semanal remunerado."]):
        leg["itens"].append({"situacao": "NOVA", "tipo": "Decreto", "tipo_chave": "decreto", "prefixo": "dec",
                             "numero": str(13180 + n), "data_ato": "19/11/2026", "dou": "19/11/2026",
                             "ementa": ementa, "url": "https://x/%d" % n, "chave": "planalto|decreto|%d" % (13180 + n)})
    res.insert(2, leg)
    res[0]["itens"].append(dict(res[0]["itens"][0], numero="15599", veto="Veto parcial nº 40", situacao="NOVA"))
    linhas = coleta_web.imprimir(res, *_janela(*J2011))
    agrupados = {x.strip(" ()").split(" ")[0] for l in linhas if " rotina — " in l for x in l.split(": ")[-1].split(", ")}
    ev = {i["id"]: dict(i, _fonte=r["fonte"]) for r in res for i in r["itens"] if i.get("id")}
    for ident, e in ev.items():
        if e["_fonte"] not in ("congresso_leis", "legin"):
            continue
        it = montar_email.resolver({"ref": ident}, json.loads(json.dumps(ev, default=str)), [])
        montador = bool(montar_email.eh_rotina(it) or it.get("_pln"))
        if e.get("veto"):
            assert ident not in agrupados and montador, ident         # com veto: linha propria (o veto aparece)
            continue
        assert (ident in agrupados) == montador, (ident, montador, it.get("resumo"))
    assert {"dec13180", "dec13181"} <= agrupados and not {"dec13182", "dec13183"} & agrupados, agrupados
    assert any(l.startswith("[NOVA] lei15599 |") and "veto: Veto parcial" in l for l in linhas)
    # sem o montador (import quebrado): nada e agrupado, cada ato na sua linha (nada some)
    antigo = coleta_web._ROTINA_MONTADOR[:]
    coleta_web._ROTINA_MONTADOR[:] = [None]
    try:
        assert not coleta_web.eh_rotina_ato({"ementa": "Abre ao Orçamento Fiscal crédito suplementar"})
        assert coleta_web.eh_rotina_ato({"ementa": "x", "materia": "PLN 3/2026"})
    finally:
        coleta_web._ROTINA_MONTADOR[:] = antigo


@teste
def coleta_legin():
    """(achado 8) LEGIN: 1 GET na busca ordenada por data e 1 por ato candidato no detalhe (DOU, edicao extra,
    apelido); leis listadas pelo Congresso e atos ja publicados nao viram item nem pedido; ids pelo tipo (dec13173);
    chave planalto|decreto|13173|...; status camara_legin. Paginas reais (busca de 21/11 e detalhe do 13.173)."""
    busca, det = pagina_fixture("legin-busca-2111.html"), pagina_fixture("legin-decreto-13173.html")

    def resp(u):
        if "legislacao/busca" in u:
            return (200, busca) if "pagina=" not in u else (200, "")
        return (200, det) if "decreto-13173" in u else (404, "")
    atos = {("decreto", "13168"), ("decreto", "13171")}
    congresso = {("lei", "15531"), ("lei", "15532")}
    with Rede(resp) as rede:
        r = coleta_web.legin(*_janela(*J2011), atos, lambda: congresso)
    det_ped = [p for p in rede.pedidos if "/legin/" in p]
    assert det_ped == ["https://www2.camara.leg.br/legin/fed/decret/2026/decreto-13173-19-novembro-2026-800207-norma-"
                       "pe.html", "https://www2.camara.leg.br/legin/fed/lei/2026/lei-15540-18-novembro-2026-800201-"
                       "norma-pl.html"], det_ped      # 15540 nao foi listada pelo Congresso: vai ao detalhe (404)
    assert r["listadas"] == 6 and r["no_congresso"] == 2 and r["ja_publicadas"] == ["Decreto 13168", "Decreto 13171"], r
    d = next(i for i in r["itens"] if i["numero"] == "13173")
    assert (d["situacao"], d["dou"], d["extra"], d["apelido"], d["chave"]) == (
        "NOVA", "19/11/2026", True, "Jornada de Trabalho 5X2", "planalto|decreto|13173|2026|2026-11-19"), d
    assert d["ementa"].startswith("Dispõe sobre a duração normal do trabalho")
    sem = next(i for i in r["itens"] if i["numero"] == "15540")
    assert sem["situacao"] == "SEM_DATA_OFICIAL" and sem["prefixo"] == "lei", sem
    linhas = coleta_web.imprimir_legin(r)
    assert any(l.startswith("[NOVA] dec13173 | Decreto nº 13173 de 19/11/2026 (DOU 19/11 · edição extra) — "
                            "«Jornada de Trabalho 5X2» Dispõe") for l in linhas), linhas
    assert "JA PUBLICADOS (nao repetir, nem pela resenha PUSH): Decreto 13168; Decreto 13171" in linhas
    assert any(l.startswith("[SEM_DATA_OFICIAL] rotina — 1 ato(s)") and "lei15540" in l for l in linhas), linhas
    assert coleta_web.status_fontes([r])["camara_legin"][0] == "ok"
    # nada novo: a linha diz que o DOU de hoje pode nao estar indexado (nunca "sem ato novo")
    with Rede(resp):
        r2 = coleta_web.legin(*_janela(*J2011), atos | {("decreto", "13173"), ("lei", "15540")},
                              lambda: congresso | {("lei", "15535"), ("lei", "15539")})
    assert not r2["itens"] and any(l.startswith("NENHUM ATO FORA DO CONGRESSO E DO HISTORICO") and 'nunca "sem ato novo"'
                                   in l for l in coleta_web.imprimir_legin(r2))
    # fora do ar: falha, e o erro aponta a resenha PUSH; uma excecao nunca derruba a coleta
    with Rede(lambda u: (503, "")):
        r3 = coleta_web.legin_seguro(*_janela(*J2011), atos)
    assert coleta_web.status_fontes([r3])["camara_legin"][0] == "falha"
    assert any(l.startswith("ERRO: LEGIN nao lido (http=503)") for l in coleta_web.imprimir_legin(r3))
    antigo = coleta_web.legin
    coleta_web.legin = lambda *a, **k: 1 / 0
    try:
        assert coleta_web.legin_seguro(*_janela(*J2011), atos)["erro"].startswith("ZeroDivisionError")
    finally:
        coleta_web.legin = antigo
    assert coleta_web.norma_legin("Lei Complementar nº 233, de 1º de Julho de 2026") == \
        ("Lei Complementar", "233", date(2026, 7, 1))
    assert coleta_web.norma_legin("Medida Provisória nº 1.400, de 3 de Março de 2026")[1] == "1400"
    # o historico identifica o ato pelo titulo de Planalto, mesmo com a chave fora do formato
    atos, _ = coleta_web.carregar_publicados([{"execution_id": "x", "items": [
        {"categoria": "Planalto/Legislação", "titulo": "Decreto nº 13.167, de 16/11/2026", "chave": "planalto|ato|x"},
        {"categoria": "Planalto/Legislação", "titulo": "Câmara aprova crédito (MP 1.397/26)", "chave": "c|d|e"}]}])
    assert ("decreto", "13167") in atos and ("mpv", "1397") not in atos, atos
    # Agencia Camara: ato interno ou honorifico aprovado em Plenario so contado
    assert coleta_web.marca_camara("Câmara aprova criação de selo de respeito à voz do cidadão") == ""
    assert coleta_web.marca_camara("Câmara aprova sessão solene em homenagem aos 50 anos da OAB-DF") == ""
    assert coleta_web.marca_camara("Câmara aprova medida provisória do crédito a exportadores") == "LEI"
    assert coleta_web.marca_camara("Câmara aprova projeto que endurece penas para feminicídio") == "PLENARIO"


# ------------------------------------------------------------ Agencia Camara (site)
def pagina_camara(noticias):
    """HTML no formato real de /noticias/ultimas: (retranca, titulo, 'DD/MM/AAAA HH:MM', id)."""
    itens = "".join(
        '<li class="l-lista-noticias__item"><article class="g-chamada chamada--ultimas">'
        '<img src="x.jpg" class="g-chamada__imagem" alt="" loading="lazy" /><div class="g-chamada__conteudo">'
        '<span class="g-chamada__retranca">%s</span><h3 class="g-chamada__titulo">\n'
        '<a href="https://www.camara.leg.br/noticias/%d-x">%s</a></h3>'
        '<span class="g-chamada__data">%s</span></div></article></li>\n' % (ret, nid, tit, quando)
        for ret, tit, quando, nid in noticias)
    return '<ul class="l-lista-noticias" aria-label="Lista de últimas notícias">\n%s</ul>' % itens


def rede_camara(paginas):
    """paginas: {numero: (http, html)}; devolve (falso para coleta_web._fetch1, lista de pedidos)."""
    pedidos = []

    def falso(url, timeout):
        pedidos.append(url)
        n = int(url.split("pagina=")[1]) if "pagina=" in url else 1
        cod, corpo = paginas.get(n, (200, pagina_camara([])))
        return cod, corpo, False
    return falso, pedidos


JAN_CAM = (datetime.fromisoformat("2026-11-16T07:07:30-03:00"), datetime.fromisoformat("2026-11-17T07:07:43-03:00"))


def coletar_camara(paginas, urls_pub=()):
    falso, pedidos = rede_camara(paginas)
    antigo, pausa = coleta_web._fetch1, coleta_web.PAUSA_REPETICAO
    coleta_web._fetch1, coleta_web.PAUSA_REPETICAO = falso, 0
    try:
        ini, fim = JAN_CAM
        return coleta_web.camara_seguro(ini, fim, fim.replace(day=16), set(urls_pub)), pedidos
    finally:
        coleta_web._fetch1, coleta_web.PAUSA_REPETICAO = antigo, pausa


@teste
def camara_marcas():
    casos = {
        "Câmara aprova criação da Política Nacional de Residência em Saúde": "PLENARIO",
        "Deputados aprovam requerimentos de urgência para duas propostas; acompanhe": "PLENARIO",
        "Congresso aprova créditos orçamentários de R$ 152,4 bilhões no Orçamento de 2026": "PLENARIO",
        "Câmara envia ao Senado projeto que flexibiliza Código Florestal": "PLENARIO",
        "Texto que cria cadastro de condenados segue para sanção": "PLENARIO",
        "Congresso derruba veto a projeto sobre licenciamento ambiental": "LEI",
        "Medida provisória prorroga Auxílio Gás do Povo até 2031": "LEI",
        "Lula sanciona lei que amplia licença-paternidade": "LEI",
        "Sancionada lei que cria o Estatuto da Segurança Privada": "LEI",
        "Congresso promulga emenda constitucional da reforma administrativa": "LEI",
        "Motta destaca sanção de lei que garante auxílio a produtores de cana-de-açúcar do Nordeste": "LEI",
        # comissao, projeto apresentado, agenda e homenagem nao entram
        "Comissão aprova classificar Hamas e Hezbollah como grupos terroristas": "",
        "Comissão mista aprova medida provisória do crédito rural": "",
        "Projeto prevê sanção para empresa que descumprir cota": "",
        "Projeto proíbe uso da imagem de empregado em redes sociais da empresa sem previsão contratual": "",
        "Câmara pode votar regras mais rígidas para progressão de pena": "",
        "Câmara homenageia ex-constituinte e ex-governador paranaense José Richa": "",
        "Líder do governo afirma que ajuste fiscal não retira recursos da saúde e da educação": "",
    }
    erradas = {t: coleta_web.marca_camara(t) for t, esperado in casos.items() if coleta_web.marca_camara(t) != esperado}
    assert not erradas, erradas


@teste
def camara_pagina_real_1711():
    """17/11/2026: nenhum boletim por e-mail em 16 e 17/11; o site tinha as noticias de 16/11 (nenhuma de lei
    ou Plenario). O trecho real da pagina e lido: 10 noticias, todas na janela, nenhuma marcada, fonte ok."""
    html_real = open(os.path.join(FIX, "camara-ultimas-1711.html"), encoding="utf-8").read()
    antiga = pagina_camara([("Política", "Câmara aprova projeto antigo", "13/11/2026 12:02", 1)])
    r, pedidos = coletar_camara({1: (200, html_real), 2: (200, antiga)})
    assert (r["http"], r["lidas"], r["na_janela"], r["resto"], r["itens"], r["completa"]) == (200, 11, 10, 10, [], True), r
    assert pedidos == [coleta_web.URL_CAMARA, coleta_web.URL_CAMARA + "?pagina=2"], pedidos
    linhas = coleta_web.imprimir_camara(r)
    assert linhas[0].startswith("\n== AGENCIA CAMARA") and "na_janela=10 LEI/PLENARIO=0" in linhas[0], linhas
    assert any(l.startswith("SEM [LEI]/[PLENARIO] NA JANELA: 10 noticia(s)") for l in linhas), linhas
    assert not any(l.startswith(("ERRO", "AVISO")) for l in linhas), linhas
    assert coleta_web.status_fontes([r])["camara_noticias"] == ("ok", "0 [LEI]/[PLENARIO] em 10 noticia(s) da janela")


@teste
def camara_itens_janela_e_repetidos():
    p1 = pagina_camara([
        ("Política", "Câmara aprova projeto que aumenta penas para compra de votos", "17/11/2026 08:30", 110),   # depois do fim
        ("Política", "Câmara aprova criação da Política Nacional de Residência em Saúde", "16/11/2026 20:53", 109),
        ("Segurança", "Comissão aprova classificar Hamas e Hezbollah como grupos terroristas", "16/11/2026 19:19", 108),
        ("Economia", "Medida provisória prorroga Auxílio Gás do Povo até 2031", "16/11/2026 11:57", 107),
        ("Agropecuária", "Comissão mista aprova medida provisória do crédito rural", "16/11/2026 11:00", 106)])
    p2 = pagina_camara([
        ("Política", "Congresso derruba veto a projeto sobre licenciamento ambiental", "16/11/2026 09:10", 105),
        ("Política", "Câmara aprova urgência para propostas sobre educação integral", "16/11/2026 08:00", 104),
        ("Política", "Câmara aprova projeto de sexta-feira", "13/11/2026 19:00", 103)])                       # antes da janela
    ja = {"https://www.camara.leg.br/noticias/104-x"}
    r, pedidos = coletar_camara({1: (200, p1), 2: (200, p2), 3: (200, pagina_camara([]))}, ja)
    assert len(pedidos) == 2 and r["completa"] and r["paginas"] == 2, (pedidos, r)       # parou no que e anterior a janela
    assert (r["lidas"], r["na_janela"], r["resto"]) == (8, 6, 2), r
    assert r["duvidosos"] == ["Comissão mista aprova medida provisória do crédito rural"], r["duvidosos"]
    assert [(i["marca"], i["situacao"], i["url"].rsplit("/", 1)[1]) for i in r["itens"]] == [
        ("PLENARIO", "NOVA", "109-x"), ("LEI", "NOVA", "107-x"), ("LEI", "NOVA", "105-x"),
        ("PLENARIO", "JA_PUBLICADA", "104-x")], r["itens"]
    linhas = coleta_web.imprimir_camara(r)
    assert [i.get("id") for i in r["itens"]] == ["cam1", "cam2", "cam3", None], r["itens"]
    assert "[NOVA|PLENARIO] cam1 | 16/11 20:53 | Câmara aprova criação da Política Nacional de Residência em Saúde — Política" in linhas
    assert "[NOVA|LEI] cam2 | 16/11 11:57 | Medida provisória prorroga Auxílio Gás do Povo até 2031 — Economia" in linhas
    assert "LEI/PLENARIO=3 JA_PUBLICADA=1" in linhas[0], linhas[0]
    assert any("(+2 noticia(s) sem [LEI]/[PLENARIO]" in l and "Comissão mista aprova medida provisória" in l for l in linhas)
    assert coleta_web.status_fontes([r])["camara_noticias"][0] == "ok"
    # o JSON e serializavel e o item carrega a hora exata (o montador tira dali data, hora e chave)
    def ser(o):
        return o.isoformat() if isinstance(o, (datetime, date)) else str(o)
    d = json.loads(json.dumps([r], ensure_ascii=False, default=ser))
    assert d[0]["itens"][0]["quando"] == "2026-11-16T20:53:00-03:00", d[0]["itens"][0]


@teste
def camara_falhas_nao_derrubam_a_coleta():
    r, pedidos = coletar_camara({1: (403, "")})
    assert r["http"] == 403 and len(pedidos) == 1 and coleta_web.status_fontes([r])["camara_noticias"][0] == "falha"
    linhas = coleta_web.imprimir_camara(r)
    assert any(l.startswith("ERRO: Agencia Camara nao lida no site (http=403)") and "coletor Gmail" in l
               and "sem WebSearch" in l for l in linhas), linhas
    r, _ = coletar_camara({1: (200, "<html><body>layout novo</body></html>")})
    assert coleta_web.status_fontes([r])["camara_noticias"] == ("falha", "pagina lida, 0 noticias extraidas (layout?)")
    # pagina 2 falha: as noticias da pagina 1 valem, com aviso de leitura incompleta
    p1 = pagina_camara([("Política", "Câmara aprova criação da Política Nacional de Residência em Saúde", "16/11/2026 20:53", 109)])
    r, _ = coletar_camara({1: (200, p1), 2: (503, "")})
    linhas = coleta_web.imprimir_camara(r)
    assert len(r["itens"]) == 1 and not r["completa"] and any(l.startswith("AVISO: a leitura parou antes") for l in linhas), linhas
    assert coleta_web.status_fontes([r])["camara_noticias"] == ("ok", "1 [LEI]/[PLENARIO] em 1 noticia(s) da janela; leitura incompleta")
    # excecao dentro da leitura: bloco de erro, nunca excecao para o main()
    antigo = coleta_web.camara
    coleta_web.camara = lambda *a: 1 / 0
    try:
        ini, fim = JAN_CAM
        r = coleta_web.camara_seguro(ini, fim, fim, set())
    finally:
        coleta_web.camara = antigo
    assert r["erro"].startswith("ZeroDivisionError") and coleta_web.status_fontes([r])["camara_noticias"][0] == "falha"
    assert any(l.startswith("ERRO: Agencia Camara nao lida no site (ZeroDivisionError") for l in coleta_web.imprimir_camara(r))
    # teto de paginas: nunca mais que MAX_PAGINAS_CAMARA pedidos
    cheia = pagina_camara([("Política", "Câmara aprova projeto %d" % n, "16/11/2026 20:%02d" % n, 200 + n) for n in range(10)])
    r, pedidos = coletar_camara({n: (200, cheia.replace("/noticias/2", "/noticias/%d2" % n)) for n in range(1, 30)})
    assert len(pedidos) == coleta_web.MAX_PAGINAS_CAMARA and not r["completa"], len(pedidos)


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
    linhas = out.splitlines()
    rede.ja_saiu = [l for l in linhas if l.startswith("JA SAIU ")]    # lista do fim (com historico)
    return codigo, [l for l in linhas if not l.startswith("JA SAIU ")], rede


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
def resolver_metadados_da_pagina_e_ja_saiu():
    """(21/11, achado 12) A linha OK traz a data da materia (article:published_time), o autor e a linha-fina
    (og:description) da pagina ja baixada: 9 de 19 itens do JOTA sairam com a data do e-mail e varios sem resumo.
    Materia anterior ao inicio da janela: '(antes da janela)'. No fim, a lista JA SAIU das 2 ultimas edicoes."""
    destino = "https://www.jota.info/justica/stj-fara-audiencia-sobre-cartao-de-credito-consignado-e-criterios"
    tit = "STJ fará audiência sobre cartão de crédito consignado e critérios para contrato abusivo"
    mapa = {W % 1: (302, destino, ""), destino: (200, "", pagina_fixture("jota-stj-consignado.html"))}
    janela = {"ignorar_execucao": "", "inicio": "2026-11-16T07:05:00-03:00"}
    _, out, rede = rodar_resolver([tit + "\t" + W % 1], mapa, ["--sem-historico"], janela=janela)
    assert out == ["OK\t%s\t%s\t16/11 17:02\tLucas Mendes\tSTJ marcou para 27 de novembro uma audiência pública "
                   "sobre o funcionamento do cartão de crédito consignado." % (tit, destino)], out
    assert not rede.ja_saiu                                   # sem historico, sem lista
    janela["inicio"] = "2026-11-17T07:05:00-03:00"
    _, out, rede = rodar_resolver([tit + "\t" + W % 1], mapa, janela=janela)
    assert out[0].split("\t")[3] == "16/11 17:02 (antes da janela)", out
    assert rede.ja_saiu and rede.ja_saiu[0].startswith("JA SAIU 13/11 — Mídia: "), rede.ja_saiu
    # pagina sem metadado nenhum: a linha OK de sempre (3 campos)
    q, a, f = resolver_jota.metadados(pagina("x"))
    assert (q, a, f) == (None, "", "")
    longa = '<meta content="%s" property="og:description">' % ("palavra " * 40)
    assert resolver_jota.metadados(longa)[2].endswith("…") and len(resolver_jota.metadados(longa)[2]) <= 200


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
    assert len(linhas) == 4 and linhas[1].startswith("JA_PUBLICADA"), linhas
    assert linhas[2].startswith("JA SAIU 13/11 — ") and linhas[3].startswith("JA SAIU 12/11 — "), linhas[2:]


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
    # (21/11) funil do JOTA: a saida compacta das duas chamadas fica em $ROBOZINHO_TMP/jota_extrato.txt
    ext = open(os.path.join(TMPDIR, "jota_extrato.txt"), encoding="utf-8").read()
    assert "Fim da 6x1: Dino mira em lacunas, faz ajustes, mas não muda principais pontos da emenda [L1]" in ext
    assert "Matéria direta: [L10]" in ext and "rdsv2" not in ext and ext.count("=== ") == out.count("=== ") + \
        out2.count("=== "), ext[:300]


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


MANCHETES_FRACAS = [        # trecho de descadastro "fraco", sem contexto de e-mail: e manchete (volta 3)
    "Aposentados podem deixar de receber benefício em 2027",
    "Brasil pode sair da lista suja da OIT",
    "PREVIDÊNCIA | Aposentados podem deixar de receber benefício em 2027",
    "TRABALHO | Brasil pode sair da lista suja da OIT",
    "Aposentados podem deixar de receber benefício após revisão. Entenda",
    "TSE manda cancelar inscrição de candidato por fraude em domicílio eleitoral",
    "STF decide que contribuinte não precisa mais receber notificação por carta",
    "Caso não queira depor, Bolsonaro pode ser conduzido pela PF",
    "TCU determina que estado deixe de receber repasses do fundo",
    "'Não quero mais receber visitas de políticos', diz Bolsonaro ao STF",
    "Lei garante preferência a idosos no pagamento de precatórios"]
RODAPES_FRACOS = [          # o mesmo trecho fraco, com contexto de rodape (ou curto): sempre descadastro
    "Caso não queira mais receber nossos boletins, acesse",
    "Se não deseja mais receber nossos informativos diários, use o endereço",
    "Para parar de receber o JOTA Principal diariamente na sua caixa de entrada",
    "Sair da lista de distribuição do JOTA Principal",
    "Deixe de receber os alertas do JOTA PRO Tributos",
    "Não quero mais receber o JOTA Principal todas as manhãs",
    "Pare de receber o boletim do JOTA Principal",
    "Remover meu endereço da lista de envio do JOTA",
    "Para cancelar sua assinatura de alertas, responda a esta mensagem",
    "Brasil pode sair da lista",                                       # curto (<= 6 palavras)
    "Deixar de receber"]


@teste
def jota_manchete_com_trecho_fraco():
    """Volta 3 (P1): o extrator tratava como descadastro manchetes legitimas
    ("Aposentados podem deixar de receber beneficio em 2027", "Brasil pode sair da
    lista suja da OIT"): o link saia do indice e a noticia ia ao leitor sem link.
    Agora vale a MESMA regra do resolver (uma funcao so, descadastro_no_texto):
    trecho fraco so conta com contexto de e-mail ou em texto curto; a frase
    anterior a 'clique aqui' e a zona de rodape continuam sem isencao."""
    # uma regra so: as listas sao as do extrator, nao copias
    assert resolver_jota.TRECHO_FRACO is jota_extrair.TRECHO_FRACO
    assert resolver_jota.CONTEXTO_EMAIL is jota_extrair.CONTEXTO_EMAIL
    for t in MANCHETES_FRACAS:
        assert jota_extrair.trecho_descadastro(t) == "", (t, jota_extrair.trecho_descadastro(t))
        assert resolver_jota.titulo_de_descadastro(t) == "", (t, resolver_jota.titulo_de_descadastro(t))
    for t in RODAPES_FRACOS + [unicodedata.normalize("NFD", r) for r in RODAPES_FRACOS] + \
            [r.upper() for r in RODAPES_FRACOS]:
        assert jota_extrair.trecho_descadastro(t), t
        assert resolver_jota.titulo_de_descadastro(t), t
    # extrator: as manchetes ficam com link; os rodapes, fora do indice
    partes = []
    for i, t in enumerate(MANCHETES_FRACAS):
        partes.append("%s [ https://t.rdsv2.net/ls/click?upn=u001.MAN-%02d ]\n Linha-fina qualquer." % (t, i))
    for i, t in enumerate(RODAPES_FRACOS):
        partes.append("%s [ https://t.rdsv2.net/ls/click?upn=u001.ROD-%02d ]." % (t, i))
    # frase anterior a "clique aqui" (sem isencao) e zona de rodape (sem isencao)
    partes.append("Aposentados podem deixar de receber benefício em 2027.\n clique aqui "
                  "[ https://t.rdsv2.net/ls/click?upn=u001.ROD-90 ]")
    partes.append("JOTA Jornalismo · Todos os direitos reservados.\n Brasil pode sair da lista suja da OIT "
                  "[ https://t.rdsv2.net/ls/click?upn=u001.ROD-91 ]")
    arq = os.path.join(TMPDIR, "manchetes_fracas.txt")
    with open(arq, "w", encoding="utf-8") as f:
        f.write("\n\n".join(partes) + "\n")
    urls = os.path.join(TMPDIR, "jota_urls_fracas.tsv")
    codigo, out = saida_de(jota_extrair.main, ["--novo", "--urls", urls, arq])
    indice = open(urls, encoding="utf-8").read()
    assert codigo == 0 and "ROD-" not in indice, [l for l in indice.splitlines() if "ROD-" in l]
    faltam = [t for i, t in enumerate(MANCHETES_FRACAS) if "MAN-%02d" % i not in indice]
    assert not faltam, faltam
    assert "Aposentados podem deixar de receber benefício em 2027 [L1]" in out, out
    assert "Brasil pode sair da lista suja da OIT [L2]" in out, out
    assert "%d descadastro/preferencias" % (len(RODAPES_FRACOS) + 2) in out.splitlines()[0], out.splitlines()[0]


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
