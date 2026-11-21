#!/usr/bin/env python3
# =====================================================================
# Update-Historico.py - porte Python do helper oficial de gravacao do
# historico da newsletter "Robozinho dos Momozis ate Passar", para uso
# no ambiente de nuvem (Linux) das rotinas agendadas.
#
# Nasceu como porte do antigo helper PowerShell (Update-Historico.ps1, do
# ambiente Windows; nao esta neste repositorio) e hoje e a unica versao:
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
#
#   --validar      : so valida (itens, selos, chaves, URLs, ledger_updates)
#                    e acusa POSSIVEL_REPETIDA (mesma materia de outra fonte
#                    ja publicada) e POSSIVEL_DUPLICATA_NA_EDICAO. Nao grava
#                    nada. Chamado pelo work/montar_email.py (ROTINA passos 4/5).
#   --draft-id ID  : grava o id do rascunho; run_finished_at vazio ou
#                    "PENDENTE" vira agora.
#   --medir-uso    : preenche `coletores` e `orquestrador` com o uso real
#                    medido nas transcricoes locais (work/medir_uso.py).
#   --janela       : (padrao /tmp/janela.json, do inicio.py) preenche os campos
#                    de cabecalho que faltarem: execution_id, date, type,
#                    timezone, window_start/end, run_started_at, email_subject,
#                    recipients — o orquestrador so escreve o julgamento.
#   ledger_updates : campo da nova execucao com as decisoes de julgamento do
#                    ledger (notas, pendencias, concursos, armadilhas),
#                    aplicadas aqui junto com os contadores — sem Edit manual.
#                    Validados (so nos campos tocados) contra o padrao de prova:
#                    selo de concurso da lista propria; selo que promove ou
#                    prazo confirmado so com fonte oficial (selos.py); remover
#                    exige desfecho; concurso novo exige fonte http; linha sem
#                    "hoje/amanha/ontem"; verificado_em ate a data da janela;
#                    url_oficial e dominio_oficial escritos so oficiais. AVISOs:
#                    DIVERGE DO REGISTRO nao corrigido; prazo escrito hoje que
#                    difere do edital lido hoje (ALERTA na gravacao); selo
#                    escrito que contradiz o selo por data.
#   Migracao     : regra de armadilha que o codigo tornou falsa e reescrita
#                    (REGRAS_ATUALIZADAS; so se o texto atual for o antigo,
#                    idempotente; o inicio.py aplica o mesmo em memoria).
#   Mecanico (o orquestrador nao escreve): carimbo da banca lida hoje
#                    (verificado_em/fonte/dominio_oficial, bancas.carimbos; nunca
#                    no registro que ainda DIVERGE DO REGISTRO), selo por data
#                    (bancas.selo_do_dia, a mesma regra do montador: suspenso,
#                    com ALERTA, enquanto o edital lido hoje contestar a data do
#                    registro; nunca sobre selo escrito hoje; o selo
#                    copiado igual ao do registro sai do update antes: nao e
#                    decisao — marca `selos_copiados` na execucao),
#                    mudou_em dos concursos, URLs vistas na banca
#                    (work/concursos-estado.json), status das fontes lidas por
#                    script ($ROBOZINHO_TMP/fontes_status.json).
#   --refazer      : os ledger_updates da re-execucao sao aplicados de novo
#                    (upsert idempotente); so os contadores ficam 1 vez por
#                    execution_id.
#   Entrega        : "sent" so com --reconciliar-message-id (prova do in:sent);
#                    sem ela, fica "draft" com delivery_check e ALERTA.
#   Uso            : custo_relativo do orquestrador (medir_uso.py); ALERTA_ECONOMIA
#                    acima de 1,3x a mediana das ultimas 10; ALERTA de troca de modelo.
# Temporarios em $ROBOZINHO_TMP (padrao /tmp).
# =====================================================================

import argparse
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, date

import selos

TMP = os.environ.get("ROBOZINHO_TMP", "/tmp")

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


def validar(ex, chaves_anteriores, pre_rascunho=False):
    """Normaliza ex no lugar. Devolve (erros, avisos). pre_rascunho: o
    draft_id ainda nao existe (modo --validar, antes do create_draft)."""
    erros, avisos = [], []
    for campo in ("execution_id", "date", "window_start", "window_end", "email_subject",
                  "delivery", "items"):
        if campo not in ex or ex[campo] in (None, ""):
            erros.append("campo obrigatorio ausente: " + campo)
    if ex.get("delivery") not in ("draft", "draft_ja_existente", "sent"):
        erros.append("delivery invalido: %r" % ex.get("delivery"))
    if ex.get("delivery") == "draft" and ex.get("draft_id") in (None, "", "PENDENTE") \
            and not pre_rascunho:
        erros.append("delivery=draft sem draft_id (passe --draft-id)")
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
    # buscas_gmail: a linha BUSCAS do coletor-gmail, copiada pelo orquestrador (o montador deriva dela o
    # source_status dos gmail_*); fica no registro da execucao como veio
    if ex.get("buscas_gmail") is not None and not isinstance(ex["buscas_gmail"], str):
        avisos.append("buscas_gmail deveria ser texto (a linha BUSCAS do coletor-gmail): %r guardado como veio"
                      % (ex["buscas_gmail"],))
    return erros, avisos


DESTINATARIOS = ["pereirafranciscofilho@gmail.com", "luizaxbarreto@gmail.com"]


def completar_cabecalho(ex, caminho_janela):
    """Campos deterministicos vem do inicio.py ($ROBOZINHO_TMP/janela.json), nao do
    orquestrador: menos saida e nenhum erro de digitacao em data ou janela."""
    if not caminho_janela or not os.path.exists(caminho_janela):
        return []
    j = read_json(caminho_janela)
    if ex.get("execution_id") and ex["execution_id"] != j.get("execution_id"):
        return []          # execucao de outro dia (ex.: reprocessamento): nao mistura
    mapa = {"execution_id": j.get("execution_id"), "date": j.get("data"), "type": j.get("tipo") or "diaria",
            "timezone": "America/Sao_Paulo", "window_start": j.get("inicio"),
            "window_end": j.get("fim"), "run_started_at": j.get("fim"),
            "email_subject": j.get("assunto"), "recipients": DESTINATARIOS}
    preenchidos = []
    for campo, valor in mapa.items():
        if valor and ex.get(campo) in (None, "", []):
            ex[campo] = valor
            preenchidos.append(campo)
    return preenchidos


def janela_fim(caminho_janela):
    try:
        return read_json(caminho_janela).get("fim")
    except (OSError, ValueError, AttributeError):
        return None


def _instante(v):
    try:
        t = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else None


def erros_window_end_r1(ex, erros, fim_inicio):
    """§R1: window_end obrigatorio e escrito pelo orquestrador (data do rascunho achado ou do envio, -03:00), entre
    o inicio da janela e a hora desta re-execucao (o fim da janela do inicio.py)."""
    erros = [e for e in erros if e != "campo obrigatorio ausente: window_end"]
    we = ex.get("window_end")
    if we in (None, ""):
        return erros + ["window_end ausente — §R1: escreva \"window_end\" = a data/hora em que o rascunho achado foi "
                        "criado (list_drafts) ou a edição foi enviada (search_threads in:sent), em -03:00; o fim da "
                        "janela do inicio.py (%s) é a hora desta re-execução e deixaria sem cobertura o que saiu "
                        "entre a edição achada e agora" % (fim_inicio or "?")]
    t, ini, fim = _instante(we), _instante(ex.get("window_start")), _instante(fim_inicio)
    if t is None:
        return erros + ["window_end %r: use AAAA-MM-DDTHH:MM:SS-03:00 (§R1: data do rascunho ou do envio achado)" % we]
    if ini and t < ini:
        return erros + ["window_end %s antes do início da janela (%s) — §R1: a data do rascunho ou do envio achado"
                        % (we, ex.get("window_start"))]
    if fim and t > fim:
        return erros + ["window_end %s depois desta re-execução (%s) — §R1: a data do rascunho ou do envio achado"
                        % (we, fim_inicio)]
    return erros


def checar_repeticao(ex, execucoes, chaves_anteriores):
    """Avisos de materia ja publicada por outra fonte e de duplicata dentro
    da propria edicao (work/repeticao.py). So no modo --validar."""
    import repeticao
    avisos, vistos = [], []
    idx = repeticao.indice(execucoes, ignorar_exec_id=ex.get("execution_id"))
    for it in ex.get("items") or []:
        ch = (it.get("chave") or "").lower()
        if not ch or repeticao.ignorar(it):
            continue
        tok = repeticao.tokens_item(ch, it.get("titulo"))
        if ch not in chaves_anteriores:
            m = repeticao.procurar(tok, idx, excluir=ch)
            if m:
                avisos.append("POSSIVEL_REPETIDA: %s ~ %s (ja saiu; so entra se for "
                              "desdobramento novo, dito como tal)" % (ch, m))
        for ch2, t2 in vistos:
            if repeticao.parecidas(tok, t2):
                avisos.append("POSSIVEL_DUPLICATA_NA_EDICAO: %s ~ %s (mesma materia de "
                              "duas fontes = 1 item citando as fontes)" % (ch, ch2))
                break
        vistos.append((ch, tok))
    return avisos


# ---------------------------------------------------------------- ledger_updates
FAIXAS = ("ativa", "longo_prazo", "cronica")
BLOCOS = ("Magistratura Estadual", "Magistratura Federal", "Promotor de Justiça (Estadual)",
          "MPF/MPU — Procurador da República", "PFN", "AGU — Advogado da União",
          "Procurador do Estado (PGE)", "Procurador do Município (PGM)",
          "Defensor Público Estadual (DPE)", "Defensor Público Federal (DPU)", "Quadro de apoio")
LIMITE = {"texto": 600, "nota": 700, "politica": 300, "linha": 450, "sintoma": 400,
          "regra": 450, "desfecho": 300, "fonte": 300}
