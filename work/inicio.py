#!/usr/bin/env python3
# =====================================================================
# inicio.py — passo 1 da ROTINA num comando so. Calcula tudo o que e
# deterministico e o orquestrador antes fazia a mao:
#   - ancora de data (America/Sao_Paulo), dia do ano, execution_id;
#   - janela elastica a partir do window_end do estado (teto de 7 dias),
#     1a execucao da semana/gap, recesso forense;
#   - assuntos de hoje e da edicao anterior, cabecalho e rodape;
#   - citacao do Munger (indice = dia do ano mod total, contado agora);
#   - prompts prontos dos coletores em /tmp/coletor-*.md, a partir de
#     work/prompts/*.md + ledger (notas vivas, pendencias, armadilhas);
#   - concursos: prazos do registro estruturado (ledger.concursos) em ordem,
#     os de ate 7 dias como VERIFICAR PRIMEIRO, os vencidos para atualizar;
#     e teste de rede (curl) das paginas oficiais: pendencia ativa cuja
#     pagina oficial esta bloqueada so e reverificada na 1a execucao da
#     semana (a busca secundaria diaria nao pode promover o selo);
#   - /tmp/janela.json, lido por coleta_web.py.
#
# USO:  python3 work/inicio.py [--agora 2026-09-24T07:17:00-03:00]
# =====================================================================

import argparse
import glob
import json
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Sao_Paulo")
AQUI = os.path.dirname(os.path.abspath(__file__))
DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
        "sexta-feira", "sábado", "domingo"]
ASSUNTO = "Robozinho dos Momozis até Passar - %s - 7h"
# Onde ficam os informativos (os e-mails do STF e do STJ trazem so o link).
DOMINIOS_INFORMATIVOS = ("www.stf.jus.br", "ww2.stj.jus.br")
PALAVRAS_CONCURSO = re.compile(
    r"concurso|edital|banca|inscri|juiz|promotor|procurador|defensor|agu|pfn|pge|pgm|dpe|dpu", re.I)


def ler(nome):
    with open(os.path.join(AQUI, nome), encoding="utf-8") as f:
        return json.load(f)


def dias_uteis_entre(a, b):
    """Dias uteis em (a, b], datas."""
    n, d = 0, a
    while d < b:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return n


def em_recesso(d):
    return (d.month == 7 and d.day >= 2) or (d.month == 12 and d.day >= 20) or d.month == 1


def alcancaveis(dominios):
    """{dominio: bool}. False = a rede do ambiente bloqueia (curl devolve 000)."""
    def teste(d):
        try:
            r = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "-m", "6",
                                "https://%s/" % d], capture_output=True, timeout=10)
            return r.stdout.decode().strip() not in ("", "000")
        except Exception:
            return False
    ds = sorted({d for d in dominios if d})
    with ThreadPoolExecutor(max_workers=8) as ex:
        return dict(zip(ds, ex.map(teste, ds)))


def orgao(c):
    """Rotulo curto: o trecho antes de ':' e de ' — ' (ex.: 'TRF2', 'PGE-RJ')."""
    return (c.get("linha") or c.get("id") or "").split(":")[0].split(" — ")[0].strip()


