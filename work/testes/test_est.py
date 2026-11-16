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
#   Rodada 2 do reteste: motivo do rebaixamento (selo que a nova data da); historico
#   sem impacto/resenha/desdobramento; armadilhas migradas (helper grava, inicio so
#   em memoria); aguardar com teto por chamada (90 s), AINDA RODANDO e --mais N;
#   errata_* fora da fila do coletor; rodape da Extra de fim de semana; GAP ->
#   email.limitacoes; banca: outro cargo do mesmo orgao, pagina sem cargo e duas
#   paginas para o mesmo registro nao cobrem; 1a leitura sem estado (anterior ao
#   verificado_em = visto); finalizar.sh: hook recusando nao reaplica, copia do
#   estado da ultima rodada, sha da 1a rodada quando a reaplicacao falha.
#   Volta 2 do reteste: classe_prazo com outras formas do fim/inicio das inscricoes;
#   AVISO de prazos[n].tipo que contradiz o evento (chave do montador); prazo vencido
#   com encerramento confirmado pela banca lida hoje nao e ALERTA; errata removida no
#   mesmo resolvido nao gera "saiu na edicao mas nao existe no ledger".
#   CORE volta 1: selo por data SUSPENSO com divergencia pendente (bancas.selo_do_dia, a mesma regra no
#   helper, no montador e no inicio; comparador montador x helper em memoria, inclusive so a linha
#   corrigida); prazo escrito hoje contra o edital lido hoje (AVISO no --validar, ALERTA na gravacao; sem
#   falso positivo com update igual ao edital, edital nao relido hoje ou bancas.json de outro dia);
#   relatorio do helper sem "atualizada ()" e sem "nao foi a edicao" no draft_ja_existente sem itens.
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
    # prorrogação: o selo que a NOVA data dá (até 7 dias = ENCERRA EM BREVE), não "INSCRIÇÕES ABERTAS" fixo
    ok("o selo que a nova data dá (ENCERRA HOJE / ENCERRA EM BREVE / INSCRIÇÕES ABERTAS)" in m
       and "e selo INSCRIÇÕES ABERTAS" not in m, m)
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


RET2 = "https://conhecimento.fgv.br/sites/default/files/concursos/retificacao-tjap.pdf"   # URL da 2ª Retificação


def vistos_sem_ret2(data="2026-11-13"):
    """Estado de URLs vistas com tudo da página do TJAP menos a 2ª Retificação (o caso de 16/11 com estado)."""
    est = {}
    bancas.atualizar_estado(est, tjap("2a9eac9"), data)
    del est["bancas"]["fgv"]["tjap26"]["urls"][RET2]
    return est


@teste
def bancas_tjap_retificacao_e_diverge():
    # b80a3bd (verificado 16/11, linha "encerradas"): com URLs vistas, a 2ª Retificação não vista é novidade.
    # 2426d11 (verificado 13/11), sem estado: o arquivo do próprio dia do verificado_em continua novo (C1).
    for commit, esperado, est in (("b80a3bd", "linha: inscrições encerradas em 13/11", vistos_sem_ret2()),
                                  ("2426d11", "prazo 13/11/2026 fim das inscrições", None)):
        res = tjap(commit, est)
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
    del est2["bancas"]["fgv"]["tjap26"]["urls"][RET2]
    c = tjap("2a9eac9", est2, hoje="2026-11-17")["concursos"][0]
    ok([a["titulo"] for a in c["novos_arquivos"]] == ["2ª Retificação"], "só a URL não vista")


@teste
def bancas_sem_estado_anterior_ao_verificado_e_visto():
    """1ª leitura sem URLs vistas: o anterior ao verificado_em conta como visto (a linha já o traz); o do
    próprio dia continua novo (a FGV publica depois da execução das 7h: TJAP 13/11, TJRS 16/11)."""
    c = tjap("2a9eac9", hoje="2026-11-17")["concursos"][0]          # verificado_em 16/11; arquivos até 13/11
    ok(c["base_novos"] == "data (sem estado)" and c["novos_arquivos"] == [], [a["titulo"] for a in c["novos_arquivos"]])
    c = tjap("2426d11", hoje="2026-11-16")["concursos"][0]          # verificado_em 13/11
    ok(sorted({a["data_efetiva"] for a in c["novos_arquivos"]}) == ["2026-11-13"] and len(c["novos_arquivos"]) == 5,
       [(a["data_efetiva"], a["titulo"][:30]) for a in c["novos_arquivos"]])
    ok(bancas.MARGEM_SEM_ESTADO == 0, "margem")


def pagina_fgv(slug, titulo):
    return bancas.analisar_pagina({"slug": slug, "titulo": titulo, "http": 200,
                                   "url": "https://conhecimento.fgv.br/concursos/" + slug}, fx("tjap26.html"))


TIT_TJAP = "Concurso Público para Tribunal de Justiça do Estado do Amapá"


