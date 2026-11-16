#!/usr/bin/env bash
# =====================================================================
# finalizar.sh — passos 7 e 8 da ROTINA numa chamada so:
#   1. Update-Historico.py: grava o historico, aplica ledger_updates, os
#      mecanicos dos concursos (carimbo da banca, selo por data, mudou_em,
#      URLs vistas) e os contadores do ledger, mede o uso real (orquestrador
#      e coletores) e regenera o estado. Sem "STATUS: OK", nada e commitado.
#      Entrada: $ROBOZINHO_TMP/execucao.resolvido.json (gravado pelo
#      montar_email.py) quando existe, e da mesma execucao e nao e mais velho
#      que o execucao.json; senao, $ROBOZINHO_TMP/execucao.json.
#   2. Commit e push para main. Trabalha na branch LOCAL main: o hook de
#      parada compara HEAD com origin/<branch atual>; commitando numa branch
#      de sessao e empurrando so para main, o hook acusava "commit nao
#      enviado" e a sessao acabava criando uma branch orfa no remoto.
#   3. Push recusado porque a main andou no remoto: em vez de rebase textual
#      dos JSON (conflito certo no historico/ledger), busca origin/main,
#      restaura dela os arquivos de estado e REAPLICA o helper com as mesmas
#      entradas (copia guardada antes da 1a rodada), uma vez. Falhou de novo:
#      copia do estado do dia em $ROBOZINHO_TMP/robozinho-estado-backup-<exec>.tar.gz.
#
# USO: bash work/finalizar.sh --draft-id ID --message-id MSG_ID \
#                             [--anterior EXEC_ID] [--trailer "linhas de atribuicao do commit"]
#      (--anterior: padrao = execucao anterior do janela.json;
#       sem rascunho novo, no caso draft_ja_existente: omita --draft-id;
#       --message-id: o da edicao anterior achada em in:sent; sem ele, a
#       anterior NAO vira "sent": fica "draft" com ALERTA)
# SAIDA: relatorio do helper + "PUSH: OK (...)" | "PUSH: FALHOU ..." (exit 3)
# Temporarios em $ROBOZINHO_TMP (padrao /tmp).
# =====================================================================
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
T="${ROBOZINHO_TMP:-/tmp}"

DRAFT="" ANTERIOR="" MSG="" TRAILER=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --draft-id) DRAFT="$2"; shift 2 ;;
    --anterior) ANTERIOR="$2"; shift 2 ;;
    --message-id) MSG="$2"; shift 2 ;;
    --trailer) TRAILER="$2"; shift 2 ;;
    *) echo "argumento desconhecido: $1"; exit 1 ;;
  esac
done

# execucao anterior: a do inicio.py, se nao vier por argumento. Numa
# re-execucao do mesmo dia ela e a propria execucao de hoje: nao reconciliar.
janela() { python3 -c "import json,sys; print(json.load(open(sys.argv[2])).get(sys.argv[1]) or '')" "$1" "$T/janela.json" 2>/dev/null; }
if [[ -z "$ANTERIOR" && -f "$T/janela.json" ]]; then ANTERIOR=$(janela execucao_anterior); fi
if [[ -n "$ANTERIOR" && "$ANTERIOR" == "$(janela execution_id)" ]]; then ANTERIOR="" MSG=""; fi

# Re-execucao detectada pelo inicio.py (a edicao de hoje ja existe): nao ha o que gravar.
if [[ "$(janela reexecucao)" == "True" ]]; then
  echo "RE-EXECUCAO: a edicao de hoje ja esta registrada — nada gravado, nada commitado."
  echo "PUSH: OK (nada a enviar)"
  exit 0
fi

# Entrada do helper: a versao resolvida pelo montador (refs ja resolvidas), se for desta execucao
ENTRADA="$T/execucao.json"
if [[ -f "$T/execucao.resolvido.json" ]] && python3 - "$T" <<'PY'
import json, os, sys
t = sys.argv[1]
r, e, j = (os.path.join(t, n) for n in ("execucao.resolvido.json", "execucao.json", "janela.json"))
try:
    ok = json.load(open(r)).get("execution_id") == json.load(open(j)).get("execution_id")
    ok = ok and (not os.path.exists(e) or os.path.getmtime(r) >= os.path.getmtime(e))
