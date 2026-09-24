#!/usr/bin/env python3
# =====================================================================
# Update-Historico.py - porte Python do helper oficial de gravacao do
# historico da newsletter "Robozinho dos Momozis ate Passar", para uso
# no ambiente de nuvem (Linux) das rotinas agendadas.
#
# Replica fielmente work/Update-Historico.ps1 (PowerShell/Windows):
# reconciliacao de entrega, anti-duplicata por execution_id,
# arquivamento (max_execucoes), gravacao UTF-8 sem BOM, deteccao de
# mojibake e emissao de robozinho-estado.json.
#
# USO TIPICO:
#   python3 work/Update-Historico.py \
#       --nova-execucao "<path>/nova-execucao.json" \
#       --reconciliar-id "2026-07-21-7h" \
#       --reconciliar-message-id "19f84bc9b511e67e" \
#       --relatorio-path "<scratchpad>/relatorio.txt"
#
#   Com --ledger work/robozinho-aprendizado.json, aplica tambem os
#   contadores mecanicos do ledger (ultimo_sucesso, sem_sucesso,
#   dias_sem_email, execucoes das pendencias, atualizado_em) a partir de
#   source_status e pendencias da nova execucao. So 1 vez por execution_id.
#
#   ANTES de gravar, valida a nova execucao: categoria (lista fechada, com
#   apelidos normalizados), status (lista fechada de selos do prompt
#   mestre; sufixo "(...)" vai para observacao), chave (5 partes,
#   minusculas), URL sem wrapper/rastreio. Erro -> nada e gravado, exit 2.
#   Chave ja publicada em execucao anterior -> aviso REPUBLICADA.
# =====================================================================

import argparse
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, date

CATEGORIAS = [
    "Planalto/Legislação", "STF Notícias", "STF Jurisprudência", "STJ Notícias",
    "STJ Jurisprudência", "Informativos", "Concursos - Carreira", "Concursos - Apoio",
    "Mídia", "Opinião/Análise", "Fofoquinha", "Versículo", "Munger",
]
SELOS = [
    "NOVO", "URGENTE", "INSCRIÇÕES ABERTAS", "INSCRIÇÕES ENCERRADAS", "ENCERRA EM BREVE",
    "ENCERRA HOJE", "EDITAL PUBLICADO", "EM ANDAMENTO", "EM PLANEJAMENTO", "PROVA EM BREVE",
    "PROVA REALIZADA", "CONFIRMADO", "CONFIRMADO POR FONTE OFICIAL",
    "CONFIRMADO POR FONTE OFICIAL ALTERNATIVA", "FORTE INDÍCIO", "RUMOR",
    "SEM CONFIRMAÇÃO OFICIAL", "PENDÊNCIA", "PENDÊNCIA DE VERIFICAÇÃO",
    "MÍDIA ESPECIALIZADA", "OPINIÃO/ANÁLISE", "VERSÍCULO DO DIA", "SABEDORIA DO DIA",
]
SELO_FIXO = {"Opinião/Análise": "OPINIÃO/ANÁLISE", "Versículo": "VERSÍCULO DO DIA",
             "Munger": "SABEDORIA DO DIA"}
STATUS_FONTE = ("ok", "vazio", "falha", "nao_tentada")


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or ""))
    return re.sub(r"[^a-z]", "", "".join(c for c in s if not unicodedata.combining(c)).lower())


ALIAS_CAT = {norm(c): c for c in CATEGORIAS}
ALIAS_CAT.update({
    "planalto": "Planalto/Legislação", "legislacao": "Planalto/Legislação",
    "planaltolei": "Planalto/Legislação", "planaltompv": "Planalto/Legislação",
    "stfnoticia": "STF Notícias", "stfdecisao": "STF Notícias", "stjnoticia": "STJ Notícias",
    "informativo": "Informativos", "stfinformativo": "Informativos", "stjinformativo": "Informativos",
    "concurso": "Concursos - Carreira",
    "concursos": "Concursos - Carreira", "concursocarreira": "Concursos - Carreira",
    "concursoapoio": "Concursos - Apoio", "midia": "Mídia", "clipping": "Mídia",
    "opiniao": "Opinião/Análise", "fofoca": "Fofoquinha", "versiculo": "Versículo",
    "sabedoria": "Munger",
})
ALIAS_SELO = {norm(s): s for s in SELOS}