@teste
def bancas_outro_concurso_do_mesmo_orgao():
    """tjapservidores26 não cai no tjap_juiz; página sem cargo identificável ou duas páginas para o mesmo
    registro não cobrem (sem carimbo, sem selo por data, sem DIVERGE) e saem com AVISO."""
    led = regs("b80a3bd")                       # registro que diverge do edital: o DIVERGE errado apareceria
    a, b = pagina_fgv("tjap26", TIT_TJAP + " - Juiz de Direito Substituto"), pagina_fgv("tjapservidores26", TIT_TJAP + " - Servidores")
    r = bancas.analisar([a, b], D("2026-11-19"), copy.deepcopy(led), vistos_sem_ret2(), ler=ler_falso)
    ok(r[0]["coberto"] == ["tjap_juiz"] and r[0]["divergencias"], "a página do Juiz cobre")
    ok(r[1]["registros"] == [] and r[1]["coberto"] == [] and r[1]["divergencias"] == []
       and r[1]["mesma_sigla"] == ["tjap_juiz"] and "incerto" not in r[1], r[1].get("registros"))
    res = {"banca": "FGV", "http": 200, "data": "2026-11-19", "concursos": r}
    ok(set(bancas.carimbos(res, led, "2026-11-19")) == {"tjap_juiz"}, "carimbo só pela página certa")
    txt = saida(res)
    ok("tjapservidores26 | " in txt and "SEM REGISTRO (tjap_juiz, da mesma sigla, é de outro cargo) → avalie como NOVO"
       in txt and txt.count("DIVERGE DO REGISTRO: tjap_juiz") == 1, txt)
    # sem cargo no título, no slug e no edital: não cobre, AVISO
    sem = pagina_fgv("tjap26", TIT_TJAP)
    r = bancas.analisar([sem], D("2026-11-19"), copy.deepcopy(led), {}, ler=lambda u: ("texto sem cargo", ""))
    ok(r[0]["coberto"] == [] and r[0]["registros"] == [] and r[0]["incerto"]["ids"] == ["tjap_juiz"]
       and r[0]["divergencias"] == [], r[0].get("incerto"))
    res = {"banca": "FGV", "http": 200, "data": "2026-11-19", "concursos": r}
    ok(bancas.carimbos(res, led, "2026-11-19") == {} and bancas.contexto_selos(res) == {}, "nada mecânico")
    txt = saida(res)
    ok("registro incerto: tjap_juiz" in txt and "  AVISO: página não cobre tjap_juiz (cargo não identificado" in txt, txt)
    # duas páginas para o mesmo registro: nenhuma cobre
    a, b = pagina_fgv("tjap26", TIT_TJAP + " - Juiz"), pagina_fgv("tjapjuiz26", TIT_TJAP + " - Juiz de Direito")
    r = bancas.analisar([a, b], D("2026-11-19"), copy.deepcopy(led), {}, ler=ler_falso)
    ok(all(c["coberto"] == [] and c["divergencias"] == [] and "2 páginas da FGV" in c["incerto"]["motivo"] for c in r),
       [(c["coberto"], c.get("incerto")) for c in r])
    # sem regressão nas páginas reais de 16/11 (TJPB sem cargo no título: 2 registros, decide pelo edital)
    b16 = json.loads(fx("bancas-1611.json"))
    ed = {c["edital_url"]: " ".join(c["edital"].values()) for c in b16["concursos"] if c.get("edital_url")}
    alvo = [{k: c[k] for k in ("slug", "titulo", "url", "http", "situacao", "arquivos")} for c in b16["concursos"]]
    r = bancas.analisar(alvo, D("2026-11-16"), regs("2a9eac9"), {}, ler=lambda u: (ed.get(u, ""), ""))
    ok({c["slug"]: c["coberto"] for c in r} == {c["slug"]: c["coberto"] for c in b16["concursos"]},
       {c["slug"]: c["coberto"] for c in r})


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
def helper_historico_enxuto_e_armadilhas_migradas():
    d = pasta_helper()
    p = os.path.join(d, "led.json")
    led = json.load(open(p))
    velhas = {x["id"]: x for x in json.load(open(os.path.join(MONFIX, "ledger-1611.json")))["armadilhas"]
              if x["id"] in uh.REGRAS_ATUALIZADAS}
    outra = {"id": "outra", "fonte": "f", "sintoma": "s", "regra": "Publicar o link so se o TITULO bater."}
    reescrita = dict(velhas["gmail_after_epoch"], regra="Regra reescrita depois por outra via.")
    led["armadilhas"] = [velhas["jota_link_wrapper_mismatch"], reescrita, outra]
    json.dump(led, open(p, "w"), ensure_ascii=False)
    item = {"categoria": "Planalto", "titulo": "Lei 15.999", "url": "https://www.planalto.gov.br/l15999.htm",
            "chave": "planalto|lei|15999|2026-11-18|x", "status": "CONFIRMADO POR FONTE OFICIAL", "fonte": "PUSH Planalto",
            "data": "2026-11-18", "impacto": "Altera: Código Penal", "resenha": "Lei nº 15.999 ...",
            "desdobramento": True, "grupo": "Leis", "meta": "DOU 18/11"}
    rc, out = rodar_helper(d, {"delivery": "draft", "items": [item]}, "--draft-id", "r1")
    ok(rc == 0 and "STATUS: OK" in out, out)
    nova = json.load(open(os.path.join(d, "hist.json")))["executions"][-1]
    ok(not {"impacto", "resenha", "desdobramento", "grupo", "meta"} & set(nova["items"][0]), nova["items"][0])
    ok(nova["items"][0]["chave"] == item["chave"] and nova["items"][0]["titulo"] == item["titulo"], "o resto fica")
    arm = {x["id"]: x for x in json.load(open(p))["armadilhas"]}
    ok(arm["jota_link_wrapper_mismatch"]["regra"] == uh.REGRAS_ATUALIZADAS["jota_link_wrapper_mismatch"]["regra"],
       "regra antiga migrada")
    ok(arm["gmail_after_epoch"]["regra"] == "Regra reescrita depois por outra via." and arm["outra"] == outra,
       "só o texto antigo exato muda")
    ok("Ledger: regra da armadilha atualizada para o comportamento atual (migracao): jota_link_wrapper_mismatch" in out,
       out)
    ok(all(len(m["regra"]) <= uh.LIMITE["regra"] for m in uh.REGRAS_ATUALIZADAS.values()), "limite da regra")
    l2 = {"armadilhas": [dict(velhas["gmail_after_epoch"])]}
    ok(uh.migrar_armadilhas(l2) == ["gmail_after_epoch"] and uh.migrar_armadilhas(l2) == [], "idempotente")
    ok(len(uh.LIMITE) and all(len(v["antigas"]) for v in uh.REGRAS_ATUALIZADAS.values()), "tabela")


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
    ok("== versiculo.py (exit 0; disparado de novo aqui (o processo do disparo morreu sem resultado))" in out, out)
    ok("versiculo" in json.load(open(os.path.join(T, "passo2-disparo.json")))["iniciado_em"], "redisparo registrado")
    # disparo de outra execução: roda tudo aqui
    with open(os.path.join(T, "passo2-disparo.json"), "w") as f:
        json.dump({"execution_id": "E0", "pids": {}}, f)
    ok("disparo de outra execução (E0)" in aguardar(d), "disparo velho")


