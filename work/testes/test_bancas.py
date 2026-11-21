#!/usr/bin/env python3
# =====================================================================
# test_bancas.py — testes da leitura da banca FGV (work/bancas.py), sem rede:
#   listagem paginada so da view "concursos_em_andamento" (todo href pt-br:
#   /juiztjba, /tjpa25, /exames/enam/6exame; a view de realizados fica de
#   fora; para na 1a pagina sem linhas; pagina com falha nao derruba as
#   outras); GETs em paralelo com teto de tempo; vinculo pagina -> registro
#   por banca_slug (e pela fonte, sem banca_slug); CANDIDATO pela organizacao
#   normalizada (dperj2026 -> dpe_rj) com linha pronta; travas de ciclo
#   (XXXIX x XL, ano seguinte, edicao antiga, registro em planejamento);
#   NOVA EDICAO; ENAM sem registro; escopo do quadro de apoio (so Sul/Sudeste,
#   contagem sem linha); MOVIMENTO e contagem; estado parcial das paginas sem
#   registro; TRECHOS_ALT (TJPB e ENAM ganham vagas/vencimento/prova; TJSC e
#   TJAP saem iguais); banca_slug no Update-Historico (formato e unicidade);
#   listagem ilegivel le os vinculados (rev1 C3); NOVA EDICAO de vinculado sem
#   ano (rev1 C4); teto do paralelo limita o processo e o curl/pdftotext (C5).
# USO: python3 work/testes/test_bancas.py   (imprime OK/FALHOU; sai != 0 em falha)
# Tudo roda numa pasta temporaria (ROBOZINHO_TMP proprio); a rede e simulada.
# =====================================================================

import contextlib
import copy
import importlib.util
import io
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import traceback
from datetime import date

AQUI = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.dirname(AQUI)
FIX = os.path.join(AQUI, "fixtures", "bancas")
FIX_EST = os.path.join(AQUI, "fixtures", "est")
TMPDIR = tempfile.mkdtemp(prefix="robozinho-bancas-")
os.environ["ROBOZINHO_TMP"] = TMPDIR
sys.path.insert(0, WORK)

import bancas            # noqa: E402

_spec = importlib.util.spec_from_file_location("uh", os.path.join(WORK, "Update-Historico.py"))
uh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(uh)

TESTES, FALHAS = [], []
HOJE = date(2026, 11, 21)
B = bancas.BASE
PDF = B + "/sites/default/files/concursos/"


def teste(f):
    TESTES.append(f)
    return f


def ok(cond, msg):
    if not cond:
        raise AssertionError(msg)


def fx(nome):
    with open(os.path.join(FIX, nome), encoding="utf-8") as f:
        return f.read()


def norm(t):
    return re.sub(r"\s+", " ", t)


def saida(res):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        bancas.imprimir(res)
    return buf.getvalue()


@contextlib.contextmanager
def trocar(**valores):
    """Troca constantes do bancas.py durante o bloco (teto de tempo, lote da listagem)."""
    antes = {k: getattr(bancas, k) for k in valores}
    for k, v in valores.items():
        setattr(bancas, k, v)
    try:
        yield
    finally:
        for k, v in antes.items():
            setattr(bancas, k, v)


def pagina_html(titulo, arquivos, situacao="Em Andamento"):
    """HTML no formato da FGV (situacao, <h1>, "Arquivos do concurso": data e titulo com link)."""
    itens = "".join(
        '<div class="field__item"><div class="paragraph paragraph--type--texto-data paragraph--view-mode--default">\n'
        '<div class="field__item"><time datetime="%sT12:00:00Z" class="datetime">%s</time>\n</div>\n'
        '<div class="field__item"><p>%s</p></div>\n</div></div>\n' % (
            d, "%s/%s/%s" % (d[8:10], d[5:7], d[:4]), ('<a href="%s">%s</a>' % (u, t)) if u else t, )
        for d, t, u in arquivos)
    return ('<html><body><header><a href="/x.pdf">menu</a></header><main role="main"><div class="container">'
            '<small class="field__item">%s</small><div class="field--name-title"><h1>%s</h1></div>'
            '<h3 class="field__label">Arquivos do concurso</h3>\n%s</div></main></body></html>' % (situacao, titulo, itens))


def pag(slug, titulo, arquivos, situacao="Em Andamento"):
    """Concurso como pagina() o devolve (para analisar() direto, sem a listagem)."""
    url = B + ("/" if "/" in slug else "/concursos/") + slug
    return bancas.analisar_pagina({"slug": slug, "titulo": titulo, "url": url, "http": 200},
                                  pagina_html(titulo, arquivos, situacao))


class Rede:
    """Rede simulada: URL -> (http, texto) | excecao | (atraso, http, texto). Anota os pedidos (de varias threads)."""

    def __init__(self, mapa):
        self.mapa, self.pedidos, self.trava = mapa, [], threading.Lock()

    def __call__(self, url, binario=False, timeout=40):
        with self.trava:
            self.pedidos.append(url)
        r = self.mapa.get(url, (404, ""))
        if isinstance(r, Exception):
            raise r
        if len(r) == 3:
            time.sleep(r[0])
            r = r[1:]
        return r


