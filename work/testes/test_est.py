#!/usr/bin/env python3
# =====================================================================
# test_est.py — testes do grupo EST (sem pytest, sem rede):
#   feriados.py (nacionais, moveis, Lei 5.010, dias uteis); selos.py (selo por
#   data com datas simuladas 17, 18 e 19/11/2026: TJPB e TJAP; precedencia;
#   inicio conhecido; ALERTA de prorrogacao; fonte oficial; termos relativos;
#   candidato a remocao; mudou_em); bancas.py (pagina real do TJAP de 16/11:
#   2a Retificacao listada e DIVERGE DO REGISTRO com o registro antigo; URLs
#   vistas; LEIA-SE de retificacao; carimbos); Update-Historico.py (validacao
#   E9, mudou_em, vinculo de pendencia, selo por data e carimbo persistidos,
#   E2, --refazer, fontes_status, ALERTA_ECONOMIA e troca de modelo, E13);
#   medir_uso.py (tokens por tipo, custo relativo, fechamento, relancamento);
#   aguardar_coleta.py (disparo, fallback, SOURCE_STATUS); paginas_oficiais.py;
#   inicio.py (janela/feriados/--extra/after: do Gmail/saida enxuta/alertas).
#   Correcoes da revisao adversarial: selo copiado x decidido, DIVERGE sem carimbo,
#   E9 (dominio_oficial/url_oficial), paginas_oficiais ausente, feriado como dia de
#   edicao, finalizar.sh (remontagem do execucao.json editado; reaplicacao com a
#   arvore limpa) num repositorio git descartavel com os dados do MON de 17/11.
# USO: python3 work/testes/test_est.py   (imprime OK/FALHOU; sai != 0 em falha)
# Tudo roda em pastas temporarias (ROBOZINHO_TMP proprio); rede simulada.
# =====================================================================

import contextlib
import copy
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
from datetime import date

AQUI = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.dirname(AQUI)
FIX = os.path.join(AQUI, "fixtures", "est")
TMPDIR = tempfile.mkdtemp(prefix="robozinho-est-")
os.environ["ROBOZINHO_TMP"] = TMPDIR
sys.path.insert(0, WORK)

import feriados          # noqa: E402
import selos             # noqa: E402
import bancas            # noqa: E402
import medir_uso         # noqa: E402
import aguardar_coleta   # noqa: E402
import paginas_oficiais  # noqa: E402

_spec = importlib.util.spec_from_file_location("uh", os.path.join(WORK, "Update-Historico.py"))
uh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(uh)

TESTES, FALHAS = [], []


def teste(f):
    TESTES.append(f)
    return f


def ok(cond, msg):
    if not cond:
        raise AssertionError(msg)


def fx(nome):
    with open(os.path.join(FIX, nome), encoding="utf-8") as f:
        return f.read()


def regs(commit):
    return json.loads(fx("concursos-%s.json" % commit))["concursos"]


def reg(commit, ident):
    return copy.deepcopy(next(c for c in regs(commit) if c["id"] == ident))


D = date.fromisoformat


# ------------------------------------------------------------------ feriados
@teste
def feriados_basico():
    ok(feriados.pascoa(2026) == D("2026-04-05") and feriados.pascoa(2027) == D("2027-03-28"), "Páscoa")
    f = feriados.feriado(D("2026-11-20"))
    ok(f and f["nacional"] and "Consciência Negra" in f["nome"], "20/11 nacional: %r" % f)
    ok(feriados.feriado(D("2026-12-08"))["tipo"] == "justica_federal", "08/12 é da JF (Lei 5.010)")
    ok(not feriados.eh_feriado_nacional(D("2026-12-08")), "08/12 não desconta dia útil")
    ok(feriados.feriado(D("2027-02-08"))["tipos"] == ["justica_federal", "ponto_facultativo"], "Carnaval 2027")
    ok(feriados.feriado(D("2027-03-26"))["nacional"], "Sexta-feira Santa 2027")
    ok(feriados.feriado(D("2026-12-24"))["tipo"] == "justica_federal", "recesso JF 24/12")
    ok(feriados.dias_uteis_entre(D("2026-11-19"), D("2026-11-23")) == 1, "20/11 (sex) não é útil")
    ok(feriados.uteis_sem_registro(D("2026-11-16"), D("2026-11-19")) == [D("2026-11-17"), D("2026-11-18")],
       "dias úteis sem registro")
    # a edição sai em feriado: o feriado conta como dia de edição (sem registro = edição faltante); fim de semana não
    ok(feriados.uteis_sem_registro(D("2026-11-19"), D("2026-11-23")) == [D("2026-11-20")], "feriado é dia de edição")
    ok(feriados.dias_de_edicao_entre(D("2026-11-19"), D("2026-11-23")) == 2, "gap conta o feriado")
    ok(feriados.uteis_sem_registro(D("2027-04-20"), D("2027-04-22")) == [D("2027-04-21")], "Tiradentes (qua)")
    ok(feriados.uteis_sem_registro(D("2026-11-20"), D("2026-11-23")) == [], "fim de semana não conta")
    ok(feriados.agrupar(feriados.no_intervalo(D("2026-12-26"), D("2026-12-31")))[0].startswith("26/12 a 31/12"),
       "agrupamento do recesso")


# ------------------------------------------------------------------ selos
CTX = {"tjpb_apoio": "2026-11-12", "tjap_juiz": "2026-11-13"}   # última retificação na página da FGV


def cadeia(r, datas, banca=True):
    """Aplica o selo por data dia a dia, persistindo como o helper; devolve os selos."""
    out = []
    for d in datas:
        s, m = selos.selo_por_data(r, D(d), banca_lida_hoje=banca, ultima_retificacao=CTX.get(r["id"]))
        if s != r["selo"]:
            ok(m and "→" in m, "mudança sem motivo: %r" % m)
        r["selo"] = s
        out.append(s)
    return out


@teste
def selo_tjpb_17_18_19():
    r = reg("2a9eac9", "tjpb_apoio")
    ok(cadeia(r, ["2026-11-17", "2026-11-18", "2026-11-19"]) ==
       ["ENCERRA EM BREVE", "ENCERRA HOJE", "INSCRIÇÕES ENCERRADAS"], "TJPB: %r" % r)


@teste
def selo_tjap_nao_regride():
    r = reg("2a9eac9", "tjap_juiz")
    ok(cadeia(r, ["2026-11-16", "2026-11-17", "2026-11-18", "2026-11-19", "2026-11-20"]) ==
       ["ENCERRA EM BREVE", "ENCERRA EM BREVE", "ENCERRA HOJE", "INSCRIÇÕES ENCERRADAS", "INSCRIÇÕES ENCERRADAS"],
       "TJAP corrigido")
    # registro antigo (13/11, ENCERRA HOJE), banca lida em 16/11 com retificação de 13/11: NÃO conclui encerradas,
    # e o ENCERRA HOJE também não fica (o leitor o leu de 13 a 16/11): PENDÊNCIA DE VERIFICAÇÃO com o que fazer
    r = reg("2426d11", "tjap_juiz")
    s, m = selos.selo_por_data(r, D("2026-11-16"), banca_lida_hoje=True, ultima_retificacao="2026-11-13")
    ok(s == selos.SELO_SEM_CONFIRMACAO and "prorrogação não confirmada" in m and "retificação em 13/11" in m
       and m.startswith("ENCERRA HOJE → PENDÊNCIA DE VERIFICAÇÃO"), "TJAP antigo: %r %r" % (s, m))
    # registro de 16/11 (INSCRIÇÕES ENCERRADAS sem prazo de inscrição): fica como está
    ok(selos.selo_por_data(reg("b80a3bd", "tjap_juiz"), D("2026-11-17"), True, "2026-11-13") ==
       ("INSCRIÇÕES ENCERRADAS", None), "b80a3bd")


@teste
def selo_vencido_sem_confirmacao():
    r = reg("2a9eac9", "tjpb_apoio")
    r["selo"] = "ENCERRA HOJE"
    s, m = selos.selo_por_data(r, D("2026-11-19"), banca_lida_hoje=False)
    ok(s == selos.SELO_SEM_CONFIRMACAO and "não foi lida" in m and "INSCRIÇÕES ENCERRADAS" in m, "sem banca: %r %r" % (s, m))
    # DPE-SP (fora da FGV): ENCERRA HOJE com prazo de 11/11 nunca mais sai como ENCERRA HOJE
    dpe = {"id": "dpe_sp", "selo": "ENCERRA HOJE", "fonte": "https://www.defensoria.sp.def.br",
           "prazos": [{"data": "2026-11-11", "evento": "fim das inscrições", "confirmado": True}]}
    for d in ("2026-11-12", "2026-11-16", "2026-12-31"):
        ok(selos.selo_por_data(dpe, D(d))[0] == selos.SELO_SEM_CONFIRMACAO, "DPE-SP %s" % d)
    # depois do rebaixamento o selo sai da família: nada mais muda sozinho; o orquestrador decide
    ok(selos.selo_por_data(dict(dpe, selo=selos.SELO_SEM_CONFIRMACAO), D("2026-11-17")) ==
       (selos.SELO_SEM_CONFIRMACAO, None), "estável")
    # prova confirmada em até 14 dias vence o rebaixamento (precedência)
    p = dict(dpe, prazos=dpe["prazos"] + [{"data": "2026-11-22", "evento": "prova objetiva", "confirmado": True}])
    ok(selos.selo_por_data(p, D("2026-11-16"))[0] == "PROVA EM BREVE", "PROVA EM BREVE vence")
    ok(selos.selo_escrito({"selo": "ENCERRA EM BREVE"}, {"selo": "ENCERRA EM BREVE"}) is False, "cópia")
    ok(selos.selo_escrito({"selo": "INSCRIÇÕES ENCERRADAS"}, {"selo": "ENCERRA HOJE"}), "decisão")
    ok(selos.selo_escrito({"selo": "EM PLANEJAMENTO"}, None) and not selos.selo_escrito({"linha": "x"}, None), "novo")


