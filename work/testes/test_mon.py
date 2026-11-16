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
    avisos = []
    upd = {"concursos": {"tjpb_apoio": {"selo": "ENCERRA EM BREVE"}}}
    ctx2 = M.estado_concursos({"ledger_updates": upd}, j, led, {"historico": os.path.join(FIX, "historico.json")}, avisos)
    ok(next(c for c in ctx2["regs"] if c["id"] == "tjpb_apoio")["selo"] == "ENCERRA EM BREVE",
       "selo escrito hoje nunca e sobrescrito")
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
    # identidade visual: todo estilo do e-mail enviado em 16/11 continua no novo
    with open(os.path.join(FIX, "estilos-1611.txt"), encoding="utf-8") as f:
        estilos = [l.rstrip("\n") for l in f if l.strip()]
    novos = set(re.findall(r'style="([^"]*)"', html))
    faltam = [e for e in estilos if e not in novos]
    ok(not faltam, "identidade visual: estilos de 16/11 preservados (faltam %s)" % faltam[:3])


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
    ok("MÍDIA ESPECIALIZADA" in stj and "STJ define diretrizes" in stj and "sem confirmação oficial localizada" in stj,
       "STJ Noticias aceita midia com selo e nota")
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
