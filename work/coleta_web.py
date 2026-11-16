#!/usr/bin/env python3
# =====================================================================
# coleta_web.py — coleta deterministica das fontes web liberadas no
# allowlist: Congresso (leis e MPVs), ConJur e Migalhas. Substitui o
# curl+regex que o coletor Web improvisava a cada dia (e errava).
#
# - Data/hora exata por item: ConJur e Migalhas expoem
#   article:published_time na pagina da materia (confirmado em 24/09/2026);
#   so as materias cuja data de listagem nao decide sozinha sao abertas.
# - MPV: data oficial "Publicada no DOU de ..." da pagina de detalhe
#   (resolve a armadilha congresso_mpv sem WebSearch).
# - Dedupe: numero da lei/MPV contra as chaves do historico; URL das
#   materias contra as URLs ja publicadas; e, por semelhanca de titulo
#   (work/repeticao.py), materia que ja saiu por OUTRA fonte ganha a marca
#   [REPETIDA?~chave] — o orquestrador nao precisa ler as chaves publicadas.
# - Sorteios e eventos promocionais do Migalhas/ConJur viram PROMO (so contados).
#
# - Cada item publicavel ganha um id curto (lei15527, mpv1400, c7, m3): o
#   orquestrador cita o id em $ROBOZINHO_TMP/execucao.json ({"ref": "c7", ...}) e o
#   work/montar_email.py copia titulo, linha-fina, hora, URL e chave daqui —
#   nada disso e redigitado (menos saida e nenhum erro de copia).
#
# - Rede: 1 nova tentativa apos ~3 s em http 0/429/5xx (16/11: um http 0
#   transitorio nas MPVs custou ToolSearch + WebSearch inuteis). Em tempo
#   esgotado (curl -m 20) so a listagem tenta de novo; as paginas de materia nao.
# - Linha-fina (ConJur: og:description da materia; Migalhas: listagem) sem
#   propaganda ("(clique aqui para garantir o seu exemplar)", Anuario) e sem o
#   "[…]" do WordPress; frase cortada e completada pela propria pagina (ja
#   baixada) ou o item ganha "resumo_truncado": true (17/11: "... invasao de
#   domic." no e-mail). Nenhum pedido a mais.
# - Saida compacta: noticias com linha-fina; artigos/colunas do ConJur so o
#   titulo (ate ~90 caracteres) e no maximo 10 no indice — escolhidos pelos
#   termos de prova no titulo, nao pela recencia; o resto so contado (id no JSON).
# - Status das fontes: grava $ROBOZINHO_TMP/fontes_status.json (merge, com trava)
#   e imprime no fim "SOURCE_STATUS {json}" pronto para o source_status.
#
# USO:   python3 work/coleta_web.py [--janela $ROBOZINHO_TMP/janela.json]
#        [--saida $ROBOZINHO_TMP/coleta_web.json] [--historico work/resumo-...json]
#        (sem janela.json: inicio = window_end do estado, fim = agora)
#        ROBOZINHO_TMP (padrao /tmp) e a pasta de todos os arquivos temporarios.
# SAIDA: indice compacto em stdout (sem URL); JSON completo em $ROBOZINHO_TMP/coleta_web.json.
#        Fonte com erro aparece como "ERRO ... usar WebSearch" (MPV: conferir antes
#        as PLANALTO_ATO do coletor Gmail). Ultima linha: SOURCE_STATUS {...}.
# =====================================================================

import argparse
import html
import json
import os
import re
import subprocess
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Sao_Paulo")
UA = "Mozilla/5.0 (X11; Linux x86_64) Robozinho/1.0"
AQUI = os.path.dirname(os.path.abspath(__file__))
TMP = os.environ.get("ROBOZINHO_TMP", "/tmp")
HISTORICO = os.path.join(AQUI, "resumo-legislativo-historico.json")
PAUSA_REPETICAO = 3      # segundos antes da nova tentativa (http 0/429/5xx)
MESES = {m: i + 1 for i, m in enumerate(
    "jan fev mar abr mai jun jul ago set out nov dez".split())}

URL_LEIS = "https://www.congressonacional.leg.br/materias/ultimas-leis-publicadas"
URL_MPV = "https://www.congressonacional.leg.br/materias/medidas-provisorias"
URLS_CONJUR = {"noticia": "https://conjur.com.br/noticias/",
               "artigo": "https://conjur.com.br/artigos/",
               "coluna": "https://conjur.com.br/colunas/"}
URL_MIGALHAS = "https://www.migalhas.com.br/quentes"
IGNORAR_EXEC = ""   # re-execucao (inicio.py --refazer): a edicao de hoje nao conta como publicada
PROMO = re.compile(r"^\s*sorteio\b|\bsorteio d[aoe]\b|\bpromove (congresso|semin[aá]rio|evento|"
                   r"webin[aá]rio|curso|encontro|jornada)\b|\blan[cç]amento d[eo] livro\b", re.I)


