#!/usr/bin/env bash
# =====================================================================
# finalizar.sh — passos 7 e 8 da ROTINA numa chamada so:
#   1. Update-Historico.py: grava o historico, aplica ledger_updates, os
#      mecanicos dos concursos (carimbo da banca, selo por data, mudou_em,
#      URLs vistas) e os contadores do ledger, mede o uso real (orquestrador
#      e coletores) e regenera o estado. Sem "STATUS: OK", nada e commitado.
#      Entrada: $ROBOZINHO_TMP/execucao.resolvido.json (gravado pelo
#      montar_email.py) quando existe, e da mesma execucao e nao e mais velho
#      que o execucao.json. execucao.json editado DEPOIS da ultima montagem
#      (ex.: pendencia errata_* achada depois do rascunho) e com item por
#      `ref` ou sem `chave`: roda o montador de novo (so regrava o resolvido;
#      o HTML vai para $ROBOZINHO_TMP/finalizar-email.html, o email.html do
#      rascunho fica) e compara os itens com a montagem anterior; remontagem
#      com ERRO = PERSISTENCIA ABORTADA com o que fazer. O execucao.json nao
#      resolvido so entra sem ref e com chave (fluxo antigo, draft_ja_existente).
#   2. Commit e push para main. Trabalha na branch LOCAL main: o hook de
#      parada compara HEAD com origin/<branch atual>; commitando numa branch
#      de sessao e empurrando so para main, o hook acusava "commit nao
#      enviado" e a sessao acabava criando uma branch orfa no remoto.
#   3. Push recusado porque a main andou no remoto: em vez de rebase textual
#      dos JSON (conflito certo no historico/ledger), busca origin/main,
#      restaura dela os arquivos de estado e REAPLICA o helper com as mesmas
#      entradas (copia guardada antes da 1a rodada), uma vez. A arvore vai
#      inteira para origin/main (reset --keep): com --mixed ela ficava com a
#      versao antiga do que mudou no remoto, e o `git diff` pos-push (o reverso
#      da mudanca concorrente) seria commitado por quem obedecesse ao hook de
#      parada. Falhou de novo: copia do estado do dia em
#      $ROBOZINHO_TMP/robozinho-estado-backup-<exec>.tar.gz — refeita depois
#      de cada rodada OK do helper (a linha ESTADO aponta para a ULTIMA); se a
#      reaplicacao nao chegou ao fim, a copia e a da 1a rodada, sobre a main
#      antiga, e a linha ESTADO manda rodar o finalizar.sh de novo em vez de
#      aplicar o tar (apagaria a mudanca concorrente). So "[rejected]",
#      non-fast-forward e fetch first contam como "main andou" ("[remote
#      rejected]" de hook nao: e repetido como falha comum).
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

