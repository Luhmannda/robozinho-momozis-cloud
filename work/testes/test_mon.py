#!/usr/bin/env python3
# =====================================================================
# test_mon.py — testes do grupo MON (work/montar_email.py), sem pytest e sem rede:
#   K2 (execucao.json intacto, resolvido em $ROBOZINHO_TMP, 2a montagem reflete
#   "destaques"); saida (sem corpo, ordem, BYTES/SHA256/CAMINHO, < 3 KB, HTML
#   velho apagado, email-com-avisos.html, sentinela); linhas de apoio; "sem
#   link"; ponto depois de aspa; metadado do Planalto; tamanho nunca ERRO; selo
#   por data; concursos compactos e dormentes; quadro "a confirmar"; informativos
#   completos (resumo STF, estagio RG, tipo STJ, "Em atraso"); STJ Noticias de
#   midia; atos de rotina; impacto; DESCARTADA; Midia ligada a informativo;
#   leitor sem ruido tecnico; Munger; edicao extra; feriado; grupo da resenha.
#   2a rodada: montador e helper sobre a MESMA entrada (selo copiado x decidido, carimbo
#   com o update de hoje, DIVERGE; inclui a entrada do test_est.selo_copiado_nao_e_decisao),
#   "contradiz o selo por data"/"prorrogação não confirmada" acionaveis e sem corte, temas
#   da RG no resolvido, ordem da RG por estagio, apoio sem edicao vazia, email.suporte
#   ignorado, limitacoes tecnicas, meta preservado, feriado sem parenteses aninhados.
#   Volta 2: prazos[n].tipo 'outro'/'prova' num prazo cujo evento e de inscricao vira AVISO ACIONÁVEL
#   (com o selo que a data daria), sem duplicar o do helper com o mesmo prefixo.
#   CORE volta 1: selo por data suspenso com divergencia pendente (TJSC 25/11 x edital 26/11, tambem com so a
#   linha corrigida) igual no e-mail e no ledger; prazo escrito hoje contra o edital lido hoje (AVISO ACIONÁVEL,
#   ALERTA no helper, sem falso positivo); resumo_truncado do ConJur termina em "…" ou some (< 40 caracteres).
# Replay real: execucao do orquestrador de 16/11/2026 (1a rodada) e uma
# simulacao de 17/11 (terca: compactacao e errata do TJAP).
# USO: python3 work/testes/test_mon.py   (imprime OK/FALHOU; sai != 0 em falha)
# Tudo roda em pastas temporarias (ROBOZINHO_TMP proprio).
# =====================================================================

import copy
import hashlib
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
FIX = os.path.join(AQUI, "fixtures", "mon")
FIX_INF = os.path.join(AQUI, "fixtures", "informativos")
BASE_TMP = tempfile.mkdtemp(prefix="robozinho-mon-")
os.environ["ROBOZINHO_TMP"] = os.path.join(BASE_TMP, "padrao")
os.makedirs(os.environ["ROBOZINHO_TMP"])
sys.path.insert(0, WORK)

import montar_email as M  # noqa: E402

TESTES, FALHAS = [], []
N_OK = [0]


def teste(f):
    TESTES.append(f)
    return f


def ok(cond, msg):
    if cond:
        N_OK[0] += 1
    else:
        FALHAS.append(msg)
        print("  FALHOU: " + msg)


def fx(nome):
    with open(os.path.join(FIX, nome), encoding="utf-8") as f:
        return json.load(f)


CENARIOS = {
    "1611": {"janela": "janela-1611.json", "execucao": "execucao-1611.json", "coleta_web": "coleta_web-1611.json",
             "informativos": "informativos-1611.json", "versiculo": "versiculo-1611.json",
             "ledger": "ledger-1311.json"},
    "1711": {"janela": "janela-1711.json", "execucao": "execucao-1711.json", "coleta_web": "coleta_web-1711.json",
             "informativos": "informativos-1711.json", "versiculo": "versiculo-1711.json",
             "bancas": "bancas-1711.json", "fontes_status": "fontes_status-1711.json",
             "ledger": "ledger-1611.json"},
}
N_PASTA = [0]


def preparar_pasta(cen, execucao=None, janela=None):
    N_PASTA[0] += 1
    t = os.path.join(BASE_TMP, "c%d-%s" % (N_PASTA[0], cen))
    os.makedirs(t)
    c = CENARIOS[cen]
    for papel, nome in c.items():
        if papel == "ledger":
            continue
        shutil.copy(os.path.join(FIX, nome), os.path.join(t, papel + ".json"))
    if execucao is not None:
        with open(os.path.join(t, "execucao.json"), "w", encoding="utf-8") as f:
            json.dump(execucao, f, ensure_ascii=False)
    if janela is not None:
        with open(os.path.join(t, "janela.json"), "w", encoding="utf-8") as f:
            json.dump(janela, f, ensure_ascii=False)
    return t


def rodar(cen, t, *extra):
    env = dict(os.environ, ROBOZINHO_TMP=t)
    r = subprocess.run([sys.executable, os.path.join(WORK, "montar_email.py"),
                        "--ledger", os.path.join(FIX, CENARIOS[cen]["ledger"]),
                        "--historico", os.path.join(FIX, "historico.json")] + list(extra),
                       capture_output=True, text=True, env=env, cwd=WORK)
    return r.returncode, r.stdout, r.stderr


def linha(saida, prefixo):
    return next((l for l in saida.splitlines() if l.startswith(prefixo)), "")


def corpo(saida):
    p = linha(saida, "CAMINHO: ")[len("CAMINHO: "):]
    with open(p, encoding="utf-8") as f:
        return f.read()


# 21/11/2026 (montador): reescritas de estilo com a MESMA renderizacao (capturas de tela da edicao de 20/11 antes e
# depois, Chromium, deviceScaleFactor 1, larguras 360, 700 e 1024, com e sem doctype: 0 pixel diferente). #ffffff -> #fff e 0px -> 0 dentro de
# style; a frase do Planalto sem a margem negativa (-4px), com o titulo da secao em margin-bottom 6px (10 - 4, as
# margens colapsavam) — o cliente que recusa margem negativa descartava a declaracao inteira.
PLANALTO_TITULO_6PX = ('border-left:4px solid #c5a253;padding-left:10px;font-size:16px;line-height:22px;'
                       'font-weight:bold;color:#0b2545;margin-bottom:6px">🏛️ Planalto')


def estilo_equivalente(e):
    e = e.replace("#ffffff", "#fff")
    e = re.sub(r"margin:0px\b", "margin:0", e)
    return e.replace("font-style:italic;margin:-4px 0 12px 14px", "font-style:italic;margin:0 0 12px 14px")


# ------------------------------------------------------------------ funcoes puras
@teste
def t_ponto_e_nota():
    ok(M.ponto('STF reconhece repercussão geral do "milagre da contribuição única"')
       == 'STF reconhece repercussão geral do "milagre da contribuição única".', "ponto depois de aspa reta")
    ok(M.ponto("Tese: “É constitucional.”") == "Tese: “É constitucional.”", "aspa precedida de ponto fica")
    ok(M.ponto("“Quem?”") == "“Quem?”" and M.ponto("abc") == "abc." and M.ponto("abc.") == "abc.", "ponto simples")
    ok(M.ponto("x <i>y</i>") == "x <i>y</i>", "tag final nao ganha ponto")
    ok(M.limpar_nota("clipping sem link; sem confirmação oficial localizada nesta execução")
       == "sem confirmação oficial localizada nesta execução", "clipping sem link sai da nota")
    ok(M.limpar_nota("sem link") == "" and M.limpar_nota("sem link próprio") == "", "sem link sai da nota")
    ok(M.limpar_nota("só o título veio no push") == "só o título veio no push", "nota comum fica")
    it = {"status": "RUMOR", "titulo": "T", "fonte": "JOTA", "data": "2026-11-13", "url": "", "nota": ""}
    ok(M.item_padrao(it).count("sem link") == 1, "item sem URL: 'sem link' uma vez")
    it["nota"] = "link não localizado; sem link do push"
    ok(M.item_padrao(it).count("sem link") == 1, "nota que ja fala em sem link nao ganha o rotulo de novo")


@teste
def t_meta_resenha_rotina_impacto():
    ok(M.norm_meta("12/11, DOU 12/11 (edição extra)") == "DOU 12/11 · edição extra", "meta antigo")
    ok(M.norm_meta("ato 12/11/2026; DOU 13/11/2026 (edição extra)") == "DOU 13/11 · edição extra", "meta do coletor")
    ok(M.norm_meta("DOU 13/11") == "DOU 13/11" and M.norm_meta("Plenário") == "Plenário", "meta novo/Plenario")
    ok(M.norm_meta("DOU 12/11; com veto — art. 3º") == "DOU 12/11; com veto — art. 3º", "veto preservado")
    ok("(" not in M.norm_meta("12/11, DOU 12/11 (edição extra)"), "sem parenteses aninhados")
    g = M.grupo_resenha('"Resenha Diária PUSH Legislação - 13/11/2026" (edição extra) | recebida 14/11 01h43')
    ok(g == "Resenha Diária PUSH Legislação de 13/11 — edição extra (recebida em 14/11, 01h43)", "grupo: %s" % g)
    g = M.grupo_resenha("Resenha Diária PUSH Legislação - 13/11/2026 | recebida 13/11 11:55")
    ok(g == "Resenha Diária PUSH Legislação de 13/11 (recebida em 13/11, 11h55)", "grupo sem extra: %s" % g)
    ok(M.grupo_resenha("e-mail qualquer") == "", "resenha irreconhecivel")
    ementas = {  # 16/11: os 5 atos de rotina e o 13.166 (nao rotina)
        "Abre ao Orçamento da Seguridade Social da União ... crédito suplementar no valor de R$ 1,00": True,
        "Altera o Decreto nº 11.178 ... e remaneja e transforma cargos em comissão e funções de confiança.": True,
        "Autoriza o aumento de capital social da Telecomunicações Brasileiras S.A.": True,
        "Promulga o Acordo entre o Governo da República Federativa do Brasil e o Governo da República de Cuba em "
        "Matéria de Turismo, firmado em Havana": True,
        "Promulga o Acordo sobre Serviços Aéreos entre o Governo da República Federativa do Brasil e a Côte d'Ivoire": True,
        "Promulga o Acordo-Quadro para a Disposição de Bens Apreendidos do Crime Organizado Transnacional": False,
        "Promulga o Acordo de Cooperação Jurídica em Matéria Penal entre o Brasil e a Suíça": False,
        "Promulga o Tratado de Extradição entre o Brasil e o Japão": False,
        "Promulga o Acordo sobre Transferência de Pessoas Condenadas e de Serviços Aéreos": False,
    }
    for em, esperado in ementas.items():
        ok(M.eh_rotina({"titulo": "Decreto nº 1", "resumo": em}) is esperado, "rotina=%s: %s" % (esperado, em[:50]))
    imp = M.impacto_auto("Altera o Decreto-Lei nº 2.848, de 7 de dezembro de 1940 (Código Penal), e a Lei nº 7.210, "
                         "de 11 de julho de 1984 (Lei de Execução Penal), para tratar da progressão de regime.")
    ok(imp == "Altera: Código Penal; Lei de Execução Penal", "impacto: %s" % imp)
    ok(M.impacto_auto("Institui o Dia Nacional do Livro.") == "", "sem impacto em ementa que nao altera diploma")
    ok(M.impacto_auto("Revoga a Lei nº 9.099, de 26 de setembro de 1995") == "Revoga: Lei dos Juizados Especiais",
       "impacto revoga")
    ok(len(M.impacto_auto("Altera " + " e ".join(["o Código Penal", "o Código Civil", "a CLT", "o Código de Processo "
       "Civil", "o Código de Processo Penal", "o Código Eleitoral", "o Código Tributário Nacional",
       "o Código de Trânsito", "a Lei nº 8.112", "a Lei nº 9.784"]))) <= 160, "impacto ate 160 caracteres")


@teste
def t_destaques_informativos():
    sys.path.insert(0, WORK)
    import informativos as I
    with open(os.path.join(FIX_INF, "stj909.html"), "rb") as f:
        _, stj, _ = I.stj_html(f.read().decode("cp1252"), 909)
    txt = [M.texto_destaque("stj", d) for d in stj]
    ok(txt[0].startswith("<b>RQF · Tema 1403</b> · Direito Processual Penal — "), "STJ RQF: %s" % txt[0][:60])
    ok(txt[1].startswith("<b>Repetitivo · Tema 1270</b> · Execução Penal — "), "STJ repetitivo: %s" % txt[1][:60])
    ok(txt[2].startswith("<b>Corte Especial</b> · "), "STJ Corte Especial")
    ok(txt[3].startswith("<b>Direito Tributário</b> — "), "STJ turma sem prefixo")
    inf = {r["id"]: r for r in fx("informativos-1611.json")}
    rg = inf["rg397"]["itens"]
    hoje = date(2026, 11, 16)
    ok(M.rotulo_rg(rg[5], hoje) == "Repercussão geral em votação (PV, até 13/11; resultado no próximo boletim)",
       "rotulo votacao: %s" % M.rotulo_rg(rg[5], hoje))
    ok(M.rotulo_rg(rg[5], date(2026, 11, 12)) == "Repercussão geral em votação (PV, até 13/11)", "votacao em curso")
    ok(M.rotulo_rg(rg[7], date(2026, 11, 10)) == "Pauta do Plenário 11/11", "rotulo pauta")
    ok(M.rotulo_rg(rg[0]) == "Tese publicada" and M.rotulo_rg(rg[2]) == "Trânsito em julgado", "rotulo tese/transito")
    ok(M.rotulo_rg(rg[9], date(2026, 11, 10)) == "Sessão virtual de 06/11 a 13/11", "rotulo sessao virtual")
    ok(M.rotulo_rg({"estagio": ""}) == "", "estagio vazio: sem rotulo")
    html = M.destaques_html("rg", rg, hoje)
    ok(len(html) == 10, "RG: 11 temas em 10 linhas (2 sem RG numa so): %d" % len(html))
    ok(html[-1].startswith("<i>Sem repercussão geral:</i> <b>Tema 1.487</b>") and "Tema 1.478" in html[-1],
       "linha unica dos sem RG")
    ok(all("Tese:" in h for h in html[:3]) and "Tema 1.338" in " ".join(html), "temas com tese primeiro; 1.338 presente")
    stf = M.texto_destaque("stf", inf["stf1236"]["itens"][3])
    ok("<i>Resumo:</i> O Imposto sobre Serviços" in stf, "STF com o resumo oficial")
    erros, avisos = [], []
    ok(M.selecionar(None, 5, "x", erros, avisos) == [0, 1, 2, 3, 4], "padrao: todos")
    ok(M.selecionar([3, 1], 5, "x", erros, avisos) == [3, 1, 0, 2, 4] and avisos, "lista antiga: so ordena (+ aviso)")
    ok(M.selecionar({"excluir": [1]}, 4, "x", erros, avisos) == [0, 2, 3], "exclusao explicita")
    ok(M.selecionar({"ordem": [2], "excluir": [0]}, 3, "x", erros, avisos) == [2, 1], "ordem + exclusao")
    M.selecionar([9], 3, "rgX", erros, avisos)
    ok(any("fora de 0..2" in e for e in erros), "indice fora do intervalo e ERRO")


@teste
def t_textos_leitor():
    ok(M.ja_em_limitacoes("Medidas provisórias: fonte do Congresso indisponível hoje; nenhuma MPV publicada nesta "
                          "edição.", "A página de medidas provisórias do Congresso não respondeu nesta execução; a "
                          "busca de apoio não localizou MPV nova com data oficial."), "MPV repetida das limitacoes")
    ok(not M.ja_em_limitacoes("Boletim da Câmara de 14/11 trouxe só aprovações em comissão.",
                              "A página de medidas provisórias do Congresso não respondeu."), "observacao diferente fica")
    sup = M.suporte_txt({"congresso_mpvs": "falha", "youversion": "nao_tentada", "conjur": "ok"}, {})
    ok("Congresso Nacional (medidas provisórias)" in sup and "YouVersion" not in sup, "suporte: falha em linguagem simples")
    ok(not re.search(r"http\s*\d|\.py\b|coleta_web", sup), "suporte sem codigo http nem script")
    sup = M.suporte_txt({}, {"suporte": "Falhas: congresso_mpvs: coleta_web.py http 0; youversion: http 403 (anti-bot)"})
    ok(not re.search(r"http\s*\d|\.py\b|anti-bot|congresso_mpvs|coleta_web", sup),
       "suporte escrito a mao perde o ruido tecnico: %s" % sup)
    lic = M.sec_munger({"texto": "Quantifique antes de acreditar", "fonte": "Aforismos", "tipo": "licao", "obs": ""})
    afo = M.sec_munger({"texto": "Inverta, sempre inverta", "fonte": "Discurso", "tipo": "aforismo"})
    ok("“" not in lic and "— lição inspirada em Charlie Munger · <i>Aforismos</i>" in lic and
       "Quantifique antes de acreditar." in lic, "Munger licao sem aspas e assinada")
    ok("“Inverta, sempre inverta”" in afo and "— Charlie Munger · <i>Discurso</i>" in afo, "Munger aforismo com aspas")
    ok(lic.count("#f4f6fa") == afo.count("#f4f6fa") == 1, "mesma caixa")
    j = fx("janela-1711.json")
    j.update(data="2026-11-20", inicio="2026-11-19T07:05:00-03:00", fim="2026-11-20T07:05:00-03:00",
             feriado_hoje={"data": "2026-11-20", "tipo": "nacional",
                           "nome": "Dia Nacional de Zumbi e da Consciência Negra"})
    t = M.janela_txt(j, "")
    ok(t.endswith("Hoje é feriado nacional (Dia Nacional de Zumbi e da Consciência Negra)."), "feriado hoje: %s" % t)
    j.update(data="2026-11-23", inicio="2026-11-20T07:05:00-03:00", fim="2026-11-23T07:05:00-03:00", feriado_hoje=None,
             feriados_na_janela=[{"data": "2026-11-20", "tipo": "nacional", "nome": "Consciência Negra"}])
    t = M.janela_txt(j, "")
    ok("cobrindo o fim de semana e o feriado de 20/11 (Consciência Negra)" in t, "feriado na janela: %s" % t)


@teste
def t_apoio_calculado():
    infs = [{"ref": "rg397", "titulo": "Repercussão Geral em Pauta nº 397", "herdada": True},
            {"ref": "stf1236", "titulo": "Informativo STF nº 1236", "herdada": True}]
    t = M.apoio_calculado("STF Jurisprudência", {"Informativos": infs})
    ok(t.startswith("Sem Repercussão Geral em Pauta nova na janela") and "Repercussão Geral em Pauta nº 397" in t,
       "STF Jurisprudencia aponta Informativos: %s" % t)
    t = M.apoio_calculado("STF Jurisprudência", {"Informativos": [dict(infs[0], herdada=False)]})
    ok(t.startswith("Teses e julgados do STF") and "Sem Repercussão" not in t, "RG nova nao vira 'sem RG nova'")
    ok(M.apoio_calculado("STF Jurisprudência", {}) is None, "sem informativo: linha padrao")
    stj = [{"ref": "stj909", "titulo": "Informativo STJ nº 909"}]
    ok("Informativo STJ nº 909" in M.apoio_calculado("STJ Jurisprudência", {"Informativos": stj}), "STJ Jurisprudencia")
    ok(M.apoio_calculado("STJ Jurisprudência", {}) == "Sem teses do CodJu nem Informativo STJ novo na janela.",
       "STJ Jurisprudencia sem informativo nao manda ver Informativos")
    ok(M.apoio_calculado("STJ Notícias", {"Mídia": [{"titulo": "STJ limita x"}]}) is None, "STJ na midia: linha padrao")
    ok(M.apoio_calculado("STJ Notícias", {}) == "Nenhuma notícia do STJ localizada nesta janela.", "STJ sem nada")


