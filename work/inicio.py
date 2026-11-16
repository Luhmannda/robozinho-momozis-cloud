#!/usr/bin/env python3
# =====================================================================
# inicio.py — passo 1 da ROTINA num comando so. Calcula tudo o que e
# deterministico e o orquestrador antes fazia a mao:
#   - ancora de data (America/Sao_Paulo), dia do ano, execution_id;
#   - janela elastica a partir do window_end do estado (teto de 7 dias),
#     1a execucao da semana/gap, recesso forense, FERIADOS (work/feriados.py:
#     nacionais, pontos facultativos e Lei 5.010/66 art. 62) — a edicao sai
#     em feriado; o calendario informa o julgamento e desconta os feriados
#     nacionais dos dias uteis do rodizio; gap e "dia util sem execucao
#     registrada" contam seg-sex COM feriado (dia de edicao);
#   - assuntos de hoje e da edicao anterior, cabecalho e rodape;
#   - citacao do Munger (indice = dia do ano mod total, contado agora; +1 na Extra),
#     com tipo (licao|aforismo) e obs para o montador;
#   - dispara em SEGUNDO PLANO coleta_web.py, informativos.py e versiculo.py
#     (logo depois de gravar o janela.json): o passo 2 so espera o resultado com
#     work/aguardar_coleta.py, sem os ~31 s parados depois dos coletores
#     (--sem-disparo ou ROBOZINHO_DISPARO=0 desliga; o aguardar roda os scripts);
#   - prompts prontos dos coletores em $ROBOZINHO_TMP/coletor-*.md, a partir de
#     work/prompts/*.md + ledger (notas vivas, pendencias, armadilhas); o de
#     concursos ganha no fim o "Registro atual" (linha completa dos concursos
#     que nao estao em foco hoje: fidelidade da reescrita de `linha`); errata_*
#     nunca entra na fila do coletor de concursos (e correcao para o leitor);
#     regra de armadilha que o codigo tornou falsa sai ja atualizada (a mesma
#     migracao do helper, Update-Historico.REGRAS_ATUALIZADAS, so em memoria);
#   - rodape "Proxima edicao": o proximo dia de edicao (seg-sex) — "amanhã" ou,
#     de sexta e de (Extra de) sabado, "segunda-feira";
#   - concursos: banca oficial (work/bancas.py: arquivos novos, DIVERGE DO
#     REGISTRO), selo por data (work/selos.py), prazos do registro em ordem,
#     os de ate 7 dias como VERIFICAR PRIMEIRO, os vencidos para confirmar,
#     candidatos a remocao; teste de rede (curl) das paginas oficiais;
#   - LEDGER resumido e enxuto: so os concursos EM FOCO com a linha completa
#     (prazo em ate 30 dias, mudanca recente, pendencia ativa, rodizio, banca
#     lida hoje); os demais contados por bloco, com os ids;
#   - $ROBOZINHO_TMP/janela.json, lido pelos demais scripts (janela, assunto,
#     cabecalho, rodape, Munger, feriados: nada disso e redigitado).
#   - RE-EXECUCAO (a edicao de hoje ja esta no estado): saida curta, so com o
#     anti-duplicata — sem ledger nem prompts. Em 11/11/2026 um disparo extra as
#     16h40 recebeu a saida inteira e a rotina mandava gravar por cima do registro
#     da manha. Se o rascunho foi apagado sem envio, --refazer reabre a janela
#     original e ignora o registro de hoje na deduplicacao.
#   - --extra: edicao extraordinaria (prompt mestre §15): execution_id
#     AAAA-MM-DD-extra, assunto "... - DD/MM/AAAA - Extra", cabecalho "Edição extra",
#     Munger com indice + 1.
#
# USO:  python3 work/inicio.py [--refazer] [--extra] [--sem-disparo]
#                              [--agora 2026-09-24T07:17:00-03:00]   (--agora: so teste)
# Temporarios em $ROBOZINHO_TMP (padrao /tmp).
# =====================================================================

import argparse
import glob
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import feriados
import selos

TZ = ZoneInfo("America/Sao_Paulo")
AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
        "sexta-feira", "sábado", "domingo"]
ASSUNTO = "Robozinho dos Momozis até Passar - %s - 7h"
ASSUNTO_EXTRA = "Robozinho dos Momozis até Passar - %s - Extra"     # prompt mestre §15
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
RODIZIO_DIAS = 7       # so entra no rodizio quem esta sem verificacao ha >= N dias UTEIS (~10 corridos)
LIMITE_ATIVA = 21      # prompt mestre §16: pendencia ativa nao passa disso
FOCO_PRAZO_DIAS = 30   # concurso com prazo ate aqui fica "em foco" (linha completa no LEDGER)
FOCO_MUDANCA_DIAS = 3  # ... e o que mudou nos ultimos N dias
NOTA_CURTA = 160       # nota de fonte nao saudavel no LEDGER
REMOCAO_DIAS = 30      # candidato a remocao: prazos confirmados vencidos ha mais disso
PASSO2 = ("coleta_web", "informativos", "versiculo")
ORDEM_BLOCOS = ["Magistratura Estadual", "Magistratura Federal", "Promotor de Justiça (Estadual)",
                "MPF/MPU — Procurador da República", "PFN", "AGU — Advogado da União",
                "Procurador do Estado (PGE)", "Procurador do Município (PGM)",
                "Defensor Público Estadual (DPE)", "Defensor Público Federal (DPU)", "Quadro de apoio"]