TIT_TJSC = "Concurso Público para o Tribunal de Justiça do Estado de Santa Catarina"
REGS = [
    {"id": "tjsc_juiz", "bloco": "Magistratura Estadual", "linha": "TJSC — Juiz Substituto: inscrições até 26/11",
     "selo": "ENCERRA EM BREVE", "verificado_em": "2026-11-20", "fonte": "secundária (busca)",
     "banca_slug": "tjscjuiz26",
     "prazos": [{"data": "2026-11-26", "evento": "fim das inscrições, 16h", "confirmado": True}]},
    {"id": "dpe_rj", "bloco": "Defensor Público Estadual (DPE)", "linha": "DPE-RJ — Defensor: FGV, 35 vagas",
     "selo": "PENDÊNCIA DE VERIFICAÇÃO", "verificado_em": "2026-11-11", "fonte": "https://ceisc.com.br/blog/dpe-rj"},
    {"id": "mprj_promotor", "bloco": "Promotor de Justiça (Estadual)",
     "linha": "MP-RJ — Promotor de Justiça (XL Concurso): regulamento divulgado", "selo": "EM PLANEJAMENTO",
     "verificado_em": "2026-11-16", "fonte": "https://folha.qconcursos.com/n/mprj"},
    {"id": "trf1_juiz", "bloco": "Magistratura Federal", "linha": "TRF1 — Juiz Federal Substituto (XVIII concurso)",
     "selo": "PENDÊNCIA DE VERIFICAÇÃO", "verificado_em": "2026-11-10", "fonte": "https://valorfinal.com.br/trf1",
     "banca_slug": "trf1juiz25"},
]
PAGINAS = {
    "tjscjuiz26": (TIT_TJSC + " - Juiz Substituto (2026)", [
        ("2026-11-10", "Interposição de recursos contra o Resultado preliminar da análise dos pedidos de isenção", ""),
        ("2026-10-19", "1ª Retificação", PDF + "tjsc-retificacao-1.pdf"),
        ("2026-09-29", "Edital (retificado em 19/10/2026)", PDF + "edital-tjsc.pdf")]),
    "exames/enam/6exame": ("Exame Nacional da Magistratura - ENAM (2026.2)", [
        ("2026-11-05", "Resultado definitivo dos pedidos de atendimento especial", PDF + "enam-atend.pdf"),
        ("2026-08-24", "Edital", PDF + "edital-enam.pdf")]),
    "exames/enam/5exame": ("Exame Nacional da Magistratura - ENAM (2026.1)", [
        ("2026-08-31", "Resultado final", PDF + "enam5-final.pdf"), ("2026-02-10", "Edital", PDF + "edital-enam5.pdf")]),
    "dperj2026": ("Concurso Público para a Defensoria Pública do Estado do Rio de Janeiro", [
        ("2026-11-03", "Prova Específica Dissertativa", ""), ("2026-06-01", "Edital", PDF + "edital-dperj.pdf")]),
    "tjscservidor26": (TIT_TJSC, [
        ("2026-11-18", "Resultado preliminar da análise dos pedidos de isenção", PDF + "tjscserv-isencao.pdf"),
        ("2026-10-20", "Edital", PDF + "edital-tjscservidor.pdf")]),
    "juiztjba": ("Concurso Público para o Tribunal de Justiça do Estado da Bahia", [
        ("2026-11-19", "Sessão Pública de Identificação das Provas Práticas de Sentença", PDF + "tjba-sessao.pdf"),
        ("2026-01-30", "Edital (retificado em 07/04/2026)", PDF + "edital-tjba.pdf")]),
    "mprjpromotor2026": ("XXXIX Concurso para Ingresso na Classe Inicial da Carreira do Ministério Público do Estado "
                         "do Rio de Janeiro", [
                             ("2026-11-17", "Resultado Final - Ampla Concorrência", PDF + "mprj-final.pdf"),
                             ("2026-03-12", "Edital do XXXIX Concurso para Ingresso na Classe Inicial",
                              PDF + "edital-xxxix.pdf")]),
    "tjpa25": ("Concurso Público para o Tribunal de Justiça do Estado do Pará", [
        ("2026-11-09", "Comunicado", PDF + "tjpa-com.pdf"), ("2025-06-02", "Edital", PDF + "edital-tjpa.pdf")]),
    "tjscjuiz25": (TIT_TJSC + " - Juiz Substituto (2025)", [
        ("2025-12-12", "Resultado Definitivo", PDF + "tjsc25-final.pdf"), ("2025-03-10", "Edital", PDF + "ed-tjsc25.pdf")]),
    "tjscjuiz27": (TIT_TJSC + " - Juiz Substituto (2027)", [
        ("2026-11-20", "Portaria da Comissão do Concurso", PDF + "tjsc27-comissao.pdf")]),
    "trf1juiz25": ("", [
        ("2026-11-16", "Resultado Provisório da Avaliação de Títulos", PDF + "trf1-titulos.pdf"),
        ("2026-11-12", "Resultado da Prova Oral", PDF + "trf1-oral.pdf"),
        ("2025-02-28", "Edital", PDF + "edital-trf1.pdf")]),
}
EDITAIS = {
    PDF + "edital-tjsc.pdf": "edital-tjsc-trechos.txt",
    PDF + "edital-dperj.pdf": "O presente Concurso Público destina-se ao provimento de 35 (trinta e cinco) vagas para o "
                              "cargo de Defensor Público do Estado do Rio de Janeiro.",
    PDF + "edital-tjscservidor.pdf": "destinado ao provimento de 40 (quarenta) cargos efetivos de Analista Judiciário "
                                     "e Técnico Judiciário. A taxa de inscrição é de R$ 110,00.",
    PDF + "edital-trf1.pdf": "destina-se ao provimento de 50 (cinquenta) vagas para o cargo de Juiz Federal Substituto.",
}


def ler_falso(url):
    t = EDITAIS.get(url)
    if t is None:
        return None, "http 404"
    return norm(fx(t) if t.endswith(".txt") else t), ""


def rede_fgv(paginas=PAGINAS, extra=None):
    mapa = {B + "/concursos": (200, fx("listagem-p0.html")), B + "/concursos?page=1": (200, fx("listagem-p1.html")),
            B + "/concursos?page=2": (200, fx("listagem-p2.html"))}
    for p in range(3, 30):
        mapa[B + "/concursos?page=%d" % p] = (200, fx("listagem-p2.html"))
    for slug, (tit, arqs) in paginas.items():
        mapa[B + ("/" if "/" in slug or slug == "juiztjba" or slug == "tjpa25" else "/concursos/") + slug] = (
            200, pagina_html(tit or "Concurso Público para o Tribunal Regional Federal da 1ª Região", arqs))
    mapa.update(extra or {})
    return Rede(mapa)


def coletar(rede=None, regs=REGS, estado=None):
    rede = rede or rede_fgv()
    res = bancas.coletar(HOJE, copy.deepcopy(regs), {} if estado is None else estado, buscar=rede, ler=ler_falso)
    return res, rede, {c["slug"]: c for c in res["concursos"]}


# ------------------------------------------------------------------ listagem
@teste
def listagem_paginada_so_em_andamento():
    """Todo href pt-br do bloco em andamento (inclusive /juiztjba, /tjpa25, /exames/enam/6exame), paginado ate a 1a
    pagina sem linhas; a view de realizados fica de fora; slug repetido entre paginas conta uma vez."""
    rede = rede_fgv()
    http, itens, falhas = bancas.listagem(rede)
    slugs = [i["slug"] for i in itens]
    ok(http == 200 and falhas == [], (http, falhas))
    ok({"juiztjba", "tjpa25", "exames/enam/6exame", "exames/enam/5exame", "dperj2026", "tjscjuiz27"} <= set(slugs), slugs)
    ok("tjrs2019" not in slugs and "tjap23" not in slugs and "mprjpromotor2025" not in slugs, "view de realizados")
    ok(slugs.count("tjscjuiz26") == 1 and len(slugs) == 15, slugs)
    url = {i["slug"]: i["url"] for i in itens}
    ok(url["juiztjba"] == B + "/juiztjba" and url["exames/enam/6exame"] == B + "/exames/enam/6exame"
       and url["dperj2026"] == B + "/concursos/dperj2026", url)
    # lote de 2: pede ?page=0..1, depois 2..3, e para no bloco vazio da ?page=2
    rede = rede_fgv()
    with trocar(LISTAGEM_LOTE=2):
        http, itens2, _ = bancas.listagem(rede)
    ok([i["slug"] for i in itens2] == slugs, "mesma lista em lotes")
    ok(B + "/concursos?page=4" not in rede.pedidos and B + "/concursos?page=2" in rede.pedidos, rede.pedidos)
    # pagina com falha (rede): as outras seguem, a falha fica anotada
    rede = rede_fgv(extra={B + "/concursos?page=1": (500, "")})
    http, itens3, falhas = bancas.listagem(rede)
    ok(http == 200 and falhas == [1] and "juiztjba" in [i["slug"] for i in itens3]
       and "tjpa25" not in [i["slug"] for i in itens3], (falhas, len(itens3)))
    res, _, _ = coletar(rede)
    ok("listagem incompleta: ?page=1 não lida(s)" in saida(res), saida(res))
    # tudo fora do ar: "não lida", como antes
    res = bancas.coletar(HOJE, REGS, {}, buscar=Rede({}), ler=ler_falso)
    ok(res["http"] == 404 and res["concursos"] == [] and "BANCA FGV: página não lida (http 404)" in saida(res), res)


