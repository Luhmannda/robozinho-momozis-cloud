#!/usr/bin/env python3
# =====================================================================
# test_concursos.py — testes da frente CONCURSOS (sem pytest, sem rede):
#   selos.py: PROVA EM BREVE sai da familia quando a prova passa (sem regressao a
#   INSCRICOES ENCERRADAS com a banca lida; o motivo casa o ACIONAVEL do
#   montador); prova adiada/distante sem prova passada segue as regras normais e
#   volta a PROVA EM BREVE na janela de 14 dias; candidato a remocao por datas so de
#   secundaria; _dm herda o ano do mesmo trecho e le 29/02; inicio coerente.
#   paginas_oficiais.py (paginas reduzidas do TRF2 e da PGE-RJ de 21/11/2026):
#   item = titulo + continuacao (o nome da Portaria nº 578 inteiro), ato sem
#   palavra-chave com data, titulo repetido com data nova e MUDOU, reordenar
#   nao e MUDOU, carimbo "atualizado em" nao e item, os 5 mais recentes na NOVA,
#   estado v1 relido sem MUDOU falso, IGUAL numa linha, FORA_DA_REDE sem baixar.
#   inicio.py: migracoes antes do ledger e nunca na RE-EXECUCAO (linhas impressas; ausente/erro =
#   ALERTA), escopo regional (FORA DO ESCOPO, sem fila/rodizio/foco/registro
#   atual), sonda proxy x site x SPA e REDE do ambiente (sem resposta = indeterminado,
#   nao liberado), url_oficial lida todo
#   dia e MUDOU no foco, dominio sem resposta nao baixado, prazo so secundario
#   so em D-7/D-1/D0/D+1, pendencia COBERTA/SO VIGIAR, {prox} e DATA_MIN_NOVO,
#   consultas regionais do apoio, candidato a remocao (secundaria), regra
#   de armadilha sem a medicao fixa de rede.
# USO: python3 work/testes/test_concursos.py   (imprime OK/FALHOU; sai != 0 em falha)
# Tudo roda em pastas temporarias (ROBOZINHO_TMP proprio); rede simulada.
# =====================================================================

import contextlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import traceback
import types
from datetime import date

AQUI = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.dirname(AQUI)
FIX = os.path.join(AQUI, "fixtures", "concursos")
TMPDIR = tempfile.mkdtemp(prefix="robozinho-conc-")
os.environ["ROBOZINHO_TMP"] = TMPDIR
sys.path.insert(0, WORK)

import selos             # noqa: E402
import bancas            # noqa: E402
import paginas_oficiais  # noqa: E402
import inicio            # noqa: E402
import montar_email      # noqa: E402

TESTES, FALHAS = [], []
D = date.fromisoformat


def teste(f):
    TESTES.append(f)
    return f


def ok(cond, msg):
    if not cond:
        raise AssertionError(msg)


def fx(nome):
    with open(os.path.join(FIX, nome), encoding="utf-8") as f:
        return f.read()