def validar(ex, chaves_anteriores):
    """Normaliza ex no lugar. Devolve (erros, avisos)."""
    erros, avisos = [], []
    for campo in ("execution_id", "date", "window_start", "window_end", "email_subject",
                  "delivery", "items"):
        if campo not in ex or ex[campo] in (None, ""):
            erros.append("campo obrigatorio ausente: " + campo)
    if ex.get("delivery") not in ("draft", "draft_ja_existente", "sent"):
        erros.append("delivery invalido: %r" % ex.get("delivery"))
    if ex.get("delivery") == "draft" and not ex.get("draft_id"):
        erros.append("delivery=draft sem draft_id")
    vistas = set()
    for n, it in enumerate(ex.get("items") or []):
        ch = it.get("chave") or ""
        rot = ch or "item %d" % n
        cat = ALIAS_CAT.get(norm(it.get("categoria")))
        if not cat:
            erros.append("%s: categoria fora da lista %r" % (rot, it.get("categoria")))
        else:
            it["categoria"] = cat
        base, _, resto = (it.get("status") or "").partition(" (")
        selo = SELO_FIXO.get(cat) or ALIAS_SELO.get(norm(base))
        if not selo:
            erros.append("%s: status fora da lista fechada de selos %r" % (rot, it.get("status")))
        else:
            if resto:
                it["observacao"] = ((it.get("observacao") or "") + " (" + resto).strip()
            if selo != it.get("status"):
                avisos.append("%s: status normalizado %r -> %r" % (rot, it.get("status"), selo))
            it["status"] = selo
        partes = ch.split("|")
        if ch != ch.lower() or " " in ch or len(partes) != 5 or not all(partes):
            erros.append("%s: chave malformada (esperado fonte|tipo|slug|ano|data, minusculas)" % rot)
        if ch in vistas:
            erros.append("%s: chave duplicada nesta execucao" % rot)
        vistas.add(ch)
        if ch in chaves_anteriores:
            avisos.append("REPUBLICADA (chave ja saiu em edicao anterior): " + ch)
        if re.search(r"t\.rdsv2\.net|google\.com/url|[?&]utm_", it.get("url") or ""):
            erros.append("%s: URL com wrapper/rastreio: %s" % (rot, it.get("url")))
    for fid, v in (ex.get("source_status") or {}).items():
        if v not in STATUS_FONTE:
            avisos.append("source_status[%s]=%r fora de %s (contador do ledger nao aplicado)"
                          % (fid, v, "/".join(STATUS_FONTE)))
    for nome, uso in (ex.get("coletores") or {}).items():
        if not all(isinstance((uso or {}).get(k), int) for k in ("tokens", "chamadas", "duracao_ms")):
            avisos.append("coletores[%s] sem tokens/chamadas/duracao_ms inteiros" % nome)
    return erros, avisos


def gravar_ledger(caminho, led):
    """Uma entrada de lista por linha: compacto para ler e estavel para diff."""
    partes = []
    for k, v in led.items():
        if isinstance(v, list) and v:
            corpo = ",\n".join("    " + json.dumps(x, ensure_ascii=False) for x in v)
            partes.append("  %s: [\n%s\n  ]" % (json.dumps(k), corpo))
        else:
            partes.append("  %s: %s" % (json.dumps(k), json.dumps(v, ensure_ascii=False)))
    texto = "{\n" + ",\n\n".join(partes) + "\n}\n"
    json.loads(texto)
    with open(caminho, "w", encoding="utf-8", newline="") as f:
        f.write(texto)