@teste
def slug_organizacao_ciclo_e_ordinal():
    casos = {"tjscjuiz26": ("tjsc", 2026), "mpes25promotor": ("mpes", 2025), "juiztjba": ("tjba", None),
             "dperj2026": ("dperj", 2026), "trt24": ("trt24", None), "trt225": ("trt2", 2025),
             "trf5juiz26": ("trf5", 2026), "trf2juiz": ("trf2", None), "trf6": ("trf6", None),
             "dpe-pe": ("dpepe", None), "exames/enam/6exame": ("enam", None), "tjscservidor26": ("tjsc", 2026),
             "tjrjservidores25": ("tjrj", 2025), "mprjpromotor2026": ("mprj", 2026), "tjgo2025": ("tjgo", 2025),
             "defensoriapublica25": ("defensoriapublica", 2025)}
    for slug, esperado in casos.items():
        ok(bancas.partes_slug(slug) == esperado, "%s: %r" % (slug, bancas.partes_slug(slug)))
    ids = {"dpe_rj": "dperj", "tjpb_apoio": "tjpb", "pge_rj_apoio": "pgerj", "mp_ap_promotor": "mpap", "enam": "enam",
           "trf1_juiz": "trf1", "mpsp_oficial": "mpsp", "trt8_apoio": "trt8"}
    for ident, org in ids.items():
        ok(bancas.org_id(ident) == org, "%s: %r" % (ident, bancas.org_id(ident)))
    ok(bancas.ciclo("exames/enam/7exame") == 7 and bancas.ciclo("tjscjuiz27") == 2027 and bancas.ciclo("trf6") is None,
       "ciclo")
    ok(bancas.norm_slug("/concursos/tjap26") == "tjap26" and bancas.norm_slug(B + "/exames/enam/6exame") == "exames/enam/6exame"
       and bancas.norm_slug("concursos/tjap26") == "tjap26", "norm_slug")
    ok(bancas.cargo_slug("juiztjba") == {"magistratura"} and bancas.cargo_slug("tjscservidor26") == {"apoio"}, "cargo")
    ok(set(bancas.ordinais("XXXIX Concurso para Ingresso")) == {39}, bancas.ordinais("XXXIX Concurso"))
    ok(set(bancas.ordinais("MP-RJ — Promotor (XL Concurso)")) == {40}, "XL")
    ok(set(bancas.ordinais("TJPB — Juiz Substituto (54º concurso)")) == {54}, "54º")
    ok(bancas.ordinais("direito CIVIL concurso") == {} and bancas.ordinais("o concurso XL") == {}, "falso ordinal")


# ------------------------------------------------------------------ coleta inteira (rede simulada)
@teste
def coleta_vinculo_candidato_travas_e_contagem():
    res, rede, cs = coletar()
    # nao baixa: nao juridico, fora de carreira (juiz leigo, tribunal de contas) e apoio fora do escopo (MT)
    for slug in ("concursoseducsp27", "tjbajuizleigo26", "tjmtservidor", "tcesc26", "cpnu2"):
        ok(not any(u.endswith("/" + slug) for u in rede.pedidos), "%s baixado" % slug)
    ok(res["listagem"]["fora_escopo"] == ["tjmtservidor"]
       and set(res["listagem"]["fora_carreira"]) == {"tjbajuizleigo26", "tcesc26"}, res["listagem"])
    # vinculo por banca_slug: cobre, carimba, rele o edital e nao diverge (26/11 nos dois)
    t = cs["tjscjuiz26"]
    ok(t["exibir"] == "registro" and t["coberto"] == ["tjsc_juiz"] and t["vinculo"] == "banca_slug"
       and t["inscricoes"]["fim"] == "2026-11-26" and t["divergencias"] == [], t.get("coberto"))
    car = bancas.carimbos(res, REGS, HOJE)
    ok(car["tjsc_juiz"]["fonte"] == B + "/concursos/tjscjuiz26" and car["trf1_juiz"]["verificado_em"] == "2026-11-21",
       car)
    # registro com banca_slug fora da listagem: a pagina e lida assim mesmo (titulo do <h1>)
    f = cs["trf1juiz25"]
    ok(f["coberto"] == ["trf1_juiz"] and f.get("fora_da_listagem") and "1ª Região" in f["titulo"], f.get("titulo"))
    # edicao anterior (tjscjuiz25) nao derruba o tjsc_juiz; a do ano seguinte e NOVA EDICAO
    ok(cs["tjscjuiz25"]["exibir"] == "outros" and "tjsc_juiz" in cs["tjscjuiz25"]["edicao"], cs["tjscjuiz25"].get("edicao"))
    ok(cs["tjscjuiz27"]["exibir"] == "nova_edicao" and cs["tjscjuiz27"]["coberto"] == [], cs["tjscjuiz27"]["exibir"])
    # CANDIDATO pela organizacao normalizada (dpe_rj -> dperj); o edital decide o cargo (Defensor)
    d = cs["dperj2026"]
    ok(d["exibir"] == "candidato" and d["candidatos"] == ["dpe_rj"] and d["coberto"] == [] and not d.get("cargo_incerto")
       and d["releitura"] == "cargo do candidato não identificado", d)
    # XXXIX x XL: nao e candidato do mprj_promotor; o movimento sai numa linha
    m = cs["mprjpromotor2026"]
    ok(m["exibir"] == "movimento" and m["candidatos"] == [] and "XXXIX × XL" in m["edicao"], m.get("edicao"))
    # mesma sigla, outro cargo (servidores do TJSC, apoio no escopo) com abertura recente: SEM REGISTRO completo
    s = cs["tjscservidor26"]
    ok(s["exibir"] == "novo" and s["mesma_sigla"] == ["tjsc_juiz"] and s["releitura"] == "concurso sem registro"
       and "vagas" in s["edital"], s)
    ok(cs["juiztjba"]["exibir"] == "movimento" and cs["tjpa25"]["exibir"] == "outros", "movimento x contagem")
    # ENAM sem registro enam: so a edicao mais nova e candidata a registro novo
    ok(cs["exames/enam/6exame"]["exibir"] == "exame" and cs["exames/enam/5exame"]["exibir"] == "outros", "ENAM")
    ok(cs["tjpa25"]["arquivos"] == [] and cs["tjpa25"]["ultimo"]["data"] == "2026-11-09", "contagem sem arquivos")
    txt = saida(res)
    for trecho in (
            'CANDIDATO dpe_rj ← dperj2026 | Em Andamento | Concurso Público para a Defensoria Pública do Estado do Rio de '
            'Janeiro | últ. 03/11 Prova Específica Dissertativa | ' + B + '/concursos/dperj2026 → confirme o ciclo '
            '(ordinal/ano) e grave ledger_updates.concursos.dpe_rj.banca_slug="dperj2026"',
            'CANDIDATO a registro NOVO enam ← exames/enam/6exame |',
            'banca_slug="exames/enam/6exame"',
            'NOVA EDIÇÃO? tjscjuiz27 |', 'tjsc_juiz está vinculado a tjscjuiz26',
            "- tjscservidor26 | Em Andamento | %s | SEM REGISTRO (tjsc_juiz, da mesma sigla, é de outro cargo) → avalie "
            "como NOVO | " % TIT_TJSC,
            "- MOVIMENTO sem registro: juiztjba | Concurso Público para o Tribunal de Justiça do Estado da Bahia | 19/11 "
            "Sessão Pública de Identificação das Provas Práticas de… | " + B + "/juiztjba",
            "[não é mprj_promotor: XXXIX × XL]",
            "- tjscjuiz26 | Em Andamento | %s - Juiz Substituto (2026) | registro tjsc_juiz | " % TIT_TJSC,
            "1 fora do escopo (apoio só Sul/Sudeste)", "2 fora de carreira",
            "lidos dos 15 em andamento na listagem; 2 com registro"):
        ok(trecho in txt, "falta %r em\n%s" % (trecho, txt))
    for nada in ("tjrs2019", "concursoseducsp27", "tjmtservidor |", "tjpa25 |", "tjscjuiz25 |", "5exame |"):
        ok(nada not in txt, "%r na saída" % nada)
    linhas = [l for l in txt.splitlines() if l.startswith(("CANDIDATO", "NOVA EDIÇÃO", "- MOVIMENTO"))]
    ok(len(linhas) == 5 and all(len(l) < 520 for l in linhas), linhas)
    # o inicio.py le estes campos do bancas.json
    ok({i for c in res["concursos"] for i in c.get("coberto") or []} == {"tjsc_juiz", "trf1_juiz"}
       and {i for c in res["concursos"] for i in c.get("registros") or []} == {"tjsc_juiz", "trf1_juiz"}, "cobertos")
    json.dumps(res, ensure_ascii=False)