CAMPOS_EDITAVEIS = {
    "fontes": {"nota", "status"},
    "pendencias": {"texto", "faixa", "politica", "coletor", "dominio_oficial", "remover", "desfecho"},
    "concursos": {"bloco", "linha", "selo", "prazos", "fonte", "verificado_em",
                  "dominio_oficial", "pendencia", "url_oficial", "remover", "desfecho"},
}
# mecanicos (gravados so por este helper): concursos.mudou_em; fontes: ultimo_sucesso, sem_sucesso...
OBRIGATORIOS_NOVO = {"pendencias": ("texto", "faixa"),
                     "concursos": ("bloco", "linha", "selo", "verificado_em")}
LISTA_DO_LEDGER = {"fontes": "fontes", "pendencias": "pendencias_vivas", "concursos": "concursos"}


# movimento (concursos): false = a linha foi reescrita sem fato novo para o leitor (enriquecida com fato antigo, nota
# de busca) — grava os outros campos, mas o campo nao vai ao registro, nao atualiza mudou_em e nao conta como
# alteracao (a mesma regra de montar_email.sem_movimento, para o e-mail e o ledger nao divergirem).
CAMPOS_EDITAVEIS["concursos"] = CAMPOS_EDITAVEIS["concursos"] | {"movimento"}
NAO_GRAVA = ("remover", "desfecho", "movimento")      # campos do update que nao vao ao registro


def sem_movimento(campos):
    """ledger_updates.concursos.<id>.movimento = false (ou "false"/"0"/"nao"), como no montador."""
    v = (campos or {}).get("movimento")
    return v is False or str(v).strip().lower() in ("false", "0", "nao", "não")


def _data_iso(v):
    try:
        date.fromisoformat(v)
        return True
    except (TypeError, ValueError):
        return False


LIMITE_ATIVA = 21   # prompt mestre §16


def pendencias_estouradas(upd, led):
    """Pendencia 'ativa' com >= LIMITE_ATIVA execucoes precisa ser rebaixada ou removida
    NESTA execucao. Antes so havia aviso pos-commit, ignorado por semanas (ex.: PGE-RJ, 24)."""
    pend_upd = (upd or {}).get("pendencias") or {}
    erros = []
    for p in led.get("pendencias_vivas") or []:
        if p.get("faixa") != "ativa" or int(p.get("execucoes") or 0) < LIMITE_ATIVA:
            continue
        u = pend_upd.get(p.get("id")) or {}
        if u.get("remover") or (u.get("faixa") and u["faixa"] != "ativa"):
            continue
        erros.append("ledger_updates.pendencias.%s: ativa ha %s execucoes (limite %d) — rebaixe a "
                     "faixa (longo_prazo ou cronica) ou remova com desfecho" % (
                         p.get("id"), p.get("execucoes"), LIMITE_ATIVA))
    return erros


def validar_ledger_updates(upd, led, hoje=None, ex_id=None, carimbos=None):
    """Erros do campo ledger_updates (forma e padrao de prova, so nos campos tocados). Nada e
    aplicado aqui. hoje = data da janela (AAAA-MM-DD); ex_id = execution_id (re-aplicacao do
    mesmo dia: armadilha nova ja gravada nao e erro); carimbos = bancas.carimbos() de hoje."""
    if not upd:
        return pendencias_estouradas({}, led)
    if not isinstance(upd, dict):
        return ["ledger_updates deve ser um objeto"]
    erros = []
    secoes = set(LISTA_DO_LEDGER) | {"armadilhas_detectadas", "armadilhas_novas"}
    for k in upd:
        if k not in secoes:
            erros.append("ledger_updates: secao desconhecida %r (use %s)" % (k, ", ".join(sorted(secoes))))
    niveis = set((led.get("niveis_de_esforco") or {}).keys()) | {"indisponivel"}
    reaplicacao = bool(ex_id) and led.get("atualizado_por_execucao") == ex_id
    pend_upd = upd.get("pendencias") if isinstance(upd.get("pendencias"), dict) else {}
    pend_ids = ({p.get("id") for p in led.get("pendencias_vivas") or []}
                | {i for i, c in pend_upd.items() if isinstance(c, dict) and not c.get("remover")}) \
        - {i for i, c in pend_upd.items() if isinstance(c, dict) and c.get("remover")}
    for secao, nome_lista in LISTA_DO_LEDGER.items():
        bloco = upd.get(secao) or {}
        if not isinstance(bloco, dict):
            erros.append("ledger_updates.%s deve ser {id: {campos}}" % secao)
            continue
        por_id = {x.get("id"): x for x in led.get(nome_lista) or []}
        for ident, campos in bloco.items():
            rot = "ledger_updates.%s.%s" % (secao, ident)
            if not isinstance(campos, dict):
                erros.append(rot + ": deve ser um objeto")
                continue
            extras = set(campos) - CAMPOS_EDITAVEIS[secao]
            if extras:
                erros.append("%s: campos nao editaveis %s (contadores e carimbos sao mecanicos)" % (rot, sorted(extras)))
            novo = ident not in por_id
            if novo:
                if campos.get("remover") and reaplicacao and campos.get("desfecho"):
                    continue            # ja removido na 1a aplicacao desta mesma execucao
                if secao == "fontes" or campos.get("remover"):
                    erros.append(rot + ": id inexistente no ledger")
                    continue
                falta = [c for c in OBRIGATORIOS_NOVO[secao] if not campos.get(c)]
                if falta:
                    erros.append("%s: id novo exige %s" % (rot, ", ".join(falta)))
            if campos.get("remover") and secao in ("concursos", "pendencias") and not campos.get("desfecho"):
                erros.append("%s: remover exige desfecho (o que aconteceu, dito na edição)" % rot)
            for c, lim in LIMITE.items():
                v = campos.get(c)
                if isinstance(v, str) and len(v) > lim:
                    erros.append("%s.%s: %d caracteres (max %d) — reescreva compacto: estado "
                                 "atual + no maximo 1 padrao recente" % (rot, c, len(v), lim))
            if "faixa" in campos and campos["faixa"] not in FAIXAS:
                erros.append("%s.faixa: %r fora de %s" % (rot, campos["faixa"], "/".join(FAIXAS)))
            if "status" in campos and campos["status"] not in niveis:
                erros.append("%s.status: %r fora de %s" % (rot, campos["status"], "/".join(sorted(niveis))))
            if "selo" in campos and campos["selo"] not in SELOS:
                erros.append("%s.selo: %r fora da lista fechada" % (rot, campos["selo"]))
            if "bloco" in campos and campos["bloco"] not in BLOCOS:
                erros.append("%s.bloco: %r fora de %s" % (rot, campos["bloco"], " | ".join(BLOCOS)))
            if "verificado_em" in campos:
                if not _data_iso(campos["verificado_em"]):
                    erros.append("%s.verificado_em: use AAAA-MM-DD" % rot)
                elif hoje and campos["verificado_em"] > hoje:
                    erros.append("%s.verificado_em: %s depois da data da janela (%s)" % (rot, campos["verificado_em"], hoje))
            for n, p in enumerate(campos.get("prazos") or []):
                if not (isinstance(p, dict) and _data_iso(p.get("data")) and p.get("evento")
                        and isinstance(p.get("confirmado"), bool)):
                    erros.append("%s.prazos[%d]: use {data: AAAA-MM-DD, evento, confirmado: "
                                 "true|false}" % (rot, n))
                elif "tipo" in p and p["tipo"] not in selos.TIPOS_PRAZO:
                    erros.append("%s.prazos[%d].tipo: %r fora de %s" % (rot, n, p["tipo"], "/".join(selos.TIPOS_PRAZO)))
            if secao != "concursos" or campos.get("remover"):
                continue
            # ---- padrao de prova do concurso (so o que este update toca; o legado continua passando)
            if "selo" in campos and campos["selo"] in SELOS and campos["selo"] not in selos.SELOS_CONCURSO:
                erros.append("%s.selo: %r nao e selo de concurso (use %s)" % (rot, campos["selo"],
                                                                         ", ".join(selos.SELOS_CONCURSO)))
            mesclado = dict(por_id.get(ident) or {})
            mesclado.update((carimbos or {}).get(ident) or {})
            mesclado.update(campos)
            promove = campos.get("selo") in selos.SELOS_EXIGEM_OFICIAL
            confirma = any(isinstance(p, dict) and p.get("confirmado") is True for p in campos.get("prazos") or [])
            if (promove or confirma) and not selos.fonte_oficial(mesclado.get("fonte"), mesclado.get("dominio_oficial")):
                erros.append("%s: %s exige fonte oficial em `fonte` (órgão .jus/.gov/.leg/.mp/.def.br ou banca "
                             "organizadora); fonte atual %r — fonte secundária: PENDÊNCIA DE VERIFICAÇÃO e "
                             "confirmado: false" % (rot, ("selo " + campos["selo"]) if promove else "prazo confirmado",
                                                    mesclado.get("fonte")))
            if novo and not str(campos.get("fonte") or "").startswith("http"):
                erros.append("%s: concurso novo exige `fonte` com a URL (http...) da evidência" % rot)
            # E9: o dominio_oficial/url_oficial escritos hoje tambem sao padrao de prova (o paginas_oficiais.py
            # rotula a url_oficial de PAGINA OFICIAL; o inicio.py manda o coletor ler o dominio_oficial)
            uo = campos.get("url_oficial")
            if uo and not (str(uo).startswith("http") and selos.fonte_oficial(str(uo))):
                erros.append("%s.url_oficial: %r não é página oficial (http de órgão .jus/.gov/.leg/.mp/.def.br ou de "
                             "banca de selos.BANCAS_OFICIAIS) — o paginas_oficiais.py a leria como PAGINA OFICIAL; "
                             "deixe sem url_oficial" % (rot, uo))
            do = campos.get("dominio_oficial")
            if do and not selos.dominio_oficial(selos.host(str(do))):
                erros.append("%s.dominio_oficial: %r não é domínio oficial (órgão .jus/.gov/.leg/.mp/.def.br ou banca "
                             "de selos.BANCAS_OFICIAIS) — não sustenta selo nem prazo confirmado; deixe sem ou use o "
                             "do órgão/banca" % (rot, do))
            rel = selos.relativos(campos.get("linha"))
            if rel:
                erros.append("%s.linha: termo relativo %s envelhece no registro — escreva a data (DD/MM)"
                             % (rot, "/".join(rel)))
            if campos.get("pendencia") and campos["pendencia"] not in pend_ids:
                erros.append("%s.pendencia: %r nao existe em pendencias_vivas (nem e criada neste update)"
                             % (rot, campos["pendencia"]))
    ativas = {x.get("id") for x in led.get("armadilhas") or []}
    erros += pendencias_estouradas(upd, led)
    for ident in upd.get("armadilhas_detectadas") or []:
        if ident not in ativas:
            erros.append("ledger_updates.armadilhas_detectadas: %r nao e armadilha ativa" % ident)
    for n, x in enumerate(upd.get("armadilhas_novas") or []):
        if not isinstance(x, dict) or not all(x.get(c) for c in ("id", "fonte", "sintoma", "regra")):
            erros.append("ledger_updates.armadilhas_novas[%d]: exige id, fonte, sintoma, regra" % n)
        elif x["id"] in ativas:
            if not reaplicacao:         # mesma execucao de novo (--refazer, finalizar repetido): ja gravada
                erros.append("ledger_updates.armadilhas_novas: %r ja existe — use armadilhas_detectadas" % x["id"])
        else:
            for c in ("sintoma", "regra"):
                if len(x[c]) > LIMITE[c]:
                    erros.append("ledger_updates.armadilhas_novas[%d].%s: max %d caracteres" % (n, c, LIMITE[c]))
    return erros