@teste
def selo_regras():
    base = {"id": "x", "linha": "X — Juiz: banca FGV", "selo": "ENCERRA EM BREVE",
            "prazos": [{"data": "2026-12-20", "evento": "fim das inscrições", "confirmado": True}]}
    ok(selos.selo_por_data(base, D("2026-11-17")) == ("ENCERRA EM BREVE", None), "sem início: não vira ABERTAS")
    b = dict(base, linha="X — Juiz: inscrições das 16h de 10/11 até 16h de 20/12")
    ok(selos.selo_por_data(b, D("2026-11-17"))[0] == "INSCRIÇÕES ABERTAS", "início na linha ≤ hoje")
    ok(selos.selo_por_data(dict(base, selo="EM PLANEJAMENTO"), D("2026-12-20")) == ("EM PLANEJAMENTO", None),
       "fora da família")
    ok(selos.selo_por_data(dict(base, selo="EDITAL PUBLICADO"), D("2026-12-20"))[0] == "EDITAL PUBLICADO",
       "EDITAL PUBLICADO não é da família")
    c = dict(base, prazos=[{"data": "2026-11-17", "evento": "fim das inscrições", "confirmado": True},
                           {"data": "2026-11-20", "evento": "prova objetiva", "confirmado": True}])
    ok(selos.selo_por_data(c, D("2026-11-17"))[0] == "ENCERRA HOJE", "precedência: HOJE vence PROVA EM BREVE")
    c["selo"] = "INSCRIÇÕES ENCERRADAS"
    ok(selos.selo_por_data(c, D("2026-11-18"))[0] == "PROVA EM BREVE", "encerradas + prova em 2 dias")
    n = dict(base, prazos=[{"data": "2026-11-17", "evento": "fim das inscrições", "confirmado": False}])
    ok(selos.selo_por_data(n, D("2026-11-17")) == ("ENCERRA EM BREVE", None), "prazo a confirmar não conta")
    # derivação antes da poda: o prazo retirado hoje ainda vale para concluir
    p = dict(base, prazos=[])
    s, _ = selos.selo_por_data(p, D("2026-11-19"), True, None,
                               prazos_podados=[{"data": "2026-11-18", "evento": "fim das inscrições",
                                                "confirmado": True}])
    ok(s == "INSCRIÇÕES ENCERRADAS", "prazos_podados")
    ok(selos.classe_prazo({"evento": "pagamento da taxa até 19/11 (inscrições)"}) == "outro", "pagamento")
    ok(selos.classe_prazo({"evento": "fim das inscrições, 16h (prorrogado)"}) == "inscricoes_fim", "fim")
    # inscrição definitiva (2ª fase) e eventos acessórios da prova não são inscrição nem prova
    for ev in ("fim das inscrições definitivas", "término da inscrição definitiva", "fim da inscrição definitiva "
               "(fonte secundária)", "início da inscrição definitiva (16/10 a 06/11)", "resultado preliminar da prova "
               "objetiva", "edital de convocação para as provas", "recurso contra o gabarito da prova",
               "divulgação dos locais de prova", "vista da prova discursiva"):
        ok(selos.classe_prazo({"evento": ev}) == "outro", "outro: %s" % ev)
    for ev in ("prova objetiva", "prova objetiva (data divulgada pela banca)", "aplicação da prova objetiva",
               "provas das duas primeiras etapas (fonte secundária)"):
        ok(selos.classe_prazo({"evento": ev}) == "prova", "prova: %s" % ev)
    ok(selos.classe_prazo({"evento": "resultado da prova objetiva", "tipo": "prova"}) == "prova", "tipo explícito vence")
    tjrs = {"id": "tjrs_juiz", "selo": "INSCRIÇÕES ENCERRADAS",
            "linha": "TJRS — Juiz: inscrições das 16h de 15/09 até 16h de 14/10",
            "prazos": [{"data": "2027-03-10", "evento": "fim das inscrições definitivas", "confirmado": True}]}
    ok(selos.selo_por_data(tjrs, D("2027-02-01")) == ("INSCRIÇÕES ENCERRADAS", None) and
       selos.selo_por_data(tjrs, D("2027-03-05")) == ("INSCRIÇÕES ENCERRADAS", None), "definitiva não reabre")
    pos = {"id": "x", "selo": "INSCRIÇÕES ENCERRADAS",
           "prazos": [{"data": "2026-11-08", "evento": "prova objetiva", "confirmado": True},
                      {"data": "2026-11-25", "evento": "resultado preliminar da prova objetiva", "confirmado": True}]}
    ok(selos.selo_por_data(pos, D("2026-11-17")) == ("INSCRIÇÕES ENCERRADAS", None), "resultado não é PROVA EM BREVE")


@teste
def fontes_e_termos():
    ok(selos.fonte_oficial("https://conhecimento.fgv.br/concursos/tjap26"), "FGV")
    ok(selos.fonte_oficial("https://www.tjsp.jus.br/x") and selos.fonte_oficial("pge.rj.gov.br/concursos"), "órgãos")
    ok(selos.fonte_oficial("https://www.defensoria.sp.def.br/") and selos.fonte_oficial("https://mpsp.mp.br/"), "def/mp")
    ok(not selos.fonte_oficial("https://cj.estrategia.com/portal/?p=1"), "secundária")
    ok(not selos.fonte_oficial("secundária (busca)"), "texto")
    # E9: o dominio_oficial do registro não vale como prova (podia vir no mesmo update); banca nova entra na lista
    ok(not selos.fonte_oficial("https://www.institutonovo.org.br/ed", "institutonovo.org.br"), "banca não listada")
    ok(not selos.fonte_oficial("https://tribunadejundiai.com.br/x", "tribunadejundiai.com.br"), "secundário fora da lista")
    ok(not selos.fonte_oficial("https://blog.qconcursos.com/x", "blog.qconcursos.com"), "secundário nunca")
    ok(selos.fonte_oficial("https://www.institutoaocp.org.br/x", "qualquer.com"), "banca listada")
    ok(selos.relativos("até 16h de 13/11 (hoje); amanhã sai") == ["amanhã", "hoje"], "relativos")


@teste
def remocao_e_mudou_em():
    r = {"id": "v", "prazos": [{"data": "2026-09-01", "evento": "prova", "confirmado": True}]}
    ok(selos.candidato_remocao(r, D("2026-11-17")), "vencido há 77 dias")
    ok(not selos.candidato_remocao(r, D("2026-09-20")), "vencido há 19 dias")
    r2 = dict(r, prazos=r["prazos"] + [{"data": "2026-12-01", "evento": "resultado", "confirmado": False}])
    ok(not selos.candidato_remocao(r2, D("2026-11-17")), "etapa futura")
    ok(not selos.candidato_remocao({"id": "s", "prazos": []}, D("2026-11-17")), "sem prazo")
    execs = [{"date": "2026-11-10", "ledger_updates": {"concursos": {"a": {"linha": "x"}, "b": {"verificado_em": "y"}}}},
             {"date": "2026-11-12", "ledger_updates": {"concursos": {"a": {"selo": "EM ANDAMENTO"}}}}]
    cs = [{"id": "a"}, {"id": "b", "verificado_em": "2026-11-11"}, {"id": "c", "mudou_em": "2026-01-01"}]
    ok(selos.garantir_mudou_em(cs, execs) == 2, "preenchidos")
    ok([c.get("mudou_em") for c in cs] == ["2026-11-12", "2026-11-11", "2026-01-01"], "mudou_em %r" % cs)
    ok(selos.garantir_mudou_em(cs, lambda: 1 / 0) == 0, "idempotente (nem carrega o histórico)")


# ------------------------------------------------------------------ bancas
def ler_falso(url):
    t = fx("tjap-2a-retificacao-trecho.txt") if "retificacao" in url else fx("tjap-edital-consolidado-trechos.txt")
    return re.sub(r"\s+", " ", t), ""