# ------------------------------------------------------------------ selos: PROVA EM BREVE
@teste
def prova_em_breve_sai_da_familia():
    tjrs = {"id": "tjrs_juiz", "selo": "PROVA EM BREVE", "fonte": "https://conhecimento.fgv.br/concursos/tjrsjuiz26",
            "prazos": [{"data": "2026-12-13", "evento": "prova objetiva (prevista)", "confirmado": True}]}
    ok(selos.selo_por_data(tjrs, D("2026-12-01")) == ("PROVA EM BREVE", None), "prova em 12 dias: fica")
    s, m = selos.selo_por_data(tjrs, D("2026-12-14"))
    ok(s == selos.SELO_SEM_CONFIRMACAO and "a prova de 13/12 já passou" in m and "PROVA REALIZADA" in m, (s, m))
    ok(montar_email.ACIONAVEL.search("selo por data: tjrs_juiz " + m), "o montador segura o rascunho: %s" % m)
    # TJAP com a banca lida e o fim das inscricoes vencido: nao volta a INSCRICOES ENCERRADAS
    tjap = {"id": "tjap_juiz", "selo": "PROVA EM BREVE",
            "prazos": [{"data": "2026-11-18", "evento": "fim das inscrições, 16h (prorrogado)", "confirmado": True},
                       {"data": "2027-01-24", "evento": "prova objetiva (prevista)", "confirmado": True}]}
    ok(selos.selo_por_data(tjap, D("2027-01-20"), banca_lida_hoje=True, ultima_retificacao="2026-11-13")[0]
       == "PROVA EM BREVE", "antes da prova")
    s, m = selos.selo_por_data(tjap, D("2027-01-25"), banca_lida_hoje=True, ultima_retificacao="2026-11-13")
    ok(s == selos.SELO_SEM_CONFIRMACAO and "24/01" in m, (s, m))
    # o mesmo pela regra unica (bancas.selo_do_dia), com o contexto da banca lida hoje
    ctx = {"tjap_juiz": {"banca_lida_hoje": True, "ultima_retificacao": "2026-11-13"}}
    ok(bancas.selo_do_dia(tjap, D("2027-01-25"), ctx, {})[0] == selos.SELO_SEM_CONFIRMACAO, "selo_do_dia")
    # 2a prova distante: a 1a passou, a proxima a mais de 14 dias
    duas = dict(tjrs, prazos=tjrs["prazos"] + [{"data": "2027-03-07", "evento": "prova discursiva", "confirmado": True}])
    s, m = selos.selo_por_data(duas, D("2026-12-14"))
    ok(s == selos.SELO_SEM_CONFIRMACAO and "13/12" in m, (s, m))
    ok("a próxima (07/03) está a mais de 14 dias" in m, m)
    # adiada (rev1 C1): so a data nova, a mais de 14 dias, sem prova passada -> regras normais, nao PENDENCIA (antes
    # caia para PENDENCIA e nunca voltava); a data entra na janela: PROVA EM BREVE; passa: sai da familia
    adiada = dict(tjrs, prazos=[{"data": "2027-02-07", "evento": "prova objetiva (adiada)", "confirmado": True}])
    ok(selos.selo_por_data(adiada, D("2026-12-14")) == ("PROVA EM BREVE", None), "adiada distante: fica")
    ok(selos.selo_por_data(adiada, D("2027-01-25")) == ("PROVA EM BREVE", None), "adiada na janela")
    s, m = selos.selo_por_data(adiada, D("2027-02-08"))
    ok(s == selos.SELO_SEM_CONFIRMACAO and "a prova de 07/02 já passou" in m, (s, m))
    # adiada com a banca lida e o fim das inscricoes vencido: INSCRICOES ENCERRADAS (regra normal) e volta a
    # PROVA EM BREVE quando a prova entra na janela
    adi_b = dict(adiada, prazos=adiada["prazos"] + [{"data": "2026-11-18", "evento": "fim das inscrições",
                                                      "confirmado": True}])
    s, m = selos.selo_por_data(adi_b, D("2026-12-14"), banca_lida_hoje=True, ultima_retificacao="2026-11-13")
    ok(s == "INSCRIÇÕES ENCERRADAS", (s, m))
    ok(selos.selo_por_data(dict(adi_b, selo=s), D("2027-01-25"), banca_lida_hoje=True,
                           ultima_retificacao="2026-11-13")[0] == "PROVA EM BREVE", "volta à janela da prova")
    # prova (a confirmar) na janela: fica; sem prazo de prova: fica (sem dado)
    sec = dict(tjrs, prazos=[{"data": "2026-12-20", "evento": "prova (fonte secundária)", "confirmado": False}])
    ok(selos.selo_por_data(sec, D("2026-12-14")) == ("PROVA EM BREVE", None), "secundária na janela")
    ok(selos.selo_por_data(dict(tjrs, prazos=[]), D("2026-12-14")) == ("PROVA EM BREVE", None), "sem prova")
    # inscricoes reabertas (ENCERRA EM BREVE) vencem a saida
    reab = dict(tjrs, prazos=[{"data": "2026-12-18", "evento": "fim das inscrições (reabertas)", "confirmado": True}])
    ok(selos.selo_por_data(reab, D("2026-12-14"))[0] == "ENCERRA EM BREVE", "inscrição reaberta")
    # fora da familia (ja escrito PROVA REALIZADA ou a PENDENCIA): nada muda sozinho
    ok(selos.selo_por_data(dict(tjrs, selo=selos.SELO_SEM_CONFIRMACAO), D("2026-12-15")) ==
       (selos.SELO_SEM_CONFIRMACAO, None), "estável")


@teste
def remocao_por_datas_de_secundaria():
    alepa = {"id": "alepa", "prazos": [{"data": "2026-10-20", "evento": "prova (fonte secundária)", "confirmado": False}]}
    ok(selos.candidato_remocao(alepa, D("2026-12-02")) == "secundária", "secundária vencida há 43 dias")
    ok(not selos.candidato_remocao(alepa, D("2026-11-10")), "há 21 dias: ainda não")
    futuro = dict(alepa, prazos=alepa["prazos"] + [{"data": "2027-01-10", "evento": "x", "confirmado": False}])
    ok(not selos.candidato_remocao(futuro, D("2026-12-02")), "etapa futura")
    conf = {"id": "c", "prazos": [{"data": "2026-09-01", "evento": "prova", "confirmado": True},
                                  {"data": "2026-11-20", "evento": "resultado (secundária)", "confirmado": False}]}
    ok(selos.candidato_remocao(conf, D("2026-12-02")) == "confirmados", "a regra dos confirmados continua")
    ok(selos.candidato_remocao({"id": "s", "prazos": []}, D("2026-12-02")) == "", "sem prazo: nunca")