def avisos_ledger_updates(upd, led, hoje, banca_res=None):
    """Avisos (nao travam): nota de fonte usada como diario do dia; movimento da banca nao refletido."""
    avisos = []
    upd = upd if isinstance(upd, dict) else {}
    try:
        dm = date.fromisoformat(hoje).strftime("%d/%m") if hoje else ""
    except ValueError:
        dm = ""
    fontes = {f.get("id"): f for f in led.get("fontes") or []}
    for fid, campos in (upd.get("fontes") or {}).items():
        if not isinstance(campos, dict) or not dm or dm not in str(campos.get("nota") or ""):
            continue
        if campos.get("status") in (None, (fontes.get(fid) or {}).get("status")):
            avisos.append("ledger_updates.fontes.%s.nota: traz a data de hoje (%s) sem mudança de status — a nota é "
                          "regra para a próxima execução, não diário (o resultado do dia vai para verification_notes; "
                          "o status técnico dos scripts já vem do fontes_status.json)" % (fid, dm))
    conc = upd.get("concursos") if isinstance(upd.get("concursos"), dict) else {}
    por_id = {c.get("id"): c for c in led.get("concursos") or []}
    avisos += avisos_selo_escrito(conc, por_id, hoje, banca_res)
    avisos += avisos_tipo_prazo(conc, por_id, hoje, banca_res)
    if banca_res:
        import bancas
        for ident, arqs in bancas.novos_por_registro(banca_res).items():
            u = conc.get(ident) or {}
            if not (any(k in u for k in ("linha", "prazos", "remover")) or selos.selo_escrito(u, por_id.get(ident))):
                avisos.append("banca FGV com arquivo novo em %s (%s) e ledger_updates.concursos.%s não toca linha/"
                              "prazos/selo — movimento oficial não refletido no registro%s" % (
                                  ident, "; ".join("%s %s" % (bancas.dm(a.get("data_efetiva") or a["data"]),
                                                              a["titulo"][:60]) for a in arqs[:3]), ident,
                                  "" if bancas.base_dos_novos(banca_res, ident) == "urls_vistas" else
                                  " (1ª leitura sem URLs vistas: se a linha já traz esse fato, ignore)"))
        try:
            pend = bancas.divergencias_pendentes(banca_res, list(por_id.values()), hoje, conc)
        except (KeyError, ValueError, TypeError):
            pend = {}
        for ident, d in sorted(pend.items()):
            if d.get("escrito_hoje"):
                # o prazo ESCRITO hoje contradiz o edital lido hoje (antes passava sem aviso, com carimbo da banca)
                avisos.append('%s %s edital "%s" × update "%s" — confira a fonte da data escrita: se o edital lido '
                              "hoje está certo, corrija prazos/linha em ledger_updates.concursos.%s; se a data vem "
                              "de ato oficial que o edital lido hoje não traz (retificação nova), cite-o na fonte e "
                              "aceite (até lá: sem carimbo da banca e selo por data suspenso)" % (
                                  PRAZO_CONTRA_EDITAL, ident, d["edital"][:170], d["registro"][:120], ident))
                continue
            avisos.append('DIVERGE DO REGISTRO em %s: edital "%s" × registro "%s" — corrija prazos/linha em '
                          "ledger_updates.concursos.%s (movimento oficial não refletido no registro; sem o carimbo "
                          "de verificação da banca hoje)" % (ident, d["edital"][:170], d["registro"][:120], ident))
    return avisos


# prazo escrito hoje que contradiz o edital lido hoje: AVISO no --validar (o montador o mostra como AVISO
# ACIONÁVEL) e ALERTA no relatorio da gravacao (finalizar.sh)
PRAZO_CONTRA_EDITAL = "prazo escrito hoje difere do edital lido hoje:"


def avisos_selo_escrito(conc, por_id, hoje, banca_res=None):
    """Selo da familia de datas ESCRITO hoje (selos.selo_escrito: difere do selo do registro) que contradiz o
    selo por data calculado sobre o registro mesclado: o escrito prevalece, entao avisa (acionavel)."""
    out = []
    if not hoje:
        return out
    import bancas
    try:
        car = bancas.carimbos(banca_res, list(por_id.values()), hoje, upd=conc) if banca_res else {}
    except (KeyError, ValueError, TypeError):
        car = {}
    for ident, u in sorted(conc.items()):
        if not selos.selo_escrito(u, por_id.get(ident)) or u["selo"] not in selos.FAMILIA_DATA:
            continue
        reg = dict(por_id.get(ident) or {})
        reg.update({k: v for k, v in (car.get(ident) or {}).items() if k not in u})
        reg.update({k: v for k, v in u.items() if k != "desfecho"})
        try:
            x = (bancas.contexto_selos(banca_res, [reg], hoje, {ident: u}) if banca_res else {}).get(ident) or {}
        except (KeyError, ValueError, TypeError):
            x = {}
        novo, motivo = selos.selo_por_data(reg, hoje, banca_lida_hoje=x.get("banca_lida_hoje", False),
                                           ultima_retificacao=x.get("ultima_retificacao"),
                                           inicio_inscricoes_banca=x.get("inicio_inscricoes"))
        if novo != u["selo"]:
            out.append("ledger_updates.concursos.%s.selo: %r escrito hoje contradiz o selo por data %r (%s) — o "
                       "escrito prevalece no e-mail e no registro; se não foi decisão, escreva %r ou tire o selo do "
                       "update, ou corrija os prazos" % (ident, u["selo"], novo, (motivo or "").split(": ", 1)[-1],
                                                         novo))
    return out


CLASSE_INSCRICAO = {"inscricoes_fim": "o fim das inscrições", "inscricoes_inicio": "o início das inscrições"}


def avisos_tipo_prazo(conc, por_id, hoje, banca_res=None):
    """`prazos[n].tipo` escrito hoje que esconde um prazo de inscricao (selos.tipo_contradiz_evento: o `evento`,
    pelo texto, e o fim/inicio das inscricoes e o tipo diz outra classe, ex.: 'outro' em "fim das inscrições,
    16h (prorrogado)"). O tipo prevalece: o selo por data, o rebaixamento e o DIVERGE ignoram o prazo, e o
    leitor via INSCRIÇÕES ABERTAS para inscricao que acaba em 2 dias, sem aviso. Nao muda nada (o tipo pode ser
    decisao: o regex do evento erra); diz o que a data daria com a classe do evento, sobre o registro mesclado
    (atual + carimbo da banca + update). Mesmo texto e mesma chave (id, n) do montador (tipo_contra_evento),
    que tira este AVISO do --validar quando da o seu para o mesmo prazo."""
    out = []
    if not hoje:
        return out
    import bancas
    try:
        car = bancas.carimbos(banca_res, list(por_id.values()), hoje, upd=conc) if banca_res else {}
    except (KeyError, ValueError, TypeError):
        car = {}
    for ident, u in sorted(conc.items()):
        if not isinstance(u, dict) or u.get("remover") or not isinstance(u.get("prazos"), list):
            continue
        for n, p in enumerate(u["prazos"]):
            pelo_evento = selos.tipo_contradiz_evento(p)
            if not pelo_evento:
                continue
            daria = ""
            if ident in por_id:
                reg = dict(por_id[ident])
                reg.update({k: v for k, v in (car.get(ident) or {}).items() if k not in u})
                reg.update({k: v for k, v in u.items() if k != "desfecho"})
                alt = dict(reg, prazos=[dict(q, tipo=pelo_evento) if i == n and isinstance(q, dict) else q
                                        for i, q in enumerate(u["prazos"])])
                try:
                    x = (bancas.contexto_selos(banca_res, [reg], hoje, {ident: u}) if banca_res else {}).get(ident) or {}
                    novo, motivo = selos.selo_por_data(alt, hoje, banca_lida_hoje=x.get("banca_lida_hoje", False),
                                                       ultima_retificacao=x.get("ultima_retificacao"),
                                                       inicio_inscricoes_banca=x.get("inicio_inscricoes"))
                except (KeyError, ValueError, TypeError, AttributeError):
                    novo, motivo = reg.get("selo"), None
                if novo != reg.get("selo") and motivo:
                    porque = motivo.split(": ", 1)[-1].split(": ")[0].split(" — ")[0]
                    daria = " (com '%s', o selo por data daria '%s': %s)" % (pelo_evento, novo, porque)
            out.append("ledger_updates.concursos.%s.prazos[%d].tipo: %r num prazo cujo evento é %s («%s») — com "
                       "esse tipo o selo por data ignora o prazo%s; se é %s, escreva tipo '%s' ou omita o tipo; "
                       "se não é, aceite o aviso" % (
                           ident, n, p.get("tipo"), CLASSE_INSCRICAO[pelo_evento], str(p.get("evento") or "")[:80],
                           daria, CLASSE_INSCRICAO[pelo_evento], pelo_evento))
    return out