@teste
def t_selo_compacto_radar():
    led = fx("ledger-1611.json")
    j = fx("janela-1711.json")
    j.update(data="2026-11-18", execution_id="2026-11-18-7h", execucao_anterior="2026-11-17-7h")
    avisos = []
    ctx = M.estado_concursos({"ledger_updates": {}}, j, led, {"historico": os.path.join(FIX, "historico.json"),
                                                              "bancas": "/inexistente"}, avisos)
    por = {c["id"]: c for c in ctx["regs"]}
    ok(por["tjpb_apoio"]["selo"] == "ENCERRA HOJE" and por["tjap_juiz"]["selo"] == "ENCERRA HOJE",
       "selo por data em 18/11: ENCERRA HOJE")
    ok(any(a.startswith("selo por data: tjpb_apoio ENCERRA EM BREVE → ENCERRA HOJE") for a in avisos),
       "AVISO do selo derivado")
    ok("tjpb_apoio" not in ctx["alterados"] and "tjpb_apoio" in ctx["selo_mudou"], "mudanca mecanica nao e 'Atualizado hoje'")
    html = M.linha_concurso(por["tjpb_apoio"], date(2026, 11, 18), ctx["novos"], ctx["alterados"], 0)
    ok("Atualizado hoje" not in html and "ENCERRA HOJE" in html, "linha com o selo novo, sem 'Atualizado hoje'")
    # selo no update IGUAL ao do registro e copia, nao decisao (selos.selo_escrito, a regra do helper): vale o
    # selo por data. Antes (P3) o montador mantinha a copia e o ledger gravava o selo por data, sem aviso.
    avisos = []
    upd = {"concursos": {"tjpb_apoio": {"selo": "ENCERRA EM BREVE"}}}
    ctx2 = M.estado_concursos({"ledger_updates": upd}, j, led, {"historico": os.path.join(FIX, "historico.json")}, avisos)
    ok(next(c for c in ctx2["regs"] if c["id"] == "tjpb_apoio")["selo"] == "ENCERRA HOJE",
       "copia do selo do registro: vale o selo por data (ENCERRA HOJE)")
    ok(any(a.startswith("selo por data: tjpb_apoio ENCERRA EM BREVE → ENCERRA HOJE") for a in avisos),
       "copia do selo: AVISO do selo derivado")
    # selo DIFERENTE do registro e decisao: nunca sobrescrito (o --validar avisa se contradiz a data)
    avisos = []
    upd = {"concursos": {"tjpb_apoio": {"selo": "INSCRIÇÕES ENCERRADAS"}}}
    ctx2 = M.estado_concursos({"ledger_updates": upd}, j, led, {"historico": os.path.join(FIX, "historico.json")}, avisos)
    ok(next(c for c in ctx2["regs"] if c["id"] == "tjpb_apoio")["selo"] == "INSCRIÇÕES ENCERRADAS"
       and not any("tjpb_apoio" in a for a in avisos), "selo escrito hoje (decisao) nunca e sobrescrito")
    # compactacao: terca compacta o que nao mudou desde antes da edicao anterior; segunda so os dormentes
    hoje = date(2026, 11, 17)
    regs = [{"id": "a", "selo": "EM PLANEJAMENTO", "mudou_em": "2026-11-09", "prazos": []},
            {"id": "b", "selo": "EM PLANEJAMENTO", "mudou_em": "2026-11-16", "prazos": []},
            {"id": "c", "selo": "PENDÊNCIA DE VERIFICAÇÃO", "mudou_em": "2026-10-01", "prazos": []},
            {"id": "d", "selo": "EM PLANEJAMENTO", "mudou_em": "2026-11-02",
             "prazos": [{"data": "2026-11-30", "evento": "prova", "confirmado": False}]},
            {"id": "e", "selo": "INSCRIÇÕES ABERTAS", "mudou_em": "2026-10-01", "prazos": []},
            {"id": "f", "selo": "EM ANDAMENTO", "mudou_em": "2026-10-01", "prazos": []}]
    ter = M.criterio_compacto({"primeira_semana": False, "execucao_anterior": "2026-11-16-7h"}, hoje, set(), set(), set())
    seg = M.criterio_compacto({"primeira_semana": True, "execucao_anterior": "2026-11-13-7h"}, hoje, set(), set(), set())
    ok([ter(c) for c in regs] == ["sem_mudanca", None, "dormente", None, None, "sem_mudanca"],
       "terca: %s" % [ter(c) for c in regs])
    ok([seg(c) for c in regs] == [None, None, "dormente", None, None, None], "segunda: %s" % [seg(c) for c in regs])
    ok(M.criterio_compacto({"execucao_anterior": "2026-11-16-7h"}, hoje, {"a"}, set(), set())(regs[0]) is None,
       "novo nunca compacta")
    html = "\n".join(M.bloco_concursos("PFN", regs[:2], hoje, set(), set(), True, ter))
    ok(html.count("<tr") == 3 and "Sem mudança recente" in html and "— EM PLANEJAMENTO (desde 09/11)" in html,
       "uma linha compacta por bloco")
    # quadro "a confirmar": so inscricao/prova em ate 14 dias e sem divergencia
    regs = [{"id": "x", "linha": "X — Cargo", "prazos": [{"data": "2026-11-25", "evento": "fim das inscrições",
                                                          "confirmado": False}]},
            {"id": "y", "linha": "Y — Cargo", "prazos": [{"data": "2026-12-10", "evento": "prova", "confirmado": False}]},
            {"id": "z", "linha": "Z — Cargo", "pendencia": "z_div",
             "prazos": [{"data": "2026-11-20", "evento": "prova", "confirmado": False}]},
            {"id": "w", "linha": "W — Cargo", "prazos": [{"data": "2026-11-21", "evento": "convocação",
                                                          "confirmado": False}]}]
    div = M.com_divergencia(regs, [{"id": "z_div", "texto": "fontes divergem sobre a data"}], {})
    r = M.radar(regs, hoje, div)
    ok("X — fim" in r and "Y —" not in r and "Z —" not in r and "W —" not in r, "a confirmar filtrado")


@teste
def t_descarte_e_relacionados():
    hist = [{"execution_id": "2026-11-13-7h", "date": "2026-11-13", "items": [
        {"chave": "jota|noticia|gilmar-mendes-interrompe-julgamento-com-maioria-formada|2026|2026-11-12",
         "titulo": "Gilmar Mendes interrompe julgamento com maioria formada", "categoria": "Mídia"},
        {"chave": "push-stf|noticia|stf-rejeita-recursos-contra-decisao-que-homologou-acordo|2026|2026-11-12",
         "titulo": "STF rejeita recursos contra decisão que homologou acordo dos planos econômicos",
         "categoria": "STF Notícias"},
        {"chave": "conjur|opiniao|um-artigo|2026|2026-11-12", "titulo": "Um artigo", "categoria": "Opinião/Análise"}]}]
    itens = [{"categoria": "Mídia", "titulo": "Gilmar Mendes interrompe julgamento com maioria formada para derrubar lei",
              "chave": "jota|noticia|gilmar-mendes-interrompe-julgamento-com-maioria-formada|2026|2026-11-14"},
             {"categoria": "Mídia", "titulo": "STF rejeita recursos e manda encerrar ação sobre acordo dos planos econômicos",
              "chave": "jota|noticia|stf-rejeita-recursos-e-manda-encerrar-acao-sobre-acordo|2026|2026-11-13"},
             {"categoria": "Opinião/Análise", "titulo": "Um artigo", "chave": "conjur|opiniao|um-artigo|2026|2026-11-12"},
             {"categoria": "STF Notícias", "titulo": "Um artigo", "chave": "conjur|opiniao|um-artigo|2026|2026-11-12"},
             {"categoria": "Mídia", "titulo": "Gilmar Mendes interrompe julgamento com maioria formada (desdobramento)",
              "chave": "jota|noticia|gilmar-mendes-interrompe-julgamento-com-maioria-formada|2026|2026-11-15",
              "desdobramento": True}]
    ficam, fora = M.descartar_repetidos(itens, hist, {"2026-11-16-7h"})
    motivos = [m for _, m in fora]
    ok(len(fora) == 2 and motivos[0].startswith("POSSIVEL_REPETIDA da mesma fonte (jota)")
       and motivos[1].startswith("REPUBLICADA"), "descarta mesma fonte e chave exata: %s" % motivos)
    ok(len(ficam) == 3 and ficam[0]["chave"].startswith("jota|noticia|stf-rejeita"), "outra fonte fica (vira AVISO)")
    ok(any(it.get("desdobramento") for it in ficam) and any(it["categoria"] == "STF Notícias" for it in ficam),
       "desdobramento e secoes centrais nunca descartados")
    ev = {"rg397": dict(next(r for r in fx("informativos-1611.json") if r["id"] == "rg397"), _fonte="informativo")}
    midia = {"categoria": "Mídia", "titulo": "STF reconhece repercussão geral do \"milagre da contribuição única\"",
             "resumo": "A controvérsia vai da reforma de 2019 à lei de 2022 que restabeleceu o divisor mínimo da "
                       "aposentadoria.", "nota": "sem confirmação oficial localizada nesta execução"}
    av = M.relacionados_informativos([{"categoria": "Informativos", "ref": "rg397"}, midia], ev)
    ok(len(av) == 1 and "relacionado a rg397[5] (Tema 1.499" in av[0] and "cite o tema" in av[0],
       "Midia ligada ao Tema 1.499: %s" % av)
    midia["resumo"] += " O tema é o Tema 1.499."
    ok(M.relacionados_informativos([{"categoria": "Informativos", "ref": "rg397"}, midia], ev) == [],
       "citado o tema, o aviso some")


# ------------------------------------------------------------------ ponta a ponta: 16/11 (1a rodada real)
@teste
def t_replay_1611():
    t = preparar_pasta("1611")
    exe = os.path.join(t, "execucao.json")
    with open(exe, "rb") as f:
        original = f.read()
    with open(os.path.join(t, "email.html"), "w") as f:      # HTML velho de outra rodada
        f.write("velho")
    rc, out, err = rodar("1611", t)
    ok(rc == 0, "16/11: rc=%d %s" % (rc, (out + err)[-300:]))
    with open(exe, "rb") as f:
        ok(f.read() == original, "K2: execucao.json do orquestrador intacto")
    res = json.load(open(os.path.join(t, "execucao.resolvido.json"), encoding="utf-8"))
    ok(res.get("execution_id") == "2026-11-16-7h" and not any(k.startswith("_") for it in res["items"] for k in it),
       "resolvido gravado em ROBOZINHO_TMP, sem campos internos")
    ok(len(out.encode("utf-8")) < 3000, "saida < 3 KB (%d bytes)" % len(out.encode("utf-8")))
    ok("HTMLBODY" not in out and "<table" not in out, "corpo nao vai ao stdout")
    pref = [l.split(":")[0].split(" ")[0] for l in out.splitlines()]
    ordem = [p for p in pref if p in ("VALIDACAO", "MONTAGEM", "ASSUNTO", "PARA", "BYTES", "SHA256", "CAMINHO")]
    ok(ordem == ["VALIDACAO", "MONTAGEM", "ASSUNTO", "PARA", "BYTES", "SHA256", "CAMINHO"], "ordem da saida: %s" % ordem)
    i_para, i_bytes = pref.index("PARA"), pref.index("BYTES")
    ok(all(p in ("DESCARTADA", "AVISO") for p in pref[i_para + 1:i_bytes]), "avisos e descartes entre PARA e BYTES")
    ok(not os.path.exists(os.path.join(t, "email.html")), "com aviso acionavel, email.html nao existe (o velho foi apagado)")
    caminho = linha(out, "CAMINHO: ")[9:]
    ok(caminho.endswith("email-com-avisos.html"), "CAMINHO aponta email-com-avisos.html")
    with open(caminho, "rb") as f:
        dados = f.read()
    ok(linha(out, "BYTES: ") == "BYTES: %d" % len(dados), "BYTES confere")
    ok(linha(out, "SHA256: ") == "SHA256: " + hashlib.sha256(dados).hexdigest(), "SHA256 confere")
    html = dados.decode("utf-8")
    ok(html.endswith('</table>\n<span style="display:none">fim-2026-11-16-7h</span>\n</td></tr></table>'),
       "sentinela oculta antes do fechamento final")
    ok("sem link; sem link" not in html and "clipping sem link" not in html, "some 'sem link; sem link'")
    ok('do &quot;milagre da contribuição única&quot;.</b> Decisão' in html
       or 'do "milagre da contribuição única".</b> Decisão' in html, "aspa ganha ponto")
    ok("Sem Repercussão Geral em Pauta nova na janela; teses e julgados do STF desta edição estão em 📚 Informativos"
       in html, "apoio da STF Jurisprudencia aponta Informativos")
    ok("Concursos com confirmação oficial pendente" not in html, "linha 'confirmação oficial pendente' saiu")
    ok("— falhou" not in html.split("Fontes secundárias consultadas")[1].split("📋")[0], "YouVersion nao aparece como falha")
    sup = html.split("Suporte usado na execução")[1]
    ok(not re.search(r"http\s*\d|\.py\b|coleta_web|informativos\.py", sup.split("Gerado em")[0]), "rodape sem ruido tecnico")
    ok(html.count("Informativo STF 1238") == 0 or "Informativo STF 1238" not in html.split("📋")[1],
       "observacao repetida das Limitacoes saiu")
    ok("Lei nº 15.529, de 12/11/2026</b></a> <span style=\"font-size:11px;color:#5a6773\">· DOU 12/11 · edição extra"
       in html, "metadado do Planalto sem parenteses aninhados")
    ok(html.index("Decreto nº 13.166") < html.index("Atos de rotina") < html.index("Lei nº 15.529"),
       "atos de rotina no fim da secao (13.166 antes)")
    for n in ("13.162", "13.163", "13.164", "13.165", "15.529"):
        ok(("nº %s" % n) in html.split("Atos de rotina")[1].split("STF — Notícias")[0], "rotina %s nao omitido" % n)
    ok("Tema 1.338" in html and "Tema 1.499" in html and "11 de 11" in json.dumps(res, ensure_ascii=False),
       "RG com todos os temas por padrao")
    ok("destaques da edição anunciada em 11/11" in html, "atrasada com a data do anuncio")
    ok("<i>Resumo:</i> É constitucional lei complementar estadual" in html, "STF com resumo oficial")
    ok(linha(out, "DESCARTADA ").startswith("DESCARTADA «Gilmar Mendes interrompe julgamento"),
       "repetido da mesma fonte descartado sozinho")
    ok("Gilmar Mendes interrompe julgamento" not in html, "descartado nao sai no e-mail")
    ok("AVISO ACIONÁVEL: POSSIVEL_REPETIDA: jota|noticia|stf-rejeita" in out, "repetido de outra fonte segue AVISO")
    ok("relacionado a rg397[5] (Tema 1.499" in out and "relacionado a rg397[9] (Tema 977" in out,
       "midia ligada aos temas 1.499 e 977")
    ok(not re.search(r"(?m)^ERRO", out) and "corpo com" not in out, "nenhum ERRO (nem por tamanho)")
    ok("AVISO: Planalto sem \"impacto\"" in out and "Decreto nº 13.166" in linha(out, "AVISO: Planalto sem"),
       "AVISO de ato oficial sem impacto")
    ok("card de Legislação e preheader citam só ato de rotina" in out, "AVISO do card/preheader so com rotina")
    # identidade visual: todo estilo do e-mail enviado em 16/11 continua no novo, a menos das reescritas equivalentes
    # (mesma renderizacao, provada por captura de tela pixel a pixel em 21/11: estilo_equivalente)
    with open(os.path.join(FIX, "estilos-1611.txt"), encoding="utf-8") as f:
        estilos = [estilo_equivalente(l.rstrip("\n")) for l in f if l.strip()]
    novos = set(re.findall(r'style="([^"]*)"', html))
    faltam = [e for e in estilos if e not in novos]
    ok(not faltam, "identidade visual: estilos de 16/11 preservados (faltam %s)" % faltam[:3])
    ok(PLANALTO_TITULO_6PX in html, "Planalto: titulo com 6px embaixo (a frase sem margem negativa)")


@teste
def t_k2_duas_rodadas():
    ex = fx("execucao-1611.json")
    t = preparar_pasta("1611", execucao=ex)
    rc, out, _ = rodar("1611", t)
    res1 = json.load(open(os.path.join(t, "execucao.resolvido.json"), encoding="utf-8"))
    rg1 = next(i for i in res1["items"] if i.get("ref") == "rg397")
    ok(rg1["observacao"] == "11 de 11 destaques publicados", "1a rodada: %s" % rg1["observacao"])
    for it in ex["items"]:
        if it.get("ref") == "rg397":
            it["destaques"] = {"excluir": [1, 4]}
    json.dump(ex, open(os.path.join(t, "execucao.json"), "w", encoding="utf-8"), ensure_ascii=False)
    rc, out, _ = rodar("1611", t)
    res2 = json.load(open(os.path.join(t, "execucao.resolvido.json"), encoding="utf-8"))
    rg2 = next(i for i in res2["items"] if i.get("ref") == "rg397")
    ok(rc == 0 and rg2["observacao"] == "9 de 11 destaques publicados", "2a rodada reflete 'destaques': %s"
       % rg2["observacao"])
    ok(not any("Tema 1.487" in d for d in rg2["destaques_texto"]), "tema excluido some")
    # entrada que ja e uma versao resolvida (campos derivados velhos) + destaques novos: vale o novo
    velho = copy.deepcopy(res1)
    for it in velho["items"]:
        if it.get("ref") == "rg397":
            it["destaques"] = [5, 6]
    json.dump(velho, open(os.path.join(t, "execucao.json"), "w", encoding="utf-8"), ensure_ascii=False)
    rc, out, _ = rodar("1611", t)
    res3 = json.load(open(os.path.join(t, "execucao.resolvido.json"), encoding="utf-8"))
    rg3 = next(i for i in res3["items"] if i.get("ref") == "rg397")
    ok(rc == 0 and rg3["destaques_texto"] != rg1["destaques_texto"] and rg3["observacao"] == "11 de 11 destaques "
       "publicados", "derivados velhos do arquivo ignorados (recalculados)")
    pend = [d for d in rg3["destaques_texto"] if "em votação" in d]
    ok(pend and "Tema 1.499" in pend[0], "ordem dada vale dentro do grupo: %s" % (pend[:1],))