@teste
def ano_das_datas_da_linha():
    r = {"linha": "DPE-MA — VII concurso (FCC, inscrições de 26/01 a 26/02 e prova em 19/04/2026)"}
    ok(selos.fim_inscricoes_registro(r, D("2026-11-20"))[0] == D("2026-02-26"), "fim herda 2026 (antes 2027)")
    ok(selos.inicio_inscricoes(r, D("2026-11-20")) == D("2026-01-26"), "início herda 2026")
    r = {"linha": "X — Juiz: inscrições de 02/06 a 01/07/2027"}
    ok(selos.inicio_inscricoes(r, D("2026-11-20")) == D("2027-06-02"), "início no ano do fim (antes 2026)")
    r = {"linha": "X — Juiz: inscrições de 20/12 a 15/01/2027"}
    ok(selos.inicio_inscricoes(r, D("2026-11-20")) == D("2026-12-20"), "virada do ano")
    m = selos.RE_LINHA_INI.search("inscrições de 29/02 a 10/03")
    ok(selos._dm(m, D("2028-01-10")) == D("2028-02-29"), "29/02 em ano bissexto")
    ok(selos._dm(m, D("2026-11-20")) is None, "29/02 sem ano bissexto perto")
    # sem ancora no trecho (';' separa): o ano mais proximo de hoje, como antes
    r = {"linha": "TJSC — Juiz: inscrições das 16h de 19/10 até 16h de 26/11, conforme a FGV; prova em 31/01/2027"}
    ok(selos.fim_inscricoes_registro(r, D("2026-11-20"))[0] == D("2026-11-26"), "fim pelo ano mais próximo")
    ok(selos.inicio_inscricoes(r, D("2026-11-20")) == D("2026-10-19"), "início coerente")
    # rev1 C6: a data de um ato citado no trecho nao e ancora (dava 2025); o fim do mesmo intervalo e
    r = {"linha": "TJXX — Juiz: inscrições de 20/10 até 26/11, conforme o Edital nº 1, de 15/10/2026"}
    ok(selos.fim_inscricoes_registro(r, D("2026-11-23"))[0] == D("2026-11-26"), "ato citado não ancora o fim")
    ok(selos.inicio_inscricoes(r, D("2026-11-23")) == D("2026-10-20"), "nem o início")
    r = {"linha": "Z — Juiz: inscrições até 05/01, segundo matéria de 20/12/2026"}
    ok(selos.fim_inscricoes_registro(r, D("2026-12-28"))[0] == D("2027-01-05"), "notícia citada não ancora")
    r = {"linha": "W — Juiz: inscrições das 16h de 19/10 até 16h de 26/11/2026"}
    ok(selos.inicio_inscricoes(r, D("2027-06-01")) == D("2026-10-19"), "fim do intervalo com hora")
    r = {"linha": "V — Juiz: inscrições de 01/12 a 20/12 e prova em 15/02/2027"}
    ok(selos.fim_inscricoes_registro(r, D("2026-06-01"))[0] == D("2026-12-20"), "etapa seguinte do cronograma")
    # inicio depois do fim confirmado: tenta o ano anterior
    r = {"linha": "Y: inscrições de 10/12 até 20/01", "prazos": [
        {"data": "2027-01-20", "evento": "fim das inscrições", "confirmado": True}]}
    ok(selos.inicio_inscricoes(r, D("2027-01-05")) == D("2026-12-10"), "início antes do fim")


# ------------------------------------------------------------------ paginas oficiais
URL_TRF2 = "https://www.trf2.jus.br/trf2/consultas-e-servicos/concursos-publicos-para-magistrados"
URL_PGE = "https://pge.rj.gov.br/concurso/19o-concurso-para-ingresso-na-carreira-de-procurador-do-estado"
PORTARIA = ('<li><strong>18/11/2026 - </strong><a href="https://static.trf2.jus.br/x/portaria-578.pdf"><strong>'
            'PORTARIA PRES/TRF2 Nº 578</strong></a><strong>, disponibilizado nas Publicações Eletrônicas do dia '
            '18/11/2026 &nbsp;– Institui a Comissão de Heteroidentificação para atuar na verificação dos candidatos '
            'aprovados que se autodeclararam negros no XIX Concurso</strong></li>')
ATO_PGE = ('<hr /><p><a href="https://pge.rj.gov.br/x/edital-alteracao-2011.pdf"><strong><u>edital - Alteração</u>'
           '</strong></a></p>\n<p>Publicado no Diário Oficial de 20 de novembro de 2026</p>')


def trf2(com_portaria=False):
    h = fx("trf2-1811.html")
    return h.replace("<!--PORTARIA_NOVA-->", PORTARIA) if com_portaria else h


def estado_de(*res):
    est = {}
    paginas_oficiais.atualizar_estado(est, list(res), "2026-11-18")
    return est


@teste
def paginas_trf2_item_inteiro_e_mudou():
    r1 = paginas_oficiais.analisar("trf2_juiz", URL_TRF2, 200, trf2(), None, "2026-11-18")
    ok(r1["situacao"] == "NOVA" and r1["novos"][0].startswith("03/11/2026 – Edital TRF2 Nº 117/2026, disponibilizado"),
       "NOVA: o ato mais recente primeiro, não o cabeçalho: %r" % r1["novos"][:2])
    ok(len(r1["novos"]) == 5 and not any("Concursos públicos para magistrados" in x for x in r1["novos"]), r1["novos"])
    ok(any(x.startswith("17/12/2025 – Edital TRF2 Nº 154/2025 - Retificado em 17/12/2025") for x in
           paginas_oficiais.trechos(paginas_oficiais.texto_util(trf2()))), "continuação com hífen junta")
    est = estado_de(r1)
    ok(est["paginas"]["trf2_juiz"]["v"] == paginas_oficiais.VERSAO, est)
    r2 = paginas_oficiais.analisar("trf2_juiz", URL_TRF2, 200, trf2(True), est["paginas"]["trf2_juiz"], "2026-11-20")
    ok(r2["situacao"] == "MUDOU" and len(r2["novos"]) == 1, r2)
    ok(r2["novos"][0].startswith("18/11/2026 - PORTARIA PRES/TRF2 Nº 578, disponibilizado nas Publicações "
                                 "Eletrônicas do dia 18/11/2026"), "nome do ato inteiro: %r" % r2["novos"])
    # comunicados sem palavra-chave, mas com data, sao itens (antes ficavam de fora)
    tr = paginas_oficiais.trechos(paginas_oficiais.texto_util(trf2()))
    ok("22/05/2026 – COMUNICADO 03 – Suspensão Sine Die do Calendário do Certame" in tr, tr)
    # "Atualizado em" muda sem ato novo: IGUAL
    h = trf2().replace("18  Novembro,  2026", "19  Novembro,  2026").replace("2026-11-18T13", "2026-11-19T13")
    r3 = paginas_oficiais.analisar("trf2_juiz", URL_TRF2, 200, h, est["paginas"]["trf2_juiz"], "2026-11-19")
    ok(r3["situacao"] == "IGUAL" and r3["desde"] == "2026-11-18", r3)
    # reordenar ou retirar item nao e MUDOU (IGUAL, com o hash novo gravado)
    h = trf2().replace('<li>08/06/2026', '<li>X08/06/2026').replace(
        '<li>X08/06/2026 – <a href="https://static.trf2.jus.br/x/comunicado-04.pdf">COMUNICADO 04 – Retomada do '
        'Certame</a></li>', '')
    r4 = paginas_oficiais.analisar("trf2_juiz", URL_TRF2, 200, h, est["paginas"]["trf2_juiz"], "2026-11-19")
    ok(r4["situacao"] == "IGUAL" and r4["hash"] != est["paginas"]["trf2_juiz"]["hash"], r4)


