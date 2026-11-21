#!/usr/bin/env python3
# =====================================================================
# resolver_jota.py — resolve os links-wrapper do JOTA (t.rdsv2.net) por
# curl e confere se o titulo da pagina final bate com o anunciado.
# Substitui ate 16 WebSearch por execucao QUANDO t.rdsv2.net e
# www.jota.info estiverem no allowlist do ambiente; senao imprime
# BLOQUEADO e sai com 3 (o coletor cai no fallback por WebSearch).
#
# SEGURANCA (16/11/2026; lista de permitidos em 17/11): o rodape do e-mail
# traz "parar de receber esta newsletter" no mesmo wrapper t.rdsv2.net das
# materias. Nada aqui segue redirecionamento as cegas (antes: curl -L):
#   - linha cujo TITULO e de descadastro ("Caso nao queira mais receber estes
#     e-mails...", "cancele sua inscricao", "Sair da lista", "Voce recebeu este
#     e-mail porque...", com ou sem acento), termina em oracao so de saida
#     ("... Para sair, clique aqui") ou nao diz nada ("clique aqui", "aqui",
#     "Sair") -> RECUSADO antes de
#     qualquer pedido, nem o wrapper e tocado (via inline titulo<TAB>wrapper);
#   - cada salto e resolvido SEM seguir (-o /dev/null -w redirect_url), no
#     maximo 5, e so no caminho de clique do rastreio (t.rdsv2.net/ls/click);
#   - antes de QUALQUER pedido, a URL passa pela LISTA DE PERMITIDOS
#     (motivo_proibido): jota.info so com o 1o segmento numa editoria
#     (stf, justica, tributos, opiniao-e-analise...), slug de materia, nenhum
#     segmento de conta/newsletter/preferencias e nenhuma palavra de
#     descadastro fora do slug; no slug da materia so "remover"/"cancelar"
#     soltos passam (.../nunes-marques-manda-remover-em-24h-...), "preferenc"
#     e frase de descadastro nunca;
#   - so o GET final, no jota.info, baixa a pagina (para conferir o titulo).
#   Destino fora da lista -> RECUSADO, sem pedido nenhum a ele.
#   Links que o work/jota_extrair.py reconheceu como descadastro nem entram
#   no indice $ROBOZINHO_TMP/jota_urls.tsv.
#
# HISTORICO (16/11: 2 materias ja publicadas em 12/11 sairam OK e so o
# montador as pegou): cada titulo e procurado no historico com
# work/repeticao.py (ignorar_execucao do janela.json vale para re-execucao);
# a URL final tambem e comparada com as URLs ja publicadas.
#
# USO:   python3 work/resolver_jota.py [$ROBOZINHO_TMP/jota_links.tsv]
#        [--urls $ROBOZINHO_TMP/jota_urls.tsv] [--janela $ROBOZINHO_TMP/janela.json]
#        [--historico work/resumo-legislativo-historico.json] [--sem-historico]
# ENTRADA (uma linha por item; vazia ou iniciada por # e ignorada):
#        titulo<TAB>url              (url do wrapper ou url direta do jota.info)
#        titulo<TAB>L<n>             (indice do jota_urls.tsv gravado pelo jota_extrair.py;
#                                     aceita tambem [L<n>])
#        titulo                      (sem link: so a checagem de historico; idem
#                                     titulo<TAB>sem link ou qualquer coisa que nao seja URL/L<n>)
# SAIDA (uma linha por item, na ordem da entrada, campos separados por TAB):
#        OK<TAB>titulo<TAB>url-final (sem utm_/rd_)[<TAB>DD/MM HH:MM<TAB>autor<TAB>linha-fina]
#              (21/11: os metadados da pagina ja baixada — article:published_time, author e
#              og:description, ate 200 caracteres — vao junto quando existem; publicada antes
#              do inicio da janela: "DD/MM HH:MM (antes da janela)". 9 de 19 itens do JOTA de
#              17-20/11 sairam com a data do e-mail, nao a da materia, e varios sem resumo.)
#        SEM_MATCH<TAB>titulo<TAB>titulo-da-pagina
#        ERRO<TAB>titulo<TAB>motivo
#        RECUSADO<TAB>titulo<TAB>motivo          (destino proibido: nenhum pedido a ele)
#        JA_PUBLICADA<TAB>titulo<TAB>chave-parecida-do-historico
#        SEM_LINK<TAB>titulo<TAB>nao publicada antes   (linha sem URL)
#        BLOQUEADO<TAB><host> http=<codigo> — usar o fallback por WebSearch
#              (primeira linha; depois so as JA_PUBLICADA/SEM_LINK; sai com 3)
#        AVISO<TAB>-<TAB>historico indisponivel: sem checagem JA_PUBLICADA
#        JA SAIU DD/MM — Mídia: <titulo> [fonte] · ... | Fofoquinha: ...   (no fim; com historico)
#              Midia e Fofoquinha das 2 ultimas edicoes (repeticao.ja_saiu): a mesma historia com
#              outro titulo ("Dino da mais prazo" x "Mais tempo de reflexao") e o coletor que
#              compara — vai como JA_PUBLICADA ou como desdobramento dito no titulo.
# =====================================================================