@teste
def coleta_paralela_com_teto_e_falha():
    """Uma pagina que levanta excecao e outra que nao responde no teto nao derrubam as demais (GETs em paralelo)."""
    extra = {B + "/juiztjba": RuntimeError("conexão recusada"),
             B + "/concursos/dperj2026": (3.0, 200, pagina_html("x", []))}
    t0 = time.time()
    with trocar(TETO_PAGINAS_S=0.6):
        res, rede, cs = coletar(rede_fgv(extra=extra))
    ok(time.time() - t0 < 2.5, "teto respeitado: %.1f s" % (time.time() - t0))
    ok(cs["juiztjba"]["exibir"] == "nao_lida" and cs["dperj2026"]["exibir"] == "nao_lida"
       and cs["dperj2026"]["http"] == 0, (cs["juiztjba"].get("http"), cs["dperj2026"].get("http")))
    ok(cs["tjscjuiz26"]["coberto"] == ["tjsc_juiz"], "as outras seguem")
    ok("2 páginas não lidas (rede/tempo)" in saida(res), saida(res))
    # pagina de registro que nao responde: sai completa, com o aviso, e nao cobre
    extra = {B + "/concursos/tjscjuiz26": (500, "")}
    res, _, cs = coletar(rede_fgv(extra=extra))
    ok(cs["tjscjuiz26"]["exibir"] == "registro" and cs["tjscjuiz26"]["coberto"] == []
       and "página não lida (http 500)" in saida(res), saida(res))


@teste
def listagem_ilegivel_le_os_vinculados():
    """rev1 C3: a listagem 200 sem o bloco da view (view renomeada) nao derruba as paginas com banca_slug: lidas
    assim mesmo, http = 200, aviso honesto (nao "fora da listagem: confira se acabou"); sem pagina nenhuma: nao lida,
    com o motivo da listagem (antes: "página não lida (http 200)")."""
    renomeada = "<html><div class='view-id-concursos_abertos'>...</div></html>"
    extra = {B + "/concursos" + ("?page=%d" % p if p else ""): (200, renomeada) for p in range(30)}
    res, rede, cs = coletar(rede_fgv(extra=extra))
    ok(res["http"] == 200 and set(cs) == {"tjscjuiz26", "trf1juiz25"}, (res["http"], sorted(cs)))
    ok(cs["tjscjuiz26"]["coberto"] == ["tjsc_juiz"] and cs["trf1juiz25"]["coberto"] == ["trf1_juiz"]
       and not cs["trf1juiz25"].get("fora_da_listagem"), [c.get("coberto") for c in cs.values()])
    ok(set(bancas.carimbos(res, REGS, HOJE)) == {"tjsc_juiz", "trf1_juiz"}, "carimbo dos vinculados")
    txt = saida(res)
    ok("sem a listagem hoje (listagem ilegível: http 200 sem o bloco de concursos em andamento): só as páginas com "
       "banca_slug foram lidas" in txt and "confira se o concurso acabou" not in txt
       and "listagem incompleta" not in txt, txt)
    # listagem ilegivel e as paginas vinculadas fora do ar: "nao lida", com o motivo verdadeiro
    for slug in ("tjscjuiz26", "trf1juiz25"):
        extra[B + "/concursos/" + slug] = (500, "")
        extra[B + "/" + slug] = (500, "")
    res, _, _ = coletar(rede_fgv(extra=extra))
    ok(res["http"] == 0 and res["concursos"] == [] and "página não lida (listagem ilegível: http 200 sem o bloco" in
       saida(res), (res["http"], saida(res)))
    # sem registro vinculado: volta cedo, sem pagina nenhuma (como antes), com o motivo
    sem = [dict(r, banca_slug="") for r in REGS]
    res, rede, _ = coletar(rede_fgv(extra=extra), regs=sem)
    ok(res["concursos"] == [] and res["erro"].startswith("listagem ilegível")
       and not any("/concursos/" in u and "?page" not in u and not u.endswith("/concursos") for u in rede.pedidos),
       rede.pedidos)