def tjap(commit, estado=None, hoje="2026-11-16"):
    c = bancas.analisar_pagina({"slug": "tjap26", "titulo": "Concurso Público para Tribunal de Justiça do Estado "
                                "do Amapá - Juiz de Direito Substituto", "http": 200,
                                "url": "https://conhecimento.fgv.br/concursos/tjap26"}, fx("tjap26.html"))
    alvo = bancas.analisar([c], D(hoje), regs(commit), estado={} if estado is None else estado, ler=ler_falso)
    return {"banca": "FGV", "dominio": bancas.DOMINIO, "http": 200, "data": hoje, "concursos": alvo}


def saida(res):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        bancas.imprimir(res)
    return buf.getvalue()


@teste
def bancas_tjap_retificacao_e_diverge():
    for commit, esperado in (("b80a3bd", "linha: inscrições encerradas em 13/11"),
                             ("2426d11", "prazo 13/11/2026 fim das inscrições")):
        res = tjap(commit)
        c = res["concursos"][0]
        ok(len(c["arquivos"]) == 11, "11 arquivos na página")
        ed = next(a for a in c["arquivos"] if a["titulo"].startswith("Edital"))
        ok(ed["data_efetiva"] == "2026-11-13" and ed["data"] == "2026-10-05", "data efetiva do edital")
        ok(any(a["titulo"] == "2ª Retificação" for a in c["novos_arquivos"]), "%s: 2ª Retificação listada" % commit)
        ok(c["releitura"].startswith("arquivo novo"), "releitura: %r" % c["releitura"])
        ok(c["inscricoes"]["fim"] == "2026-11-18", "fim no edital")
        txt = saida(res)
        ok("2ª Retificação" in txt and "DIVERGE DO REGISTRO: tjap_juiz" in txt and esperado in txt,
           "%s: saída\n%s" % (commit, txt))
        ok(c["coberto"] == ["tjap_juiz"] and c["ultima_retificacao"] == "2026-11-13", "coberto/retificação")
    ok("DIVERGE" not in saida(tjap("2a9eac9")), "registro corrigido não diverge")


@teste
def bancas_urls_vistas():
    res = tjap("2a9eac9")
    est = {}
    ok(bancas.atualizar_estado(est, res, "2026-11-16") == 11, "11 arquivos vistos")
    ok(bancas.atualizar_estado(est, res, "2026-11-16") == 0, "idempotente")
    c = tjap("2a9eac9", est, hoje="2026-11-17")["concursos"][0]
    ok(c["novos_arquivos"] == [] and c["base_novos"] == "urls_vistas", "nada novo no dia seguinte")
    ok(c["releitura"].startswith("prazo do registro"), "prazo 18/11 em +1 dia relê: %r" % c["releitura"])
    txt = saida({"http": 200, "concursos": [c]})
    ok("sem arquivo novo; último: 13/11" in txt and "última retificação: 13/11" in txt, txt)
    c = tjap("2a9eac9", est, hoje="2026-11-16")["concursos"][0]
    ok(len(c["novos_arquivos"]) == 11, "re-execução no mesmo dia: vistos hoje continuam novos")
    est2 = copy.deepcopy(est)
    del est2["bancas"]["fgv"]["tjap26"]["urls"]["https://conhecimento.fgv.br/sites/default/files/concursos/retificacao-tjap.pdf"]
    c = tjap("2a9eac9", est2, hoje="2026-11-17")["concursos"][0]
    ok([a["titulo"] for a in c["novos_arquivos"]] == ["2ª Retificação"], "só a URL não vista")


@teste
def bancas_leia_se_e_carimbos():
    t = re.sub(r"\s+", " ", fx("tjap-2a-retificacao-trecho.txt"))
    ok("18 de novembro" in bancas.trecho_leia_se(t), "LEIA-SE")
    # edital não consolidado + retificação posterior: vale o LEIA-SE da retificação
    c = {"slug": "x26", "titulo": "Tribunal X - Juiz", "url": "https://conhecimento.fgv.br/concursos/x26", "http": 200,
         "arquivos": [{"data": "2026-11-13", "titulo": "2ª Retificação", "url": "https://h/retificacao-x.pdf"},
                      {"data": "2026-10-05", "titulo": "Edital", "url": "https://h/edital-x.pdf"}]}
    for a in c["arquivos"]:
        a["data_efetiva"] = bancas.data_efetiva(a)

    def ler(url):
        if "retificacao" in url:
            return re.sub(r"\s+", " ", fx("tjap-2a-retificacao-trecho.txt")), ""
        return ("das 16h do dia 13 de outubro de 2026 até às 16h do dia 13 de novembro de 2026", "")
    bancas.edital(c, ler)
    ok(c["inscricoes"]["origem"] == "retificação" and c["inscricoes"]["fim"] == "2026-11-18", "retificação: %r" % c)
    rs = [{"id": "tjap_juiz", "verificado_em": "2026-11-13", "fonte": "secundária (busca)"},
          {"id": "outro_juiz", "verificado_em": "2026-11-13",
           "fonte": "https://www.tjap.jus.br/edital.pdf", "dominio_oficial": "www.tjap.jus.br"}]
    res = {"http": 200, "dominio": bancas.DOMINIO, "concursos": [
        {"slug": "tjap26", "url": "https://conhecimento.fgv.br/concursos/tjap26", "http": 200, "arquivos": [{}],
         "coberto": ["tjap_juiz"]},
        {"slug": "outro26", "url": "https://conhecimento.fgv.br/concursos/outro26", "http": 200, "arquivos": [{}],
         "coberto": ["outro_juiz"]}]}
    car = bancas.carimbos(res, rs, D("2026-11-16"))
    ok(car["tjap_juiz"] == {"verificado_em": "2026-11-16", "fonte": "https://conhecimento.fgv.br/concursos/tjap26",
                            "dominio_oficial": "conhecimento.fgv.br"}, "carimbo secundária: %r" % car)
    ok(car["outro_juiz"] == {"verificado_em": "2026-11-16"}, "fonte oficial de outro domínio preservada")
    ctx = bancas.contexto_selos(json.loads(fx("bancas-1611.json")))     # bancas.json antigo, sem o campo
    ok(ctx["tjap_juiz"]["ultima_retificacao"] == "2026-11-13" and ctx["tjpb_apoio"]["ultima_retificacao"] == "2026-11-12",
       "contexto do bancas.json de 16/11: %r" % ctx)


# ------------------------------------------------------------------ helper: validação E9
LED = {"concursos": [{"id": "leg", "bloco": "Magistratura Estadual", "linha": "Leg — Juiz", "selo": "INSCRIÇÕES ABERTAS",
                      "verificado_em": "2026-11-10", "fonte": "secundária (busca)"},
                     {"id": "ofi", "bloco": "Magistratura Estadual", "linha": "Ofi — Juiz", "selo": "EM ANDAMENTO",
                      "verificado_em": "2026-11-10", "fonte": "https://conhecimento.fgv.br/concursos/ofi26",
                      "pendencia": "ofi_verificar"}],
       "pendencias_vivas": [{"id": "ofi_verificar", "texto": "t", "faixa": "ativa", "execucoes": 2}],
       "fontes": [{"id": "conjur", "status": "instavel", "nota": "n"}], "armadilhas": [{"id": "arm1"}],
       "niveis_de_esforco": {"saudavel": "", "instavel": ""}}


def erros(upd, **kw):
    kw.setdefault("hoje", "2026-11-17")
    return uh.validar_ledger_updates(upd, copy.deepcopy(LED), **kw)