def retirar_selos_copiados(upd, led):
    """Selo do update IGUAL ao do registro (copia da linha, nao decisao) sai de ledger_updates.concursos, para o
    selo por data valer no helper como no montador (selos.selo_escrito). Devolve os ids (None sem concursos).
    O helper o faz uma vez por arquivo (marca `selos_copiados`): na reaplicacao da mesma entrada (finalizar
    repetido) o registro ja traz o selo decidido, e compara-lo de novo apagaria a decisao."""
    conc = upd.get("concursos") if isinstance(upd, dict) else None
    if not isinstance(conc, dict):
        return None
    por_id = {c.get("id"): c for c in led.get("concursos") or []}
    ids = []
    for ident, u in conc.items():
        if isinstance(u, dict) and "selo" in u and not u.get("remover") and ident in por_id \
                and not selos.selo_escrito(u, por_id[ident]):
            del u["selo"]
            ids.append(ident)
    return sorted(ids)


def aplicar_updates(led, upd, hoje, add_log, retirar_copias=True):
    """Aplica ledger_updates (ja validado). Antes dos contadores, para que
    pendencia criada hoje ja conte a execucao e removida nao gere aviso.
    Idempotente: aplicado de novo (--refazer, finalizar repetido) nao duplica nada.
    Concursos: `mudou_em` = hoje quando linha/selo/prazos mudam (ou o registro nasce).
    retirar_copias: antes de aplicar, tira de `upd` (no lugar) o selo igual ao do registro (copia, nao
    decisao: o selo por data vale depois). False quando a entrada ja veio normalizada (marca
    `selos_copiados`), porque o ledger ja traz o selo decidido e a comparacao apagaria a decisao."""
    if not upd:
        return
    if retirar_copias:
        retirar_selos_copiados(upd, led)
    removidas = []
    for secao, nome_lista in LISTA_DO_LEDGER.items():
        for ident, campos in (upd.get(secao) or {}).items():
            lista = led.setdefault(nome_lista, [])
            if campos.get("remover"):
                antes = len(lista)
                led[nome_lista] = [x for x in lista if x.get("id") != ident]
                if len(led[nome_lista]) != antes:
                    add_log("Ledger: %s %s removida%s" % (secao, ident, (" — " + campos["desfecho"])
                                                          if campos.get("desfecho") else ""))
                if secao == "pendencias":
                    removidas.append(ident)
                continue
            alvo = next((x for x in lista if x.get("id") == ident), None)
            if alvo is not None and not [c for c in campos if c not in NAO_GRAVA]:
                continue        # nada a aplicar (ex.: o update so copiava o selo, ja retirado): sem "atualizada ()"
            if alvo is None:
                alvo = {"id": ident}
                if secao == "pendencias":
                    alvo.update({"desde": hoje, "execucoes": 0})
                lista.append(alvo)
                acao = "criada"
            else:
                acao = "atualizada"
            antes = dict(alvo)
            alvo.update({c: v for c, v in campos.items() if c not in NAO_GRAVA})
            parado = secao == "concursos" and acao == "atualizada" and sem_movimento(campos)
            if secao == "concursos" and (acao == "criada" or (selos.mudou(antes, alvo) and not parado)):
                alvo["mudou_em"] = hoje
            add_log("Ledger: %s %s %s (%s)%s" % (secao, ident, acao, ", ".join(sorted(c for c in campos if c != "movimento")),
                                                 " — sem movimento (mudou_em mantido)" if parado else ""))
    for ident in removidas:              # vinculo do concurso com a pendencia removida
        for c in led.get("concursos") or []:
            if ident and c.get("pendencia") == ident:
                del c["pendencia"]
                add_log("Ledger: concurso %s sem a pendencia %s (removida)" % (c.get("id"), ident))
    ativas = {x.get("id"): x for x in led.get("armadilhas") or []}
    for ident in upd.get("armadilhas_detectadas") or []:
        x = ativas[ident]
        if "detectado_em" in x:                    # formato antigo: lista de datas
            datas = list(x.pop("detectado_em") or [])
            x.update({"detectado_em_qtd": len(datas),
                      "detectado_em_primeira": datas[0] if datas else hoje,
                      "detectado_em_ultimas": datas[-3:]})
        ult = x.get("detectado_em_ultimas") or []
        if hoje not in ult:
            x["detectado_em_qtd"] = int(x.get("detectado_em_qtd") or 0) + 1
            x.setdefault("detectado_em_primeira", hoje)
            x["detectado_em_ultimas"] = (ult + [hoje])[-3:]
            add_log("Ledger: armadilha %s detectada de novo (%d)" % (ident, x["detectado_em_qtd"]))
    for x in upd.get("armadilhas_novas") or []:
        if x.get("id") in ativas:              # re-aplicacao da mesma execucao
            continue
        novo = dict(x)
        novo.update({"detectado_em_qtd": 1, "detectado_em_primeira": hoje, "detectado_em_ultimas": [hoje]})
        led.setdefault("armadilhas", []).append(novo)
        ativas[x["id"]] = novo
        add_log("Ledger: armadilha nova %s" % x["id"])


ALERTA_FALLBACK = ("ALERTA: mecânico dos concursos com fallback (%s — %s: %s): passo pulado, como no e-mail (o "
                   "montador cai igual); a próxima execução refaz com a banca lida de novo")


def aplicar_mecanicos_concursos(led, upd, hoje, banca_res, add_log):
    """Depois dos ledger_updates: carimbo da banca lida hoje e selo por data (nunca sobre selo
    escrito hoje; bancas.selo_do_dia, a regra do montador: suspenso, com ALERTA, enquanto o edital lido hoje
    contestar a data do registro). Idempotente. Devolve o numero de registros alterados."""
    import bancas
    conc = (upd or {}).get("concursos") or {}
    regs = led.get("concursos") or []
    n = 0
    hj = date.fromisoformat(hoje)
    # as MESMAS quedas do montador (montar_email.estado_concursos): excecao na leitura da banca = sem carimbo e/ou
    # sem contexto, como no e-mail ja criado — o ledger nao diverge do e-mail e a execucao do dia nao se perde
    carimbos = {}
    if banca_res:
        try:
            carimbos = bancas.carimbos(banca_res, regs, hj, upd=conc)
        except (KeyError, ValueError, TypeError) as e:
            add_log(ALERTA_FALLBACK % ("bancas.carimbos", type(e).__name__, e))
    for ident, campos in carimbos.items():     # o registro que ainda DIVERGE DO REGISTRO nao e carimbado
        reg = next((c for c in regs if c.get("id") == ident), None)
        u = conc.get(ident) or {}
        campos = {k: v for k, v in campos.items() if k not in u}   # o julgamento de hoje prevalece
        if reg is None or not campos:
            continue
        reg.update(campos)
        n += 1
        add_log("Ledger: carimbo da banca: %s (%s)" % (ident, ", ".join(sorted(campos))))
    try:
        ctx = bancas.contexto_selos(banca_res, regs, hj, conc) if banca_res else {}
        pend = bancas.divergencias_pendentes(banca_res, regs, hj, conc) if banca_res else {}
    except (KeyError, ValueError, TypeError) as e:
        ctx, pend = {}, {}
        add_log(ALERTA_FALLBACK % ("bancas.contexto_selos/divergencias_pendentes", type(e).__name__, e))
    for reg in regs:
        u = conc.get(reg.get("id")) or {}
        if "selo" in u:
            # selo escrito hoje pelo orquestrador: nunca sobrescrever. A copia do selo inalterado ja saiu do
            # update em main() (retirar_selos_copiados, contra o registro de antes): o que sobra e decisao.
            continue
        # a mesma regra do montador (bancas.selo_do_dia): com divergencia pendente o selo por data fica suspenso
        selo, motivo, suspenso = bancas.selo_do_dia(reg, hj, ctx, pend)
        if suspenso:
            add_log("ALERTA: " + suspenso)
            continue
        if selo != reg.get("selo"):
            reg["selo"] = selo
            reg["mudou_em"] = hoje
            n += 1
            add_log("AVISO: selo por data: %s %s" % (reg.get("id"), motivo))
        elif motivo:
            add_log("ALERTA: %s: %s" % (reg.get("id"), motivo))
    return n


def ler_banca(caminho, hoje):
    """$ROBOZINHO_TMP/bancas.json de HOJE (o inicio.py grava `data`); outro dia ou ausente = None."""
    try:
        res = read_json(caminho)
    except (OSError, ValueError):
        return None
    if not isinstance(res, dict) or res.get("data") != hoje:
        return None
    return res


DO_SCRIPT = set()          # ids de fonte cujo status veio do fontes_status.json nesta rodada