@teste
def teto_limita_o_processo():
    """rev1 C5: o teto do paralelo() limita o processo (threads daemon), e o curl/pdftotext de dentro dele usam so
    o que resta do teto (antes: -m 60 e pdftotext 60 s; o interpretador esperava as threads na saida)."""
    import subprocess as sp
    codigo = ("import sys, time; sys.path.insert(0, %r); import bancas; t = time.time(); "
              "r = bancas.paralelo(lambda x: time.sleep(x) or x, [0.2, 8], 2, 1.5); "
              "print(r, round(time.time() - t, 1))" % WORK)
    t0 = time.time()
    r = sp.run([sys.executable, "-c", codigo], capture_output=True, text=True, timeout=30)
    ok(r.stdout.startswith("[0.2, None]") and time.time() - t0 < 5, (r.stdout, r.stderr[-300:], time.time() - t0))
    chamadas, real = [], bancas.subprocess.run

    def falso(cmd, **kw):
        chamadas.append((cmd, kw.get("timeout")))
        if cmd[0] == "pdftotext":
            return sp.CompletedProcess(cmd, 0, b"texto do edital", b"")
        raise OSError("sem rede no teste")
    bancas.subprocess.run = falso
    try:
        bancas.paralelo(lambda u: bancas.fetch(u, timeout=40), ["https://x/a"], 1, 3)
        cmd, tmo = chamadas[-1]
        ok(int(cmd[cmd.index("-m") + 1]) <= 3 and tmo <= 8, chamadas[-1])
        bancas.fetch("https://x/b", timeout=40)                 # fora do paralelo: o padrao
        cmd, _ = chamadas[-1]
        ok(cmd[cmd.index("-m") + 1] == "40", cmd)
        orig_fetch = bancas.fetch
        bancas.fetch = lambda url, binario=False, timeout=40: (200, b"%PDF-1.4 x")
        try:
            r = bancas.paralelo(bancas.texto_pdf, ["https://x/e.pdf"], 1, 2)
        finally:
            bancas.fetch = orig_fetch
        ok(r == [("texto do edital", "")] and chamadas[-1][0][0] == "pdftotext" and chamadas[-1][1] <= 2, chamadas[-1])
    finally:
        bancas.subprocess.run = real


# ------------------------------------------------------------------ vinculo e travas (analisar direto)
@teste
def vinculo_pela_fonte_sem_banca_slug():
    """Sem banca_slug, a fonte/url_oficial do registro = a pagina ou um PDF dela vincula (transicao); cargo contrario
    no slug/titulo nao vincula; o registro com banca_slug nao entra por fonte."""
    arqs = [("2026-11-13", "2ª Retificação", PDF + "retificacao-tjap.pdf"), ("2026-10-05", "Edital", PDF + "ed-tjap.pdf")]
    base = {"id": "tjap_juiz", "bloco": "Magistratura Estadual", "linha": "TJAP — Juiz", "selo": "EM ANDAMENTO",
            "verificado_em": "2026-11-20"}
    for fonte in (B + "/concursos/tjap26", PDF + "retificacao-tjap.pdf", B + "/concursos/tjap26/"):
        c = pag("tjap26", "Concurso Público para o TJAP - Juiz de Direito Substituto", arqs)
        r = bancas.analisar([c], HOJE, [dict(base, fonte=fonte)], {}, ler=lambda u: ("", ""))
        ok(r[0]["coberto"] == ["tjap_juiz"] and r[0]["vinculo"] == "fonte", (fonte, r[0].get("vinculo")))
        ok('registro tjap_juiz [vínculo pela fonte: grave banca_slug="tjap26"]' in saida(
            {"http": 200, "concursos": r}), "dica do banca_slug")
    c = pag("tjapservidores26", "Concurso Público para o TJAP - Servidores", arqs)
    r = bancas.analisar([c], HOJE, [dict(base, fonte=PDF + "retificacao-tjap.pdf")], {}, ler=lambda u: ("", ""))
    ok(r[0]["coberto"] == [] and r[0]["mesma_sigla"] == ["tjap_juiz"], "cargo contrário")
    c = pag("tjap26", "Concurso Público para o TJAP - Juiz de Direito Substituto", arqs)
    r = bancas.analisar([c], HOJE, [dict(base, fonte=B + "/concursos/tjap26", banca_slug="tjapjuiz27")], {},
                        ler=lambda u: ("", ""))
    ok(r[0]["coberto"] == [] and r[0]["exibir"] == "outros", "banca_slug manda: %r" % r[0]["exibir"])


