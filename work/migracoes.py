#!/usr/bin/env python3
# =====================================================================
# migracoes.py — migracoes de DADO do ledger (work/robozinho-aprendizado.json),
# aplicadas uma unica vez cada.
#
# Por que: o ledger e reescrito todo dia pela rotina na main; mudanca de dado
# decidida fora da rotina (escopo regional, registro novo conferido a mao...)
# nao pode ser um Edit no arquivo (conflita com a execucao do dia). Vai como
# arquivo de migracao, aplicado pela propria rotina no passo 1.
#
# Arquivo: work/migracoes/<id>.json =
#   {"id": "2026-11-21-escopo-e-concursos", "descricao": "...", "criado_em": "AAAA-MM-DD",
#    "ledger_updates": {...}}      (o MESMO esquema do execucao.json: fontes, pendencias,
#                                   concursos, armadilhas_detectadas, armadilhas_novas)
#
# aplicar(hoje, work_dir=None) -> [linhas]: chamado pelo inicio.py (passo 1), antes de ler o
# ledger, e pelo finalizar.sh (CLI abaixo) antes do helper quando os arquivos de estado voltam
# da origin/main (reaplicacao: a main andou no remoto):
#   - le <work_dir>/migracoes/*.json e aplica, em ordem de id, as que nao constam em
#     ledger["migracoes_aplicadas"], uma por vez, sobre o resultado da anterior;
#   - validacao = Update-Historico.validar_ledger_updates (a mesma da execucao, via importlib;
#     nenhuma regra duplicada aqui). Fica de fora so a regra pendencias_estouradas sobre pendencia
#     que a migracao nao toca: ela cobra o julgamento do dia, nao a migracao. `remover` de id que
#     ja nao existe sai do update antes de validar (o estado final pedido ja vale: idempotente);
#   - aplicacao = Update-Historico.aplicar_updates (os mecanicos de uma execucao: desfecho no log,
#     mudou_em = hoje no concurso criado ou com linha/selo/prazos mudados — salvo movimento: false —,
#     vinculo de pendencia removida, selo copiado igual ao do registro retirado). Contadores e selo
#     por data ficam para o helper do dia (o selo por data depende da banca lida hoje);
#   - recusada (erro de validacao ou de aplicacao): nada dela e gravado e as outras seguem;
#   - grava o ledger uma vez (Update-Historico.gravar_ledger) e marca {"id", "aplicada_em"} em
#     migracoes_aplicadas (o helper preserva a lista). Idempotente: a marcada nao reaplica. Se a
#     execucao cair antes do commit, o clone do dia seguinte nao tem a marca e a migracao e
#     aplicada de novo sobre o ledger da main (upsert: o mesmo resultado, com mudou_em do novo dia).
# Linhas devolvidas (o inicio.py as imprime logo abaixo de HOJE):
#   MIGRACAO <id>: aplicada (<n> concursos, <m> pendências)[ — <k> remoção(ões) já feita(s) antes]
#   ALERTA: migracao <id> recusada: <erros>
#   ALERTA: migracao <arquivo>: ilegível (<erro>)
# Nada pendente -> [] (nada impresso).
#
# USO avulso: python3 work/migracoes.py [--hoje AAAA-MM-DD] [--work DIR]
#   (sem --hoje: a data do $ROBOZINHO_TMP/janela.json, senao hoje em America/Sao_Paulo)
# =====================================================================

import argparse
import copy
import glob
import importlib.util
import json
import os
import sys
from datetime import date, datetime

AQUI = os.path.dirname(os.path.abspath(__file__))
LEDGER = "robozinho-aprendizado.json"
PASTA = "migracoes"
CHAVE = "migracoes_aplicadas"
_UH = None