def mesclar_fontes_status(ex, caminho, add_log):
    """Status das fontes lidas por script ($ROBOZINHO_TMP/fontes_status.json, gravado por coleta_web,
    informativos e versiculo): preenche o source_status; o do script prevalece sobre o escrito a mao.
    Entradas de outra execucao (execution_id diferente) sao descartadas."""
    try:
        import aguardar_coleta
        st = aguardar_coleta.ler_fontes_status(caminho, ex.get("execution_id"))
    except Exception as e:  # noqa: BLE001 — acessorio
        add_log("AVISO: fontes_status.json nao lido (%s)" % e)
        return
    if not st:
        return
    ss = ex.setdefault("source_status", {})
    for fid, v in sorted(st.items()):
        status = (v or {}).get("status")
        if status not in STATUS_FONTE:
            continue
        DO_SCRIPT.add(fid)
        if fid in ss and ss[fid] != status:
            add_log("AVISO: source_status[%s]: %r escrito, %r do script (%s) — vale o do script"
                    % (fid, ss[fid], status, (v or {}).get("detalhe", "")[:80]))
        ss[fid] = status


def medir_e_preencher(ex, add_log):
    """Uso real (tokens por tipo, chamadas, modelo servido, custo relativo) do orquestrador
    e dos coletores, lido das transcricoes locais. Falha so gera aviso."""
    try:
        import medir_uso
        m = medir_uso.medir(medir_uso._ts(ex.get("run_started_at") or ""))
    except Exception as e:  # noqa: BLE001 — medicao e acessoria
        add_log("AVISO: uso nao medido (%s) — coletores ficam como informados" % e)
        return
    if not m:
        add_log("AVISO: transcricoes locais nao encontradas — uso nao medido")
        return
    col = ex.setdefault("coletores", {})
    for nome, u in (m.get("coletores") or {}).items():
        col.setdefault(nome, {}).update(u)
    if m.get("orquestrador"):
        ex["orquestrador"] = m["orquestrador"]
    resumo = ["%s=%s/%dk/custo %s" % (n, (u.get("modelo") or "?").replace("claude-", ""),
                                      (u.get("contexto_total") or 0) // 1000,
                                      "%.0fk" % (u["custo_relativo"] / 1000) if u.get("custo_relativo") else "?")
              for n, u in [("orquestrador", m.get("orquestrador") or {})] + sorted(col.items())]
    add_log("Uso medido (modelo/contexto processado/custo relativo em tokens de entrada): " + " ".join(resumo))


# Migracao idempotente das regras de armadilha que o codigo tornou falsas (o LEDGER impresso pelo inicio.py e
# "checklist antes de publicar" e vence o prompt mestre). So troca quando a regra atual e uma das antigas, texto
# exato: regra reescrita depois por outra via fica como esta.
REGRAS_ATUALIZADAS = {
    "jota_link_wrapper_mismatch": {
        "antigas": (
            "Publicar o link so se o TITULO da pagina de destino bater com o anunciado. Em nuvem o WebFetch do "
            "wrapper e bloqueado — usar so WebSearch site:jota.info; 1 tentativa por item, senao publicar sem link.",
        ),
        "regra": ("Link do JOTA só o que o coletor trouxe do work/resolver_jota.py (OK = título da página de destino "
                  "conferido); SEM_MATCH, ERRO, SEM_LINK e RECUSADO → sem link, e RECUSADO nunca por outro caminho; "
                  "JA_PUBLICADA só como desdobramento. Resolver BLOQUEADO → só a sondagem curta por WebSearch "
                  "site:jota.info do prompt do coletor, com título igual ao anunciado; nada de WebSearch por item "
                  "fora dela."),
    },
    "gmail_after_epoch": {
        "antigas": (
            "Corrigido na origem em 04/11: inicio.py gera GMAIL_APOS (dia anterior ao início da janela) e os prompts "
            "usam after:AAAA/MM/DD + filtro pelo horário interno. Nunca voltar a epoch; vazio com epoch nunca vale "
            "como ausência.",
            "Usar after:AAAA/MM/DD (dia anterior ao início da janela) e filtrar pelo horário interno do e-mail; "
            "vazio com epoch nunca vale como ausência.",
        ),
        "regra": ("Corrigido na origem: o inicio.py gera GMAIL_APOS = a data do início da janela (o dia anterior, se "
                  "o início for antes das 06:00) e os prompts usam after:AAAA/MM/DD + filtro pelo horário interno. "
                  "Nunca voltar a epoch; vazio com epoch nunca vale como ausência."),
    },
}


def migrar_armadilhas(led):
    """Reescreve a `regra` das armadilhas de REGRAS_ATUALIZADAS cujo texto atual e o antigo. Idempotente.
    Devolve os ids migrados."""
    feitos = []
    for x in (led or {}).get("armadilhas") or []:
        m = REGRAS_ATUALIZADAS.get(x.get("id")) if isinstance(x, dict) else None
        if m and x.get("regra") in m["antigas"]:
            x["regra"] = m["regra"]
            feitos.append(x["id"])
    return feitos


def texto_ledger(led):
    """Uma entrada de lista por linha: compacto para ler e estavel para diff. Validado (json.loads)."""
    partes = []
    for k, v in led.items():
        if isinstance(v, list) and v:
            corpo = ",\n".join("    " + json.dumps(x, ensure_ascii=False) for x in v)
            partes.append("  %s: [\n%s\n  ]" % (json.dumps(k), corpo))
        else:
            partes.append("  %s: %s" % (json.dumps(k), json.dumps(v, ensure_ascii=False)))
    texto = "{\n" + ",\n\n".join(partes) + "\n}\n"
    json.loads(texto)
    return texto


def gravar_texto(caminho, texto):
    """Grava por arquivo temporario + os.replace: quem le nunca ve o arquivo pela metade."""
    parcial = "%s.%d.tmp" % (caminho, os.getpid())
    try:
        with open(parcial, "w", encoding="utf-8", newline="") as f:
            f.write(texto)
        os.replace(parcial, caminho)
    finally:
        if os.path.exists(parcial):
            os.remove(parcial)


def gravar_ledger(caminho, led):
    gravar_texto(caminho, texto_ledger(led))


def aplicar_ledger(caminho, ex, add_log, execucoes=None, banca_res=None):
    """ledger_updates + mecanicos (sempre; idempotentes) e contadores (1 vez por execution_id).
    Antes o guard por execution_id vinha primeiro e descartava em silencio os ledger_updates de
    um --refazer (E14/F7). Le, calcula (calcular_ledger) e grava."""
    led = calcular_ledger(read_json(caminho), ex, add_log, execucoes, banca_res)
    gravar_ledger(caminho, led)
    return led


def calcular_ledger(led, ex, add_log, execucoes=None, banca_res=None):
    """O ledger da gravacao, so em memoria (o main grava junto com o resto: sem gravacao parcial).
    Preserva toda chave que nao conhece (ex.: migracoes_aplicadas, do work/migracoes.py)."""
    hoje = ex["date"]

    def anteriores():           # a execucao de hoje ja esta no historico: nao conta na inicializacao
        lista = execucoes() if callable(execucoes) else (execucoes or [])
        return [e for e in lista if e.get("execution_id") != ex["execution_id"]]
    n = selos.garantir_mudou_em(led.get("concursos") or [], anteriores)
    if n:
        add_log("Ledger: mudou_em inicializado em %d concursos (historico de ledger_updates)" % n)
    migradas = migrar_armadilhas(led)
    if migradas:
        add_log("Ledger: regra da armadilha atualizada para o comportamento atual (migracao): %s"
                % ", ".join(migradas))
    aplicar_updates(led, ex.get("ledger_updates"), hoje, add_log, retirar_copias="selos_copiados" not in ex)
    aplicar_mecanicos_concursos(led, ex.get("ledger_updates"), hoje, banca_res, add_log)
    if led.get("licoes_de_processo") == []:         # E13: lista vazia, sem leitor
        del led["licoes_de_processo"]
    if led.get("atualizado_por_execucao") == ex["execution_id"]:
        add_log("Ledger: contadores ja aplicados para %s — ledger_updates reaplicados, contadores nao."
                % ex["execution_id"])
        texto_ledger(led)
        return led
    fontes = {f.get("id"): f for f in led.get("fontes") or []}
    for fid, v in (ex.get("source_status") or {}).items():
        f = fontes.get(fid)
        if f is None:
            if fid not in DO_SCRIPT:     # status de script (ex.: informativos_docs) sem fonte no ledger: normal
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
    # re-execucao sem rascunho novo (draft_ja_existente) e sem a lista do que foi a edicao: nao ha como saber quais
    # pendencias foram — o aviso "nao foi a edicao" sairia para todas (ruido no relatorio)
    sem_edicao = ex.get("delivery") == "draft_ja_existente" and not (ex.get("items") or ex.get("pendencias"))
    no_ledger = set()
    for p in led.get("pendencias_vivas") or []:
        no_ledger.add(p.get("id"))
        if p.get("id") in ids:
            p["execucoes"] = int(p.get("execucoes") or 0) + 1
            if p.get("faixa") == "ativa" and p["execucoes"] > LIMITE_ATIVA:
                add_log("Ledger: pendencia %s ativa ha %d execucoes (>21) — rebaixar ou aposentar."
                        % (p["id"], p["execucoes"]))
        elif not sem_edicao:
            add_log("Ledger: pendencia %s nao foi a edicao — se resolvida, remova-a." % p.get("id"))
    # pendencia removida pelo ledger_updates desta mesma execucao (a errata herdada sai na edicao e e removida
    # no mesmo resolvido): nao e inconsistencia
    removidas_hoje = {i for i, c in (((ex.get("ledger_updates") or {}).get("pendencias")) or {}).items()
                      if isinstance(c, dict) and c.get("remover")}
    for novo in sorted(ids - no_ledger - removidas_hoje):
        add_log("Ledger: pendencia %s saiu na edicao mas nao existe no ledger." % novo)
    led["atualizado_em"] = now_iso_with_offset()
    led["atualizado_por_execucao"] = ex["execution_id"]
    texto_ledger(led)                   # valida (json.loads) antes de aceitar
    add_log("Ledger: contadores aplicados e JSON validado.")
    return led