@teste
def travas_de_ciclo_e_candidatos():
    tjsc = [{"id": "tjsc_juiz", "bloco": "Magistratura Estadual", "linha": "TJSC — Juiz Substituto", "selo": "EM ANDAMENTO",
             "verificado_em": "2026-11-20", "fonte": "secundária"}]
    a25 = pag("tjscjuiz25", TIT_TJSC + " - Juiz Substituto (2025)", PAGINAS["tjscjuiz25"][1])
    a26 = pag("tjscjuiz26", TIT_TJSC + " - Juiz Substituto (2026)", PAGINAS["tjscjuiz26"][1])
    # com banca_slug: tjscjuiz25 + tjscjuiz26 -> o tjsc_juiz continua coberto (antes: "2 páginas", nenhuma cobria)
    r = bancas.analisar([a25, a26], HOJE, [dict(tjsc[0], banca_slug="tjscjuiz26")], {}, ler=ler_falso)
    ok(r[1]["coberto"] == ["tjsc_juiz"] and r[0]["coberto"] == [] and "incerto" not in r[0], [c.get("incerto") for c in r])
    # sem banca_slug nem fonte: as duas sao CANDIDATAS (o orquestrador escolhe), nenhuma cobre
    a25 = pag("tjscjuiz25", TIT_TJSC + " - Juiz Substituto (2025)", PAGINAS["tjscjuiz25"][1])   # analisar() muda a pagina
    a26 = pag("tjscjuiz26", TIT_TJSC + " - Juiz Substituto (2026)", PAGINAS["tjscjuiz26"][1])
    r = bancas.analisar([a25, a26], HOJE, copy.deepcopy(tjsc), {}, ler=ler_falso)
    ok([c["candidatos"] for c in r] == [["tjsc_juiz"], ["tjsc_juiz"]] and all(c["coberto"] == [] for c in r), r)
    txt = saida({"http": 200, "concursos": r})
    ok(txt.count("CANDIDATO tjsc_juiz ←") == 2 and "DIVERGE" not in txt, txt)
    # slug do ano seguinte (sem vinculo): nao casa, nao cobre, nao diverge; sai como SEM REGISTRO (ciclo 2027)
    a27 = pag("tjscjuiz27", TIT_TJSC + " - Juiz Substituto (2027)", [
        ("2026-11-20", "Portaria da Comissão", PDF + "c27.pdf"), ("2026-11-18", "Edital", PDF + "edital-tjsc.pdf")])
    r = bancas.analisar([a27], HOJE, copy.deepcopy(tjsc), {}, ler=ler_falso)
    ok(r[0]["registros"] == [] and r[0]["coberto"] == [] and r[0]["divergencias"] == [] and r[0]["candidatos"] == []
       and r[0]["ciclo_seguinte"] == 2027 and r[0]["exibir"] == "novo", r[0])
    ok("SEM REGISTRO (ciclo 2027) → avalie como NOVO [não é tjsc_juiz: ciclo 2027]" in saida(
        {"http": 200, "concursos": r}), saida({"http": 200, "concursos": r}))
    # registro EM PLANEJAMENTO x pagina com edital antigo (dpero25 x dpe_ro): nao e candidato
    dpe_ro = [{"id": "dpe_ro", "bloco": "Defensor Público Estadual (DPE)", "selo": "EM PLANEJAMENTO",
               "linha": "DPE-RO — Defensor Público Substituto (VI concurso): comissão formada em maio/2026",
               "verificado_em": "2026-11-17", "fonte": "https://x.com/dpe-ro"}]
    p = pag("dpero25", "Concurso Público para a Defensoria Pública do Estado de Rondônia - Defensor",
            [("2026-05-14", "COMUNICADO", PDF + "com.pdf"), ("2025-03-20", "Edital", PDF + "ed-dpero.pdf")])
    r = bancas.analisar([p], HOJE, dpe_ro, {}, ler=ler_falso)
    ok(r[0]["candidatos"] == [] and "registro em planejamento × edital de 03/2025" in r[0]["edicao"], r[0].get("edicao"))
    # edicao de 2+ anos antes: nao e candidata
    p = pag("tjrr24", "Concurso Público para o Tribunal de Justiça do Estado de Roraima - Juiz",
            [("2026-11-09", "Comunicado", PDF + "rr.pdf")])
    r = bancas.analisar([p], HOJE, [{"id": "tjrr_juiz", "bloco": "Magistratura Estadual", "selo": "EM ANDAMENTO",
                                     "linha": "TJRR — Juiz", "verificado_em": "2026-11-10"}], {}, ler=ler_falso)
    ok(r[0]["candidatos"] == [] and r[0]["edicao"] == "não é tjrr_juiz: edição de 2024", r[0].get("edicao"))


@teste
def candidato_sem_cargo_edital_decide_e_escopo_do_apoio():
    """tjpb26 (titulo sem cargo): com tjpb_apoio e tjpb_juiz, o edital (Analista) deixa so o tjpb_apoio; sem o
    tjpb_apoio (removido pelo escopo), a pagina e apoio da PB: fora do escopo, so contagem (nunca 'avalie como
    NOVO')."""
    tit = "Concurso Público para Tribunal de Justiça do Estado da Paraíba"
    arqs = [("2026-11-18", "Resultado definitivo da análise dos pedidos de isenção", PDF + "tjpb-isencao.pdf"),
            ("2026-10-05", "Edital (retificado em 11/11/2026)", PDF + "edital-tjpb.pdf")]
    EDITAIS[PDF + "edital-tjpb.pdf"] = "edital-tjpb-trechos.txt"
    juiz = {"id": "tjpb_juiz", "bloco": "Magistratura Estadual", "selo": "EM PLANEJAMENTO", "verificado_em": "2026-11-17",
            "linha": "TJPB — Juiz Substituto (54º concurso): comissão instituída", "fonte": "https://direcao.com/tjpb"}
    apoio = {"id": "tjpb_apoio", "bloco": "Quadro de apoio", "selo": "PENDÊNCIA DE VERIFICAÇÃO",
             "verificado_em": "2026-11-17", "linha": "TJPB — Analista Judiciário", "fonte": "secundária"}
    r = bancas.analisar([pag("tjpb26", tit, arqs)], HOJE, [juiz, apoio], {}, ler=ler_falso)
    ok(r[0]["candidatos"] == ["tjpb_apoio"] and not r[0].get("cargo_incerto") and r[0]["exibir"] == "candidato", r[0])
    r = bancas.analisar([pag("tjpb26", tit, arqs)], HOJE, [juiz], {}, ler=ler_falso)
    ok(r[0]["candidatos"] == [] and r[0]["mesma_sigla"] == ["tjpb_juiz"] and r[0]["exibir"] == "fora_escopo", r[0])
    txt = saida({"http": 200, "concursos": r})
    ok("tjpb26" not in txt and "1 fora do escopo (apoio só Sul/Sudeste)" in txt, txt)
    # apoio no escopo (MG) com abertura recente: SEM REGISTRO → avalie como NOVO
    p = pag("tjmgservidor26", "Concurso Público para o Tribunal de Justiça do Estado de Minas Gerais - Servidores",
            [("2026-11-19", "Edital", PDF + "edital-tjscservidor.pdf")])
    r = bancas.analisar([p], HOJE, [], {}, ler=ler_falso)
    ok(r[0]["exibir"] == "novo" and "SEM REGISTRO → avalie como NOVO" in saida({"http": 200, "concursos": r}), r[0])


@teste
def enam_registro_e_nova_edicao():
    enam = [{"id": "enam", "bloco": "Magistratura Estadual", "linha": "ENAM 6ª edição (2026.2): prova em 29/11",
             "selo": "PROVA EM BREVE", "verificado_em": "2026-11-21", "banca_slug": "exames/enam/6exame",
             "fonte": B + "/exames/enam/6exame",
             "prazos": [{"data": "2026-11-29", "evento": "prova", "tipo": "prova", "confirmado": True}]}]
    e6 = pag("exames/enam/6exame", "Exame Nacional da Magistratura - ENAM (2026.2)", PAGINAS["exames/enam/6exame"][1])
    e7 = pag("exames/enam/7exame", "Exame Nacional da Magistratura - ENAM (2027.1)",
             [("2026-11-20", "Edital", PDF + "edital-enam7.pdf")])
    e5 = pag("exames/enam/5exame", "Exame Nacional da Magistratura - ENAM (2026.1)", PAGINAS["exames/enam/5exame"][1])
    r = bancas.analisar([e6, e7, e5], HOJE, enam, {}, ler=ler_falso)
    ok(r[0]["coberto"] == ["enam"] and r[0]["exibir"] == "registro", r[0].get("coberto"))
    ok(r[1]["exibir"] == "nova_edicao" and r[1]["nova_edicao"] == {"id": "enam", "vinculada": "exames/enam/6exame"}, r[1])
    ok(r[2]["exibir"] == "outros" and "enam" in r[2]["edicao"], r[2].get("edicao"))
    txt = saida({"http": 200, "concursos": r})
    ok('NOVA EDIÇÃO? exames/enam/7exame |' in txt and 'banca_slug="exames/enam/7exame"' in txt, txt)
    # registro enam gravado sem banca_slug (e com fonte de fora): so a edicao mais nova e candidata
    sem = [dict(enam[0], banca_slug="", fonte="https://www.enfam.jus.br/enam")]
    e6 = pag("exames/enam/6exame", "Exame Nacional da Magistratura - ENAM (2026.2)", PAGINAS["exames/enam/6exame"][1])
    e5 = pag("exames/enam/5exame", "Exame Nacional da Magistratura - ENAM (2026.1)", PAGINAS["exames/enam/5exame"][1])
    r = bancas.analisar([e5, e6], HOJE, sem, {}, ler=ler_falso)
    ok(r[1]["candidatos"] == ["enam"] and r[0]["candidatos"] == [] and r[0]["edicao"] == "edição anterior de enam",
       [(c["slug"], c["candidatos"], c.get("edicao")) for c in r])
    ok(set(bancas.ordinais("ENAM 6ª edição (2026.2)")) == {6}, "edição")