except Exception:
    ok = False
sys.exit(0 if ok else 1)
PY
then
  ENTRADA="$T/execucao.resolvido.json"
fi
echo "ENTRADA: $ENTRADA"
COPIA="$T/finalizar-entrada.json"
cp "$ENTRADA" "$COPIA" || { echo "PERSISTENCIA ABORTADA: $ENTRADA nao encontrado — nada foi commitado."; exit 2; }

ESTADO=(work/robozinho-aprendizado.json work/robozinho-estado.json work/concursos-estado.json
        work/resumo-legislativo-historico.json)
arquivos_estado() { ls "${ESTADO[@]}" work/resumo-legislativo-historico-arquivo-*.json 2>/dev/null; }

helper() {   # $1 = arquivo de entrada (uma copia: o helper o normaliza no lugar)
  rm -f "$T/relatorio.txt"
  python3 work/Update-Historico.py --nova-execucao "$1" \
    ${DRAFT:+--draft-id "$DRAFT"} \
    ${ANTERIOR:+--reconciliar-id "$ANTERIOR"} ${MSG:+--reconciliar-message-id "$MSG"} \
    --ledger work/robozinho-aprendizado.json --medir-uso --relatorio-path "$T/relatorio.txt" \
    --janela "$T/janela.json"
  local rc=$?
  [[ $rc -eq 0 ]] && grep -q '^STATUS: OK' "$T/relatorio.txt" 2>/dev/null
}

cp "$COPIA" "$T/finalizar-rodada1.json"
if ! helper "$T/finalizar-rodada1.json"; then
  echo "PERSISTENCIA ABORTADA: o helper nao terminou com STATUS: OK — nada foi commitado."
  exit 2
fi
cp "$T/finalizar-rodada1.json" "$ENTRADA"      # a entrada fica normalizada, como antes

EXEC=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['execution_id'])" "$ENTRADA")
BACKUP="$T/robozinho-estado-backup-$EXEC.tar.gz"
tar -czf "$BACKUP" $(arquivos_estado) 2>/dev/null || BACKUP=""

commitar() {
  git add $(arquivos_estado)
  if git diff --cached --quiet; then
    echo "COMMIT: nada mudou nos arquivos de estado"
  else
    git commit -q -m "Robozinho: execução $EXEC" ${TRAILER:+-m "$TRAILER"} || return 1
  fi
}

falhou() {
  echo "PUSH: FALHOU ($1) — registrar no relatorio final."
  if [[ -n "$BACKUP" ]]; then
    echo "ESTADO: copia do estado do dia em $BACKUP (commit local $(git rev-parse --short HEAD 2>/dev/null)) —" \
         "para reaplicar: tar -xzf $BACKUP e commitar os arquivos work/ na main"
  fi
  exit 3
}

git switch -q -C main || falhou "git switch main"
commitar || falhou "commit"

reaplicado=0
for espera in 0 2 4 8 16; do
  sleep "$espera"
  if saida=$(git push -q -u origin main 2>&1); then
    echo "PUSH: OK (main $(git rev-parse --short HEAD))"
    exit 0
  fi
  # main andou no remoto (ex.: alteracao manual no dia): reaplica o helper sobre o estado de origin/main
  if [[ $reaplicado -eq 0 ]] && grep -qiE "rejected|non-fast-forward|fetch first" <<< "$saida"; then
    reaplicado=1
    echo "PUSH: recusado (main andou no remoto) — reaplicando o helper sobre origin/main"
    git fetch -q origin main || falhou "git fetch origin main"
    git reset -q --mixed origin/main || falhou "git reset origin/main"
    for f in $(arquivos_estado) "${ESTADO[@]}"; do
      if git cat-file -e "origin/main:$f" 2>/dev/null; then
        git checkout -q origin/main -- "$f"
      else
        rm -f "$f"          # nao existe la: o helper recria se for o caso
      fi
    done
    cp "$COPIA" "$T/finalizar-rodada2.json"
    helper "$T/finalizar-rodada2.json" || falhou "helper na reaplicacao sobre origin/main (STATUS != OK)"
    commitar || falhou "commit na reaplicacao"
  fi
done
echo "Ultimo erro do push:"
echo "$saida" | tail -3
falhou "apos 5 tentativas"