@teste
def paginas_pge_titulo_sem_chave_e_repetido():
    r1 = paginas_oficiais.analisar("pge_rj", URL_PGE, 200, fx("pgerj-1811.html"), None, "2026-11-18")
    ok(r1["novos"][0] == "DESIGNAÇÃO DE MEMBRO DA COMISSÃO EXAMINADORA — Publicado no Diário Oficial de 18 de "
                         "novembro de 2026", r1["novos"])
    ok("COMISSÃO ORGANIZADORA - ALTERAÇÃO — Publicado no Diário Oficial de 09 de novembro de 2026" in r1["novos"],
       "ato sem palavra-chave entra pela data")
    ok(not any(x.startswith("03/02/2026") for x in paginas_oficiais.trechos(paginas_oficiais.texto_util(
        fx("pgerj-1811.html")))), "data solta não é item")
    est = estado_de(r1)
    novo = fx("pgerj-1811.html").replace("<!--ATO_NOVO-->", ATO_PGE)
    r2 = paginas_oficiais.analisar("pge_rj", URL_PGE, 200, novo, est["paginas"]["pge_rj"], "2026-11-20")
    ok(r2["situacao"] == "MUDOU" and r2["novos"] == ["edital - Alteração — Publicado no Diário Oficial de 20 de "
                                                     "novembro de 2026"], "título repetido com data nova: %r" % r2)


@teste
def paginas_estado_v1_e_saida():
    v1 = {"url": URL_TRF2, "hash": "abc", "trechos_hash": ["x1", "x2"], "desde": "2026-11-19", "lido_em": "2026-11-20"}
    r = paginas_oficiais.analisar("trf2_juiz", URL_TRF2, 200, trf2(True), v1, "2026-11-23")
    ok(r["situacao"] == "NOVA" and r["releitura"] and r["novos"][0].startswith("18/11/2026 - PORTARIA"), r)
    linhas = paginas_oficiais.linhas_saida([
        r, {"id": "a", "url": "u", "http": 200, "situacao": "IGUAL", "desde": "2026-11-18"},
        {"id": "b", "url": "u2", "http": 200, "situacao": "IGUAL", "desde": "2026-11-02"},
        {"id": "trf3_apoio", "url": "https://www.trf3.jus.br/e.pdf", "http": 0, "situacao": "FORA_DA_REDE",
         "motivo": "sem resposta"}])
    ok(linhas[0] == "PAGINA OFICIAL sem item novo: a desde 18/11; b desde 02/11", linhas)
    ok(linhas[1].startswith("PAGINA OFICIAL trf2_juiz RELIDA (formato novo: confira com o registro)"), linhas[1])
    ok(linhas[-1] == "PAGINA OFICIAL não lida (domínio fora da rede hoje): trf3_apoio (www.trf3.jus.br: sem resposta)",
       linhas[-1])
    est = {}
    ok(paginas_oficiais.atualizar_estado(est, [linhas and {"id": "trf3_apoio", "situacao": "FORA_DA_REDE"}], "d") == 0
       and est["paginas"] == {}, "FORA_DA_REDE não grava estado")
    # verificar: o dominio em `pular` nao e baixado
    salvo = paginas_oficiais.baixar
    pedidos = []
    paginas_oficiais.baixar = lambda url, timeout=20: (pedidos.append(url), (200, trf2()))[1]
    try:
        res = paginas_oficiais.verificar(
            [{"id": "trf2_juiz", "url_oficial": URL_TRF2}, {"id": "trf3_apoio", "url_oficial": "https://www.trf3.jus.br/e.pdf"}],
            {}, "2026-11-23", pular={"www.trf3.jus.br": "sem resposta"})
    finally:
        paginas_oficiais.baixar = salvo
    ok(pedidos == [URL_TRF2] and [x["situacao"] for x in res] == ["NOVA", "FORA_DA_REDE"], (pedidos, res))