def helper():
    """Update-Historico.py carregado por importlib (nome com hifen), uma vez."""
    global _UH
    if _UH is None:
        if AQUI not in sys.path:
            sys.path.insert(0, AQUI)          # o helper importa selos (e bancas) da mesma pasta
        spec = importlib.util.spec_from_file_location("update_historico_migracoes",
                                                      os.path.join(AQUI, "Update-Historico.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _UH = mod
    return _UH


def ids_aplicadas(led):
    out = set()
    for x in (led or {}).get(CHAVE) or []:
        out.add(x.get("id") if isinstance(x, dict) else x)
    return out - {None, ""}


def ler_migracoes(pasta):
    """[(id, dados, arquivo)] ordenado por id + [linhas de ALERTA] dos arquivos ilegiveis."""
    itens, alertas, vistos = [], [], set()
    for arq in sorted(glob.glob(os.path.join(pasta, "*.json"))):
        nome = os.path.basename(arq)
        try:
            with open(arq, encoding="utf-8") as f:
                dados = json.load(f)
        except (OSError, ValueError) as e:
            alertas.append("ALERTA: migracao %s: ilegível (%s)" % (nome, e))
            continue
        ident = dados.get("id") if isinstance(dados, dict) else None
        if not ident or not isinstance(ident, str):
            alertas.append("ALERTA: migracao %s recusada: sem \"id\"" % nome)
            continue
        if ident in vistos:
            alertas.append("ALERTA: migracao %s recusada: id repetido (%s)" % (ident, nome))
            continue
        vistos.add(ident)
        itens.append((ident, dados, nome))
    return sorted(itens, key=lambda x: x[0]), alertas


def sem_remocoes_feitas(upd, led):
    """Tira do update (copia) o `remover` de concurso/pendencia que ja nao existe no ledger. Devolve (upd, k)."""
    upd = copy.deepcopy(upd)
    uh = helper()
    k = 0
    for secao in ("concursos", "pendencias"):
        bloco = upd.get(secao)
        if not isinstance(bloco, dict):
            continue
        existentes = {x.get("id") for x in led.get(uh.LISTA_DO_LEDGER[secao]) or []}
        for ident in [i for i, c in bloco.items() if isinstance(c, dict) and c.get("remover") and i not in existentes]:
            del bloco[ident]
            k += 1
    return upd, k


def erros_da_migracao(upd, led, hoje):
    """validar_ledger_updates do helper, menos as pendencias estouradas que a migracao nao toca."""
    uh = helper()
    erros = uh.validar_ledger_updates(upd, led, hoje=hoje)
    do_dia = set(uh.pendencias_estouradas({}, led))       # obrigacao do julgamento do dia, nao da migracao
    return [e for e in erros if e not in do_dia]


def contagem(upd):
    n = len(upd.get("concursos") or {}) if isinstance(upd.get("concursos"), dict) else 0
    m = len(upd.get("pendencias") or {}) if isinstance(upd.get("pendencias"), dict) else 0
    return n, m


def aplicar(hoje, work_dir=None):
    """Aplica as migracoes pendentes de <work_dir>/migracoes ao <work_dir>/robozinho-aprendizado.json.
    hoje: date (ou AAAA-MM-DD). Devolve as linhas para o relatorio (vazia sem nada pendente)."""
    work_dir = work_dir or AQUI
    hj = hoje.isoformat() if isinstance(hoje, (date, datetime)) else str(hoje)[:10]
    date.fromisoformat(hj)                                 # data invalida: erro (o inicio.py vira ALERTA)
    pendentes, linhas = ler_migracoes(os.path.join(work_dir, PASTA))
    if not pendentes and not linhas:
        return []
    caminho = os.path.join(work_dir, LEDGER)
    with open(caminho, encoding="utf-8") as f:
        led = json.load(f)
    feitas = ids_aplicadas(led)
    pendentes = [p for p in pendentes if p[0] not in feitas]
    if not pendentes:
        return linhas
    uh = helper()
    mudou = False
    for ident, dados, nome in pendentes:
        upd = dados.get("ledger_updates")
        if not isinstance(upd, dict) or not upd:
            linhas.append("ALERTA: migracao %s recusada: sem \"ledger_updates\" (objeto no esquema do execucao.json)"
                          % ident)
            continue
        upd, ja_feitas = sem_remocoes_feitas(upd, led)
        erros = erros_da_migracao(upd, led, hj)
        if erros:
            linhas.append("ALERTA: migracao %s recusada: %s" % (ident, " | ".join(erros)))
            continue
        novo = copy.deepcopy(led)
        log = []
        try:
            uh.aplicar_updates(novo, upd, hj, log.append)
            uh.texto_ledger(novo)                       # serializavel e valido, antes de aceitar
        except Exception as e:  # noqa: BLE001 — recusada inteira, sem gravacao parcial
            linhas.append("ALERTA: migracao %s recusada: falha ao aplicar (%s: %s)" % (ident, type(e).__name__, e))
            continue
        novo.setdefault(CHAVE, []).append({"id": ident, "aplicada_em": hj})
        led, mudou = novo, True
        n, m = contagem(upd)
        linhas.append("MIGRACAO %s: aplicada (%d concursos, %d pendências)%s" % (
            ident, n, m, (" — %d remoç%s já feita%s antes" % (ja_feitas, "ão" if ja_feitas == 1 else "ões",
                                                              "" if ja_feitas == 1 else "s")) if ja_feitas else ""))
    if mudou:
        uh.gravar_ledger(caminho, led)
    return linhas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hoje", help="AAAA-MM-DD (padrao: data do janela.json; sem ele, hoje em Sao Paulo)")
    ap.add_argument("--work", default=AQUI, help="pasta com robozinho-aprendizado.json e migracoes/")
    a = ap.parse_args()
    hoje = a.hoje
    if not hoje:
        try:
            with open(os.path.join(os.environ.get("ROBOZINHO_TMP", "/tmp"), "janela.json"), encoding="utf-8") as f:
                hoje = json.load(f).get("data")
        except (OSError, ValueError):
            hoje = None
    if not hoje:
        try:
            from zoneinfo import ZoneInfo
            hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date().isoformat()
        except Exception:  # noqa: BLE001
            hoje = date.today().isoformat()
    for linha in aplicar(hoje, work_dir=a.work):
        print(linha)


if __name__ == "__main__":
    main()