def _fetch1(url, timeout):
    """Um GET (curl -L). Devolve (codigo, corpo, tempo_esgotado)."""
    try:
        r = subprocess.run(["curl", "-s", "-L", "-m", str(timeout), "-A", UA,
                            "-w", "\n%{http_code}", url],
                           capture_output=True, timeout=timeout + 5)
        out = r.stdout.decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        return 0, "", True
    except Exception:
        return 0, "", False
    corpo, _, codigo = out.rpartition("\n")
    try:
        return int(codigo), corpo, r.returncode == 28
    except ValueError:
        return 0, out, r.returncode == 28


def repetir(codigo):
    return codigo == 0 or codigo == 429 or codigo >= 500


def fetch_n(url, timeout=20, repetir_timeout=True):
    """(codigo, corpo, tentativas): GET com 1 nova tentativa apos ~3 s em http
    0/429/5xx. Tempo esgotado so tenta de novo se repetir_timeout (senao uma
    fonte lenta soma 20 s por pagina). 403/404 = 1 tentativa so."""
    codigo, corpo, esgotado = _fetch1(url, timeout)
    if repetir(codigo) and (repetir_timeout or not esgotado):
        time.sleep(PAUSA_REPETICAO)
        codigo, corpo, _ = _fetch1(url, timeout)
        return codigo, corpo, 2
    return codigo, corpo, 1


def fetch(url, timeout=20, repetir_timeout=True):
    """(codigo, corpo) do fetch_n."""
    return fetch_n(url, timeout, repetir_timeout)[:2]


def tentativas_txt(r):
    """'1 tentativa' / '2 tentativas' da listagem (campo "tentativas"); '' se faltar."""
    n = r.get("tentativas")
    return "%d tentativa%s" % (n, "s" if n != 1 else "") if isinstance(n, int) and n > 0 else ""


def fetch_many(urls):
    with ThreadPoolExecutor(max_workers=8) as ex:
        return dict(zip(urls, ex.map(lambda u: fetch(u, repetir_timeout=False), urls)))