@teste
def aguardar_cabe_no_bash_e_mais():
    """O Bash do agente tem timeout padrão de 2 min: sem flag, a chamada volta em até CHAMADA_S (90 s) com o
    que terminou e AINDA RODANDO para o resto; --mais N espera N s a partir da chamada seguinte."""
    L = aguardar_coleta.limite_da_chamada
    ok(aguardar_coleta.CHAMADA_S <= 100, "teto por chamada")
    ok(L(1000, 970) == 1090, "disparo há 30 s: 90 s nesta chamada (não os 240 do disparo)")
    ok(L(1000, 400) == 1005, "teto do disparo vencido: só confere")
    ok(L(1000, 400, mais=240) == 1240 and L(1000, 400, mais=0) == 1000, "--mais conta da chamada")
    ok(L(1000, 400, teto=900) == 1300, "--teto explícito conta do disparo (compatibilidade)")
    d = pasta_aguardar()
    T = os.path.join(d, "tmp")
    for n in ("coleta_web", "versiculo"):
        open(os.path.join(T, "passo2-%s.out" % n), "w").write("pronto %s\nSOURCE_STATUS {\"%s\": \"ok\"}\n" % (n, n))
        open(os.path.join(T, "passo2-%s.rc" % n), "w").write("0\n")
    lento = subprocess.Popen([sys.executable, "-c",
                              "import os,sys,time\ntime.sleep(4)\nt=sys.argv[1]\n"
                              "open(os.path.join(t,'passo2-informativos.out'),'w').write('stf1237 NOVA\\n"
                              "SOURCE_STATUS {\"informativos_docs\": \"ok\"}\\n')\n"
                              "open(os.path.join(t,'passo2-informativos.rc'),'w').write('0\\n')\n", T])
    from datetime import datetime, timedelta
    json.dump({"execution_id": "E1", "pids": {"informativos": lento.pid},
               "disparado_em": (datetime.now().astimezone() - timedelta(seconds=30)).isoformat(timespec="seconds")},
              open(os.path.join(T, "passo2-disparo.json"), "w"))
    out = aguardar(d, "--mais", "1")
    ok("pronto coleta_web" in out and "pronto versiculo" in out and "stf1237" not in out, out)
    ok(re.search(r"^AINDA RODANDO informativos\.py \((3\d|4\d) s desde o disparo\) — para esperar mais: "
                 r"python3 work/aguardar_coleta\.py --mais N", out, re.M), out)
    ok("== informativos.py (exit ?; segundo plano) — AINDA RODANDO (" in out, out)
    ok(json.loads(out.strip().splitlines()[-1][len("SOURCE_STATUS "):]) == {"coleta_web": "ok", "versiculo": "ok"}, out)
    out = aguardar(d, "--mais", "20")
    lento.wait()
    ok("stf1237 NOVA" in out and "AINDA RODANDO" not in out, out)
    ok("== coleta_web.py (exit 0; saída já impressa inteira na chamada anterior)" in out
       and "pronto coleta_web" not in out, "o que já saiu não se repete no --mais: " + out)
    ok(json.loads(out.strip().splitlines()[-1][len("SOURCE_STATUS "):]) ==
       {"coleta_web": "ok", "informativos_docs": "ok", "versiculo": "ok"}, "SOURCE_STATUS completo")
    ok("pronto coleta_web" in aguardar(d), "sem --mais: tudo de novo")


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
def rodar_inicio(agora, *args, estado_data="2026-11-16", extra_concursos=(), banca_mod=None, mod_concursos=None):
    import inicio
    d = tempfile.mkdtemp(dir=TMPDIR)
    t = os.path.join(d, "tmp")
    os.makedirs(t)
    shutil.copytree(os.path.join(WORK, "prompts"), os.path.join(d, "prompts"))
    shutil.copy(os.path.join(WORK, "munger-quotes.json"), d)
    led = json.load(open(os.path.join(WORK, "robozinho-aprendizado.json"), encoding="utf-8"))
    led["concursos"] = regs("2a9eac9") + list(extra_concursos)
    if mod_concursos:
        mod_concursos(led["concursos"])
    json.dump(led, open(os.path.join(d, "robozinho-aprendizado.json"), "w"), ensure_ascii=False)
    json.dump({"ultima_execucao": {"execution_id": "%s-7h" % estado_data, "date": estado_data, "delivery": "draft",
                                   "email_subject": "S", "draft_id": "r",
                                   "window_end": "%sT07:07:30-03:00" % estado_data}},
              open(os.path.join(d, "robozinho-estado.json"), "w"))
    banca = json.loads(fx("bancas-1611.json"))
    if banca_mod:
        banca_mod(banca)
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
def inicio_errata_rodape_gap_armadilhas():
    out, j, t = rodar_inicio("2026-11-17T07:05:00-03:00")
    cc = open(os.path.join(t, "coletor-concursos.md"), encoding="utf-8").read()
    ok("errata_2026_11_16:" not in cc, "errata_* não é tarefa do coletor de concursos")
    ok("- errata_2026_11_16 [ativa" in out.split("PENDÊNCIAS VIVAS:")[1], "a errata segue no LEDGER (com o texto)")
    arm = out.split("ARMADILHAS (checklist")[1].split("PENDÊNCIAS VIVAS:")[0]
    ok("- jota_link_wrapper_mismatch: Link do JOTA só o que o coletor trouxe do work/resolver_jota.py" in arm
       and "1 tentativa por item" not in arm and "BLOQUEADO" in arm and "RECUSADO" in arm and "JA_PUBLICADA" in arm, arm)
    ok("GMAIL_APOS = a data do início da janela (o dia anterior, se o início for antes das 06:00)" in arm
       and "(dia anterior ao início da janela)" not in arm, arm)
    led = json.load(open(os.path.join(os.path.dirname(t), "robozinho-aprendizado.json"), encoding="utf-8"))
    ok(any("1 tentativa por item" in x.get("regra", "") for x in led["armadilhas"]),
       "o inicio só migra em memória (quem grava é o helper)")
    out, _, _ = rodar_inicio("2026-11-27T07:05:00-03:00", estado_data="2026-11-16")
    ok("ALERTA: GAP > 7 dias (a última janela terminou em 2026-11-16T07:07:30-03:00): cobrir só 7 dias e dizer em "
       "email.limitacoes que o intervalo além do teto pode ter lacunas" in out, [l for l in out.splitlines() if "GAP" in l])
    esperado = {"2026-11-19T15:00:00": "amanhã", "2026-11-20T15:00:00": "segunda-feira",
                "2026-11-21T15:00:00": "segunda-feira", "2026-11-22T15:00:00": "amanhã"}
    for agora, rod in esperado.items():
        _, j, _ = rodar_inicio(agora, "--extra", estado_data="2026-11-19")
        ok(j["rodape"] == rod, "Extra %s (%s): %r" % (agora[:10], j["dia_semana"], j["rodape"]))
    for agora, rod in (("2026-11-20T07:05:00-03:00", "segunda-feira"), ("2026-11-23T07:05:00-03:00", "amanhã")):
        _, j, _ = rodar_inicio(agora, estado_data="2026-11-19")
        ok(j["rodape"] == rod, "diária %s: %r" % (agora[:10], j["rodape"]))


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
    res = tjap("b80a3bd", vistos_sem_ret2(), hoje="2026-11-17")    # com URLs vistas: a 2ª Retificação é nova
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


