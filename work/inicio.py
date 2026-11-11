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
#   - /tmp/janela.json, lido pelos demais scripts (janela, assunto, cabecalho,
#     rodape e citacao do Munger: nada disso e redigitado pelo orquestrador).
#   - RE-EXECUCAO (a edicao de hoje ja esta no estado): saida curta, so com o
#     anti-duplicata — sem ledger nem prompts. Em 11/11/2026 um disparo extra as
#     16h40 recebeu a saida inteira e a rotina mandava gravar por cima do registro
#     da manha. Se o rascunho foi apagado sem envio, --refazer reabre a janela
#     original e ignora o registro de hoje na deduplicacao.
#
# USO:  python3 work/inicio.py [--refazer] [--agora 2026-09-24T07:17:00-03:00]
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
# Descoberta de concursos NOVOS (abertos ou que vao abrir), uma carreira por dia util.
# O registro do ledger so cresce com o que esta varredura encontra.
DESCOBERTA = {
    0: ("Varredura geral (1ª do ciclo semanal)",
        ["concursos carreiras jurídicas inscrições abertas {mes} {ano}",
         "concursos jurídicos editais previstos autorizados {ano} juiz promotor procurador defensor",
         "concurso edital publicado {mes} {ano} procurador OR defensor OR juiz OR promotor"]),
    1: ("Magistratura Estadual e Federal",
        ["concurso juiz substituto edital {ano} inscrições",
         "concurso juiz federal TRF edital {ano} OR comissão formada OR banca definida",
         "tribunal de justiça concurso magistratura {ano} comissão banca previsto"]),
    2: ("Ministério Público (estadual, MPF/MPU) e Defensorias (DPE, DPU)",
        ["concurso promotor de justiça edital {ano} inscrições OR comissão OR banca",
         "concurso defensor público edital {ano} inscrições OR comissão OR banca",
         "concurso MPU OR MPF procurador da república {ano} edital previsto"]),
    3: ("Procuradorias (PGE, PGM, assembleias) e AGU/PFN",
        ["concurso procurador do estado PGE edital {ano} inscrições OR comissão OR banca",
         "concurso procurador do município PGM edital {ano} inscrições abertas",
         "concurso AGU procurador da fazenda nacional {ano} banca edital"]),
    4: ("Quadro de apoio (analista/técnico de TJ, MP, Defensoria, TRF/TRT)",
        ["concurso analista judiciário técnico judiciário edital {ano} inscrições abertas",
         "concurso analista ministério público defensoria edital {ano} inscrições",
         "concurso TJ OR TRF OR TRT servidores edital previsto {ano} banca definida"]),
}
MESES_PT = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
            "setembro", "outubro", "novembro", "dezembro"]
RODIZIO_N = 3          # registros mais antigos reverificados por dia
RODIZIO_DIAS = 10      # so entra no rodizio quem esta sem verificacao ha >= N dias
LIMITE_ATIVA = 21      # prompt mestre §16: pendencia ativa nao passa disso

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
    """{dominio: bool}. False = a rede do ambiente bloqueia (curl devolve 000) ou o
    servidor recusa (403/5xx): mandar o coletor "ler por curl" nesses casos so gasta turno."""
    def teste(d):
        try:
            r = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "-m", "6",
                                "https://%s/" % d], capture_output=True, timeout=10)
            return r.stdout.decode().strip()[:1] in ("2", "3")
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