import argparse
import html
import json
import os
import re
import subprocess
import sys
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import parse_qsl, unquote, urlencode, urljoin, urlsplit, urlunsplit

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import jota_extrair  # noqa: E402
import repeticao  # noqa: E402

TMP = os.environ.get("ROBOZINHO_TMP", "/tmp")
TZ = ZoneInfo("America/Sao_Paulo")
MAX_LINHA_FINA = 200
UA = "Mozilla/5.0 (X11; Linux x86_64) Robozinho/1.0"
HOSTS_JOTA = {"www.jota.info", "jota.info"}
RASTREIO = {"t.rdsv2.net"}        # wrappers resolvidos salto a salto (sem baixar nada)
MAX_SALTOS = 5
REDIRECIONA = {301, 302, 303, 307, 308}
# LISTA DE PERMITIDOS (17/11/2026; antes era so uma lista de palavras proibidas,
# e "/newsletter/cancelamento", "/newsletter/sair-da-lista" ou "/conta/
# preferencias-..." passavam e recebiam GET com corpo). Recebe pedido so:
#   - o wrapper de clique do rastreio (t.rdsv2.net/ls/click ou /wf/click);
#   - pagina do jota.info cujo 1o segmento e uma editoria (EDITORIAS), com pelo
#     menos 2 segmentos, slug final de materia (>= 3 palavras, so [a-z0-9-]),
#     nenhum segmento de conta/newsletter (SEGMENTOS_CONTA) e
#     "/newsletters/<nome>/<slug de materia>" so nesse formato exato.
# Palavras: PROIBIDO (unsub, descadastr, opt-out, preferenc) vale em qualquer
# parte, inclusive slug e utm_*; PROIBIDO_FORA_DO_SLUG vale nos segmentos antes
# do slug e na consulta sem utm_/rd_, e tambem no slug curto (<= 5 palavras); no
# slug longo, "remover"/"cancelar" soltos sao isentos (".../manda-remover-em-
# 24h-postagens..."), nunca quando formam frase de descadastro
# (FRASE_DESCADASTRO: "cancelar-inscricao...", "remover-meu-email").
EDITORIAS = {
    "stf", "justica", "tributos", "tributos-e-empresas", "opiniao-e-analise", "legislativo", "executivo",
    "trabalho", "saude", "eleicoes", "coberturas-especiais", "poder", "energia", "internacional",
    "tecnologia", "advocacia", "carreira", "regulacao", "mercado", "infraestrutura", "meio-ambiente",
    "educacao", "dados", "especiais", "podcasts", "videos", "pro", "newsletters"}
SEGMENTOS_CONTA = {
    "newsletter", "conta", "contas", "minha-conta", "minhaconta", "my-account", "account", "email", "e-mail",
    "emails", "perfil", "assinatura", "assinaturas", "assine", "preferencias", "preferencia", "login", "logout",
    "entrar", "sair", "cadastro", "cadastre-se", "registro", "inscricao", "inscricoes", "wp-admin",
    "wp-login.php", "wp-json", "api", "cancelamento", "cancelar", "remover"}
PROIBIDO = re.compile(r"unsub|descadastr|opt-?out|opt_out|preferenc")       # em qualquer parte
# fora do slug (no slug sao manchete: ".../aposentados-podem-deixar-de-receber-...")
PROIBIDO_FORA_DO_SLUG = re.compile(r"manage|remov|cancel|inscri|assinatura|newsletter|e-?mail|gerenci|desinscrev|"
                                   r"sa(?:ir|ia)-d[aeo]s?-lista|(?:parar|pare|deixar|deixe)-de-receber|"
                                   r"nao-(?:[a-z]+-){0,2}?(?:mais-receber|receber-mais)|"
                                   r"caso-nao-(?:queira|quiser|deseje)")
