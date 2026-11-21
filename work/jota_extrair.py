#!/usr/bin/env python3
# =====================================================================
# jota_extrair.py — texto compacto dos boletins do JOTA, sem as URLs de
# rastreio. 76–95% do corpo dos e-mails do JOTA e wrapper t.rdsv2.net
# (~1 KB cada; 16/11: 97 mil dos 103 mil caracteres das "Ultimas noticias"),
# e o coletor pagava por isso em todo turno e ainda copiava wrappers num
# heredoc para o resolver.
#
# O que faz, por mensagem:
#   - cada URL vira um marcador [L<n>] e vai para o indice
#     $ROBOZINHO_TMP/jota_urls.tsv (n<TAB>url); a mesma URL tem sempre o mesmo n;
#   - link de descadastro/preferencias ("parar de receber esta newsletter",
#     "Caso não queira mais receber estes e-mails, cancele sua inscrição",
#     "descadastr", "preferencias"...) e OMITIDO: nao recebe marcador nem entra
#     no indice, de modo que nada o resolve por engano. Com ou sem acento; e
#     link que nao diz nada sozinho ("clique aqui", "aqui", imagem) olha a frase
#     anterior, mesmo depois de quebra de linha (trecho_descadastro); frase de
#     rodape ("Você recebeu este e-mail porque...") e ultima oracao so de saida
#     ("... no JOTA. Para sair, clique aqui") tambem. Na duvida, fora. Mas o
#     trecho que tambem e manchete ("Aposentados podem deixar de receber
#     beneficio em 2027", "Brasil pode sair da lista suja da OIT") so conta com
#     contexto de rodape ou em texto curto — a MESMA regra do resolver
#     (descadastro_no_texto; volta 3: antes essas manchetes perdiam o link);
#   - link sem texto proprio (imagem, logo, rede social), link de propaganda do
#     proprio JOTA e mailto: tambem saem; "| Leia mais [link]" de um bloco que
#     ja tem o link do titulo sai (e o mesmo destino);
#   - espacos de diagramacao viram " | ", um bloco ("EDITORIA | Titulo [L4] |
#     linha-fina | Por Autor") por linha.
# O resolver_jota.py aceita "titulo<TAB>L<n>" e resolve o indice.
# - (21/11) A mesma saida compacta vai tambem para $ROBOZINHO_TMP/jota_extrato.txt (a 2a chamada
#   da mesma execucao acrescenta): e o "funil" do JOTA — manchetes com [L<n>] que o e-mail trouxe —
#   para um script cruzar com o jota_links.tsv (selecao do coletor) e com o que foi publicado, sem
#   token nenhum (antes nao se sabia quem cortou "Fachin suspende prazos apos falha da Microsoft").
#
# ENTRADA: o arquivo em que o harness salvou um get_thread grande (JSON do MCP
#   do Gmail: {"id", "messages": [{"subject", "date", "internalDate",
#   "plaintextBody", ...}]}, inclusive dentro de blocos de conteudo
#   [{"type": "text", "text": "<json>"}], ou com texto antes do JSON), ou um
#   texto puro (e-mail colado). Varios arquivos numa chamada; "-" = stdin.
# USO:   python3 work/jota_extrair.py ARQ [ARQ ...] [--urls $ROBOZINHO_TMP/jota_urls.tsv] [--novo]
#        [--extrato $ROBOZINHO_TMP/jota_extrato.txt]
#        --novo: recomeca a numeracao (padrao: continua o indice gravado ha menos
#        de 12 h, para duas chamadas na mesma execucao nao trocarem os numeros).
# SAIDA: JOTA_EXTRAIR: <m> mensagem(ns) | links L<a>–L<b> em <indice> | omitidos: ...
#        === <assunto> | <DD/MM/AAAA HH:MM> | <remetente> ===
#        <texto compacto>
# =====================================================================

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Sao_Paulo")
TMP = os.environ.get("ROBOZINHO_TMP", "/tmp")
VALIDADE_INDICE = 12 * 3600