def falha_de_push(cenario):
    """finalizar.sh (sem as esperas entre tentativas) com: 'hook' = pre-receive que sempre recusa; 'concorrente+hook'
    = main andou no remoto (ledger com marca_concorrente) e o hook recusa o push da reaplicação; 'helper2' = main
    andou e traz um helper que falha (a reaplicação não termina)."""
    import tarfile
    base, sess, t, g, run = repo_finalizar()
    outro = os.path.join(base, "outro")
    g(base, "clone", "-q", "origin.git", outro)
    fin = os.path.join(outro, "work", "finalizar.sh")
    src = open(fin).read()
    open(fin, "w").write(src.replace("for espera in 0 2 4 8 16; do", "for espera in 0 0 0 0 0; do"))
    g(outro, "commit", "-qam", "finalizar sem espera")
    g(outro, "push", "-q", "origin", "main")
    g(sess, "fetch", "-q", "origin")
    g(sess, "reset", "-q", "--hard", "origin/main")
    run(sys.executable, "work/montar_email.py")
    if cenario != "hook":
        pl = os.path.join(outro, "work", "robozinho-aprendizado.json")
        led = json.load(open(pl))
        led["marca_concorrente"] = "x"
        json.dump(led, open(pl, "w"), ensure_ascii=False, indent=1)
        if cenario == "helper2":
            h = os.path.join(outro, "work", "Update-Historico.py")
            src = open(h).read()
            open(h, "w").write(src.replace("import argparse\n", "import argparse\nraise SystemExit(1)\n", 1))
        g(outro, "commit", "-qam", "concorrente")
        g(outro, "push", "-q", "origin", "main")
    if cenario != "helper2":
        hook = os.path.join(base, "origin.git", "hooks", "pre-receive")
        open(hook, "w").write("#!/bin/sh\necho 'recusado pelo hook' >&2\nexit 1\n")
        os.chmod(hook, 0o755)
    rc, out = run("bash", "work/finalizar.sh", "--draft-id", "r-X", "--message-id", "m-X")
    est = [l for l in out.splitlines() if l.startswith("ESTADO:")]
    bk = os.path.join(t, "robozinho-estado-backup-2026-11-17-7h.tar.gz")
    with tarfile.open(bk) as tf:
        marca = "marca_concorrente" in json.load(tf.extractfile("work/robozinho-aprendizado.json"))
    sha = lambda ref: g(sess, "rev-parse", "--short", ref).stdout.strip()
    return rc, out, est[0] if est else "", marca, sha, g, sess


@teste
def finalizar_falha_estado_e_recusa_de_hook():
    # (3) hook do servidor recusando ("[remote rejected]") não é "main andou": nada de reset/reaplicação
    rc, out, est, marca, sha, g, sess = falha_de_push("hook")
    ok(rc == 3 and "PUSH: recusado (main andou" not in out and "PUSH: FALHOU (apos 5 tentativas)" in out, out[-600:])
    ok("(commit local %s) — para reaplicar: tar -xzf" % sha("HEAD") in est
       and "Robozinho: execução" in g(sess, "log", "-1", "--format=%s").stdout, est)
    # (1) reaplicação OK e push recusado de novo: a cópia é a da ÚLTIMA rodada (com a mudança concorrente)
    rc, out, est, marca, sha, g, sess = falha_de_push("concorrente+hook")
    ok(rc == 3 and "PUSH: recusado (main andou no remoto)" in out and out.count("STATUS: OK") == 2, out[-600:])
    ok(marca, "tar da 2ª rodada (com a mudança concorrente)")
    ok("(commit local %s) — para reaplicar: tar -xzf" % sha("HEAD") in est
       and g(sess, "merge-base", "--is-ancestor", "origin/main", "HEAD").returncode == 0, est)
    # (2) helper da reaplicação falhou: o commit impresso é o da 1ª rodada (não origin/main) e o tar não é aplicável
    rc, out, est, marca, sha, g, sess = falha_de_push("helper2")
    ok(rc == 3 and "PUSH: FALHOU (helper na reaplicacao" in out and not marca, out[-600:])
    m = re.search(r"commit local (\w+), da 1a rodada", est)
    ok(m and m.group(1) != sha("origin/main") and m.group(1) != sha("HEAD")
       and "Robozinho: execução" in g(sess, "log", "-1", "--format=%s", m.group(1)).stdout, est)
    ok("NAO aplique o tar sobre a main atual" in est and "rode bash work/finalizar.sh de novo" in est, est)