@teste
def t_erros_e_flags():
    ex = fx("execucao-1611.json")
    ex["items"].append({"categoria": "STJ Jurisprudência", "titulo": "STJ fixa tese x", "fonte": "ConJur",
                        "url": "https://www.conjur.com.br/2026-nov-15/stj-fixa-tese", "data": "2026-11-15"})
    t = preparar_pasta("1611", execucao=ex)
    with open(os.path.join(t, "email.html"), "w") as f:
        f.write("velho")
    rc, out, _ = rodar("1611", t)
    ok(rc == 2 and "MONTAGEM: ERRO" in out and "STJ Jurisprudência só aceita fonte oficial" in out,
       "STJ Jurisprudencia de midia e ERRO")
    ok(not any(os.path.exists(os.path.join(t, n)) for n in ("email.html", "email-com-avisos.html",
                                                            "execucao.resolvido.json")), "ERRO: nada gravado")
    ex = fx("execucao-1611.json")
    ex["items"].append({"categoria": "Planalto/Legislação", "status": "CONFIRMADO POR FONTE OFICIAL",
                        "titulo": "Lei nº 99.999, de 12/11/2026", "data": "2026-11-12", "impacto": "x" * 161,
                        "url": "https://www.planalto.gov.br/ccivil_03/x.htm"})
    t = preparar_pasta("1611", execucao=ex)
    rc, out, _ = rodar("1611", t)
    ok(rc == 2 and "\"impacto\" com 161 caracteres" in out, "impacto acima de 160 e ERRO")
    # tamanho: nunca ERRO; AVISO a partir de 80 KB, com o tamanho por secao
    ex = fx("execucao-1611.json")
    for it in ex["items"]:
        if it.get("categoria") == "Fofoquinha":
            it["resumo"] = (it.get("resumo") or "") + " " + "texto longo de teste " * 700
    t = preparar_pasta("1611", execucao=ex)
    rc, out, _ = rodar("1611", t, "--com-html")
    ok(rc == 0 and "AVISO: corpo com" in out and "maiores seções: Fofoquinha" in out, "tamanho: AVISO, nao ERRO")
    ok("==== HTMLBODY ====" in out and "==== FIM HTMLBODY ====" in out, "--com-html imprime o corpo")


# ------------------------------------------------------------------ ponta a ponta: 17/11 simulado (terca)
@teste
def t_simulacao_1711():
    t = preparar_pasta("1711")
    rc, out, err = rodar("1711", t)
    ok(rc == 0, "17/11: rc=%d %s" % (rc, (out + err)[-300:]))
    html = corpo(out)
    n = int(re.search(r"(\d+) em linha compacta", out).group(1))
    ok(n >= 15 and html.count("Sem mudança recente — selo e data da última mudança") >= 8,
       "terca: concursos sem mudanca compactos (%d)" % n)
    ok("<b>Errata:</b> Na edição de 16/11, onde se leu que as inscrições do TJAP" in html, "errata do TJAP publicada")
    tjap = html.split("TJAP — Juiz de Direito Substituto</b>")[1].split("</tr>")[0]
    ok("ENCERRA EM BREVE" in tjap and "(herdada" not in tjap, "TJAP com carimbo da banca de hoje (sem 'herdada')")
    ok("Em atraso — edições anteriores cujo documento só agora abriu" in html and "destaques da edição anunciada em 21/10"
       in html, "sub-bloco Em atraso (revisitas)")
    stj = html.split("⚖️ STJ — Notícias")[1].split("⚖️ STJ — Jurisprudência")[0]
    ok("MÍDIA ESPECIALIZADA" in stj and "STJ define diretrizes" in stj and "sem confirmação oficial localizada" not in stj
       and stj.count(M.LINHA_STJ_MIDIA) == 1 and stj.index(M.LINHA_STJ_MIDIA) < stj.index("STJ define diretrizes"),
       "STJ Noticias aceita midia com selo, sem nota por item e com a linha fixa no topo")
    ok(linha(out, "DESCARTADA ").startswith("DESCARTADA «Senado aprova texto-base") and "REPUBLICADA" in out,
       "republicada de apoio descartada")
    ok("lição inspirada em Charlie Munger" in html, "Munger licao")
    ok("youversion falha→nao_tentada" in out and "YouVersion" not in html.split("Fontes secundárias")[1].split("📋")[0],
       "YouVersion nao_tentada pelo fontes_status")
    ok("A confirmar — inscrição ou prova em até 14 dias" in html and "PGM Suzano" not in
       html.split("Prazos no radar")[1].split("Magistratura Estadual")[0], "a confirmar sem divergencia/retificacao")
    # sem aviso acionavel -> email.html
    ex = fx("execucao-1711.json")
    ex["items"] = [it for it in ex["items"] if it.get("ref") != "c1"]
    t = preparar_pasta("1711", execucao=ex)
    rc, out, _ = rodar("1711", t)
    ok(rc == 0 and linha(out, "MONTAGEM: ").startswith("MONTAGEM: OK —") and linha(out, "CAMINHO: ").endswith(
        "/email.html") and not os.path.exists(os.path.join(t, "email-com-avisos.html")), "sem aviso acionavel: email.html")
    # segunda-feira (1a da semana): so os dormentes compactam
    j = fx("janela-1711.json")
    j["primeira_semana"] = True
    t = preparar_pasta("1711", execucao=ex, janela=j)
    rc, out, _ = rodar("1711", t)
    ok(rc == 0 and re.search(r" 0 em linha compacta", out), "1a edicao da semana: completa (%s)"
       % re.search(r"\d+ em linha compacta", out).group(0))
    # edicao extra
    j = fx("janela-1711.json")
    j.update(edicao_extra=True, cabecalho_extra="Edição extra", tipo="extra", execution_id="2026-11-17-extra")
    t = preparar_pasta("1711", execucao=ex, janela=j)
    rc, out, _ = rodar("1711", t)
    html = corpo(out)
    ok(rc == 0 and "Edição extra · 17/11/2026 (terça-feira)" in html and "fim-2026-11-17-extra" in html,
       "cabecalho da edicao extra")


@teste
def t_planalto_resenha_impacto():
    ex = fx("execucao-1711.json")
    ex["items"].insert(0, {"categoria": "Planalto/Legislação", "status": "CONFIRMADO POR FONTE OFICIAL",
                           "titulo": "Lei nº 99.998, de 16/11/2026", "data": "2026-11-16",
                           "resenha": "Resenha Diária PUSH Legislação - 16/11/2026 | recebida 16/11 09h50",
                           "meta": "ato 16/11/2026; DOU 17/11/2026 (edição extra)",
                           "resumo": "Altera o Decreto-Lei nº 2.848, de 7 de dezembro de 1940 (Código Penal), para "
                                     "teste do montador.",
                           "url": "https://www.planalto.gov.br/ccivil_03/teste.htm"})
    t = preparar_pasta("1711", execucao=ex)
    rc, out, _ = rodar("1711", t)
    html = corpo(out)
    ok(rc == 0 and "— Resenha Diária PUSH Legislação de 16/11 (recebida em 16/11, 09h50)." in html,
       "grupo derivado da resenha")
    ok("· DOU 17/11 · edição extra" in html and "<i>Para a prova</i> — Altera: Código Penal." in html,
       "meta normalizado e impacto pre-preenchido")
    ok("Planalto sem \"impacto\"" not in out, "com impacto pre-preenchido, sem AVISO")


# ------------------------------------------------------------------ revisao adversarial (REV-MON): 4 correcoes
ATOS_REV = [  # casos reproduzidos pelos revisores (Planalto de 16/11 simulado)
    {"categoria": "Planalto/Legislação", "titulo": "Decreto nº 13.170, de 16/11/2026", "status": "CONFIRMADO POR FONTE OFICIAL",
     "resumo": "Altera o Decreto nº 11.615, de 21 de julho de 2023, que regulamenta a Lei nº 10.826, de 22 de dezembro "
               "de 2003, para dispor sobre o registro de armas de fogo.",
     "url": "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2026/decreto/D13170.htm", "data": "2026-11-16",
     "fonte": "PUSH Planalto", "meta": "DOU 17/11",
     "resenha": "Resenha Diária PUSH Legislação - 16/11/2026 | recebida 16/11 19:02"},
    {"categoria": "Planalto/Legislação", "titulo": "Lei nº 15.540, de 16/11/2026", "status": "CONFIRMADO POR FONTE OFICIAL",
     "resumo": "Altera a Lei nº 12.153, de 22 de dezembro de 2009, que regulamenta o art. 98, I, da Constituição "
               "Federal, para dispor sobre os Juizados Especiais da Fazenda Pública.",
     "url": "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2026/lei/L15540.htm", "data": "2026-11-16",
     "fonte": "PUSH Planalto", "meta": "DOU 17/11",
     "resenha": "Resenha Diária PUSH Legislação - 16/11/2026 | recebida 16/11 19:02"},
    {"categoria": "Planalto/Legislação", "titulo": "Lei nº 15.541, de 16/11/2026", "status": "CONFIRMADO POR FONTE OFICIAL",
     "resumo": "Transforma cargos vagos do Quadro de Pessoal do Tribunal Regional Federal da 6ª Região em cargos de "
               "Juiz Federal Substituto.",
     "url": "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2026/lei/L15541.htm", "data": "2026-11-16",
     "fonte": "PUSH Planalto", "meta": "DOU 17/11",
     "resenha": "Resenha Diária PUSH Legislação - 16/11/2026 | recebida 16/11 19:02"},
]


@teste
def t_rev_impacto_so_objeto():
    casos = [  # (titulo, ementa, impacto esperado)
        ("Decreto nº 13.170", ATOS_REV[0]["resumo"], ""),                       # decreto nao altera lei
        ("Lei nº 15.540", ATOS_REV[1]["resumo"], ""),                           # CF so na oracao "que regulamenta"
        ("Lei nº 15.542", "Altera a Lei nº 13.675, de 2018, para prever ações de combate às organizações criminosas.", ""),
        ("Lei nº 1", "Altera a Lei nº 14.230, de 2021, que trata de improbidade administrativa.", ""),
        ("Lei nº 1", "Altera a Lei nº 13.675, de 2018, nos termos da Lei nº 11.340, de 2006.", ""),
        ("Lei nº 1", "Altera o art. 5º da Constituição Federal.", ""),          # so emenda altera a Constituicao
        ("Decreto nº 1", "Altera o Decreto-Lei nº 2.848, de 7 de dezembro de 1940 (Código Penal).", ""),
        ("Lei nº 1", "Altera os valores previstos na Lei nº 8.112, de 1990.", ""),   # na duvida, vazio
        ("Emenda Constitucional nº 136, de 2026", "Altera o art. 100 da Constituição Federal e o Ato das Disposições "
         "Constitucionais Transitórias para dispor sobre precatórios.", "Altera: Constituição Federal"),
        ("Lei nº 1", "Altera a Consolidação das Leis do Trabalho (CLT), aprovada pelo Decreto-Lei nº 5.452, de 1º de "
         "maio de 1943, para dispor sobre o teletrabalho.", "Altera: CLT"),
        ("Lei nº 1", "Acrescenta o art. 121-B ao Decreto-Lei nº 2.848, de 7 de dezembro de 1940 (Código Penal), para "
         "tipificar o crime.", "Altera: Código Penal"),
        ("Medida Provisória nº 1.300, de 2026", "Altera a Lei nº 8.112, de 11 de dezembro de 1990, que dispõe sobre o "
         "regime jurídico dos servidores, para ...", "Altera: Estatuto dos Servidores Federais (Lei 8.112/1990)"),
        ("Lei nº 1", "Altera a Lei nº 11.340, de 7 de agosto de 2006 (Lei Maria da Penha), para prever medida "
         "protetiva.", "Altera: Lei Maria da Penha"),
    ]
    for tit, em, esperado in casos:
        r = M.impacto_auto(em, tit)
        ok(r == esperado, "impacto(%s, %s…) = %r (esperado %r)" % (tit, em[:40], r, esperado))
    ex = fx("execucao-1711.json")
    ex["items"] += copy.deepcopy(ATOS_REV)
    ex["email"]["resumo"].insert(1, ["📜", "Legislação", "Lei 15.541 transforma cargos vagos do TRF6 em cargos de "
                                     "Juiz Federal Substituto."])
    t = preparar_pasta("1711", execucao=ex)
    rc, out, _ = rodar("1711", t)
    html = corpo(out)
    plan = html.split("⚖️ STF — Notícias")[0]
    ok(rc == 0 and "Altera: Constituição Federal" not in html and "Altera: Estatuto do Desarmamento" not in html,
       "sem 'Para a prova' falso no Planalto")
    av = linha(out, "AVISO: Planalto sem \"impacto\"")
    ok(all(n in av for n in ("Decreto nº 13.170", "Lei nº 15.540", "Lei nº 15.541")), "AVISO sem impacto: %s" % av)
    ok("Lei nº 15.541" in plan and "Atos de rotina" not in plan, "cargos de Juiz nao sao ato de rotina")
    ok("só ato de rotina" not in out, "card da Lei 15.541 nao pede troca")


@teste
def t_rev_rotina_cargos():
    casos = {
        ATOS_REV[2]["resumo"]: False,
        "Cria cargos efetivos e cargos em comissão no Quadro de Pessoal do Tribunal Regional do Trabalho da 8ª Região.": False,
        "Transforma cargos em comissão em cargos de Procurador da Fazenda Nacional.": False,
        "Dispõe sobre a transformação de cargos vagos em vagas de Promotor de Justiça.": False,
        "Transforma cargos vagos de Agente Administrativo em cargos de Analista.": False,
        "Altera o Decreto nº 11.178 e remaneja e transforma cargos em comissão e funções de confiança.": True,
        "Remaneja cargos em comissão da Procuradoria-Geral da Fazenda Nacional.": True,
        "Abre ao Orçamento Fiscal da União, em favor da Defensoria Pública da União e do Ministério Público da União, "
        "crédito suplementar.": True,
    }
    for em, esperado in casos.items():
        ok(M.eh_rotina({"titulo": "Lei nº 1", "resumo": em}) is esperado, "rotina=%s: %s" % (esperado, em[:60]))


@teste
def t_rev_fonte_oficial_sem_url():
    for f in ("Push STF", "STJ CodJu", "PUSH Planalto (Resenha Diária 09/11)", "Congresso Nacional (Rota 13)",
              "boletim da Agência Câmara", "Agência Câmara (boletim 11/11)", "STF Notícias (Push STF)",
              "STJ — página oficial do informativo", "gmail_stj_codju", "Jurisprudência em Teses (STJ)"):
        ok(M.item_oficial({"fonte": f}), "rotulo oficial: %s" % f)
    for f in ("STJ (via JOTA)", "JOTA (decisão do STJ)", "Valor Econômico (via JOTA)", "Push STF + ConJur",
              "STJ, segundo O Tempo", "ConJur", ""):
        ok(not M.item_oficial({"fonte": f}), "rotulo nao oficial: %r" % f)
    ok(M.item_oficial({"fonte": "JOTA", "url": "https://processo.stj.jus.br/x"})
       and not M.item_oficial({"fonte": "STJ", "url": "https://www.jota.info/x"}), "com URL vale o dominio")
    ex = fx("execucao-1711.json")
    ex["items"].append({"categoria": "STJ Jurisprudência", "titulo": "STJ fixa tese sobre remição pelo Enem",
                        "fonte": "STJ (via JOTA)", "data": "2026-11-16", "status": "CONFIRMADO POR FONTE OFICIAL"})
    t = preparar_pasta("1711", execucao=ex)
    rc, out, _ = rodar("1711", t)
    ok(rc == 2 and "STJ fixa tese sobre remição pelo Enem: STJ Jurisprudência só aceita fonte oficial" in out,
       "STJ Jurisprudencia 'via JOTA' sem URL e ERRO")
    ex = fx("execucao-1711.json")
    ex["items"].append({"categoria": "STJ Notícias", "titulo": "STJ decide sobre honorários",
                        "fonte": "JOTA (decisão do STJ)", "data": "2026-11-16", "status": "CONFIRMADO POR FONTE OFICIAL"})
    t = preparar_pasta("1711", execucao=ex)
    rc, out, _ = rodar("1711", t)
    stj = corpo(out).split("⚖️ STJ — Notícias")[1].split("⚖️ STJ — Jurisprudência")[0]
    trecho = stj.split("STJ decide sobre honorários")[0][-400:]
    ok(rc == 0 and "MÍDIA ESPECIALIZADA" in trecho and "CONFIRMADO POR FONTE OFICIAL" not in trecho
       and "STJ decide sobre honorários: STJ Notícias de mídia sai como MÍDIA ESPECIALIZADA" in out,
       "STJ Noticias 'JOTA (decisão do STJ)' sem URL perde o selo oficial")


@teste
def t_rev_card_cita_descartado():
    descartado = {"categoria": "Mídia", "titulo": "Senado aprova texto-base do pacote fiscal com impacto previsto de "
                  "até R$ 56 bi", "resumo": ""}
    ficou = {"categoria": "Mídia", "titulo": "Senado conclui votação do pacote fiscal", "resumo": ""}
    em = {"resumo": [["🗞️", "Mídia", "Senado conclui votação do pacote fiscal; TJAP encerra inscrições amanhã."]],
          "preheader": "TJAP encerra amanhã"}
    ok(M.cards_citam_descartados(em, [ficou], [(descartado, "REPUBLICADA: x")]) == [],
       "card explicado por item que ficou: sem aviso")
    em["resumo"][0][2] = "Senado aprova texto-base do pacote fiscal (R$ 56 bi)."
    av = M.cards_citam_descartados(em, [ficou], [(descartado, "REPUBLICADA: x")])
    ok(len(av) == 1 and av[0].startswith("card do resumo «Mídia» cita item descartado («Senado aprova")
       and M.ACIONAVEL.search(av[0]), "card cita o descartado: %s" % av)
    ex = fx("execucao-1711.json")
    ex["email"]["resumo"].append(["🗞️", "Mídia", "Senado aprova texto-base do pacote fiscal com impacto de até R$ 56 bi."])
    ex["email"]["preheader"] += " · Senado aprova pacote fiscal de R$ 56 bi"
    t = preparar_pasta("1711", execucao=ex)
    rc, out, _ = rodar("1711", t)
    av = linha(out, "AVISO ACIONÁVEL: card do resumo «Mídia» e preheader citam item descartado («Senado aprova")
    ok(rc == 0 and av and "MONTAGEM: OK COM AVISOS" in out and linha(out, "CAMINHO: ").endswith("email-com-avisos.html"),
       "e-mail com card sobre item descartado pede decisao: %s" % linha(out, "AVISO ACIONÁVEL: card"))
    for it in ex["items"]:
        if it.get("titulo", "").startswith("Senado aprova"):
            it["desdobramento"] = True
    t = preparar_pasta("1711", execucao=ex)
    rc, out, _ = rodar("1711", t)
    ok(rc == 0 and "DESCARTADA" not in out and "item descartado" not in out, "desdobramento: nada descartado nem avisado")