def aplicar_ledger(caminho, ex, add_log):
    led = read_json(caminho)
    if led.get("atualizado_por_execucao") == ex["execution_id"]:
        add_log("Ledger: contadores ja aplicados para %s — nada a fazer." % ex["execution_id"])
        return
    hoje = ex["date"]
    fontes = {f.get("id"): f for f in led.get("fontes") or []}
    for fid, v in (ex.get("source_status") or {}).items():
        f = fontes.get(fid)
        if f is None:
            add_log("Ledger: fonte '%s' nao existe no ledger (criar so se mudar uma decisao)." % fid)
            continue
        if v == "ok":
            f["ultimo_email" if "ultimo_email" in f else "ultimo_sucesso"] = hoje
            if "dias_sem_email" in f:
                f["dias_sem_email"] = 0
            if "sem_sucesso" in f:
                f["sem_sucesso"] = 0
            if f.get("status") == "mudo":
                f["status"], f["voltou_em"] = "saudavel", hoje
                add_log("Ledger: fonte %s VOLTOU -> saudavel (revise a nota)." % fid)
        elif v in ("vazio", "falha"):
            if v == "vazio" and f.get("status") == "intermitente":
                continue
            f["sem_sucesso"] = int(f.get("sem_sucesso") or 0) + 1
            if f.get("ultimo_email"):
                f["dias_sem_email"] = (date.fromisoformat(hoje) - date.fromisoformat(f["ultimo_email"])).days
            if f.get("status") == "saudavel" and f["sem_sucesso"] >= 5:
                f["status"] = "mudo"
                add_log("Ledger: fonte %s REBAIXADA -> mudo (%d execucoes sem sucesso; revise a nota)."
                        % (fid, f["sem_sucesso"]))
    ids = {p.get("id") for p in ex.get("pendencias") or [] if p.get("id")}
    no_ledger = set()
    for p in led.get("pendencias_vivas") or []:
        no_ledger.add(p.get("id"))
        if p.get("id") in ids:
            p["execucoes"] = int(p.get("execucoes") or 0) + 1
            if p.get("faixa") == "ativa" and p["execucoes"] > 21:
                add_log("Ledger: pendencia %s ativa ha %d execucoes (>21) — rebaixar ou aposentar."
                        % (p["id"], p["execucoes"]))
        else:
            add_log("Ledger: pendencia %s nao foi a edicao — se resolvida, remova-a." % p.get("id"))
    for novo in sorted(ids - no_ledger):
        add_log("Ledger: pendencia %s saiu na edicao mas nao existe no ledger." % novo)
    led["atualizado_em"] = now_iso_with_offset()
    led["atualizado_por_execucao"] = ex["execution_id"]
    gravar_ledger(caminho, led)
    add_log("Ledger: contadores aplicados e JSON validado.")


def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json_no_bom(path, data):
    with open(path, "w", encoding="utf-8", newline="") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def now_iso_with_offset():
    # Fuso da newsletter, nao o do container (que e UTC na nuvem).
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("America/Sao_Paulo")).isoformat(timespec="seconds")
    except Exception:
        return datetime.now().astimezone().isoformat(timespec="seconds")


