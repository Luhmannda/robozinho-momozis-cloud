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
#   2. Commit (so dos arquivos de estado, por pathspec: o que mais estiver no
#      indice fica fora, com AVISO) e push para main. Trabalha na branch LOCAL main: o hook de
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
#   4. Protecoes (revisao de 21/11/2026):
#      - helper sem STATUS: OK (inclusive "STATUS: ERRO INTERNO") = os arquivos de
#        estado voltam ao que eram antes dele ("RESTAURADO: ...") e PERSISTENCIA
#        ABORTADA: nada fica gravado pela metade diante do hook de parada;
#      - trava de sanidade antes de cada commit: registro, pendencia, fonte ou
#        armadilha que sumiu sem `remover` no update de hoje nem numa migracao
#        aplicada agora, ou execucao que saiu do historico sem ir para o arquivo
#        morto ("TRAVA: ...") = nada commitado;
#      - sessao que contem a origin/main E commits fora dela: o estado e gravado
#        sobre a origin/main (reaplicacao), sem levar esses commits para a main;
#      - reaplicacao e migracoes de dado (rev3, P2): antes do helper, so as que o dia VIU
#        (marcadas no ledger local quando o finalizar.sh comecou, guardadas em
#        $ROBOZINHO_TMP/finalizar-migracoes-vistas.json) e que o ledger da origin/main nao
#        tem; as novas da origin/main, depois do helper (work/migracoes.py), antes da trava —
#        a correcao/remocao do dono vale por cima do que o dia gravou. O finalizar.sh repetido
#        reaplica as vistas que faltarem no ledger antes da 1a rodada ("MIGRACOES DO DIA: ");
#      - rede com prazo (rev3, P1): cada push/fetch ate ROBOZINHO_LIMITE_REDE s (12), 4
#        tentativas com esperas ROBOZINHO_PUSH_ESPERAS ("0 5 10 15"): pior caso ~90 s de rede
#        + o helper, abaixo de 100 s (o Bash do passo 7 roda com timeout 300000; o padrao
#        do Bash e 120 s);
#      - TERM/INT (corte do timeout, Ctrl-C): nunca morre calado — antes da copia do estado,
#        RESTAURADO + PERSISTENCIA ABORTADA (exit 2); depois, PUSH: FALHOU (interrompido)
#        com a linha ESTADO (exit 3);
#      - falha definitiva: copia em tar do estado do dia (ESTADO: ...). Nenhuma outra branch
#        e criada no remoto: a tarefa agendada so autoriza push na main. Falha depois de
#        comecar a reaplicacao: os arquivos de estado voltam ao ultimo commit ("RESTAURADO: ...
#        voltaram ao ultimo commit"), sem o estado recusado na arvore (rev3, P9).
#
# USO: bash work/finalizar.sh --draft-id ID --message-id MSG_ID \
#                             [--anterior EXEC_ID] [--trailer "linhas de atribuicao do commit"]
#      (--anterior: padrao = execucao anterior do janela.json;
#       sem rascunho novo, no caso draft_ja_existente: omita --draft-id;
#       --message-id: o da edicao anterior achada em in:sent; sem ele, a
#       anterior NAO vira "sent": fica "draft" com ALERTA)
# SAIDA: relatorio do helper + "PUSH: OK (...)" | "PUSH: FALHOU ..." (exit 3) | "PERSISTENCIA ABORTADA ..." (exit 2)
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
DATA=$(janela data)

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

BACKUP="" ESTADO_DE="" SHA="" SHA1="" reaplicado=0 PID_REDE="" FASE=inicio
# rede com prazo (verified[44]; rev3, P1): cada push/fetch tem LIMITE_REDE s; 4 tentativas de push, com esperas que
# somam 30 s. Pior caso (rede sem resposta): fetch 12 + 4 x 12 de push + 30 de espera = 90 s, mais as rodadas do
# helper (~1-3 s cada) — abaixo dos 100 s, folga dentro dos 120 s do timeout padrao do Bash, se o passo 7 esquecer o
# timeout 300000. Reaplicacao: o push recusado responde logo e soma 1 fetch (12) e o helper; a reaplicacao por
# commits fora da main nao busca de novo. Os dois sao configuraveis (testes: ROBOZINHO_PUSH_ESPERAS="0 0 0 0 0").
ESPERAS=(${ROBOZINHO_PUSH_ESPERAS:-0 5 10 15})
LIMITE_REDE=${ROBOZINHO_LIMITE_REDE:-12}
# o comando de rede e a espera rodam em segundo plano + wait: TERM/INT interrompem na hora (o trap mata o filho);
# em primeiro plano, ou dentro de $( ), o bash so atenderia o sinal quando o comando terminasse. A saida vai para
# um arquivo pelo --saida (redirecionar a chamada da funcao mandaria para la tambem as linhas do trap)
rede() {   # rede [--saida ARQUIVO] comando...
  if [[ "$1" == --saida ]]; then
    local arq="$2"
    shift 2
    timeout "$LIMITE_REDE" "$@" > "$arq" 2>&1 &
  else
    timeout "$LIMITE_REDE" "$@" &
  fi
  PID_REDE=$!
  wait "$PID_REDE"
  local rc=$?
  PID_REDE=""
  return $rc
}
pausa() { sleep "$1" & PID_REDE=$!; wait "$PID_REDE"; PID_REDE=""; }

