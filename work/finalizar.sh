#!/usr/bin/env bash
# =====================================================================
# finalizar.sh — passos 9 e 10 da ROTINA numa chamada so:
#   1. Update-Historico.py: grava o historico, aplica ledger_updates e os
#      contadores do ledger, mede o uso real (orquestrador e coletores) e
#      regenera o estado. Sem "STATUS: OK", nada e commitado.
#   2. Commit e push para main. Trabalha na branch LOCAL main: o hook de
#      parada compara HEAD com origin/<branch atual>; commitando numa branch
#      de sessao e empurrando so para main, o hook acusava "commit nao
#      enviado" e a sessao acabava criando uma branch orfa no remoto.
#
# USO: bash work/finalizar.sh --draft-id ID --message-id MSG_ID \
#                             [--anterior EXEC_ID] [--trailer "linhas de atribuicao do commit"]
#      (--anterior: padrao = execucao anterior do /tmp/janela.json;
#       sem rascunho novo, no caso draft_ja_existente: omita --draft-id)
# SAIDA: relatorio do helper + "PUSH: OK (...)" | "PUSH: FALHOU ..." (exit 3)
# =====================================================================
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

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
janela() { python3 -c "import json,sys; print(json.load(open('/tmp/janela.json')).get(sys.argv[1]) or '')" "$1" 2>/dev/null; }
if [[ -z "$ANTERIOR" && -f /tmp/janela.json ]]; then ANTERIOR=$(janela execucao_anterior); fi
if [[ -n "$ANTERIOR" && "$ANTERIOR" == "$(janela execution_id)" ]]; then ANTERIOR="" MSG=""; fi

rm -f /tmp/relatorio.txt
python3 work/Update-Historico.py --nova-execucao /tmp/execucao.json \
  ${DRAFT:+--draft-id "$DRAFT"} \
  ${ANTERIOR:+--reconciliar-id "$ANTERIOR"} ${MSG:+--reconciliar-message-id "$MSG"} \
  --ledger work/robozinho-aprendizado.json --medir-uso --relatorio-path /tmp/relatorio.txt
rc=$?
if [[ $rc -ne 0 ]] || ! grep -q '^STATUS: OK' /tmp/relatorio.txt 2>/dev/null; then
  echo "PERSISTENCIA ABORTADA: o helper nao terminou com STATUS: OK — nada foi commitado."
  exit 2
fi

EXEC=$(python3 -c "import json; print(json.load(open('/tmp/execucao.json'))['execution_id'])")
git switch -q -C main || { echo "PUSH: FALHOU (git switch main)"; exit 3; }
git add work/robozinho-aprendizado.json work/robozinho-estado.json \
  work/resumo-legislativo-historico.json work/resumo-legislativo-historico-arquivo-*.json
if git diff --cached --quiet; then
  echo "COMMIT: nada mudou nos arquivos de estado"
else
  git commit -q -m "Robozinho: execução $EXEC" ${TRAILER:+-m "$TRAILER"} || { echo "PUSH: FALHOU (commit)"; exit 3; }
fi

rebaseado=0
for espera in 0 2 4 8 16; do
  sleep "$espera"
  if saida=$(git push -q -u origin main 2>&1); then
    echo "PUSH: OK (main $(git rev-parse --short HEAD))"
    exit 0
  fi
  # main andou no remoto (ex.: alteracao manual no dia): integra uma vez e tenta de novo
  if [[ $rebaseado -eq 0 ]] && grep -qiE "rejected|non-fast-forward|fetch first" <<< "$saida"; then
    rebaseado=1
    git pull -q --rebase origin main || { git rebase --abort 2>/dev/null
      echo "PUSH: FALHOU (conflito ao integrar origin/main) — registrar no relatorio final"; exit 3; }
  fi
done
echo "PUSH: FALHOU apos 5 tentativas — registrar no relatorio final. Ultimo erro:"
echo "$saida" | tail -3
exit 3