def metricas_derivadas(historico, execucoes_principal):
    """Numeros que antes eram mantidos a mao no ledger (metricas.itens_ultimas_10,
    media). Calculados do historico para nao depender de aritmetica manual.
    Tambem agrega o uso dos coletores (campo opcional `coletores` de cada
    execucao: {nome: {tokens, chamadas, duracao_ms, modelo}})."""
    pasta = os.path.dirname(os.path.abspath(historico_path_global))
    arquivadas = 0
    for nome in historico.get("archive_files") or []:
        caminho = os.path.join(pasta, nome)
        if os.path.exists(caminho):
            try:
                arquivadas += len(read_json(caminho).get("executions") or [])
            except Exception:
                pass

    ult10 = execucoes_principal[-10:]
    itens = [len(e.get("items") or []) for e in ult10]
    media = round(sum(itens) / len(itens), 1) if itens else 0

    coletores = {}
    for e in ult10:
        for nome, uso in (e.get("coletores") or {}).items():
            c = coletores.setdefault(
                nome, {"execucoes": 0, "tokens_total": 0, "chamadas_total": 0}
            )
            c["execucoes"] += 1
            c["tokens_total"] += int(uso.get("tokens") or 0)
            c["chamadas_total"] += int(uso.get("chamadas") or 0)
    for c in coletores.values():
        n = c["execucoes"] or 1
        c["tokens_media"] = round(c["tokens_total"] / n)
        c["chamadas_media"] = round(c["chamadas_total"] / n, 1)

    ultima = ult10[-1] if ult10 else {}
    return {
        "execucoes_registradas": len(execucoes_principal) + arquivadas,
        "itens_ultimas_10": itens,
        "media_itens": media,
        "itens_ultima": itens[-1] if itens else 0,
        "coletores_ultima": ultima.get("coletores") or {},
        "coletores_ultimas_10": coletores,
    }