PALAVRAS_CONCURSO = re.compile(
    r"concurso|edital|banca|inscri|juiz|promotor|procurador|defensor|agu|pfn|pge|pgm|dpe|dpu", re.I)


def tmp(nome):
    return os.path.join(os.environ.get("ROBOZINHO_TMP", "/tmp"), nome)


def ler(nome):
    with open(os.path.join(AQUI, nome), encoding="utf-8") as f:
        return json.load(f)


def gravar_json(caminho, dados):
    """Gravacao atomica: os scripts do passo 2 leem o janela.json enquanto o inicio segue."""
    parcial = "%s.%d.tmp" % (caminho, os.getpid())
    with open(parcial, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=1)
    os.replace(parcial, caminho)


def dias_uteis_entre(a, b):
    """Dias uteis em (a, b], datas, sem os feriados nacionais (work/feriados.py)."""
    return feriados.dias_uteis_entre(a, b)


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


def br(iso):
    try:
        return date.fromisoformat(iso).strftime("%d/%m")
    except (TypeError, ValueError):
        return iso or "?"


def migrar_armadilhas(ledger):
    """A mesma migracao de regra de armadilha do helper (Update-Historico.REGRAS_ATUALIZADAS), so em memoria:
    o LEDGER impresso ja sai com a regra atual no dia em que o helper ainda nao gravou. Falha = segue."""
    try:
        import importlib.util
        codigo = os.path.dirname(os.path.abspath(__file__))       # o codigo, nao os dados (AQUI)
        spec = importlib.util.spec_from_file_location("update_historico", os.path.join(codigo, "Update-Historico.py"))
        uh = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(uh)
        return uh.migrar_armadilhas(ledger)
    except Exception:  # noqa: BLE001 — so o texto impresso; nunca bloqueia o passo 1
        return []


def disparar_passo2(exec_id, desligado):
    """coleta_web, informativos e versiculo em processos destacados (sobrevivem ao fim do Bash: testado em
    16/11/2026 na nuvem). Saidas em $ROBOZINHO_TMP/passo2-<nome>.out/.rc; o aguardar_coleta.py espera e
    imprime. Devolve o que foi disparado ([] se desligado ou se falhar: o aguardar roda os scripts)."""
    for nome in PASSO2:
        for ext in (".out", ".rc"):
            try:
                os.remove(tmp("passo2-%s%s" % (nome, ext)))
            except OSError:
                pass
    for nome in ("passo2-disparo.json", "passo2-impresso.json"):      # impresso: o que o aguardar ja mostrou
        try:
            os.remove(tmp(nome))
        except OSError:
            pass
    if desligado:
        return []
    pids = {}
    for nome in PASSO2:
        out, rc = tmp("passo2-%s.out" % nome), tmp("passo2-%s.rc" % nome)
        cmd = ('cd "$1" && "$2" work/%s.py > "$3" 2>&1; echo $? > "$4.tmp" && mv "$4.tmp" "$4"' % nome)
        try:
            p = subprocess.Popen(["bash", "-c", cmd, "passo2", RAIZ, sys.executable, out, rc],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 start_new_session=True, env=dict(os.environ))
            pids[nome] = p.pid
        except OSError:
            continue
    if pids:
        gravar_json(tmp("passo2-disparo.json"), {"execution_id": exec_id, "pids": pids,
                                                 "disparado_em": datetime.now(TZ).isoformat(timespec="seconds")})
    return sorted(pids)