def atualizar_estado_concursos(caminho, banca_res, hoje, add_log, paginas_path=None):
    """URLs vistas na banca e hash das paginas oficiais (work/concursos-estado.json): so avancam quando a
    execucao e registrada (o inicio.py so le). Calcula (calcular_estado_concursos) e grava."""
    estado = calcular_estado_concursos(caminho, banca_res, hoje, add_log, paginas_path)
    if estado is not None:
        import bancas
        bancas.gravar_estado(caminho, estado)
    return estado


def calcular_estado_concursos(caminho, banca_res, hoje, add_log, paginas_path=None):
    """O concursos-estado.json da gravacao, so em memoria; None = nada a gravar."""
    pags = None
    if paginas_path:
        try:
            p = read_json(paginas_path)
            pags = p.get("paginas") if isinstance(p, dict) and p.get("data") == hoje else None
        except (OSError, ValueError):
            pags = None
    if not banca_res and not pags:
        return None
    import bancas
    estado = bancas.carregar_estado(caminho)
    partes = []
    if banca_res:
        partes.append("%d arquivo(s) da banca marcados como vistos" % bancas.atualizar_estado(estado, banca_res, hoje))
    if pags:
        try:          # a pagina oficial e reforco: modulo ausente (merge parcial) nunca derruba a gravacao
            import paginas_oficiais
            partes.append("%d página(s) oficial(is) com trecho novo"
                          % paginas_oficiais.atualizar_estado(estado, pags, hoje))
        except Exception as e:  # noqa: BLE001
            add_log("AVISO: paginas_oficiais nao gravadas no estado (%s)" % e)
    if not partes:
        return None
    add_log("Estado de concursos: %s (%s)" % ("; ".join(partes), os.path.basename(caminho)))
    return estado


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


def metricas_derivadas(historico, execucoes_principal, gravacoes=None):
    """Numeros que antes eram mantidos a mao no ledger (metricas.itens_ultimas_10,
    media). Calculados do historico para nao depender de aritmetica manual.
    Tambem agrega o uso dos coletores (campo opcional `coletores` de cada
    execucao: {nome: {tokens, chamadas, duracao_ms, modelo}}). gravacoes: o arquivo
    morto ainda nao gravado nesta rodada (Gravacoes) conta como o que sera gravado."""
    pasta = os.path.dirname(os.path.abspath(historico_path_global))
    arquivadas = 0
    for nome in historico.get("archive_files") or []:
        caminho = os.path.join(pasta, nome)
        if (gravacoes.existe(caminho) if gravacoes else os.path.exists(caminho)):
            try:
                arquivadas += len((gravacoes.ler(caminho) if gravacoes else read_json(caminho)).get("executions") or [])
            except Exception:
                pass

    ult10 = execucoes_principal[-10:]
    itens = [len(e.get("items") or []) for e in ult10]
    media = round(sum(itens) / len(itens), 1) if itens else 0
    # Itens de noticia: sem as ~17 linhas fixas por dia (concursos, versiculo,
    # Munger), que mascaravam o alarme de queda de fonte.
    noticia = [sum(1 for i in (e.get("items") or []) if i.get("categoria") not in NAO_NOTICIA)
               for e in ult10]

    coletores = {}
    for e in ult10:
        for nome, uso in (e.get("coletores") or {}).items():
            c = coletores.setdefault(
                nome, {"execucoes": 0, "tokens_total": 0, "chamadas_total": 0}
            )
            c["execucoes"] += 1
            c["tokens_total"] += int(uso.get("tokens") or 0)
            c["chamadas_total"] += int(uso.get("chamadas") or 0)
            if uso.get("contexto_total"):
                c["medidas"] = c.get("medidas", 0) + 1
                c["contexto_total_soma"] = c.get("contexto_total_soma", 0) + int(uso["contexto_total"])
    for c in coletores.values():
        n = c["execucoes"] or 1
        c["tokens_media"] = round(c["tokens_total"] / n)
        c["chamadas_media"] = round(c["chamadas_total"] / n, 1)
        if c.get("medidas"):
            c["contexto_total_media"] = round(c.pop("contexto_total_soma") / c["medidas"])

    orq = [int((e.get("orquestrador") or {}).get("contexto_total") or 0) for e in ult10
           if (e.get("orquestrador") or {}).get("contexto_total")]
    custos = [c for c in (custo_relativo_execucao(e) for e in ult10) if c]

    # E13: sem "coletores_ultima"/"orquestrador_ultima" (copias de executions[-1], sem leitor)
    return {
        "execucoes_registradas": len(execucoes_principal) + arquivadas,
        "itens_ultimas_10": itens,
        "media_itens": media,
        "itens_ultima": itens[-1] if itens else 0,
        "itens_noticia_ultimas_10": noticia,
        "media_itens_noticia": round(sum(noticia) / len(noticia), 1) if noticia else 0,
        "itens_noticia_ultima": noticia[-1] if noticia else 0,
        "coletores_ultimas_10": coletores,
        "orquestrador_contexto_media": round(sum(orq) / len(orq)) if orq else None,
        "orquestrador_custo_relativo_ultimas_10": custos,
        "orquestrador_custo_relativo_mediana": round(mediana(custos)) if custos else None,
    }


def mediana(xs):
    xs = sorted(xs)
    n = len(xs)
    if not n:
        return None
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def custo_relativo_execucao(e):
    """custo_relativo do orquestrador (medir_uso.py). Execucao antiga, sem o campo: estimado dos
    agregados (leitura = contexto_total - cache_gravado; entrada desprezivel), mesmos pesos."""
    o = e.get("orquestrador") or {}
    if o.get("custo_relativo"):
        return o["custo_relativo"]
    if not o.get("contexto_total"):
        return None
    try:
        import medir_uso
        base = medir_uso.custo_relativo(0, max(0, int(o["contexto_total"]) - int(o.get("cache_gravado") or 0)),
                                        int(o.get("cache_gravado") or 0), int(o.get("saida") or 0))
        # mesma estimativa da chamada final que medir_uso soma as medicoes novas (comparavel com elas)
        return base + medir_uso.custo_relativo(0, int(o.get("tokens") or 0), medir_uso.FECHAMENTO["cache_gravado"],
                                               medir_uso.FECHAMENTO["saida"])
    except Exception:  # noqa: BLE001
        return None


def alertas_uso(execucoes, add_log):
    """ALERTA_ECONOMIA (custo relativo do orquestrador > 1,3x a mediana das 10 anteriores) e ALERTA de
    troca do modelo do orquestrador em relacao a execucao anterior (K5: a troca de 13/11 passou calada)."""
    if not execucoes:
        return
    atual = execucoes[-1]
    anteriores = [e for e in execucoes[:-1] if (e.get("orquestrador") or {}).get("contexto_total")][-10:]
    o = atual.get("orquestrador") or {}
    c = custo_relativo_execucao(atual)
    base = [x for x in (custo_relativo_execucao(e) for e in anteriores) if x]
    med = mediana(base)
    if c and med and c > 1.3 * med:
        add_log("ALERTA_ECONOMIA: custo relativo do orquestrador %.0fk = %.2fx a mediana das ultimas %d (%.0fk) — "
                "chamadas_modelo %s, gravacao de cache %s, saida %s, modelo %s"
                % (c / 1000, c / med, len(base), med / 1000, o.get("chamadas_modelo"), o.get("cache_gravado"),
                   o.get("saida"), o.get("modelo")))
    ant = next((e for e in reversed(execucoes[:-1]) if (e.get("orquestrador") or {}).get("modelo")), None)
    if ant and o.get("modelo") and ant["orquestrador"]["modelo"] != o["modelo"]:
        add_log("ALERTA: modelo do orquestrador mudou: %s (%s) -> %s (%s) — a escolha do modelo e do dono "
                "(README); se nao foi decidida, avise na notificacao"
                % (ant["orquestrador"]["modelo"], ant.get("execution_id"), o["modelo"], atual.get("execution_id")))


NAO_NOTICIA = {"Concursos - Carreira", "Concursos - Apoio", "Versículo", "Munger"}


def em_recesso(iso):
    try:
        d = date.fromisoformat(iso)
    except (TypeError, ValueError):
        return False
    return (d.month == 7 and d.day >= 2) or (d.month == 12 and d.day >= 20) or d.month == 1


historico_path_global = ""


class Gravacoes:
    """As gravacoes de estado do helper, adiadas para o fim e feitas todas ou nenhuma (verified[14]: antes o
    historico e o estado eram gravados e so depois o ledger era calculado; uma excecao ali deixava o historico
    gravado sem o ledger). Tudo e calculado em memoria; `aplicar` grava em ordem, guardando o conteudo de antes
    de cada arquivo, e se uma gravacao (ou a conferencia final) falha devolve todos ao que eram."""

    def __init__(self):
        self.fila = []           # (caminho, texto | None, funcao | None)
        self.dados = {}          # caminho absoluto -> dados (quem le o que ainda vai ser gravado)

    def json(self, caminho, dados):
        """Mesmo formato do write_json_no_bom (indent 2, UTF-8 sem BOM)."""
        self.texto(caminho, json.dumps(dados, ensure_ascii=False, indent=2), dados)

    def texto(self, caminho, texto, dados=None):
        self.fila = [x for x in self.fila if x[0] != caminho] + [(caminho, texto, None)]
        if dados is not None:
            self.dados[os.path.abspath(caminho)] = dados

    def funcao(self, caminho, gravar):
        """Gravacao feita por funcao de outro modulo (ex.: bancas.gravar_estado), com a mesma restauracao."""
        self.fila = [x for x in self.fila if x[0] != caminho] + [(caminho, None, gravar)]

    def existe(self, caminho):
        return os.path.abspath(caminho) in self.dados or os.path.exists(caminho)

    def ler(self, caminho):
        d = self.dados.get(os.path.abspath(caminho))
        return d if d is not None else read_json(caminho)

    def aplicar(self, add_log, conferir=None):
        antes = []
        atual = None
        try:
            for caminho, texto, gravar in self.fila:
                atual = caminho
                anterior = None
                if os.path.exists(caminho):
                    with open(caminho, "rb") as f:
                        anterior = f.read()
                antes.append((caminho, anterior))
                if gravar is not None:
                    gravar()
                else:
                    gravar_texto(caminho, texto)
            atual = "conferencia"
            if conferir:
                conferir()
        except BaseException as e:
            for caminho, anterior in reversed(antes):
                try:
                    if anterior is None:
                        if os.path.exists(caminho):
                            os.remove(caminho)
                    else:
                        parcial = "%s.%d.volta" % (caminho, os.getpid())
                        with open(parcial, "wb") as f:
                            f.write(anterior)
                        os.replace(parcial, caminho)
                except OSError:
                    pass
            add_log("ERRO: gravacao interrompida em %s (%s: %s) — os %d arquivo(s) ja gravados voltaram ao que eram"
                    % (os.path.basename(atual or "?"), type(e).__name__, e, len(antes)))
            raise


