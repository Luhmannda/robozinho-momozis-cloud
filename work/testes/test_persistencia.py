#!/usr/bin/env python3
# =====================================================================
# test_persistencia.py — testes da frente PERSISTENCIA (sem pytest, sem rede):
#   migracoes.py (aplica em ordem de id, nao reaplica, recusa a invalida sem gravar
#   nada dela, remocao ja feita, pendencia estourada do dia nao bloqueia, mesmo
#   aplicar_updates do helper: mudou_em, vinculo, movimento: false); helper
#   (preserva migracoes_aplicadas; movimento: false nao grava o campo nem mexe no
#   mudou_em; buscas_gmail guardado; sem gravacao parcial: mecanico dos concursos
#   com o fallback do montador + ALERTA, excecao vira STATUS: ERRO INTERNO com o
#   relatorio e os arquivos intactos; §R1 exige window_end); medir_uso (WebSearch,
#   esforco, pesos por modelo, US$ com a tabela de precos, 1a chamada antes do
#   run_started_at); ALERTA_ECONOMIA pelo TOTAL contra a media das ultimas 10 com
#   o mesmo modelo do orquestrador; finalizar.sh num repositorio git descartavel
#   (push com espera configuravel, branch de socorro, estado restaurado quando o
#   helper falha, trava de sanidade, sessao fora da origin/main, migracao reaplicada
#   na reaplicacao).
# USO: python3 work/testes/test_persistencia.py   (imprime OK/FALHOU; sai != 0 em falha)
# Tudo roda em pastas temporarias (ROBOZINHO_TMP proprio).
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
FIX = os.path.join(AQUI, "fixtures", "persistencia")
TMPDIR = tempfile.mkdtemp(prefix="robozinho-persist-")
os.environ["ROBOZINHO_TMP"] = TMPDIR
sys.path.insert(0, WORK)

import migracoes         # noqa: E402
import medir_uso         # noqa: E402

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


def ler(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def gravar(p, dados):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=1)


def pasta_migracao(arquivos=None):
    """work_dir descartavel: o ledger pequeno da fixture + migracoes/ (todas, ou so `arquivos`)."""
    d = tempfile.mkdtemp(dir=TMPDIR)
    shutil.copy(os.path.join(FIX, "ledger.json"), os.path.join(d, "robozinho-aprendizado.json"))
    os.makedirs(os.path.join(d, "migracoes"))
    for nome in sorted(os.listdir(os.path.join(FIX, "migracoes"))):
        if arquivos is None or nome in arquivos:
            shutil.copy(os.path.join(FIX, "migracoes", nome), os.path.join(d, "migracoes", nome))
    return d