# (conta/perfil/login: SEGMENTOS_CONTA). Caminho e consulta sao conferidos DOBRADOS
# (jota_extrair.dobrar: "prefer%C3%AAncias" -> "preferencias", "n%C3%A3o" -> "nao").
FRASE_DESCADASTRO = re.compile(r"(?:^|-)(?:cancel|remov|sair|desinscrev|desativ)[a-z]*"
                               r"(?:-[a-z0-9]+){0,3}?-(?:inscri|assinatura|e-?mail|newsletter)")
# Titulo da linha (via inline "titulo<TAB>wrapper"), conferido DOBRADO (sem
# acento, qualquer espaco): os trechos do DESCADASTRO que tambem aparecem em
# manchete ("Aposentados podem deixar de receber...", "Brasil pode sair da lista
# suja...", "TSE manda cancelar inscricao...", "...nao precisa mais receber...")
# so contam com contexto de e-mail ou em texto curto de link (<= 6 palavras).
# Titulo que nao diz nada ("clique aqui", "aqui", vazio) ou so verbo de saida
# ("Sair", "Cancelar") e rodape copiado sem contexto: RECUSADO tambem.
# A regra (TRECHO_FRACO, CONTEXTO_EMAIL, ate 6 palavras) e UMA SO, a do
# jota_extrair.descadastro_no_texto (volta 3): o texto do link no extrator e o
# titulo aqui sao julgados do mesmo jeito. Nomes mantidos por compatibilidade.
TRECHO_FRACO = jota_extrair.TRECHO_FRACO
CONTEXTO_EMAIL = jota_extrair.CONTEXTO_EMAIL
CAMINHOS_RASTREIO = {"/ls/click", "/wf/click"}


def curl(url, corpo=False, timeout=20):
    """UM pedido, sem seguir redirecionamento. Devolve (codigo, redirect_url, html)."""
    cmd = ["curl", "-s", "-m", str(timeout), "-A", UA,
           "-w", "\n%{http_code} %{redirect_url}"]
    if not corpo:
        cmd += ["-o", "/dev/null"]
    try:
        r = subprocess.run(cmd + [url], capture_output=True, timeout=timeout + 5)
        out = r.stdout.decode("utf-8", "replace")
    except Exception:
        return 0, "", ""
    pagina, _, fim = out.rpartition("\n")
    codigo, _, prox = fim.partition(" ")
    return (int(codigo) if codigo.isdigit() else 0), prox.strip(), pagina