def resumo_ledger(led):
    """O que o orquestrador precisa do ledger, sem descricao, niveis, dormentes e metricas.
    Substitui o Read do JSON inteiro no passo 1 (~40% menor, reenviado a cada turno)."""
    print("\n==== LEDGER (resumo; em conflito com o prompt mestre, o ledger vence) ====")
    print("FONTES:")
    mortas = [f["id"] for f in led.get("fontes", [])
              if f.get("status") in ("bloqueado", "descontinuado", "indisponivel")]
    for f in led.get("fontes", []):
        if f["id"] in mortas:
            continue
        extra = "".join(" %s=%s" % (k, f[k]) for k in ("ultimo_sucesso", "sem_sucesso", "dias_sem_email")
                        if f.get(k) not in (None, "", 0))
        print("- %s [%s%s]: %s" % (f["id"], f.get("status"), extra, f.get("nota", "")))
    if mortas:
        print("- não tentar (bloqueado/descontinuado/indisponível): " + ", ".join(mortas))
    print("ARMADILHAS (checklist antes de publicar):")
    for x in led.get("armadilhas", []):
        print("- %s (%s): %s" % (x["id"], x.get("fonte", ""), x.get("regra", "")))
    print("PENDENCIAS VIVAS:")
    for p in led.get("pendencias_vivas", []):
        print("- %s [%s, %s execuções, desde %s]: %s | política: %s" % (
            p["id"], p.get("faixa"), p.get("execucoes"), p.get("desde"), p.get("texto", ""), p.get("politica", "")))
    print("CONCURSOS (registro, na ordem dos blocos do e-mail):")
    blocos = []
    for c in led.get("concursos", []):
        if c.get("bloco") not in blocos:
            blocos.append(c.get("bloco"))
    ordem = ["Magistratura Estadual", "Magistratura Federal", "Promotor de Justiça (Estadual)",
             "MPF/MPU — Procurador da República", "PFN", "AGU — Advogado da União",
             "Procurador do Estado (PGE)", "Procurador do Município (PGM)",
             "Defensor Público Estadual (DPE)", "Defensor Público Federal (DPU)", "Quadro de apoio"]
    for b in sorted(blocos, key=lambda b: ordem.index(b) if b in ordem else 99):
        print("  [%s]" % b)
        for c in led.get("concursos", []):
            if c.get("bloco") != b:
                continue
            pz = "; ".join("%s %s%s" % (z.get("data"), z.get("evento"), "" if z.get("confirmado") else " (a confirmar)")
                           for z in c.get("prazos") or [])
            print("  - %s | %s | verificado %s%s | %s%s" % (
                c["id"], c.get("selo"), c.get("verificado_em"),
                " | pendência " + c["pendencia"] if c.get("pendencia") else "", c.get("linha", ""),
                " | prazos: " + pz if pz else ""))
    print("==== fim do LEDGER ====\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agora", help="ISO com fuso, so para teste")
    ap.add_argument("--refazer", action="store_true",
                    help="re-execucao legitima: o rascunho de hoje foi apagado sem envio")
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
    ignorar_exec = ""
    if ult.get("execution_id") == exec_id:
        assunto = ult.get("email_subject") or ASSUNTO % hoje.strftime("%d/%m/%Y")
        if not a.refazer:
            with open("/tmp/janela.json", "w", encoding="utf-8") as f:
                json.dump({"data": hoje.isoformat(), "execution_id": exec_id, "assunto": assunto,
                           "reexecucao": True}, f, ensure_ascii=False, indent=1)
            # o prompt do agendamento le os tres prompts na mesma mensagem: deixa-los curtos, nao ausentes
            for nome in ("gmail", "jota", "concursos"):
                with open("/tmp/coletor-%s.md" % nome, "w", encoding="utf-8") as f:
                    f.write("RE-EXECUÇÃO: a edição de hoje já existe; não há coleta. Siga a saída do work/inicio.py.\n")
            print("HOJE %s (%s) %s | execution_id=%s" % (hoje.strftime("%d/%m/%Y"), DIAS[agora.weekday()],
                                                       agora.strftime("%H:%M:%S %z"), exec_id))
            print("ASSUNTO HOJE: %s" % assunto)
            print("RE-EXECUÇÃO: a edição de hoje já está registrada (delivery %s, draft_id %s, janela até %s)."
                  % (ult.get("delivery"), ult.get("draft_id"), ult.get("window_end")))
            print("1) Faça SÓ o anti-duplicata, numa mensagem: list_drafts com o assunto de hoje + "
                  "search_threads com o assunto de hoje + in:sent.")
            print("2) Algum devolveu algo → a edição existe: PushNotification \"duplicata detectada, nada "
                  "criado\" e FIM. Não rode coleta, não escreva /tmp/execucao.json e NÃO rode "
                  "work/finalizar.sh — o registro da manhã fica intacto.")
            print("3) Os dois vazios (rascunho apagado sem envio) → rode `python3 work/inicio.py --refazer` "
                  "e siga a ROTINA normalmente a partir do passo 1.")
            return
        # refazer: mesma janela da execucao de hoje (ate agora) e a "anterior" volta a ser a de ontem
        try:
            execs = ler("resumo-legislativo-historico.json")["executions"]
        except Exception:
            execs = []
        de_hoje = next((e for e in execs if e.get("execution_id") == exec_id), {})
        antes = [e for e in execs if e.get("execution_id") != exec_id]
        ignorar_exec = exec_id
        alertas.append("REFAZENDO a execução %s: janela original reaberta; o registro de hoje será "
                       "substituído no passo 7 e não conta na deduplicação" % exec_id)
        ult = dict(antes[-1]) if antes else {}
        if de_hoje.get("window_start"):
            ult["window_end"] = de_hoje["window_start"]

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
                       [c.get("dominio_oficial") for c in concursos])
    # banca oficial lida por script (work/bancas.py): o que ela cobre sai da fila do coletor
    try:
        import bancas
        banca = bancas.coletar(hoje, concursos)
    except Exception as e:  # noqa: BLE001 — a banca e reforco, nunca bloqueia a edicao
        banca = {"banca": "FGV", "http": 0, "concursos": [], "erro": str(e)}
    with open("/tmp/bancas.json", "w", encoding="utf-8") as f:
        json.dump(banca, f, ensure_ascii=False, indent=1)
    cobertos = {i for c in banca["concursos"] for i in c.get("coberto") or []}
    pend_coberta = {c.get("pendencia") for c in concursos if c.get("id") in cobertos and c.get("pendencia")}
    linhas = []
    for p in pend_conc:
        dom = p.get("dominio_oficial")
        bloqueado = bool(dom) and not rede.get(dom, False)
        if p["id"] in pend_coberta:
            continue                      # o orquestrador ja tem a pagina oficial da banca
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
    fila = lambda x: x[2].get("id") not in cobertos      # so vai ao coletor o que a banca nao cobriu
    fmt_pz = lambda dias, d, c, pz: "%s (%s) %s — %s [%s] (id %s)" % (
        d.strftime("%d/%m"), quando(dias), orgao(c), pz.get("evento"),
        "confirmado" if pz.get("confirmado") else "a confirmar", c.get("id"))
    prioridade = (["- confirmar desfecho: " + fmt_pz(*x) for x in vencidos if fila(x)] +
                  ["- " + fmt_pz(*x) for x in proximos if x[0] <= 7 and fila(x)])
    na_fila = {x[2].get("id") for x in vencidos} | {x[2].get("id") for x in proximos if x[0] <= 7}
    demais = [orgao(c) for c in concursos if not c.get("pendencia") and c.get("id") not in na_fila]

    # rodizio: os registros com verificacao mais antiga (fora da fila de prazos) ganham busca propria
    def idade(c):
        try:
            return (hoje - date.fromisoformat(c.get("verificado_em", ""))).days
        except ValueError:
            return 999
    velhos = sorted((c for c in concursos if c.get("id") not in na_fila | cobertos and idade(c) >= RODIZIO_DIAS),
                    key=idade, reverse=True)[:RODIZIO_N]
    rodizio = ["- %s (id %s; verificado há %d dias; selo %s): %s" % (
        orgao(c), c.get("id"), idade(c), c.get("selo"), c.get("linha", "")) +
        (" | página oficial %s acessível: leia por curl antes de buscar" % c["dominio_oficial"]
         if c.get("dominio_oficial") and rede.get(c["dominio_oficial"]) else "")
        for c in velhos]
    tema, consultas = DESCOBERTA.get(0 if primeira else agora.weekday(), DESCOBERTA[0])
    consultas = [q.format(mes=MESES_PT[hoje.month - 1], ano=hoje.year) for q in consultas]
    acompanhados = "; ".join("%s [%s]" % (orgao(c), c.get("bloco")) for c in concursos)
    regra = ("1ª execução da semana (ou após gap): até 12 WebSearch — 4 em prazos/pendências "
             "(ativa E longo_prazo), 3 no rodízio, 5 na descoberta (varredura geral)."
             if primeira else
             "dia comum: até 9 WebSearch — 3 em prazos/pendências ativa, 3 no rodízio, 3 na descoberta "
             "da carreira do dia; nas longo_prazo, só movimento NOVO.")

    vars_ = {
        "HOJE_BR": hoje_br, "DIA_SEMANA": DIAS[agora.weekday()],
        "INICIO": inicio.isoformat(), "FIM": agora.isoformat(),
        "INICIO_BR": inicio.strftime(fmt), "FIM_BR": agora.strftime(fmt),
        "EPOCH": str(int(inicio.timestamp())), "HORAS": "%.0f" % horas,
        # after:<epoch> devolve {} no MCP do Gmail (armadilha gmail_after_epoch, 6 execucoes
        # seguidas ate 04/11): busca pelo dia anterior ao inicio e filtro pelo horario interno.
        "GMAIL_APOS": (inicio.date() - timedelta(days=1)).strftime("%Y/%m/%d"),
        "PRIMEIRA_SEMANA": "sim" if primeira else "não",
        "RECESSO": "sim — fluxo reduzido de STF/STJ é normal" if recesso else "não",
        "REGRA_FAIXA": regra,
        "PENDENCIAS_CONCURSOS": "\n".join(linhas) or "- (nenhuma pendência de concurso no ledger)",
        "CONCURSOS_PRIORIDADE": "\n".join(prioridade) or "- (nenhum prazo nos próximos 7 dias)",
        "CONCURSOS_DEMAIS": "; ".join(demais) or "(nenhum)",
        "CONCURSOS_RODIZIO": "\n".join(rodizio) or "- (todos verificados nos últimos %d dias)" % RODIZIO_DIAS,
        "DESCOBERTA_TEMA": tema,
        "DESCOBERTA_CONSULTAS": "\n".join("- `%s`" % q for q in consultas),
        "CONCURSOS_ACOMPANHADOS": acompanhados or "(nenhum)",
        "BANCA_COBERTOS": "; ".join("%s (id %s)" % (orgao(c), c["id"]) for c in concursos
                                    if c["id"] in cobertos) or "(nenhum hoje)",
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

    janela = {"data": hoje.isoformat(), "doy": doy, "execution_id": exec_id, "gmail_apos": vars_["GMAIL_APOS"],
              "inicio": inicio.isoformat(), "fim": agora.isoformat(), "epoch_inicio": int(inicio.timestamp()),
              "primeira_semana": primeira, "recesso": recesso,
              "assunto": ASSUNTO % hoje_br,
              "assunto_anterior": ult.get("email_subject") or ASSUNTO % ant_br,
              "execucao_anterior": ult.get("execution_id"), "draft_id_anterior": ult.get("draft_id"),
              "ignorar_execucao": ignorar_exec,
              # lidos pelo montar_email.py: cabecalho, rodape e Munger nao sao redigitados
              "hoje_br": hoje_br, "dia_semana": DIAS[agora.weekday()], "rodape": rodape,
              "munger": {"texto": cit["pt"], "fonte": fontes_m.get(cit.get("fonte"), cit.get("fonte")),
                         "obs": cit.get("obs") or "", "idx": doy % len(q["quotes"])}}
    with open("/tmp/janela.json", "w", encoding="utf-8") as f:
        json.dump(janela, f, ensure_ascii=False, indent=1)

    print("HOJE %s (%s) %s | doy=%d | execution_id=%s" % (hoje_br, DIAS[agora.weekday()],
                                                           agora.strftime("%H:%M:%S %z"), doy, exec_id))
    print("ASSUNTO HOJE:     %s" % janela["assunto"])
    print("ASSUNTO ANTERIOR: %s | exec %s | delivery %s | draft_id %s" % (
        janela["assunto_anterior"], ult.get("execution_id"), ult.get("delivery"), ult.get("draft_id")))
    print("JANELA: %s -> %s (%.1fh) | Gmail after:%s + filtrar pelo horário interno >= %s | 1a da semana: %s | gap: %s | recesso: %s" % (
        janela["inicio"], janela["fim"], horas, vars_["GMAIL_APOS"], inicio.strftime(fmt), vars_["PRIMEIRA_SEMANA"],
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
    print("CONCURSOS: %d no registro | PRAZOS confirmados em fonte oficial (30 dias): %s" % (
        len(concursos), "; ".join(radar) or "nenhum"))
    if a_conf:
        print("  só em fonte secundária (o quadro os lista à parte, em cinza): " + "; ".join(a_conf))
    for x in vencidos:
        print("ALERTA: prazo vencido %s — confirmar desfecho e atualizar o registro (ledger_updates.concursos)"
              % fmt_pz(*x))
    bloq = [d for d, ok in rede.items() if not ok]
    print("REDE: páginas oficiais bloqueadas: %s | acessíveis: %s" % (
        ", ".join(bloq) or "nenhuma", ", ".join(d for d, ok in rede.items() if ok) or "nenhuma"))
    for p in ledger.get("pendencias_vivas", []):
        if p.get("faixa") == "ativa" and int(p.get("execucoes") or 0) >= LIMITE_ATIVA:
            alertas.append("pendência %s ativa há %s execuções (limite %d): no passo 4, em "
                           "ledger_updates.pendencias, rebaixar a faixa (longo_prazo/cronica) ou remover "
                           "— a validação recusa sem isso" % (p["id"], p.get("execucoes"), LIMITE_ATIVA))
    print("CONCURSOS COLETOR: rodízio=%d registro(s) | descoberta do dia: %s" % (len(velhos), tema))
    for al in alertas:
        print("ALERTA: " + al)
    print()
    bancas.imprimir(banca) if banca.get("concursos") else print(
        "BANCA FGV: não lida (%s) — concursos da FGV seguem pelo coletor." % (banca.get("erro") or "http %s" % banca.get("http")))
    resumo_ledger(ledger)
    print("PROMPTS: " + " ".join(gerados))
    print("PASSO 2 (uma mensagem): 3 buscas de anti-duplicata no Gmail + Agent coletor-gmail, "
          "coletor-jota e coletor-concursos (primeiro plano) + Bash: python3 work/coleta_web.py; "
          "python3 work/informativos.py; python3 work/versiculo.py")


if __name__ == "__main__":
    main()