def onde_falhou(e):
    """arquivo:linha do ponto mais interno da excecao (o relatorio diz onde o codigo quebrou)."""
    import traceback
    tb = traceback.extract_tb(e.__traceback__)
    return "%s:%d" % (os.path.basename(tb[-1].filename), tb[-1].lineno) if tb else "?"


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
    parser.add_argument("--validar", action="store_true",
                        help="so valida (inclusive ledger_updates e repeticao); nao grava nada")
    parser.add_argument("--draft-id", dest="draft_id", default="")
    parser.add_argument("--medir-uso", dest="medir_uso", action="store_true")
    parser.add_argument("--janela", default=os.path.join(TMP, "janela.json"))
    parser.add_argument("--bancas", default=os.path.join(TMP, "bancas.json"),
                        help="bancas.json do inicio.py (carimbo, selo por data, URLs vistas)")
    parser.add_argument("--fontes-status", dest="fontes_status", default=os.path.join(TMP, "fontes_status.json"))
    parser.add_argument("--estado-concursos", dest="estado_concursos", default="",
                        help="padrao: concursos-estado.json ao lado do historico")
    args = parser.parse_args()

    log = []
    emitido = []

    def add_log(linha):
        log.append(linha)

    def emitir(status_final):
        """O relatorio sai SEMPRE (inclusive em erro interno): e o que o finalizar.sh e a §R11 leem."""
        add_log(status_final)
        emitido.append(status_final)
        texto = "\n".join(log)
        if args.relatorio_path:
            try:
                with open(args.relatorio_path, "w", encoding="utf-8", newline="") as f:
                    f.write(texto)
            except OSError as e:
                texto += "\nAVISO: relatorio nao gravado em %s (%s)" % (args.relatorio_path, e)
        print(texto)

    try:
        executar(args, add_log, emitir)
    except SystemExit as e:
        if emitido or e.code in (0, None):
            raise                       # saida deliberada, ja com o relatorio (ex.: ERRO DE VALIDACAO, exit 2)
        erro_interno(args, emitir, "SystemExit", e.code, None)
    except BaseException as e:  # noqa: BLE001 — o relatorio sai sempre; nada fica gravado pela metade
        import traceback
        traceback.print_exc()
        erro_interno(args, emitir, type(e).__name__, e, onde_falhou(e))


def erro_interno(args, emitir, tipo, msg, onde):
    """STATUS: ERRO INTERNO: falha do codigo ou de um dado inesperado, nao do execucao.json. As gravacoes de
    estado sao todas ou nenhuma (Gravacoes): nada foi gravado. Exit 4 (o finalizar.sh nao commita)."""
    det = "%s: %s%s" % (tipo, msg, " (%s)" % onde if onde else "")
    if args.validar:
        emitir("VALIDACAO: ERRO INTERNO %s — nada foi gravado." % det)
    else:
        emitir("STATUS: ERRO INTERNO %s — nada foi gravado no estado; nada commitado. Repita o finalizar.sh uma vez; "
               "persistindo, nao edite codigo nem o execucao.json para contornar" % det)
    sys.exit(4)