CORPOS = ("plaintextBody", "plainTextBody", "textBody", "bodyText", "body")
URL = re.compile(r"\[\s*((?:https?|mailto):[^\s\]]+)\s*\]|(?<![\w/\[])((?:https?)://[^\s<>\[\]\"']+)")
# Descadastro/preferencias no texto do link. Casa sobre o texto DOBRADO (dobrar():
# sem acento, qualquer espaco), entao "nao", "não" e "não" decomposto (NFD), "inscricao"/"inscrição"
# e "preferencias"/"preferências" sao a mesma coisa; os [aã]/[eê] ficam para quem
# usar a regex direto no texto cru. Rodape real do JOTA (16/11): "Caso não queira
# mais receber estes e-mails,  cancele sua inscrição [url]" e "Se quer parar de
# receber esta newsletter, clique aqui [url]". Na duvida, o link fica FORA.
_OBJ = r"(?:inscri|assinatura|envio|recebimento|cadastro|newsletter|e-?mail)"
DESCADASTRO = re.compile(
    r"\b(?:parar|pare|deixar|deixe)\s+de\s+receber|"
    r"\bn[aã]o\s+(?:\w+\s+){0,2}?(?:mais\s+receber|receber\s+mais)|"          # nao queira/quer/deseja mais receber
    r"\bcaso\s+n[aã]o\s+(?:queira|quiser|deseje|desejar)|"
    r"descadastr|desinscrev|unsubscri|opt-?out|"
    r"\bcancel\w*\s+(?:(?:a|o|as|os|sua|seu|suas|seus|minha|meu|da|do|de|desta|deste)\s+){0,2}" + _OBJ + "|"
    r"\bprefer[eê]ncias|\bprefer[eê]ncia\s+(?:de\s+)?(?:e-?mail|envio|comunica|newsletter|contato)|"
    r"\bgerenci\w*\s+(?:(?:as|os|sua|seu|suas|seus|minha|meu|minhas|meus)\s+)?"
    r"(?:e-?mails?|inscri|prefer|assinatura|newsletter|comunica)|"
    r"\bsa(?:ir|ia)\s+d[aeo]s?\s+(?:\w+\s+)?lista|"
    r"\bremov\w*\s+(?:(?:o|meu|seu|sua|minha|este|esse)\s+)?(?:e-?mail|endere[cç]o|cadastro|inscri)", re.I)
URL_DESCADASTRO = re.compile(r"unsub|descadastr|opt-?out|opt_out|preferenc", re.I)
# Trechos do DESCADASTRO que tambem aparecem em manchete ("Aposentados podem
# deixar de receber beneficio em 2027", "Brasil pode sair da lista suja da OIT",
# "TSE manda cancelar inscricao de candidato", "...nao precisa mais receber...",
# "Caso nao queira depor, ..."): so contam com contexto de e-mail (CONTEXTO_EMAIL)
# ou em texto curto (ate MAX_PALAVRAS_CURTO palavras). REGRA UNICA do extrator
# (texto do link) e do resolver_jota.py (titulo da linha): descadastro_no_texto().
# Antes da volta 3 o extrator nao tinha a isencao, e as manchetes acima perdiam o
# link. Sem isencao (qualquer trecho conta): a frase anterior a link generico
# ("... 2027.\n clique aqui") e a zona de rodape (ZONA_RODAPE).
TRECHO_FRACO = re.compile(r"prefer|cancel|sa(?:ir|ia)\s+d|(?:deix|par)\w*\s+de|n[aã]o\s|caso\s|remov", re.I)
# Contexto de rodape (casa sobre o texto DOBRADO): e-mail, newsletter, boletim,
# chamada para clicar ("clique aqui", "basta clicar", "acesse", "link"), "voce",
# primeira pessoa ("meu e-mail", "Nao quero..."), canal ("nossos alertas", "lista
# de distribuicao", "caixa de entrada", "receber o JOTA...") e, no INICIO da
# oracao, o imperativo ou o infinitivo ("Deixe de receber...", "Pare de...", "Sair
# da lista de...") ou a abertura de rodape ("Caso nao queira mais receber", "Se
# quer parar de", "Para deixar de", "Para sair da", "Nao quer/deseja mais...").
# O subjuntivo de manchete ("TCU determina que estado deixe de receber") e "Caso
# nao queira depor, ..." nao casam.
_INICIO = r"(?:^|[|:.!?;])\s*"
CONTEXTO_EMAIL = re.compile(
    r"e-?mails?\b|newsletter|\bboletin|\bboletim\b|\bcli(?:que|ques|quem|ca|car|cando|ck|cks)\b|\btoque\b|\baqui\b|"
    r"\blink\b|\bacesse\b|"
    r"voc[eê]|\b(?:sua|minha)\s+inscri|\b(?:seu|meu)\s+(?:e-?mail|endere[cç]o|cadastro)|"
    r"\b(?:(?:est|ess)[ae]s?|noss[ao]s?)\s+(?:mensage|comunica|e-?mail|alerta|informativ|envio|conte[uú]do)|"
    r"\blista\s+de\s+(?:e-?mails?|envios?|distribui|contatos?|assinantes|leitores|transmiss)|"
    r"\bcaixa\s+de\s+entrada|\breceber\s+(?:\w+\s+){0,3}?jota\b|"
    + _INICIO + r"(?:pare|deixe|saia|cancele|remova|desative|descadastre|parar|deixar|sair|cancelar|remover|desativar)\b|"
    + _INICIO + r"n[aã]o\s+(?:quero|quer|queira|deseja|desejo)\b|"
    + _INICIO + r"(?:caso|se|para)\s+(?:voc[eê]\s+)?(?:(?:n[aã]o|prefira|preferir|quiser|quer|queira|deseja|desejar|"
    r"deseje)\s+){0,3}(?:mais\s+)?(?:receber|deixar|parar|sair|cancelar|remover)\b", re.I)
