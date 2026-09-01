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
#   Depois, SEMPRE ler o arquivo indicado em --relatorio-path com a
#   ferramenta de leitura de arquivos (nunca confiar na saida do console
#   para validar acentuacao).
# =====================================================================

import argparse
import json
import os
import re
import sys
from datetime import datetime


def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json_no_bom(path, data):
    with open(path, "w", encoding="utf-8", newline="") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def now_iso_with_offset():
    return datetime.now().astimezone().isoformat(timespec="seconds")


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
    args = parser.parse_args()

    log = []

    def add_log(linha):
        log.append(linha)

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
    }

    write_json_no_bom(estado_path, estado)
    add_log(
        f"Estado emitido: robozinho-estado.json ({len(chaves)} chaves, "
        f"ultima execucao {ultima.get('execution_id')})"
    )

    add_log("STATUS: OK")

    # -------------------------------------------------------------
    # 7. Relatorio (ler este arquivo para validar de verdade)
    # -------------------------------------------------------------
    texto = "\n".join(log)
    if args.relatorio_path:
        with open(args.relatorio_path, "w", encoding="utf-8", newline="") as f:
            f.write(texto)
    print(texto)


if __name__ == "__main__":
    main()