@teste
def nova_edicao_de_vinculado_sem_ano():
    """rev1 C4: registro vinculado a slug sem ano (trf2juiz): a pagina trf2juiz27 e NOVA EDICAO? (antes: "edição
    anterior ou outra página"); a de 2+ anos antes continua edicao anterior; com ano nos dois, como antes."""
    trf2 = [{"id": "trf2_juiz", "bloco": "Magistratura Federal", "linha": "TRF2 — Juiz Federal Substituto",
             "selo": "EM ANDAMENTO", "verificado_em": "2026-11-20", "banca_slug": "trf2juiz",
             "fonte": B + "/concursos/trf2juiz"}]
    tit = "Concurso Público para o Tribunal Regional Federal da 2ª Região - Juiz Federal"
    vinc = pag("trf2juiz", tit, [("2026-11-10", "Resultado", PDF + "trf2-res.pdf")])
    nova = pag("trf2juiz27", tit + " (2027)", [("2026-11-20", "Portaria da Comissão", PDF + "trf2-27.pdf")])
    velha = pag("trf2juiz24", tit + " (2024)", [("2026-11-12", "Comunicado", PDF + "trf2-24.pdf")])
    r = bancas.analisar([vinc, nova, velha], HOJE, copy.deepcopy(trf2), {}, ler=ler_falso)
    ok(r[0]["coberto"] == ["trf2_juiz"], r[0].get("coberto"))
    ok(r[1]["exibir"] == "nova_edicao" and r[1]["nova_edicao"] == {"id": "trf2_juiz", "vinculada": "trf2juiz"}
       and "edicao" not in r[1], (r[1]["exibir"], r[1].get("edicao")))
    ok(r[2]["exibir"] != "nova_edicao" and "trf2_juiz" in r[2]["edicao"], (r[2]["exibir"], r[2].get("edicao")))
    ok('NOVA EDIÇÃO? trf2juiz27 |' in saida({"http": 200, "concursos": r}), saida({"http": 200, "concursos": r}))


# ------------------------------------------------------------------ estado (URLs vistas)
@teste
def estado_parcial_das_paginas_sem_registro():
    """Pagina sem registro guarda so as URLs recentes (entrada `parcial`, podada); no dia seguinte o mesmo arquivo nao
    e movimento; vinculada depois, a entrada parcial nao serve de URLs vistas (base pela data); registro: tudo."""
    est = {}
    res, _, cs = coletar(estado=est)
    n = bancas.atualizar_estado(est, res, HOJE)
    fgv = est["bancas"]["fgv"]
    ok(fgv["juiztjba"] == {"urls": {PDF + "tjba-sessao.pdf": "2026-11-21"}, "parcial": True, "lido_em": "2026-11-21"},
       fgv.get("juiztjba"))
    ok(len(fgv["tjscjuiz26"]["urls"]) == 3 and "parcial" not in fgv["tjscjuiz26"], fgv["tjscjuiz26"])
    ok("tjpa25" not in fgv and "tjscjuiz25" not in fgv, "contagem não grava estado")
    ok(bancas.atualizar_estado(est, res, HOJE) == 0 and n > 0, "idempotente")
    dia2 = date(2026, 11, 23)
    res2 = bancas.coletar(dia2, copy.deepcopy(REGS), est, buscar=rede_fgv(), ler=ler_falso)
    cs2 = {c["slug"]: c for c in res2["concursos"]}
    ok(cs2["juiztjba"]["exibir"] == "outros" and cs2["mprjpromotor2026"]["exibir"] == "outros", "visto ontem")
    ok("- MOVIMENTO" not in saida(res2), saida(res2))
    # pagina que passa a ter registro: a entrada parcial nao vale como URLs vistas
    regs = copy.deepcopy(REGS) + [{"id": "tjba_juiz", "bloco": "Magistratura Estadual", "linha": "TJBA — Juiz",
                                   "selo": "EM ANDAMENTO", "verificado_em": "2026-11-18", "banca_slug": "juiztjba",
                                   "fonte": "https://x.com/tjba"}]
    res3 = bancas.coletar(dia2, regs, est, buscar=rede_fgv(), ler=ler_falso)
    c3 = next(c for c in res3["concursos"] if c["slug"] == "juiztjba")
    ok(c3["coberto"] == ["tjba_juiz"] and c3["base_novos"] == "data (sem estado)"
       and [a["titulo"][:13] for a in c3["novos_arquivos"]] == ["Sessão Públic"], c3.get("base_novos"))
    bancas.atualizar_estado(est, res3, dia2)
    ok("parcial" not in fgv["juiztjba"] and len(fgv["juiztjba"]["urls"]) == 2, fgv["juiztjba"])
    # poda: parcial sem URL recente some
    bancas.atualizar_estado(est, {"http": 200, "concursos": []}, date(2026, 12, 10))
    ok("mprjpromotor2026" not in fgv and "juiztjba" in fgv, sorted(fgv))