@teste
def validacao_padrao_de_prova():
    ok(erros({"concursos": {"leg": {"verificado_em": "2026-11-17"}}}) == [], "legado intocado passa")
    ok(any("nao e selo de concurso" in e for e in erros({"concursos": {"ofi": {"selo": "NOVO"}}})), "NOVO")
    ok(any("exige fonte oficial" in e for e in erros({"concursos": {"leg": {"selo": "ENCERRA EM BREVE"}}})), "promove")
    ok(erros({"concursos": {"ofi": {"selo": "INSCRIÇÕES ABERTAS"}}}) == [], "FGV promove")
    ok(erros({"concursos": {"leg": {"selo": "INSCRIÇÕES ABERTAS"}}},
             carimbos={"leg": {"fonte": "https://conhecimento.fgv.br/concursos/leg26"}}) == [], "carimbo da banca")
    ok(any("prazo confirmado" in e for e in erros({"concursos": {"leg": {"prazos": [
        {"data": "2026-12-01", "evento": "fim das inscrições", "confirmado": True}]}}})), "prazo confirmado")
    ok(any("remover exige desfecho" in e for e in erros({"concursos": {"ofi": {"remover": True}}})), "remover concurso")
    ok(any("remover exige desfecho" in e for e in erros({"pendencias": {"ofi_verificar": {"remover": True}}})), "pend")
    novo = {"bloco": "PFN", "linha": "PFN — Procurador", "selo": "EM PLANEJAMENTO", "verificado_em": "2026-11-17"}
    ok(any("fonte` com a URL" in e for e in erros({"concursos": {"novo": dict(novo, fonte="busca")}})), "novo sem http")
    ok(erros({"concursos": {"novo": dict(novo, fonte="https://x.com/a")}}) == [], "novo com http")
    ok(any("termo relativo" in e for e in erros({"concursos": {"ofi": {"linha": "Ofi — até 16h de 13/11 (hoje)"}}})),
       "hoje na linha")
    ok(any("depois da data da janela" in e for e in erros({"concursos": {"ofi": {"verificado_em": "2026-11-18"}}})),
       "verificado_em no futuro")
    ok(any("nao existe em pendencias_vivas" in e for e in erros({"concursos": {"ofi": {"pendencia": "zzz"}}})), "vínculo")
    ok(erros({"concursos": {"ofi": {"pendencia": "nova_p"}}, "pendencias": {"nova_p": {"texto": "t", "faixa": "ativa"}}})
       == [], "vínculo com pendência criada no mesmo update")
    ok(any("campos nao editaveis" in e for e in erros({"concursos": {"ofi": {"mudou_em": "2026-11-17"}}})), "mudou_em")
    ok(any("ja existe" in e for e in erros({"armadilhas_novas": [{"id": "arm1", "fonte": "f", "sintoma": "s",
                                                                   "regra": "r"}]})), "armadilha repetida")
    led = copy.deepcopy(LED)
    led["atualizado_por_execucao"] = "2026-11-17-7h"
    ok(uh.validar_ledger_updates({"armadilhas_novas": [{"id": "arm1", "fonte": "f", "sintoma": "s", "regra": "r"}]},
                                 led, hoje="2026-11-17", ex_id="2026-11-17-7h") == [], "reaplicação (--refazer)")
    av = uh.avisos_ledger_updates({"fontes": {"conjur": {"nota": "17/11: deu 403"}}}, LED, "2026-11-17")
    ok(len(av) == 1 and "diário" in av[0], "nota-diário: %r" % av)
    ok(uh.avisos_ledger_updates({"fontes": {"conjur": {"nota": "17/11: x", "status": "saudavel"}}}, LED,
                                "2026-11-17") == [], "com mudança de status, sem aviso")


@teste
def aplicar_updates_mecanicos():
    led = copy.deepcopy(LED)
    log = []
    upd = {"concursos": {"ofi": {"verificado_em": "2026-11-17"}, "leg": {"linha": "Leg — Juiz: nova"}},
           "pendencias": {"ofi_verificar": {"remover": True, "desfecho": "resolvida"}},
           "armadilhas_novas": [{"id": "arm2", "fonte": "f", "sintoma": "s", "regra": "r"}]}
    uh.aplicar_updates(led, upd, "2026-11-17", log.append)
    uh.aplicar_updates(led, upd, "2026-11-17", log.append)          # idempotente
    cs = {c["id"]: c for c in led["concursos"]}
    ok(cs["leg"].get("mudou_em") == "2026-11-17" and "mudou_em" not in cs["ofi"], "mudou_em só com mudança")
    ok("pendencia" not in cs["ofi"], "vínculo zerado")
    ok([a["id"] for a in led["armadilhas"]] == ["arm1", "arm2"], "armadilha nova uma vez só")
    # selo por data persistido (TJPB 18/11), nunca sobre selo escrito hoje; carimbo não troca o julgamento de hoje
    led = {"concursos": regs("2a9eac9")}
    banca = json.loads(fx("bancas-1611.json"))
    log = []
    uh.aplicar_mecanicos_concursos(led, {"concursos": {"tjap_juiz": {"selo": "INSCRIÇÕES ENCERRADAS",
                                                                     "verificado_em": "2026-11-17"}}},
                                   "2026-11-18", banca, log.append)
    cs = {c["id"]: c for c in led["concursos"]}
    ok(cs["tjpb_apoio"]["selo"] == "ENCERRA HOJE" and cs["tjpb_apoio"]["mudou_em"] == "2026-11-18", "TJPB 18/11")
    ok(cs["tjap_juiz"]["selo"] == "ENCERRA EM BREVE", "selo escrito hoje preservado (mecânico não o reescreve)")
    # a reprodução da revisão: a linha reescrita copiando o selo (ENCERRA EM BREVE) não bloqueia o ENCERRA HOJE
    led = {"concursos": regs("2a9eac9")}
    tjpb = next(c for c in led["concursos"] if c["id"] == "tjpb_apoio")
    upd = {"concursos": {"tjpb_apoio": {"linha": tjpb["linha"], "selo": "ENCERRA EM BREVE"}}}
    uh.aplicar_updates(led, upd, "2026-11-18", log.append)
    uh.aplicar_mecanicos_concursos(led, upd, "2026-11-18", banca, log.append)
    ok(tjpb["selo"] == "ENCERRA HOJE" and "selo" not in upd["concursos"]["tjpb_apoio"], "cópia do selo: %r" % tjpb)
    ok(cs["tjsc_juiz"]["verificado_em"] == "2026-11-18" and cs["tjap_juiz"]["verificado_em"] == "2026-11-16",
       "carimbo só onde o orquestrador não escreveu: %r" % log)
    ok(any(l.startswith("AVISO: selo por data: tjpb_apoio ENCERRA EM BREVE → ENCERRA HOJE") for l in log), log)


# ------------------------------------------------------------------ helper: execução completa
def pasta_helper():
    d = tempfile.mkdtemp(dir=TMPDIR)
    led = copy.deepcopy(LED)
    led["concursos"] = regs("2a9eac9") + led["concursos"]
    led["fontes"] = [{"id": "conjur", "status": "saudavel", "sem_sucesso": 0, "nota": "n"}]
    led["licoes_de_processo"] = []
    with open(os.path.join(d, "led.json"), "w") as f:
        json.dump(led, f, ensure_ascii=False)
    orq = lambda m, c: {"modelo": m, "contexto_total": c, "cache_gravado": 100000, "saida": 40000}
    hist = {"archive_files": ["resumo-legislativo-historico-arquivo-2026-06.json"], "executions": [
        {"execution_id": "2026-11-%02d-7h" % d_, "date": "2026-11-%02d" % d_, "items": [], "delivery": "draft",
         "window_end": "2026-11-%02dT07:05:00-03:00" % d_, "orquestrador": orq("claude-sonnet-5-5", 1000000),
         "ledger_updates": {"concursos": {"tjrs_juiz": {"linha": "x"}}} if d_ == 12 else {}}
        for d_ in (10, 11, 12, 13)]}
    with open(os.path.join(d, "hist.json"), "w") as f:
        json.dump(hist, f, ensure_ascii=False)
    with open(os.path.join(d, "janela.json"), "w") as f:
        json.dump({"execution_id": "2026-11-18-7h", "data": "2026-11-18", "inicio": "2026-11-13T07:05:00-03:00",
                   "fim": "2026-11-18T07:05:00-03:00", "assunto": "A - 18/11/2026 - 7h"}, f)
    b = json.loads(fx("bancas-1611.json"))
    b["data"] = "2026-11-18"
    with open(os.path.join(d, "bancas.json"), "w") as f:
        json.dump(b, f, ensure_ascii=False)
    with open(os.path.join(d, "fs.json"), "w") as f:
        json.dump({"conjur": {"status": "falha", "detalhe": "http 403", "execution_id": "2026-11-18-7h"},
                   "migalhas": {"status": "ok", "execution_id": "2026-11-13-7h"}}, f)
    return d