historico_path_global = ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--nova-execucao", required=True, dest="nova_execucao_path")
    parser.add_argument(
        "--historico",
        dest="historico_path",
        default=os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "resumo-legislativo-historico.json",
        ),
    )
    parser.add_argument("--reconciliar-id", dest="reconciliar_id", default="")
    parser.add_argument(
        "--reconciliar-message-id", dest="reconciliar_message_id", default=""
    )
    parser.add_argument("--max-execucoes", dest="max_execucoes", type=int, default=10)
    parser.add_argument("--relatorio-path", dest="relatorio_path", default="")
    parser.add_argument("--ledger", dest="ledger_path", default="")
    args = parser.parse_args()

    log = []

    def add_log(linha):
        log.append(linha)

    def emitir(status_final):
        add_log(status_final)
        texto = "\n".join(log)
        if args.relatorio_path:
            with open(args.relatorio_path, "w", encoding="utf-8", newline="") as f:
                f.write(texto)
        print(texto)

    # -------------------------------------------------------------
    # 1. Carregar historico e nova execucao
    # -------------------------------------------------------------
    if not os.path.exists(args.historico_path):
        envelope = {
            "schema_version": 1,
            "timezone": "America/Sao_Paulo",
            "newsletter": None,
            "recipients": [],
            "archive_files": [],
            "executions": [],
        }
        write_json_no_bom(args.historico_path, envelope)
        add_log("AVISO: historico inexistente; envelope novo criado.")

    historico = read_json(args.historico_path)
    historico.setdefault("executions", [])
    historico.setdefault("archive_files", [])

    if not os.path.exists(args.nova_execucao_path):
        raise SystemExit(
            f"Arquivo da nova execucao nao encontrado: {args.nova_execucao_path}"
        )
    nova_exec = read_json(args.nova_execucao_path)

    if not nova_exec.get("execution_id"):
        raise SystemExit("A nova execucao nao possui execution_id.")
    add_log("Nova execucao: " + nova_exec["execution_id"])

    chaves_anteriores = {
        it.get("chave")
        for e in historico["executions"]
        if e.get("execution_id") != nova_exec["execution_id"]
        for it in e.get("items") or []
        if it.get("chave")
    }
    erros, avisos = validar(nova_exec, chaves_anteriores)
    for a in avisos:
        add_log("AVISO: " + a)
    if erros:
        for e in erros:
            add_log("ERRO: " + e)
        emitir("STATUS: ERRO DE VALIDACAO — nada foi gravado. Corrija o arquivo da "
               "nova execucao e rode de novo.")
        sys.exit(2)
    # grava a versao normalizada, para o historico ficar consistente
    write_json_no_bom(args.nova_execucao_path, nova_exec)

    # -------------------------------------------------------------
    # 2. Reconciliacao de entrega da edicao anterior (opcional)
    # -------------------------------------------------------------
    if args.reconciliar_id:
        alvo = next(
            (
                e
                for e in historico["executions"]
                if e.get("execution_id") == args.reconciliar_id
            ),
            None,
        )
        if alvo is None:
            add_log("AVISO: execucao a reconciliar nao encontrada: " + args.reconciliar_id)
        else:
            alvo["delivery"] = "sent"
            if args.reconciliar_message_id:
                alvo["gmail_message_id"] = args.reconciliar_message_id
            alvo["delivery_reconciled_at"] = now_iso_with_offset()
            add_log("Reconciliado: " + args.reconciliar_id + " -> delivery=sent")

    # -------------------------------------------------------------
    # 3. Anti-duplicata: nunca gravar a mesma execution_id duas vezes
    # -------------------------------------------------------------
    ja_existe = any(
        e.get("execution_id") == nova_exec["execution_id"]
        for e in historico["executions"]
    )
    if ja_existe:
        add_log(
            "AVISO: execution_id ja existia no historico e sera SUBSTITUIDO: "
            + nova_exec["execution_id"]
        )
    restantes = [
        e
        for e in historico["executions"]
        if e.get("execution_id") != nova_exec["execution_id"]
    ]
    historico["executions"] = restantes + [nova_exec]

    # -------------------------------------------------------------
    # 4. Arquivamento: manter no maximo max_execucoes no arquivo
    #    principal (nunca apagar - apenas mover para o arquivo morto
    #    do mes)
    # -------------------------------------------------------------
    total = len(historico["executions"])
    if total > args.max_execucoes:
        excedente = total - args.max_execucoes
        para_arquivar = historico["executions"][:excedente]
        historico["executions"] = historico["executions"][excedente:]

        pasta_hist = os.path.dirname(os.path.abspath(args.historico_path))

        for item in para_arquivar:
            data_ref = item.get("date") or datetime.now().strftime("%Y-%m-%d")
            ano_mes = data_ref[0:7]
            arquivo_morto = os.path.join(
                pasta_hist, f"resumo-legislativo-historico-arquivo-{ano_mes}.json"
            )

            if os.path.exists(arquivo_morto):
                arq = read_json(arquivo_morto)
            else:
                arq = {
                    "schema_version": historico.get("schema_version"),
                    "timezone": historico.get("timezone"),
                    "newsletter": historico.get("newsletter"),
                    "recipients": historico.get("recipients"),
                    "executions": [],
                }

            ja_arquivado = any(
                e.get("execution_id") == item.get("execution_id")
                for e in arq["executions"]
            )
            if not ja_arquivado:
                arq["executions"].append(item)
                write_json_no_bom(arquivo_morto, arq)
                add_log(
                    "Arquivado: "
                    + item.get("execution_id", "")
                    + " -> "
                    + os.path.basename(arquivo_morto)
                )
            else:
                add_log(
                    "Ja estava no arquivo morto, nada a fazer: "
                    + item.get("execution_id", "")
                )

            nome_arq = os.path.basename(arquivo_morto)
            lista_arq = [a for a in historico["archive_files"] if a]
            if nome_arq not in lista_arq:
                historico["archive_files"] = lista_arq + [nome_arq]

    # -------------------------------------------------------------
    # 5. Gravar historico principal
    # -------------------------------------------------------------
    write_json_no_bom(args.historico_path, historico)

    # -------------------------------------------------------------
    # 6. Validar relendo do disco
    # -------------------------------------------------------------
    verif = read_json(args.historico_path)
    add_log("Execucoes no arquivo principal: " + str(len(verif["executions"])))
    add_log(
        "IDs: "
        + ", ".join(e.get("execution_id", "") for e in verif["executions"])
    )

    gravada = any(
        e.get("execution_id") == nova_exec["execution_id"] for e in verif["executions"]
    )
    if not gravada:
        raise SystemExit("FALHA: a nova execucao nao foi encontrada apos a gravacao.")

    # Deteccao de mojibake: sequencias tipicas de UTF-8 lido como
    # ANSI/cp1252 e regravado. Regex identica (em codepoints) a
    # work/Update-Historico.ps1: Ã[ -¿] ou â
    with open(args.historico_path, "r", encoding="utf-8") as f:
        bruto = f.read()
    padrao_mojibake = "Ã[ -¿]|â"
    suspeitas = re.findall(padrao_mojibake, bruto)
    if suspeitas:
        add_log(
            f"ALERTA DE ENCODING: {len(suspeitas)} ocorrencia(s) de mojibake "
            "detectada(s). Revisar antes de considerar a execucao concluida."
        )
    else:
        add_log("Encoding: nenhuma marca de mojibake detectada.")

    # -------------------------------------------------------------
    # 6-A. Emitir o resumo de estado (robozinho-estado.json)
    # -------------------------------------------------------------
    pasta_estado = os.path.dirname(os.path.abspath(args.historico_path))
    estado_path = os.path.join(pasta_estado, "robozinho-estado.json")

    ultima = verif["executions"][-1]

    # Chaves apenas das 5 execucoes mais recentes: a janela elastica tem
    # no maximo 7 dias (~5 dias uteis), entao chave mais antiga que isso
    # nao pode reaparecer como "novidade de hoje". Mantem o arquivo enxuto.
    todas = verif["executions"]
    corte = max(0, len(todas) - 5)
    recentes = todas[corte:]

    chaves = []
    for ex in recentes:
        for it in ex.get("items", []) or []:
            if it.get("chave"):
                chaves.append(it["chave"])

    pend = [p for p in (ultima.get("pendencias") or []) if p]

    global historico_path_global
    historico_path_global = args.historico_path
    metricas = metricas_derivadas(verif, todas)

    estado = {
        "gerado_em": now_iso_with_offset(),
        "gerado_por": ultima.get("execution_id"),
        "aviso": (
            "Arquivo gerado automaticamente por Update-Historico.py. Nao editar "
            "a mao. Substitui a leitura integral do historico no inicio da "
            "execucao."
        ),
        "ultima_execucao": {
            "execution_id": ultima.get("execution_id"),
            "date": ultima.get("date"),
            "email_subject": ultima.get("email_subject"),
            "delivery": ultima.get("delivery"),
            "draft_id": ultima.get("draft_id"),
            "window_end": ultima.get("window_end"),
        },
        "total_execucoes_arquivo": len(verif["executions"]),
        "pendencias_ultima": pend,
        "chaves_publicadas": chaves,
        "total_chaves": len(chaves),
        "metricas": metricas,
    }

    write_json_no_bom(estado_path, estado)
    add_log(
        f"Estado emitido: robozinho-estado.json ({len(chaves)} chaves, "
        f"ultima execucao {ultima.get('execution_id')})"
    )
    add_log(
        "Metricas: itens_ultima=%d media_itens_10=%s execucoes_registradas=%d coletores_ultima=%s"
        % (
            metricas["itens_ultima"],
            metricas["media_itens"],
            metricas["execucoes_registradas"],
            json.dumps(metricas["coletores_ultima"], ensure_ascii=False),
        )
    )

    # -------------------------------------------------------------
    # 7. Contadores mecanicos do ledger (opcional)
    # -------------------------------------------------------------
    if args.ledger_path:
        if os.path.exists(args.ledger_path):
            aplicar_ledger(args.ledger_path, nova_exec, add_log)
        else:
            add_log("AVISO: ledger nao encontrado: " + args.ledger_path)

    emitir("STATUS: OK")


if __name__ == "__main__":
    main()