# ------------------------------------------------------------------ 2a rodada de correcao (reteste final)
DIAS_SEMANA = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]


def pasta_dia(dia, upd, ledger=None, banca=None):
    """Execucao minima de `dia` (18 ou 19/11) com o ledger de 16/11 (ou `ledger`), a banca de 17/11 reaproveitada
    como lida em `dia` (banca: funcao que altera o bancas.json; False = sem bancas.json) e ledger_updates.concursos
    = `upd`. Devolve a pasta (ROBOZINHO_TMP) com led.json e hist.json proprios (o helper grava neles)."""
    N_PASTA[0] += 1
    t = os.path.join(BASE_TMP, "d%d-%s" % (N_PASTA[0], dia[5:]))
    os.makedirs(t)
    d = date.fromisoformat(dia)
    ant = date.fromordinal(d.toordinal() - 1)
    j = fx("janela-1711.json")
    j.update(data=dia, execution_id=dia + "-7h", inicio=ant.isoformat() + "T07:05:00-03:00",
             fim=dia + "T07:05:00-03:00", hoje_br=d.strftime("%d/%m/%Y"), dia_semana=DIAS_SEMANA[d.weekday()],
             execucao_anterior=ant.isoformat() + "-7h", assunto="Robozinho dos Momozis até Passar - %s - 7h"
             % d.strftime("%d/%m/%Y"), gmail_apos=ant.strftime("%Y/%m/%d"))
    json.dump(j, open(os.path.join(t, "janela.json"), "w", encoding="utf-8"), ensure_ascii=False)
    if banca is not False:
        b = fx("bancas-1711.json")
        b.update(data=dia, execution_id=dia + "-7h")
        if banca:
            banca(b)
        json.dump(b, open(os.path.join(t, "bancas.json"), "w", encoding="utf-8"), ensure_ascii=False)
    shutil.copy(os.path.join(FIX, "versiculo-1711.json"), os.path.join(t, "versiculo.json"))
    json.dump(ledger or fx("ledger-1611.json"), open(os.path.join(t, "led.json"), "w", encoding="utf-8"),
              ensure_ascii=False)
    shutil.copy(os.path.join(FIX, "historico.json"), os.path.join(t, "hist.json"))
    ex = {"delivery": "draft", "verification_notes": ["teste"], "errors": [],
          "source_status": {"gmail_push_stf": "ok", "gmail_push_planalto": "vazio", "gmail_stj_codju": "ok"},
          "items": [{"categoria": "STF Notícias", "titulo": "STF começa a julgar exigência de valor em pedidos "
                     "trabalhistas", "fonte": "Push STF", "data": ant.isoformat(), "hora": "19:02",
                     "url": "https://noticias.stf.jus.br/postsnoticias/stf-comeca-a-julgar-exigencia/",
                     "status": "CONFIRMADO POR FONTE OFICIAL"}],
          "email": {"preheader": "Concursos do TJAP e do TJPB", "reflexao": "Reflexão de teste.",
                    "resumo": [["⏰", "Concursos", "TJAP (Juiz) e TJPB (Analista): inscrições na FGV."],
                               ["⚖️", "STF", "STF começa a julgar exigência de valor em pedidos trabalhistas."],
                               ["📚", "Informativos", "Sem informativo novo nesta janela."]]},
          "ledger_updates": {"concursos": upd} if upd else {}}
    json.dump(ex, open(os.path.join(t, "execucao.json"), "w", encoding="utf-8"), ensure_ascii=False)
    return t


HELPER_OUT = [""]          # relatorio do helper (persistencia) da ultima chamada de montador_e_helper


def montador_e_helper(t):
    """Roda os dois sobre a MESMA entrada: o montador (CLI e estado_concursos, que e o que o e-mail mostra) e o
    helper persistindo o execucao.resolvido.json do montador (o que o finalizar.sh faz). Devolve
    (stdout do montador, html, {id: (selo, verificado_em)} do e-mail, idem do ledger gravado pelo helper).
    O relatorio do helper fica em HELPER_OUT[0]."""
    env = dict(os.environ, ROBOZINHO_TMP=t)
    led, hist = os.path.join(t, "led.json"), os.path.join(t, "hist.json")
    r = subprocess.run([sys.executable, os.path.join(WORK, "montar_email.py"), "--ledger", led, "--historico", hist],
                       capture_output=True, text=True, env=env, cwd=WORK)
    out = r.stdout + r.stderr
    html = corpo(r.stdout) if linha(r.stdout, "CAMINHO: ") else ""
    ex = json.load(open(os.path.join(t, "execucao.json"), encoding="utf-8"))
    j = json.load(open(os.path.join(t, "janela.json"), encoding="utf-8"))
    ctx = M.estado_concursos(ex, j, json.load(open(led, encoding="utf-8")),
                             {"historico": hist, "bancas": os.path.join(t, "bancas.json")}, [])
    no_email = {c["id"]: (c.get("selo"), c.get("verificado_em")) for c in ctx["regs"]}
    h = subprocess.run([sys.executable, os.path.join(WORK, "Update-Historico.py"), "--nova-execucao",
                        os.path.join(t, "execucao.resolvido.json"), "--ledger", led, "--historico", hist,
                        "--janela", os.path.join(t, "janela.json"), "--bancas", os.path.join(t, "bancas.json"),
                        "--fontes-status", os.path.join(t, "fontes_status.json"), "--draft-id", "r-teste"],
                       capture_output=True, text=True, env=env, cwd=WORK)
    ok(h.returncode == 0 and "STATUS: OK" in h.stdout, "helper persistiu: %s" % (h.stdout + h.stderr)[-300:])
    HELPER_OUT[0] = h.stdout + h.stderr
    no_ledger = {c["id"]: (c.get("selo"), c.get("verificado_em"))
                 for c in json.load(open(led, encoding="utf-8"))["concursos"]}
    return out, html, no_email, no_ledger


def concordam(no_email, no_ledger, rotulo):
    dif = {k: (no_email.get(k), no_ledger.get(k)) for k in set(no_email) | set(no_ledger)
           if no_email.get(k) != no_ledger.get(k)}
    ok(not dif, "%s: montador e helper concordam em selo e verificado_em (diferem: %s)" % (rotulo, dif))


def selo_no_html(html, cabeca):
    m = re.search(r"<b>%s</b> (?:<b [^>]*>NOVO</b> )?<b [^>]*>([^<]+)</b>" % re.escape(cabeca), html)
    return m.group(1) if m else None


TRECHO_TJSC = "das 16h do dia 19 de outubro de 2026 até às 16h do dia 26 de novembro de 2026"
TRECHO_TJAP = "das 16h do dia 13 de outubro de 2026 até às 16h do dia 18 de novembro de 2026"


def tjsc_com_fim(led, dia):
    """Registro do TJSC com o fim das inscricoes em `dia`/11 (prazos e linha; o edital da FGV diz 26/11)."""
    for c in led["concursos"]:
        if c["id"] == "tjsc_juiz":
            c["linha"] = c["linha"].replace("até 16h de 26/11", "até 16h de %s/11" % dia)
            c["prazos"][0]["data"] = "2026-11-%s" % dia
    return led


def edital_relido(ident, fim, trecho, inicio, motivo, registro=None):
    """bancas.json com o edital de `ident` relido hoje (o que o bancas.py grava: releitura, edital, inscricoes e,
    se o registro da manha divergia, `divergencias` com o texto `registro`)."""
    def f(b):
        for c in b["concursos"]:
            if ident in c["coberto"]:
                c["releitura"] = motivo
                c["edital"] = {"inscrições": trecho}
                c["inscricoes"] = {"inicio": inicio, "fim": fim, "trecho": trecho, "origem": "edital"}
                c["divergencias"] = ([{"id": ident, "edital": trecho, "registro": registro, "origem": "edital"}]
                                     if registro else [])
    return f


@teste
def t_r2_montador_e_helper_mesma_entrada():
    """P3 (selo copiado x decidido) e P9 (carimbo com o update de hoje): para a mesma entrada, o e-mail e o ledger
    gravado pelo helper tem o mesmo selo e o mesmo verificado_em em todos os concursos.
    CORE P2: registro que o edital lido hoje contesta (TJSC com fim 25/11 x edital 26/11) fica com o selo por data
    SUSPENSO nos dois (o selo do registro fica; AVISO ACIONÁVEL com as duas datas), tambem quando o orquestrador
    corrige so a linha e nao os prazos."""
    led = fx("ledger-1611.json")
    linha_tjpb = next(c for c in led["concursos"] if c["id"] == "tjpb_apoio")["linha"]
    # 18/11: copia (tjpb com a linha reescrita e o selo do registro; tjsc so o selo) e decisao (tjap)
    t = pasta_dia("2026-11-18", {"tjpb_apoio": {"linha": linha_tjpb, "selo": "ENCERRA EM BREVE"},
                                 "tjsc_juiz": {"selo": "INSCRIÇÕES ABERTAS"},
                                 "tjap_juiz": {"selo": "INSCRIÇÕES ENCERRADAS"}})
    out, html, em, lg = montador_e_helper(t)
    concordam(em, lg, "18/11 copia x decisao")
    ok(em["tjpb_apoio"][0] == "ENCERRA HOJE" and selo_no_html(html, "TJPB — Analista Judiciário (Edital nº 01/2026)")
       == "ENCERRA HOJE", "18/11: copia do selo -> ENCERRA HOJE no e-mail (%r)" % (em["tjpb_apoio"],))
    ok(em["tjap_juiz"][0] == "INSCRIÇÕES ENCERRADAS", "decisao mantida no e-mail e no ledger")
    ok("AVISO ACIONÁVEL: ledger_updates.concursos.tjap_juiz.selo: 'INSCRIÇÕES ENCERRADAS' escrito hoje contradiz o "
       "selo por data 'ENCERRA HOJE'" in out and linha(out, "CAMINHO: ").endswith("email-com-avisos.html"),
       "selo escrito que contradiz a data e acionavel: %s" % linha(out, "AVISO ACIONÁVEL: ledger"))
    ok(em["tjpb_apoio"][1] == "2026-11-18", "banca lida hoje: carimbo no e-mail")
    # 19/11: TJSC copiado com o fim das inscricoes a 7 dias
    t = pasta_dia("2026-11-19", {"tjsc_juiz": {"selo": "INSCRIÇÕES ABERTAS"}})
    out, html, em, lg = montador_e_helper(t)
    concordam(em, lg, "19/11 copia")
    ok(em["tjsc_juiz"][0] == "ENCERRA EM BREVE" and selo_no_html(html, "TJSC — Juiz Substituto") == "ENCERRA EM BREVE",
       "19/11: copia do TJSC -> ENCERRA EM BREVE (%r)" % (em["tjsc_juiz"],))
    ok(em["tjap_juiz"][0] == em["tjpb_apoio"][0] == "INSCRIÇÕES ENCERRADAS", "19/11: banca lida, encerradas")
    # P9: registro que diverge do edital (fim 20/11 x edital 18/11) nao e carimbado nem conta como banca lida
    div = copy.deepcopy(led)
    for c in div["concursos"]:
        if c["id"] == "tjpb_apoio":
            c["linha"] = c["linha"].replace("até 16h de 18/11", "até 16h de 20/11")
            c["prazos"][0]["data"] = "2026-11-20"

    def diverge(b):
        for c in b["concursos"]:
            if "tjpb_apoio" in c["coberto"]:
                c["divergencias"] = [{"id": "tjpb_apoio", "edital": c["inscricoes"]["trecho"],
                                      "registro": "prazo 20/11/2026 fim das inscrições, 16h", "origem": "edital"}]
    t = pasta_dia("2026-11-18", {}, ledger=div, banca=diverge)
    out, html, em, lg = montador_e_helper(t)
    concordam(em, lg, "18/11 diverge")
    tjpb = html.split("TJPB — Analista Judiciário (Edital nº 01/2026)</b>")[1].split("</tr>")[0]
    ok(em["tjpb_apoio"] == ("ENCERRA EM BREVE", "2026-11-16") and "(herdada; verificado em 16/11)" in tjpb,
       "diverge: sem carimbo de hoje no e-mail (%r)" % (em["tjpb_apoio"],))
    ok("AVISO ACIONÁVEL: DIVERGE DO REGISTRO em tjpb_apoio" in out and " … " not in linha(out, "AVISO ACIONÁVEL: DIVERGE"),
       "DIVERGE acionavel e inteiro (o fim diz o que fazer)")
    corrigido = {"tjpb_apoio": {"prazos": [{"data": "2026-11-18", "evento": "fim das inscrições, 16h", "confirmado": True}],
                                "linha": linha_tjpb}}
    t = pasta_dia("2026-11-18", corrigido, ledger=div, banca=diverge)
    out, html, em, lg = montador_e_helper(t)
    concordam(em, lg, "18/11 diverge corrigido")
    ok(em["tjpb_apoio"] == ("ENCERRA HOJE", "2026-11-18"), "corrigido hoje: carimbo e selo por data (%r)"
       % (em["tjpb_apoio"],))
    # a entrada do test_est.selo_copiado_nao_e_decisao (registro de 2a9eac9 + o LED do teste, banca de 16/11 lida em
    # 18/11, tjpb copiado e tjap decidido): o montador da o que o helper grava (so le as fixtures do EST)
    fe = os.path.join(AQUI, "fixtures", "est")
    if os.path.exists(os.path.join(fe, "concursos-2a9eac9.json")) and os.path.exists(os.path.join(fe, "bancas-1611.json")):
        regs = json.load(open(os.path.join(fe, "concursos-2a9eac9.json"), encoding="utf-8"))["concursos"]
        led_est = {"concursos": regs + [
            {"id": "leg", "bloco": "Magistratura Estadual", "linha": "Leg — Juiz", "selo": "INSCRIÇÕES ABERTAS",
             "verificado_em": "2026-11-10", "fonte": "secundária (busca)"},
            {"id": "ofi", "bloco": "Magistratura Estadual", "linha": "Ofi — Juiz", "selo": "EM ANDAMENTO",
             "verificado_em": "2026-11-10", "fonte": "https://conhecimento.fgv.br/concursos/ofi26",
             "pendencia": "ofi_verificar"}],
            "pendencias_vivas": [{"id": "ofi_verificar", "texto": "t", "faixa": "ativa", "execucoes": 2}],
            "fontes": [{"id": "conjur", "status": "saudavel", "sem_sucesso": 0, "nota": "n"}],
            "armadilhas": [{"id": "arm1"}], "licoes_de_processo": [], "niveis_de_esforco": {"saudavel": "", "instavel": ""}}
        tj = next(c for c in regs if c["id"] == "tjpb_apoio")
        t = pasta_dia("2026-11-18", {"tjpb_apoio": {"linha": tj["linha"], "selo": "ENCERRA EM BREVE"},
                                     "tjap_juiz": {"selo": "INSCRIÇÕES ENCERRADAS"}}, ledger=led_est)
        b = json.load(open(os.path.join(fe, "bancas-1611.json"), encoding="utf-8"))
        b["data"] = "2026-11-18"
        json.dump(b, open(os.path.join(t, "bancas.json"), "w", encoding="utf-8"), ensure_ascii=False)
        out, html, em, lg = montador_e_helper(t)
        concordam(em, lg, "entrada do test_est")
        ok(em["tjpb_apoio"][0] == "ENCERRA HOJE" and em["tjap_juiz"][0] == "INSCRIÇÕES ENCERRADAS",
           "entrada do test_est: copia -> selo por data, decisao mantida (%r, %r)" % (em["tjpb_apoio"], em["tjap_juiz"]))
    # CORE P2: TJSC com fim 25/11 no registro e 26/11 no edital relido em 18/11. Antes: o selo por data usava a data
    # contestada (ENCERRA EM BREVE, 7 dias) quando a oficial ainda dava INSCRIÇÕES ABERTAS (8 dias)
    led25 = tjsc_com_fim(copy.deepcopy(led), "25")
    banca25 = edital_relido("tjsc_juiz", "2026-11-26", TRECHO_TJSC, "2026-10-19", "prazo do registro em 25/11",
                            registro="prazo 25/11/2026 fim das inscrições, 16h")
    linha26 = next(c for c in led["concursos"] if c["id"] == "tjsc_juiz")["linha"]
    for rotulo, upd in (("sem update", {}), ("so a linha corrigida", {"tjsc_juiz": {"linha": linha26}})):
        t = pasta_dia("2026-11-18", upd, ledger=led25, banca=banca25)
        out, html, em, lg = montador_e_helper(t)
        concordam(em, lg, "P2 %s" % rotulo)
        av = linha(out, "AVISO ACIONÁVEL: selo por data suspenso em tjsc_juiz")
        ok(em["tjsc_juiz"] == ("INSCRIÇÕES ABERTAS", "2026-11-16")
           and selo_no_html(html, "TJSC — Juiz Substituto") == "INSCRIÇÕES ABERTAS",
           "P2 %s: selo do registro mantido, sem carimbo (%r)" % (rotulo, em["tjsc_juiz"]))
        ok("25/11" in av and "26/11" in av and "INSCRIÇÕES ABERTAS" in av and " … " not in av,
           "P2 %s: AVISO ACIONÁVEL com as duas datas: %s" % (rotulo, av or out))
        ok("selo por data: tjsc_juiz" not in out and "MONTAGEM: OK COM AVISOS" in out
           and linha(out, "CAMINHO: ").endswith("email-com-avisos.html"), "P2 %s: sem recalculo, corpo com avisos" % rotulo)
        ok("ALERTA: selo por data suspenso em tjsc_juiz" in HELPER_OUT[0]
           and "selo por data: tjsc_juiz" not in HELPER_OUT[0], "P2 %s: o helper suspende igual e avisa: %s"
           % (rotulo, HELPER_OUT[0][-600:]))
        ok(len(out.encode("utf-8")) < 3000, "P2 %s: stdout < 3 KB (%d)" % (rotulo, len(out.encode("utf-8"))))
    # prazos (e linha) corrigidos hoje: sem divergencia, carimbo e selo por data pela data oficial (8 dias: ABERTAS)
    t = pasta_dia("2026-11-18", {"tjsc_juiz": {"linha": linha26, "prazos": next(
        c for c in led["concursos"] if c["id"] == "tjsc_juiz")["prazos"]}}, ledger=led25, banca=banca25)
    out, html, em, lg = montador_e_helper(t)
    concordam(em, lg, "P2 prazos corrigidos")
    ok(em["tjsc_juiz"] == ("INSCRIÇÕES ABERTAS", "2026-11-18") and "suspenso" not in out
       and "suspenso" not in HELPER_OUT[0], "P2 corrigido: carimbo, sem suspensao (%r)" % (em["tjsc_juiz"],))
    # 19/11 sem update: pelo registro seria ENCERRA EM BREVE (6 dias); suspenso, fica o selo do registro
    t = pasta_dia("2026-11-19", {}, ledger=led25, banca=banca25)
    out, html, em, lg = montador_e_helper(t)
    concordam(em, lg, "P2 19/11")
    ok(em["tjsc_juiz"][0] == "INSCRIÇÕES ABERTAS" and linha(out, "AVISO ACIONÁVEL: selo por data suspenso em tjsc_juiz"),
       "P2 19/11: suspenso (%r)" % (em["tjsc_juiz"],))