# ------------------------------------------------------------------ inicio.py
def ledger_base():
    sec = "https://cj.estrategia.com/portal/x"

    def reg(i, bloco, linha, **k):
        r = {"id": i, "bloco": bloco, "linha": linha, "selo": "PENDÊNCIA DE VERIFICAÇÃO", "verificado_em": "2026-12-01",
             "mudou_em": "2026-11-10", "fonte": sec, "prazos": []}
        r.update(k)
        return r

    def pz(d, ev, conf=False):
        return {"data": d, "evento": ev, "confirmado": conf}
    return {
        "fontes": [{"id": "conjur", "status": "saudavel"}],
        "armadilhas": [{"id": "cloud_egress_bloqueado", "sintoma": "s", "regra": "Leitura direta e sempre curl. 000/403 "
                        "numa fonte: WebSearch. Medido em 17/11/2026 — abrem: conjur.com.br. Recusados: www.in.gov.br."},
                       {"id": "banca_edital_antigo", "sintoma": "edital antigo", "regra": "Conferir o ano."}],
        "pendencias_vivas": [
            {"id": "sec_verificar", "faixa": "ativa", "execucoes": 3, "coletor": "concursos", "desde": "2026-11-20",
             "texto": "PGM Sec/SP: inscrições só em secundária"},
            {"id": "fila_verificar", "faixa": "ativa", "execucoes": 2, "coletor": "concursos", "desde": "2026-11-20",
             "texto": "PGM Fila/SP: retificação só em secundária"},
            {"id": "trt8_edital_verificar", "faixa": "longo_prazo", "execucoes": 20, "coletor": "concursos",
             "desde": "2026-10-01", "texto": "TRT8: convocação só em secundária"},
            {"id": "cebraspe_edital", "faixa": "longo_prazo", "execucoes": 9, "coletor": "concursos",
             "dominio_oficial": "www.cebraspe.org.br", "desde": "2026-10-01", "texto": "TJDFT: sem edital"}],
        "concursos": [
            reg("trf2_juiz", "Magistratura Federal", "TRF2 — Juiz Federal Substituto: XIX concurso", selo="EM ANDAMENTO",
                fonte="https://www.trf2.jus.br/x", dominio_oficial="www.trf2.jus.br", url_oficial=URL_TRF2,
                verificado_em="2026-11-30"),
            reg("trf3_apoio", "Quadro de apoio", "TRF3 — Analista e Técnico Judiciário (Vunesp)",
                url_oficial="https://www.trf3.jus.br/edital.pdf", verificado_em="2026-11-30"),
            reg("trt8_apoio", "Quadro de apoio", "TRT8 — Analista e Técnico Judiciário: FCC",
                pendencia="trt8_edital_verificar", verificado_em="2026-10-01", prazos=[pz("2026-12-08", "convocação")]),
            reg("pgm_sec", "Procurador do Município (PGM)", "PGM Sec/SP — Procurador", pendencia="sec_verificar",
                prazos=[pz("2026-12-14", "fim das inscrições (fonte secundária)")]),
            reg("pgm_fila", "Procurador do Município (PGM)", "PGM Fila/SP — Procurador", pendencia="fila_verificar",
                prazos=[pz("2026-12-09", "fim das inscrições (fonte secundária)")]),
            reg("pgm_meio", "Procurador do Município (PGM)", "PGM Meio/SP — Procurador",
                prazos=[pz("2026-12-05", "fim das inscrições (fonte secundária)")]),
            reg("pgm_d1", "Procurador do Município (PGM)", "PGM Dum/SP — Procurador",
                prazos=[pz("2026-12-01", "fim das inscrições (fonte secundária)")]),
            reg("pgm_d3", "Procurador do Município (PGM)", "PGM Dtres/SP — Procurador",
                prazos=[pz("2026-11-29", "fim das inscrições (fonte secundária)")]),
            reg("tj_conf", "Magistratura Estadual", "TJXX — Juiz Substituto", selo="ENCERRA EM BREVE",
                fonte="https://www.tjxx.jus.br/concurso", prazos=[pz("2026-12-05", "fim das inscrições", True)]),
            reg("alepa_sec", "Procurador do Estado (PGE)", "ALEPA — Procurador",
                prazos=[pz("2026-10-20", "prova (fonte secundária)")]),
            reg("velho_dpe", "Defensor Público Estadual (DPE)", "DPE-ZZ — Defensor: comissão formada",
                selo="EM PLANEJAMENTO", verificado_em="2026-10-01"),
            reg("tjdft_juiz", "Magistratura Estadual", "TJDFT — Juiz: sem edital", selo="EM PLANEJAMENTO",
                pendencia="cebraspe_edital"),
        ],
    }


SONDA_TESTE = {"www.trf2.jus.br": "ok", "www.trf3.jus.br": "sem resposta", "www.cebraspe.org.br": "só JavaScript",
               "www.in.gov.br": "ok"}


def sonda_falsa(ds):
    res = {d: SONDA_TESTE.get(d, "proxy" if d in inicio.REDE_DONO else "ok") for d in ds if d}
    inicio.SONDA.update(res)
    return {d: s == "ok" for d, s in res.items()}


def rodar(agora, estado_data, led=None, migr=None, pag_estado=None, html_trf2=None, banca_extra=None):
    """inicio.main() numa pasta descartavel; migr: modulo falso de migracoes (None = ausente); banca_extra: campos
    a mais no resultado falso do bancas.coletar (ex.: erro da listagem)."""
    d = tempfile.mkdtemp(dir=TMPDIR)
    t = os.path.join(d, "tmp")
    os.makedirs(t)
    shutil.copytree(os.path.join(WORK, "prompts"), os.path.join(d, "prompts"))
    shutil.copy(os.path.join(WORK, "munger-quotes.json"), d)
    json.dump(led or ledger_base(), open(os.path.join(d, "robozinho-aprendizado.json"), "w"), ensure_ascii=False)
    json.dump({"ultima_execucao": {"execution_id": "%s-7h" % estado_data, "date": estado_data, "delivery": "draft",
                                   "email_subject": "S", "draft_id": "r",
                                   "window_end": "%sT07:07:30-03:00" % estado_data}},
              open(os.path.join(d, "robozinho-estado.json"), "w"))
    pedidos = []

    def baixar(url, timeout=20):
        pedidos.append(url)
        ok("trf3" not in url, "domínio sem resposta não é baixado")
        return 200, html_trf2 if html_trf2 is not None else trf2(True)
    salvo = (inicio.AQUI, inicio.alcancaveis, bancas.coletar, bancas.carregar_estado, paginas_oficiais.baixar,
             os.environ.get("ROBOZINHO_TMP"), sys.argv, sys.modules.get("migracoes", "ausente"))
    inicio.AQUI = d
    inicio.alcancaveis = sonda_falsa
    bancas.coletar = lambda hoje, conc, estado=None: dict({"banca": "FGV", "http": 200, "concursos": [],
                                                           "data": hoje.isoformat()}, **(banca_extra or {}))
    bancas.carregar_estado = lambda caminho=None: {"paginas": pag_estado or {}}
    paginas_oficiais.baixar = baixar
    sys.modules["migracoes"] = migr
    os.environ["ROBOZINHO_TMP"] = t
    sys.argv = ["inicio.py", "--agora", agora, "--sem-disparo"]
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            inicio.main()
    finally:
        (inicio.AQUI, inicio.alcancaveis, bancas.coletar, bancas.carregar_estado, paginas_oficiais.baixar,
         os.environ["ROBOZINHO_TMP"], sys.argv, mig) = salvo
        if mig == "ausente":
            sys.modules.pop("migracoes", None)
        else:
            sys.modules["migracoes"] = mig
    cc = open(os.path.join(t, "coletor-concursos.md"), encoding="utf-8").read()
    return buf.getvalue(), cc, d, pedidos


