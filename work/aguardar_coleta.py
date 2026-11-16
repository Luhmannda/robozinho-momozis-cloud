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
#      $ROBOZINHO_TMP/passo2-<nome>.rc; processo morto sem .rc = dispara o
#      script de novo (destacado) e segue esperando;
#   2. sem disparo, ou disparo de OUTRA execucao (janela.json com outro
#      execution_id), ou --rodar -> dispara os tres scripts ele mesmo, em
#      paralelo e destacados como no inicio.py (fallback seguro), e espera;
#   3. imprime as saidas na ordem coleta_web, informativos, versiculo (sem as
#      linhas SOURCE_STATUS de cada uma), uma linha "AINDA RODANDO <script>
#      (<s> s desde o disparo)" para cada script que nao terminou e, por ultimo,
#      UMA linha "SOURCE_STATUS {json}" com o status de todas as fontes lidas
#      por script, mesclado de $ROBOZINHO_TMP/fontes_status.json (so entradas
#      desta execucao) e das linhas SOURCE_STATUS de cada saida.
#
# Quanto espera (o Bash do agente tem timeout PADRAO de 2 min: a chamada sem
# flag tem de voltar antes, com o que ja terminou):
#   - sem flag: ate CHAMADA_S (90 s) a partir da chamada, e nunca alem de
#     TETO_S (240 s) contados do disparo (com o teto ja vencido, so confere: 5 s);
#   - --mais N: ate N s a partir da chamada (a chamada seguinte, para o script
#     que ficou AINDA RODANDO; o Bash precisa de timeout maior que N). Na saida,
#     o script ja impresso inteiro numa chamada anterior sai numa linha so;
#   - --teto S (compatibilidade): ate S s contados do disparo, sem o limite de
#     CHAMADA_S (quem passa --teto passa tambem o timeout do Bash).
#
# USO:   python3 work/aguardar_coleta.py [--mais N | --teto S] [--rodar]   (--rodar: ignora o disparo)
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
TETO_S = 240          # teto contado do disparo
CHAMADA_S = 90        # teto de UMA chamada sem flag (cabe no timeout padrao de 2 min do Bash, com folga)
MINIMO_S = 5          # sempre confere por pelo menos isto (o .rc pode estar a caminho)


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


def agora_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def disparar(nomes, exec_id, disparo=None):
    """Dispara os scripts em processos destacados (como o inicio.py: sobrevivem ao fim desta chamada) e
    grava/atualiza passo2-disparo.json. Sem `disparo` (fallback), o arquivo e refeito do zero; com ele, so os
    pids e o `iniciado_em` dos `nomes` mudam (script que morreu sem .rc). Devolve o disparo atualizado."""
    novo = disparo is None
    disparo = {"execution_id": exec_id, "pids": {}, "disparado_em": agora_iso()} if novo else disparo
    for nome in nomes:
        for ext in (".out", ".rc"):
            try:
                os.remove(tmp("passo2-%s%s" % (nome, ext)))
            except OSError:
                pass
        out, rc = tmp("passo2-%s.out" % nome), tmp("passo2-%s.rc" % nome)
        cmd = 'cd "$1" && "$2" "$3" > "$4" 2>&1; echo $? > "$5.tmp" && mv "$5.tmp" "$5"'
        try:
            p = subprocess.Popen(["bash", "-c", cmd, "passo2", RAIZ, sys.executable,
                                  os.path.join(AQUI, "%s.py" % nome), out, rc],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 start_new_session=True, env=dict(os.environ))
        except OSError:
            continue
        disparo.setdefault("pids", {})[nome] = p.pid
        if not novo:
            disparo.setdefault("iniciado_em", {})[nome] = agora_iso()
    parcial = "%s.%d.tmp" % (tmp("passo2-disparo.json"), os.getpid())
    with open(parcial, "w", encoding="utf-8") as f:
        json.dump(disparo, f, ensure_ascii=False, indent=1)
    os.replace(parcial, tmp("passo2-disparo.json"))
    return disparo


def inicio_de(disparo, nome):
    """Instante (epoch) em que o script `nome` foi disparado (o redisparo conta do novo inicio)."""
    for v in ((disparo.get("iniciado_em") or {}).get(nome), disparo.get("disparado_em")):
        try:
            return datetime.fromisoformat(v).timestamp()
        except (TypeError, ValueError):
            continue
    return None


def limite_da_chamada(t_ini, t0, mais=None, teto=None):
    """Ate quando (epoch) esta chamada espera. `t_ini` = inicio da chamada, `t0` = disparo."""
    if mais is not None:
        return t_ini + max(0, mais)
    if teto is not None:
        return max(t_ini + MINIMO_S, t0 + teto)
    return min(t_ini + CHAMADA_S, max(t_ini + MINIMO_S, t0 + TETO_S))