MAX_PALAVRAS_CURTO = 6
# Frase de rodape que explica o envio ("Você recebeu este e-mail porque se
# cadastrou no JOTA. Para sair, clique aqui [url]"; "Este e-mail foi enviado
# para..."; "Enviamos este e-mail para: ..."): link na mesma linha e rodape, e
# conta como descadastro (v2). A pergunta ("Você recebeu este e-mail? Golpe...")
# e manchete e nao casa. Tambem casa sobre o texto DOBRADO.
_MSG = r"(?:e-?mails?|mensage\w*|newsletters?|boletins?|boletim|comunica\w*|informativos?)"
RODAPE = re.compile(
    r"\bvoc[eê]\s+(?:est[aá]\s+)?receb(?:eu|e|endo)\s+(?:(?:est|ess)[ae]s?|noss[ao]s?)\s+" + _MSG + r"\b(?!\s*\?)|"
    r"\b(?:est|ess)[ae]\s+(?:e-?mail|mensagem|newsletter)\s+foi\s+enviad[ao]\s+(?:a|ao|para)\b|"
    r"\benviamos\s+(?:est|ess)[ae]\s+(?:e-?mail|mensagem|newsletter)\s+(?:a|ao|para)\b", re.I)
# texto de link que nao diz nada sozinho ("clique aqui", "aqui", "Clique neste link",
# imagem): o contexto e a frase ANTERIOR ("Caso nao queira mais receber estes
# e-mails,\n clique aqui"), que pode estar depois de quebra de linha ou de espacos
# de diagramacao
GENERICAS = {"clique", "clica", "clicar", "click", "toque", "tocar", "here", "aqui", "acesse", "acessar", "neste",
             "nesse", "deste", "desse", "este", "esse", "link", "no", "na", "em", "o", "a", "e", "ou", "para", "pelo",
             "pela", "botao", "abaixo", "agora", "ja", "me", "se",
             # volta 3: "basta clicar", "use este link", "clicando aqui"
             "basta", "use", "usar", "utilize", "clicando", "tocando", "acessando", "pressione", "selecione"}
# so verbo de saida, sem materia ("Sair", "Cancelar aqui", "Para sair, clique aqui",
# "Gerencie aqui"); vale para o texto todo ou para a sua ULTIMA oracao (v2)
SAIDA = re.compile(r"sair|cancel\w*|remov\w*|descadastr\w*|desinscrev\w*|unsubscribe|desativ\w*|opt-?out|gerenci\w*",
                   re.I)
