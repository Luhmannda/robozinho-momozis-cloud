#!/usr/bin/env python3
# =====================================================================
# aguardar_coleta.py — o Bash do passo 2 da ROTINA (no lugar de
# "python3 work/coleta_web.py; python3 work/informativos.py; python3 work/versiculo.py").
#
# Por que: o harness roda os Agents do passo 2 em paralelo e o Bash so depois
# deles; os tres scripts somavam ~31 s parados no caminho critico (16/11/2026).
# Agora o inicio.py os dispara em segundo plano logo depois de gravar o
# janela.json (processo destacado: sobrevive ao fim do Bash, testado na nuvem
# em 16/11/2026), e este script so espera e imprime.
#
# O que faz:
#   1. le $ROBOZINHO_TMP/passo2-disparo.json (gravado pelo inicio.py: pids e
#      execution_id). Disparo desta execucao -> espera cada
#      $ROBOZINHO_TMP/passo2-<nome>.rc (teto TETO_S, padrao 240 s, contado do
#      disparo); processo morto sem .rc = roda o script de novo aqui;
#   2. sem disparo, ou disparo de OUTRA execucao (janela.json com outro
#      execution_id), ou saidas velhas -> roda os tres scripts ele mesmo, em
#      paralelo (fallback seguro);
#   3. imprime as saidas na ordem coleta_web, informativos, versiculo (sem as
#      linhas SOURCE_STATUS de cada uma) e, por ultimo, UMA linha
#      "SOURCE_STATUS {json}" com o status de todas as fontes lidas por script,
#      mesclado de $ROBOZINHO_TMP/fontes_status.json (so entradas desta
#      execucao) e das linhas SOURCE_STATUS de cada saida.
#
# USO:   python3 work/aguardar_coleta.py [--teto 240] [--rodar]   (--rodar: ignora o disparo)
# Saida: blocos "== <script> ..." + "SOURCE_STATUS {...}". Exit 0 (o orquestrador le a saida).
#
# Tambem exporta ler_fontes_status(caminho, execution_id), usado pelo helper
# (Update-Historico.py) com a mesma trava (fcntl) dos scripts que gravam o arquivo.
# =====================================================================

import argparse
import fcntl
import json
import os
import subprocess
import sys
import time
from datetime import datetime

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
SCRIPTS = ("coleta_web", "informativos", "versiculo")
TETO_S = 240


def tmp(nome):
    return os.path.join(os.environ.get("ROBOZINHO_TMP", "/tmp"), nome)