# Entrada do helper: a versao resolvida pelo montador (refs ja resolvidas), se for desta execucao e nao
# for mais velha que o execucao.json. Mais velha (Edit depois da ultima montagem) ou ausente, com item por
# `ref` ou sem `chave`: o execucao.json nao passa no helper (categoria/selo/chave None) -> remontar.
DECISAO=$(python3 - "$T" <<'PY'
import json, os, sys
t = sys.argv[1]
r, e, j = (os.path.join(t, n) for n in ("execucao.resolvido.json", "execucao.json", "janela.json"))
def ler(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None
jid = (ler(j) or {}).get("execution_id")
rv = ler(r)
# sem execution_id (o orquestrador nao o escreve; o helper completa do janela.json) tambem vale
r_ok = isinstance(rv, dict) and rv.get("execution_id") in (None, "", jid)
if r_ok and (not os.path.exists(e) or os.path.getmtime(r) >= os.path.getmtime(e)):
    print("resolvido")
    sys.exit()
ev = ler(e)
itens = (ev.get("items") or []) if isinstance(ev, dict) else []
print("remontar" if any(isinstance(it, dict) and ("ref" in it or not it.get("chave")) for it in itens)
      else "execucao")
PY
)

remontar() {   # execucao.json editado depois da montagem: o montador regrava o resolvido (nao envia nada)
  echo "REMONTAGEM: $T/execucao.json é mais novo que a última montagem (ou não há versão resolvida desta" \
       "execução) — rodando o montador de novo; o rascunho já criado não muda"
  rm -f "$T/finalizar-remontado.json"
  local out rc
  out=$(python3 work/montar_email.py --resolvido "$T/finalizar-remontado.json" --saida "$T/finalizar-email.html" 2>&1)
  rc=$?
  if [[ $rc -ne 0 || ! -s "$T/finalizar-remontado.json" ]]; then
    grep -E '^(ERRO|VALIDACAO|MONTAGEM)' <<< "$out" | head -20
    [[ $rc -ne 0 ]] && ! grep -qE '^(ERRO|MONTAGEM)' <<< "$out" && tail -5 <<< "$out"
    echo "PERSISTENCIA ABORTADA: execucao.json editado depois da montagem e a remontagem deu ERRO (acima) —" \
         "corrija o $T/execucao.json, rode python3 work/montar_email.py e repita o finalizar.sh. Nada foi commitado."
    return 1
  fi
  echo "REMONTAGEM: $(grep -m1 -oE '^MONTAGEM: OK( COM AVISOS)?' <<< "$out")"
  python3 - "$T" <<'PY'
import json, os, re, sys
t = sys.argv[1]
def ler(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None
novo = ler(os.path.join(t, "finalizar-remontado.json")) or {}
ant = ler(os.path.join(t, "execucao.resolvido.json"))
if isinstance(ant, dict) and ant.get("execution_id") in (None, "", novo.get("execution_id")):
    ka = [i.get("chave") for i in ant.get("items") or []]
    kn = [i.get("chave") for i in novo.get("items") or []]
    if ka == kn:
        print("REMONTAGEM: itens iguais aos da montagem anterior (%d)" % len(kn))
    else:
        mais = [k for k in kn if k not in ka]
        menos = [k for k in ka if k not in kn]
        print("ALERTA: o execucao.json editado depois da montagem mudou os itens (%d -> %d%s%s) — o histórico "
              "registra o arquivo editado, não o rascunho já criado: confira e diga na notificação"
              % (len(ka), len(kn), "; + " + ", ".join(mais[:5]) if mais else "",
                 "; - " + ", ".join(menos[:5]) if menos else ""))
else:
    print("REMONTAGEM: sem montagem anterior desta execução para comparar os itens")
carimbo = re.compile(rb"Gerado em \d{2}/\d{2}/\d{4} \d{2}:\d{2}")
rasc = next((p for p in ("email.html", "email-com-avisos.html") if os.path.exists(os.path.join(t, p))), None)
nov = next((p for p in ("finalizar-email.html", "finalizar-email-com-avisos.html")
            if os.path.exists(os.path.join(t, p))), None)
if rasc and nov:
    a, b = (open(os.path.join(t, p), "rb").read() for p in (rasc, nov))
    print("REMONTAGEM: corpo %s %s (%d -> %d bytes, fora o carimbo)" % (
        "igual ao" if carimbo.sub(b"", a) == carimbo.sub(b"", b) else "diferente do", rasc, len(a), len(b)))
PY
  mv -f "$T/finalizar-remontado.json" "$T/execucao.resolvido.json"
}

case "$DECISAO" in
  resolvido) ENTRADA="$T/execucao.resolvido.json" ;;
  remontar)  remontar || exit 2; ENTRADA="$T/execucao.resolvido.json" ;;
  *)         ENTRADA="$T/execucao.json" ;;
esac
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