def estado_trf2_1811():
    r = paginas_oficiais.analisar("trf2_juiz", URL_TRF2, 200, trf2(), None, "2026-11-18")
    return estado_de(r)["paginas"]


def stub_migracoes(f):
    m = types.ModuleType("migracoes")
    m.aplicar = f
    return m


@teste
def inicio_migracoes_antes_do_ledger():
    chamadas = []

    def aplicar(hoje, work_dir=None):
        chamadas.append((hoje, work_dir))
        p = os.path.join(work_dir, "robozinho-aprendizado.json")
        led = json.load(open(p, encoding="utf-8"))
        led["concursos"] = [c for c in led["concursos"] if c["id"] != "trt8_apoio"]
        json.dump(led, open(p, "w", encoding="utf-8"), ensure_ascii=False)
        return ["MIGRACAO 2026-12-escopo: 1 registro fora do escopo removido (trt8_apoio)"]
    out, cc, d, _ = rodar("2026-12-02T07:05:00-03:00", "2026-12-01", migr=stub_migracoes(aplicar))
    ok(chamadas == [(D("2026-12-02"), d)], "aplicar(hoje, work_dir=AQUI): %r" % chamadas)
    linhas = out.splitlines()
    ok(linhas[1] == "MIGRACAO 2026-12-escopo: 1 registro fora do escopo removido (trt8_apoio)", linhas[:3])
    ok("FORA DO ESCOPO" not in out, "o ledger lido já é o migrado")

    def quebra(hoje, work_dir=None):
        raise RuntimeError("estado ilegível")
    out, _, _, _ = rodar("2026-12-02T07:05:00-03:00", "2026-12-01", migr=stub_migracoes(quebra))
    ok("ALERTA: migracoes: estado ilegível" in out and "==== LEDGER" in out, "erro: ALERTA e segue")
    out, _, _, _ = rodar("2026-12-02T07:05:00-03:00", "2026-12-01", migr=None)
    ok(re.search(r"^ALERTA: migracoes: .+", out, re.M) and "PASSO 2" in out, "ausente: ALERTA e segue")
    # rev3 P4: RE-EXECUCAO (a edicao de hoje ja esta no estado) nao aplica migracao nem suja o ledger: nada roda
    # depois dela para commitar
    chamadas.clear()
    out, cc, d, _ = rodar("2026-12-02T16:40:00-03:00", "2026-12-02", migr=stub_migracoes(aplicar))
    led = json.load(open(os.path.join(d, "robozinho-aprendizado.json"), encoding="utf-8"))
    ok("RE-EXECUÇÃO: a edição de hoje já está registrada" in out and chamadas == [] and "MIGRACAO" not in out
       and any(c["id"] == "trt8_apoio" for c in led["concursos"]) and cc.startswith("RE-EXECUÇÃO"),
       (chamadas, out[:300]))