# fim de oracao: ". ", "? ", "! ", "… ", "; ", ": " ("15.123" e "e-mail:x" nao cortam; "|" de
# editoria tambem nao)
FIM_ORACAO = re.compile(r"[.?!…;:](?=\s)")
# Zona de rodape: depois da frase de rodape (RODAPE, sobre o texto dobrado) ou de
# "Todos os direitos reservados" / linha "Enviado por ...", nenhum link da mensagem
# tem a isencao de manchete (volta 3; e o fim do e-mail, nao ha materia ali)
ZONA_RODAPE = re.compile(r"\btodos\s+os\s+direitos\s+reservados\b|^[^\S\n]*enviado\s+por\s", re.I | re.M)
PROPAGANDA = re.compile(r"antecipe mudan[çc]as e decida melhor|inscreva-se aqui|entrar no canal|"
                        r"siga o jota|baixe o app", re.I)
LEIA_MAIS = re.compile(r"\|\s*Leia mais\s*$", re.I)
LIMITE = re.compile(r"\n| {3,}|\[L\d+\]")
ESPACOS = re.compile(r"[\t\xa0\u2000-\u200a\u202f\u205f\u3000]")      # diagramacao: \xa0 entre blocos
INVISIVEIS = re.compile(r"[\u00ad\u034f\u200b-\u200d\u2060\ufeff]")      # enchimento do preheader


# ------------------------------------------------------------ descadastro
def dobrar(s):
    """Texto do MESMO comprimento de s (passe s ja em NFC), para casar regex sem
    acento: 'não' -> 'nao', 'inscrição' -> 'inscricao'; espaco de qualquer tipo e
    caractere invisivel viram ' '. As posicoes de um match valem para s."""
    out = []
    for c in s:
        if c.isspace() or INVISIVEIS.match(c):
            out.append(" ")
        elif c < "\x80":
            out.append(c)
        else:
            b = unicodedata.normalize("NFKD", c)[:1]
            out.append(b if b and not unicodedata.combining(b) else c)
    return "".join(out)


def _palavras(dobrado):
    return re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", dobrado.lower())


def generico(texto):
    """Texto de link que nao diz nada sozinho: vazio, 'clique aqui', 'aqui', 'Clique neste link'."""
    return all(p in GENERICAS for p in _palavras(dobrar(unicodedata.normalize("NFC", texto or ""))))


def so_saida(texto):
    """So verbo de saida, sem materia: 'Sair', 'Cancelar aqui', 'Para sair, clique aqui'."""
    resto = [p for p in _palavras(dobrar(unicodedata.normalize("NFC", texto or ""))) if p not in GENERICAS]
    return bool(resto) and all(SAIDA.fullmatch(p) for p in resto)


def ultima_oracao(texto):
    """(previo, ultima): a ultima oracao do texto, depois do ultimo '.', '?', '!',
    '…', ';' ou ':' seguido de espaco, e o que vem antes dela. Pontuacao no
    fim do texto nao conta. Com uma oracao so: ('', texto)."""
    texto = texto or ""
    cortes = [m.end() for m in FIM_ORACAO.finditer(texto.rstrip(" \t\r\n.,;:|!?…"))]
    if not cortes:
        return "", texto
    return texto[:cortes[-1]], texto[cortes[-1]:]


def saida(texto):
    """Trecho so de saida, sem materia, no texto original: o texto todo ('Sair',
    'Cancelar aqui') ou a sua ultima oracao ('... no JOTA. Para sair, clique
    aqui'); ou ''."""
    t = unicodedata.normalize("NFC", texto or "")
    if so_saida(t):
        return t.strip(" .,;:|!?…")
    previo, ultima = ultima_oracao(t)
    if previo and so_saida(ultima):
        return ultima.strip(" .,;:|!?…")
    return ""