def rodar_helper(d, ex, *extra):
    with open(os.path.join(d, "ex.json"), "w") as f:
        json.dump(ex, f, ensure_ascii=False)
    r = subprocess.run([sys.executable, os.path.join(WORK, "Update-Historico.py"), "--nova-execucao",
                        os.path.join(d, "ex.json"), "--historico", os.path.join(d, "hist.json"), "--ledger",
                        os.path.join(d, "led.json"), "--janela", os.path.join(d, "janela.json"), "--bancas",
                        os.path.join(d, "bancas.json"), "--fontes-status", os.path.join(d, "fs.json")] + list(extra),
                       capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


@teste
def helper_completo():
    d = pasta_helper()
    ex = {"delivery": "draft", "items": [], "source_status": {"conjur": "ok"},
          "orquestrador": {"modelo": "claude-fable-5-2", "contexto_total": 1000000, "cache_gravado": 170000,
                           "saida": 50000, "custo_relativo": 900000},
          "ledger_updates": {"concursos": {"tjrs_juiz": {"verificado_em": "2026-11-18"}},
                             "pendencias": {"ofi_verificar": {"remover": True, "desfecho": "resolvida"}}}}
    rc, out = rodar_helper(d, ex, "--draft-id", "r1", "--reconciliar-id", "2026-11-13-7h")
    ok(rc == 0 and "STATUS: OK" in out, out)
    ok("ALERTA: edicao anterior 2026-11-13-7h sem --message-id" in out, "E2")
    ok("ALERTA_ECONOMIA:" in out and "ALERTA: modelo do orquestrador mudou: claude-sonnet-5-5" in out, "uso: " + out)
    ok("vale o do script" in out, "fontes_status mesclado")
    h = json.load(open(os.path.join(d, "hist.json")))
    ant = next(e for e in h["executions"] if e["execution_id"] == "2026-11-13-7h")
    ok(ant["delivery"] == "draft" and ant["delivery_check"] == "ausente_em_sent", "delivery da anterior")
    nova = h["executions"][-1]
    ok(nova["source_status"]["conjur"] == "falha" and "migalhas" not in nova["source_status"], "status do script")
    ok(h["archive_files"] == [], "E13 archive_files")
    led = json.load(open(os.path.join(d, "led.json")))
    cs = {c["id"]: c for c in led["concursos"]}
    ok(cs["tjpb_apoio"]["selo"] == "ENCERRA HOJE" and cs["tjap_juiz"]["selo"] == "ENCERRA HOJE", "selos 18/11")
    ok(cs["tjrs_juiz"]["mudou_em"] == "2026-11-12" and cs["tjsc_juiz"]["mudou_em"] == "2026-11-16", "mudou_em init")
    ok(cs["tjsc_juiz"]["verificado_em"] == "2026-11-18", "carimbo")
    ok("licoes_de_processo" not in led, "E13 licoes vazia")
    ok(led["fontes"][0]["sem_sucesso"] == 1, "contador do conjur (falha do script)")
    est = json.load(open(os.path.join(d, "robozinho-estado.json")))
    ok("pendencias_ultima" not in est and "chaves_publicadas" not in est, "E13 estado")
    ok(est["metricas"]["orquestrador_custo_relativo_mediana"], "mediana no estado")
    ok(json.load(open(os.path.join(d, "concursos-estado.json")))["bancas"]["fgv"]["tjap26"]["urls"], "URLs vistas")
    # --refazer / finalizar repetido: os ledger_updates novos entram, contadores não
    ex2 = dict(ex, ledger_updates={"concursos": {"tjrs_juiz": {"linha": "TJRS — Juiz: linha refeita"}},
                                   "pendencias": {"ofi_verificar": {"remover": True, "desfecho": "resolvida"}}})
    rc, out = rodar_helper(d, ex2, "--draft-id", "r2", "--reconciliar-id", "2026-11-13-7h",
                           "--reconciliar-message-id", "m1")
    ok(rc == 0 and "contadores nao" in out, out)
    led = json.load(open(os.path.join(d, "led.json")))
    cs = {c["id"]: c for c in led["concursos"]}
    ok(cs["tjrs_juiz"]["linha"] == "TJRS — Juiz: linha refeita" and cs["tjrs_juiz"]["mudou_em"] == "2026-11-18",
       "updates da re-execução aplicados")
    ok(led["fontes"][0]["sem_sucesso"] == 1, "contadores uma vez só")
    h = json.load(open(os.path.join(d, "hist.json")))
    ok(next(e for e in h["executions"] if e["execution_id"] == "2026-11-13-7h")["delivery"] == "sent", "sent com prova")


# ------------------------------------------------------------------ medir_uso
@teste
def medir_uso_tipos_e_custo():
    raiz = tempfile.mkdtemp(dir=TMPDIR)
    proj = os.path.join(raiz, "proj")
    os.makedirs(os.path.join(proj, "sessao", "subagents"))

    def msg(i, ts, ent, lido, grav, saida, modelo="claude-fable-5-2"):
        return json.dumps({"type": "assistant", "timestamp": ts, "message": {
            "id": i, "model": modelo, "content": [{"type": "tool_use"}],
            "usage": {"input_tokens": ent, "cache_read_input_tokens": lido, "cache_creation_input_tokens": grav,
                      "cache_creation": {"ephemeral_1h_input_tokens": grav}, "output_tokens": saida}}})
    with open(os.path.join(proj, "sessao.jsonl"), "w") as f:
        f.write(msg("a", "2026-11-17T10:00:00Z", 10, 1000, 500, 100) + "\n")
        f.write(msg("a", "2026-11-17T10:00:01Z", 10, 1000, 500, 300) + "\n")      # mesma mensagem, saída maior
        f.write(msg("b", "2026-11-17T10:01:00Z", 0, 2000, 100, 50) + "\n")
    for n, nome in enumerate(("a1", "a2")):
        with open(os.path.join(proj, "sessao", "subagents", "agent-%s.jsonl" % nome), "w") as f:
            f.write(json.dumps({"type": "user", "timestamp": "2026-11-17T10:00:00Z",
                                "message": {"content": "Read de /tmp/coletor-gmail.md"}}) + "\n")
            f.write(msg("g%d" % n, "2026-11-17T10:00:%02dZ" % (5 + n), 0, 100, 10, 5, "claude-haiku-5-5") + "\n")
        os.utime(os.path.join(proj, "sessao", "subagents", "agent-%s.jsonl" % nome), (1000 + n, 1000 + n))
    antigo = medir_uso.RAIZ
    medir_uso.RAIZ = raiz
    try:
        m = medir_uso.medir()
    finally:
        medir_uso.RAIZ = antigo
    o = m["orquestrador"]
    ok(o["entrada"] == 10 and o["cache_lido"] == 3000 and o["cache_gravado"] == 600 and o["saida"] == 350, o)
    base = medir_uso.custo_relativo(10, 3000, 600, 350)
    ok(base == round(10 + 300 + 750 + 1750), "pesos 1/0,1/1,25/5: %d" % base)
    ok(o["fechamento_estimado"]["cache_lido"] == 2100 and o["custo_relativo"] == base +
       o["fechamento_estimado"]["custo_relativo"], "fechamento estimado")
    g = m["coletores"]["gmail"]
    ok(g["relancamentos"] == 1 and g["chamadas_modelo"] == 2 and g["saida"] == 10, "relançamento somado: %r" % g)
    ok(uh.custo_relativo_execucao({"orquestrador": {"contexto_total": 1000, "cache_gravado": 100, "saida": 10,
                                                    "tokens": 500}}) ==
       medir_uso.custo_relativo(0, 900, 100, 10) + medir_uso.custo_relativo(0, 500, 2000, 700),
       "estimativa do histórico antigo (com o mesmo fechamento estimado)")


# ------------------------------------------------------------------ aguardar_coleta
STUB = '''import os, sys, json
t = os.environ["ROBOZINHO_TMP"]
print("linha de %(n)s")
print("SOURCE_STATUS " + json.dumps({"%(n)s_fonte": "ok"}))
'''


def pasta_aguardar():
    d = tempfile.mkdtemp(dir=TMPDIR)
    os.makedirs(os.path.join(d, "work"))
    os.makedirs(os.path.join(d, "tmp"))
    shutil.copy(os.path.join(WORK, "aguardar_coleta.py"), os.path.join(d, "work"))
    for n in aguardar_coleta.SCRIPTS:
        with open(os.path.join(d, "work", n + ".py"), "w") as f:
            f.write(STUB % {"n": n})
    with open(os.path.join(d, "tmp", "janela.json"), "w") as f:
        json.dump({"execution_id": "E1"}, f)
    return d


def aguardar(d, *args):
    env = dict(os.environ, ROBOZINHO_TMP=os.path.join(d, "tmp"))
    r = subprocess.run([sys.executable, os.path.join(d, "work", "aguardar_coleta.py")] + list(args),
                       capture_output=True, text=True, env=env, cwd=d)
    return r.stdout


@teste
def aguardar_fallback_e_status():
    d = pasta_aguardar()
    with open(os.path.join(d, "tmp", "fontes_status.json"), "w") as f:
        json.dump({"x": {"status": "falha", "execution_id": "E1"}, "velha": {"status": "ok", "execution_id": "E0"}}, f)
    out = aguardar(d)
    linhas = out.strip().splitlines()
    ok([l.split()[1] for l in linhas if l.startswith("== ")] == ["coleta_web.py", "informativos.py", "versiculo.py"],
       "ordem: " + out)
    ok("rodado aqui (sem disparo do inicio.py)" in out, "fallback")
    st = json.loads(linhas[-1][len("SOURCE_STATUS "):])
    ok(st == {"coleta_web_fonte": "ok", "informativos_fonte": "ok", "versiculo_fonte": "ok", "x": "falha"}, st)
    ok(sum(l.startswith("SOURCE_STATUS") for l in linhas) == 1, "uma linha SOURCE_STATUS")
    # disparo desta execução, já terminado (pid morto, .rc presente): só imprime, não roda de novo
    T = os.path.join(d, "tmp")
    for n in aguardar_coleta.SCRIPTS:
        with open(os.path.join(T, "passo2-%s.out" % n), "w") as f:
            f.write("feito em segundo plano %s\nSOURCE_STATUS {}\n" % n)
        with open(os.path.join(T, "passo2-%s.rc" % n), "w") as f:
            f.write("0\n")
    os.remove(os.path.join(T, "passo2-versiculo.rc"))           # este morreu sem .rc: roda de novo
    with open(os.path.join(T, "passo2-disparo.json"), "w") as f:
        json.dump({"execution_id": "E1", "pids": {n: 999999 for n in aguardar_coleta.SCRIPTS},
                   "disparado_em": "2026-11-17T07:05:00-03:00"}, f)
    out = aguardar(d)
    ok("feito em segundo plano coleta_web" in out and "linha de versiculo" in out
       and "feito em segundo plano versiculo" not in out, out)
    # disparo de outra execução: roda tudo aqui
    with open(os.path.join(T, "passo2-disparo.json"), "w") as f:
        json.dump({"execution_id": "E0", "pids": {}}, f)
    ok("disparo de outra execução (E0)" in aguardar(d), "disparo velho")


# ------------------------------------------------------------------ paginas_oficiais
@teste
def paginas_oficiais_offline():
    html1 = "<html><body><nav>menu concurso</nav><p>Concurso para Procurador: edital publicado em 10/11</p>" \
            "<p>%s</p><p>Notícia sem palavra-chave nenhuma, só texto comprido para passar do mínimo</p></body></html>" \
            % ("Inscrições abertas até 30/11 para o concurso. " * 8)
    r1 = paginas_oficiais.analisar("p", "https://x.gov.br/c", 200, html1, None, "2026-11-17")
    ok(r1["situacao"] == "NOVA" and r1["novos"], r1)
    est = {}
    paginas_oficiais.atualizar_estado(est, [r1], "2026-11-17")
    r2 = paginas_oficiais.analisar("p", "https://x.gov.br/c", 200, html1, est["paginas"]["p"], "2026-11-18")
    ok(r2["situacao"] == "IGUAL" and r2["desde"] == "2026-11-17", r2)
    html2 = html1.replace("</body>", "<p>Resultado da prova objetiva publicado</p></body>")
    r3 = paginas_oficiais.analisar("p", "https://x.gov.br/c", 200, html2, est["paginas"]["p"], "2026-11-18")
    ok(r3["situacao"] == "MUDOU" and r3["novos"] == ["Resultado da prova objetiva publicado"], r3)
    r4 = paginas_oficiais.analisar("p", "https://x/c", 200, "<script>app()</script><div id=app></div>", None, "d")
    ok(r4["situacao"] == "SEM_TEXTO", r4)
    ok("SEM TEXTO" in paginas_oficiais.linhas_saida([r4])[0], "linha SEM TEXTO")


# ------------------------------------------------------------------ inicio.py
def rodar_inicio(agora, *args, estado_data="2026-11-16", extra_concursos=()):
    import inicio
    d = tempfile.mkdtemp(dir=TMPDIR)
    t = os.path.join(d, "tmp")
    os.makedirs(t)
    shutil.copytree(os.path.join(WORK, "prompts"), os.path.join(d, "prompts"))
    shutil.copy(os.path.join(WORK, "munger-quotes.json"), d)
    led = json.load(open(os.path.join(WORK, "robozinho-aprendizado.json"), encoding="utf-8"))
    led["concursos"] = regs("2a9eac9") + list(extra_concursos)
    json.dump(led, open(os.path.join(d, "robozinho-aprendizado.json"), "w"), ensure_ascii=False)
    json.dump({"ultima_execucao": {"execution_id": "%s-7h" % estado_data, "date": estado_data, "delivery": "draft",
                                   "email_subject": "S", "draft_id": "r",
                                   "window_end": "%sT07:07:30-03:00" % estado_data}},
              open(os.path.join(d, "robozinho-estado.json"), "w"))
    banca = json.loads(fx("bancas-1611.json"))
    salvo = (inicio.AQUI, inicio.alcancaveis, bancas.coletar, os.environ.get("ROBOZINHO_TMP"), sys.argv)
    inicio.AQUI = d
    inicio.alcancaveis = lambda ds: {x: True for x in ds if x}
    bancas.coletar = lambda hoje, conc, estado=None: dict(copy.deepcopy(banca), data=hoje.isoformat())
    os.environ["ROBOZINHO_TMP"] = t
    sys.argv = ["inicio.py", "--agora", agora, "--sem-disparo"] + list(args)
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            inicio.main()
    finally:
        inicio.AQUI, inicio.alcancaveis, bancas.coletar, os.environ["ROBOZINHO_TMP"], sys.argv = salvo
    return buf.getvalue(), json.load(open(os.path.join(t, "janela.json"))), t


@teste
def inicio_17_11():
    velho = {"id": "velho_pge", "bloco": "Procurador do Estado (PGE)", "linha": "PGE-ZZ — Procurador: homologado",
             "selo": "INSCRIÇÕES ENCERRADAS", "verificado_em": "2026-10-01",
             "prazos": [{"data": "2026-09-01", "evento": "prova objetiva", "confirmado": True}]}
    out, j, t = rodar_inicio("2026-11-17T07:05:00-03:00", extra_concursos=[velho])
    ok(j["execution_id"] == "2026-11-17-7h" and j["gmail_apos"] == "2026/11/16", "after: = data do início")
    ok(j["tipo"] == "diaria" and j["feriado_hoje"] is None and j["feriados_na_janela"] == [], j)
    ok(j["munger"]["tipo"] in ("licao", "aforismo") and "obs" in j["munger"], "Munger com tipo e obs")
    ok("ALERTA: candidato a remoção (velho_pge)" in out, "candidato a remoção")
    ok("FERIADO" not in out and "demais" not in out.split("==== LEDGER")[0].lower().replace("os demais", ""), "limpo")
    cc = open(os.path.join(t, "coletor-concursos.md"), encoding="utf-8").read()
    ok("TJAP [tjap_juiz]" in cc and "TJPB [tjpb_apoio]" in cc, "B2d: acompanhados com id")
    ok("## Registro atual dos demais acompanhados" in cc and "velho_pge" not in cc.split("## Registro atual")[1]
       and "tjpb_juiz | EM PLANEJAMENTO" in cc.split("## Registro atual")[1], "registro atual (sem os em foco)")
    ok("  [Magistratura Estadual]" in out and "sem foco: tjpb_juiz" in out, "concursos contados por bloco")
    ok(len(out.replace(t, "/tmp")) < 22000, "saída enxuta: %d" % len(out))
    ok(not re.search(r"\{\{[A-Z_]+", cc), "placeholder sobrando")
    out18, _, _ = rodar_inicio("2026-11-18T07:05:00-03:00", estado_data="2026-11-17")
    ok("SELO POR DATA: tjpb_apoio ENCERRA EM BREVE → ENCERRA HOJE" in out18, "selo por data no inicio")


@teste
def inicio_feriados_gap_extra():
    out, j, _ = rodar_inicio("2026-11-20T07:05:00-03:00", estado_data="2026-11-19")
    ok("FERIADO HOJE: 20/11 (sex) Dia Nacional de Zumbi e da Consciência Negra [nacional]" in out, out[:600])
    ok(j["feriado_hoje"]["data"] == "2026-11-20", "janela.feriado_hoje")
    out, j, t = rodar_inicio("2026-11-23T07:05:00-03:00", estado_data="2026-11-19")
    # a edição de sexta (feriado) não foi registrada: o alerta tem de aparecer (antes ficava calado)
    ok("FERIADOS NA JANELA: 20/11 (sex)" in out and "ALERTA: dia útil sem execução registrada: 20/11 (feriado: a "
       "edição sai em feriado)" in out and "gap: sim" in out, "segunda após feriado sem registro")
    ok(j["dias_uteis_sem_registro"] == ["2026-11-20"], j["dias_uteis_sem_registro"])
    out2, j2, _ = rodar_inicio("2026-11-23T07:05:00-03:00", estado_data="2026-11-20")
    ok("dia útil sem execução" not in out2 and "gap: não" in out2, "edição do feriado registrada: sem alerta")
    ok("feriado na janela: 20/11" in open(os.path.join(t, "coletor-gmail.md"), encoding="utf-8").read()
       or "{{RECESSO}}" not in open(os.path.join(WORK, "prompts", "coletor-gmail.md"), encoding="utf-8").read(),
       "RECESSO com o feriado")
    out, j, _ = rodar_inicio("2026-11-19T07:05:00-03:00", estado_data="2026-11-16")
    ok("ALERTA: dia útil sem execução registrada: 17/11, 18/11" in out, "dia útil sem registro")
    ok(j["dias_uteis_sem_registro"] == ["2026-11-17", "2026-11-18"], j)
    out, j, _ = rodar_inicio("2026-11-17T15:00:00", "--extra")         # --agora sem fuso = BRT
    ok(j["execution_id"] == "2026-11-17-extra" and j["assunto"].endswith("17/11/2026 - Extra"), j)
    ok(j["cabecalho_extra"] == "Edição extra" and j["tipo"] == "extra" and j["munger"]["idx"] == (321 + 1) % 200, j)
    _, j, _ = rodar_inicio("2026-11-17T07:05:00-03:00", estado_data="2026-11-16")
    ok(j["munger"]["idx"] == 321 % 200, "idx diário")


@teste
def gmail_apos_madrugada():
    out, j, _ = rodar_inicio("2026-11-17T07:05:00-03:00", estado_data="2026-11-16")
    ok(j["gmail_apos"] == "2026/11/16", j["gmail_apos"])
    # janela que começa de madrugada (execução anterior atrasada que terminou às 02h): volta um dia
    import inicio
    d = tempfile.mkdtemp(dir=TMPDIR)
    shutil.copytree(os.path.join(WORK, "prompts"), os.path.join(d, "prompts"))
    shutil.copy(os.path.join(WORK, "munger-quotes.json"), d)
    led = json.load(open(os.path.join(WORK, "robozinho-aprendizado.json"), encoding="utf-8"))
    led["concursos"] = []
    json.dump(led, open(os.path.join(d, "robozinho-aprendizado.json"), "w"), ensure_ascii=False)
    json.dump({"ultima_execucao": {"execution_id": "2026-11-16-7h", "date": "2026-11-16",
                                   "window_end": "2026-11-17T02:10:00-03:00"}},
              open(os.path.join(d, "robozinho-estado.json"), "w"))
    salvo = (inicio.AQUI, inicio.alcancaveis, bancas.coletar, sys.argv)
    inicio.AQUI, inicio.alcancaveis = d, (lambda ds: {})
    bancas.coletar = lambda hoje, conc, estado=None: {"banca": "FGV", "http": 0, "concursos": [], "data": hoje.isoformat()}
    sys.argv = ["inicio.py", "--agora", "2026-11-17T07:05:00-03:00", "--sem-disparo"]
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            inicio.main()
    finally:
        inicio.AQUI, inicio.alcancaveis, bancas.coletar, sys.argv = salvo
    j = json.load(open(os.path.join(TMPDIR, "janela.json")))
    ok(j["gmail_apos"] == "2026/11/16", "início 02h10 de 17/11 → after:2026/11/16: %r" % j["gmail_apos"])


# ------------------------------------------------------------------ correções da revisão adversarial (grupo EST)
@teste
def selo_copiado_nao_e_decisao():
    """Selo igual ao do registro no update (cópia) não bloqueia o selo por data; selo diferente (decisão) sim,
    com AVISO no --validar; o finalizar repetido (entrada já normalizada) não apaga a decisão."""
    d = pasta_helper()
    led = json.load(open(os.path.join(d, "led.json")))
    tjpb = next(c for c in led["concursos"] if c["id"] == "tjpb_apoio")
    ok(tjpb["selo"] == "ENCERRA EM BREVE", "pré-condição")
    ex = {"delivery": "draft", "items": [], "source_status": {},
          "ledger_updates": {"concursos": {"tjpb_apoio": {"linha": tjpb["linha"], "selo": "ENCERRA EM BREVE"},
                                           "tjap_juiz": {"selo": "INSCRIÇÕES ENCERRADAS"}}}}
    rc, out = rodar_helper(d, ex, "--validar")
    ok(rc == 0 and "tjap_juiz.selo: 'INSCRIÇÕES ENCERRADAS' escrito hoje contradiz o selo por data 'ENCERRA HOJE'"
       in out and "tjpb_apoio.selo" not in out, out)
    rc, out = rodar_helper(d, ex, "--draft-id", "r1")
    ok(rc == 0 and "STATUS: OK" in out, out)
    ok("selo igual ao do registro retirado do update" in out and "tjpb_apoio" in out, out)
    cs = {c["id"]: c for c in json.load(open(os.path.join(d, "led.json")))["concursos"]}
    ok(cs["tjpb_apoio"]["selo"] == "ENCERRA HOJE", "cópia: vale o selo por data (%r)" % cs["tjpb_apoio"]["selo"])
    ok(cs["tjap_juiz"]["selo"] == "INSCRIÇÕES ENCERRADAS", "decisão preservada")
    nova = json.load(open(os.path.join(d, "hist.json")))["executions"][-1]
    ok(nova["selos_copiados"] == ["tjpb_apoio"] and "selo" not in nova["ledger_updates"]["concursos"]["tjpb_apoio"]
       and nova["ledger_updates"]["concursos"]["tjap_juiz"]["selo"] == "INSCRIÇÕES ENCERRADAS", nova["ledger_updates"])
    # finalizar repetido: a entrada normalizada (gravada pelo helper) sobre o ledger já atualizado
    ex2 = json.load(open(os.path.join(d, "ex.json")))
    ok(ex2.get("selos_copiados") == ["tjpb_apoio"], "entrada normalizada no lugar")
    rc, out = rodar_helper(d, ex2, "--draft-id", "r1")
    cs = {c["id"]: c for c in json.load(open(os.path.join(d, "led.json")))["concursos"]}
    ok(rc == 0 and cs["tjap_juiz"]["selo"] == "INSCRIÇÕES ENCERRADAS" and cs["tjpb_apoio"]["selo"] == "ENCERRA HOJE",
       "reaplicação idempotente: %r" % {k: cs[k]["selo"] for k in ("tjap_juiz", "tjpb_apoio")})


@teste
def diverge_sem_carimbo():
    """Registro que a banca contradiz (TJAP de b80a3bd) não ganha verificado_em de hoje nem conta como banca lida,
    até o update corrigir prazos/linha; o --validar avisa (acionável no montador)."""
    res = tjap("b80a3bd", hoje="2026-11-17")
    rs = regs("b80a3bd")
    ok(bancas.carimbos(res, rs, D("2026-11-17")).get("tjap_juiz"), "sem upd: comportamento antigo (compatível)")
    ok("tjap_juiz" not in bancas.carimbos(res, rs, D("2026-11-17"), upd={}), "diverge: sem carimbo")
    ok("tjap_juiz" not in bancas.contexto_selos(res, rs, D("2026-11-17"), {}), "diverge: banca não sustenta o selo")
    fix = {"tjap_juiz": {"prazos": [{"data": "2026-11-18", "evento": "fim das inscrições, 16h", "confirmado": True}]}}
    ok(bancas.carimbos(res, rs, D("2026-11-17"), upd=fix)["tjap_juiz"]["verificado_em"] == "2026-11-17", "corrigido")
    ok(bancas.contexto_selos(res, rs, D("2026-11-17"), fix)["tjap_juiz"]["banca_lida_hoje"], "corrigido: banca lida")
    errado = {"tjap_juiz": {"prazos": [{"data": "2026-11-13", "evento": "fim das inscrições", "confirmado": True}]}}
    ok("tjap_juiz" not in bancas.carimbos(res, rs, D("2026-11-17"), upd=errado), "update que ainda diverge")
    av = uh.avisos_ledger_updates({}, {"concursos": rs}, "2026-11-17", res)
    ok(any(a.startswith("DIVERGE DO REGISTRO em tjap_juiz") and "movimento oficial não refletido" in a for a in av), av)
    ok(not any("DIVERGE" in a for a in uh.avisos_ledger_updates({"concursos": fix}, {"concursos": rs}, "2026-11-17",
                                                                 res)), "sem aviso depois da correção")
    led = {"concursos": copy.deepcopy(rs)}
    antes = next(c for c in rs if c["id"] == "tjap_juiz")["verificado_em"]
    uh.aplicar_mecanicos_concursos(led, {}, "2026-11-17", res, lambda l: None)
    ok(next(c for c in led["concursos"] if c["id"] == "tjap_juiz")["verificado_em"] == antes, "helper não carimba")
    led = {"concursos": copy.deepcopy(rs)}
    uh.aplicar_updates(led, {"concursos": fix}, "2026-11-17", lambda l: None)
    uh.aplicar_mecanicos_concursos(led, {"concursos": fix}, "2026-11-17", res, lambda l: None)
    ok(next(c for c in led["concursos"] if c["id"] == "tjap_juiz")["verificado_em"] == "2026-11-17", "helper carimba")


@teste
def e9_dominio_e_url_oficial():
    pz = [{"data": "2026-11-23", "evento": "fim das inscrições", "confirmado": True}]
    e = erros({"concursos": {"leg": {"selo": "INSCRIÇÕES ABERTAS", "dominio_oficial": "www.dgabc.com.br", "prazos": pz}}})
    ok(any("exige fonte oficial" in x for x in e) and any("dominio_oficial: 'www.dgabc.com.br'" in x for x in e), e)
    e = erros({"concursos": {"leg": {"fonte": "https://www.dgabc.com.br/n", "dominio_oficial": "www.dgabc.com.br",
                                     "prazos": pz}}})
    ok(any("exige fonte oficial" in x for x in e), "fonte e domínio secundários no mesmo update: %r" % e)
    ok(any("url_oficial" in x for x in erros({"concursos": {"ofi": {"url_oficial": "https://www.dgabc.com.br/x"}}})),
       "url_oficial secundária")
    ok(any("url_oficial" in x for x in erros({"concursos": {"ofi": {"url_oficial": "www.tjsc.jus.br/concursos"}}})),
       "url_oficial sem http")
    ok(erros({"concursos": {"ofi": {"url_oficial": "https://www.tjsc.jus.br/concursos/juiz",
                                    "dominio_oficial": "www.tjsc.jus.br"}}}) == [], "oficiais passam")


@teste
def paginas_oficiais_ausente():
    """Merge sem work/paginas_oficiais.py: nem o inicio nem o helper caem."""
    salvo = sys.modules.get("paginas_oficiais")
    sys.modules["paginas_oficiais"] = None            # import falha (ImportError), como sem o arquivo
    try:
        d = tempfile.mkdtemp(dir=TMPDIR)
        pag = os.path.join(d, "paginas_oficiais.json")
        json.dump({"data": "2026-11-17", "paginas": [{"id": "-", "url": "", "http": 0, "situacao": "HTTP",
                                                       "erro": "No module named 'paginas_oficiais'"}]}, open(pag, "w"))
        log = []
        uh.atualizar_estado_concursos(os.path.join(d, "ce.json"), None, "2026-11-17", log.append, pag)
        ok(any(l.startswith("AVISO: paginas_oficiais nao gravadas") for l in log), log)
        foco = {"id": "tjxx_juiz", "bloco": "Magistratura Estadual", "linha": "TJXX — Juiz", "selo": "EM ANDAMENTO",
                "verificado_em": "2026-11-16", "url_oficial": "https://www.tjxx.jus.br/concursos",
                "prazos": [{"data": "2026-11-20", "evento": "prova objetiva", "confirmado": True}]}
        out, _, _ = rodar_inicio("2026-11-17T07:05:00-03:00", extra_concursos=[foco])
        ok("PAGINA OFICIAL: não lida (" in out and "paginas_oficiais" in out.split("PAGINA OFICIAL: não lida")[1][:120]
           and "PASSO 2" in out
           and "==== LEDGER" in out, out[-800:])
    finally:
        if salvo is None:
            sys.modules.pop("paginas_oficiais", None)
        else:
            sys.modules["paginas_oficiais"] = salvo


# ---- finalizar.sh num repositório git descartável (origin bare + clone de sessão), com os dados do MON de 17/11
MONFIX = os.path.join(AQUI, "fixtures", "mon")


def repo_finalizar():
    base = tempfile.mkdtemp(dir=TMPDIR)
    seed = os.path.join(base, "seed")
    os.makedirs(os.path.join(seed, "work"))
    for f in os.listdir(WORK):
        if f.endswith(".py") or f in ("finalizar.sh", "munger-quotes.json"):
            shutil.copy(os.path.join(WORK, f), os.path.join(seed, "work", f))
    shutil.copy(os.path.join(MONFIX, "ledger-1611.json"), os.path.join(seed, "work", "robozinho-aprendizado.json"))
    shutil.copy(os.path.join(MONFIX, "historico.json"), os.path.join(seed, "work", "resumo-legislativo-historico.json"))
    json.dump({"ultima_execucao": {"execution_id": "2026-11-16-7h"}},
              open(os.path.join(seed, "work", "robozinho-estado.json"), "w"))
    open(os.path.join(seed, ".gitignore"), "w").write("__pycache__/\n")
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@t", ROBOZINHO_TMP=os.path.join(base, "tmp"))

    def g(cwd, *a):
        return subprocess.run(["git"] + list(a), cwd=cwd, env=env, capture_output=True, text=True)
    g(seed, "init", "-q", "-b", "main")
    g(seed, "add", "-A")
    g(seed, "commit", "-qm", "seed")
    g(base, "clone", "-q", "--bare", seed, "origin.git")
    sess = os.path.join(base, "sess")
    g(base, "clone", "-q", "origin.git", sess)
    g(sess, "switch", "-q", "-c", "claude/sessao")
    os.makedirs(env["ROBOZINHO_TMP"])
    for a, b in (("janela-1711.json", "janela.json"), ("coleta_web-1711.json", "coleta_web.json"),
                 ("informativos-1711.json", "informativos.json"), ("versiculo-1711.json", "versiculo.json"),
                 ("bancas-1711.json", "bancas.json"), ("fontes_status-1711.json", "fontes_status.json"),
                 ("execucao-1711.json", "execucao.json")):
        shutil.copy(os.path.join(MONFIX, a), os.path.join(env["ROBOZINHO_TMP"], b))

    def run(*cmd):
        r = subprocess.run(list(cmd), cwd=sess, env=env, capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr
    return base, sess, env["ROBOZINHO_TMP"], g, run


def editar_execucao(t, f):
    import time
    time.sleep(1.05)                     # mtime do execucao.json depois do resolvido
    p = os.path.join(t, "execucao.json")
    ex = json.load(open(p))
    f(ex)
    json.dump(ex, open(p, "w"), ensure_ascii=False)


@teste
def finalizar_remonta_execucao_editada():
    base, sess, t, g, run = repo_finalizar()
    rc, out = run(sys.executable, "work/montar_email.py")
    ok(rc == 0 and os.path.exists(os.path.join(t, "execucao.resolvido.json")), out)
    rascunho = [f for f in ("email.html", "email-com-avisos.html") if os.path.exists(os.path.join(t, f))][0]
    corpo = open(os.path.join(t, rascunho), "rb").read()

    def errata(ex):            # o Edit tardio que a ROTINA prevê: pendência errata achada depois do rascunho
        ex["email"]["preheader"] += " ·"
        ex["ledger_updates"] = {"pendencias": {"errata_2026_11_17": {"texto": "onde se leu X, leia-se Y",
                                                                     "faixa": "ativa"}}}
    editar_execucao(t, errata)
    rc, out = run("bash", "work/finalizar.sh", "--draft-id", "r-X", "--message-id", "m-X")
    ok(rc == 0 and "REMONTAGEM: MONTAGEM: OK" in out and "REMONTAGEM: itens iguais" in out
       and "ENTRADA: %s/execucao.resolvido.json" % t in out and "STATUS: OK" in out and "PUSH: OK" in out, out)
    ok("ERRO" not in out and open(os.path.join(t, rascunho), "rb").read() == corpo, "o e-mail do rascunho fica")
    led = json.load(open(os.path.join(sess, "work", "robozinho-aprendizado.json")))
    ok(any(p["id"] == "errata_2026_11_17" for p in led["pendencias_vivas"]), "o Edit tardio chegou ao ledger")
    e = json.load(open(os.path.join(sess, "work", "resumo-legislativo-historico.json")))["executions"][-1]
    ok(e["execution_id"] == "2026-11-17-7h" and e["items"] and all(i.get("chave") for i in e["items"]), "resolvido")
    ok(g(sess, "status", "--porcelain").stdout == "", "árvore limpa")


@teste
def finalizar_remontagem_com_erro_e_itens_mudados():
    base, sess, t, g, run = repo_finalizar()
    run(sys.executable, "work/montar_email.py")
    editar_execucao(t, lambda ex: ex["items"].append({"ref": "zz999"}))
    rc, out = run("bash", "work/finalizar.sh", "--draft-id", "r-X", "--message-id", "m-X")
    ok(rc == 2 and "ERRO: ref desconhecido: 'zz999'" in out and "PERSISTENCIA ABORTADA: execucao.json editado depois "
       "da montagem e a remontagem deu ERRO" in out and "categoria fora da lista" not in out, out)
    ok(os.path.exists(os.path.join(t, "execucao.resolvido.json")), "o resolvido da montagem do rascunho fica")
    editar_execucao(t, lambda ex: ex["items"].pop())
    editar_execucao(t, lambda ex: ex["items"].pop(0))         # item retirado depois do rascunho
    rc, out = run("bash", "work/finalizar.sh", "--draft-id", "r-X", "--message-id", "m-X")
    ok(rc == 0 and "ALERTA: o execucao.json editado depois da montagem mudou os itens (9 -> 8; - " in out
       and "PUSH: OK" in out, out)


@teste
def finalizar_reaplicacao_arvore_limpa():
    base, sess, t, g, run = repo_finalizar()
    run(sys.executable, "work/montar_email.py")
    outro = os.path.join(base, "outro")
    g(base, "clone", "-q", "origin.git", outro)
    with open(os.path.join(outro, "work", "selos.py"), "a") as f:
        f.write("\n# mudanca concorrente na main\n")
    p = os.path.join(outro, "work", "robozinho-aprendizado.json")
    led = json.load(open(p))
    led["atualizado_em"] = "2026-11-17T06:50:00-03:00"
    json.dump(led, open(p, "w"), ensure_ascii=False, indent=1)
    g(outro, "commit", "-qam", "concorrente")
    ok(g(outro, "push", "-q", "origin", "main").returncode == 0, "push concorrente")
    rc, out = run("bash", "work/finalizar.sh", "--draft-id", "r-X", "--message-id", "m-X")
    ok(rc == 0 and "PUSH: recusado" in out and "PUSH: OK" in out, out)
    ok(g(sess, "status", "--porcelain").stdout == "", "árvore limpa: %r" % g(sess, "status", "--porcelain").stdout)
    ok("mudanca concorrente" in open(os.path.join(sess, "work", "selos.py")).read(), "árvore = origin/main")
    ok(g(sess, "rev-parse", "HEAD").stdout == g(sess, "rev-parse", "origin/main").stdout, "HEAD enviado")
    e = json.load(open(os.path.join(sess, "work", "resumo-legislativo-historico.json")))["executions"][-1]
    ok(e["execution_id"] == "2026-11-17-7h", "execução gravada sobre a main concorrente")


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