@teste
def t_r2_selo_acionavel_e_rebaixamento():
    """MON 3/14: "contradiz o selo por data" e "prorrogação não confirmada" sao acionaveis. MON 13: o rebaixamento
    para PENDÊNCIA DE VERIFICAÇÃO sai sem "(automático; não escreva o selo)" e com o que fazer inteiro."""
    ok(M.ACIONAVEL.search("ledger_updates.concursos.x.selo: 'INSCRIÇÕES ABERTAS' escrito hoje contradiz o selo por "
                          "data 'ENCERRA EM BREVE'") and M.ACIONAVEL.search("selo por data: x A → B: prorrogação não "
                                                                            "confirmada — confirme"), "regex ACIONAVEL")
    ok(not M.ACIONAVEL.search("selo por data: x INSCRIÇÕES ABERTAS → ENCERRA EM BREVE: fim das inscrições em 7 dias "
                              "(26/11) (automático; não escreva o selo)"), "selo por data comum segue informativo")

    def sem_tjap(b):
        b["concursos"] = [c for c in b["concursos"] if "tjap_juiz" not in c["coberto"]]
    t = pasta_dia("2026-11-19", {}, banca=sem_tjap)
    out, html, em, lg = montador_e_helper(t)
    concordam(em, lg, "19/11 sem a banca do TJAP")
    av = linha(out, "AVISO ACIONÁVEL: selo por data: tjap_juiz")
    ok(av.startswith("AVISO ACIONÁVEL: selo por data: tjap_juiz ENCERRA EM BREVE → PENDÊNCIA DE VERIFICAÇÃO: o fim "
                     "das inscrições (18/11) já passou e a banca oficial não foi lida hoje"), "rebaixamento acionavel: %s" % av)
    ok("não escreva o selo" not in av and " … " not in av and "encerradas → selo INSCRIÇÕES ENCERRADAS" in av
       and "prorrogadas →" in av, "rebaixamento sem o sufixo e sem corte: %s" % av)
    ok("MONTAGEM: OK COM AVISOS" in out and linha(out, "CAMINHO: ").endswith("email-com-avisos.html")
       and selo_no_html(html, "TJAP — Juiz de Direito Substituto") == "PENDÊNCIA DE VERIFICAÇÃO", "corpo com avisos")
    ok(len(out.encode("utf-8")) < 3000, "stdout < 3 KB com a linha inteira (%d)" % len(out.encode("utf-8")))
    # prorrogacao escrita com o selo de antes (INSCRIÇÕES ABERTAS) e o novo fim a 2 dias: acionavel, nao OK
    prorrog = {"tjap_juiz": {"prazos": [{"data": "2026-11-21", "evento": "fim das inscrições, 16h (prorrogado)",
                                         "confirmado": True},
                                        {"data": "2027-01-24", "evento": "prova objetiva (prevista)", "confirmado": True}],
                             "selo": "INSCRIÇÕES ABERTAS"}}
    t = pasta_dia("2026-11-19", prorrog)
    out, html, em, lg = montador_e_helper(t)
    concordam(em, lg, "19/11 prorrogacao")
    ok("AVISO ACIONÁVEL: ledger_updates.concursos.tjap_juiz.selo: 'INSCRIÇÕES ABERTAS' escrito hoje contradiz o selo "
       "por data 'ENCERRA EM BREVE'" in out and "MONTAGEM: OK COM AVISOS" in out, "prorrogacao: contradiz acionavel")


@teste
def t_r2_temas_rg_no_resolvido():
    """INF-rev-1c: o item RG resolvido grava os temas publicados ("temas"); o escrito no arquivo e ignorado."""
    ev = {r["id"]: dict(r, _fonte="informativo") for r in fx("informativos-1711.json")}
    r = M.resolver({"ref": "rg394", "destaques": {"excluir": [1]}, "temas": ["999"]}, ev, [], [], None)
    esperado = [d["tema"] for i, d in enumerate(ev["rg394"]["itens"]) if i != 1]
    ok(r["temas"] == esperado and "106" not in r["temas"] and "1.483" in r["temas"], "temas: %s" % r.get("temas"))
    ok("temas" not in M.resolver({"ref": "stf1233"}, ev, [], [], None), "so RG grava temas")
    t = preparar_pasta("1711")
    rc, out, _ = rodar("1711", t)
    res = json.load(open(os.path.join(t, "execucao.resolvido.json"), encoding="utf-8"))
    rg = next(i for i in res["items"] if i.get("ref") == "rg394")
    ok(rc == 0 and rg.get("temas") and all(isinstance(x, str) for x in rg["temas"]), "resolvido com temas")


@teste
def t_r2_baixos():
    # RG: a "ordem" vale dentro de cada estagio; a que pede outra ordem ganha AVISO
    ev = {r["id"]: dict(r, _fonte="informativo") for r in fx("informativos-1711.json")}
    av = []
    r = M.resolver({"ref": "rg394", "destaques": {"ordem": [5, 0], "excluir": [7, 1]}}, ev, [], av, None)
    temas = [re.search(r"Tema ([\d.]+)", x).group(1) for x in r["destaques_texto"]]
    ok(temas.index("1.016") < temas.index("1.493") and "106" not in temas and "1.490" not in " ".join(r["destaques_texto"]),
       "RG: ordem dentro do estagio, exclusao ok: %s" % temas[:5])
    ok(len(av) == 1 and "na Repercussão Geral a \"ordem\" vale dentro de cada estágio" in av[0]
       and "Tema 1.493 sai depois do Tema 1.016" in av[0], "AVISO da ordem na RG: %s" % av)
    av = []
    M.resolver({"ref": "rg394", "destaques": {"ordem": [0, 5]}}, ev, [], av, None)
    ok(av == [], "ordem compativel com os estagios: sem AVISO")
    # apoio: edicao sem conteudo nao vira "estao em Informativos"
    vazia = [{"ref": "stf1240", "titulo": "Informativo STF nº 1240", "sem_conteudo": True}]
    t = M.apoio_calculado("STF Jurisprudência", {"Informativos": vazia})
    ok("estão em 📚 Informativos" not in t and "não abriu" in t and "Informativo STF nº 1240" in t, "STF sem conteudo: %s" % t)
    t = M.apoio_calculado("STF Jurisprudência", {"Informativos": vazia + [
        {"ref": "rg397", "titulo": "Repercussão Geral em Pauta nº 397", "herdada": True}]})
    ok(t.startswith("Sem Repercussão Geral em Pauta nova") and "nº 1240" not in t and "nº 397" in t, "so a com conteudo: %s" % t)
    t = M.apoio_calculado("STF Jurisprudência", {"Informativos": [
        {"ref": "rg398", "titulo": "Repercussão Geral em Pauta nº 398", "sem_conteudo": True},
        {"ref": "stf1236", "titulo": "Informativo STF nº 1236"}]})
    ok(t.startswith("Teses e julgados do STF desta edição estão em") and "nº 398" not in t,
       "RG nova sem conteudo nao vira 'sem RG nova': %s" % t)
    stj = [{"ref": "stj910", "titulo": "Informativo STJ nº 910", "sem_conteudo": True}]
    t = M.apoio_calculado("STJ Jurisprudência", {"Informativos": stj})
    ok(t.startswith("Sem teses do CodJu na janela; o documento do Informativo STJ nº 910 não abriu"), "STJ: %s" % t)
    ok(M.apoio_calculado("STJ Notícias", {"Informativos": stj}) == "Nenhuma notícia do STJ localizada nesta janela.",
       "STJ Noticias nao aponta edicao vazia")
    # email.suporte escrito a mao: ignorado (o calculado sai), com AVISO
    escrito = {"suporte": "scripts coleta_web, informativos, versiculo e montar_email; informativos.py: STF 1238 (403)"}
    ok(M.suporte_txt({"conjur": "falha"}, escrito) == M.suporte_txt({"conjur": "falha"}, {}), "suporte: sempre o calculado")
    # norm_meta: o resto do meta fica (republicacao, retificacao, veto total, vigencia)
    for m, esperado in (("DOU 13/11 (republicação por incorreção)", "DOU 13/11; republicação por incorreção"),
                        ("DOU 13/11; sanção com veto total", "DOU 13/11; sanção com veto total"),
                        ("DOU 13/11; retificado no DOU 14/11", "DOU 13/11; retificado no DOU 14/11"),
                        ("DOU 13/11, vigência em 90 dias", "DOU 13/11; vigência em 90 dias"),
                        ("ato 12/11/2026; DOU 13/11/2026 (edição extra); com veto — art. 2º",
                         "DOU 13/11 · edição extra; com veto — art. 2º")):
        ok(M.norm_meta(m) == esperado, "norm_meta(%r) = %r" % (m, M.norm_meta(m)))
    # feriado com parenteses no nome: sem parenteses aninhados
    j = fx("janela-1711.json")
    j["feriado_hoje"] = {"data": "2026-12-21", "tipo": "justica_federal", "nome": "Recesso da Justiça Federal (20/12 a 06/01)"}
    t = M.janela_txt(j, "")
    ok(t.endswith("Hoje é feriado na Justiça Federal (Recesso da Justiça Federal, 20/12 a 06/01).") and "((" not in t
       and "))" not in t, "feriado JF: %s" % t[-90:])
    j["feriado_hoje"] = {"data": "2027-02-08", "tipo": "ponto_facultativo", "nome": "Carnaval (segunda-feira)"}
    ok(M.janela_txt(j, "").endswith("Hoje é ponto facultativo (Carnaval, segunda-feira)."), "Carnaval sem aninhar")
    ok(M.tecnico_para_leitor("O Informativo STF 1238 não abriu (403); informativos.py e resolver_jota; erro 404; http 503")
       == ["(403)", "informativos.py", "resolver_jota", "erro 404", "http 503"], "trechos tecnicos")
    ok(M.tecnico_para_leitor("A página do Congresso não respondeu; o Informativo 1238 sai na próxima edição (2026).") == [],
       "linguagem simples: nada")
    # ponta a ponta: suporte escrito, limitacoes e observacoes com codigo -> AVISO informativo (nao acionavel)
    ex = fx("execucao-1711.json")
    ex["email"].update(suporte="Falhas: coleta_web.py http 403", limitacoes="O Informativo STF 1238 não abriu (403).",
                       observacoes=["Boletim lido por gmail_extrair sem erro.", "Página do STJ sem novidade."])
    ex["items"] = [it for it in ex["items"] if it.get("ref") != "c1"]
    t = preparar_pasta("1711", execucao=ex)
    rc, out, _ = rodar("1711", t)
    html = corpo(out)
    ok(rc == 0 and "AVISO: email.suporte ignorado" in out and "coleta_web" not in html.split("Suporte usado")[1],
       "suporte escrito ignorado, com AVISO")
    ok("AVISO: email.limitacoes traz detalhe técnico ao leitor ((403))" in out
       and "AVISO: email.observacoes[0] traz detalhe técnico ao leitor (gmail_extrair)" in out
       and "observacoes[1]" not in out, "AVISO de limitacoes/observacoes tecnicas")
    ok(linha(out, "MONTAGEM: ").startswith("MONTAGEM: OK —"), "esses AVISOs nao sao acionaveis")


# ------------------------------------------------------------------ volta 2 (reteste da volta 1)
def prazos_tjap(fim, tipo=None, evento="fim das inscrições, 16h (prorrogado)"):
    p = {"data": fim, "evento": evento, "confirmado": True}
    if tipo is not None:
        p["tipo"] = tipo
    return [p, {"data": "2027-01-24", "evento": "prova objetiva (prevista)", "confirmado": True, "tipo": "prova"}]


@teste
def t_v2_tipo_contra_evento():
    """ROTINA:59 (reteste): `tipo` 'outro'/'prova' num prazo cujo evento e o fim (ou o inicio) das inscricoes
    desligava o selo por data sem alerta — o e-mail saia INSCRIÇÕES ABERTAS para inscricao que acaba em 2 dias.
    Agora e AVISO ACIONÁVEL `ledger_updates.concursos.<id>.prazos[n].tipo: …` (o tipo nao e trocado: pode ser decisao),
    com o selo que a data daria pela classe do evento; o do helper com o mesmo prefixo tambem e acionavel e nao duplica."""
    pref = "AVISO ACIONÁVEL: ledger_updates.concursos.tjap_juiz.prazos[0].tipo: "
    # 1) a reproducao do reteste: prorrogacao ate 21/11 com tipo 'outro' e o selo de antes (INSCRIÇÕES ABERTAS)
    t = pasta_dia("2026-11-19", {"tjap_juiz": {"prazos": prazos_tjap("2026-11-21", "outro"), "selo": "INSCRIÇÕES ABERTAS",
                                               "fonte": "https://conhecimento.fgv.br/concursos/tjap26"}})
    out, html, em, lg = montador_e_helper(t)
    concordam(em, lg, "19/11 tipo outro")
    av = linha(out, pref)
    ok(av.startswith(pref + "'outro' num prazo cujo evento é o fim das inscrições («fim das inscrições, 16h (prorrogado)»)")
       and "(com 'inscricoes_fim', o selo por data daria 'ENCERRA EM BREVE': fim das inscrições em 2 dias (21/11))" in av
       and av.endswith("escreva tipo 'inscricoes_fim' ou omita o tipo; se não é, aceite o aviso") and " … " not in av,
       "tipo 'outro' x fim das inscricoes: acionavel, com o selo que a data daria: %s" % av)
    ok("MONTAGEM: OK COM AVISOS" in out and linha(out, "CAMINHO: ").endswith("email-com-avisos.html"),
       "tipo 'outro': corpo em email-com-avisos.html")
    ok(out.count("concursos.tjap_juiz.prazos[0].tipo") == 1, "um aviso so por prazo (montador + helper nao duplicam)")
    ok(selo_no_html(html, "TJAP — Juiz de Direito Substituto") == "INSCRIÇÕES ABERTAS",
       "o montador nao troca o tipo nem o selo (o aviso pede a decisao)")
    ok(len(out.encode("utf-8")) < 3000, "stdout < 3 KB (%d)" % len(out.encode("utf-8")))
    # 2) sem selo no update: antes ficava o ENCERRA EM BREVE do registro com o fim HOJE, sem aviso nenhum
    t = pasta_dia("2026-11-19", {"tjap_juiz": {"prazos": prazos_tjap("2026-11-19", "outro")}}, banca=False)
    out, html, em, lg = montador_e_helper(t)
    concordam(em, lg, "19/11 tipo outro sem selo")
    ok("'outro' num prazo cujo evento é o fim das inscrições" in linha(out, pref)
       and "o selo por data daria 'ENCERRA HOJE': fim das inscrições hoje (19/11))" in linha(out, pref)
       and "MONTAGEM: OK COM AVISOS" in out, "sem selo: acionavel, daria ENCERRA HOJE: %s" % linha(out, pref))
    # 3) 'prova' no fim das inscricoes: o selo por data via "prova em 21/11"
    t = pasta_dia("2026-11-19", {"tjap_juiz": {"prazos": prazos_tjap("2026-11-21", "prova")}}, banca=False)
    out, html, em, lg = montador_e_helper(t)
    ok(linha(out, pref).startswith(pref + "'prova' num prazo cujo evento é o fim das inscrições"),
       "tipo 'prova' x fim das inscricoes: acionavel: %s" % linha(out, pref))
    # 4) tipo certo ou omitido: nenhum aviso de tipo; o selo por data funciona (ENCERRA HOJE)
    for tipo in ("inscricoes_fim", None):
        t = pasta_dia("2026-11-19", {"tjap_juiz": {"prazos": prazos_tjap("2026-11-19", tipo)}}, banca=False)
        out, html, em, lg = montador_e_helper(t)
        concordam(em, lg, "19/11 tipo %s" % tipo)
        ok(".prazos[" not in out and em["tjap_juiz"][0] == "ENCERRA HOJE"
           and "AVISO: selo por data: tjap_juiz ENCERRA EM BREVE → ENCERRA HOJE" in out,
           "tipo %r: sem aviso de tipo, selo por data ENCERRA HOJE (%r)" % (tipo, em["tjap_juiz"]))
    # 5) funcao pura: 'outro' legitimo (o evento ja e 'outro'), classes trocadas, remover, prazos invalidos
    regs = {"x": {"id": "x", "selo": "INSCRIÇÕES ABERTAS"}}
    hoje = date(2026, 11, 19)
    for ev in ("inscrição definitiva (2ª fase)", "pagamento da taxa de inscrição até 19/11", "resultado preliminar da prova",
               "homologação das inscrições", "convocação para a prova oral"):
        ok(M.tipo_contra_evento({"x": {"prazos": [{"data": "2026-11-21", "evento": ev, "tipo": "outro",
                                                   "confirmado": True}]}}, regs, hoje, {}) == [],
           "'outro' legitimo sem aviso: %s" % ev)
    a = M.tipo_contra_evento({"x": {"prazos": [{"data": "2026-11-21", "evento": "prova objetiva"},
                                               {"data": "2026-11-20", "evento": "início das inscrições", "tipo": "outro"},
                                               {"data": "2026-12-01", "evento": "fim das inscrições",
                                                "tipo": "inscricoes_inicio"}]}}, regs, hoje, {})
    ok(len(a) == 2 and a[0].startswith("ledger_updates.concursos.x.prazos[1].tipo: 'outro' num prazo cujo evento é o "
                                       "início das inscrições") and "escreva tipo 'inscricoes_inicio'" in a[0]
       and a[1].startswith("ledger_updates.concursos.x.prazos[2].tipo: 'inscricoes_inicio' num prazo cujo evento é o "
                           "fim das inscrições") and all(M.ACIONAVEL.search(x) for x in a), "inicio e classes trocadas: %s" % a)
    ok(M.tipo_contra_evento({"x": {"remover": True, "prazos": [{"evento": "fim das inscrições", "tipo": "outro"}]},
                             "y": {"prazos": "21/11"}, "z": {"prazos": [None, {"evento": "fim das inscrições", "tipo": 3}]}},
                            regs, hoje, {}) == [], "remover, prazos invalidos e tipo fora da lista: nada (o helper da ERRO)")
    novo = M.tipo_contra_evento({"n": {"prazos": [{"data": "2026-11-21", "evento": "fim das inscrições", "tipo": "outro"}]}},
                                {}, hoje, {})
    ok(len(novo) == 1 and "daria" not in novo[0], "sem registro: aviso sem o selo que a data daria")
    # 6) o do helper com o mesmo prefixo e acionavel; para o mesmo prazo fica so o do montador (diz o que a data
    # daria); prazo que so o helper avisou e os demais avisos do helper ficam
    h = ["ledger_updates.concursos.x.prazos[1].tipo: 'outro', mas o evento é de inscrição",
         "ledger_updates.concursos.x.prazos[0].tipo: 'outro' e o evento fala em inscrição",
         "ledger_updates.concursos.x.selo: 'A' escrito hoje contradiz o selo por data 'B'"]
    ok(all(M.ACIONAVEL.search(x) for x in h) and M.sem_tipo_repetido(h, a) == h[1:]
       and M.sem_tipo_repetido(h, []) == h and M.sem_tipo_repetido([], a) == [], "dedup com o aviso do helper")
    ok(not M.ACIONAVEL.search("ledger_updates.concursos.x.prazos: 'linha' fala em 21/11") and
       not M.ACIONAVEL.search("selo por data: x INSCRIÇÕES ABERTAS → ENCERRA EM BREVE: fim das inscrições em 7 dias "
                              "(26/11) (automático; não escreva o selo)"), "regex nao pega outros avisos de concurso")