def executar(args, add_log, emitir):
    # -------------------------------------------------------------
    # 1. Carregar historico e nova execucao
    # -------------------------------------------------------------
    g = Gravacoes()
    if not os.path.exists(args.historico_path):
        envelope = {
            "schema_version": 1,
            "timezone": "America/Sao_Paulo",
            "newsletter": None,
            "recipients": [],
            "archive_files": [],
            "executions": [],
        }
        if args.validar:
            historico = envelope
        else:
            g.json(args.historico_path, envelope)
            historico = json.loads(json.dumps(envelope))
        add_log("AVISO: historico inexistente; envelope novo criado.")
    else:
        historico = read_json(args.historico_path)
    historico.setdefault("executions", [])
    historico.setdefault("archive_files", [])

    if not os.path.exists(args.nova_execucao_path):
        raise SystemExit(
            f"Arquivo da nova execucao nao encontrado: {args.nova_execucao_path}"
        )
    nova_exec = read_json(args.nova_execucao_path)
    preenchidos = completar_cabecalho(nova_exec, args.janela)
    for campo in ("verification_notes", "errors"):   # texto solto (16/10) vira lista
        if isinstance(nova_exec.get(campo), str):
            nova_exec[campo] = [nova_exec[campo]] if nova_exec[campo].strip() else []

    if not nova_exec.get("execution_id"):
        raise SystemExit("A nova execucao nao possui execution_id.")
    add_log("Nova execucao: " + nova_exec["execution_id"] +
            (" (do inicio.py: %s)" % ", ".join(preenchidos) if preenchidos else ""))
    mesclar_fontes_status(nova_exec, args.fontes_status, add_log)

    if args.draft_id:
        nova_exec["draft_id"] = args.draft_id
    if not args.validar:
        if nova_exec.get("run_finished_at") in (None, "", "PENDENTE"):
            nova_exec["run_finished_at"] = now_iso_with_offset()
        if args.medir_uso:
            medir_e_preencher(nova_exec, add_log)

    chaves_anteriores = {
        it.get("chave")
        for e in historico["executions"]
        if e.get("execution_id") != nova_exec["execution_id"]
        for it in e.get("items") or []
        if it.get("chave")
    }
    # §R1 (verified[45]): a edicao de hoje ja existe sem registro (sessao que caiu antes do finalizar.sh). O fim da
    # janela do inicio.py e a hora DESTA re-execucao: grava-lo como window_end pularia tudo o que saiu entre a edicao
    # achada e agora. O orquestrador escreve a data do rascunho/envio achado; o helper nao completa o campo.
    r1 = (not args.validar and nova_exec.get("delivery") == "draft_ja_existente"
          and not any(e.get("execution_id") == nova_exec["execution_id"] for e in historico["executions"]))
    fim_inicio = None
    if r1 and "window_end" in preenchidos:
        fim_inicio = nova_exec.pop("window_end")
        preenchidos.remove("window_end")
    erros, avisos = validar(nova_exec, chaves_anteriores, pre_rascunho=args.validar)
    if r1:
        erros = erros_window_end_r1(nova_exec, erros, fim_inicio or janela_fim(args.janela))
    banca_res = ler_banca(args.bancas, nova_exec.get("date"))
    led_atual = None
    if args.ledger_path and os.path.exists(args.ledger_path):
        led_atual = read_json(args.ledger_path)
        carimbos = {}
        if banca_res:
            import bancas
            try:
                carimbos = bancas.carimbos(banca_res, led_atual.get("concursos") or [],
                                           date.fromisoformat(nova_exec["date"]),
                                           upd=((nova_exec.get("ledger_updates") or {}).get("concursos") or {}))
            except (KeyError, ValueError, TypeError):
                carimbos = {}
        erros += validar_ledger_updates(nova_exec.get("ledger_updates"), led_atual, hoje=nova_exec.get("date"),
                                        ex_id=nova_exec.get("execution_id"), carimbos=carimbos)
        avisos += avisos_ledger_updates(nova_exec.get("ledger_updates"), led_atual, nova_exec.get("date"), banca_res)
    elif nova_exec.get("ledger_updates"):
        avisos.append("ledger_updates presente, mas --ledger nao informado: nao sera aplicado")
    if args.validar:
        avisos += checar_repeticao(nova_exec, historico["executions"], chaves_anteriores)
    for a in avisos:
        # na gravacao, o prazo escrito hoje contra o edital lido hoje e ALERTA (vai a notificacao); no --validar
        # fica AVISO (o montador o le assim e o mostra como AVISO ACIONÁVEL)
        add_log(("ALERTA: " if not args.validar and a.startswith(PRAZO_CONTRA_EDITAL) else "AVISO: ") + a)
    if erros:
        for e in erros:
            add_log("ERRO: " + e)
        emitir("VALIDACAO: ERRO — corrija /tmp/execucao.json e valide de novo." if args.validar
               else "STATUS: ERRO DE VALIDACAO — nada foi gravado. Corrija o arquivo da "
                    "nova execucao e rode de novo.")
        sys.exit(2)
    if args.validar:
        try:
            from zoneinfo import ZoneInfo
            agora = datetime.now(ZoneInfo("America/Sao_Paulo"))
        except Exception:
            agora = datetime.now()
        add_log("CARIMBO: Gerado em %s (America/São Paulo) · execução %s"
                % (agora.strftime("%d/%m/%Y %H:%M"), nova_exec["execution_id"]))
        emitir("VALIDACAO: OK (%d itens, %d avisos) — nada foi gravado."
               % (len(nova_exec.get("items") or []), len(avisos)))
        return
    # Re-execucao no mesmo dia SEM rascunho novo (a edicao ja existe): o registro da
    # execucao original fica como esta. Antes ele era substituido por um registro vazio,
    # o que apagava os itens publicados (deduplicacao) e adiantava o fim da janela —
    # a edicao seguinte pularia o intervalo (disparo extra de 11/11/2026, 16h40).
    original = next((e for e in historico["executions"]
                     if e.get("execution_id") == nova_exec["execution_id"]), None)
    if original is not None and nova_exec.get("delivery") == "draft_ja_existente":
        add_log("RE-EXECUCAO sem rascunho novo: registro %s preservado (%d itens, delivery=%s, janela ate %s)."
                % (original.get("execution_id"), len(original.get("items") or []),
                   original.get("delivery"), original.get("window_end")))
        g.aplicar(add_log)              # so o envelope novo, se o historico nao existia
        emitir("STATUS: OK — nada a gravar (duplicata; historico, estado e ledger intactos)")
        return

    # Selo copiado sem mudanca nao e decisao: sai do update (vale o selo por data), contra o ledger de antes da
    # gravacao. Uma vez por arquivo (`selos_copiados` marca): o finalizar repetido reaplica a entrada ja
    # normalizada sobre o ledger ja atualizado, e la o selo decidido seria igual ao do registro.
    if isinstance(led_atual, dict) and isinstance(nova_exec.get("ledger_updates"), dict) \
            and "selos_copiados" not in nova_exec:
        copiados = retirar_selos_copiados(nova_exec["ledger_updates"], led_atual)
        if copiados is not None:
            nova_exec["selos_copiados"] = copiados
            if copiados:
                add_log("Ledger: selo igual ao do registro retirado do update (copia, nao decisao; vale o selo por "
                        "data): %s" % ", ".join(copiados))
    # O historico guarda o registro do que saiu, nao o texto do e-mail: os campos que so
    # servem a montagem (work/montar_email.py) ficam de fora para o arquivo nao inchar.
    nova_exec.pop("email", None)
    for it in nova_exec.get("items") or []:
        if it.get("nota") and not it.get("observacao"):
            it["observacao"] = it["nota"]
        for campo in ("resumo", "destaques", "destaques_texto", "grupo", "meta", "nota", "herdada", "autor",
                      "impacto", "resenha", "desdobramento", "resumo_truncado"):
            it.pop(campo, None)
    # grava a versao normalizada, para o historico ficar consistente (a entrada e uma copia do finalizar.sh)
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
        elif args.reconciliar_message_id:
            # "sent" so com prova: o message_id achado em in:sent no passo 2 (E2)
            alvo["delivery"] = "sent"
            alvo["gmail_message_id"] = args.reconciliar_message_id
            alvo.pop("delivery_check", None)
            alvo["delivery_reconciled_at"] = now_iso_with_offset()
            add_log("Reconciliado: " + args.reconciliar_id + " -> delivery=sent")
        elif alvo.get("delivery") == "sent":
            add_log("Reconciliacao: %s ja estava sent — nada a fazer." % args.reconciliar_id)
        else:
            alvo["delivery_check"] = "ausente_em_sent"
            alvo["delivery_checked_at"] = now_iso_with_offset()
            add_log("ALERTA: edicao anterior %s sem --message-id (nao achada em in:sent no passo 2): delivery "
                    "segue %r e delivery_check=ausente_em_sent — conferir se o Apps Script enviou"
                    % (args.reconciliar_id, alvo.get("delivery")))

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
    #    do mes). Tudo em memoria: a gravacao e no fim (Gravacoes).
    # -------------------------------------------------------------
    pasta_hist = os.path.dirname(os.path.abspath(args.historico_path))
    total = len(historico["executions"])
    if total > args.max_execucoes:
        excedente = total - args.max_execucoes
        para_arquivar = historico["executions"][:excedente]
        historico["executions"] = historico["executions"][excedente:]

        for item in para_arquivar:
            data_ref = item.get("date") or datetime.now().strftime("%Y-%m-%d")
            ano_mes = data_ref[0:7]
            arquivo_morto = os.path.join(
                pasta_hist, f"resumo-legislativo-historico-arquivo-{ano_mes}.json"
            )

            if g.existe(arquivo_morto):
                arq = g.ler(arquivo_morto)
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
                g.json(arquivo_morto, arq)
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

    # E13: arquivo morto listado que nao existe (ex.: ...-2026-06.json) sai da lista
    sumidos = [a for a in historico["archive_files"] if a and not g.existe(os.path.join(pasta_hist, a))]
    if sumidos:
        historico["archive_files"] = [a for a in historico["archive_files"] if a and a not in sumidos]
        add_log("archive_files: retirados %s (arquivo inexistente)" % ", ".join(sumidos))

    # -------------------------------------------------------------
    # 5. Historico principal (texto final, conferido antes de gravar)
    # -------------------------------------------------------------
    texto_hist = json.dumps(historico, ensure_ascii=False, indent=2)
    verif = json.loads(texto_hist)
    g.texto(args.historico_path, texto_hist, verif)

    # -------------------------------------------------------------
    # 6. Validar o texto que sera gravado (e, depois da gravacao, relido do disco)
    # -------------------------------------------------------------
    add_log("Execucoes no arquivo principal: " + str(len(verif["executions"])))
    add_log(
        "IDs: "
        + ", ".join(e.get("execution_id", "") for e in verif["executions"])
    )

    gravada = any(
        e.get("execution_id") == nova_exec["execution_id"] for e in verif["executions"]
    )
    if not gravada:
        raise SystemExit("FALHA: a nova execucao nao foi encontrada no historico a gravar.")

    # Deteccao de mojibake: sequencias tipicas de UTF-8 lido como
    # ANSI/cp1252 e regravado. Regex identica (em codepoints) a
    # work/Update-Historico.ps1: Ã[ -¿] ou â
    padrao_mojibake = "Ã[ -¿]|â"
    suspeitas = re.findall(padrao_mojibake, texto_hist)
    if suspeitas:
        add_log(
            f"ALERTA DE ENCODING: {len(suspeitas)} ocorrencia(s) de mojibake "
            "detectada(s). Revisar antes de considerar a execucao concluida."
        )
    else:
        add_log("Encoding: nenhuma marca de mojibake detectada.")

    # -------------------------------------------------------------
    # 6-A. Resumo de estado (robozinho-estado.json)
    # -------------------------------------------------------------
    estado_path = os.path.join(pasta_hist, "robozinho-estado.json")

    ultima = verif["executions"][-1]

    # E13: o estado nao guarda mais chaves_publicadas nem pendencias_ultima (copias sem leitor:
    # a repeticao e o resolver_jota leem o proprio historico).
    todas = verif["executions"]

    global historico_path_global
    historico_path_global = args.historico_path
    metricas = metricas_derivadas(verif, todas, g)

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
        "metricas": metricas,
    }

    g.json(estado_path, estado)
    add_log(f"Estado emitido: robozinho-estado.json (ultima execucao {ultima.get('execution_id')})")
    add_log(
        "Metricas: itens_ultima=%d (noticia=%d) media_itens_10=%s (noticia=%s) execucoes_registradas=%d"
        % (
            metricas["itens_ultima"],
            metricas["itens_noticia_ultima"],
            metricas["media_itens"],
            metricas["media_itens_noticia"],
            metricas["execucoes_registradas"],
        )
    )
    alertas_uso(todas, add_log)
    feriado_janela = []
    try:
        feriado_janela = [f for f in (read_json(args.janela).get("feriados_na_janela") or [])
                          if f.get("tipo") in ("nacional", "justica_federal")]
    except Exception:  # noqa: BLE001
        pass
    # §R1 (draft_ja_existente, sem itens): a contagem baixa e do registro, nao de fonte em falha — sem ALERTA
    if metricas["itens_noticia_ultima"] < 10 and not em_recesso(ultima.get("date")) and not feriado_janela \
            and ultima.get("delivery") != "draft_ja_existente":
        add_log("ALERTA: so %d itens de noticia (fora concursos/versiculo/Munger) numa janela "
                "fora do recesso — sinal de falha de fonte; conferir os coletores."
                % metricas["itens_noticia_ultima"])

    # -------------------------------------------------------------
    # 7. Ledger: ledger_updates, mecanicos dos concursos e contadores (opcional), em memoria
    # -------------------------------------------------------------
    if args.ledger_path:
        if os.path.exists(args.ledger_path):
            def todas_execucoes():
                out = list(todas)
                for nome in historico.get("archive_files") or []:
                    try:
                        out += g.ler(os.path.join(pasta_hist, nome)).get("executions") or []
                    except Exception:  # noqa: BLE001
                        pass
                return out
            led = calcular_ledger(read_json(args.ledger_path), nova_exec, add_log, todas_execucoes, banca_res)
            g.texto(args.ledger_path, texto_ledger(led), led)
            caminho_ce = args.estado_concursos or os.path.join(pasta_hist, "concursos-estado.json")
            try:          # URLs vistas e paginas oficiais sao reforco: falha aqui nao derruba a gravacao do dia
                estado_ce = calcular_estado_concursos(
                    caminho_ce, banca_res, nova_exec["date"], add_log,
                    os.path.join(os.path.dirname(os.path.abspath(args.bancas)), "paginas_oficiais.json"))
            except Exception as e:  # noqa: BLE001
                estado_ce = None
                add_log("AVISO: estado de concursos nao atualizado (%s: %s, %s) — os arquivos da banca de hoje "
                        "voltam como novos amanha" % (type(e).__name__, e, onde_falhou(e)))
            if estado_ce is not None:
                import bancas
                g.funcao(caminho_ce, lambda: bancas.gravar_estado(caminho_ce, estado_ce))
        else:
            add_log("AVISO: ledger nao encontrado: " + args.ledger_path)

    # -------------------------------------------------------------
    # 8. Gravar tudo (todas ou nenhuma) e conferir o historico relido do disco
    # -------------------------------------------------------------
    def conferir():
        relido = read_json(args.historico_path)
        if not any(e.get("execution_id") == nova_exec["execution_id"] for e in relido.get("executions") or []):
            raise SystemExit("FALHA: a nova execucao nao foi encontrada apos a gravacao.")
    g.aplicar(add_log, conferir)
    emitir("STATUS: OK")


if __name__ == "__main__":
    main()