def descadastro_no_texto(texto, isencao=True):
    """Trecho (no texto original) de DESCADASTRO ou da frase de rodape (RODAPE), ou ''.
    REGRA UNICA do texto do link (aqui) e do titulo da linha (resolver_jota.py):
    com isencao, os trechos fracos (TRECHO_FRACO: 'deixar de receber', 'sair da
    lista', 'cancelar inscricao', 'nao ... mais receber', 'caso nao queira'...) so
    contam com contexto de e-mail (CONTEXTO_EMAIL) ou em texto de ate
    MAX_PALAVRAS_CURTO palavras: 'Brasil pode sair da lista suja da OIT' e manchete,
    'Sair da lista' e 'Caso nao queira mais receber estes e-mails' nao.
    isencao=False: qualquer trecho conta (frase anterior a 'clique aqui', zona de rodape)."""
    t = unicodedata.normalize("NFC", texto or "")
    d = dobrar(t)
    fraco_conta = (not isencao or len(re.findall(r"\w+", d)) <= MAX_PALAVRAS_CURTO
                   or CONTEXTO_EMAIL.search(d))
    for m in DESCADASTRO.finditer(d):
        if fraco_conta or not TRECHO_FRACO.match(m.group(0)):
            return t[m.start():m.end()]
    m = RODAPE.search(d)                      # frase de rodape: nunca e manchete (v2)
    return t[m.start():m.end()] if m else ""


def trecho_descadastro(texto, antes="", isencao=True):
    """Trecho de descadastro/preferencias do link (no texto original), ou ''.
    texto: o texto do link; antes: a frase que o precede (sem atravessar outro
    link). 'antes' so conta quando o texto do link nao diz nada sozinho ('clique
    aqui', 'aqui', imagem): 'Caso não queira mais receber estes e-mails,\\n clique aqui'.
    Tambem e descadastro (v2): frase de rodape (RODAPE: 'Você recebeu este e-mail
    porque...') e ultima oracao so de saida ('... no JOTA. Para sair, clique aqui').
    O texto do link tem a isencao de manchete do resolver (descadastro_no_texto,
    volta 3); a frase anterior a link generico nunca tem; isencao=False (zona de
    rodape) tira a isencao tambem do texto do link."""
    t = unicodedata.normalize("NFC", texto or "")
    achado = descadastro_no_texto(t, isencao) or saida(t)
    if achado:
        return achado
    if antes and generico(t):
        a = unicodedata.normalize("NFC", antes)
        return descadastro_no_texto(a, isencao=False) or saida(a)
    return ""


# ------------------------------------------------------------ leitura
def _nome(m):
    for d in m.get("addressDisplayNames") or []:
        if isinstance(d, dict) and d.get("displayName"):
            return d["displayName"]
    return m.get("sender") or m.get("from") or ""


def _quando(m):
    try:
        return datetime.fromtimestamp(int(m["internalDate"]) / 1000, TZ).strftime("%d/%m/%Y %H:%M")
    except (KeyError, TypeError, ValueError, OSError):
        pass
    try:
        return datetime.fromisoformat(str(m.get("date")).replace("Z", "+00:00")).astimezone(TZ) \
            .strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return str(m.get("date") or "")


def html_para_texto(h):
    """FULL_CONTENT sem plaintextBody: <a href=U>t</a> -> 't [ U ]'; tags fora."""
    import html as _html
    h = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", h)
    h = re.sub(r'(?is)<a\s[^>]*href="([^"]+)"[^>]*>(.*?)</a>', r"\2 [ \1 ]", h)
    h = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</h\d>", "\n", h)
    return _html.unescape(re.sub(r"<[^>]+>", " ", h))


def achar_mensagens(obj, out):
    """Percorre o JSON (inclusive strings que sao JSON) atras de mensagens com corpo."""
    if isinstance(obj, dict):
        corpo = next((obj[k] for k in CORPOS if isinstance(obj.get(k), str) and obj[k].strip()), None)
        if corpo is None and isinstance(obj.get("htmlBody"), str) and obj["htmlBody"].strip():
            corpo = html_para_texto(obj["htmlBody"])
        if corpo is not None:
            out.append({"id": obj.get("id") or "", "assunto": obj.get("subject") or "",
                        "quando": _quando(obj), "remetente": _nome(obj), "corpo": corpo})
            return
        for v in obj.values():
            achar_mensagens(v, out)
    elif isinstance(obj, list):
        for v in obj:
            achar_mensagens(v, out)
    elif isinstance(obj, str):
        s = obj.strip()
        if len(s) > 20 and s[:1] in "{[":
            try:
                achar_mensagens(json.loads(s), out)
            except ValueError:
                pass