# ------------------------------------------------------------------ CORE volta 1
@teste
def t_core_prazo_escrito_contra_edital():
    """P3: prazo escrito hoje que contradiz o edital lido hoje (banca de 19/11 com fim 18/11, igual ao registro; o
    orquestrador grava prorrogacao para 21/11 com fonte FGV). Antes passava sem aviso, com o carimbo da banca e o selo
    por data da data escrita. Agora: AVISO ACIONÁVEL no montador, ALERTA no relatorio do helper, sem carimbo e com o
    selo por data suspenso (regra do P2). Sem falso positivo com o update igual ao edital nem sem edital relido."""
    relido = edital_relido("tjap_juiz", "2026-11-18", TRECHO_TJAP, "2026-10-13", "prazo do registro em 18/11")
    prorrog = {"tjap_juiz": {"prazos": prazos_tjap("2026-11-21"), "fonte": "https://conhecimento.fgv.br/concursos/tjap26"}}
    t = pasta_dia("2026-11-19", copy.deepcopy(prorrog), banca=relido)
    out, html, em, lg = montador_e_helper(t)
    concordam(em, lg, "P3 prorrogacao contra o edital")
    av = linha(out, "AVISO ACIONÁVEL: prazo escrito hoje difere do edital lido hoje: tjap_juiz")
    ok(av and "18 de novembro de 2026" in av and "21/11/2026" in av and " × update " in av and " … " not in av,
       "P3: aviso acionavel com edital x update: %s" % (av or out))
    ok("DIVERGE DO REGISTRO em tjap_juiz" not in out, "P3: um aviso so (sem o DIVERGE generico)")
    ok(em["tjap_juiz"] == ("ENCERRA EM BREVE", "2026-11-16") and linha(out, "AVISO ACIONÁVEL: selo por data suspenso "
                                                                            "em tjap_juiz"),
       "P3: sem carimbo e selo por data suspenso (%r)" % (em["tjap_juiz"],))
    ok("ALERTA: prazo escrito hoje difere do edital lido hoje: tjap_juiz" in HELPER_OUT[0]
       and "AVISO: prazo escrito hoje" not in HELPER_OUT[0], "P3: ALERTA no relatorio do helper: %s" % HELPER_OUT[0][-800:])
    ok("MONTAGEM: OK COM AVISOS" in out and len(out.encode("utf-8")) < 3000, "P3: corpo com avisos, stdout < 3 KB")
    # update igual ao edital (18/11): nada de aviso; carimbo e selo por data (banca lida: ENCERRADAS)
    t = pasta_dia("2026-11-19", {"tjap_juiz": {"prazos": prazos_tjap("2026-11-18")}}, banca=relido)
    out, html, em, lg = montador_e_helper(t)
    concordam(em, lg, "P3 update igual ao edital")
    ok("prazo escrito hoje" not in out + HELPER_OUT[0] and "suspenso" not in out + HELPER_OUT[0]
       and "DIVERGE" not in out and em["tjap_juiz"] == ("INSCRIÇÕES ENCERRADAS", "2026-11-19"),
       "P3 sem falso positivo (update = edital): %r" % (em["tjap_juiz"],))
    # edital NAO relido hoje (releitura vazia, sem inscricoes; ou inscricoes de uma releitura que nao e de hoje)
    def sem_releitura(b):
        for c in b["concursos"]:
            if "tjap_juiz" in c["coberto"]:
                c["releitura"] = ""
                c.pop("inscricoes", None)

    def velha(b):
        relido(b)
        for c in b["concursos"]:
            if "tjap_juiz" in c["coberto"]:
                c["releitura"] = ""
    for rotulo, banca in (("sem releitura", sem_releitura), ("inscricoes sem releitura hoje", velha)):
        t = pasta_dia("2026-11-19", copy.deepcopy(prorrog), banca=banca)
        out, html, em, lg = montador_e_helper(t)
        concordam(em, lg, "P3 %s" % rotulo)
        ok("prazo escrito hoje" not in out + HELPER_OUT[0] and "suspenso" not in out + HELPER_OUT[0]
           and em["tjap_juiz"] == ("ENCERRA EM BREVE", "2026-11-19"),
           "P3 %s: sem aviso, carimbo e selo pela data escrita (%r)" % (rotulo, em["tjap_juiz"]))
    ok(M.ACIONAVEL.search("prazo escrito hoje difere do edital lido hoje: x edital \"a\" × update \"b\"")
       and M.ACIONAVEL.search("selo por data suspenso em x: o registro diz"), "regex ACIONAVEL")


@teste
def t_core_resumo_truncado():
    """P5: item do ConJur com "resumo_truncado" (coleta_web.json novo): o resumo termina em "…" (sem ponto) ou e
    omitido se ficar com menos de 40 caracteres. O campo e DERIVADO (o escrito pelo orquestrador e ignorado) e nao
    vai ao resolvido nem ao historico. coleta_web.json antigo (sem o campo): como antes."""
    col = fx("coleta_web-1711.json")
    for b in col:
        for x in b["itens"]:
            if x.get("id") == "c1":
                x["resumo"] = x["resumo"] + " e o"
                x["resumo_truncado"] = True
            elif x.get("id") == "c7":
                x["resumo"] = "TJ-SP absolveu um homem acusado de..."
                x["resumo_truncado"] = True
    ex = fx("execucao-1711.json")
    for it in ex["items"]:
        if it.get("ref") == "c1":
            it["resumo_truncado"] = False          # o orquestrador nao decide isto
    t = preparar_pasta("1711", execucao=ex)
    json.dump(col, open(os.path.join(t, "coleta_web.json"), "w", encoding="utf-8"), ensure_ascii=False)
    rc, out, err = rodar("1711", t)
    html = corpo(out)
    ok(rc == 0, "montagem: %s %s" % (out[-400:], err[-400:]))
    ok("é inconstitucional e o…" in html and "é inconstitucional e o." not in html and "e o….</" not in html,
       "c1: termina em reticencias, sem ponto")
    ok("TJ-SP absolveu" not in html and "Condenação por embriaguez ao volante exige prova" in html,
       "c7: resumo curto truncado omitido (o item fica)")
    ok("pendências fiscais ou financeiras." in html, "c8 (sem o campo): ponto final como antes")
    res = json.load(open(os.path.join(t, "execucao.resolvido.json"), encoding="utf-8"))
    ok(not any("resumo_truncado" in it for it in res["items"]), "resumo_truncado fora do resolvido (e do historico)")
    # o orquestrador copiou o resumo cortado no item: tambem sai com reticencias; texto proprio: o dele, com ponto
    ex = fx("execucao-1711.json")
    for it in ex["items"]:
        if it.get("ref") == "c1":
            it["resumo"] = next(x for b in col for x in b["itens"] if x.get("id") == "c1")["resumo"]
        elif it.get("ref") == "c7":
            it["resumo"] = "TJ-SP absolveu motociclista por falta de prova de que ele conduzia"
    t = preparar_pasta("1711", execucao=ex)
    json.dump(col, open(os.path.join(t, "coleta_web.json"), "w", encoding="utf-8"), ensure_ascii=False)
    rc, out, err = rodar("1711", t)
    html = corpo(out)
    ok("é inconstitucional e o…" in html and "TJ-SP absolveu motociclista por falta de prova de que ele conduzia." in html,
       "copia do resumo cortado: reticencias; resumo proprio: o dele")
    ev = {"c9": {"_fonte": "conjur", "id": "c9", "tipo": "noticia", "titulo": "T", "url": "https://conjur.com.br/x/",
                 "data": "2026-11-16", "quando": "2026-11-16T10:00:00-03:00", "situacao": "NOVA",
                 "resumo": "Texto qualquer com mais de quarenta caracteres, cortado no meio,", "resumo_truncado": True}}
    r = M.resolver({"ref": "c9"}, ev, [], [], None)
    ok(r["resumo"] == "Texto qualquer com mais de quarenta caracteres, cortado no meio…" and "resumo_truncado" not in r,
       "pontuacao final tirada antes das reticencias: %r" % r.get("resumo"))
    ev["c9"]["resumo_truncado"] = False
    ok(M.resolver({"ref": "c9"}, ev, [], [], None)["resumo"].endswith("no meio,"), "sem o campo: intacto")


@teste
def t_camara_site_por_ref():
    """Agencia Camara lida no site pelo coleta_web.py (cam1, cam2): o ref vira item de Planalto/Legislacao com
    selo de fonte oficial alternativa, link, data/hora e chave — nada redigitado pelo orquestrador."""
    ex = fx(CENARIOS["1711"]["execucao"])
    ex["items"].insert(0, {"ref": "cam1"})
    ex["items"].insert(1, {"ref": "cam2", "impacto": "Auxílio prorrogado por medida provisória"})
    ex.setdefault("source_status", {})["camara_noticias"] = "ok"
    t = preparar_pasta("1711", execucao=ex)
    cw = json.load(open(os.path.join(t, "coleta_web.json"), encoding="utf-8"))
    cw.append({"fonte": "camara_noticias", "http": 200, "paginas": 3, "lidas": 29, "na_janela": 20, "resto": 18,
               "duvidosos": [], "completa": True, "itens": [
                   {"situacao": "NOVA", "marca": "PLENARIO", "id": "cam1", "retranca": "Política",
                    "titulo": "Câmara aprova criação da Política Nacional de Residência em Saúde",
                    "url": "https://www.camara.leg.br/noticias/1317771-camara-aprova-criacao-da-politica",
                    "quando": "2026-11-16T20:53:00-03:00"},
                   {"situacao": "NOVA", "marca": "LEI", "id": "cam2", "retranca": "Economia",
                    "titulo": "Medida provisória prorroga Auxílio Gás do Povo até 2031",
                    "url": "https://www.camara.leg.br/noticias/1317002-medida-provisoria-prorroga",
                    "quando": "2026-11-16T11:57:00-03:00"}]})
    json.dump(cw, open(os.path.join(t, "coleta_web.json"), "w", encoding="utf-8"), ensure_ascii=False)
    rc, out, err = rodar("1711", t)
    ok(rc == 0 and linha(out, "MONTAGEM: OK"), "montagem com refs da Agência Câmara: rc=%s %s %s" % (rc, out[-600:], err[-300:]))
    if rc != 0:
        return
    c = corpo(out)
    sec = c.split("Planalto — Resenha Diária")[1].split("STF — Notícias")[0]
    ok("Câmara aprova criação da Política Nacional de Residência em Saúde" in sec
       and 'href="https://www.camara.leg.br/noticias/1317771-camara-aprova-criacao-da-politica"' in sec
       and "CONFIRMADO POR FONTE OFICIAL ALTERNATIVA" in sec and "Agência Câmara — Plenário, sanções e vetos" in sec
       and "16/11 20:53" in sec and "Medida provisória prorroga Auxílio Gás do Povo até 2031" in sec
       and "Auxílio prorrogado por medida provisória" in sec, "itens da Agência Câmara na seção Planalto: %s" % sec[:900])
    ok("Agência Câmara (site)" in c.split("Fontes oficiais consultadas")[1].split("Fontes secundárias")[0],
       "Agência Câmara (site) nas fontes oficiais consultadas")
    res = json.load(open(os.path.join(t, "execucao.resolvido.json"), encoding="utf-8"))
    cam = [i for i in res["items"] if (i.get("chave") or "").startswith("agencia-camara|")]
    ok(len(cam) == 2 and cam[0]["chave"] == "agencia-camara|ato|%s|2026|2026-11-16" % M.slug(cam[0]["titulo"], 56)
       and cam[0]["data"] == "2026-11-16" and cam[0]["url"].startswith("https://www.camara.leg.br/noticias/1317771")
       and cam[0]["categoria"] == "Planalto/Legislação", "resolvido: chave, data, url e categoria: %s" % cam)


@teste
def t_waf_segunda_tentativa_insiste_e_guarda():
    """17/11/2026: o Informativo STF 1237 abriu na 1a rodada do montador, deu 403 nas seguintes e o e-mail
    saiu com "Conteudo nao acessivel". A segunda tentativa insiste e o PDF aberto fica no cache da execucao."""
    import informativos as I
    tmp = os.environ["ROBOZINHO_TMP"]
    velhos = (I.baixar, I.pdf_texto, I.dormir, os.environ.get("ROBOZINHO_INF_CACHE"))
    texto = open(os.path.join(FIX_INF, "stf1233-layout.txt"), encoding="utf-8").read()
    pedidos = []
    respostas = [(403, b"<html>Error 403</html>")] * 3 + [(200, b"%PDF-1.4 fixture")]

    def baixar(url):
        pedidos.append(url)
        return respostas.pop(0) if len(respostas) > 1 else respostas[0]

    I.baixar, I.pdf_texto, I.dormir = baixar, (lambda dados, layout: texto), (lambda s: None)
    os.environ["ROBOZINHO_INF_CACHE"] = "1"
    with open(os.path.join(tmp, "janela.json"), "w") as f:
        json.dump({"execution_id": "2026-11-17-7h"}, f)
    try:
        itens = [{"ref": "stf9237", "data": "2026-11-16", "url": "http://portal.stf.jus.br/x"}, {"ref": "c1"}]
        ev, avisos = {"stf9237": {"ok": False, "estado": "indeterminado"}, "c1": {"ok": True}}, []
        fora = M.segunda_tentativa(itens, ev, avisos)
        ok(ev["stf9237"].get("ok") and len(ev["stf9237"]["itens"]) == 4 and len(pedidos) == 4 and fora == set()
           and any("stf9237: documento abriu na segunda tentativa — 4 destaques" in a for a in avisos),
           "segunda tentativa insiste até abrir (4 pedidos): %s / %s" % (len(pedidos), avisos))
        respostas[:] = [(403, b"<html>Error 403</html>")]
        del pedidos[:]
        ev2, avisos2 = {"stf9237": {"ok": False, "estado": "indeterminado"}}, []
        M.segunda_tentativa(itens, ev2, avisos2)
        ok(ev2["stf9237"].get("ok") and ev2["stf9237"].get("cache") is True and pedidos == []
           and ev2["stf9237"]["itens"] == ev["stf9237"]["itens"],
           "rodada seguinte do montador lê o PDF do cache, sem rede: %s" % pedidos)
        ev3, avisos3 = {"stf9238": {"ok": False, "estado": "indeterminado"}}, []
        M.segunda_tentativa([{"ref": "stf9238"}], ev3, avisos3)
        ok(not ev3["stf9238"].get("ok") and len(pedidos) == I.MAX_TENTATIVAS_MONTADOR,
           "documento que não abre: MAX_TENTATIVAS_MONTADOR pedidos e segue sem destaques: %s" % len(pedidos))
    finally:
        I.baixar, I.pdf_texto, I.dormir = velhos[:3]
        if velhos[3] is None:
            os.environ.pop("ROBOZINHO_INF_CACHE", None)
        else:
            os.environ["ROBOZINHO_INF_CACHE"] = velhos[3]
        os.unlink(os.path.join(tmp, "janela.json"))
        shutil.rmtree(os.path.join(tmp, "informativos-cache"), ignore_errors=True)


# ------------------------------------------------------------------ frente 'montador' (21/11/2026)
def secao_html(html, titulo, proximo):
    return html.split(titulo)[1].split(proximo)[0]


def quadro_leitor(html):
    return html.split("📋 Observações de verificação")[1]


@teste
def t_mon_pendencias_quadro():
    """verified[3]: pendencia sem concurso vai ao leitor so com faixa 'ativa', texto mudado hoje ou na 1a execucao da
    semana; nunca quando repete item/limitacao/observacao da edicao nem com texto operacional (decisao 5)."""
    base = {"id": "p1", "texto": "Concurso de cartórios do TJXX: resultado da prova oral esperado para dezembro",
            "faixa": "longo_prazo"}
    q = {"antes": {"p1": dict(base)}, "primeira": False, "textos": []}
    ok(not M.pendencia_no_quadro(dict(base), q), "longo_prazo igual, fora da 1a da semana: fora do quadro")
    ok(M.pendencia_no_quadro(dict(base, faixa="ativa"), q), "ativa: no quadro")
    ok(M.pendencia_no_quadro(dict(base, texto=base["texto"] + "; edital de convocação publicado"), q),
       "texto mudado hoje: no quadro")
    ok(M.pendencia_no_quadro(dict(base, _nova=True), dict(q, antes={})), "criada hoje: no quadro")
    ok(M.pendencia_no_quadro(dict(base), dict(q, primeira=True)), "1a execucao da semana: no quadro")
    oper = dict(base, faixa="ativa", texto="PUSH Planalto: resenha de 19/11 recebida; manter 1 sonda por dia.")
    ok(not M.pendencia_no_quadro(oper, q), "texto operacional (sonda) nunca vai ao leitor")
    ok(not M.pendencia_no_quadro(dict(base, faixa="ativa", texto="Falha do coleta_web.py com http 403"), q),
       "texto tecnico (script, http) nunca vai ao leitor")
    ok(M.pendencia_no_quadro(dict(base, faixa="ativa", texto="Execução fiscal: STJ julga tema de protocolo"), q),
       "'execução' e 'protocolo' soltos sao vocabulario juridico")
    master = ("Caso Master: em 18/11 o diretor-geral da PF entregou a Fachin os relatórios sobre menções a ministros do "
              "STF no celular de Daniel Vorcaro; Fachin os enviará sob sigilo à PGR, que terá 15 dias.")
    fofoca = ("PGR terá 15 dias para analisar relatórios da PF sobre ministros no caso Master. Fachin enviou à PGR, "
              "sob sigilo, os relatórios da PF sobre menções a ministros no celular de Daniel Vorcaro.")
    ok(not M.pendencia_no_quadro(dict(base, faixa="ativa", texto=master), dict(q, textos=[fofoca])),
       "pendencia que repete item da edicao (Caso Master na Fofoquinha) fica fora")
    ok(M.pendencia_no_quadro(dict(base, faixa="ativa", texto=master), dict(q, textos=["STF julga ICMS sobre energia."])),
       "sem item parecido: fica")
    ok(M.rotulo_pendencia("PUSH Planalto: resenha de 19/11") == "PUSH Planalto"
       and M.rotulo_pendencia("Sem dois-pontos; segundo trecho") == "Sem dois-pontos", "rotulo da pendencia")
    # ponta a ponta (17/11, terca): as duas pendencias sem concurso sao longo_prazo e nao mudaram -> fora do quadro;
    # o historico continua com a lista inteira
    t = preparar_pasta("1711")
    rc, out, err = rodar("1711", t)
    html = corpo(out)
    q17 = quadro_leitor(html)
    ok(rc == 0 and "PUSH Planalto: resenhas" not in q17 and "Caso Master" not in q17, "17/11: quadro sem as longo_prazo")
    res = json.load(open(os.path.join(t, "execucao.resolvido.json"), encoding="utf-8"))
    ok(len(res.get("pendencias") or []) == len(fx("ledger-1611.json")["pendencias_vivas"]),
       "execucao.pendencias segue com a lista inteira (contadores e historico)")
    # segunda-feira (1a da semana): o Caso Master volta; o PUSH (operacional) nunca
    j = fx("janela-1711.json")
    j["primeira_semana"] = True
    t = preparar_pasta("1711", janela=j)
    rc, out, _ = rodar("1711", t)
    q17 = quadro_leitor(corpo(out))
    ok(rc == 0 and "Caso Master: Folha (13/11)" in q17 and "PUSH Planalto: resenhas" not in q17,
       "1a da semana: Caso Master no quadro, PUSH Planalto (manter 1 sonda) fora")
    # texto reescrito hoje: volta no mesmo dia
    ex = fx("execucao-1711.json")
    ex["ledger_updates"] = {"pendencias": {"crise_institucional_stf_pgr_acompanhar": {
        "texto": "Caso Master: a PGR recebeu os relatórios da PF em 18/11 e tem 15 dias para se manifestar."}}}
    t = preparar_pasta("1711", execucao=ex)
    rc, out, _ = rodar("1711", t)
    ok(rc == 0 and "a PGR recebeu os relatórios da PF em 18/11" in quadro_leitor(corpo(out)),
       "texto mudado hoje: no quadro (%s)" % (out[-300:] if rc else ""))