# ------------------------------------------------------------------ volta 2 do reteste
@teste
def classe_prazo_formas_de_escrever():
    # sem `tipo`, estes jeitos de escrever o fim/início das inscrições caíam em "outro" e desligavam o selo por data
    for ev in ("data limite para inscrições", "prazo limite de inscrição", "prazo de inscrição termina",
               "inscrições (prorrogadas)", "inscrições prorrogadas até 21/11", "prorrogação das inscrições",
               "inscrições abertas até 21/11", "inscrição até 21/11", "inscrições encerram em 21/11",
               "Fim das Inscrições (taxa R$ 120)", "fim das inscrições", "último dia de inscrição",
               "prazo final de inscrição", "encerramento das inscrições", "fim das inscrições, 16h (prorrogado)"):
        ok(selos.classe_prazo({"evento": ev}) == "inscricoes_fim", "fim: %s -> %s" % (ev, selos.classe_prazo({"evento": ev})))
    for ev in ("inscrições a partir de 10/11", "inscrições abertas a partir de 10/11", "inscrições abrem em 10/11",
               "início das inscrições", "abertura das inscrições"):
        ok(selos.classe_prazo({"evento": ev}) == "inscricoes_inicio", "início: %s" % ev)
    # pagamento, isenção, inscrição definitiva e eventos sobre as inscrições continuam fora
    for ev in ("pagamento da taxa de inscrição (fim)", "prazo de pagamento da inscrição termina",
               "data limite para pagamento da taxa de inscrição", "prorrogado o prazo de pagamento da inscrição",
               "fim do prazo de pedido de isenção da taxa de inscrição", "inscrições para isenção até 10/11",
               "fim da inscrição definitiva (fonte secundária)", "convocação para inscrição definitiva",
               "resultado das inscrições deferidas", "homologação das inscrições", "inscrições"):
        ok(selos.classe_prazo({"evento": ev}) == "outro", "outro: %s -> %s" % (ev, selos.classe_prazo({"evento": ev})))
    # os eventos reais (ledger e histórico, git) não mudam de classe
    for c in regs("2a9eac9") + regs("b80a3bd") + regs("2426d11"):
        for p in c.get("prazos") or []:
            ev = p.get("evento") or ""
            esperado = ("outro" if re.search(r"definitiv|resultado|convoca", ev, re.I) else
                        "inscricoes_inicio" if re.search(r"in[íi]cio", ev, re.I) else
                        "inscricoes_fim" if re.search(r"fim das inscri", ev, re.I) else
                        "prova" if re.search(r"prova", ev, re.I) else "outro")
            ok(selos.classe_prazo({"evento": ev}) == esperado, "regressão: %s -> %s" % (ev, selos.classe_prazo({"evento": ev})))
    # o tipo explícito continua prevalecendo sobre o evento
    ok(selos.classe_prazo({"evento": "data limite para inscrições", "tipo": "outro"}) == "outro", "tipo vence")


RE_AVISO_TIPO_MON = re.compile(r"^ledger_updates\.concursos\.(\S+?)\.prazos\[(\d+)\]\.tipo\b")   # montar_email.py


@teste
def tipo_outro_no_fim_das_inscricoes_avisa():
    pz = {"data": "2026-11-21", "evento": "fim das inscrições, 16h (prorrogado)", "confirmado": True}
    ok(selos.tipo_contradiz_evento(dict(pz, tipo="outro")) == "inscricoes_fim", "outro")
    ok(selos.tipo_contradiz_evento(dict(pz, tipo="prova")) == "inscricoes_fim", "prova")
    ok(selos.tipo_contradiz_evento(dict(pz, tipo="inscricoes_fim")) is None, "tipo certo")
    ok(selos.tipo_contradiz_evento(pz) is None and selos.tipo_contradiz_evento(dict(pz, tipo="xx")) is None, "sem tipo")
    ok(selos.tipo_contradiz_evento({"evento": "início das inscrições", "tipo": "outro"}) == "inscricoes_inicio", "início")
    for ev in ("fim da inscrição definitiva", "pagamento da taxa até 19/11 (inscrições)", "resultado da prova"):
        ok(selos.tipo_contradiz_evento({"evento": ev, "tipo": "outro"}) is None, "outro legítimo: %s" % ev)
    # o caso do reteste (19/11, sem a banca): tipo 'outro' tirava o prazo do selo por data, sem aviso nenhum
    r = {"id": "tjap_juiz", "selo": "INSCRIÇÕES ABERTAS", "fonte": "https://conhecimento.fgv.br/concursos/tjap26",
         "prazos": [dict(pz, tipo="outro")]}
    ok(selos.selo_por_data(r, D("2026-11-23")) == ("INSCRIÇÕES ABERTAS", None), "o tipo prevalece (nada corrigido)")
    led = json.loads(open(os.path.join(AQUI, "fixtures", "mon", "ledger-1611.json"), encoding="utf-8").read())
    fonte = "https://conhecimento.fgv.br/concursos/tjap26"
    for tipo, selo in (("outro", "INSCRIÇÕES ABERTAS"), ("prova", "INSCRIÇÕES ABERTAS"), ("outro", None)):
        u = {"prazos": [dict(pz, tipo=tipo), {"data": "2027-01-24", "evento": "prova objetiva (prevista)",
                                               "confirmado": True, "tipo": "prova"}], "fonte": fonte}
        if selo:
            u["selo"] = selo
        upd = {"concursos": {"tjap_juiz": u}}
        ok(uh.validar_ledger_updates(upd, copy.deepcopy(led), hoje="2026-11-19") == [], "não é ERRO")
        av = [a for a in uh.avisos_ledger_updates(upd, led, "2026-11-19") if ".prazos[" in a]
        ok(len(av) == 1 and RE_AVISO_TIPO_MON.match(av[0]).groups() == ("tjap_juiz", "0"), "1 AVISO, chave do MON: %r" % av)
        ok(("'%s' num prazo cujo evento é o fim das inscrições («fim das inscrições, 16h (prorrogado)») — com esse "
            "tipo o selo por data ignora o prazo" % tipo) in av[0] and "escreva tipo 'inscricoes_fim' ou omita o tipo; "
           "se não é, aceite o aviso" in av[0], av[0])
        # com o selo escrito, diz o que a data daria (o registro tinha ENCERRA EM BREVE: sem selo, nada a dizer)
        ok(("o selo por data daria 'ENCERRA EM BREVE': fim das inscrições em 2 dias (21/11)" in av[0]) == bool(selo),
           av[0])
    upd = {"concursos": {"tjap_juiz": {"prazos": [dict(pz, tipo="inscricoes_fim")], "fonte": fonte,
                                       "selo": "INSCRIÇÕES ABERTAS"}}}
    av = uh.avisos_ledger_updates(upd, led, "2026-11-19")
    ok(not any(".prazos[" in a for a in av) and any("contradiz o selo por data 'ENCERRA EM BREVE'" in a for a in av),
       "tipo certo: só o aviso do selo escrito: %r" % av)
    ok(not any(".prazos[" in a for a in uh.avisos_ledger_updates(
        {"concursos": {"tjap_juiz": {"remover": True, "desfecho": "x", "prazos": [dict(pz, tipo="outro")]}}},
        led, "2026-11-19")), "remover: sem aviso")