# Interrupcao (rev3, P1): TERM/INT (o corte do timeout do Bash, Ctrl-C) nao matam o script calado. Antes de work/ mudar
# (FASE=inicio): PERSISTENCIA ABORTADA. Durante a 1a rodada (FASE=helper): os arquivos de estado voltam ao que eram
# antes do helper (RESTAURADO) e PERSISTENCIA ABORTADA. Com a copia do estado feita (FASE=copia): a saida de falhou —
# PUSH: FALHOU (interrompido), a linha ESTADO e, na reaplicacao, os arquivos de estado de volta ao ultimo commit.
interrompido() {
  trap '' TERM INT                       # a limpeza nao se interrompe
  [[ -n "$PID_REDE" ]] && kill "$PID_REDE" 2>/dev/null
  echo "INTERROMPIDO: sinal $1 recebido (fase $FASE)"
  if [[ "$FASE" == copia ]]; then
    falhou "interrompido"
  fi
  [[ "$FASE" == helper ]] && restaurar_antes
  echo "PERSISTENCIA ABORTADA: interrompido ($1) antes do commit — nada foi commitado; repita o finalizar.sh com os" \
       "mesmos argumentos."
  exit 2
}
trap 'interrompido TERM' TERM
trap 'interrompido INT' INT

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