def textos_soltos(obj, out):
    """Sem mensagem reconhecida: os campos "text" longos viram mensagens sem cabecalho."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "text" and isinstance(v, str) and len(v) > 200:
                out.append({"id": "", "assunto": "", "quando": "", "remetente": "", "corpo": v})
            else:
                textos_soltos(v, out)
    elif isinstance(obj, list):
        for v in obj:
            textos_soltos(v, out)


def mensagens(conteudo):
    """[{id, assunto, quando, remetente, corpo}] de um arquivo salvo (JSON ou texto)."""
    obj = None
    try:
        obj = json.loads(conteudo)
    except ValueError:
        dec = json.JSONDecoder()
        for m in re.finditer(r"[\[{]", conteudo[:5000]):    # texto antes do JSON
            try:
                obj = dec.raw_decode(conteudo[m.start():])[0]
                break
            except ValueError:
                continue
    out = []
    if obj is not None:
        achar_mensagens(obj, out)
        if not out:
            textos_soltos(obj, out)
    if not out:
        out.append({"id": "", "assunto": "", "quando": "", "remetente": "", "corpo": conteudo})
    return out


# ------------------------------------------------------------ indice
class Indice:
    def __init__(self, caminho, novo=False):
        self.caminho, self.por_url, self.urls = caminho, {}, {}
        try:
            recente = time.time() - os.path.getmtime(caminho) < VALIDADE_INDICE
        except OSError:
            recente = False
        if recente and not novo:
            for linha in open(caminho, encoding="utf-8"):
                p = linha.rstrip("\r\n").split("\t")
                if len(p) >= 2 and p[0].isdigit():
                    self.urls[int(p[0])] = p[1]
                    self.por_url.setdefault(p[1], int(p[0]))
        self.inicio = max(self.urls, default=0) + 1

    def numero(self, url):
        if url not in self.por_url:
            n = max(self.urls, default=0) + 1
            self.urls[n], self.por_url[url] = url, n
        return self.por_url[url]

    def gravar(self):
        tmp = self.caminho + ".%d.tmp" % os.getpid()
        with open(tmp, "w", encoding="utf-8") as f:
            for n in sorted(self.urls):
                f.write("%d\t%s\n" % (n, self.urls[n]))
        os.replace(tmp, self.caminho)


# ------------------------------------------------------------ compactacao
def compactar(corpo, indice, conta):
    """Texto com [L<n>] no lugar das URLs (e sem os links omitidos)."""
    corpo = INVISIVEIS.sub("", ESPACOS.sub(" ", corpo.replace("\r", "")))
    partes, pos, bloco_com_link, zona_rodape = [], 0, False, False
    for m in URL.finditer(corpo):
        antes = corpo[pos:m.start()]
        pos = m.end()
        if "\n" in antes:
            bloco_com_link = False
        # fim do e-mail (frase de rodape, "Todos os direitos reservados"): dali em
        # diante, nenhum link tem a isencao de manchete
        zona_rodape = zona_rodape or bool(ZONA_RODAPE.search(antes) or
                                           RODAPE.search(dobrar(unicodedata.normalize("NFC", antes))))
        partes.append(antes)
        url = m.group(1) or m.group(2).rstrip(".,;:)")
        trecho = LIMITE.split("".join(partes[-3:]))[-1]      # texto do link: desde o ultimo limite
        # frase anterior (ate 2 blocos, sem atravessar link mantido): contexto de
        # "clique aqui" depois de quebra de linha ou de espacos de diagramacao
        anterior = LIMITE.split(re.split(r"\[L\d+\]", "".join(partes[-8:]))[-1])[-3:-1]
        if url.lower().startswith("mailto:"):
            conta["mailto"] += 1
            continue
        if trecho_descadastro(trecho, " ".join(anterior)[-300:], isencao=not zona_rodape) \
                or URL_DESCADASTRO.search(url):
            conta["descadastro"] += 1
            continue
        if not re.search(r"\w", trecho):
            conta["sem_texto"] += 1
            continue
        if PROPAGANDA.search(trecho):
            conta["propaganda"] += 1
            continue
        leia_mais = LEIA_MAIS.search(trecho)
        if leia_mais and bloco_com_link:          # o titulo do bloco ja tem o link
            partes[-1] = LEIA_MAIS.sub("", partes[-1]).rstrip() + "\n"
            conta["leia_mais"] += 1
            bloco_com_link = False
            continue
        partes.append("[L%d]" % indice.numero(url))
        if leia_mais:                             # fim de bloco sem link no titulo
            partes.append("\n")
        bloco_com_link = not leia_mais
    partes.append(corpo[pos:])
    linhas, vazia = [], False
    for linha in "".join(partes).split("\n"):
        linha = re.sub(r" {3,}", " | ", linha)
        linha = re.sub(r"\s+", " ", linha)
        linha = re.sub(r"(?:\s*\|\s*){2,}", " | ", linha).strip(" |")
        if not linha:
            if linhas and not vazia:
                linhas.append("")
            vazia = True
            continue
        linhas.append(linha)
        vazia = False
    return "\n".join(linhas).strip()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Texto compacto dos e-mails do JOTA, sem URLs de rastreio.")
    ap.add_argument("arquivos", nargs="+")
    ap.add_argument("--urls", default=os.path.join(TMP, "jota_urls.tsv"))
    ap.add_argument("--novo", action="store_true", help="recomeca a numeracao do indice")
    ap.add_argument("--extrato", default=os.path.join(TMP, "jota_extrato.txt"),
                    help="copia da saida compacta (funil do JOTA); a 2a chamada da execucao acrescenta")
    a = ap.parse_args(argv)
    indice = Indice(a.urls, a.novo)
    continua = indice.inicio > 1          # indice recente: mesma execucao
    conta = {"descadastro": 0, "sem_texto": 0, "propaganda": 0, "leia_mais": 0, "mailto": 0}
    blocos, vistos, erros = [], set(), []
    for arq in a.arquivos:
        try:
            conteudo = sys.stdin.read() if arq == "-" else open(arq, encoding="utf-8", errors="replace").read()
        except OSError as e:
            erros.append("ERRO: %s nao abriu (%s)" % (arq, e))
            continue
        for msg in mensagens(conteudo):
            if msg["id"] and msg["id"] in vistos:
                continue
            vistos.add(msg["id"])
            cab = " | ".join(x for x in (msg["assunto"], msg["quando"], msg["remetente"]) if x)
            blocos.append("=== %s ===\n%s" % (cab or os.path.basename(arq), compactar(msg["corpo"], indice, conta)))
    indice.gravar()
    fim = max(indice.urls, default=0)
    faixa = "L%d–L%d" % (indice.inicio, fim) if fim >= indice.inicio else "nenhum link novo"
    print("JOTA_EXTRAIR: %d mensagem(ns) | %s em %s | omitidos: %d descadastro/preferencias, "
          "%d sem texto (imagem/rede social), %d propaganda, %d 'Leia mais' repetido, %d mailto"
          % (len(blocos), faixa, a.urls, conta["descadastro"], conta["sem_texto"], conta["propaganda"],
             conta["leia_mais"], conta["mailto"]))
    for e in erros:
        print(e)
    for b in blocos:
        print(b)
    print("(links: grave titulo<TAB>L<n> em %s e rode python3 work/resolver_jota.py)"
          % os.path.join(TMP, "jota_links.tsv"))
    if blocos and a.extrato:
        try:
            with open(a.extrato, "a" if continua else "w", encoding="utf-8") as f:
                f.write("\n".join(blocos) + "\n")
        except OSError:
            pass                          # acessorio: a saida impressa e o que o coletor usa
    return 1 if erros and not blocos else 0


if __name__ == "__main__":
    sys.exit(main())