@teste
def inicio_prazo_vencido_confirmado_pela_banca():
    # 19/11 com a banca lida: o mesmo registro tinha ALERTA de prazo vencido e SELO POR DATA → ENCERRADAS
    out, _, _ = rodar_inicio("2026-11-19T07:05:00-03:00", estado_data="2026-11-18")
    for org, ident, ret in (("TJAP", "tjap_juiz", "13/11"), ("TJPB", "tjpb_apoio", "12/11")):
        ok("ALERTA: prazo vencido 18/11 (ontem) %s" % org not in out, "sem ALERTA: %s" % org)
        ok(("PRAZO VENCIDO (sem ação): 18/11 (ontem) %s — fim das inscrições" % org) in out and
           ("(id %s) — encerramento confirmado pela banca oficial lida hoje (última retificação %s): selo INSCRIÇÕES "
            "ENCERRADAS automático" % (ident, ret)) in out, [l for l in out.splitlines() if ident in l][:3])
        ok("SELO POR DATA: %s ENCERRA EM BREVE → INSCRIÇÕES ENCERRADAS" % ident in out, "o selo por data continua")
    # dia seguinte, com o selo já ENCERRADAS no registro: continua sem ALERTA (a banca segue confirmando)
    def encerradas(cs):
        for c in cs:
            if c["id"] in ("tjap_juiz", "tjpb_apoio"):
                c["selo"] = "INSCRIÇÕES ENCERRADAS"
    out, _, _ = rodar_inicio("2026-11-20T07:05:00-03:00", estado_data="2026-11-19", mod_concursos=encerradas)
    ok("ALERTA: prazo vencido 18/11 (há 2 dias) TJAP" not in out and
       "PRAZO VENCIDO (sem ação): 18/11 (há 2 dias) TJAP" in out and "SELO POR DATA: tjap_juiz" not in out, "20/11")
    # retificação no dia do prazo (prorrogação possível) ou banca não lida: o ALERTA fica
    def retificou(b):
        for c in b["concursos"]:
            if c["slug"] == "tjap26":
                c["ultima_retificacao"] = "2026-11-18"
    out, _, _ = rodar_inicio("2026-11-19T07:05:00-03:00", estado_data="2026-11-18", banca_mod=retificou)
    ok("ALERTA: prazo vencido 18/11 (ontem) TJAP" in out and "PRAZO VENCIDO (sem ação): 18/11 (ontem) TJAP" not in out
       and "PRAZO VENCIDO (sem ação): 18/11 (ontem) TJPB" in out, "retificação em 18/11")
    def sem_tjap(b):
        b["concursos"] = [c for c in b["concursos"] if c["slug"] != "tjap26"]
    out, _, _ = rodar_inicio("2026-11-19T07:05:00-03:00", estado_data="2026-11-18", banca_mod=sem_tjap)
    ok("ALERTA: prazo vencido 18/11 (ontem) TJAP" in out and "PRAZO VENCIDO (sem ação): 18/11 (ontem) TJAP" not in out,
       "banca do TJAP não lida")


@teste
def helper_errata_removida_sem_falso_indicio():
    d = tempfile.mkdtemp(dir=TMPDIR)
    caminho = os.path.join(d, "led.json")
    led = json.loads(open(os.path.join(AQUI, "fixtures", "mon", "ledger-1611.json"), encoding="utf-8").read())
    json.dump(led, open(caminho, "w"), ensure_ascii=False)
    log = []
    ex = {"execution_id": "2026-11-17-7h", "date": "2026-11-17", "source_status": {},
          "pendencias": [{"id": "errata_2026_11_16", "texto": "errata"}, {"id": "outra_fora", "texto": "x"}],
          "ledger_updates": {"pendencias": {"errata_2026_11_16": {"remover": True, "desfecho": "errata publicada"}}}}
    uh.aplicar_ledger(caminho, ex, log.append)
    ok(any("errata_2026_11_16 removida" in l for l in log), log)
    ok(not any("errata_2026_11_16 saiu na edicao" in l for l in log), "falso indício: %r" % log)
    ok(any("outra_fora saiu na edicao mas nao existe no ledger" in l for l in log), "o indício real continua")


# ------------------------------------------------------------------ CORE volta 1 (P2, P3, P4)
TRECHO_TJSC = "das 16h do dia 19 de outubro de 2026 até às 16h do dia 26 de novembro de 2026"
TRECHO_TJAP = "das 16h do dia 13 de outubro de 2026 até às 16h do dia 18 de novembro de 2026"


def com_fim_tjsc(rs, dia):
    for c in rs:
        if c["id"] == "tjsc_juiz":
            c["linha"] = c["linha"].replace("até 16h de 26/11", "até 16h de %s/11" % dia)
            c["prazos"][0]["data"] = "2026-11-%s" % dia
    return rs


def banca_relida(dia, slug, ident, fim, trecho, inicio, rs, releitura="prazo do registro", lido_em=None):
    """bancas.json de `dia` (bancas-1611 reaproveitada) com o edital de `slug` relido hoje e o DIVERGE da manhã
    calculado como o bancas.analisar o faz (contra o registro `rs`)."""
    b = json.loads(fx("bancas-1611.json"))
    b.update(data=dia, dominio=bancas.DOMINIO)
    for c in b["concursos"]:
        if c["slug"] == slug:
            c["releitura"] = releitura
            c["edital"] = {"inscrições": trecho}
            c["inscricoes"] = {"inicio": inicio, "fim": fim, "trecho": trecho, "origem": "edital"}
            if lido_em:
                c["inscricoes"]["lido_em"] = lido_em
            c["divergencias"] = bancas.divergencias(c, [r for r in rs if r["id"] == ident], D(dia))
    return b


def montador_e_helper_em_memoria(led, upd, banca, dia):
    """O comparador: o MESMO estado (selo, verificado_em) no e-mail (montar_email.estado_concursos) e no ledger
    (helper: aplicar_updates + aplicar_mecanicos_concursos) para a mesma entrada. Devolve (email, ledger, avisos do
    montador, log do helper)."""
    import montar_email
    d = tempfile.mkdtemp(dir=TMPDIR)
    bp = os.path.join(d, "bancas.json")
    json.dump(banca, open(bp, "w"), ensure_ascii=False)
    avisos = []
    ctx = montar_email.estado_concursos({"ledger_updates": {"concursos": copy.deepcopy(upd)}},
                                        {"data": dia, "execution_id": dia + "-7h"}, copy.deepcopy(led),
                                        {"bancas": bp, "historico": os.path.join(d, "sem-historico.json")}, avisos)
    em = {c["id"]: (c.get("selo"), c.get("verificado_em")) for c in ctx["regs"]}
    l2, u2, log = copy.deepcopy(led), {"concursos": copy.deepcopy(upd)}, []
    uh.aplicar_updates(l2, u2, dia, log.append)
    uh.aplicar_mecanicos_concursos(l2, u2, dia, banca, log.append)
    lg = {c["id"]: (c.get("selo"), c.get("verificado_em")) for c in l2["concursos"]}
    dif = {k: (em.get(k), lg.get(k)) for k in set(em) | set(lg) if em.get(k) != lg.get(k)}
    ok(not dif, "montador e helper divergem: %r" % dif)
    return em, lg, avisos, log