def palavras(s):
    s = unicodedata.normalize("NFKD", html.unescape(s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return {w for w in re.findall(r"[a-z0-9]+", s) if len(w) > 2}


def bate(anunciado, pagina):
    a, p = palavras(anunciado), palavras(pagina)
    return bool(a) and len(a & p) / len(a) >= 0.6


def sem_rastreio(url):
    u = urlsplit(url)
    q = [(k, v) for k, v in parse_qsl(u.query) if not k.lower().startswith(("utm_", "rd_"))]
    return urlunsplit((u.scheme, u.netloc, u.path, urlencode(q), ""))


def motivo_proibido(url):
    """'' se a URL pode receber um pedido; senao o motivo da recusa (lista de permitidos)."""
    u = urlsplit(url)
    host = (u.hostname or "").lower()
    if u.scheme not in ("http", "https"):
        return "esquema nao permitido: %s" % (u.scheme or "?")
    caminho, consulta = unquote(u.path or "").lower(), unquote(u.query or "").lower()
    m = PROIBIDO.search(_dobrado(caminho + "?" + consulta))
    if m:
        return "caminho/consulta de descadastro ou preferencias (%s)" % m.group(0)
    if host in RASTREIO:
        # o upn e cifrado: as palavras so valem no caminho, que tem de ser o clique
        if caminho.rstrip("/") not in CAMINHOS_RASTREIO:
            return "caminho de rastreio fora da lista (%s%s)" % (host, caminho or "/")
        return ""
    if host not in HOSTS_JOTA:
        return "destino fora do jota.info: %s" % (host or "?")
    segs = [x for x in caminho.split("/") if x]
    if len(segs) < 2 or segs[0] not in EDITORIAS:
        return "caminho fora das editorias do jota.info (/%s)" % "/".join(segs[:2])
    conta = next((x for x in segs if _dobrado(x) in SEGMENTOS_CONTA), None)
    if conta:
        return "caminho/consulta de descadastro ou preferencias (/%s)" % conta
    slug = segs[-1]
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+){2,}", slug):
        # materia do JOTA tem slug de >= 3 palavras (176 URLs reais: 4 a 19)
        return "caminho do jota.info que nao e materia (/%s)" % "/".join(segs)
    if segs[0] == "newsletters":
        # so /newsletters/<nome>/<slug de materia>, como as do JOTA Principal no historico
        if len(segs) != 3 or slug.count("-") < 5:
            return "caminho de newsletter que nao e materia (/%s)" % "/".join(segs)
        antes = segs[1]
    else:
        antes = "/".join(segs[:-1])
    util = urlencode([(k, v) for k, v in parse_qsl(u.query, keep_blank_values=True)
                      if not k.lower().startswith(("utm_", "rd_"))]).lower()
    m = PROIBIDO_FORA_DO_SLUG.search(_dobrado(antes + "?" + unquote(util)))
    if m:
        return "caminho/consulta de descadastro ou preferencias (%s)" % m.group(0)
    m = FRASE_DESCADASTRO.search(slug) or re.search(r"manage", slug)
    if not m and slug.count("-") < 5:
        # slug curto (<= 5 palavras: "sair-da-lista", "cancelar-envio") e mais
        # pagina de rodape que manchete: sem isencao nenhuma
        m = PROIBIDO_FORA_DO_SLUG.search(slug)
    if m:
        return "caminho/consulta de descadastro ou preferencias (%s)" % m.group(0).strip("-")
    return ""


def _dobrado(s):
    """Minusculo e sem acento (jota_extrair.dobrar), para as palavras proibidas."""
    return jota_extrair.dobrar(unicodedata.normalize("NFC", s)).lower()


def titulo_de_descadastro(titulo):
    """Trecho de descadastro no titulo da linha ('Caso nao queira mais receber
    estes e-mails', 'cancele sua inscricao', 'Sair da lista', 'Você recebeu este
    e-mail porque...'), com ou sem acento; 'titulo generico: ...' para 'clique
    aqui', 'aqui', 'Sair'; a ultima oracao so de saida ('... no JOTA. Para sair,
    clique aqui'); ou ''."""
    titulo = unicodedata.normalize("NFC", titulo or "")
    achado = jota_extrair.descadastro_no_texto(titulo)    # DESCADASTRO (com a isencao) ou RODAPE
    if achado:
        return achado
    if jota_extrair.generico(titulo) or jota_extrair.so_saida(titulo):
        return "titulo generico: %s" % (" ".join(titulo.split()) or "vazio")
    return jota_extrair.saida(titulo)         # "... no JOTA. Para sair, clique aqui" (v2)


def seguir(url):
    """Resolve salto a salto. ("PAGINA", url_final, html) | ("RECUSADO"|"ERRO", motivo, "")."""
    atual = url.strip()
    for salto in range(MAX_SALTOS + 1):
        motivo = motivo_proibido(atual)
        if motivo:
            return "RECUSADO", motivo, ""
        jota = (urlsplit(atual).hostname or "").lower() in HOSTS_JOTA
        codigo, prox, pagina = curl(atual, corpo=jota)
        if codigo in REDIRECIONA and prox:
            if salto == MAX_SALTOS:
                break
            atual = urljoin(atual, prox)
            continue
        if not jota:
            return "ERRO", "http=%s sem redirecionamento em %s" % (codigo, urlsplit(atual).hostname), ""
        if codigo != 200:
            return "ERRO", "http=%s final=%s" % (codigo, sem_rastreio(atual)), ""
        return "PAGINA", sem_rastreio(atual), pagina
    return "RECUSADO", "mais de %d redirecionamentos" % MAX_SALTOS, ""


def titulo_pagina(corpo):
    m = re.search(r'property="og:title"\s+content="([^"]+)"', corpo) or \
        re.search(r"<title>(.*?)</title>", corpo, re.S)
    return html.unescape(m.group(1)).strip() if m else ""


def _metas(corpo):
    """{property ou name: content} dos <meta> da pagina (a 1a ocorrencia vale; qualquer ordem de atributos)."""
    out = {}
    for tag in re.findall(r"<meta\b[^>]*>", corpo or "", re.I):
        chave = re.search(r'\b(?:property|name)\s*=\s*"([^"]+)"', tag, re.I)
        valor = re.search(r'\bcontent\s*=\s*"([^"]*)"', tag, re.I)
        if chave and valor:
            out.setdefault(chave.group(1).lower(), html.unescape(valor.group(1)).strip())
    return out


def metadados(corpo):
    """(publicada_em: datetime | None, autor, linha_fina) da pagina do jota.info ja baixada (nenhum pedido a mais).
    Linha-fina = og:description (ou description), ate MAX_LINHA_FINA caracteres, cortada em palavra."""
    m = _metas(corpo)
    quando = None
    for k in ("article:published_time", "og:published_time"):
        try:
            quando = datetime.fromisoformat(m[k].replace("Z", "+00:00")).astimezone(TZ)
            break
        except (KeyError, ValueError):
            continue
    autor = m.get("author") or m.get("article:author") or ""
    fina = " ".join((m.get("og:description") or m.get("description") or "").split())
    if len(fina) > MAX_LINHA_FINA:
        fina = fina[:MAX_LINHA_FINA - 1].rsplit(" ", 1)[0] + "…"
    return quando, autor, fina


def limpo(s):
    return re.sub(r"[\t\r\n]+", " ", s or "").strip()


MARCADOR = re.compile(r"^\[?L(\d+)\]?$", re.I)


def ler_linhas(caminho):
    """[(titulo, alvo)] — alvo = url, 'L<n>' ou ''."""
    out = []
    for bruta in open(caminho, encoding="utf-8"):
        linha = bruta.rstrip("\r\n")
        if not linha.strip() or linha.lstrip().startswith("#"):
            continue
        titulo, _, alvo = linha.partition("\t")
        titulo, alvo = titulo.strip(), alvo.strip()
        if not alvo:                          # "titulo [L12]" sem TAB
            m = re.search(r"\s*\[L(\d+)\]\s*$", titulo, re.I)
            if m:
                titulo, alvo = titulo[:m.start()].strip(), "L" + m.group(1)
        if alvo and not MARCADOR.match(alvo) and not re.match(r"https?://", alvo, re.I):
            alvo = ""                         # "sem link", "-" etc.: so a checagem de historico
        out.append((titulo, alvo))
    return out


def ler_indice(caminho):
    """{n: url} do jota_urls.tsv (n<TAB>url[<TAB>...])."""
    idx = {}
    try:
        for linha in open(caminho, encoding="utf-8"):
            p = linha.rstrip("\r\n").split("\t")
            if len(p) >= 2 and p[0].strip().isdigit():
                idx[int(p[0])] = p[1].strip()
    except OSError:
        pass
    return idx


class Contexto:
    def __init__(self, historico=None, urls=None, inicio=None, ja_saiu=None):
        self.idx_hist = historico[0] if historico else None      # repeticao.indice
        self.urls_pub = historico[1] if historico else {}         # {url normalizada: chave}
        self.indice = urls or {}
        self.inicio = inicio                                      # inicio da janela (datetime) ou None
        self.ja_saiu = ja_saiu or []                              # linhas "JA SAIU DD/MM — ..."

    def repetida(self, titulo):
        if self.idx_hist is None:
            return None
        return repeticao.procurar(repeticao.tokens(titulo), self.idx_hist)


def resolve(item, ctx):
    titulo, alvo = item
    t = limpo(titulo)
    desc = titulo_de_descadastro(titulo)
    if desc:                              # rodape copiado com o wrapper: nem o wrapper recebe pedido
        return "RECUSADO\t%s\ttitulo de descadastro ou preferencias (%s)" % (t, limpo(desc))
    ja = ctx.repetida(titulo)
    if ja:
        return "JA_PUBLICADA\t%s\t%s" % (t, ja)
    if not alvo:
        return "SEM_LINK\t%s\tnao publicada antes" % t
    m = MARCADOR.match(alvo)
    if m:
        url = ctx.indice.get(int(m.group(1)))
        if not url:
            return "ERRO\t%s\tindice L%s inexistente no jota_urls.tsv" % (t, m.group(1))
    else:
        url = alvo
    estado, detalhe, corpo = seguir(url)
    if estado != "PAGINA":
        return "%s\t%s\t%s" % (estado, t, limpo(detalhe))
    tit_pag = titulo_pagina(corpo)
    if not bate(titulo, tit_pag):
        return "SEM_MATCH\t%s\t%s" % (t, limpo(tit_pag))
    chave = ctx.urls_pub.get(repeticao.normalizar_url(detalhe))
    if chave:
        return "JA_PUBLICADA\t%s\t%s" % (t, chave)
    quando, autor, fina = metadados(corpo)
    if not (quando or autor or fina):
        return "OK\t%s\t%s" % (t, detalhe)
    data = ""
    if quando:
        data = quando.strftime("%d/%m %H:%M")
        if ctx.inicio and quando < ctx.inicio:
            data += " (antes da janela)"
    return "OK\t%s\t%s\t%s\t%s\t%s" % (t, detalhe, data, limpo(autor), limpo(fina))


def sondar():
    """(host, codigo) do primeiro host bloqueado, ou None."""
    for host in ("https://t.rdsv2.net/", "https://www.jota.info/"):
        codigo = subprocess.run(["curl", "-s", "-o", "/dev/null", "-m", "8", "-w", "%{http_code}", host],
                                capture_output=True, text=True).stdout.strip()
        if codigo in ("000", "403", ""):
            return host, codigo or "000"
    return None


def carregar_contexto(a):
    hist = None
    avisos = []
    janela = {}
    try:
        janela = json.load(open(a.janela, encoding="utf-8"))
    except Exception:
        pass
    inicio = None
    try:
        inicio = datetime.fromisoformat(janela["inicio"])
    except (KeyError, TypeError, ValueError):
        pass
    ja_saiu = []
    if not a.sem_historico:
        ignorar = janela.get("ignorar_execucao") or ""
        execs = repeticao.carregar_historico(a.historico)
        if execs:
            hist = (repeticao.indice(execs, ignorar_exec_id=ignorar or None),
                    repeticao.urls_publicadas(execs, ignorar_exec_id=ignorar or None))
            ja_saiu = repeticao.ja_saiu(execs, ignorar_exec_id=ignorar or None)
        else:
            avisos.append("AVISO\t-\thistorico indisponivel: sem checagem JA_PUBLICADA")
    return Contexto(hist, ler_indice(a.urls), inicio, ja_saiu), avisos


def main(argv=None):
    ap = argparse.ArgumentParser(description="Resolve os links do JOTA com seguranca e marca os ja publicados.")
    ap.add_argument("tsv", nargs="?", default=os.path.join(TMP, "jota_links.tsv"))
    ap.add_argument("--urls", default=os.path.join(TMP, "jota_urls.tsv"),
                    help="indice n<TAB>url do jota_extrair.py (para linhas titulo<TAB>L<n>)")
    ap.add_argument("--janela", default=os.path.join(TMP, "janela.json"))
    ap.add_argument("--historico", default=os.path.join(AQUI, "resumo-legislativo-historico.json"))
    ap.add_argument("--sem-historico", action="store_true", help="nao procura JA_PUBLICADA")
    a = ap.parse_args(argv)
    try:
        itens = ler_linhas(a.tsv)
    except OSError as e:
        print("uso: resolver_jota.py arquivo.tsv (%s)" % e, file=sys.stderr)
        return 2
    ctx, avisos = carregar_contexto(a)
    for av in avisos:
        print(av)
    precisa_rede = [it for it in itens if it[1] and not titulo_de_descadastro(it[0]) and not ctx.repetida(it[0])]
    bloqueio = sondar() if precisa_rede else None
    if bloqueio:
        print("BLOQUEADO\t%s http=%s — usar o fallback por WebSearch" % bloqueio)
        for it in itens:
            if it not in precisa_rede:
                print(resolve(it, ctx))
        for linha in ctx.ja_saiu:
            print(linha)
        return 3
    with ThreadPoolExecutor(max_workers=6) as ex:
        for r in ex.map(lambda it: resolve(it, ctx), itens):
            print(r)
    for linha in ctx.ja_saiu:
        print(linha)
    return 0


if __name__ == "__main__":
    sys.exit(main())