def resumo_ledger(led, foco, motivos, pend_no_coletor):
    """O que o orquestrador precisa do ledger, enxuto (A7/E8): fontes saudaveis so listadas, as demais
    com nota curta; armadilhas com id + regra; pendencias de concurso que ja estao com texto no
    coletor-concursos.md so pelo id; concursos em foco com a linha completa, os demais so contados
    (a linha deles esta no fim do $ROBOZINHO_TMP/coletor-concursos.md)."""
    out = ["", "==== LEDGER (resumo; em conflito com o prompt mestre, o ledger vence) ===="]
    mortas = [f["id"] for f in led.get("fontes", []) if f.get("status") in ("bloqueado", "descontinuado", "indisponivel")]
    saud = [f["id"] for f in led.get("fontes", []) if f.get("status") == "saudavel"]
    out.append("FONTES saudáveis: " + (", ".join(saud) or "nenhuma"))
    for f in led.get("fontes", []):
        if f["id"] in mortas or f["id"] in saud:
            continue
        extra = "".join(" %s=%s" % (k, f[k]) for k in ("ultimo_sucesso", "sem_sucesso", "dias_sem_email")
                        if f.get(k) not in (None, "", 0))
        nota = f.get("nota", "")
        out.append("- %s [%s%s]: %s" % (f["id"], f.get("status"), extra,
                                        nota if len(nota) <= NOTA_CURTA else nota[:NOTA_CURTA].rsplit(" ", 1)[0] + " …"))
    if mortas:
        out.append("- não tentar (bloqueado/descontinuado/indisponível): " + ", ".join(mortas))
    out.append("ARMADILHAS (checklist antes de publicar — id: regra):")
    out += ["- %s: %s" % (x["id"], x.get("regra", "")) for x in led.get("armadilhas", [])]
    out.append("PENDÊNCIAS VIVAS:")
    compactas = []
    for p in led.get("pendencias_vivas", []):
        cab = "%s [%s, %s execuções, desde %s]" % (p["id"], p.get("faixa"), p.get("execucoes"), br(p.get("desde")))
        if p["id"] in pend_no_coletor:      # politica so das ativas (as longo_prazo repetem a regra geral)
            compactas.append("%s [%s, %sx]%s" % (p["id"], p.get("faixa"), p.get("execucoes"), " política: " + p["politica"]
                                                 if p.get("politica") and p.get("faixa") == "ativa" else ""))
        else:
            out.append("- %s: %s%s" % (cab, p.get("texto", ""), " | política: " + p["politica"] if p.get("politica") else ""))
    if compactas:
        out.append("- de concurso, com o texto em %s (seção A): %s" % (tmp("coletor-concursos.md"), "; ".join(compactas)))
    out.append("CONCURSOS (registro, na ordem dos blocos do e-mail; em foco = linha completa; os demais têm a linha "
               "no fim de %s):" % tmp("coletor-concursos.md"))
    blocos = []
    for c in led.get("concursos", []):
        if c.get("bloco") not in blocos:
            blocos.append(c.get("bloco"))
    for b in sorted(blocos, key=lambda b: ORDEM_BLOCOS.index(b) if b in ORDEM_BLOCOS else 99):
        regs = [c for c in led.get("concursos", []) if c.get("bloco") == b]
        demais = [c["id"] for c in regs if c["id"] not in foco]
        out.append("  [%s] %d em foco%s" % (b, len(regs) - len(demais),
                                           "; %d sem foco: %s" % (len(demais), ", ".join(demais)) if demais else ""))
        for c in regs:
            if c["id"] not in foco:
                continue
            if motivos.get(c["id"]) == ["rodízio"]:     # a linha completa ja esta na secao B do coletor-concursos.md
                out.append("  - %s | %s | verificado %s | foco: rodízio (linha na seção B do coletor-concursos.md)"
                           % (c["id"], c.get("selo"), br(c.get("verificado_em"))))
                continue
            pz = "; ".join("%s %s%s" % (br(z.get("data")), z.get("evento"), "" if z.get("confirmado") else " (a confirmar)")
                           for z in c.get("prazos") or [])
            out.append("  - %s | %s | verificado %s%s%s | foco: %s | %s%s" % (
                c["id"], c.get("selo"), br(c.get("verificado_em")),
                " | mudou %s" % br(c["mudou_em"]) if c.get("mudou_em") else "",
                " | pendência " + c["pendencia"] if c.get("pendencia") else "", ", ".join(motivos.get(c["id"], [])),
                c.get("linha", ""), " | prazos: " + pz if pz else ""))
    out.append("==== fim do LEDGER ====")
    out.append("")
    return out