@teste
def t_mon_alvo_nao_vale_para_legislacao():
    """verified[2]: 'alvo ~10' nunca em Planalto/Legislação (secao central: entra completa); Midia continua."""
    ex = fx("execucao-1711.json")
    for n in range(13):
        ex["items"].insert(0, {"categoria": "Planalto/Legislação", "status": "CONFIRMADO POR FONTE OFICIAL",
                               "titulo": "Lei nº %d, de 16/11/2026" % (99000 + n), "data": "2026-11-16",
                               "meta": "DOU 17/11", "url": "https://www.planalto.gov.br/l%d.htm" % n,
                               "resumo": ("Abre ao Orçamento Fiscal da União crédito suplementar no valor de R$ %d,00."
                                          % (n + 1)) if n < 10 else "Institui a Semana Nacional %d." % n,
                               "impacto": "" if n < 10 else "Data comemorativa"})
    t = preparar_pasta("1711", execucao=ex)
    rc, out, _ = rodar("1711", t)
    html = corpo(out)
    plan = secao_html(html, "Planalto — Resenha Diária", "STF — Notícias")
    ok(rc == 0 and "AVISO: Planalto/Legislação com" not in out and "alvo" not in linha(out, "AVISO: Planalto"),
       "sem 'alvo ~10' para Planalto/Legislação")
    ok(all(("Lei nº %d" % (99000 + n)) in plan for n in range(13)), "os 13 atos saem")
    ok(all(plan.index("Lei nº %d" % (99000 + n)) > plan.index("Atos de rotina") for n in range(10))
       and all(plan.index("Lei nº %d" % (99000 + n)) < plan.index("Atos de rotina") for n in range(10, 13)),
       "creditos depois de 'Atos de rotina', o resto antes")
    # Midia (apoio) segue com o alvo, em tom de aviso comum (nao pede rodada sozinho)
    midia = [{"categoria": "Mídia", "titulo": "Matéria de teste número %d sobre tema distinto %d" % (n, n * 7),
              "fonte": "ConJur", "url": "https://www.conjur.com.br/2026-nov-17/teste-%d/" % n, "data": "2026-11-17"}
             for n in range(13)]
    erros, avisos, _ = M.preparar({"items": midia, "email": {}}, fx("janela-1711.json"), fx("ledger-1611.json"), {}, {},
                                  {"historico": os.path.join(FIX, "historico.json"), "bancas": "/inexistente",
                                   "fontes_status": "/inexistente"})
    ok(any(a.startswith("Mídia com 13 itens (alvo ~10): numa nova rodada") for a in avisos)
       and not M.ACIONAVEL.search(next(a for a in avisos if a.startswith("Mídia com"))),
       "Midia: alvo como aviso comum (%s)" % [a for a in avisos if "alvo" in a])


ROTINA_20_11 = [
    "Altera o art. 4º da Lei nº 15.346, de 14 de janeiro de 2026, que estima a receita e fixa a despesa da União para o "
    "exercício financeiro de 2026.",
    "Altera a Lei nº 15.321, de 31 de dezembro de 2025, que dispõe sobre as diretrizes para a elaboração e a execução da "
    "Lei Orçamentária de 2026.",
    "Altera o Anexo V à Lei nº 15.346, de 14 de janeiro de 2026, que estima a receita e fixa a despesa da União para o "
    "exercício financeiro de 2026.",
]
TITULOS_18_11 = ["Deputados aprovam crédito de R$ 6,6 bi para pagar subvenção aos combustíveis",
                 "Câmara aprova crédito de R$ 925 milhões para prevenir efeitos do El Niño",
                 "Câmara aprova crédito extra de R$ 360 milhões para ações de defesa civil"]


@teste
def t_mon_rotina_orcamento():
    """verified[22]: LOA/LDO/PPA, credito em valor e lei de materia PLN vao para 'Atos de rotina' (ementa inteira);
    linha de credito, consignado e Credito do Trabalhador nao."""
    for em in ROTINA_20_11:
        ok(M.eh_rotina({"titulo": "Lei nº 15.541, de 18/11/2026", "resumo": em}), "rotina: %s" % em[:60])
    for tit in TITULOS_18_11:
        ok(M.eh_rotina({"titulo": tit}), "rotina: %s" % tit)
    ok(M.eh_rotina({"titulo": "Lei nº 1", "resumo": "Dispõe sobre o Plano Plurianual da União para 2028-2031."}), "PPA")
    for tit in ("Câmara aprova crédito consignado para trabalhadores do setor privado",
                "Câmara aprova MP que cria linha de crédito de R$ 30 bilhões para exportadores",
                "Senado aprova crédito do trabalhador", "MP abre linhas de crédito de R$ 5 bi para pequenas empresas"):
        ok(not M.eh_rotina({"titulo": tit}), "nao rotina: %s" % tit)
    ev = {"lei1": {"_fonte": "congresso_leis", "numero": "15531", "tipo": "Lei", "data_ato": "18/11/2026",
                   "dou": "19/11/2026", "ementa": "Altera a Lei nº 14.133, de 1º de abril de 2021, para dispor sobre x.",
                   "materia": "PLN 2/2026", "veto": "", "url": "https://legis.senado.leg.br/norma/1",
                   "chave": "planalto|lei|15531|2026|2026-11-18", "id": "lei1"},
          "lei2": {"_fonte": "congresso_leis", "numero": "15532", "tipo": "Lei", "data_ato": "18/11/2026",
                   "dou": "19/11/2026", "ementa": "Altera o Decreto-Lei nº 2.848 (Código Penal) para tipificar x.",
                   "materia": "PL 10/2026", "veto": "", "url": "https://legis.senado.leg.br/norma/2",
                   "chave": "planalto|lei|15532|2026|2026-11-18", "id": "lei2"}}
    r1, r2 = M.resolver({"ref": "lei1"}, ev, []), M.resolver({"ref": "lei2"}, ev, [])
    ok(r1.get("_pln") is True and r2.get("_pln") is False, "_pln pela materia")
    ok("_pln" not in M.limpar_para_gravar({"items": [r1]})["items"][0], "_pln nao vai ao resolvido")
    ex = fx("execucao-1711.json")
    ex["items"][:0] = [{"ref": "lei2"}, {"ref": "lei1"}]
    t = preparar_pasta("1711", execucao=ex)
    cw = json.load(open(os.path.join(t, "coleta_web.json"), encoding="utf-8"))
    cw.append({"fonte": "congresso_leis", "itens": [dict(e, situacao="NOVA") for e in ev.values()]})
    json.dump(cw, open(os.path.join(t, "coleta_web.json"), "w", encoding="utf-8"), ensure_ascii=False)
    rc, out, err = rodar("1711", t)
    plan = secao_html(corpo(out), "Planalto — Resenha Diária", "STF — Notícias") if rc == 0 else ""
    ok(rc == 0 and plan.index("Lei nº 15.532") < plan.index(M.SUBTITULO_ROTINA) < plan.index("Lei nº 15.531")
       and "para dispor sobre x." in plan, "lei PLN de ementa atipica na rotina, com a ementa inteira (%s)"
       % (out + err)[-300:])


RESENHA_20_11 = "Resenha Diária PUSH Legislação - 19/11/2026 · recebida 19/11 10:37"


@teste
def t_mon_resenha_no_ref():
    """verified[24]: `resenha` num ref de lei/MPV do Congresso da o grupo, a fonte e o selo oficial do PUSH."""
    ev = {"lei15541": {"_fonte": "congresso_leis", "numero": "15541", "tipo": "Lei", "data_ato": "18/11/2026",
                       "dou": "19/11/2026", "ementa": ROTINA_20_11[0], "materia": "PLN 18/2026", "veto": "",
                       "url": "https://legis.senado.leg.br/norma/44447000",
                       "chave": "planalto|lei|15541|2026|2026-11-18", "id": "lei15541"},
          "mpv1400": {"_fonte": "congresso_mpv", "numero": "1400", "ano": "2026", "dou": "19/11/2026",
                      "ementa": "Dispõe sobre x.", "url": "https://www.congressonacional.leg.br/mpv1400",
                      "chave": "planalto|mpv|1400|2026|2026-11-19", "id": "mpv1400"}}
    avisos = []
    r = M.resolver({"ref": "lei15541", "resenha": RESENHA_20_11}, ev, [], avisos)
    ok(r["grupo"] == "Resenha Diária PUSH Legislação de 19/11 (recebida em 19/11, 10h37)" and r["fonte"] == "PUSH Planalto"
       and r["status"] == "CONFIRMADO POR FONTE OFICIAL" and r["chave"] == "planalto|lei|15541|2026|2026-11-18"
       and not avisos, "ref + resenha: grupo, fonte e selo do PUSH; a chave nao muda (%s)" % r)
    r = M.resolver({"ref": "lei15541"}, ev, [])
    ok(r["status"] == "CONFIRMADO POR FONTE OFICIAL ALTERNATIVA" and r["fonte"] == "Congresso Nacional"
       and r["grupo"] == "Congresso Nacional — últimas leis publicadas", "sem resenha: pagina do Congresso")
    r = M.resolver({"ref": "lei15541", "resenha": RESENHA_20_11, "grupo": "Meu grupo", "status": "PENDÊNCIA DE "
                    "VERIFICAÇÃO"}, ev, [])
    ok(r["grupo"] == "Meu grupo" and r["status"] == "PENDÊNCIA DE VERIFICAÇÃO", "grupo/status escritos vencem")
    r = M.resolver({"ref": "mpv1400", "resenha": RESENHA_20_11, "fonte": "PUSH Planalto (edição extra)"}, ev, [])
    ok(r["grupo"].startswith("Resenha Diária PUSH Legislação de 19/11") and r["fonte"] == "PUSH Planalto (edição extra)"
       and r["status"] == "CONFIRMADO POR FONTE OFICIAL", "MPV + resenha; fonte escrita vence")
    avisos = []
    r = M.resolver({"ref": "lei15541", "resenha": "e-mail qualquer"}, ev, [], avisos)
    ok(r["grupo"] == "Congresso Nacional — últimas leis publicadas" and any("resenha\" sem data" in a for a in avisos),
       "resenha irreconhecivel: AVISO e fica a base")
    # ponta a ponta: o cabecalho do grupo e o do PUSH; o historico grava a fonte PUSH Planalto
    ex = fx("execucao-1711.json")
    ex["items"].insert(0, {"ref": "lei15541", "resenha": RESENHA_20_11})
    t = preparar_pasta("1711", execucao=ex)
    cw = json.load(open(os.path.join(t, "coleta_web.json"), encoding="utf-8"))
    cw.append({"fonte": "congresso_leis", "itens": [dict(ev["lei15541"], situacao="NOVA")]})
    json.dump(cw, open(os.path.join(t, "coleta_web.json"), "w", encoding="utf-8"), ensure_ascii=False)
    rc, out, err = rodar("1711", t)
    plan = secao_html(corpo(out), "Planalto — Resenha Diária", "STF — Notícias") if rc == 0 else ""
    res = json.load(open(os.path.join(t, "execucao.resolvido.json"), encoding="utf-8")) if rc == 0 else {"items": []}
    lei = next((i for i in res["items"] if i.get("ref") == "lei15541"), {})
    ok(rc == 0 and "CONFIRMADO POR FONTE OFICIAL</b> <span style=\"font-size:12px;color:#5a6773\">— Resenha Diária PUSH "
       "Legislação de 19/11 (recebida em 19/11, 10h37)." in plan and "Congresso Nacional — últimas" not in plan
       and lei.get("fonte") == "PUSH Planalto" and lei.get("status") == "CONFIRMADO POR FONTE OFICIAL",
       "e-mail e resolvido com a atribuicao do PUSH (%s)" % (out + err)[-300:])


def ctx_1811(upd):
    led = fx("ledger-1611.json")
    j = fx("janela-1711.json")
    j.update(data="2026-11-18", execution_id="2026-11-18-7h", execucao_anterior="2026-11-17-7h")
    return M.estado_concursos({"ledger_updates": {"concursos": upd}}, j, led,
                              {"historico": os.path.join(FIX, "historico.json"), "bancas": "/inexistente"}, []), led, j


@teste
def t_mon_movimento_falso():
    """verified[28]: ledger_updates.concursos.<id>.movimento = false grava a linha sem 'Atualizado hoje', sem fundo
    creme, sem item 'atualizado' e sem mudar o mudou_em; o campo nao vai ao registro."""
    nova = fx("ledger-1611.json")["concursos"][0]["linha"] + "; buscas devolvem o ciclo anterior, sem fato novo"
    ctx, led, j = ctx_1811({"tjrs_juiz": {"linha": nova, "movimento": False, "verificado_em": "2026-11-18"}})
    reg = next(c for c in ctx["regs"] if c["id"] == "tjrs_juiz")
    antes = next(c for c in led["concursos"] if c["id"] == "tjrs_juiz")
    ok(reg["linha"] == nova and "movimento" not in reg, "linha gravada, sem o campo movimento")
    ok("tjrs_juiz" not in ctx["alterados"] and reg.get("mudou_em") != "2026-11-18"
       and (not antes.get("mudou_em") or reg.get("mudou_em") == antes.get("mudou_em")), "nao e alterado; mudou_em mantido")
    html = M.linha_concurso(reg, date(2026, 11, 18), ctx["novos"], ctx["alterados"], 0)
    ok("Atualizado hoje" not in html and "#fdf6e9" not in html, "sem 'Atualizado hoje' nem fundo creme")
    ctx2, _, _ = ctx_1811({"tjrs_juiz": {"linha": nova, "verificado_em": "2026-11-18"}})
    reg2 = next(c for c in ctx2["regs"] if c["id"] == "tjrs_juiz")
    ok("tjrs_juiz" in ctx2["alterados"] and reg2["mudou_em"] == "2026-11-18"
       and "Atualizado hoje" in M.linha_concurso(reg2, date(2026, 11, 18), ctx2["novos"], ctx2["alterados"], 0),
       "sem o campo: linha mudada = movimento (padrao mantido)")
    ok(M.sem_movimento({"movimento": False}) and M.sem_movimento({"movimento": "false"})
       and not M.sem_movimento({"movimento": True}) and not M.sem_movimento({}), "sem_movimento")
    # preparar: nenhum item 'concurso|tjrs_juiz|atualizado' no historico
    ex = {"items": [], "email": {}, "ledger_updates": {"concursos": {"tjrs_juiz": {"linha": nova, "movimento": False}}}}
    M.preparar(ex, j, led, {}, {}, {"historico": os.path.join(FIX, "historico.json"), "bancas": "/inexistente",
                                    "fontes_status": "/inexistente"})
    ok(not any(i.get("chave", "").startswith("concurso|tjrs_juiz|") for i in ex["items"]),
       "sem item 'atualizado' no historico")


@teste
def t_mon_saiu_do_acompanhamento():
    """verified[46]: concurso removido sai do bloco com 'Saiu do acompanhamento: <órgão> — <desfecho>' so no dia;
    pendencia visivel (sem concurso, sem errata, fora da cronica, nao operacional) removida idem, no quadro."""
    ctx, led, j = ctx_1811({"pgm_curitiba": {"remover": True, "desfecho": "inscrições encerradas em 05/11 sem prorrogação"}})
    ok(ctx["removidos"] == [{"id": "pgm_curitiba", "orgao": "PGM Curitiba", "bloco": "Procurador do Município (PGM)",
                             "desfecho": "inscrições encerradas em 05/11 sem prorrogação"}], "removidos: %s" % ctx["removidos"])
    html = M.sec_concursos(ctx["regs"], date(2026, 11, 18), ctx["novos"], ctx["alterados"], removidos=ctx["removidos"])
    pgm = html.split("Procurador do Município (PGM)</td>")[1].split("Defensor Público Estadual (DPE)")[0]
    ok("Saiu do acompanhamento: <b>PGM Curitiba</b> — inscrições encerradas em 05/11 sem prorrogação." in pgm
       and html.count("Saiu do acompanhamento") == 1, "linha no bloco PGM")
    ok("PGM Curitiba — Procurador" not in html, "o registro removido nao sai")
    ok(M.linha_removido({"orgao": "PGM Curitiba", "desfecho": ""}, 0).endswith(
        "Saiu do acompanhamento: <b>PGM Curitiba</b>.</td></tr>"), "sem desfecho: sem travessao solto")
    ctx2, _, _ = ctx_1811({})
    ok(not ctx2["removidos"] and "Saiu do acompanhamento" not in M.sec_concursos(
        ctx2["regs"], date(2026, 11, 18), ctx2["novos"], ctx2["alterados"]), "sem remocao hoje: nada")
    # pendencias
    upd = {"crise_institucional_stf_pgr_acompanhar": {"remover": True, "desfecho": "a PGR apresentou a denúncia em 19/11"},
           "trf2_oral_divergencia": {"remover": True, "desfecho": "TRF2 confirmou o resultado"},
           "planalto_push_mudo": {"remover": True, "desfecho": "PUSH diário desde 09/11"},
           "errata_2026_11_16": {"remover": True, "desfecho": "Errata publicada na edição de 17/11."}}
    ex = {"items": [], "email": {}}
    q = M.quadro_pendencias(led, upd, ctx2["regs"], ex, j)
    ok(q["removidas"] == [("Caso Master", "a PGR apresentou a denúncia em 19/11")],
       "so a pendencia visivel: sem a ligada a concurso, a errata e a operacional (%s)" % q["removidas"])
    pend = M.aplicar_pendencias(led["pendencias_vivas"], upd)
    box = M.sec_pendencias(pend, ctx2["regs"], {"email": {}}, {}, q)
    ok("Saiu do acompanhamento: Caso Master — a PGR apresentou a denúncia em 19/11." in box
       and "trf2" not in box.lower() and "PUSH" not in box, "quadro com o desfecho")