def md5(p):
    import hashlib
    with open(p, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


# ------------------------------------------------------------------ migracoes.py
@teste
def migracao_aplica_nao_reaplica_e_recusa_invalida():
    d = pasta_migracao()
    p = os.path.join(d, "robozinho-aprendizado.json")
    linhas = migracoes.aplicar(date(2026, 11, 23), work_dir=d)
    ok(linhas[0] == "MIGRACAO 2026-11-21-a-escopo: aplicada (4 concursos, 2 pendências)", linhas)
    ok(len(linhas) == 2 and linhas[1].startswith("ALERTA: migracao 2026-11-21-b-invalida recusada: ")
       and "'BOATO' fora da lista fechada" in linhas[1] and "concurso novo exige `fonte`" in linhas[1], linhas)
    led = ler(p)
    cs = {c["id"]: c for c in led["concursos"]}
    ok("trt8_apoio" not in cs and "novo_sem_fonte" not in cs, "removido; a invalida nao gravou nada")
    ok(cs["enam"]["mudou_em"] == "2026-11-23" and cs["enam"]["selo"] == "PROVA EM BREVE", cs["enam"])
    ok(cs["pge_rj"]["mudou_em"] == "2026-11-23" and "pendencia" not in cs["pge_rj"]
       and cs["pge_rj"]["url_oficial"].startswith("https://pge.rj.gov.br/"), "mecanicos de uma execucao: %r" % cs["pge_rj"])
    ok(cs["tjrs_juiz"]["mudou_em"] == "2026-11-16" and "movimento" not in cs["tjrs_juiz"]
       and "30 vagas" in cs["tjrs_juiz"]["linha"], "movimento: false: linha gravada, mudou_em mantido")
    ok([x["id"] for x in led["pendencias_vivas"]] == ["estourada_x"], "pendencias removidas (a estourada do dia fica)")
    ok(led["migracoes_aplicadas"] == [{"id": "2026-11-21-a-escopo", "aplicada_em": "2026-11-23"}], led.get("migracoes_aplicadas"))
    ok(led["atualizado_por_execucao"] == "2026-11-20-7h", "a migracao nao mexe na marca dos contadores")
    ok(all(x.get("execucoes") == 25 for x in led["pendencias_vivas"]), "contadores intactos")
    # idempotente: a aplicada nao volta; a invalida segue recusada, sem gravar
    antes = md5(p)
    linhas = migracoes.aplicar("2026-11-24", work_dir=d)
    ok(len(linhas) == 1 and "2026-11-21-b-invalida recusada" in linhas[0] and md5(p) == antes, linhas)


@teste
def migracao_so_invalida_nao_grava_e_sem_pasta_nada():
    d = pasta_migracao(["2026-11-21-b-invalida.json"])
    p = os.path.join(d, "robozinho-aprendizado.json")
    antes = md5(p)
    linhas = migracoes.aplicar(date(2026, 11, 23), work_dir=d)
    ok(len(linhas) == 1 and linhas[0].startswith("ALERTA: migracao 2026-11-21-b-invalida recusada:"), linhas)
    ok(md5(p) == antes and "migracoes_aplicadas" not in ler(p), "recusada: o ledger fica byte a byte")
    shutil.rmtree(os.path.join(d, "migracoes"))
    ok(migracoes.aplicar(date(2026, 11, 23), work_dir=d) == [] and md5(p) == antes, "sem migracoes: nada")
    # arquivo ilegivel e sem id: ALERTA, sem derrubar o passo 1
    os.makedirs(os.path.join(d, "migracoes"))
    open(os.path.join(d, "migracoes", "x.json"), "w").write("{nao e json")
    gravar(os.path.join(d, "migracoes", "y.json"), {"ledger_updates": {}})
    linhas = migracoes.aplicar(date(2026, 11, 23), work_dir=d)
    ok(any("x.json: ilegível" in l for l in linhas) and any('y.json recusada: sem "id"' in l for l in linhas), linhas)


@teste
def migracao_reaplicada_num_clone_novo_e_remocao_ja_feita():
    # a execucao caiu antes do commit: o clone do dia seguinte nao tem a marca -> aplica de novo, mesmo resultado
    d1 = pasta_migracao(["2026-11-21-a-escopo.json"])
    migracoes.aplicar(date(2026, 11, 23), work_dir=d1)
    d2 = pasta_migracao(["2026-11-21-a-escopo.json"])
    migracoes.aplicar(date(2026, 11, 24), work_dir=d2)
    l1, l2 = ler(os.path.join(d1, "robozinho-aprendizado.json")), ler(os.path.join(d2, "robozinho-aprendizado.json"))
    tira = lambda led: [{k: v for k, v in c.items() if k != "mudou_em"} for c in led["concursos"]]
    ok(tira(l1) == tira(l2) and l2["migracoes_aplicadas"][0]["aplicada_em"] == "2026-11-24", "upsert idempotente")
    # remocao de id que ja saiu (o julgamento de um dia removeu antes): nao recusa a migracao
    d3 = pasta_migracao(["2026-11-21-a-escopo.json"])
    p = os.path.join(d3, "robozinho-aprendizado.json")
    led = ler(p)
    led["concursos"] = [c for c in led["concursos"] if c["id"] != "trt8_apoio"]
    gravar(p, led)
    linhas = migracoes.aplicar(date(2026, 11, 23), work_dir=d3)
    ok(linhas == ["MIGRACAO 2026-11-21-a-escopo: aplicada (3 concursos, 2 pendências) — 1 remoção já feita antes"],
       linhas)


@teste
def migracao_usa_a_validacao_e_a_aplicacao_do_helper():
    # nenhuma regra duplicada: o validador e o aplicador sao os do Update-Historico.py
    src = open(os.path.join(WORK, "migracoes.py"), encoding="utf-8").read()
    ok("uh.validar_ledger_updates(" in src and "uh.aplicar_updates(" in src and "uh.gravar_ledger(" in src, "importlib")
    # erro de aplicacao (excecao) = recusada inteira, nada gravado
    d = pasta_migracao(["2026-11-21-a-escopo.json"])
    p = os.path.join(d, "robozinho-aprendizado.json")
    antes = md5(p)
    real = migracoes.helper().aplicar_updates

    def quebra(*a, **k):
        raise KeyError("x")
    migracoes.helper().aplicar_updates = quebra
    try:
        linhas = migracoes.aplicar(date(2026, 11, 23), work_dir=d)
    finally:
        migracoes.helper().aplicar_updates = real
    ok(linhas == ["ALERTA: migracao 2026-11-21-a-escopo recusada: falha ao aplicar (KeyError: 'x')"] and md5(p) == antes,
       linhas)


@teste
def migracao_cli():
    d = pasta_migracao(["2026-11-21-a-escopo.json"])
    r = subprocess.run([sys.executable, os.path.join(WORK, "migracoes.py"), "--hoje", "2026-11-23", "--work", d],
                       capture_output=True, text=True)
    ok(r.returncode == 0 and r.stdout.strip() == "MIGRACAO 2026-11-21-a-escopo: aplicada (4 concursos, 2 pendências)",
       r.stdout + r.stderr)


# ------------------------------------------------------------------ helper (Update-Historico.py)
def orq(modelo, lido, grav, saida, chamadas=8, esforco=None):
    o = {"modelo": modelo, "entrada": 15, "cache_lido": lido, "cache_gravado": grav, "cache_gravado_1h": grav,
         "saida": saida, "chamadas_modelo": chamadas, "tokens": 120000, "contexto_total": lido + grav + 15}
    if esforco:
        o["esforco"] = esforco
    return o


def col(modelo, lido, grav, saida, websearch=None):
    c = {"modelo": modelo, "entrada": 8, "cache_lido": lido, "cache_gravado": grav, "cache_gravado_1h": 0,
         "saida": saida, "tokens": 30000, "chamadas": 5, "duracao_ms": 60000}
    if websearch is not None:
        c["websearch"] = websearch
    return c


def execucao_antiga(dia, modelo="claude-fable-5-2", fator=1.0):
    return {"execution_id": "2026-11-%02d-7h" % dia, "date": "2026-11-%02d" % dia, "delivery": "sent",
            "window_start": "2026-11-%02dT07:05:00-03:00" % (dia - 1), "window_end": "2026-11-%02dT07:05:00-03:00" % dia,
            "items": [{"chave": "stf|noticia|x%d|2026|11-%02d" % (i, dia), "categoria": "STF Notícias",
                       "status": "NOVO", "titulo": "t"} for i in range(12)],
            "orquestrador": orq(modelo, int(900000 * fator), int(190000 * fator), int(72000 * fator)),
            "coletores": {"gmail": col("claude-haiku-5-5", 38000, 22000, 9000),
                          "jota": col("claude-sonnet-5-5", 150000, 60000, 7000),
                          "concursos": col("claude-sonnet-5-5", 60000, 38000, 6000, websearch=9)}}


def pasta_helper(execucoes=None, ledger=None):
    d = tempfile.mkdtemp(dir=TMPDIR)
    led = ledger or ler(os.path.join(FIX, "ledger.json"))
    for p in led.get("pendencias_vivas") or []:
        if p["id"] == "estourada_x" and ledger is None:
            p["execucoes"] = 5               # a estourada e so da fixture das migracoes
    led.setdefault("migracoes_aplicadas", [{"id": "2026-11-21-a-escopo", "aplicada_em": "2026-11-23"}])
    gravar(os.path.join(d, "led.json"), led)
    if execucoes is None:
        execucoes = [execucao_antiga(x) for x in (16, 17, 18, 19, 20)]
    gravar(os.path.join(d, "hist.json"), {"archive_files": [], "executions": execucoes})
    gravar(os.path.join(d, "janela.json"), {"execution_id": "2026-11-23-7h", "data": "2026-11-23",
                                            "inicio": "2026-11-20T07:05:00-03:00", "fim": "2026-11-23T07:05:00-03:00",
                                            "assunto": "Robozinho - 23/11/2026 - 7h", "execucao_anterior": "2026-11-20-7h"})
    return d


def rodar_helper(d, ex, *extra):
    gravar(os.path.join(d, "ex.json"), ex)
    r = subprocess.run([sys.executable, os.path.join(WORK, "Update-Historico.py"), "--nova-execucao",
                        os.path.join(d, "ex.json"), "--historico", os.path.join(d, "hist.json"), "--ledger",
                        os.path.join(d, "led.json"), "--janela", os.path.join(d, "janela.json"), "--bancas",
                        os.path.join(d, "bancas.json"), "--fontes-status", os.path.join(d, "fs.json"),
                        "--relatorio-path", os.path.join(d, "relatorio.txt")] + list(extra),
                       capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def itens(n, dia="2026-11-23"):
    return [{"chave": "stf|noticia|novo%d|2026|%s" % (i, dia[5:]), "categoria": "STF Notícias", "status": "NOVO",
             "titulo": "Notícia %d" % i, "url": "https://portal.stf.jus.br/n%d" % i} for i in range(n)]


@teste
def helper_preserva_migracoes_movimento_e_buscas_gmail():
    d = pasta_helper()
    linha = "TJRS — Juiz de Direito Substituto: banca FGV, 30 vagas, taxa R$ 305,00; prova objetiva prevista para 13/12/2026"
    busca = "BUSCAS | a=2/3 b=0/1 c=0/0 d=1/1 e=0/2 | abertas=3 | anteriores à janela, não abertas=2 | erros: nenhum"
    ex = {"delivery": "draft", "items": itens(12), "buscas_gmail": busca,
          "ledger_updates": {"concursos": {"tjrs_juiz": {"linha": linha, "movimento": False},
                                           "pge_rj": {"linha": "PGE-RJ — 19º concurso: orais convocadas (DO 20/11)",
                                                      "movimento": True}},
                             "pendencias": {"estourada_x": {"faixa": "longo_prazo"}}}}
    rc, out = rodar_helper(d, ex, "--draft-id", "r1")
    ok(rc == 0 and "STATUS: OK" in out, out)
    led = ler(os.path.join(d, "led.json"))
    ok(led["migracoes_aplicadas"] == [{"id": "2026-11-21-a-escopo", "aplicada_em": "2026-11-23"}], "preservada")
    cs = {c["id"]: c for c in led["concursos"]}
    ok(cs["tjrs_juiz"]["linha"] == linha and cs["tjrs_juiz"]["mudou_em"] == "2026-11-16" and "movimento" not in cs["tjrs_juiz"],
       "movimento false: grava a linha, sem o campo e sem mudou_em: %r" % cs["tjrs_juiz"])
    ok(cs["pge_rj"]["mudou_em"] == "2026-11-23" and "movimento" not in cs["pge_rj"], "movimento true = alteracao normal")
    ok("Ledger: concursos tjrs_juiz atualizada (linha) — sem movimento (mudou_em mantido)" in out, out)
    nova = ler(os.path.join(d, "hist.json"))["executions"][-1]
    ok(nova["buscas_gmail"] == busca and "AVISO: buscas_gmail" not in out, "buscas_gmail guardado sem erro")
    # so movimento: false sobre o registro (nada a gravar): sem "atualizada ()"
    rc, out = rodar_helper(d, dict(ex, ledger_updates={"concursos": {"tjrs_juiz": {"movimento": False}}}),
                           "--draft-id", "r1")
    ok(rc == 0 and "STATUS: OK" in out and "tjrs_juiz atualizada" not in out, out)


def helper_em_processo(d, ex, *extra):
    """uh.main() no proprio processo (para trocar funcoes de bancas/uh); devolve (rc, saida)."""
    gravar(os.path.join(d, "ex.json"), ex)
    argv = ["Update-Historico.py", "--nova-execucao", os.path.join(d, "ex.json"), "--historico",
            os.path.join(d, "hist.json"), "--ledger", os.path.join(d, "led.json"), "--janela",
            os.path.join(d, "janela.json"), "--bancas", os.path.join(d, "bancas.json"), "--fontes-status",
            os.path.join(d, "fs.json"), "--estado-concursos", os.path.join(d, "ce.json"),
            "--relatorio-path", os.path.join(d, "relatorio.txt")] + list(extra)
    salvo, buf, err, rc = sys.argv, io.StringIO(), io.StringIO(), 0
    sys.argv = argv
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
            uh.main()
    except SystemExit as e:
        rc = e.code if isinstance(e.code, int) else 1
    finally:
        sys.argv = salvo
    return rc, buf.getvalue() + err.getvalue()


def banca_minima(d, dia="2026-11-23"):
    gravar(os.path.join(d, "bancas.json"), {"data": dia, "banca": "FGV", "http": 200, "concursos": []})


def arquivos_de_estado(d):
    return {n: md5(os.path.join(d, n)) for n in sorted(os.listdir(d))
            if n.endswith(".json") and n not in ("ex.json", "janela.json", "bancas.json", "fs.json")}


@teste
def mecanico_dos_concursos_cai_como_o_montador():
    import bancas
    d = pasta_helper()
    banca_minima(d)
    reais = bancas.carimbos, bancas.contexto_selos

    def quebra(*a, **k):
        raise KeyError("prazos")
    bancas.carimbos = bancas.contexto_selos = quebra
    try:
        rc, out = helper_em_processo(d, {"delivery": "draft", "items": itens(12),
                                         "ledger_updates": {"pendencias": {"estourada_x": {"faixa": "longo_prazo"}}}},
                                     "--draft-id", "r1")
    finally:
        bancas.carimbos, bancas.contexto_selos = reais
    ok(rc == 0 and out.rstrip().endswith("STATUS: OK"), out[-800:])
    ok("ALERTA: mecânico dos concursos com fallback (bancas.carimbos — KeyError: 'prazos')" in out
       and "ALERTA: mecânico dos concursos com fallback (bancas.contexto_selos/divergencias_pendentes — KeyError" in out,
       out)
    led = ler(os.path.join(d, "led.json"))
    ok(led["atualizado_por_execucao"] == "2026-11-23-7h" and ler(os.path.join(d, "hist.json"))["executions"][-1][
        "execution_id"] == "2026-11-23-7h", "a execucao do dia foi gravada inteira")


@teste
def erro_interno_relatorio_sempre_e_nada_gravado():
    d = pasta_helper(execucoes=[execucao_antiga(x) for x in (16, 17, 18, 19, 20)])
    banca_minima(d)
    antes = arquivos_de_estado(d)
    real = uh.calcular_ledger

    def quebra(*a, **k):
        raise ValueError("dado inesperado")
    uh.calcular_ledger = quebra
    try:
        rc, out = helper_em_processo(d, {"delivery": "draft", "items": itens(12)}, "--draft-id", "r1",
                                     "--max-execucoes", "3")
    finally:
        uh.calcular_ledger = real
    rel = open(os.path.join(d, "relatorio.txt"), encoding="utf-8").read()
    ok(rc == 4 and re.search(r"^STATUS: ERRO INTERNO ValueError: dado inesperado \(test_persistencia\.py:\d+\) — "
                             r"nada foi gravado no estado; nada commitado", rel, re.M), rel[-600:])
    ok("Arquivado: 2026-11-16-7h" in rel, "o relatorio traz o log acumulado ate a falha")
    ok(arquivos_de_estado(d) == antes and not os.path.exists(os.path.join(d, "robozinho-estado.json")),
       "nada gravado: %r x %r" % (arquivos_de_estado(d), antes))
    ok(not [n for n in os.listdir(d) if "arquivo-2026-11" in n], "o arquivo morto do mes nao nasceu")


@teste
def gravacao_que_falha_no_meio_volta_tudo():
    d = pasta_helper(execucoes=[execucao_antiga(x) for x in (16, 17, 18, 19, 20)])
    gravar(os.path.join(d, "robozinho-estado.json"), {"ultima_execucao": {"execution_id": "2026-11-20-7h"}})
    antes = arquivos_de_estado(d)
    real = uh.gravar_texto

    def falha_no_ledger(caminho, texto):
        if caminho.endswith("led.json"):
            raise OSError(28, "No space left on device")
        real(caminho, texto)
    uh.gravar_texto = falha_no_ledger
    try:
        rc, out = helper_em_processo(d, {"delivery": "draft", "items": itens(12)}, "--draft-id", "r1",
                                     "--max-execucoes", "3")
    finally:
        uh.gravar_texto = real
    ok(rc == 4 and "ERRO: gravacao interrompida em led.json (OSError" in out and "voltaram ao que eram" in out
       and "STATUS: ERRO INTERNO OSError" in out, out[-800:])
    ok(arquivos_de_estado(d) == antes, "historico, arquivo morto e estado voltaram: %r" % arquivos_de_estado(d))


@teste
def validar_nao_grava_nem_o_envelope():
    d = pasta_helper()
    os.remove(os.path.join(d, "hist.json"))
    rc, out = helper_em_processo(d, {"delivery": "draft", "items": itens(12)}, "--validar")
    ok(rc == 0 and "VALIDACAO: OK" in out and not os.path.exists(os.path.join(d, "hist.json")), out[-400:])


@teste
def r1_exige_window_end_do_rascunho_achado():
    d = pasta_helper()
    j = ler(os.path.join(d, "janela.json"))
    j["fim"] = "2026-11-23T16:40:00-03:00"            # re-execucao a tarde (sessao da manha caiu antes do push)
    gravar(os.path.join(d, "janela.json"), j)
    base = {"delivery": "draft_ja_existente", "items": [], "verification_notes": ["rascunho r-manha achado"]}
    rc, out = rodar_helper(d, base)
    ok(rc == 2 and "ERRO: window_end ausente — §R1:" in out and "(2026-11-23T16:40:00-03:00)" in out
       and "campo obrigatorio ausente: window_end" not in out, out[-600:])
    rc, out = rodar_helper(d, dict(base, window_end="2026-11-23T17:00:00-03:00"))
    ok(rc == 2 and "depois desta re-execução" in out, out[-400:])
    rc, out = rodar_helper(d, dict(base, window_end="2026-11-23T07:14:00-03:00"))
    ok(rc == 0 and "STATUS: OK" in out and "itens de noticia" not in out, out[-600:])
    est = ler(os.path.join(d, "robozinho-estado.json"))
    ok(est["ultima_execucao"]["window_end"] == "2026-11-23T07:14:00-03:00", est["ultima_execucao"])
    # registro de hoje ja existe: nada muda (o janela.fim nao importa, nada e gravado)
    rc, out = rodar_helper(d, base)
    ok(rc == 0 and "nada a gravar (duplicata" in out, out[-300:])
    # execucao normal: o helper continua completando o window_end do inicio.py
    d = pasta_helper()
    rc, out = rodar_helper(d, {"delivery": "draft", "items": itens(12)}, "--draft-id", "r1")
    ok(rc == 0 and ler(os.path.join(d, "hist.json"))["executions"][-1]["window_end"] == "2026-11-23T07:05:00-03:00", out)


@teste
def mojibake_so_o_de_verdade():
    # o regex de sempre (U+00C3 + U+00A0..U+00BF, ou U+00E2 U+0080): portugues normal ("âmbito") nao e mojibake
    d = pasta_helper()
    it = itens(12)
    it[0]["titulo"] = "No âmbito do STF, ação"
    rc, out = rodar_helper(d, {"delivery": "draft", "items": it}, "--draft-id", "r1")
    ok(rc == 0 and "Encoding: nenhuma marca de mojibake detectada." in out and "ALERTA DE ENCODING" not in out, out[-500:])
    it[1]["titulo"] = "aÃ§Ã£o lida como cp1252 â\u0080\u0094 travessão"
    rc, out = rodar_helper(d, {"delivery": "draft", "items": it}, "--draft-id", "r1")
    ok(rc == 0 and "ALERTA DE ENCODING: 3 ocorrencia(s) de mojibake" in out, out[-500:])


# ------------------------------------------------------------------ medicao do gasto (medir_uso + helper)
def transcricoes(raiz, orq_msgs, coletores):
    """~/.claude/projects falso: sessao.jsonl (orquestrador) + subagents/agent-*.jsonl."""
    proj = os.path.join(raiz, "proj")
    os.makedirs(os.path.join(proj, "sessao", "subagents"), exist_ok=True)
    with open(os.path.join(proj, "sessao.jsonl"), "w") as f:
        f.write("\n".join(json.dumps(m) for m in orq_msgs) + "\n")
    for n, (marca, msgs) in enumerate(coletores):
        p = os.path.join(proj, "sessao", "subagents", "agent-%d.jsonl" % n)
        with open(p, "w") as f:
            f.write(json.dumps({"type": "user", "timestamp": msgs[0]["timestamp"],
                                "message": {"content": "Read de /tmp/%s.md" % marca}}) + "\n")
            f.write("\n".join(json.dumps(m) for m in msgs) + "\n")
        os.utime(p, (1000 + n, 1000 + n))


def msg(i, ts, modelo, ent, lido, grav, saida, grav1h=0, ferramentas=("Bash",), esforco="xhigh", pensou=0, speed=None):
    u = {"input_tokens": ent, "cache_read_input_tokens": lido, "cache_creation_input_tokens": grav,
         "cache_creation": {"ephemeral_1h_input_tokens": grav1h, "ephemeral_5m_input_tokens": grav - grav1h},
         "output_tokens": saida, "output_tokens_details": {"thinking_tokens": pensou},
         "server_tool_use": {"web_search_requests": 0}}
    if speed:
        u["speed"] = speed
    return {"type": "assistant", "timestamp": ts, "effort": esforco, "message": {
        "id": i, "model": modelo, "usage": u, "content": [{"type": "tool_use", "name": n} for n in ferramentas]}}


@teste
def medir_uso_buscas_esforco_pesos_e_dolar():
    raiz = tempfile.mkdtemp(dir=TMPDIR)
    F, S, H = "claude-fable-5-2", "claude-sonnet-5-5", "claude-haiku-5-5"
    transcricoes(raiz, [
        # 1a chamada (le a ROTINA e chama o inicio.py): registros ANTES do run_started_at (10:07:04Z)
        msg("o1", "2026-11-20T10:07:02Z", F, 2, 29625, 19482, 454, 19482, ferramentas=("Read",)),
        msg("o1", "2026-11-20T10:07:03Z", F, 2, 29625, 19482, 454, 19482, ferramentas=("Bash",)),
        msg("o2", "2026-11-20T10:09:00Z", F, 10, 500000, 100000, 40000, 100000, pensou=20000),
    ], [("coletor-concursos", [msg("c1", "2026-11-20T10:07:30Z", S, 4, 30000, 20000, 3000, ferramentas=("WebSearch",) * 5,
                                   esforco="medium"),
                               msg("c2", "2026-11-20T10:08:00Z", S, 4, 31000, 18000, 2500,
                                   ferramentas=("WebSearch", "WebSearch", "Bash"), esforco="medium")]),
        ("coletor-gmail", [msg("g1", "2026-11-20T10:07:30Z", H, 4, 100000, 30000, 6000, esforco="medium")])])
    antigo = medir_uso.RAIZ
    medir_uso.RAIZ = raiz
    try:
        ex = {"run_started_at": "2026-11-20T07:07:04-03:00"}
        log = []
        uh.medir_e_preencher(ex, log.append)
    finally:
        medir_uso.RAIZ = antigo
    o, c, g = ex["orquestrador"], ex["coletores"]["concursos"], ex["coletores"]["gmail"]
    ok(o["chamadas_modelo"] == 2 and o["chamadas"] == 3, "1a chamada inteira, com a margem: %r" % o)
    ok(o["esforco"] == "xhigh" and c["esforco"] == "medium" and o["saida_raciocinio"] == 20000, "esforco e raciocinio")
    ok(c["websearch"] == 7 and o["websearch"] == 0 and c["websearch_usd_est"] == round(7 * 0.055, 4), c)
    # pesos do proprio modelo: Fable le a 0,025 e grava 1 h a 2x
    ok(o["custo_relativo"] - o["fechamento_estimado"]["custo_relativo"] ==
       round(12 + 529625 * 0.025 + 119482 * 2 + 40454 * 5), o["custo_relativo"])
    ok(medir_uso.custo_relativo(10, 3000, 600, 350) == 2810, "sem modelo: os pesos antigos")
    # US$: chamada a chamada; o Haiku com 130 mil tokens de prompt cobra 5x
    usd_o = (12 * 8 + 529625 * 0.20 + 119482 * 16 + 40454 * 40) / 1e6
    ok(abs(o["custo_usd"] - o["fechamento_estimado"]["custo_usd"] - usd_o) < 1e-3, (o["custo_usd"], usd_o))
    usd_g = 5 * (4 * 0.10 + 100000 * 0.01 + 30000 * 0.125 + 6000 * 0.50) / 1e6
    ok(abs(g["custo_usd"] - usd_g) < 1e-4, (g["custo_usd"], usd_g))
    t = ex["custo_usd"]
    ok(t["buscas"] == 7 and abs(t["total"] - (o["custo_usd"] + c["custo_usd"] + g["custo_usd"] + 7 * 0.055)) < 1e-3
       and t["precos_em"] == medir_uso.PRECOS_EM, t)
    ok(any(l.startswith("Custo da execucao (preco de lista da API") for l in log)
       and "orquestrador=fable-5-2/xhigh/" in log[0] and "(7 buscas)" in log[0], log)
    # modelo fora da tabela: None, sem chutar, com AVISO
    ok(medir_uso.custo_usd(1, 1, 1, 1, "claude-desconhecido-9") is None, "sem preco")
    ex2 = {"orquestrador": {}, "coletores": {}}
    m = {"orquestrador": dict(o, modelo="claude-novo-1", custo_usd=None), "coletores": {},
         "custo_usd": medir_uso.custo_execucao(dict(o, modelo="claude-novo-1", custo_usd=None), {})}
    real = medir_uso.medir
    medir_uso.medir = lambda *a, **k: m
    log = []
    try:
        uh.medir_e_preencher(ex2, log.append)
    finally:
        medir_uso.medir = real
    ok(any("AVISO: modelo sem preço na tabela" in l and "claude-novo-1" in l for l in log), log)


@teste
def custo_usd_de_execucao_antiga_recalculado():
    # 20/11 (Fable, gravacao 1 h, chamada final estimada): US$ 6,22 no orquestrador, como na transcricao do cliente
    e = {"orquestrador": {"modelo": "claude-fable-5-2", "entrada": 15, "cache_lido": 972846, "cache_gravado": 189262,
                          "cache_gravado_1h": 189262, "saida": 72315, "tokens": 134000, "contexto_total": 1162123,
                          "fechamento_estimado": {"cache_lido": 134000, "cache_gravado": 2000, "saida": 700}},
         "coletores": {"jota": {"modelo": "claude-sonnet-5-5", "entrada": 12, "cache_lido": 117436,
                                "cache_gravado": 42914, "cache_gravado_1h": 0, "saida": 5643}}}
    c = uh.custo_usd_execucao(e)
    ok(abs(c["orquestrador"] - 6.22) < 0.02 and abs(c["coletores"]["jota"] - 0.18) < 0.01 and c["estimado"], c)
    # sem os tipos separados (antes de 17/11): leitura = contexto - gravacao; gravacao do orquestrador como 1 h
    e = {"orquestrador": {"modelo": "claude-fable-5-2", "contexto_total": 1000000, "cache_gravado": 150000,
                          "saida": 45000, "tokens": 100000}}
    c = uh.custo_usd_execucao(e)
    esperado = (850000 * 0.20 + 150000 * 16 + 45000 * 40 + 100000 * 0.20 + 2000 * 16 + 700 * 40) / 1e6
    ok(abs(c["total"] - esperado) < 1e-3, (c, esperado))
    ok(uh.custo_usd_execucao({"orquestrador": {"modelo": "x-9", "contexto_total": 10}}) is None, "modelo sem preco")
    ok(uh.custo_usd_execucao({"custo_usd": {"total": 7.1, "orquestrador": 6.0, "coletores": {"g": 0.1}, "buscas": 3}})
       == {"total": 7.1, "orquestrador": 6.0, "coletores": {"g": 0.1}, "buscas": 3, "estimado": False}, "medido")


def ex_medida(dia, modelo, orq_usd, col_usd=0.35, buscas=9, chamadas=8):
    return {"execution_id": "2026-11-%02d-7h" % dia, "date": "2026-11-%02d" % dia,
            "orquestrador": {"modelo": modelo, "contexto_total": 10, "chamadas_modelo": chamadas, "esforco": "xhigh",
                             "custo_usd": orq_usd},
            "coletores": {"jota": {"modelo": "claude-sonnet-5-5", "custo_usd": col_usd}},
            "custo_usd": {"total": round(orq_usd + col_usd + buscas * 0.055, 4), "orquestrador": orq_usd,
                          "coletores": {"jota": col_usd}, "buscas": buscas}}


@teste
def alerta_economia_total_contra_media_do_mesmo_modelo():
    F, O = "claude-fable-5-2", "claude-opus-5-5"
    base = [ex_medida(d, F, 6.0) for d in (9, 10, 11, 12, 13)] + [ex_medida(14, O, 3.0)]
    # +30% so nos coletores e nas buscas (o orquestrador igual): o TOTAL passa de 1,3x a media
    log = []
    uh.alertas_uso(base + [ex_medida(16, F, 6.0, col_usd=1.2, buscas=40)], log.append)
    al = [l for l in log if l.startswith("ALERTA_ECONOMIA")]
    ok(len(al) == 1 and "a media das ultimas 5 com claude-fable-5-2" in al[0] and "buscas 40" in al[0]
       and "esforco xhigh" in al[0], log)
    ok(any(l.startswith("AVISO: coletor jota US$ 1.20 = 3.43x") for l in log), log)
    ok(any("ALERTA: modelo do orquestrador mudou: claude-opus-5-5 (2026-11-14-7h) -> claude-fable-5-2" in l
           and "(preco por token de entrada 2x)" in l for l in log), log)
    # dentro de 1,3x: nada
    log = []
    uh.alertas_uso(base + [ex_medida(16, F, 7.0)], log.append)
    ok(not [l for l in log if l.startswith("ALERTA_ECONOMIA")], log)
    # o Fable nao entra na media do Opus; com menos de 3 do mesmo modelo, sem ALERTA_ECONOMIA
    log = []
    uh.alertas_uso(base + [ex_medida(16, O, 9.0)], log.append)
    ok(not [l for l in log if l.startswith("ALERTA") or "mudou" in l], log)
    log = []
    uh.alertas_uso(base[:5] + [ex_medida(16, O, 9.0)], log.append)       # troca Fable -> Opus: so o ALERTA da troca
    ok(not [l for l in log if l.startswith("ALERTA_ECONOMIA")] and any("modelo do orquestrador mudou" in l
                                                                       and "(preco por token de entrada 0.5x)" in l
                                                                       for l in log), log)
    # media de 10, nao mediana: a base usa so as 10 ultimas do mesmo modelo
    longa = [ex_medida(d, F, 2.0) for d in range(1, 6)] + [ex_medida(d, F, 6.0) for d in range(6, 16)]
    ok(len(uh.base_economia(longa, F)) == 10 and all(c["total"] > 6 for _, c in uh.base_economia(longa, F)), "10")
    # troca de esforco: AVISO (nao vai a notificacao)
    log = []
    nova = ex_medida(16, F, 6.0)
    nova["orquestrador"]["esforco"] = "high"
    uh.alertas_uso(base[:5] + [nova], log.append)
    ok(any(l.startswith("AVISO: esforco do orquestrador mudou: xhigh (2026-11-13-7h) -> high") for l in log), log)


@teste
def metricas_de_custo_no_estado():
    F = "claude-fable-5-2"
    exs = [ex_medida(d, F, 6.0) for d in (9, 10, 11)]
    d = pasta_helper(execucoes=exs)
    rc, out = rodar_helper(d, dict(ex_medida(23, F, 6.1), delivery="draft", items=itens(12)), "--draft-id", "r1")
    ok(rc == 0, out)
    m = ler(os.path.join(d, "robozinho-estado.json"))["metricas"]
    ok(m["custo_usd_media_mesmo_modelo"] == {"modelo": F, "execucoes": 4, "media": 6.87}
       and len(m["custo_usd_ultimas_10"]) == 4 and m["custo_usd_ultimas_10"][-1]["execution_id"] == "2026-11-23-7h", m)


# ------------------------------------------------------------------ finalizar.sh (repositorio git descartavel)
MONFIX = os.path.join(AQUI, "fixtures", "mon")
MIGR_TESTE = {"id": "2026-11-16-teste", "descricao": "pendência criada por migração (teste)", "criado_em": "2026-11-16",
              "ledger_updates": {"pendencias": {"migr_teste": {"texto": "Criada pela migração de teste.",
                                                               "faixa": "longo_prazo"}}}}


def repo_finalizar(migracao=False, extra_env=None):
    """origin bare + clone da sessao (branch claude/sessao) com os dados do MON de 17/11 (como o test_est)."""
    base = tempfile.mkdtemp(dir=TMPDIR)
    seed = os.path.join(base, "seed")
    os.makedirs(os.path.join(seed, "work"))
    for f in os.listdir(WORK):
        if f.endswith(".py") or f in ("finalizar.sh", "munger-quotes.json"):
            shutil.copy(os.path.join(WORK, f), os.path.join(seed, "work", f))
    shutil.copy(os.path.join(MONFIX, "ledger-1611.json"), os.path.join(seed, "work", "robozinho-aprendizado.json"))
    shutil.copy(os.path.join(MONFIX, "historico.json"), os.path.join(seed, "work", "resumo-legislativo-historico.json"))
    gravar(os.path.join(seed, "work", "robozinho-estado.json"), {"ultima_execucao": {"execution_id": "2026-11-16-7h"}})
    if migracao:
        os.makedirs(os.path.join(seed, "work", "migracoes"))
        gravar(os.path.join(seed, "work", "migracoes", "2026-11-16-teste.json"), MIGR_TESTE)
    open(os.path.join(seed, ".gitignore"), "w").write("__pycache__/\n")
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@t", ROBOZINHO_TMP=os.path.join(base, "tmp"), ROBOZINHO_PUSH_ESPERAS="0 0 0 0 0")
    env.update(extra_env or {})

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


def helper_falso(sess, corpo):
    """Troca o helper da sessao por um script (defeito simulado) que, importado, expoe as funcoes do helper real
    (a trava do finalizar.sh as usa); o commit nao leva o arquivo (so estado e commitado)."""
    real = os.path.join(sess, "work", "Update-Historico-real.py")
    shutil.copy(os.path.join(sess, "work", "Update-Historico.py"), real)
    cab = ("import json, os, sys, importlib.util\n"
           "_s = importlib.util.spec_from_file_location('uh_real', %r)\n"
           "_m = importlib.util.module_from_spec(_s); _s.loader.exec_module(_m)\n"
           "trava_sanidade, removidos_pedidos = _m.trava_sanidade, _m.removidos_pedidos\n"
           "if __name__ == '__main__':\n    args = sys.argv\n    rel = args[args.index('--relatorio-path') + 1]\n" % real)
    open(os.path.join(sess, "work", "Update-Historico.py"), "w").write(
        cab + "".join("    " + l + "\n" for l in corpo.splitlines()))


FINALIZAR = ("bash", "work/finalizar.sh", "--draft-id", "r-X", "--message-id", "m-X")


@teste
def finalizar_helper_que_morre_restaura_o_estado_de_antes():
    base, sess, t, g, run = repo_finalizar(migracao=True)
    rc, out = run(sys.executable, "work/migracoes.py", "--hoje", "2026-11-17")       # o que o inicio.py faz
    ok(rc == 0 and "MIGRACAO 2026-11-16-teste: aplicada" in out, out)
    run(sys.executable, "work/montar_email.py")
    p = os.path.join(sess, "work", "robozinho-aprendizado.json")
    migrado = md5(p)
    # helper que grava o ledger pela metade e morre sem relatorio (o caso do verified[14] antes da correcao)
    helper_falso(sess, "open('work/robozinho-aprendizado.json', 'w').write('{\"concursos\": [')\n"
                       "open('work/resumo-legislativo-historico-arquivo-2026-11.json', 'w').write('{}')\n"
                       "raise KeyError('contexto_selos')\n")
    rc, out = run(*FINALIZAR)
    ok(rc == 2 and "RESTAURADO: os arquivos de estado de work/ voltaram ao que eram antes do helper" in out
       and "PERSISTENCIA ABORTADA: o helper nao terminou com STATUS: OK" in out, out[-800:])
    ok(md5(p) == migrado and not os.path.exists(os.path.join(sess, "work", "resumo-legislativo-historico-arquivo-2026-11.json")),
       "o ledger volta ao de antes do helper (com a migracao do inicio.py); o arquivo criado sai")
    st = g(sess, "status", "--porcelain", "--untracked-files=no").stdout
    ok(sorted(l[3:] for l in st.splitlines()) == ["work/Update-Historico.py", "work/robozinho-aprendizado.json"], st)
    ok(g(sess, "rev-parse", "HEAD").stdout == g(sess, "rev-parse", "origin/main").stdout, "nada commitado")


@teste
def finalizar_trava_de_sanidade():
    base, sess, t, g, run = repo_finalizar()
    run(sys.executable, "work/montar_email.py")
    p = os.path.join(sess, "work", "robozinho-aprendizado.json")
    antes = md5(p)
    # helper "OK" que perde dois concursos e uma pendencia sem `remover` (defeito de codigo simulado)
    helper_falso(sess, "led = json.load(open('work/robozinho-aprendizado.json'))\n"
                       "fora = [c['id'] for c in led['concursos'][:2]]\n"
                       "led['concursos'] = led['concursos'][2:]\n"
                       "led['pendencias_vivas'] = led['pendencias_vivas'][:-1]\n"
                       "json.dump(led, open('work/robozinho-aprendizado.json', 'w'))\n"
                       "open(rel, 'w').write('STATUS: OK')\nprint('STATUS: OK')\n")
    rc, out = run(*FINALIZAR)
    ok(rc == 2 and re.search(r"^TRAVA: concursos: 2 sumiram sem `remover`", out, re.M)
       and re.search(r"^TRAVA: pendencias_vivas: 1 sumiram .*\(pgm_campinas_setec_verificar\)", out, re.M)
       and "PERSISTENCIA ABORTADA: trava de sanidade" in out and "RESTAURADO:" in out, out[-900:])
    ok(md5(p) == antes and g(sess, "rev-parse", "HEAD").stdout == g(sess, "rev-parse", "origin/main").stdout,
       "nada commitado, ledger de volta")
    # a mesma perda pedida no update de hoje (remover + desfecho) passa
    led = ler(p)
    ids = [c["id"] for c in led["concursos"][:2]]
    ok(uh.trava_sanidade(led, dict(led, concursos=led["concursos"][2:]),
                         [{"concursos": {i: {"remover": True, "desfecho": "d"} for i in ids}}], {"a"}, {"a"}) == [],
       "remover pedido")
    ok(uh.trava_sanidade({"x": [1], "licoes_de_processo": []}, {}, [], {"a", "b"}, {"a"}) ==
       ["ledger: a chave 'x' sumiu", "histórico: 1 execução(ões) sumiram do principal e dos arquivos mortos (b)"],
       "chave e execucao")


@teste
def finalizar_sessao_com_commit_fora_da_main():
    base, sess, t, g, run = repo_finalizar()
    with open(os.path.join(sess, "work", "selos.py"), "a") as f:
        f.write("\n# commit avulso da sessao\n")
    g(sess, "commit", "-qam", "commit avulso na branch da sessao")
    run(sys.executable, "work/montar_email.py")
    rc, out = run(*FINALIZAR)
    ok(rc == 0 and "AVISO: a sessão partiu de um commit com 1 commit(s) fora da origin/main (commit avulso na branch "
       "da sessao;)" in out and "PUSH: OK" in out and out.count("STATUS: OK") == 2, out[-900:])
    ok(g(base, "--git-dir", os.path.join(base, "origin.git"), "log", "--format=%s", "main").stdout.splitlines()
       == ["Robozinho: execução 2026-11-17-7h", "seed"], "o commit avulso nao foi para a main")
    e = ler(os.path.join(sess, "work", "resumo-legislativo-historico.json"))["executions"][-1]
    ok(e["execution_id"] == "2026-11-17-7h", "execucao gravada sobre a origin/main")


@teste
def finalizar_reaplicacao_reaplica_a_migracao():
    base, sess, t, g, run = repo_finalizar(migracao=True)
    run(sys.executable, "work/migracoes.py", "--hoje", "2026-11-17")
    run(sys.executable, "work/montar_email.py")
    outro = os.path.join(base, "outro")
    g(base, "clone", "-q", "origin.git", outro)
    pl = os.path.join(outro, "work", "robozinho-aprendizado.json")
    led = ler(pl)
    led["marca_concorrente"] = "x"
    gravar(pl, led)
    g(outro, "commit", "-qam", "concorrente")
    ok(g(outro, "push", "-q", "origin", "main").returncode == 0, "push concorrente")
    rc, out = run(*FINALIZAR)
    ok(rc == 0 and "PUSH: recusado (main andou no remoto)" in out
       and "REAPLICACAO: MIGRACAO 2026-11-16-teste: aplicada (0 concursos, 1 pendências)" in out
       and "PUSH: OK" in out, out[-900:])
    led = ler(os.path.join(sess, "work", "robozinho-aprendizado.json"))
    ok(led.get("marca_concorrente") == "x" and any(p["id"] == "migr_teste" for p in led["pendencias_vivas"])
       and led["migracoes_aplicadas"][0]["id"] == "2026-11-16-teste" and led["atualizado_por_execucao"] == "2026-11-17-7h",
       "migracao + mudanca concorrente + execucao: %r" % {k: led.get(k) for k in ("migracoes_aplicadas", "marca_concorrente")})
    ok(g(sess, "status", "--porcelain").stdout == "", "árvore limpa")


def hook(base, script):
    h = os.path.join(base, "origin.git", "hooks", "pre-receive")
    open(h, "w").write("#!/bin/sh\n" + script)
    os.chmod(h, 0o755)


@teste
def finalizar_push_falho_vai_para_a_branch_de_socorro():
    base, sess, t, g, run = repo_finalizar()
    run(sys.executable, "work/montar_email.py")
    # o remoto recusa a main (como em 09/10) e aceita outra branch
    hook(base, 'while read a b ref; do [ "$ref" = refs/heads/main ] && { echo "main protegida" >&2; exit 1; }; done; exit 0\n')
    rc, out = run(*FINALIZAR)
    sha = g(sess, "rev-parse", "--short", "HEAD").stdout.strip()
    ok(rc == 3 and "PUSH: FALHOU (apos 5 tentativas)" in out
       and "SOCORRO: commit %s (estado do dia) enviado para a branch robozinho/socorro-2026-11-17-7h" % sha in out, out[-900:])
    remoto = g(base, "--git-dir", os.path.join(base, "origin.git"), "rev-parse", "robozinho/socorro-2026-11-17-7h").stdout
    ok(remoto.strip() == g(sess, "rev-parse", "HEAD").stdout.strip(), "o commit do estado esta no remoto")
    ok(re.search(r"^ESTADO: copia do estado do dia em .* — para reaplicar: tar -xzf", out, re.M), "ESTADO continua")


@teste
def finalizar_push_que_trava_e_cortado():
    base, sess, t, g, run = repo_finalizar(extra_env={"ROBOZINHO_PUSH_ESPERAS": "0 0", "ROBOZINHO_LIMITE_REDE": "2"})
    run(sys.executable, "work/montar_email.py")
    hook(base, "sleep 6\nexit 0\n")
    import time
    t0 = time.time()
    rc, out = run(*FINALIZAR)
    ok(rc == 3 and "push sem resposta em 2 s (cortado)" in out and "PUSH: FALHOU (apos 2 tentativas)" in out
       and time.time() - t0 < 60, out[-900:])


@teste
def finalizar_caminho_feliz_sem_alarme():
    base, sess, t, g, run = repo_finalizar()
    run(sys.executable, "work/montar_email.py")
    rc, out = run(*FINALIZAR)
    ok(rc == 0 and "PUSH: OK" in out and "TRAVA" not in out and "AVISO: a sessão partiu" not in out
       and "SOCORRO" not in out and "RESTAURADO" not in out, out[-600:])
    ok(g(sess, "status", "--porcelain").stdout == "", "árvore limpa")


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