# ------------------------------------------------------------------ trechos do edital
@teste
def trechos_alternativos_so_quando_o_principal_falha():
    tjpb = bancas.trechos(norm(fx("edital-tjpb-trechos.txt")))
    ok(tjpb["vagas"].startswith("provimento de 50 (cinquenta) cargos efetivos de Analista Judiciário")
       and tjpb["remuneração"] == "VENCIMENTO: R$ 7.526,14"
       and tjpb["prova objetiva"].endswith("serão realizadas no dia 24 de janeiro de 2027, das 13h às 18h")
       and tjpb["inscrições"] == "das 16h do dia 20 de outubro de 2026 até às 16h do dia 18 de novembro de 2026", tjpb)
    ok(list(tjpb) == ["vagas", "inscrições", "taxa", "remuneração", "prova objetiva"], list(tjpb))
    enam = bancas.trechos(norm(fx("edital-enam-trechos.txt")))
    ok(enam["prova objetiva"] == "A prova, de caráter exclusivamente eliminatório, será realizada na data provável de 29 "
       "de novembro de 2026, com duração de 5h, das 13h às 18h", enam)
    # TJSC e TJAP (o padrao principal ja casava): saida igual a de antes, byte a byte
    ok(bancas.trechos(norm(fx("edital-tjsc-trechos.txt"))) == {
        "vagas": "provimento de 15 (quinze) vagas para o cargo de Juiz Substituto do Tribunal de Justiça do Estado de "
                 "Santa Catarina e form",
        "inscrições": "das 16h do dia 19 de outubro de 2026 até às 16h do dia 26 de novembro de 2026",
        "taxa": "taxa de inscrição R$ 340,00",
        "remuneração": "subsídio do cargo de Juiz Substituto do Estado de Santa Catarina é de R$ 34.083,15",
        "prova objetiva": "Prova Objetiva Seletiva, de caráter eliminatório e classificatório está prevista para o dia 31 "
                          "de janeiro de 2027"}, "TJSC mudou")
    with open(os.path.join(FIX_EST, "tjap-edital-consolidado-trechos.txt"), encoding="utf-8") as f:
        tjap = bancas.trechos(norm(f.read()))
    ok(json.dumps(tjap, ensure_ascii=False) == json.dumps({
        "vagas": "provimento de 15 (quinze) vagas e a formação de cadastro de reserva para o cargo de Juiz de Direito "
                 "Substituto do Tribuna",
        "inscrições": "das 16h do dia 13 de outubro de 2026 até às 16h do dia 18 de novembro de 2026",
        "taxa": "taxa de inscrição R$ 358,77",
        "remuneração": "subsídio do cargo de Juiz de Direito Substituto do Estado do Amapá é de R$ 35.877,27",
        "prova objetiva": "Prova Objetiva Seletiva, de caráter eliminatório e classificatório, está prevista para o dia "
                          "24 de janeiro de 2027"}, ensure_ascii=False), "TJAP mudou: %r" % tjap)
    ok(bancas.TRECHOS[1][0] == "inscrições" and "LEIA" not in bancas.TRECHOS[1][1], "índice do LEIA-SE")


# ------------------------------------------------------------------ helper: banca_slug
@teste
def helper_banca_slug_formato_e_unicidade():
    led = {"concursos": [
        {"id": "tjsc_juiz", "bloco": "Magistratura Estadual", "linha": "TJSC — Juiz", "selo": "EM ANDAMENTO",
         "verificado_em": "2026-11-20", "fonte": B + "/concursos/tjscjuiz26", "banca_slug": "tjscjuiz26"},
        {"id": "dpe_rj", "bloco": "Defensor Público Estadual (DPE)", "linha": "DPE-RJ — Defensor", "selo": "EM ANDAMENTO",
         "verificado_em": "2026-11-11", "fonte": "https://ceisc.com.br/x"}],
        "pendencias_vivas": [], "fontes": [], "armadilhas": [], "niveis_de_esforco": {"saudavel": ""}}

    def erros(conc):
        return uh.validar_ledger_updates({"concursos": conc}, led, "2026-11-21")
    ok(erros({"dpe_rj": {"banca_slug": "dperj2026"}}) == [], erros({"dpe_rj": {"banca_slug": "dperj2026"}}))
    ok(erros({"enam": {"bloco": "Magistratura Estadual", "linha": "ENAM 6ª edição", "selo": "PROVA EM BREVE",
                       "verificado_em": "2026-11-21", "fonte": B + "/exames/enam/6exame",
                       "banca_slug": "exames/enam/6exame"}}) == [], "ENAM novo com banca_slug")
    ok(erros({"dpe_rj": {"banca_slug": ""}}) == [], "\"\" desfaz o vínculo")
    for ruim in ("DPERJ2026", "concursos/dperj2026", "https://conhecimento.fgv.br/concursos/dperj2026", "dperj 2026",
                 "/dperj2026", None, 26):
        e = erros({"dpe_rj": {"banca_slug": ruim}})
        ok(len(e) == 1 and "banca_slug" in e[0] and "fora do formato" in e[0], (ruim, e))
    e = erros({"dpe_rj": {"banca_slug": "tjscjuiz26"}})
    ok(len(e) == 1 and "também é de tjsc_juiz" in e[0], e)
    ok(erros({"dpe_rj": {"banca_slug": "tjscjuiz26"}, "tjsc_juiz": {"remover": True, "desfecho": "encerrado"}}) == [],
       "remover libera o slug")
    ok(erros({"dpe_rj": {"banca_slug": "tjscjuiz26"}, "tjsc_juiz": {"banca_slug": "tjscjuiz27"}}) == [], "troca")
    e = erros({"dpe_rj": {"banca_slug": "x26"}, "enam": {"bloco": "Magistratura Estadual", "linha": "ENAM",
                                                         "selo": "EM ANDAMENTO", "verificado_em": "2026-11-21",
                                                         "fonte": "https://x.br", "banca_slug": "x26"}})
    ok(len(e) == 2, e)
    # aplicado, vai para o registro (campo editavel); o legado sem banca_slug continua passando
    led2 = copy.deepcopy(led)
    uh.aplicar_updates(led2, {"concursos": {"dpe_rj": {"banca_slug": "dperj2026"}}}, "2026-11-21", lambda m: None)
    ok(next(c for c in led2["concursos"] if c["id"] == "dpe_rj")["banca_slug"] == "dperj2026", "aplicado")
    ok(erros({"dpe_rj": {"linha": "DPE-RJ — Defensor: FGV"}}) == [], "sem banca_slug")


@teste
def saida_compativel_com_bancas_json_antigo():
    """bancas.json de antes (sem exibir/listagem): tudo completo, como antes, sem CANDIDATO/MOVIMENTO."""
    with open(os.path.join(FIX_EST, "bancas-1611.json"), encoding="utf-8") as f:
        b16 = json.load(f)
    txt = saida(b16)
    ok(txt.startswith("BANCA FGV (fonte OFICIAL") and ": 5 concursos jurídicos\n" in txt
       and "- tjap26 | " in txt and "registro tjap_juiz |" in txt and "CANDIDATO" not in txt and "MOVIMENTO" not in txt,
       txt)
    est = {}
    ok(bancas.atualizar_estado(est, b16, "2026-11-16") > 0
       and not any(e.get("parcial") for e in est["bancas"]["fgv"].values()), "antigo: tudo completo")


def main():
    for t in TESTES:
        try:
            t()
            print("OK      %s" % t.__name__)
        except Exception:  # noqa: BLE001
            FALHAS.append(t.__name__)
            print("FALHOU  %s\n%s" % (t.__name__, traceback.format_exc()))
    shutil.rmtree(TMPDIR, ignore_errors=True)
    print("\n%d testes, %d falha(s)" % (len(TESTES), len(FALHAS)))
    sys.exit(1 if FALHAS else 0)


if __name__ == "__main__":
    main()