def limpa(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def publicado_em(pagina):
    m = re.search(r'property="article:published_time"\s+content="([^"]+)"', pagina)
    if not m:
        return None
    try:
        return datetime.fromisoformat(m.group(1).replace("Z", "+00:00")).astimezone(TZ)
    except ValueError:
        return None


def dmy(s):
    return datetime.strptime(s, "%d/%m/%Y").date()


def carregar_janela(caminho):
    global IGNORAR_EXEC
    if caminho and os.path.exists(caminho):
        j = json.load(open(caminho, encoding="utf-8"))
        IGNORAR_EXEC = j.get("ignorar_execucao") or ""
        return datetime.fromisoformat(j["inicio"]), datetime.fromisoformat(j["fim"])
    est = json.load(open(os.path.join(AQUI, "robozinho-estado.json"), encoding="utf-8"))
    return (datetime.fromisoformat(est["ultima_execucao"]["window_end"]),
            datetime.now(TZ).replace(microsecond=0))


def chave_url(url):
    m = re.search(r"migalhas\.com\.br/\w+/(\d+)", url or "")
    return "migalhas:" + m.group(1) if m else (url or "").rstrip("/")


def carregar_historico():
    try:
        return json.load(open(HISTORICO, encoding="utf-8"))["executions"]
    except Exception:
        return []


def carregar_publicados(h=None):
    h = carregar_historico() if h is None else h
    chaves, urls = set(), set()
    for e in h:
        if e.get("execution_id") == IGNORAR_EXEC:
            continue
        for it in e.get("items") or []:
            chaves.add((it.get("chave") or "").lower())
            if it.get("url"):
                urls.add(chave_url(it["url"]))
    import repeticao
    atos = set()          # (tipo canonico, numero): "planalto|lc|239" = Lei Complementar 239
    for k in chaves:
        p = k.split("|")
        if len(p) >= 4 and p[0] == "planalto" and p[2].isdigit():
            atos.add((repeticao.tipo_canonico(p[1]), p[2].lstrip("0") or p[2]))
    return atos, urls


def classifica(quando, inicio, fim, recorte):
    """NOVA (na janela, ultimas 24h), HERDADA (na janela, antes de 24h),
    FORA (antes do inicio), DEPOIS (apos o fim: entra na proxima edicao)."""
    if quando is None:
        return "SEM_DATA"
    if isinstance(quando, datetime):
        if quando < inicio:
            return "FORA"
        if quando > fim:
            return "DEPOIS"
        return "NOVA" if quando >= recorte else "HERDADA"
    if quando < inicio.date():
        return "FORA"
    return "NOVA" if quando >= recorte.date() else "HERDADA"


# ------------------------------------------------------------ Congresso
def leis(inicio, fim, recorte, atos_pub):
    import repeticao
    cod, t, n_tent = fetch_n(URL_LEIS)
    # listadas/mais_recente: pagina lida sem norma na janela (ex.: periodo
    # eleitoral, out/2026) nao e erro da fonte; em 16/10 isso virou "ERRO",
    # WebSearch inutil e status "falha".
    out = {"fonte": "congresso_leis", "http": cod, "tentativas": n_tent, "itens": [], "listadas": 0,
           "mais_recente": ""}
    for bloco in t.split('<div class="sf-lista-resumos__resumo">')[1:]:
        m = re.search(r'<dt>Norma:</dt>\s*<dd>\s*<a href="([^"]+)">([^<]+)</a>\s*'
                      r'\(<a[^>]*>DOU de (\d\d/\d\d/\d{4})</a>\)', bloco)
        if not m:
            continue
        url, norma, dou = m.group(1), limpa(m.group(2)), dmy(m.group(3))
        n = re.match(r"(.+?) n[ºo°.]*\s*([\d.]+)\s+de\s+(\d\d/\d\d/\d{4})", norma)
        if not n:
            continue
        out["listadas"] += 1
        if not out["mais_recente"]:       # a pagina vem da mais nova para a mais antiga
            out["mais_recente"] = "%s, DOU %s" % (norma, dou.strftime("%d/%m/%Y"))
        tipo, numero, data_ato = n.group(1).strip(), n.group(2).replace(".", ""), n.group(3)
        slug = re.sub(r"\s+", "-", tipo.lower())
        ementa = re.search(r"<dt>Ementa:</dt>\s*<dd>(.*?)</dd>", bloco, re.S)
        materia = re.search(r"<dt>Mat[ée]ria:</dt>\s*<dd>\s*<a[^>]*>([^<]+)</a>", bloco)
        veto = re.search(r"<dt>Veto aposto:</dt>\s*<dd>\s*<a[^>]*>([^<]+)</a>", bloco)
        if (repeticao.tipo_canonico(slug), numero.lstrip("0") or numero) in atos_pub:
            sit = "JA_PUBLICADA"
        elif dou < inicio.date() - timedelta(days=7):
            continue
        else:
            # DOU de D sai de madrugada: ato com DOU no dia do inicio da
            # janela so nao foi publicado ontem se a pagina atrasou.
            sit = "NOVA" if dou >= inicio.date() else "HERDADA"
        out["itens"].append({
            "situacao": sit, "tipo": tipo, "numero": numero, "data_ato": data_ato,
            "dou": dou.strftime("%d/%m/%Y"), "ementa": limpa(ementa.group(1)) if ementa else "",
            "materia": limpa(materia.group(1)) if materia else "",
            "veto": limpa(veto.group(1)) if veto else "", "url": url,
            "chave": "planalto|%s|%s|%s|%s" % (slug, numero, data_ato[-4:],
                                               dmy(data_ato).isoformat())})
    return out


def mpvs(inicio, fim, recorte, atos_pub):
    cod, t, n_tent = fetch_n(URL_MPV)
    out = {"fonte": "congresso_mpv", "http": cod, "tentativas": n_tent, "itens": [], "listadas": 0}
    candidatos = []
    for bloco in t.split('<div class="sf-lista-resumos__resumo">')[1:]:
        m = re.search(r'href="(https://www\.congressonacional\.leg\.br/materias/medidas-provisorias/-/mpv/\d+)"'
                      r'.*?MPV (\d+)/(\d{4})', bloco, re.S)
        if m:
            out["listadas"] += 1
        dia = re.search(r"Dia de tramita[çc][ãa]o</dt>\s*<dd><span>(\d+)</span>", bloco)
        if not m or not dia or int(dia.group(1)) > 10:
            continue
        ementa = re.search(r"<dt>Ementa</dt>\s*<dd>(.*?)</dd>", bloco, re.S)
        candidatos.append((m.group(1), m.group(2), m.group(3),
                           limpa(ementa.group(1)) if ementa else ""))
    paginas = fetch_many([c[0] for c in candidatos])
    for url, numero, ano, ementa in candidatos:
        c2, p = paginas[url]
        d = re.search(r"Publicada no DOU de (\d\d/\d\d/\d{4})", p)
        dou = dmy(d.group(1)) if d else None
        if ("mpv", numero.lstrip("0") or numero) in atos_pub:
            sit = "JA_PUBLICADA"
        else:
            sit = classifica(dou, inicio, fim, recorte) if dou else "SEM_DATA_OFICIAL"
        out["itens"].append({
            "situacao": sit, "numero": numero, "ano": ano, "ementa": ementa,
            "dou": dou.strftime("%d/%m/%Y") if dou else "", "http_detalhe": c2, "url": url,
            "chave": "planalto|mpv|%s|%s|%s" % (numero, ano, dou.isoformat() if dou else "")})
    return out


# ------------------------------------------------------------ Midia
def descricao(pagina):
    """Linha-fina da materia (og:description / description), copiada da propria pagina."""
    m = (re.search(r'<meta\s+property="og:description"\s+content="([^"]*)"', pagina or "") or
         re.search(r'<meta\s+name="description"\s+content="([^"]*)"', pagina or ""))
    return limpa(m.group(1)) if m else ""


# Linha-fina cortada ou com propaganda (volta 3). Em 17/11 a og:description do
# ConJur veio cortada no meio da palavra ("... fazem a invasao de domic"; o e-mail
# saiu com "domic.") e outra era o resumo automatico do WordPress, com a
# propaganda do Anuario e o "[…]" no fim ("... Livraria ConJur (clique aqui para
# garantir o seu exemplar). Capa da edicao ... criou 13 varas regionais das […]").
# resumo_da_pagina() tira a propaganda, completa a frase cortada pela propria
# pagina (ja baixada: nenhum pedido a mais) e, sem como completar, devolve o
# texto sem o pedaco de palavra e truncado=True ("resumo_truncado" no JSON; o
# montador termina o resumo em "…", nunca em ".").
MARCADOR_CORTE = re.compile(r"\s*(?:\[\s*(?:…|\.\.\.|&hellip;)\s*\]|…|\.\.\.)\s*$")
CTA_RESUMO = re.compile(r"\s*\(\s*clique aqui para [^)]*\)", re.I)       # "(clique aqui para garantir o seu exemplar)"
PROPAGANDA_RESUMO = re.compile(r"clique aqui para (?:garantir|comprar|adquirir|reservar|assinar)|livraria conjur|"
                               r"reportagem publicada no anu[aá]rio", re.I)          # frase de propaganda: sai
LEGENDA_RESUMO = re.compile(r"^\s*capa d[ao] (?:edi[cç][aã]o|anu[aá]rio)", re.I)  # paragrafo-legenda do comeco: sai
FIM_FRASE = re.compile(r"[.!?…][\"”’»)]*(?=\s+[\"“«(]?[A-ZÀ-Ý0-9]|\s*$)")
MAX_COMPLEMENTO = 300     # no maximo isto de texto vem da pagina para fechar a frase


def _sem_acento(s):
    s = unicodedata.normalize("NFKD", (s or "").lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def _chave(s):
    """So letras e digitos, minusculos e sem acento (compara texto com espacamento diferente)."""
    return re.sub(r"[\W_]+", "", _sem_acento(s))


def _depois_de(texto, chave):
    """Posicao em texto logo depois de consumir os caracteres de chave (_chave), ou -1."""
    j = 0
    for i, c in enumerate(texto):
        if j == len(chave):
            return i
        k = _chave(c)
        if not k:
            continue
        if not chave.startswith(k, j):
            return -1
        j += len(k)
    return len(texto) if j == len(chave) else -1


def paragrafos(pagina):
    """Textos dos <p> da pagina, sem tags, na ordem."""
    out = []
    for m in re.finditer(r"<p\b[^>]*>(.*?)</p>", pagina or "", re.S | re.I):
        t = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", m.group(1)))).strip()
        if t:
            out.append(t)
    return out


def palavra_cortada(texto, referencia):
    """Pedaco de palavra no fim do texto ('... invasao de domic'), ou ''. So
    conta sem pontuacao final e quando o pedaco NAO e palavra na referencia
    (titulo, slug, paragrafos), mas comeca uma palavra mais longa dela
    ('domicilio'); plural e flexao curta (s/es/as/os) nao valem."""
    if re.search(r"[.!?…:;)\]\"”’»]\s*$", texto or ""):
        return ""
    m = re.search(r"([^\W\d_]{2,})$", texto or "")
    if not m:
        return ""
    w = _sem_acento(m.group(1))
    ref = set(re.findall(r"[^\W\d_]+", _sem_acento(referencia)))
    if w in ref:
        return ""
    return m.group(1) if any(p.startswith(w) and len(p) - len(w) >= 2 and p[len(w):] not in ("es", "as", "os")
                             for p in ref) else ""


def resumo_da_pagina(pagina, titulo="", url="", texto=None):
    """(resumo, truncado) da linha-fina: texto (padrao: og:description/description
    da pagina) sem propaganda e sem o '[…]' do fim; frase cortada completada pelo
    paragrafo da pagina que comeca com ela (no maximo MAX_COMPLEMENTO caracteres);
    sem paragrafo que complete, truncado=True e o pedaco de palavra do fim sai."""
    d = descricao(pagina) if texto is None else limpa(texto)
    if not d:
        return "", False
    m = MARCADOR_CORTE.search(d)
    marcado = bool(m)
    if m:
        d = d[:m.start()].rstrip()
    pars = paragrafos(pagina)
    # resumo automatico (paragrafos do comeco da materia): os paragrafos de
    # propaganda/legenda do comeco saem; o que sobra e o paragrafo cortado
    for p in pars:
        if not _chave(d).startswith(_chave(p)) or not (PROPAGANDA_RESUMO.search(p) or LEGENDA_RESUMO.search(p)):
            break
        fim = _depois_de(d, _chave(p))
        if fim < 0:
            break
        d = d[fim:].lstrip(" .,;:)-")
    d = CTA_RESUMO.sub("", d)
    d = " ".join(f for f in re.split(r"(?<=[.!?])\s+", d) if not PROPAGANDA_RESUMO.search(f)).strip()
    if not d:                 # so propaganda/marcador: sem linha-fina
        return "", False
    cortada = palavra_cortada(d, " ".join([titulo or "", (url or "").rstrip("/").rsplit("/", 1)[-1].replace("-", " ")]
                                          + pars))
    if not (marcado or cortada):
        return d, False
    # completar pela propria pagina: paragrafo que comeca com a frase cortada
    frases = re.split(r"(?<=[.!?])\s+", d)
    ultima = frases[-1]
    for p in pars:
        if _chave(p).startswith(_chave(ultima)) and len(_chave(p)) > len(_chave(ultima)):
            i = _depois_de(p, _chave(ultima))
            f = FIM_FRASE.search(p, i) if i >= 0 else None
            if f and f.end() - i <= MAX_COMPLEMENTO:
                return " ".join(frases[:-1] + [p[:f.end()]]).strip(), False
    if cortada:
        d = d[:len(d) - len(cortada)].rstrip(" ,;:-–—(")
    return d.rstrip(" ,;:-–—("), True


def conjur(inicio, fim, recorte, urls_pub):
    pags = fetch_many(list(URLS_CONJUR.values()))
    out = {"fonte": "conjur", "http": {k: pags[u][0] for k, u in URLS_CONJUR.items()},
           "itens": []}
    vistos, abrir = {}, []
    padrao = re.compile(r'<h2 class="conjur-posts-tipo-titulo"[^>]*>\s*<a href="'
                        r'(https://conjur\.com\.br/(\d{4})-([a-z]{3})-(\d{2})/[^"]+)"[^>]*>(.*?)</a>', re.S)
    for tipo, u in URLS_CONJUR.items():
        for url, a, mes, d, tit in padrao.findall(pags[u][1]):
            if url in vistos or mes not in MESES:
                continue
            dia = date(int(a), MESES[mes], int(d))
            it = {"tipo": tipo, "titulo": limpa(tit), "url": url, "data": dia}
            vistos[url] = it
            # pelo dia; so os dias de borda (inicio, recorte, fim) sao abertos para
            # a hora decidir. Antes todo dia intermediario virava NOVA: na janela de
            # 72h de 16/11, os itens de 14/11 (antes do recorte) sairam NOVA.
            if dia < inicio.date():
                it["situacao"] = "FORA"
            elif dia in (inicio.date(), recorte.date(), fim.date()):
                abrir.append(url)          # so a hora decide
            elif dia < recorte.date():
                it["situacao"] = "HERDADA"
            elif dia > fim.date():
                it["situacao"] = "DEPOIS"
            else:
                it["situacao"] = "NOVA"
    abertas = fetch_many(abrir)
    for url, (c, p) in abertas.items():
        quando = publicado_em(p)
        it = vistos[url]
        it["quando"] = quando
        it["situacao"] = classifica(quando, inicio, fim, recorte) if quando else "HERDADA"
    for it in vistos.values():
        if chave_url(it["url"]) in urls_pub:
            it["situacao"] = "JA_PUBLICADA"
        out["itens"].append(it)
    # linha-fina das materias publicaveis (antes so o titulo era conferido)
    publicaveis = [it["url"] for it in out["itens"] if it.get("situacao") in ("NOVA", "HERDADA", "SEM_DATA")]
    abertas.update(fetch_many([u for u in publicaveis if u not in abertas]))
    for it in out["itens"]:
        if it["url"] in publicaveis:
            # sem propaganda; frase cortada completada pela pagina ou marcada (volta 3)
            it["resumo"], truncado = resumo_da_pagina(abertas[it["url"]][1], it["titulo"], it["url"])
            if truncado:
                it["resumo_truncado"] = True
    return out


def migalhas(inicio, fim, recorte, urls_pub):
    cod, t, n_tent = fetch_n(URL_MIGALHAS)
    out = {"fonte": "migalhas", "http": cod, "tentativas": n_tent, "itens": []}
    lista = []
    for art in t.split("<article")[1:]:
        m = re.search(r'href="(https://www\.migalhas\.com\.br/quentes/\d+/[^"]+)"', art)
        h2 = re.search(r'class="topico__header">(.*?)</h2>', art, re.S)
        if not m or not h2:
            continue
        h3 = re.search(r'class="topico__body">(.*?)</h3>', art, re.S)
        badge = re.search(r'class="badge badge--\w+">([^<]+)<', art)
        lista.append({"titulo": limpa(h2.group(1)), "resumo": limpa(h3.group(1)) if h3 else "",
                      "badge": limpa(badge.group(1)) if badge else "", "url": m.group(1)})
    unicos = {i["url"]: i for i in lista}
    paginas = fetch_many(list(unicos))
    for url, it in unicos.items():
        if it["resumo"]:          # mesma limpeza da linha-fina do ConJur, com a pagina ja baixada (volta 3)
            it["resumo"], truncado = resumo_da_pagina(paginas[url][1], it["titulo"], url, texto=it["resumo"])
            if truncado:
                it["resumo_truncado"] = True
        quando = publicado_em(paginas[url][1])
        it["quando"] = quando
        it["situacao"] = ("JA_PUBLICADA" if chave_url(url) in urls_pub
                          else classifica(quando, inicio, fim, recorte))
        out["itens"].append(it)
    return out


def marcar_promo_e_repetidas(res, h=None):
    """PROMO: sorteio/evento promocional (nao e noticia). REPETIDA?: mesma
    materia ja publicada por outra fonte nas ultimas edicoes.
    h: execucoes do historico (padrao: o historico principal)."""
    import repeticao
    h = carregar_historico() if h is None else h
    idx = repeticao.indice(h, ignorar_exec_id=IGNORAR_EXEC or None)
    for r in res:
        if r["fonte"] not in ("conjur", "migalhas"):
            continue
        for i in r["itens"]:
            if i["situacao"] not in ("NOVA", "HERDADA", "SEM_DATA"):
                continue
            if PROMO.search(i["titulo"]):
                i["situacao"] = "PROMO"
                continue
            m = repeticao.procurar(repeticao.tokens(i["titulo"]), idx)
            if m:
                i["repetida"] = m


# ------------------------------------------------------------ saida
def hm(it):
    q = it.get("quando")
    if isinstance(q, datetime):
        return q.strftime("%d/%m %H:%M")
    d = it.get("data")
    return d.strftime("%d/%m") if d else "?"


def curto(t, n):
    t = (t or "").strip()
    return t if len(t) <= n else t[:n - 1].rsplit(" ", 1)[0] + "…"


def ok(http):
    vals = http.values() if isinstance(http, dict) else [http]
    return all(v == 200 for v in vals)


# Opiniao do ConJur no indice: no maximo MAX_OPINIAO, pelos termos de prova no
# titulo (nao pela recencia: recente nao e o mesmo que relevante para concurso).
MAX_OPINIAO, MAX_TIT_OPINIAO = 10, 90
_ANCORA = re.compile(r"\b(stf|stj|tst|tse|tcu|cnj|cnmp|supremo|tema|sumulas?|vinculantes?|repercussao|"
                     r"repetitivos?|precedentes?|adi|adpf|adc|re|resp|hc|lei|lc|pec|plp|codigo|cpc|cpp|"
                     r"clt|ctn|constituicao)\b")
_TERMO = re.compile(r"\b(constitucional\w*|penal|processo\w*|processua\w*|tribut\w*|improbidade|provas?|"
                    r"juri|jurisprud\w*|recursos?|execucao|licita\w*|administrativ\w*|civil|consumidor\w*|"
                    r"familia|sucess\w*|contrat\w*|responsabilidade|crimes?|criminal|delitos?|dolo|trafico|"
                    r"inquerito|foro|ilicit\w*|penas?|fiscal|impostos?|icms|iss|cbs|ibs|reforma|direitos?|"
                    r"garantias?|juros|creditos?|dividas?|nulidade|competencia|prescricao|honorarios|"
                    r"sucumb\w*|servidor\w*|concurso\w*)\b")
_NUMERO = re.compile(r"\b(tema|sumula|lei|lc|pec|plp|adi|adpf|adc|re|resp|hc|decreto|mpv?|ec)\s*"
                     r"(?:n[o°.]*\s*)?\d")


def nota_prova(titulo):
    """2 por ancora (tribunal, precedente, ato), 1 por termo juridico, +2 se cita numero."""
    s = unicodedata.normalize("NFKD", (titulo or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return (2 * len(set(_ANCORA.findall(s))) + len(set(_TERMO.findall(s)))
            + (2 if _NUMERO.search(s) else 0))


def opiniao_no_indice(itens, maximo=MAX_OPINIAO):
    """ids dos artigos/colunas publicaveis que entram no indice impresso."""
    cand = [(n, i) for n, i in enumerate(itens)
            if i.get("tipo") in ("artigo", "coluna") and i.get("situacao") in ("NOVA", "HERDADA", "SEM_DATA")]
    melhores = sorted(cand, key=lambda x: (-nota_prova(x[1]["titulo"]), x[0]))[:maximo]
    return {i["id"] for _, i in melhores}


def imprimir(res, inicio, fim, recorte):
    """Indice compacto (linhas de texto). Atribui os ids (lei15527, mpv1400, c7, m3)."""
    out = ["JANELA %s -> %s (herdada = antes de %s) | cite o id em {\"ref\": ...}; URL, hora e chave "
           "saem do JSON" % (inicio.isoformat(), fim.isoformat(), recorte.strftime("%d/%m %H:%M"))]
    seq = {"conjur": 0, "migalhas": 0}
    for r in res:                     # ids primeiro (a ordem de sempre: os refs nao mudam)
        for i in r["itens"]:
            if r["fonte"] in seq and i["situacao"] in ("NOVA", "HERDADA", "SEM_DATA"):
                seq[r["fonte"]] += 1
                i["id"] = "%s%d" % (r["fonte"][0], seq[r["fonte"]])
    for r in res:
        itens = r["itens"]
        cont = {}
        for i in itens:
            cont[i["situacao"]] = cont.get(i["situacao"], 0) + 1
        out.append("\n== %s http=%s %s" % (r["fonte"].upper(), r["http"],
                                           " ".join("%s=%d" % kv for kv in sorted(cont.items()))))
        if r["fonte"] == "congresso_mpv" and (not ok(r["http"]) or not r.get("listadas", 1)):
            out.append("ERRO: congresso_mpv %s — antes de gastar WebSearch, confira as PLANALTO_ATO do "
                       "coletor Gmail (a Resenha PUSH traz as MPVs da janela); WebSearch "
                       "site:congressonacional.leg.br so se o PUSH Planalto nao veio"
                       % ("indisponivel (%s)" % ", ".join(x for x in ("http=%s" % r["http"], tentativas_txt(r)) if x)
                          if not ok(r["http"])
                          else "lida sem nenhuma MPV listada (layout mudou?)"))
        elif r["fonte"] == "congresso_leis" and ok(r["http"]) and not itens and r.get("listadas"):
            out.append("SEM NORMA NOVA NA JANELA: pagina lida (%d normas listadas; a mais recente: %s)"
                       " — fonte ok, sem WebSearch" % (r["listadas"], r["mais_recente"]))
        elif not ok(r["http"]) or (not itens and r["fonte"] != "congresso_mpv"):
            out.append("ERRO: fonte indisponivel ou 0 itens extraidos — usar WebSearch (fallback)")
        ja = ["%s %s (%s)" % ("MPV" if r["fonte"] == "congresso_mpv" else i.get("tipo", "Lei"), i["numero"],
                              curto(i["ementa"], 70))
              for i in itens if i["situacao"] == "JA_PUBLICADA" and r["fonte"].startswith("congresso")]
        if ja:
            out.append("JA PUBLICADAS (nao repetir, nem pelo boletim da Camara): " + "; ".join(ja[:6]))
        no_indice = opiniao_no_indice(itens) if r["fonte"] == "conjur" else set()
        fora = 0
        for i in itens:
            s = i["situacao"]
            if r["fonte"] == "congresso_leis":
                if s == "JA_PUBLICADA":
                    continue
                i["id"] = "lei%s" % i["numero"]
                out.append("[%s] %s | %s nº %s de %s (DOU %s) — %s%s | %s" % (
                    s, i["id"], i["tipo"], i["numero"], i["data_ato"], i["dou"], i["ementa"],
                    " | veto: " + i["veto"] if i["veto"] else "", i["materia"]))
            elif r["fonte"] == "congresso_mpv":
                if s == "JA_PUBLICADA":
                    continue
                i["id"] = "mpv%s" % i["numero"]
                out.append("[%s] %s | MPV %s/%s — DOU %s (detalhe oficial, http %s) — %s" % (
                    s, i["id"], i["numero"], i["ano"], i["dou"] or "?", i["http_detalhe"], i["ementa"]))
            elif s in ("NOVA", "HERDADA", "SEM_DATA"):
                tag = i.get("tipo", "noticia")[:3].upper()
                rep = " [REPETIDA?~%s]" % i["repetida"] if i.get("repetida") else ""
                if i.get("tipo") in ("artigo", "coluna"):
                    # artigo/coluna: so o titulo, encurtado (no maximo 6 vao ao e-mail, sem resumo)
                    if i["id"] not in no_indice:
                        fora += 1
                        continue
                    out.append("[%s|%s] %s | %s | %s%s" % (s, tag, i["id"], hm(i),
                                                           curto(i["titulo"], MAX_TIT_OPINIAO), rep))
                    continue
                extra = (" — " + curto(i["resumo"], 170)) if i.get("resumo") and tag == "NOT" else ""
                if extra and i.get("resumo_truncado") and not extra.endswith("…"):
                    extra += "…"              # linha-fina cortada na fonte (volta 3)
                out.append("[%s|%s] %s | %s | %s%s%s" % (s, tag, i["id"], hm(i), i["titulo"], extra, rep))
        if fora:
            out.append("(+%d artigos/colunas fora do indice: titulos com menos termos de prova; "
                       "continuam no JSON)" % fora)
    return out


# ------------------------------------------------------------ status das fontes
def _entre_parenteses(s):
    return " (%s)" % s if s else ""


def status_fontes(res):
    """{id do source_status: (status, detalhe)} das 4 fontes deste script."""
    por = {r["fonte"]: r for r in res}
    st = {}
    r = por.get("congresso_leis")
    if r:
        if r["http"] != 200:
            st["congresso_ultimas_leis"] = ("falha", "http=%s%s" % (r["http"], _entre_parenteses(tentativas_txt(r))))
        elif not r.get("listadas"):
            st["congresso_ultimas_leis"] = ("falha", "pagina lida, 0 normas extraidas (layout?)")
        else:
            novas = sum(1 for i in r["itens"] if i["situacao"] != "JA_PUBLICADA")
            st["congresso_ultimas_leis"] = ("ok", "%d norma(s) na janela" % novas if novas
                                            else "sem norma nova na janela")
    r = por.get("congresso_mpv")
    if r:
        if r["http"] != 200:
            st["congresso_mpvs"] = ("falha", "http=%s%s; conferir PLANALTO_ATO"
                                    % (r["http"], _entre_parenteses(tentativas_txt(r))))
        elif not r.get("listadas", 1):
            st["congresso_mpvs"] = ("falha", "pagina lida, 0 MPVs listadas (layout?)")
        else:
            st["congresso_mpvs"] = ("ok", "%d MPV(s) recente(s)" % len(r["itens"]))
    for fonte in ("conjur", "migalhas"):
        r = por.get(fonte)
        if not r:
            continue
        if not ok(r["http"]):
            st[fonte] = ("falha", "http=%s%s" % (r["http"], _entre_parenteses(tentativas_txt(r))))
        elif not r["itens"]:
            st[fonte] = ("falha", "0 itens extraidos (layout?)")
        else:
            pub = sum(1 for i in r["itens"] if i["situacao"] in ("NOVA", "HERDADA", "SEM_DATA"))
            st[fonte] = ("ok", "%d publicaveis" % pub)
    return st


def gravar_status(st, script, caminho=None):
    """Merge em $ROBOZINHO_TMP/fontes_status.json ({id: {status, detalhe, script,
    execution_id}}), com trava (os scripts do passo 2 rodam em paralelo)."""
    caminho = caminho or os.path.join(TMP, "fontes_status.json")
    exec_id = ""
    try:
        exec_id = json.load(open(os.path.join(TMP, "janela.json"), encoding="utf-8")).get("execution_id") or ""
    except Exception:
        pass
    try:
        import fcntl
    except ImportError:
        fcntl = None
    with open(caminho + ".lock", "w") as trava:
        if fcntl:
            fcntl.flock(trava, fcntl.LOCK_EX)
        try:
            atual = json.load(open(caminho, encoding="utf-8"))
            if not isinstance(atual, dict):
                atual = {}
        except Exception:
            atual = {}
        for ident, (status, detalhe) in st.items():
            atual[ident] = {"status": status, "detalhe": detalhe, "script": script,
                            "execution_id": exec_id}
        tmp = caminho + ".%d.tmp" % os.getpid()
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(atual, f, ensure_ascii=False, indent=1)
        os.replace(tmp, caminho)


def linha_status(st):
    return "SOURCE_STATUS " + json.dumps({k: v[0] for k, v in st.items()}, ensure_ascii=False)


def main():
    global HISTORICO
    ap = argparse.ArgumentParser()
    ap.add_argument("--janela", default=os.path.join(TMP, "janela.json"))
    ap.add_argument("--saida", default=os.path.join(TMP, "coleta_web.json"))
    ap.add_argument("--historico", default=HISTORICO,
                    help="historico principal (padrao: work/resumo-legislativo-historico.json)")
    a = ap.parse_args()
    HISTORICO = a.historico
    inicio, fim = carregar_janela(a.janela)
    recorte = fim - timedelta(hours=24)
    historico = carregar_historico()
    atos_pub, urls_pub = carregar_publicados(historico)

    with ThreadPoolExecutor(max_workers=4) as ex:
        fl = ex.submit(leis, inicio, fim, recorte, atos_pub)
        fm = ex.submit(mpvs, inicio, fim, recorte, atos_pub)
        fc = ex.submit(conjur, inicio, fim, recorte, urls_pub)
        fg = ex.submit(migalhas, inicio, fim, recorte, urls_pub)
        res = [fl.result(), fm.result(), fc.result(), fg.result()]

    marcar_promo_e_repetidas(res, historico)
    for linha in imprimir(res, inicio, fim, recorte):
        print(linha)

    def ser(o):
        return o.isoformat() if isinstance(o, (datetime, date)) else str(o)
    with open(a.saida, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1, default=ser)
    print("\n(JSON completo: %s)" % a.saida)
    st = status_fontes(res)
    try:
        gravar_status(st, "coleta_web.py")
    except Exception as e:
        print("AVISO: fontes_status.json nao gravado (%s)" % e)
    print(linha_status(st))


if __name__ == "__main__":
    main()
