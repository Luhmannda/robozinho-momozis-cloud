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
