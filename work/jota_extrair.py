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
#     "descadastr", "preferencias"...) e OMITIDO: nao recebe marcador nem entra
#     no indice, de modo que nada o resolve por engano;
#   - link sem texto proprio (imagem, logo, rede social), link de propaganda do
#     proprio JOTA e mailto: tambem saem; "| Leia mais [link]" de um bloco que
#     ja tem o link do titulo sai (e o mesmo destino);
#   - espacos de diagramacao viram " | ", um bloco ("EDITORIA | Titulo [L4] |
#     linha-fina | Por Autor") por linha.
# O resolver_jota.py aceita "titulo<TAB>L<n>" e resolve o indice.
#
# ENTRADA: o arquivo em que o harness salvou um get_thread grande (JSON do MCP
#   do Gmail: {"id", "messages": [{"subject", "date", "internalDate",
#   "plaintextBody", ...}]}, inclusive dentro de blocos de conteudo
#   [{"type": "text", "text": "<json>"}], ou com texto antes do JSON), ou um
#   texto puro (e-mail colado). Varios arquivos numa chamada; "-" = stdin.
# USO:   python3 work/jota_extrair.py ARQ [ARQ ...] [--urls $ROBOZINHO_TMP/jota_urls.tsv] [--novo]
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
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Sao_Paulo")
TMP = os.environ.get("ROBOZINHO_TMP", "/tmp")
VALIDADE_INDICE = 12 * 3600

CORPOS = ("plaintextBody", "plainTextBody", "textBody", "bodyText", "body")
URL = re.compile(r"\[\s*((?:https?|mailto):[^\s\]]+)\s*\]|(?<![\w/\[])((?:https?)://[^\s<>\[\]\"']+)")
DESCADASTRO = re.compile(
    r"parar de receber|deixar de receber|n[aã]o (?:qu[ei]\w*|desej\w*) mais receber|descadastr|"
    r"cancel(?:ar|e) (?:a |sua |o )?(?:inscri|assinatura|envio)|unsubscri|prefer[eê]ncias|"
    r"gerenci(?:ar|e) (?:seus |os |suas )?(?:e-?mails|inscri|prefer|assinatura)|sair da lista|"
    r"remover (?:meu|seu|o) e-?mail|opt-?out", re.I)
URL_DESCADASTRO = re.compile(r"unsub|descadastr|opt-?out|opt_out|preferenc", re.I)
PROPAGANDA = re.compile(r"antecipe mudan[çc]as e decida melhor|inscreva-se aqui|entrar no canal|"
                        r"siga o jota|baixe o app", re.I)
LEIA_MAIS = re.compile(r"\|\s*Leia mais\s*$", re.I)
LIMITE = re.compile(r"\n| {3,}|\[L\d+\]")
ESPACOS = re.compile(r"[\t\xa0\u2000-\u200a\u202f\u205f\u3000]")      # diagramacao: \xa0 entre blocos
INVISIVEIS = re.compile(r"[\u00ad\u034f\u200b-\u200d\u2060\ufeff]")      # enchimento do preheader


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
    partes, pos, bloco_com_link = [], 0, False
    for m in URL.finditer(corpo):
        antes = corpo[pos:m.start()]
        pos = m.end()
        if "\n" in antes:
            bloco_com_link = False
        partes.append(antes)
        url = m.group(1) or m.group(2).rstrip(".,;:)")
        trecho = LIMITE.split("".join(partes[-3:]))[-1]      # texto do link: desde o ultimo limite
        if url.lower().startswith("mailto:"):
            conta["mailto"] += 1
            continue
        if DESCADASTRO.search(trecho) or URL_DESCADASTRO.search(url):
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
    a = ap.parse_args(argv)
    indice = Indice(a.urls, a.novo)
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
    return 1 if erros and not blocos else 0


if __name__ == "__main__":
    sys.exit(main())