@teste
def inicio_escopo_rede_e_paginas():
    out, cc, _, pedidos = rodar("2026-12-02T07:05:00-03:00", "2026-12-01", migr=stub_migracoes(lambda h, work_dir=None: []),
                                pag_estado=estado_trf2_1811())
    # escopo regional: o TRT8 (PA/AP) sai de tudo e a linha pede a remocao com a pendencia ligada
    fora = [l for l in out.splitlines() if l.startswith("FORA DO ESCOPO")]
    ok(len(fora) == 1 and "trt8_apoio" in fora[0] and "trt8_edital_verificar" in fora[0] and "trf3_apoio" not in fora[0],
       fora)
    # rev1 C9: o leitor ve a saida no dia ("Saiu do acompanhamento"): a linha nao diz o contrario
    ok('remova (remover + desfecho "fora do escopo regional"), com as pendências trt8_edital_verificar' in fora[0]
       and "leitor" not in fora[0], fora)
    ok("trt8" not in cc.split("## A.")[1].split("## C.")[0], "sem fila, pendência nem rodízio do TRT8")
    ok("trt8_apoio |" not in cc.split("## Registro atual")[1], "fora do Registro atual")
    ok("- trt8_edital_verificar [" not in out.split("PENDÊNCIAS VIVAS:")[1], "pendência fora só na linha FORA DO ESCOPO")
    ok("TRT8 [trt8_apoio]" in cc, "segue nos acompanhados (não vira NOVO)")
    ok("Quadro de apoio: só órgãos com lotação em SP, RJ, MG, ES, PR, SC ou RS" in cc, "escopo no prompt")
    # rede: proxy x site x SPA, e a liberacao de dominio do dono
    rede = [l for l in out.splitlines() if l.startswith("REDE (")][0]
    ok("fora: www.cebraspe.org.br (só JavaScript), www.trf3.jus.br (sem resposta)" in rede, rede)
    amb = [l for l in out.splitlines() if l.startswith("REDE do ambiente: ")]
    ok(amb and "LIBERADO pelo proxy: www.in.gov.br (ok)" in amb[0] and "noticias.stf.jus.br" in amb[0], amb)
    # fora da rede no prompt (rev1 C8): os dos concursos e os que so o dono libera recusados pelo proxy hoje
    fora_p = re.search(r"\*\*não tente `curl`\*\*: (.*)\.\n", cc).group(1).split(", ")
    ok(fora_p == sorted(fora_p) and {"www.cebraspe.org.br", "www.trf3.jus.br", "www.vunesp.com.br",
                                     "www.concursosfcc.com.br", "apis.cebraspe.org.br", "cdn.cebraspe.org.br"}
       <= set(fora_p) and "www.in.gov.br" not in fora_p and "www.trf2.jus.br" not in fora_p, fora_p)
    # url_oficial lida todo dia: o TRF2 (sem outro motivo de foco) mudou e entrou no foco; o TRF3 nao foi baixado
    ok(pedidos == [URL_TRF2], pedidos)
    ok("PAGINA OFICIAL trf2_juiz MUDOU" in out and "· 18/11/2026 - PORTARIA PRES/TRF2 Nº 578, disponibilizado" in out,
       out.split("BANCA FGV")[1][:600])
    ok("PAGINA OFICIAL não lida (domínio fora da rede hoje): trf3_apoio (www.trf3.jus.br: sem resposta)" in out, "trf3")
    ok(re.search(r"^  - trf2_juiz \| .*foco: página oficial mudou", out, re.M), "MUDOU no foco")
    # a medicao fixa de rede sai da regra impressa da armadilha
    arm = out.split("ARMADILHAS (checklist")[1].split("PENDÊNCIAS VIVAS:")[0]
    ok("Medido em" not in arm and "Situação da rede hoje: linhas REDE acima" in arm, arm)
    # candidato a remocao so com datas de secundaria
    ok("ALERTA: candidato a remoção (alepa_sec, prazos só em secundária) — todos os prazos (só de fonte secundária) "
       "venceram há mais de 30 dias" in out, [l for l in out.splitlines() if "remoção" in l])
    # no dia seguinte, a pagina igual: uma linha so
    est = estado_trf2_1811()
    est["trf2_juiz"] = paginas_oficiais.analisar("trf2_juiz", URL_TRF2, 200, trf2(True), est["trf2_juiz"], "2026-12-02")
    est = estado_de(est["trf2_juiz"])["paginas"]
    out, _, _, _ = rodar("2026-12-03T07:05:00-03:00", "2026-12-02", migr=stub_migracoes(lambda h, work_dir=None: []),
                         pag_estado=est)
    ok("PAGINA OFICIAL sem item novo: trf2_juiz desde 02/12" in out and "foco: página oficial" not in out, "IGUAL")


@teste
def inicio_prazo_secundario_e_pendencias():
    out, cc, _, _ = rodar("2026-12-02T07:05:00-03:00", "2026-12-01", migr=stub_migracoes(lambda h, work_dir=None: []))
    a = cc.split("## A.")[1].split("Pendências vivas")[0]
    ok("09/12 (em 7 dias) PGM Fila/SP" in a, "D-7: entrada")
    ok("pgm_meio" not in a, "D-3 de prazo só secundário: sem busca hoje")
    ok("- confirmar desfecho: 01/12 (ontem) PGM Dum/SP" in a, "D+1: desfecho")
    ok("pgm_d3" not in a, "D+3: já buscado")
    ok("05/12 (em 3 dias) TJXX" in a, "prazo confirmado: todo dia")
    ok("PRAZO VENCIDO (só secundária; desfecho já buscado pelo coletor, sem busca hoje): 29/11 (há 3 dias) PGM Dtres/SP"
       in out and "ALERTA: prazo vencido 29/11" not in out, [l for l in out.splitlines() if "29/11" in l])
    pend = cc.split("Pendências vivas")[1].split("## B.")[0]
    ok("[ativa | COBERTA PELO PRAZO de pgm_fila (acima)] fila_verificar" in pend, pend)
    ok("[ativa | SÓ VIGIAR MOVIMENTO NOVO — só secundária, oficial fora da rede] sec_verificar" in pend, pend)
    ok("[longo_prazo | SÓ VIGIAR MOVIMENTO NOVO] cebraspe_edital" in pend, pend)
    ok("velho_dpe" in cc.split("## B.")[1].split("## C.")[0], "rodízio")
    # o D-3 nao ganha busca mas continua fora do rodizio (tem prazo perto)
    ok("pgm_meio" not in cc.split("## B.")[1].split("## C.")[0], "prazo perto não vai ao rodízio")
    # descoberta de quarta (MP/Defensorias) em dezembro: previsao com o ano seguinte; NOVO desde 01/01
    ok("`concurso MPU OR MPF procurador da república 2027 edital previsto`" in cc and
       "`concurso promotor de justiça edital 2026 inscrições OR comissão OR banca`" in cc, "{prox} de outubro em diante")
    ok("fato duro datado a partir de 01/01/2026" in cc, "DATA_MIN_NOVO")
    # segunda (1a da semana): a SPA do Cebraspe nao manda "ler por curl"
    out, cc, _, _ = rodar("2026-11-30T07:05:00-03:00", "2026-11-27", migr=stub_migracoes(lambda h, work_dir=None: []))
    ok("[longo_prazo | REVERIFICAR] cebraspe_edital" in cc and "www.cebraspe.org.br acessível" not in cc, "SPA")
    ok("[ativa | REVERIFICAR] sec_verificar" in cc, "1ª da semana: as ativas reverificam")