def esperar(disparo, limite, exec_id):
    """Espera os .rc do disparo ate `limite` (epoch). Processo morto sem .rc e disparado de novo uma vez
    (e a espera segue). Devolve ({nome: 'ok'|'morto'|'timeout'}, disparo, {nome redisparado})."""
    situacao, refeitos = {}, set()
    while True:
        pids = disparo.get("pids") or {}
        for nome in SCRIPTS:
            if nome in situacao:
                continue
            if os.path.exists(tmp("passo2-%s.rc" % nome)):
                situacao[nome] = "ok"
            elif nome not in pids or not vivo(pids[nome]):
                time.sleep(0.3)            # o .rc pode estar sendo renomeado neste instante
                if os.path.exists(tmp("passo2-%s.rc" % nome)):
                    situacao[nome] = "ok"
                elif nome in refeitos:
                    situacao[nome] = "morto"
                else:
                    disparo = disparar([nome], exec_id, disparo)
                    refeitos.add(nome)
        if len(situacao) == len(SCRIPTS) or time.time() > limite:
            break
        time.sleep(0.5)
    for nome in SCRIPTS:
        situacao.setdefault(nome, "timeout")
    return situacao, disparo, refeitos


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
    ap.add_argument("--teto", type=int, default=None,
                    help="segundos de espera contados do DISPARO, sem o limite por chamada (compatibilidade)")
    ap.add_argument("--mais", type=int, default=None,
                    help="segundos de espera a partir DESTA chamada (para o script que ficou AINDA RODANDO)")
    ap.add_argument("--rodar", action="store_true", help="ignora o disparo e dispara os scripts aqui")
    a = ap.parse_args()
    t_ini = time.time()
    janela = ler_json(tmp("janela.json"), {}) or {}
    exec_id = janela.get("execution_id")
    disparo = ler_json(tmp("passo2-disparo.json"), {}) or {}
    origem = "em segundo plano desde o passo 1"
    if a.rodar or not disparo or disparo.get("execution_id") != exec_id:
        motivo = ("--rodar" if a.rodar else "sem disparo do inicio.py" if not disparo
                  else "disparo de outra execução (%s)" % disparo.get("execution_id"))
        try:
            os.remove(tmp("passo2-impresso.json"))
        except OSError:
            pass
        disparo = disparar(SCRIPTS, exec_id)
        origem = "rodado aqui (%s)" % motivo
    limite = limite_da_chamada(t_ini, inicio_de(disparo, None) or t_ini, a.mais, a.teto)
    situacao, disparo, refeitos = esperar(disparo, limite, exec_id)
    impresso = ler_json(tmp("passo2-impresso.json"), {}) or {}
    impresso = impresso.get("scripts") or {} if impresso.get("execution_id") == exec_id else {}
    agora_impresso = {}
    status, rodando = {}, []
    for nome in SCRIPTS:
        texto = ""
        try:
            with open(tmp("passo2-%s.out" % nome), encoding="utf-8", errors="replace") as f:
                texto = f.read()
        except OSError:
            pass
        p_rc = tmp("passo2-%s.rc" % nome)
        rc = open(p_rc).read().strip() if os.path.exists(p_rc) else "?"
        marca = None
        if situacao[nome] == "ok":
            try:
                marca = "%s|%s" % (os.path.getmtime(p_rc), rc)
            except OSError:
                marca = None
        de = origem
        if nome in refeitos:
            de = "disparado de novo aqui (o processo do disparo morreu sem resultado)"
        if situacao[nome] == "timeout":
            ini = inicio_de(disparo, nome)
            seg = int(time.time() - ini) if ini else int(time.time() - t_ini)
            rodando.append((nome, seg))
            nota = " — AINDA RODANDO (%d s desde o disparo): saída parcial abaixo; a fonte fica sem status" % seg
            de = "segundo plano"
        elif situacao[nome] == "morto":
            nota = " — morreu sem resultado duas vezes: a fonte fica sem status"
        else:
            nota = ""
        status.update(status_da_saida(texto))
        if a.mais is not None and marca and impresso.get(nome) == marca:
            print("== %s.py (exit %s; saída já impressa inteira na chamada anterior)" % (nome, rc))
            agora_impresso[nome] = marca
            continue
        print("== %s.py (exit %s; %s)%s" % (nome, rc, de, nota))
        corpo = [l for l in texto.rstrip("\n").splitlines() if not l.startswith("SOURCE_STATUS ")]
        if corpo:
            print("\n".join(corpo))
        if marca:
            agora_impresso[nome] = marca
    for fid, v in sorted(ler_fontes_status(tmp("fontes_status.json"), exec_id).items()):
        if v.get("status"):
            status[fid] = v["status"]
    try:
        parcial = "%s.%d.tmp" % (tmp("passo2-impresso.json"), os.getpid())
        with open(parcial, "w", encoding="utf-8") as f:
            json.dump({"execution_id": exec_id, "scripts": agora_impresso}, f)
        os.replace(parcial, tmp("passo2-impresso.json"))
    except OSError:
        pass
    for nome, seg in rodando:
        print("AINDA RODANDO %s.py (%d s desde o disparo) — para esperar mais: python3 work/aguardar_coleta.py "
              "--mais N (N s a partir da chamada; Bash com timeout maior que N)" % (nome, seg))
    print("(passo 2 aguardado em %.0f s)" % (time.time() - t_ini))
    print("SOURCE_STATUS " + json.dumps(dict(sorted(status.items())), ensure_ascii=False))


if __name__ == "__main__":
    main()