def quando(dias):
    return {0: "hoje", 1: "amanhã", -1: "ontem"}.get(dias, ("em %d dias" % dias) if dias > 0
                                                    else "há %d dias" % -dias)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agora", help="ISO com fuso, so para teste")
    a = ap.parse_args()
    agora = (datetime.fromisoformat(a.agora) if a.agora else datetime.now(TZ)).replace(microsecond=0)
    hoje = agora.date()
    doy = int(agora.strftime("%j"))

    estado = ler("robozinho-estado.json")
    ledger = ler("robozinho-aprendizado.json")
    ult = estado.get("ultima_execucao") or {}

    alertas = []
    if agora.weekday() >= 5:
        alertas.append("HOJE NÃO É DIA ÚTIL — só gerar edição se for pedido expresso (Extra)")
    exec_id = "%s-7h" % hoje.isoformat()
    if ult.get("execution_id") == exec_id:
        alertas.append("JÁ EXISTE a execução %s no estado — re-execução: o anti-duplicata do passo 2 decide" % exec_id)

    inicio = datetime.fromisoformat(ult["window_end"]) if ult.get("window_end") else \
        agora - timedelta(hours=72 if agora.weekday() == 0 else 24)
    if agora - inicio > timedelta(days=7):
        alertas.append("GAP > 7 dias (a última janela terminou em %s): cobrir só 7 dias e registrar "
                       "nas pendências que o intervalo além do teto pode ter lacunas" % inicio.isoformat())
        inicio = agora - timedelta(days=7)
    horas = (agora - inicio).total_seconds() / 3600
    ult_data = datetime.fromisoformat(ult["date"]).date() if ult.get("date") else hoje - timedelta(days=1)
    gap = dias_uteis_entre(ult_data, hoje) > 1
    primeira = agora.weekday() == 0 or ult_data.isocalendar()[1] != hoje.isocalendar()[1] or gap
    recesso = em_recesso(hoje)

    q = ler("munger-quotes.json")
    cit = q["quotes"][doy % len(q["quotes"])]
    fontes_m = {f["id"]: f["titulo"] for f in q.get("fontes", [])}

    hoje_br = hoje.strftime("%d/%m/%Y")
    ant_br = ult_data.strftime("%d/%m/%Y")
    rodape = "segunda-feira" if agora.weekday() == 4 else "amanhã"
    fmt = "%d/%m %H:%M"

    # ---- variaveis dos prompts dos coletores
    fontes = {f["id"]: f for f in ledger.get("fontes", [])}
    armad = {x["id"]: x for x in ledger.get("armadilhas", [])}
    pend_conc = [p for p in ledger.get("pendencias_vivas", [])
                 if p.get("coletor") == "concursos" or
                 (not p.get("coletor") and p.get("faixa") != "cronica" and PALAVRAS_CONCURSO.search(p.get("texto", "")))]
    concursos = ledger.get("concursos", [])
    rede = alcancaveis([p.get("dominio_oficial") for p in pend_conc] +
                       [c.get("dominio_oficial") for c in concursos] + list(DOMINIOS_INFORMATIVOS))
    linhas = []
    for p in pend_conc:
        dom = p.get("dominio_oficial")
        bloqueado = bool(dom) and not rede.get(dom, False)
        if p.get("faixa") == "ativa" and bloqueado and not primeira:
            acao = ("SÓ VIGIAR MOVIMENTO NOVO — a página oficial (%s) está bloqueada pela rede; "
                    "reverificar na 1ª execução da semana" % dom)
        elif p.get("faixa") == "ativa" or (primeira and p.get("faixa") == "longo_prazo"):
            acao = "REVERIFICAR" + ((" — página oficial %s acessível: leia por curl" % dom)
                                    if dom and not bloqueado else "")
        else:
            acao = "SÓ VIGIAR MOVIMENTO NOVO"
        linhas.append("- [%s | %s] %s: %s" % (p.get("faixa"), acao, p["id"], p.get("texto", "")))

    # prazos do registro: <= 7 dias e vencidos ha ate 3 dias vao primeiro na fila do coletor
    proximos, vencidos = [], []
    for c in concursos:
        for pz in c.get("prazos") or []:
            try:
                d = date.fromisoformat(pz.get("data", ""))
            except ValueError:
                continue
            dias = (d - hoje).days
            if -3 <= dias < 0:
                vencidos.append((dias, d, c, pz))
            elif 0 <= dias <= 30:
                proximos.append((dias, d, c, pz))
    proximos.sort(key=lambda x: x[0])
    fmt_pz = lambda dias, d, c, pz: "%s (%s) %s — %s [%s] (id %s)" % (
        d.strftime("%d/%m"), quando(dias), orgao(c), pz.get("evento"),
        "confirmado" if pz.get("confirmado") else "a confirmar", c.get("id"))
    prioridade = (["- confirmar desfecho: " + fmt_pz(*x) for x in vencidos] +
                  ["- " + fmt_pz(*x) for x in proximos if x[0] <= 7])
    na_fila = {x[2].get("id") for x in vencidos} | {x[2].get("id") for x in proximos if x[0] <= 7}
    demais = [orgao(c) for c in concursos if not c.get("pendencia") and c.get("id") not in na_fila]
    regra = ("1ª execução da semana (ou após gap): reverificar as pendências ativa E longo_prazo, "
             "1–2 buscas cada, + até 6 buscas de novidades gerais."
             if primeira else
             "dia comum: reverificar só as pendências ativa; nas longo_prazo, só procurar "
             "edital/inscrição/banca/resultado NOVO dos prazos próximos; até 6 buscas no total.")

    vars_ = {
        "HOJE_BR": hoje_br, "DIA_SEMANA": DIAS[agora.weekday()],
        "INICIO": inicio.isoformat(), "FIM": agora.isoformat(),
        "INICIO_BR": inicio.strftime(fmt), "FIM_BR": agora.strftime(fmt),
        "EPOCH": str(int(inicio.timestamp())), "HORAS": "%.0f" % horas,
        "PRIMEIRA_SEMANA": "sim" if primeira else "não",
        "RECESSO": "sim — fluxo reduzido de STF/STJ é normal" if recesso else "não",
        "REGRA_FAIXA": regra,
        "PENDENCIAS_CONCURSOS": "\n".join(linhas) or "- (nenhuma pendência de concurso no ledger)",
        "CONCURSOS_PRIORIDADE": "\n".join(prioridade) or "- (nenhum prazo nos próximos 7 dias)",
        "CONCURSOS_DEMAIS": "; ".join(demais) or "(nenhum)",
        "REDE_INFORMATIVOS": "; ".join("%s %s" % (d, "acessível" if rede.get(d) else "BLOQUEADO")
                                       for d in DOMINIOS_INFORMATIVOS),
    }

    def sub(m):
        chave = m.group(1)
        if chave.startswith("NOTA:"):
            f = fontes.get(chave[5:])
            return "%s — %s" % (f.get("status"), f.get("nota", "")) if f else "(sem nota no ledger)"
        if chave.startswith("ARMADILHA:"):
            x = armad.get(chave[10:])
            return "%s REGRA: %s" % (x.get("sintoma", ""), x.get("regra", "")) if x else "(armadilha ausente)"
        return vars_.get(chave, m.group(0))

    gerados = []
    for modelo in sorted(glob.glob(os.path.join(AQUI, "prompts", "coletor-*.md"))):
        texto = re.sub(r"\{\{([A-Z_]+(?::[a-z0-9_]+)?)\}\}", sub, open(modelo, encoding="utf-8").read())
        destino = os.path.join("/tmp", os.path.basename(modelo))
        with open(destino, "w", encoding="utf-8") as f:
            f.write(texto)
        sobra = re.findall(r"\{\{[^}]+\}\}", texto)
        gerados.append(destino + (" (PLACEHOLDER SOBRANDO: %s)" % sobra if sobra else ""))

    janela = {"data": hoje.isoformat(), "doy": doy, "execution_id": exec_id,
              "inicio": inicio.isoformat(), "fim": agora.isoformat(), "epoch_inicio": int(inicio.timestamp()),
              "primeira_semana": primeira, "recesso": recesso,
              "assunto": ASSUNTO % hoje_br,
              "assunto_anterior": ult.get("email_subject") or ASSUNTO % ant_br,
              "execucao_anterior": ult.get("execution_id"), "draft_id_anterior": ult.get("draft_id")}
    with open("/tmp/janela.json", "w", encoding="utf-8") as f:
        json.dump(janela, f, ensure_ascii=False, indent=1)

    print("HOJE %s (%s) %s | doy=%d | execution_id=%s" % (hoje_br, DIAS[agora.weekday()],
                                                           agora.strftime("%H:%M:%S %z"), doy, exec_id))
    print("ASSUNTO HOJE:     %s" % janela["assunto"])
    print("ASSUNTO ANTERIOR: %s | exec %s | delivery %s | draft_id %s" % (
        janela["assunto_anterior"], ult.get("execution_id"), ult.get("delivery"), ult.get("draft_id")))
    print("JANELA: %s -> %s (%.1fh) | Gmail after:%s | 1a da semana: %s | gap: %s | recesso: %s" % (
        janela["inicio"], janela["fim"], horas, janela["epoch_inicio"], vars_["PRIMEIRA_SEMANA"],
        "sim" if gap else "não", "sim" if recesso else "não"))
    print("  (herdada = anterior a %s)" % (agora - timedelta(hours=24)).strftime(fmt))
    print("CABECALHO: %s (%s) | RODAPE: \"Próxima edição: %s, às 7h.\"" % (hoje_br, DIAS[agora.weekday()], rodape))
    print("MUNGER total=%d idx=%d fonte=%s%s" % (len(q["quotes"]), doy % len(q["quotes"]),
                                                 fontes_m.get(cit.get("fonte"), cit.get("fonte")),
                                                 " | obs: " + cit["obs"] if cit.get("obs") else ""))
    print("  \"%s\"" % cit["pt"])
    print("PENDENCIAS DE CONCURSO p/ coletor: %d | regra: %s" % (len(pend_conc), regra))
    radar = [fmt_pz(*x) for x in proximos if x[3].get("confirmado")]
    a_conf = [fmt_pz(*x) for x in proximos if not x[3].get("confirmado")]
    print("CONCURSOS: %d no registro | RADAR (só confirmados vão ao quadro): %s" % (
        len(concursos), "; ".join(radar) or "nenhum"))
    if a_conf:
        print("  a confirmar (só na linha do bloco, com o selo dela): " + "; ".join(a_conf))
    for x in vencidos:
        print("ALERTA: prazo vencido %s — confirmar desfecho e atualizar o registro (ledger_updates.concursos)"
              % fmt_pz(*x))
    bloq = [d for d, ok in rede.items() if not ok]
    print("REDE: páginas oficiais bloqueadas: %s | acessíveis: %s" % (
        ", ".join(bloq) or "nenhuma", ", ".join(d for d, ok in rede.items() if ok) or "nenhuma"))
    for al in alertas:
        print("ALERTA: " + al)
    print("PROMPTS: " + " ".join(gerados))
    print("PASSO 2 (uma mensagem): 3 buscas de anti-duplicata no Gmail + Agent coletor-gmail, "
          "coletor-jota e coletor-concursos (primeiro plano) + Bash: python3 work/coleta_web.py; "
          "python3 work/versiculo.py --data %s --dia %d + Read work/template-newsletter-referencia.html"
          % (hoje.isoformat(), doy))


if __name__ == "__main__":
    main()