# estado de work/ antes do helper (com a migracao que o inicio.py aplicou): se o helper nao terminar com
# STATUS: OK, os arquivos voltam a isto — nada fica gravado pela metade diante do hook de parada (verified[14])
ANTES="$T/finalizar-antes"
guardar_antes() {
  rm -rf "$ANTES" && mkdir -p "$ANTES" || return 1
  local f
  for f in $(arquivos_estado); do cp -p "$f" "$ANTES/" || return 1; done
}
restaurar_antes() {
  local f
  for f in $(arquivos_estado); do [[ -e "$ANTES/$(basename "$f")" ]] || rm -f "$f"; done   # criado pelo helper
  for f in "$ANTES"/*; do [[ -e "$f" ]] && cp -p "$f" "work/$(basename "$f")"; done
  echo "RESTAURADO: os arquivos de estado de work/ voltaram ao que eram antes do helper (nada gravado pela metade)"
}
guardar_antes || { echo "PERSISTENCIA ABORTADA: copia do estado antes do helper falhou em $ANTES — nada foi commitado."; exit 2; }

cp "$COPIA" "$T/finalizar-rodada1.json"
if ! helper "$T/finalizar-rodada1.json"; then
  restaurar_antes
  echo "PERSISTENCIA ABORTADA: o helper nao terminou com STATUS: OK — nada foi commitado."
  exit 2
fi
cp "$T/finalizar-rodada1.json" "$ENTRADA"      # a entrada fica normalizada, como antes

EXEC=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['execution_id'])" "$ENTRADA")
BACKUP_ARQ="$T/robozinho-estado-backup-$EXEC.tar.gz"
BACKUP="" ESTADO_DE="" SHA="" SHA1="" reaplicado=0
copiar_estado() {   # copia do estado da ULTIMA rodada OK do helper ($1 = rodada1|rodada2); falha = fica a anterior
  if tar -czf "$BACKUP_ARQ.tmp" $(arquivos_estado) 2>/dev/null && mv -f "$BACKUP_ARQ.tmp" "$BACKUP_ARQ"; then
    BACKUP="$BACKUP_ARQ" ESTADO_DE="$1"
  else
    rm -f "$BACKUP_ARQ.tmp"
  fi
}
copiar_estado rodada1

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
  if [[ -n "$BACKUP" && $reaplicado -eq 1 && "$ESTADO_DE" == "rodada1" ]]; then
    # a main remota andou e a reaplicacao nao terminou: a copia e o commit sao da main ANTIGA
    echo "ESTADO: copia do estado do dia em $BACKUP (commit local ${SHA1:-nenhum}, da 1a rodada, sobre a main" \
         "anterior a mudanca concorrente) — NAO aplique o tar sobre a main atual (apagaria a mudanca concorrente):" \
         "rode bash work/finalizar.sh de novo com os mesmos argumentos (entrada em $COPIA)"
  elif [[ -n "$BACKUP" ]]; then
    echo "ESTADO: copia do estado do dia em $BACKUP (commit local ${SHA:-nenhum}) —" \
         "para reaplicar: tar -xzf $BACKUP e commitar os arquivos work/ na main"
  fi
  exit 3
}

git switch -q -C main || falhou "git switch main"
commitar || falhou "commit"
SHA=$(git rev-parse --short HEAD 2>/dev/null) SHA1="$SHA"

for espera in 0 2 4 8 16; do
  sleep "$espera"
  if saida=$(git push -q -u origin main 2>&1); then
    echo "PUSH: OK (main $(git rev-parse --short HEAD))"
    if [[ $reaplicado -eq 1 ]] && ! git diff --quiet HEAD 2>/dev/null; then
      echo "AVISO: diferenca local depois da reaplicacao em $(git diff --name-only HEAD | tr '\n' ' ')— nao e da" \
           "execucao de hoje: NAO commite (seria o reverso da mudanca concorrente na main)"
    fi
    exit 0
  fi
  # main andou no remoto (ex.: alteracao manual no dia): reaplica o helper sobre o estado de origin/main
  # so a recusa por historico ("! [rejected] ... (fetch first|non-fast-forward)"); "[remote rejected]" (hook
  # do servidor) nao e "main andou": reset e reaplicacao seriam inuteis
  if [[ $reaplicado -eq 0 ]] && grep -qiE "non-fast-forward|fetch first|\[rejected\]" <<< "$saida"; then
    reaplicado=1
    echo "PUSH: recusado (main andou no remoto) — reaplicando o helper sobre origin/main"
    git fetch -q origin main || falhou "git fetch origin main"
    # --keep: HEAD, indice e ARVORE vao para origin/main (o commit local so tem estado, que o helper refaz);
    # recusado (alteracao local num arquivo que mudou no remoto): --mixed, como antes, com AVISO
    if ! git reset -q --keep origin/main 2>/dev/null; then
      git reset -q --mixed origin/main || falhou "git reset origin/main"
      echo "AVISO: reset --keep recusado (alteracao local fora do estado) — so os arquivos de estado vao para origin/main"
    fi
    for f in $(arquivos_estado) "${ESTADO[@]}"; do
      if git cat-file -e "origin/main:$f" 2>/dev/null; then
        git checkout -q origin/main -- "$f"
      else
        rm -f "$f"          # nao existe la: o helper recria se for o caso
      fi
    done
    cp "$COPIA" "$T/finalizar-rodada2.json"
    helper "$T/finalizar-rodada2.json" || falhou "helper na reaplicacao sobre origin/main (STATUS != OK)"
    copiar_estado rodada2
    SHA=""
    commitar || falhou "commit na reaplicacao"
    SHA=$(git rev-parse --short HEAD 2>/dev/null)
  fi
done
echo "Ultimo erro do push:"
echo "$saida" | tail -3
falhou "apos 5 tentativas"