@teste
def selo_suspenso_com_divergencia():
    """P2: com divergência pendente (o edital lido hoje contesta a data do registro, já com o update de hoje), o selo
    por data fica SUSPENSO no helper, no montador e no inicio (fica o selo do registro; aviso com as duas datas).
    TJSC com fim 25/11 no registro e 26/11 no edital: em 18/11 virava ENCERRA EM BREVE (a data oficial dá ABERTAS)."""
    rs = com_fim_tjsc(regs("2a9eac9"), "25")
    b = banca_relida("2026-11-18", "tjscjuiz26", "tjsc_juiz", "2026-11-26", TRECHO_TJSC, "2026-10-19", rs)
    ok(b["concursos"][1]["divergencias"], "pré-condição: DIVERGE da manhã")
    pend = bancas.divergencias_pendentes(b, rs, D("2026-11-18"), {})
    ok(set(pend) == {"tjsc_juiz"} and pend["tjsc_juiz"]["fim_edital"] == "2026-11-26"
       and pend["tjsc_juiz"]["fim_registro"] == "2026-11-25" and not pend["tjsc_juiz"]["escrito_hoje"], pend)
    tjsc = next(c for c in rs if c["id"] == "tjsc_juiz")
    ctx = bancas.contexto_selos(b, rs, D("2026-11-18"), {})
    selo, motivo, susp = bancas.selo_do_dia(tjsc, D("2026-11-18"), ctx, pend)
    ok(selo == "INSCRIÇÕES ABERTAS" and motivo is None and susp.startswith("selo por data suspenso em tjsc_juiz: ")
       and "25/11" in susp and "26/11" in susp and "ledger_updates.concursos.tjsc_juiz" in susp, susp)
    ok(bancas.selo_do_dia(tjsc, D("2026-11-18"), ctx, {})[:2] == selos.selo_por_data(tjsc, D("2026-11-18"))
       == ("ENCERRA EM BREVE", "INSCRIÇÕES ABERTAS → ENCERRA EM BREVE: fim das inscrições em 7 dias (25/11)"),
       "sem divergência: o selo por data de sempre")
    fora = dict(tjsc, selo="EM ANDAMENTO")
    ok(bancas.selo_do_dia(fora, D("2026-11-18"), ctx, pend) == ("EM ANDAMENTO", None, None), "fora da família: nada")
    led = {"concursos": rs}
    linha26 = reg("2a9eac9", "tjsc_juiz")["linha"]
    for rotulo, upd in (("sem update", {}), ("só a linha", {"tjsc_juiz": {"linha": linha26}})):
        em, lg, av, log = montador_e_helper_em_memoria(led, upd, b, "2026-11-18")
        ok(em["tjsc_juiz"] == ("INSCRIÇÕES ABERTAS", "2026-11-16"), "%s: suspenso e sem carimbo: %r" % (rotulo, em))
        ok(any(a.startswith("selo por data suspenso em tjsc_juiz") for a in av)
           and not any(a.startswith("selo por data: tjsc_juiz") for a in av), "%s: aviso do montador %r" % (rotulo, av))
        ok("ALERTA: selo por data suspenso em tjsc_juiz" in "\n".join(log)
           and not any(l.startswith("AVISO: selo por data: tjsc_juiz") for l in log), "%s: log %r" % (rotulo, log))
        ok(em["tjpb_apoio"] == ("ENCERRA HOJE", "2026-11-18"), "os outros seguem a regra de sempre: %r" % em)
    em, lg, av, log = montador_e_helper_em_memoria(led, {"tjsc_juiz": {"linha": linha26, "prazos": reg(
        "2a9eac9", "tjsc_juiz")["prazos"]}}, b, "2026-11-18")
    ok(em["tjsc_juiz"] == ("INSCRIÇÕES ABERTAS", "2026-11-18") and not any("suspenso" in a for a in av + log),
       "prazos corrigidos: carimbo e selo por data: %r" % (em["tjsc_juiz"],))
    # inicio.py (manhã de 18/11, a mesma banca): nada de "SELO POR DATA … automático" com a data contestada
    out, _, _ = rodar_inicio("2026-11-18T07:05:00-03:00", estado_data="2026-11-17",
                             banca_mod=lambda x: x.update(copy.deepcopy(b)), mod_concursos=lambda cs: com_fim_tjsc(cs, "25"))
    ok("SELO POR DATA: tjsc_juiz" not in out and "ALERTA: selo por data suspenso em tjsc_juiz" in out
       and "DIVERGE DO REGISTRO: tjsc_juiz" in out, [l for l in out.splitlines() if "tjsc" in l][:6])