@teste
def inicio_descoberta_regional_e_virada_do_ano():
    out, cc, _, _ = rodar("2026-12-04T07:05:00-03:00", "2026-12-03", migr=stub_migracoes(lambda h, work_dir=None: []))
    c = cc.split("## C.")[1].split("Já acompanhados")[0]
    ok("SP MG RJ ES PR SC RS inscrições abertas dezembro 2026" in c and "SP MG RJ ES PR SC RS edital dezembro 2026" in c
       and "sul sudeste edital previsto 2027" in c and "analista judiciário técnico judiciário edital 2026" not in c, c)
    out, cc, _, _ = rodar("2027-01-15T07:05:00-03:00", "2027-01-14", migr=stub_migracoes(lambda h, work_dir=None: []))
    ok("fato duro datado a partir de 16/11/2026" in cc, "janeiro aceita fato de dezembro")
    ok("sul sudeste edital previsto 2027 banca definida" in cc and "inscrições abertas janeiro 2027" in cc,
       "janeiro (sexta): {prox} = o próprio ano")
    out, cc, _, _ = rodar("2026-03-12T07:05:00-03:00", "2026-03-11", migr=stub_migracoes(lambda h, work_dir=None: []))
    ok("`concurso AGU procurador da fazenda nacional 2026 banca edital`" in cc, "março: {prox} = ano")


@teste
def sonda_classifica():
    c = inicio.classificar
    ok(c("403", "000", "www.in.gov.br") == "proxy" and c("407", "000") == "proxy", "proxy")
    ok(c("200", "000", "www.trf3.jus.br") == "sem resposta" and c("000", "000") == "sem resposta", "site")
    ok(c("200", "403", "www.stf.jus.br") == "http 403", "o site recusa")
    ok(c("200", "200", "www.cebraspe.org.br") == "só JavaScript" and c("200", "301", "x.jus.br") == "ok", "SPA x ok")
    ok(set(inicio.REDE_DONO) >= {"www.in.gov.br", "noticias.stf.jus.br", "www.vunesp.com.br", "www.concursosfcc.com.br",
                                 "normas.leg.br", "www12.senado.leg.br", "apis.cebraspe.org.br", "cdn.cebraspe.org.br"},
       inicio.REDE_DONO)


@teste
def inicio_listagem_da_fgv_no_prompt():
    """rev1 C3: com a listagem da FGV lida, o coletor deixa a FGV fora da descoberta; sem ela (erro), nao."""
    _, cc, _, _ = rodar("2026-12-02T07:05:00-03:00", "2026-12-01", migr=stub_migracoes(lambda h, work_dir=None: []))
    ok("A listagem da FGV já foi varrida: na descoberta (C), prefira concursos de outras bancas" in cc, "lida")
    out, cc, _, _ = rodar("2026-12-02T07:05:00-03:00", "2026-12-01", migr=stub_migracoes(lambda h, work_dir=None: []),
                          banca_extra={"http": 0, "erro": "listagem ilegível: http 200 sem o bloco de concursos em "
                                                          "andamento"})
    ok("A listagem da FGV não foi lida hoje (listagem ilegível: http 200 sem o bloco de concursos em andamento): na "
       "descoberta (C), a FGV conta como as outras bancas." in cc and "já foi varrida" not in cc, cc[:200])
    ok("BANCA FGV: não lida (listagem ilegível: http 200 sem o bloco" in out, "motivo honesto no inicio")


@teste
def rede_do_ambiente_sem_resposta_nao_libera():
    """rev1 C2: "sem resposta" nao prova que o proxy liberou — fica a parte, como indeterminado, sem ordem de gravar."""
    salvo = dict(inicio.SONDA)
    try:
        inicio.SONDA.clear()
        inicio.SONDA.update({d: "sem resposta" for d in inicio.REDE_DONO})
        l = inicio.linha_rede_dono({})
        ok("LIBERADO" not in l and "atualize em ledger_updates" not in l and l.startswith("indeterminado hoje")
           and all(d in l for d in inicio.REDE_DONO), l)
        inicio.SONDA.update({d: "proxy" for d in inicio.REDE_DONO})
        inicio.SONDA.update({"www.in.gov.br": "ok", "www.vunesp.com.br": "sem resposta", "normas.leg.br": "http 403"})
        l = inicio.linha_rede_dono({"www.in.gov.br": True})
        lib, _, resto = l.partition("; indeterminado hoje")
        ok("LIBERADO pelo proxy: www.in.gov.br (ok), normas.leg.br (http 403)" in lib and "vunesp" not in lib.split(
            "o proxy ainda recusa")[0] and "www.vunesp.com.br" in resto and "nada a gravar no ledger" in resto, l)
        inicio.SONDA.update({"www.in.gov.br": "proxy", "normas.leg.br": "proxy"})
        l = inicio.linha_rede_dono({})
        ok(l.startswith("o proxy recusa 7 dos 8 domínios que só o dono libera") and "LIBERADO" not in l, l)
        inicio.SONDA.update({"www.vunesp.com.br": "proxy"})
        ok(inicio.linha_rede_dono({}) == "o proxy recusa os 8 domínios que só o dono libera", "todos recusados")
    finally:
        inicio.SONDA.clear()
        inicio.SONDA.update(salvo)


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