@teste
def t_mon_compacto_regra_do_radar():
    """verified[30]: a compactacao usa a regra do radar (prazo_em_destaque); a linha compacta mostra a inscricao/
    prova a confirmar de 15 a 30 dias."""
    hoje = date(2026, 11, 20)
    pz = lambda d, ev, conf: {"data": d, "evento": ev, "confirmado": conf}
    ok(not M.prazo_em_destaque(pz("2026-12-13", "prova", False), hoje), "prova a confirmar em 23 dias: fora")
    ok(M.prazo_em_destaque(pz("2026-11-30", "prova", False), hoje), "prova a confirmar em 10 dias: destaque")
    ok(not M.prazo_em_destaque(pz("2026-12-08", "edital de convocação (previsto)", False), hoje),
       "classe 'outro' a confirmar em 18 dias: fora")
    ok(M.prazo_em_destaque(pz("2026-12-15", "resultado", True), hoje), "confirmado em 25 dias: destaque")
    ok(not M.prazo_em_destaque(pz("2026-11-19", "prova", True), hoje) and not M.prazo_em_destaque(
        pz("2026-12-25", "prova", True), hoje), "passado ou alem de 30 dias: fora")
    ok(M.prazo_em_destaque(pz("2026-12-03", "início das inscrições", False), hoje),
       "inscricao a confirmar em 13 dias (mesmo divergente): destaque")
    led = fx("ledger-1611.json")
    por = {c["id"]: dict(c, mudou_em="2026-11-05") for c in led["concursos"]}
    f = M.criterio_compacto({"primeira_semana": False, "execucao_anterior": "2026-11-19-7h"}, hoje, set(), set(), set())
    ok(f(por["alepa_procurador"]) == "sem_mudanca" and f(por["pgm_curitiba"]) == "sem_mudanca"
       and f(por["trt8_apoio"]) == "sem_mudanca", "ALEPA, PGM Curitiba e TRT8 compactam (prova a 23 dias; 'outro')")
    ok(f(por["tjrs_juiz"]) is None, "TJRS (prova confirmada em 13/12) segue cheio")
    lc = M.linha_compacta([por["alepa_procurador"], por["trt8_apoio"]], 0, hoje)
    ok("PENDÊNCIA DE VERIFICAÇÃO (desde 05/11; prova 13/12, a confirmar)" in lc
       and "TRT8</b> — PENDÊNCIA DE VERIFICAÇÃO (desde 05/11)" in lc, "linha compacta com a data a confirmar: %s" % lc)
    ok("a confirmar" not in M.linha_compacta([por["alepa_procurador"]], 0), "sem hoje: linha antiga")
    r = M.radar([por["alepa_procurador"], dict(por["pgm_curitiba"], prazos=[pz("2026-11-30", "prova", False)])], hoje)
    ok("PGM Curitiba" in r and "ALEPA" not in r, "radar: a confirmar so ate 14 dias (mesma regra)")


@teste
def t_mon_status_gmail():
    """verified[37]: source_status dos gmail_* derivado de buscas_gmail (linha BUSCAS do coletor-gmail)."""
    j = fx("janela-1711.json")            # segunda 16/11 07h -> terca 17/11 07h: sem fim de semana nem feriado
    linha_b = "BUSCAS | a=2/3 b=0/1 c=0/0 d=0/2 e=0/1 | abertas=2 | anteriores à janela, não abertas=3 | erros: nenhum"
    ex, avisos = {"buscas_gmail": linha_b}, []
    M.status_gmail(ex, j, avisos)
    ok(ex["source_status"] == {"gmail_push_stf": "ok", "gmail_push_stf_informativos": "ok", "gmail_stj_codju": "ok",
                               "gmail_push_planalto": "vazio", "gmail_camara": "ok"} and not avisos,
       "dia util: %s" % ex["source_status"])
    ex = {"buscas_gmail": linha_b, "source_status": {"gmail_push_planalto": "falha", "gmail_camara": "vazio"}}
    M.status_gmail(ex, j, [])
    ok(ex["source_status"]["gmail_push_planalto"] == "falha" and ex["source_status"]["gmail_camara"] == "vazio"
       and ex["source_status"]["gmail_push_stf"] == "ok", "o escrito pelo orquestrador prevalece")
    for mud in ({"inicio": "2026-11-13T07:05:00-03:00", "fim": "2026-11-16T07:05:00-03:00"},
                {"feriados_na_janela": [{"data": "2026-11-20", "tipo": "nacional"}]}, {"recesso": True}):
        ex = {"buscas_gmail": "a=0/0 d=0/1"}
        M.status_gmail(ex, dict(j, **mud), [])
        ok(ex["source_status"] == {"gmail_push_stf": "ok", "gmail_push_planalto": "ok"},
           "fim de semana, feriado ou recesso na janela: silencio ok (%s)" % list(mud))
    ex = {"source_status": {"gmail_push_stf": "ok"}}
    M.status_gmail(ex, j, [])
    ok(ex["source_status"] == {"gmail_push_stf": "ok"}, "sem buscas_gmail: comportamento atual")
    ex = {"buscas_gmail": "BUSCAS | a=3 b=0 c=1 d=0 e=2 | abertas=1"}
    M.status_gmail(ex, j, [])
    ok(ex["source_status"] == {"gmail_push_stf_informativos": "ok", "gmail_push_planalto": "vazio"},
       "formato antigo (so o total): decide so o zero (%s)" % ex["source_status"])
    avisos = []
    M.status_gmail({"buscas_gmail": "abertas=2 erros: nenhum"}, j, avisos)
    ok(len(avisos) == 1 and "buscas_gmail" in avisos[0], "sem contagem: AVISO curto")
    # ponta a ponta: o rodape diz "sem e-mail na janela" para o PUSH Planalto
    ex = fx("execucao-1711.json")
    for k in list(ex["source_status"]):
        if k.startswith("gmail_") and k != "gmail_jota":
            del ex["source_status"][k]
    ex["buscas_gmail"] = linha_b
    t = preparar_pasta("1711", execucao=ex)
    rc, out, _ = rodar("1711", t)
    of = corpo(out).split("Fontes oficiais consultadas")[1].split("Fontes secundárias")[0] if rc == 0 else ""
    res = json.load(open(os.path.join(t, "execucao.resolvido.json"), encoding="utf-8")) if rc == 0 else {}
    ok(rc == 0 and "PUSH Planalto (Resenha Diária) — sem e-mail na janela" in of
       and "boletim da Agência Câmara —" not in of and res["source_status"]["gmail_push_planalto"] == "vazio",
       "rodape e resolvido com o status derivado")


@teste
def t_mon_parenteses_e_stj():
    """lows[3] (parenteses aninhados nas notas) e verified[38] (STJ Noticias de midia sem nota por item)."""
    ok(M.sem_parenteses("o ConJur noticiou em 19/11 que Moraes liberou as ADIs (ver Mídia)")
       == "o ConJur noticiou em 19/11 que Moraes liberou as ADIs — ver Mídia", "aninhado vira travessao")
    ok(M.sem_parenteses("Valor (via JOTA (clipping))") == "Valor — via JOTA — clipping", "dois niveis")
    ok(M.sem_parenteses("sem parenteses") == "sem parenteses", "texto comum intacto")
    it = {"status": "RUMOR", "titulo": "T", "fonte": "JOTA", "data": "2026-11-19", "url": "https://www.jota.info/x",
          "nota": "o ConJur noticiou em 19/11 que Moraes liberou as ADIs (ver Mídia)"}
    h = M.item_padrao(it)
    ok("((" not in h and "))" not in h and "(o ConJur noticiou em 19/11 que Moraes liberou as ADIs — ver Mídia)" in h,
       "item_padrao sem parenteses aninhados: %s" % h[-140:])
    p = "\n".join(M._grupos_planalto([{"status": "CONFIRMADO POR FONTE OFICIAL", "titulo": "Lei nº 1", "grupo": "G",
                                        "nota": "republicada (ver DOU de 20/11)"}], False))
    ok("<i>(republicada — ver DOU de 20/11)</i>" in p, "nota do Planalto sem parenteses aninhados")
    # STJ Noticias: a nota "sem confirmação…" escrita a mao sai; o resto fica; a linha fixa so com item de midia
    ex = fx("execucao-1711.json")
    for i in ex["items"]:
        if i.get("ref") == "c8":
            i["nota"] = "sem confirmação oficial localizada nesta execução; julgamento de 13/11"
    t = preparar_pasta("1711", execucao=ex)
    rc, out, _ = rodar("1711", t)
    stj = secao_html(corpo(out), "⚖️ STJ — Notícias", "⚖️ STJ — Jurisprudência") if rc == 0 else ""
    ok(rc == 0 and "(julgamento de 13/11)" in stj and "sem confirmação" not in stj.replace(M.LINHA_STJ_MIDIA, ""),
       "nota escrita sem a frase automatica")
    ofic = [{"categoria": "STJ Notícias", "status": "CONFIRMADO POR FONTE OFICIAL", "titulo": "STJ x", "fonte": "STJ",
             "url": "https://www.stj.jus.br/x", "data": "2026-11-17"}]
    ok(M.LINHA_STJ_MIDIA not in M.sec_itens("STJ Notícias", "STJ", "vazio", ofic, {"email": {}}),
       "so oficial: sem a linha")


@teste
def t_mon_tamanho_equivalente():
    """verified[1] (so o tamanho) e lows[4]: estilos reescritos sem mudar a renderizacao (provado por captura de tela
    da edicao de 20/11: 0 pixel diferente) — #fff e 0 sem unidade dentro de style; sem margem negativa."""
    t = preparar_pasta("1711")
    rc, out, _ = rodar("1711", t)
    html = corpo(out)
    estilos = re.findall(r'style="([^"]*)"', html)
    ok(rc == 0 and not any("#ffffff" in e for e in estilos) and not any(re.search(r"\b0px\b", e) for e in estilos),
       "sem #ffffff nem 0px dentro de style")
    ok(not any(re.search(r"margin[\w-]*:[^;]*-\d", e) for e in estilos), "nenhuma margem negativa")
    ok('bgcolor="#ffffff"' in html, "atributo bgcolor intacto")
    ok(PLANALTO_TITULO_6PX in html and "font-style:italic;margin:0 0 12px 14px\">" + M.FRASE_PLANALTO in html,
       "frase do Planalto: titulo 6px + frase sem margem negativa")
    ok(M.px(0) == "0" and M.px(14) == "14px", "px()")


@teste
def t_informativos_docs_falha_so_com_leitor_sem_conteudo():
    """21/11/2026 (decisao do dono): informativos_docs so vira 'falha' quando um informativo citado saiu sem
    conteudo ou o informativos.py acusou falha de leitura (parser, sem historico). A sonda de numero ainda nao
    anunciado (403: stf1238/rg399 em 18-20/11) fica 'ok'. Na falha, o rotulo nomeia o produto (antes, fixo
    'documentos oficiais dos informativos (STF/STJ)'), e a decisao vai ao fontes_status.json (o helper faz o
    status de script prevalecer), com o do script em status_script."""
    d = tempfile.mkdtemp(dir=BASE_TMP)
    fs = os.path.join(d, "fontes_status.json")
    j = {"execution_id": "2026-11-20-7h"}
    entrada = {"status": "ok", "detalhe": "abertas: stf1231; nova sem abrir: stf1238 http 403", "script": "informativos.py",
               "execution_id": "2026-11-20-7h", "sem_abrir": ["stf1238"], "falhas": []}
    with open(fs, "w", encoding="utf-8") as f:
        json.dump({"informativos_docs": entrada, "conjur": {"status": "ok", "execution_id": "2026-11-20-7h"}}, f)
    aberta = {"categoria": "Informativos", "titulo": "Informativo STF nº 1231", "destaques_texto": ["x"]}
    ex = {"source_status": {"informativos_docs": "ok"}}
    M.status_informativos(ex, [aberta], fs, j)
    ok(ex["source_status"]["informativos_docs"] == "ok" and "_falha_informativos" not in ex
       and json.load(open(fs))["informativos_docs"] == entrada,
       "sonda sem resposta não citada: ok, fontes_status intacto: %s" % ex)
    sem = {"categoria": "Informativos", "titulo": "Informativo STF nº 1238", "sem_conteudo": True}
    ex = {"source_status": {"informativos_docs": "ok"}, "items": [], "email": {}}
    M.status_informativos(ex, [aberta, sem], fs, j)
    e = json.load(open(fs))["informativos_docs"]
    ok(ex["source_status"]["informativos_docs"] == "falha"
       and ex["_falha_informativos"] == "documento oficial do Informativo STF nº 1238"
       and e["status"] == "falha" and e["status_script"] == "ok"
       and e["detalhe"].startswith("citada sem conteúdo: Informativo STF nº 1238; abertas: stf1231")
       and json.load(open(fs))["conjur"]["status"] == "ok",
       "informativo citado que saiu sem conteúdo: falha com o produto, gravada no fontes_status: %s / %s" % (ex, e))
    ss = ex["source_status"]
    sup = M.suporte_txt(ss, {}, ex)
    fc = M.fontes_consultadas(ss, ex, {})
    pend = M.sec_pendencias([], [], ex, ss)
    ok("Fontes que falharam nesta execução: documento oficial do Informativo STF nº 1238" in sup
       and "documento oficial do Informativo STF nº 1238 — falhou" in fc
       and "Falha técnica nesta execução: documento oficial do Informativo STF nº 1238." in pend
       and "(STF/STJ)" not in sup + fc + pend, "rótulo por produto no rodapé, nas fontes e nas pendências: %s" % sup)
    ok("_falha_informativos" not in M.limpar_para_gravar(ex), "o rótulo não vai ao resolvido")
    avisos = []
    ex2 = {"source_status": {"informativos_docs": "ok"}}
    M.mesclar_status(ex2, j, fs, {}, avisos)
    ok(ex2["source_status"]["informativos_docs"] == "ok" and not any("informativos_docs" in a for a in avisos),
       "rodada seguinte: mesclar_status parte do status_script (sem aviso falso ok→falha): %s" % avisos)
    ex3 = {"source_status": dict(ex2["source_status"])}
    M.status_informativos(ex3, [aberta], fs, j)
    e = json.load(open(fs))["informativos_docs"]
    ok(ex3["source_status"]["informativos_docs"] == "ok" and e["status"] == "ok" and e["status_script"] == "ok"
       and e["detalhe"] == entrada["detalhe"],
       "rodada seguinte em que o 1238 abriu (cache): volta a ok, detalhe do script de volta: %s" % e)
    with open(fs, "w", encoding="utf-8") as f:
        json.dump({"informativos_docs": dict(entrada, status="falha", detalhe="falha: stj910 parser; abertas: stf1231",
                                             falhas=["stj910"])}, f)
    ex4 = {"source_status": {}}
    M.status_informativos(ex4, [aberta, dict(sem, titulo="Repercussão Geral em Pauta nº 399")], fs, j)
    ok(ex4["source_status"]["informativos_docs"] == "falha" and ex4["_falha_informativos"] ==
       "documentos oficiais da Repercussão Geral em Pauta nº 399 e do Informativo STJ nº 910",
       "parser do script + RG citada sem conteúdo: falha com os dois produtos: %s" % ex4.get("_falha_informativos"))
    ex5 = {"source_status": {"informativos_docs": "falha"}}
    M.status_informativos(ex5, [aberta], os.path.join(d, "nao-existe.json"), j)
    ok(ex5["source_status"]["informativos_docs"] == "falha" and "_falha_informativos" not in ex5,
       "sem entrada do script, o status escrito fica (rótulo genérico)")
    # STJ_TESES do coletor-gmail (Jurisprudência em Teses do CodJu) entra em STJ Jurisprudência como fonte oficial
    teses = {"categoria": "STJ Jurisprudência", "titulo": "Jurisprudência em Teses nº 286 — Dosimetria da pena",
             "fonte": "Jurisprudência em Teses (STJ)", "data": "2026-11-20"}
    ok(M.item_oficial(teses) and M.item_oficial(dict(teses, url="https://scon.stj.jus.br/SCON/jt/?action=file&num=286"))
       and M.chave_auto(teses).split("|")[1] == "tese", "STJ_TESES: oficial com e sem URL, chave de tese")


@teste
def t_teses_stj_vai_para_stj_jurisprudencia():
    """Jurisprudência em Teses (linha STJ_TESES do coletor-gmail) vai em STJ Jurisprudência, a seção feita para ela
    (vazia desde a reestruturação): escrita por engano em Informativos ou STJ Notícias, o montador a muda de seção."""
    av = []
    it = {"categoria": "Informativos", "titulo": "Jurisprudência em Teses nº 286 — Dosimetria da pena", "data": "2026-11-16"}
    M.teses_stj(it, av)
    ok(it["categoria"] == "STJ Jurisprudência" and it["fonte"] == M.JT_FONTE and M.item_oficial(it)
       and av and "vai em STJ Jurisprudência (era Informativos)" in av[0], "JT em Informativos muda de seção: %s" % it)
    midia = {"categoria": "STJ Notícias", "titulo": "Jurisprudência em Teses: STJ divulga edição", "fonte": "ConJur",
             "status": "MÍDIA ESPECIALIZADA", "data": "2026-11-16"}
    inf = {"categoria": "Informativos", "ref": "stj286", "titulo": "Jurisprudência em Teses"}
    M.teses_stj(midia, av)
    M.teses_stj(inf, av)
    ok(midia["categoria"] == "STJ Notícias" and midia["fonte"] == "ConJur" and inf["categoria"] == "Informativos"
       and len(av) == 1, "mídia e item com ref ficam onde estão")
    ex = fx("execucao-1711.json")
    ex["items"].append({"categoria": "Informativos", "titulo": "Jurisprudência em Teses nº 286 — Dosimetria da pena",
                        "data": "2026-11-16", "url": "https://scon.stj.jus.br/SCON/jt/?action=file&num=286"})
    t = preparar_pasta("1711", execucao=ex)
    rc, out, _ = rodar("1711", t)
    html = corpo(out)
    sec = html.split("⚖️ STJ — Jurisprudência")[1].split("📚 Informativos")[0]
    ok(rc == 0 and "Jurisprudência em Teses nº 286" in sec and "CONFIRMADO POR FONTE OFICIAL" in sec
       and "Jurisprudência em Teses nº 286" not in html.split("📚 Informativos")[1].split("Concursos")[0]
       and "Sem teses do CodJu" not in sec,
       "JT sai em STJ Jurisprudência com selo oficial (rc=%s)" % rc)


def main():
    try:
        for t in TESTES:
            print("· " + t.__name__)
            try:
                t()
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                ok(False, "%s sem exceção (%s)" % (t.__name__, e))
    finally:
        shutil.rmtree(BASE_TMP, ignore_errors=True)
    print("%s — %d verificações, %d falha(s)" % ("OK" if not FALHAS else "FALHOU", N_OK[0] + len(FALHAS), len(FALHAS)))
    sys.exit(1 if FALHAS else 0)


if __name__ == "__main__":
    main()