@teste
def prazo_escrito_hoje_contra_edital():
    """P3: o prazo escrito hoje em ledger_updates que contradiz o edital lido hoje (registro igual ao edital) vira
    divergência pendente (sem carimbo, selo suspenso), AVISO no --validar e ALERTA no relatório do helper; nada com
    o update igual ao edital, sem edital relido hoje ou com bancas.json de outro dia."""
    rs = regs("2a9eac9")
    b = banca_relida("2026-11-19", "tjap26", "tjap_juiz", "2026-11-18", TRECHO_TJAP, "2026-10-13", rs)
    ok(not b["concursos"][2]["divergencias"], "pré-condição: o registro (18/11) bate com o edital")
    prorrog = {"tjap_juiz": {"prazos": [{"data": "2026-11-21", "evento": "fim das inscrições, 16h (prorrogado)",
                                         "confirmado": True}],
                             "fonte": "https://conhecimento.fgv.br/concursos/tjap26"}}
    pend = bancas.divergencias_pendentes(b, rs, D("2026-11-19"), prorrog)
    ok(set(pend) == {"tjap_juiz"} and pend["tjap_juiz"]["escrito_hoje"] and pend["tjap_juiz"]["fim_registro"]
       == "2026-11-21", "antes passava sem aviso: %r" % pend)
    av = uh.avisos_ledger_updates({"concursos": prorrog}, {"concursos": rs}, "2026-11-19", b)
    p3 = [a for a in av if a.startswith("prazo escrito hoje difere do edital lido hoje: tjap_juiz")]
    ok(len(p3) == 1 and "18 de novembro de 2026" in p3[0] and "× update \"prazo 21/11/2026" in p3[0]
       and not any(a.startswith("DIVERGE DO REGISTRO em tjap_juiz") for a in av), av)
    ok("tjap_juiz" not in bancas.carimbos(b, rs, D("2026-11-19"), upd=prorrog)
       and "tjap_juiz" not in bancas.contexto_selos(b, rs, D("2026-11-19"), prorrog), "regra do P2: sem carimbo/banca")
    em, lg, avm, log = montador_e_helper_em_memoria({"concursos": rs}, prorrog, b, "2026-11-19")
    ok(em["tjap_juiz"] == ("ENCERRA EM BREVE", "2026-11-16") and any(a.startswith("selo por data suspenso em tjap_juiz")
                                                                      for a in avm), "selo suspenso: %r" % (em,))
    # sem falso positivo
    igual = {"tjap_juiz": {"prazos": [{"data": "2026-11-18", "evento": "fim das inscrições, 16h (prorrogado)",
                                       "confirmado": True}]}}
    ok(bancas.divergencias_pendentes(b, rs, D("2026-11-19"), igual) == {}, "update igual ao edital")
    ok(bancas.divergencias_pendentes(b, rs, D("2026-11-19"), {}) == {}, "sem update")
    b_sem = banca_relida("2026-11-19", "tjap26", "tjap_juiz", "2026-11-18", TRECHO_TJAP, "2026-10-13", rs, releitura="")
    ok(bancas.divergencias_pendentes(b_sem, rs, D("2026-11-19"), prorrog) == {}, "inscrições sem releitura hoje")
    b_velho = banca_relida("2026-11-19", "tjap26", "tjap_juiz", "2026-11-18", TRECHO_TJAP, "2026-10-13", rs,
                           lido_em="2026-11-18")
    ok(bancas.divergencias_pendentes(b_velho, rs, D("2026-11-19"), prorrog) == {}, "trecho lido noutro dia")
    ok(bancas.divergencias_pendentes(dict(b, data="2026-11-18"), rs, D("2026-11-19"), prorrog) == {},
       "bancas.json de outro dia")
    b_err = copy.deepcopy(b)
    b_err["concursos"][2]["edital_erro"] = "http 503"
    ok(bancas.divergencias_pendentes(b_err, rs, D("2026-11-19"), prorrog) == {}, "edital não lido")
    # o bancas.analisar marca o dia da leitura do trecho
    res = tjap("2a9eac9", hoje="2026-11-17")
    ok(res["concursos"][0]["inscricoes"]["lido_em"] == "2026-11-17", res["concursos"][0].get("inscricoes"))
    # helper (gravação): ALERTA no relatório (AVISO no --validar, que o montador mostra como acionável)
    d = pasta_helper()
    json.dump(dict(b, execution_id="2026-11-18-7h", data="2026-11-18"), open(os.path.join(d, "bancas.json"), "w"),
              ensure_ascii=False)
    ex = {"delivery": "draft", "items": [], "source_status": {}, "ledger_updates": {"concursos": {"tjap_juiz": {
        "prazos": [{"data": "2026-11-25", "evento": "fim das inscrições, 16h (prorrogado)", "confirmado": True}],
        "fonte": "https://conhecimento.fgv.br/concursos/tjap26"}}}}
    rc, out = rodar_helper(d, ex, "--validar")
    ok(rc == 0 and "AVISO: prazo escrito hoje difere do edital lido hoje: tjap_juiz" in out, out)
    rc, out = rodar_helper(d, ex, "--draft-id", "r1")
    ok(rc == 0 and "ALERTA: prazo escrito hoje difere do edital lido hoje: tjap_juiz" in out
       and "AVISO: prazo escrito hoje" not in out and "ALERTA: selo por data suspenso em tjap_juiz" in out, out)
    cs = {c["id"]: c for c in json.load(open(os.path.join(d, "led.json")))["concursos"]}
    ok(cs["tjap_juiz"]["verificado_em"] == "2026-11-16" and cs["tjap_juiz"]["selo"] == "ENCERRA EM BREVE",
       "gravado sem carimbo e com o selo do registro: %r" % {k: cs["tjap_juiz"][k] for k in ("selo", "verificado_em")})


@teste
def helper_relatorio_sem_ruido():
    """P4: sem "Ledger: concursos <id> atualizada ()" quando o update só copiava o selo; com delivery
    draft_ja_existente e sem itens, sem "pendencia X nao foi a edicao"."""
    d = pasta_helper()
    ex = {"delivery": "draft", "items": [], "source_status": {},
          "ledger_updates": {"concursos": {"tjpb_apoio": {"selo": "ENCERRA EM BREVE"},
                                           "tjsc_juiz": {"selo": "INSCRIÇÕES ABERTAS", "verificado_em": "2026-11-18"}}}}
    rc, out = rodar_helper(d, ex, "--draft-id", "r1")
    ok(rc == 0 and "selo igual ao do registro retirado do update" in out, out)
    ok("atualizada ()" not in out and "Ledger: concursos tjpb_apoio atualizada" not in out
       and "Ledger: concursos tjsc_juiz atualizada (verificado_em)" in out, out)
    log = []
    led = copy.deepcopy(LED)
    uh.aplicar_updates(led, {"concursos": {"ofi": {}}, "pendencias": {"ofi_verificar": {}}}, "2026-11-17", log.append)
    ok(log == [], "update vazio não é registrado: %r" % log)
    d = pasta_helper()
    rc, out = rodar_helper(d, {"delivery": "draft_ja_existente", "items": [], "source_status": {}}, "--draft-id", "r1")
    ok(rc == 0 and "STATUS: OK" in out and "nao foi a edicao" not in out, out)
    d = pasta_helper()
    rc, out = rodar_helper(d, {"delivery": "draft", "items": [], "source_status": {}}, "--draft-id", "r1")
    ok("Ledger: pendencia ofi_verificar nao foi a edicao" in out, "rascunho novo: o aviso continua")


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