def ler_json(caminho, padrao=None):
    try:
        with open(caminho, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return padrao


def ler_fontes_status(caminho=None, execution_id=None):
    """{id: {status, detalhe, script, execution_id}} de fontes_status.json, com a trava do contrato
    INF/WEB (flock em <arquivo>.lock). Entradas de outra execucao sao descartadas (sem execution_id
    pedido, vale tudo)."""
    caminho = caminho or tmp("fontes_status.json")
    if not os.path.exists(caminho):
        return {}
    try:
        with open(caminho + ".lock", "a+") as trava:
            fcntl.flock(trava, fcntl.LOCK_SH)
            try:
                dados = ler_json(caminho, {}) or {}
            finally:
                fcntl.flock(trava, fcntl.LOCK_UN)
    except OSError:
        dados = ler_json(caminho, {}) or {}
    if not isinstance(dados, dict):
        return {}
    return {k: v for k, v in dados.items() if isinstance(v, dict)
            and (not execution_id or v.get("execution_id") in (execution_id,))}


def vivo(pid):
    try:
        os.kill(int(pid), 0)
    except (OSError, ValueError, TypeError):
        return False
    try:                                   # zumbi (processo terminou, sem quem o colha) = morto
        with open("/proc/%d/stat" % int(pid)) as f:
            return f.read().split(")")[-1].split()[0] != "Z"
    except OSError:
        return True


def rodar(nomes):
    """Roda os scripts aqui, em paralelo; grava passo2-<nome>.out/.rc como o disparo do inicio."""
    procs = {}
    for nome in nomes:
        out = open(tmp("passo2-%s.out" % nome), "w", encoding="utf-8")
        procs[nome] = (subprocess.Popen([sys.executable, os.path.join(AQUI, "%s.py" % nome)], cwd=RAIZ,
                                        stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL), out)
    for nome, (p, out) in procs.items():
        try:
            rc = p.wait(timeout=TETO_S)
        except subprocess.TimeoutExpired:
            p.kill()
            rc = "timeout"
        out.close()
        with open(tmp("passo2-%s.rc" % nome), "w") as f:
            f.write("%s\n" % rc)


def esperar(disparo, teto):
    """Espera os .rc do disparo. Devolve {nome: 'ok'|'morto'|'timeout'}."""
    pids = disparo.get("pids") or {}
    try:
        t0 = datetime.fromisoformat(disparo.get("disparado_em")).timestamp()
    except (TypeError, ValueError):
        t0 = time.time()
    limite = max(time.time() + 5, t0 + teto)
    situacao = {}
    while True:
        for nome in SCRIPTS:
            if nome in situacao:
                continue
            if os.path.exists(tmp("passo2-%s.rc" % nome)):
                situacao[nome] = "ok"
            elif nome not in pids or not vivo(pids[nome]):
                time.sleep(0.3)            # o .rc pode estar sendo renomeado neste instante
                situacao[nome] = "ok" if os.path.exists(tmp("passo2-%s.rc" % nome)) else "morto"
        if len(situacao) == len(SCRIPTS) or time.time() > limite:
            break
        time.sleep(0.5)
    for nome in SCRIPTS:
        situacao.setdefault(nome, "timeout")
    return situacao


def status_da_saida(texto):
    """Ultima linha 'SOURCE_STATUS {...}' de uma saida -> dict."""
    for linha in reversed(texto.splitlines()):
        if linha.startswith("SOURCE_STATUS "):
            try:
                v = json.loads(linha[len("SOURCE_STATUS "):])
                return v if isinstance(v, dict) else {}
            except ValueError:
                return {}
    return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--teto", type=int, default=TETO_S, help="segundos de espera, contados do disparo")
    ap.add_argument("--rodar", action="store_true", help="ignora o disparo e roda os scripts aqui")
    a = ap.parse_args()
    t_ini = time.time()
    janela = ler_json(tmp("janela.json"), {}) or {}
    exec_id = janela.get("execution_id")
    disparo = ler_json(tmp("passo2-disparo.json"), {}) or {}
    origem = "em segundo plano desde o passo 1"
    if a.rodar or not disparo or disparo.get("execution_id") != exec_id:
        motivo = ("--rodar" if a.rodar else "sem disparo do inicio.py" if not disparo
                  else "disparo de outra execução (%s)" % disparo.get("execution_id"))
        rodar(SCRIPTS)
        situacao = {n: "ok" for n in SCRIPTS}
        origem = "rodado aqui (%s)" % motivo
    else:
        situacao = esperar(disparo, a.teto)
        refazer = [n for n, s in situacao.items() if s == "morto"]
        if refazer:
            rodar(refazer)
            for n in refazer:
                situacao[n] = "ok"
    status = {}
    for nome in SCRIPTS:
        texto = ""
        try:
            with open(tmp("passo2-%s.out" % nome), encoding="utf-8", errors="replace") as f:
                texto = f.read()
        except OSError:
            pass
        rc = (open(tmp("passo2-%s.rc" % nome)).read().strip() if os.path.exists(tmp("passo2-%s.rc" % nome))
              else "?")
        nota = {"ok": "", "timeout": " — AINDA RODANDO após %d s: saída parcial abaixo; a fonte fica sem status"
                % a.teto, "morto": ""}[situacao[nome]]
        print("== %s.py (exit %s; %s)%s" % (nome, rc, origem if situacao[nome] != "timeout" else "segundo plano", nota))
        status.update(status_da_saida(texto))
        corpo = [l for l in texto.rstrip("\n").splitlines() if not l.startswith("SOURCE_STATUS ")]
        if corpo:
            print("\n".join(corpo))
    for fid, v in sorted(ler_fontes_status(tmp("fontes_status.json"), exec_id).items()):
        if v.get("status"):
            status[fid] = v["status"]
    print("(passo 2 aguardado em %.0f s)" % (time.time() - t_ini))
    print("SOURCE_STATUS " + json.dumps(dict(sorted(status.items())), ensure_ascii=False))


if __name__ == "__main__":
    main()