# Migracoes de dado na reaplicacao (rev3, P2). Antes do helper, so as que o julgamento do dia VIU (marcadas no ledger
# local quando o finalizar.sh comecou: o inicio.py aplicou as pendentes no passo 1); as que chegaram depois na
# origin/main, depois do helper (por cima do que o dia gravou), antes da trava. Antes, todas iam antes do helper: a
# correcao do dono num registro que o dia tambem atualizou era sobrescrita em silencio, e a remocao de um id que o dia
# atualiza derrubava a validacao (o dia nunca era gravado).
# $VISTAS: os ids marcados no ledger de work/ agora, somados aos de uma chamada anterior desta mesma execucao
# (finalizar.sh repetido depois de uma reaplicacao que nao terminou: a arvore voltou ao ultimo commit, sem elas).
VISTAS="$T/finalizar-migracoes-vistas.json"
python3 - "$VISTAS" "$(janela execution_id)" <<'PY'
import json, sys
vistas_p, exec_id = sys.argv[1:3]
def ler(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None
led = ler("work/robozinho-aprendizado.json")
led = led if isinstance(led, dict) else {}
ids = {(x.get("id") if isinstance(x, dict) else x) for x in led.get("migracoes_aplicadas") or []} - {None, ""}
ant = ler(vistas_p)
if isinstance(ant, dict) and ant.get("execution_id") == exec_id:
    ids |= set(ant.get("ids") or [])
with open(vistas_p, "w", encoding="utf-8") as f:
    json.dump({"execution_id": exec_id, "ids": sorted(ids)}, f, ensure_ascii=False)
PY

migracoes_vistas() {   # $1 = prefixo das linhas. Das migracoes que o dia viu ($VISTAS), aplica as que o ledger de work/
  # nao tem marcadas, e so elas: o work/migracoes.py aplica tudo o que esta pendente na pasta, entao roda (--work) numa
  # copia com o ledger e so os arquivos escolhidos; o ledger volta para work/ se mudou
  python3 - "$VISTAS" "$T/finalizar-migracoes" "$1" ${DATA:+"$DATA"} <<'PY'
import filecmp, glob, json, os, shutil, subprocess, sys
vistas_p, tmp, prefixo = sys.argv[1:4]
hoje = sys.argv[4] if len(sys.argv) > 4 else None
led_p = os.path.join("work", "robozinho-aprendizado.json")
def ler(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None
led, vistas = ler(led_p), set((ler(vistas_p) or {}).get("ids") or [])
if not isinstance(led, dict) or not vistas:
    sys.exit(0)
faltam = vistas - {(x.get("id") if isinstance(x, dict) else x) for x in led.get("migracoes_aplicadas") or []}
if not faltam:
    sys.exit(0)
shutil.rmtree(tmp, ignore_errors=True)
os.makedirs(os.path.join(tmp, "migracoes"))
achadas = set()
for p in sorted(glob.glob(os.path.join("work", "migracoes", "*.json"))):
    m = ler(p)
    if isinstance(m, dict) and m.get("id") in faltam:
        shutil.copy(p, os.path.join(tmp, "migracoes", os.path.basename(p)))
        achadas.add(m["id"])
for i in sorted(faltam - achadas):
    print(prefixo + "AVISO: migracao %s (vista hoje) nao existe em work/migracoes desta arvore — fica de fora" % i)
if not achadas:
    sys.exit(0)
shutil.copy(led_p, os.path.join(tmp, "robozinho-aprendizado.json"))
r = subprocess.run([sys.executable, os.path.join("work", "migracoes.py"), "--work", tmp] + (["--hoje", hoje] if hoje else []),
                   capture_output=True, text=True)
for linha in (r.stdout + r.stderr).splitlines():
    print(prefixo + linha)
novo = os.path.join(tmp, "robozinho-aprendizado.json")
if r.returncode == 0 and not filecmp.cmp(novo, led_p, shallow=False):
    shutil.copy(novo, led_p + ".migracoes.tmp")
    os.replace(led_p + ".migracoes.tmp", led_p)
PY
}

migracoes_vistas "MIGRACOES DO DIA: "     # normalmente nada: o inicio.py ja as aplicou neste ledger
guardar_antes || { echo "PERSISTENCIA ABORTADA: copia do estado antes do helper falhou em $ANTES — nada foi commitado."; exit 2; }
FASE=helper

cp "$COPIA" "$T/finalizar-rodada1.json"
if ! helper "$T/finalizar-rodada1.json"; then
  restaurar_antes
  echo "PERSISTENCIA ABORTADA: o helper nao terminou com STATUS: OK — nada foi commitado."
  exit 2
fi
cp "$T/finalizar-rodada1.json" "$ENTRADA"      # a entrada fica normalizada, como antes

EXEC=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['execution_id'])" "$ENTRADA")
BACKUP_ARQ="$T/robozinho-estado-backup-$EXEC.tar.gz"

copiar_estado() {   # copia do estado da ULTIMA rodada OK do helper ($1 = rodada1|rodada2); falha = fica a anterior
  if tar -czf "$BACKUP_ARQ.tmp" $(arquivos_estado) 2>/dev/null && mv -f "$BACKUP_ARQ.tmp" "$BACKUP_ARQ"; then
    BACKUP="$BACKUP_ARQ" ESTADO_DE="$1"
  else
    rm -f "$BACKUP_ARQ.tmp"
  fi
}

# trava de sanidade (lows[13]): antes do commit, compara o estado gravado com o do HEAD — registro, pendencia,
# fonte ou armadilha que sumiu sem `remover` no update de hoje nem numa migracao aplicada agora, chave do ledger
# que sumiu, execucao que saiu do historico sem ir para o arquivo morto = nao commita
trava() {
  local d="$T/finalizar-trava" f
  rm -rf "$d" && mkdir -p "$d/work" || return 0
  git show "HEAD:work/robozinho-aprendizado.json" > "$d/work/robozinho-aprendizado.json" 2>/dev/null || return 0
  for f in $(git ls-tree --name-only HEAD work/ 2>/dev/null | grep -E '^work/resumo-legislativo-historico(-arquivo-[0-9-]+)?\.json$'); do
    git show "HEAD:$f" > "$d/$f" 2>/dev/null
  done
  python3 - "$d/work" work "$ENTRADA" <<'PY'
import glob, importlib.util, json, os, sys
antes, agora, entrada = sys.argv[1:4]
try:            # a trava e rede de seguranca: se ela mesma quebrar, avisa e nao bloqueia a gravacao do dia
    spec = importlib.util.spec_from_file_location("uh_trava", os.path.join(agora, "Update-Historico.py"))
    sys.path.insert(0, agora)
    uh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(uh)
    uh.trava_sanidade
except Exception as e:  # noqa: BLE001
    print("AVISO: trava de sanidade não conferida (%s: %s)" % (type(e).__name__, e))
    sys.exit(0)
def ler(p, padrao=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return padrao
def ids(pasta):
    out = set()
    for p in glob.glob(os.path.join(pasta, "resumo-legislativo-historico*.json")):
        out |= {e.get("execution_id") for e in (ler(p, {}) or {}).get("executions") or []}
    return out - {None}
la, ld = ler(os.path.join(antes, "robozinho-aprendizado.json"), {}), ler(os.path.join(agora, "robozinho-aprendizado.json"))
if not isinstance(ld, dict):
    print("TRAVA: work/robozinho-aprendizado.json ilegível depois do helper")
    sys.exit(1)
ja = {(x.get("id") if isinstance(x, dict) else x) for x in la.get("migracoes_aplicadas") or []}
novas = {(x.get("id") if isinstance(x, dict) else x) for x in ld.get("migracoes_aplicadas") or []} - ja
updates = [(ler(entrada, {}) or {}).get("ledger_updates")]
for p in glob.glob(os.path.join(agora, "migracoes", "*.json")):
    m = ler(p, {}) or {}
    if m.get("id") in novas:
        updates.append(m.get("ledger_updates"))
try:
    problemas = uh.trava_sanidade(la, ld, updates, ids(antes), ids(agora))
except Exception as e:  # noqa: BLE001
    print("AVISO: trava de sanidade não conferida (%s: %s)" % (type(e).__name__, e))
    sys.exit(0)
for x in problemas:
    print("TRAVA: " + x)
sys.exit(1 if problemas else 0)
PY
}

commitar() {   # so os arquivos de estado (pathspec): o que mais estiver no indice fica fora do commit (e no indice)
  local arqs fora_do_commit
  arqs=$(arquivos_estado)
  git add $arqs
  if git diff --cached --quiet -- $arqs; then
    echo "COMMIT: nada mudou nos arquivos de estado"
  else
    git commit -q -m "Robozinho: execução $EXEC" ${TRAILER:+-m "$TRAILER"} -- $arqs || return 1
  fi
  fora_do_commit=$(git diff --cached --name-only 2>/dev/null | tr '\n' ' ')
  [[ -n "$fora_do_commit" ]] && echo "AVISO: fora do commit do estado (ja estavam no indice): $fora_do_commit"
  return 0
}

restaurar_head() {   # reaplicacao que nao terminou (rev3, P9): os arquivos de estado voltam ao ultimo commit
  local f todos
  todos=$( { arquivos_estado; printf '%s\n' "${ESTADO[@]}"
             git ls-tree --name-only HEAD work/ 2>/dev/null | grep -E '^work/resumo-legislativo-historico-arquivo-'; } | sort -u)
  [[ -n "$(git status --porcelain --untracked-files=all -- $todos 2>/dev/null)" ]] || return 0
  for f in $todos; do
    if git cat-file -e "HEAD:$f" 2>/dev/null; then
      git checkout -q HEAD -- "$f" 2>/dev/null || echo "AVISO: $f nao voltou ao ultimo commit (git checkout falhou)"
    else
      rm -f "$f"          # criado na reaplicacao: nao existe no ultimo commit
    fi
  done
  echo "RESTAURADO: os arquivos de estado de work/ voltaram ao ultimo commit ($(git log -1 --format='%h %s' 2>/dev/null))" \
       "— o estado da reaplicacao que nao terminou nao fica na arvore"
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
  [[ $reaplicado -eq 1 ]] && restaurar_head
  exit 3
}

reaplicar() {   # estado de hoje refeito sobre a origin/main: helper de novo, com as mesmas entradas, uma vez
  # $1 = recusado (push recusado: busca a origin/main nova) | fora (sessao com commits fora da main: vale a origin/main
  # da conferencia, buscada agora ou, se o fetch falhou, a da hora do clone — sem 2o fetch, o pior caso fica no prazo)
  reaplicado=1
  if [[ "${1:-recusado}" == recusado ]]; then
    rede git fetch -q origin main || falhou "git fetch origin main"
  fi
  # --keep: HEAD, indice e ARVORE vao para origin/main (o commit local so tem estado, que o helper refaz);
  # recusado (alteracao local num arquivo que mudou no remoto): --mixed, como antes, com AVISO
  if ! git reset -q --keep origin/main 2>/dev/null; then
    git reset -q --mixed origin/main || falhou "git reset origin/main"
    echo "AVISO: reset --keep recusado (alteracao local fora do estado) — so os arquivos de estado vao para origin/main"
  fi
  local f
  for f in $(arquivos_estado) "${ESTADO[@]}"; do
    if git cat-file -e "origin/main:$f" 2>/dev/null; then
      git checkout -q origin/main -- "$f"
    else
      rm -f "$f"          # nao existe la: o helper recria se for o caso
    fi
  done
  # antes do helper, so as migracoes que o dia viu (o julgamento foi feito com elas) e que o ledger da origin/main nao
  # tem marcadas; as novas da origin/main, depois do helper: valem por cima do que o dia gravou (rev3, P2)
  migracoes_vistas "REAPLICACAO: "
  cp "$COPIA" "$T/finalizar-rodada2.json"
  helper "$T/finalizar-rodada2.json" || falhou "helper na reaplicacao sobre origin/main (STATUS != OK)"
  python3 work/migracoes.py ${DATA:+--hoje "$DATA"} 2>&1 | sed 's/^/REAPLICACAO (nova da origin\/main, depois do helper): /'
  trava || falhou "trava de sanidade na reaplicacao (linhas TRAVA acima)"
  copiar_estado rodada2
  SHA=""
  commitar || falhou "commit na reaplicacao"
  SHA=$(git rev-parse --short HEAD 2>/dev/null)
}

if ! trava; then
  restaurar_antes
  echo "PERSISTENCIA ABORTADA: trava de sanidade (linhas TRAVA acima: o estado perderia o que ninguém pediu para" \
       "remover) — nada foi commitado. Não edite o estado nem o código: avise o dono com as linhas TRAVA."
  exit 2
fi
copiar_estado rodada1
FASE=copia

# sessao fora da main (lows[13]): a branch da sessao contem a origin/main E commits que nao estao nela (sessao nascida
# numa branch velha ou com commit avulso) — o push seria aceito e os levaria para a main. Grava sobre a origin/main.
# Fetch que falha (rev3, P8): a conferencia segue com a origin/main da hora do clone (antes ela era pulada e um push
# aceito depois levava os commits avulsos para a main).
fora="" fora_msgs=""
if ! rede --saida /dev/null git fetch -q origin main; then
  echo "AVISO: git fetch origin main falhou — commits fora da main conferidos contra a origin/main da hora do clone"
fi
if git rev-parse -q --verify refs/remotes/origin/main >/dev/null && git merge-base --is-ancestor origin/main HEAD 2>/dev/null; then
  n=$(git rev-list --count origin/main..HEAD 2>/dev/null || echo 0)
  if [[ "$n" -gt 0 ]]; then
    fora="$n" fora_msgs=$(git log --format=%s -n 3 origin/main..HEAD 2>/dev/null | tr '\n' ';')
  fi
fi

git switch -q -C main || falhou "git switch main"
commitar || falhou "commit"
SHA=$(git rev-parse --short HEAD 2>/dev/null) SHA1="$SHA"
if [[ -n "$fora" ]]; then
  echo "AVISO: a sessão partiu de um commit com $fora commit(s) fora da origin/main ($fora_msgs) —" \
       "eles não vão para a main: reaplicando o helper sobre origin/main"
  reaplicar fora
fi

for espera in "${ESPERAS[@]}"; do
  pausa "$espera"
  rede --saida "$T/finalizar-push.txt" git push -q -u origin main     # sem $( ): o trap atende o sinal na hora
  rc=$?
  saida=$(cat "$T/finalizar-push.txt" 2>/dev/null)
  if [[ $rc -eq 0 ]]; then
    echo "PUSH: OK (main $(git rev-parse --short HEAD))"
    if [[ $reaplicado -eq 1 ]] && ! git diff --quiet HEAD 2>/dev/null; then
      echo "AVISO: diferenca local depois da reaplicacao em $(git diff --name-only HEAD | tr '\n' ' ')— nao e da" \
           "execucao de hoje: NAO commite (seria o reverso da mudanca concorrente na main)"
    fi
    exit 0
  fi
  [[ $rc -eq 124 ]] && saida="${saida:+$saida
}push sem resposta em ${LIMITE_REDE} s (cortado)"
  # main andou no remoto (ex.: alteracao manual no dia): reaplica o helper sobre o estado de origin/main
  # so a recusa por historico ("! [rejected] ... (fetch first|non-fast-forward)"); "[remote rejected]" (hook
  # do servidor) nao e "main andou": reset e reaplicacao seriam inuteis
  if [[ $reaplicado -eq 0 ]] && grep -qiE "non-fast-forward|fetch first|\[rejected\]" <<< "$saida"; then
    echo "PUSH: recusado (main andou no remoto) — reaplicando o helper sobre origin/main"
    reaplicar recusado
  fi
done
echo "Ultimo erro do push:"
echo "$saida" | tail -3
falhou "apos ${#ESPERAS[@]} tentativas"