def registro_atual(concursos, foco):
    """Secao acrescentada ao coletor-concursos.md: a linha completa dos concursos sem foco hoje."""
    linhas = ["", "## Registro atual dos demais acompanhados (dados do ledger, só para conferência — não é tarefa)",
              "Se trouxer MOVIMENTO de um destes, compare com a linha atual abaixo e diga o que mudou."]
    for c in concursos:
        if c.get("id") in foco:
            continue
        pz = "; ".join("%s %s%s" % (br(z.get("data")), z.get("evento"), "" if z.get("confirmado") else " (a confirmar)")
                       for z in c.get("prazos") or [])
        linhas.append("- %s | %s | verificado %s | %s%s" % (c.get("id"), c.get("selo"), br(c.get("verificado_em")),
                                                           c.get("linha", ""), " | prazos: " + pz if pz else ""))
    return "\n".join(linhas) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agora", help="ISO 8601 (com ou sem fuso; sem fuso = America/Sao_Paulo). SO PARA TESTE")
    ap.add_argument("--refazer", action="store_true",
                    help="re-execucao legitima: o rascunho de hoje foi apagado sem envio")
    ap.add_argument("--extra", action="store_true", help="edicao extraordinaria (prompt mestre §15)")
    ap.add_argument("--sem-disparo", action="store_true",
                    help="nao dispara o passo 2 em segundo plano (o aguardar_coleta.py roda os scripts)")
    a = ap.parse_args()
    if a.agora:
        agora = datetime.fromisoformat(a.agora)
        agora = agora.replace(tzinfo=TZ) if agora.tzinfo is None else agora.astimezone(TZ)
    else:
        agora = datetime.now(TZ)
    agora = agora.replace(microsecond=0)
    hoje = agora.date()
    doy = int(agora.strftime("%j"))
    os.makedirs(tmp(""), exist_ok=True)

    estado = ler("robozinho-estado.json")
    ledger = ler("robozinho-aprendizado.json")
    migrar_armadilhas(ledger)
    ult = estado.get("ultima_execucao") or {}

    alertas = []
    if agora.weekday() >= 5 and not a.extra:
        alertas.append("HOJE NÃO É DIA ÚTIL — só gerar edição se for pedido expresso (Extra: --extra)")
    exec_id = "%s-%s" % (hoje.isoformat(), "extra" if a.extra else "7h")
    hoje_br = hoje.strftime("%d/%m/%Y")
    assunto_hoje = (ASSUNTO_EXTRA if a.extra else ASSUNTO) % hoje_br
    ignorar_exec = ""
    if ult.get("execution_id") == exec_id:
        assunto = ult.get("email_subject") or assunto_hoje
        if not a.refazer:
            gravar_json(tmp("janela.json"), {"data": hoje.isoformat(), "execution_id": exec_id, "assunto": assunto,
                                             "reexecucao": True})
            # o prompt do agendamento le os tres prompts na mesma mensagem: deixa-los curtos, nao ausentes
            for nome in ("gmail", "jota", "concursos"):
                with open(tmp("coletor-%s.md" % nome), "w", encoding="utf-8") as f:
                    f.write("RE-EXECUÇÃO: a edição de hoje já existe; não há coleta. Siga a saída do work/inicio.py.\n")
            print("HOJE %s (%s) %s | execution_id=%s" % (hoje_br, DIAS[agora.weekday()],
                                                       agora.strftime("%H:%M:%S %z"), exec_id))
            print("ASSUNTO HOJE: %s" % assunto)
            print("RE-EXECUÇÃO: a edição de hoje já está registrada (delivery %s, draft_id %s, janela até %s)."
                  % (ult.get("delivery"), ult.get("draft_id"), ult.get("window_end")))
            print("1) Faça SÓ o anti-duplicata, numa mensagem: list_drafts com o assunto de hoje + "
                  "search_threads com o assunto de hoje + in:sent.")
            print("2) Algum devolveu algo → a edição existe: PushNotification \"duplicata detectada, nada "
                  "criado\" e FIM. Não rode coleta, não escreva %s e NÃO rode "
                  "work/finalizar.sh — o registro da manhã fica intacto." % tmp("execucao.json"))
            print("3) Os dois vazios (rascunho apagado sem envio) → rode `python3 work/inicio.py --refazer%s` "
                  "e siga a ROTINA normalmente a partir do passo 1." % (" --extra" if a.extra else ""))
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
        alertas.append("GAP > 7 dias (a última janela terminou em %s): cobrir só 7 dias e dizer em "
                       "email.limitacoes que o intervalo além do teto pode ter lacunas" % inicio.isoformat())
        inicio = agora - timedelta(days=7)
    horas = (agora - inicio).total_seconds() / 3600
    ult_data = datetime.fromisoformat(ult["date"]).date() if ult.get("date") else hoje - timedelta(days=1)
    # gap e "dia sem registro" contam dias de EDICAO (seg-sex, feriado incluido: a edicao sai em feriado);
    # o desconto do feriado nacional fica so onde mede trabalho das fontes (rodizio)
    gap = feriados.dias_de_edicao_entre(ult_data, hoje) > 1
    primeira = agora.weekday() == 0 or ult_data.isocalendar()[1] != hoje.isocalendar()[1] or gap
    recesso = em_recesso(hoje)
    # E4/F1: dia de edicao (seg-sex, feriado incluido) entre a ultima execucao registrada e hoje, sem registro
    sem_registro = feriados.uteis_sem_registro(ult_data, hoje) if ult.get("date") else []
    if sem_registro:
        alertas.append("dia útil sem execução registrada: %s (última registrada: %s) — antes de coletar, confira "
                       "in:sent: uma edição enviada sem registro (queda ou PUSH: FALHOU) seria repetida"
                       % (", ".join(d.strftime("%d/%m") + (" (feriado: a edição sai em feriado)"
                                                           if feriados.eh_feriado_nacional(d) else "")
                                    for d in sem_registro), ult_data.strftime("%d/%m")))
    fer_hoje = feriados.feriado(hoje)
    fer_janela = feriados.no_intervalo(inicio.date(), hoje)
    fer_txt = "; ".join(feriados.agrupar(fer_janela))

    q = ler("munger-quotes.json")
    idx = (doy + (1 if a.extra else 0)) % len(q["quotes"])
    cit = q["quotes"][idx]
    fontes_m = {f["id"]: f["titulo"] for f in q.get("fontes", [])}

    ant_br = ult_data.strftime("%d/%m/%Y")
    # rodape: o proximo dia de edicao (seg-sex; a edicao sai em feriado). Sexta e (Extra de) sabado ->
    # "segunda-feira"; domingo e seg-qui -> "amanhã" (a edicao normal sempre fez assim)
    prox = hoje + timedelta(days=1)
    while prox.weekday() >= 5:
        prox += timedelta(days=1)
    rodape = "amanhã" if prox == hoje + timedelta(days=1) else DIAS[prox.weekday()]
    fmt = "%d/%m %H:%M"
    # F8: o after: do Gmail e a DATA do inicio da janela (o Gmail le a data a meia-noite do Pacifico,
    # antes das 6h BRT). So quando a janela comeca de madrugada (antes das 06:00) volta um dia.
    # after:<epoch> devolve {} no MCP do Gmail (armadilha gmail_after_epoch): sempre data.
    gmail_apos = (inicio.date() - timedelta(days=1 if inicio.hour < 6 else 0)).strftime("%Y/%m/%d")
    recesso_txt = "sim — fluxo reduzido de STF/STJ é normal" if recesso else "não"
    if fer_janela:
        recesso_txt += ("; feriado na janela: %s — silêncio de Planalto, Câmara, STF e STJ nesses dias é normal"
                        % fer_txt)

    janela = {"data": hoje.isoformat(), "doy": doy, "execution_id": exec_id, "gmail_apos": gmail_apos,
              "inicio": inicio.isoformat(), "fim": agora.isoformat(), "epoch_inicio": int(inicio.timestamp()),
              "primeira_semana": primeira, "recesso": recesso,
              "tipo": "extra" if a.extra else "diaria", "edicao_extra": bool(a.extra),
              "cabecalho_extra": "Edição extra" if a.extra else "",
              "feriado_hoje": fer_hoje, "feriados_na_janela": fer_janela,
              "dias_uteis_sem_registro": [d.isoformat() for d in sem_registro],
              "assunto": assunto_hoje,
              "assunto_anterior": ult.get("email_subject") or ASSUNTO % ant_br,
              "execucao_anterior": ult.get("execution_id"), "draft_id_anterior": ult.get("draft_id"),
              "ignorar_execucao": ignorar_exec,
              # lidos pelo montar_email.py: cabecalho, rodape e Munger nao sao redigitados
              "hoje_br": hoje_br, "dia_semana": DIAS[agora.weekday()], "rodape": rodape,
              "munger": {"texto": cit["pt"], "fonte": fontes_m.get(cit.get("fonte"), cit.get("fonte")),
                         "obs": cit.get("obs") or "", "tipo": cit.get("tipo") or "", "idx": idx}}
    gravar_json(tmp("janela.json"), janela)
    # B3/C9: o passo 2 roda enquanto o orquestrador le e lanca os coletores
    try:
        os.remove(tmp("fontes_status.json"))       # status velho de outra execucao (contrato INF/WEB)
    except OSError:
        pass
    desligado = a.sem_disparo or os.environ.get("ROBOZINHO_DISPARO", "1") == "0"
    disparados = disparar_passo2(exec_id, desligado)

    # ---- variaveis dos prompts dos coletores
    fontes = {f["id"]: f for f in ledger.get("fontes", [])}
    armad = {x["id"]: x for x in ledger.get("armadilhas", [])}
    # errata_* e correcao para o leitor (o montador a publica), nao tarefa do coletor: o texto dela casa
    # PALAVRAS_CONCURSO ("inscri") e gastava uma busca de pendencia ativa
    pend_conc = [p for p in ledger.get("pendencias_vivas", [])
                 if not str(p.get("id", "")).startswith("errata_") and (
                     p.get("coletor") == "concursos" or
                     (not p.get("coletor") and p.get("faixa") != "cronica"
                      and PALAVRAS_CONCURSO.search(p.get("texto", ""))))]
    concursos = ledger.get("concursos", [])
    rede = alcancaveis([p.get("dominio_oficial") for p in pend_conc] +
                       [c.get("dominio_oficial") for c in concursos])
    # banca oficial lida por script (work/bancas.py): o que ela cobre sai da fila do coletor
    try:
        import bancas
        banca = bancas.coletar(hoje, concursos, bancas.carregar_estado())
    except Exception as e:  # noqa: BLE001 — a banca e reforco, nunca bloqueia a edicao
        bancas = None
        banca = {"banca": "FGV", "http": 0, "concursos": [], "erro": str(e), "data": hoje.isoformat()}
    banca["execution_id"] = exec_id
    gravar_json(tmp("bancas.json"), banca)
    cobertos = {i for c in banca["concursos"] for i in c.get("coberto") or []}
    na_banca = {i for c in banca["concursos"] for i in c.get("registros") or []}
    divergentes = {d["id"] for c in banca["concursos"] for d in c.get("divergencias") or []}
    # DIVERGE DO REGISTRO: a banca lida hoje contradiz o registro -> nao conta como "banca lida" no selo
    ctx_selo = bancas.contexto_selos(banca, concursos, hoje, upd={}) if bancas else {}
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
    pend_no_coletor = {p["id"] for p in pend_conc if p["id"] not in pend_coberta}

    # prazos do registro: <= 7 dias e vencidos recentes vao primeiro na fila do coletor. A faixa dos
    # vencidos cobre o intervalo desde a ultima execucao (fim de semana, feriado, falha), de 3 a 7 dias.
    lim_venc = min(7, max(3, (hoje - ult_data).days))
    proximos, vencidos = [], []
    for c in concursos:
        for pz in c.get("prazos") or []:
            try:
                d = date.fromisoformat(pz.get("data", ""))
            except ValueError:
                continue
            dias = (d - hoje).days
            if -lim_venc <= dias < 0:
                vencidos.append((dias, d, c, pz))
            elif 0 <= dias <= FOCO_PRAZO_DIAS:
                proximos.append((dias, d, c, pz))
    proximos.sort(key=lambda x: x[0])
    fila = lambda x: x[2].get("id") not in cobertos      # so vai ao coletor o que a banca nao cobriu
    fmt_pz = lambda dias, d, c, pz: "%s (%s) %s — %s [%s] (id %s)" % (
        d.strftime("%d/%m"), quando(dias), orgao(c), pz.get("evento"),
        "confirmado" if pz.get("confirmado") else "a confirmar", c.get("id"))
    prioridade = (["- confirmar desfecho: " + fmt_pz(*x) for x in vencidos if fila(x)] +
                  ["- " + fmt_pz(*x) for x in proximos if x[0] <= 7 and fila(x)])
    na_fila = {x[2].get("id") for x in vencidos} | {x[2].get("id") for x in proximos if x[0] <= 7}

    # rodizio: os registros com verificacao mais antiga (fora da fila de prazos) ganham busca propria
    def idade(c):
        try:
            return dias_uteis_entre(date.fromisoformat(c.get("verificado_em", "")), hoje)
        except ValueError:
            return 999
    velhos = sorted((c for c in concursos if c.get("id") not in na_fila | cobertos and idade(c) >= RODIZIO_DIAS),
                    key=idade, reverse=True)[:RODIZIO_N]
    rodizio = ["- %s (id %s; verificado há %d dias úteis; selo %s): %s" % (
        orgao(c), c.get("id"), idade(c), c.get("selo"), c.get("linha", "")) +
        (" | página oficial %s acessível: leia por curl antes de buscar" % c["dominio_oficial"]
         if c.get("dominio_oficial") and rede.get(c["dominio_oficial"]) else "")
        for c in velhos]
    tema, consultas = DESCOBERTA.get(0 if primeira else agora.weekday(), DESCOBERTA[0])
    consultas = [q_.format(mes=MESES_PT[hoje.month - 1], ano=hoje.year) for q_ in consultas]
    acompanhados = "; ".join("%s [%s]" % (orgao(c), c.get("id")) for c in concursos)
    regra = ("1ª execução da semana (ou após gap): até 12 WebSearch — 4 em prazos/pendências "
             "(ativa E longo_prazo), 3 no rodízio, 5 na descoberta (varredura geral)."
             if primeira else
             "dia comum: até 9 WebSearch — 3 em prazos/pendências ativa, 3 no rodízio, 3 na descoberta "
             "da carreira do dia; nas longo_prazo, só movimento NOVO.")

    # selo por data (work/selos.py) — o montador e o helper aplicam sozinhos; aqui so se avisa
    selo_auto, selo_alerta = [], []
    encerrada_pela_banca = {}       # id -> (fim, ultima retificacao): o desfecho do prazo vencido ja esta confirmado
    for c in concursos:
        x = ctx_selo.get(c.get("id")) or {}
        s, m = selos.selo_por_data(c, hoje, banca_lida_hoje=x.get("banca_lida_hoje", False),
                                   ultima_retificacao=x.get("ultima_retificacao"),
                                   inicio_inscricoes_banca=x.get("inicio_inscricoes"))
        fim, _ = selos.fim_inscricoes(c)
        ret = selos._data(x.get("ultima_retificacao"))
        if (s == "INSCRIÇÕES ENCERRADAS" and x.get("banca_lida_hoje") and fim and fim < hoje
                and (ret is None or fim > ret)):
            encerrada_pela_banca[c["id"]] = (fim, ret)
        if s == selos.SELO_SEM_CONFIRMACAO and s != c.get("selo"):
            selo_alerta.append("%s %s" % (c["id"], m))      # prazo vencido sem confirmacao: decisao do orquestrador
        elif s != c.get("selo"):
            selo_auto.append("%s %s" % (c["id"], m))
        elif m:
            selo_alerta.append("%s: %s" % (c["id"], m))
    candidatos = [c["id"] for c in concursos if selos.candidato_remocao(c, hoje, REMOCAO_DIAS)]

    # foco do dia: linha completa no LEDGER (os demais, so contados)
    motivos = {}
    ativas = {p["id"] for p in ledger.get("pendencias_vivas", []) if p.get("faixa") == "ativa"}
    for x in vencidos + proximos:
        motivos.setdefault(x[2]["id"], []).append("prazo %s" % x[1].strftime("%d/%m"))
    for c in concursos:
        m = motivos.setdefault(c["id"], [])
        try:
            if (hoje - date.fromisoformat(c.get("mudou_em", ""))).days <= FOCO_MUDANCA_DIAS:
                m.append("mudou %s" % br(c["mudou_em"]))
        except ValueError:
            pass
        if c.get("pendencia") in ativas:
            m.append("pendência ativa")
        if c["id"] in na_banca:
            m.append("banca lida hoje")
        if c["id"] in divergentes:
            m.append("DIVERGE")
        if c["id"] in candidatos:
            m.append("candidato a remoção")
    for c in velhos:
        motivos.setdefault(c["id"], []).append("rodízio")
    motivos = {k: list(dict.fromkeys(v)) for k, v in motivos.items() if v}
    foco = set(motivos)
    # B10: pagina oficial (url_oficial) dos concursos em foco, lida por script; so-JavaScript sai do "acessivel"
    paginas = []
    if any(c.get("url_oficial") and c["id"] in foco for c in concursos):
        try:
            import paginas_oficiais
            paginas = paginas_oficiais.verificar(concursos, bancas.carregar_estado() if bancas else {},
                                                 hoje.isoformat(), ids=foco)
        except Exception as e:  # noqa: BLE001 — reforco, nunca bloqueia
            paginas = [{"id": "-", "url": "", "http": 0, "situacao": "HTTP", "erro": str(e)}]
        for r in paginas:
            if r.get("situacao") == "SEM_TEXTO":
                rede[selos.host(r["url"])] = False
    gravar_json(tmp("paginas_oficiais.json"), {"data": hoje.isoformat(), "execution_id": exec_id, "paginas": paginas})

    vars_ = {
        "HOJE_BR": hoje_br, "DIA_SEMANA": DIAS[agora.weekday()],
        "INICIO": inicio.isoformat(), "FIM": agora.isoformat(),
        "INICIO_BR": inicio.strftime(fmt), "FIM_BR": agora.strftime(fmt),
        "EPOCH": str(int(inicio.timestamp())), "HORAS": "%.0f" % horas,
        "GMAIL_APOS": gmail_apos,
        "PRIMEIRA_SEMANA": "sim" if primeira else "não",
        "RECESSO": recesso_txt,
        "FERIADOS": fer_txt or "nenhum",
        "FERIADO_HOJE": feriados.rotulo(fer_hoje) if fer_hoje else "não",
        "REGRA_FAIXA": regra,
        "PENDENCIAS_CONCURSOS": "\n".join(linhas) or "- (nenhuma pendência de concurso no ledger)",
        "CONCURSOS_PRIORIDADE": "\n".join(prioridade) or "- (nenhum prazo nos próximos 7 dias)",
        "CONCURSOS_RODIZIO": "\n".join(rodizio) or "- (todos verificados nos últimos %d dias úteis)" % RODIZIO_DIAS,
        "DESCOBERTA_TEMA": tema,
        "DESCOBERTA_CONSULTAS": "\n".join("- `%s`" % q_ for q_ in consultas),
        "CONCURSOS_ACOMPANHADOS": acompanhados or "(nenhum)",
        "BANCA_COBERTOS": "; ".join("%s (id %s)" % (orgao(c), c["id"]) for c in concursos
                                    if c["id"] in cobertos) or "(nenhum hoje)",
        "REGISTRO_ATUAL": registro_atual(concursos, foco).strip(),
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
        bruto = open(modelo, encoding="utf-8").read()
        texto = re.sub(r"\{\{([A-Z_]+(?::[a-z0-9_]+)?)\}\}", sub, bruto)
        if os.path.basename(modelo) == "coletor-concursos.md" and "{{REGISTRO_ATUAL}}" not in bruto:
            texto = texto.rstrip("\n") + "\n" + registro_atual(concursos, foco)
        destino = tmp(os.path.basename(modelo))
        with open(destino, "w", encoding="utf-8") as f:
            f.write(texto)
        sobra = re.findall(r"\{\{[^}]+\}\}", texto)
        gerados.append(destino + (" (PLACEHOLDER SOBRANDO: %s)" % sobra if sobra else ""))

    # ---------------------------------------------------------------- saida
    out = []
    out.append("HOJE %s (%s) %s | doy=%d | execution_id=%s%s" % (
        hoje_br, DIAS[agora.weekday()], agora.strftime("%H:%M:%S %z"), doy, exec_id,
        " | EDIÇÃO EXTRA" if a.extra else ""))
    out.append("ASSUNTO HOJE:     %s" % janela["assunto"])
    out.append("ASSUNTO ANTERIOR: %s | exec %s | delivery %s | draft_id %s" % (
        janela["assunto_anterior"], ult.get("execution_id"), ult.get("delivery"), ult.get("draft_id")))
    out.append("JANELA: %s -> %s (%.1fh) | Gmail after:%s + filtrar pelo horário interno >= %s | 1a da semana: %s | "
               "gap: %s | recesso: %s" % (janela["inicio"], janela["fim"], horas, gmail_apos, inicio.strftime(fmt),
                                          vars_["PRIMEIRA_SEMANA"], "sim" if gap else "não", "sim" if recesso else "não"))
    out.append("  (herdada = anterior a %s)" % (agora - timedelta(hours=24)).strftime(fmt))
    if fer_hoje:
        out.append("FERIADO HOJE: %s — a edição sai normalmente; silêncio das fontes oficiais é esperado"
                   % feriados.rotulo(fer_hoje))
    if fer_janela:
        out.append("FERIADOS NA JANELA: %s" % fer_txt)
    out.append("MUNGER idx=%d/%d tipo=%s | cabeçalho, rodapé (\"Próxima edição: %s\") e citação vão do janela.json "
               "para o montador" % (idx, len(q["quotes"]), cit.get("tipo") or "?", rodape))
    out.append("PENDENCIAS DE CONCURSO p/ coletor: %d (orçamento de buscas no coletor-concursos.md)" % len(pend_conc))
    radar = [fmt_pz(*x) for x in proximos if x[3].get("confirmado")]
    a_conf = {}
    for x in proximos:
        if not x[3].get("confirmado"):
            a_conf.setdefault(x[2]["id"], []).append(x[1].strftime("%d/%m"))
    out.append("CONCURSOS: %d no registro | PRAZOS confirmados em fonte oficial (30 dias): %s" % (
        len(concursos), "; ".join(radar) or "nenhum"))
    if a_conf:
        out.append("  só em fonte secundária (o quadro os lista à parte, em cinza; evento no LEDGER): " +
                   "; ".join("%s %s" % (i, ", ".join(ds)) for i, ds in a_conf.items()))
    for x in vencidos:
        enc = encerrada_pela_banca.get(x[2].get("id"))
        if (enc and x[3].get("confirmado") and selos.classe_prazo(x[3]) == "inscricoes_fim"
                and x[1] <= enc[0]):
            # a banca lida hoje confirma o encerramento (sem retificacao depois do prazo): o ALERTA gastaria
            # uma busca para confirmar o que a linha SELO POR DATA ja diz
            out.append("PRAZO VENCIDO (sem ação): %s — encerramento confirmado pela banca oficial lida hoje (%s): "
                       "selo INSCRIÇÕES ENCERRADAS automático" % (
                           fmt_pz(*x), "última retificação %s" % enc[1].strftime("%d/%m") if enc[1] else
                           "sem retificação"))
            continue
        out.append("ALERTA: prazo vencido %s — confirmar desfecho/prorrogação e atualizar o registro "
                   "(ledger_updates.concursos)" % fmt_pz(*x))
    for s in selo_auto:
        out.append("SELO POR DATA: %s (automático no e-mail e no registro; não escreva o selo)" % s)
    for s in selo_alerta:
        out.append("ALERTA: selo por data — %s" % s)
    for i in candidatos:
        out.append("ALERTA: candidato a remoção (%s) — todos os prazos confirmados venceram há mais de %d dias e "
                   "não há etapa futura: confirme o desfecho e remova (remover + desfecho) ou atualize"
                   % (i, REMOCAO_DIAS))
    bloq = [d for d, ok in rede.items() if not ok]
    out.append("REDE: páginas oficiais bloqueadas: %s | acessíveis: %s" % (
        ", ".join(bloq) or "nenhuma", ", ".join(d for d, ok in rede.items() if ok) or "nenhuma"))
    for p in ledger.get("pendencias_vivas", []):
        if p.get("faixa") == "ativa" and int(p.get("execucoes") or 0) >= LIMITE_ATIVA:
            alertas.append("pendência %s ativa há %s execuções (limite %d): no passo 4, em "
                           "ledger_updates.pendencias, rebaixar a faixa (longo_prazo/cronica) ou remover "
                           "— a validação recusa sem isso" % (p["id"], p.get("execucoes"), LIMITE_ATIVA))
    out.append("CONCURSOS COLETOR: rodízio=%d registro(s) | descoberta do dia: %s" % (len(velhos), tema))
    out += ["ALERTA: " + al for al in alertas]
    print("\n".join(out))
    print()
    if banca.get("concursos"):
        bancas.imprimir(banca)
    else:
        print("BANCA FGV: não lida (%s) — concursos da FGV seguem pelo coletor."
              % (banca.get("erro") or "http %s" % banca.get("http")))
    if paginas:
        try:              # a pagina oficial e reforco: nunca derruba o passo 1 (modulo ausente num merge parcial)
            import paginas_oficiais
            print("\n".join(paginas_oficiais.linhas_saida(paginas)))
        except Exception as e:  # noqa: BLE001
            print("PAGINA OFICIAL: não lida (%s) — os concursos com url_oficial seguem pelo coletor"
                  % (next((r.get("erro") for r in paginas if r.get("erro")), None) or e))
    print("\n".join(resumo_ledger(ledger, foco, motivos, pend_no_coletor)))
    print("PROMPTS: " + " ".join(gerados))
    print("PASSO 2 (uma mensagem): 3 buscas de anti-duplicata no Gmail + Agent coletor-gmail, coletor-jota e "
          "coletor-concursos (primeiro plano) + Bash: python3 work/aguardar_coleta.py — %s" % (
              "coleta_web, informativos e versiculo já rodam em segundo plano desde agora" if disparados else
              "ele roda coleta_web, informativos e versiculo"))


if __name__ == "__main__":
    main()
