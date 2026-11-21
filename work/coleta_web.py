#!/usr/bin/env python3
# =====================================================================
# coleta_web.py — coleta deterministica das fontes web liberadas no
# allowlist: Congresso (leis e MPVs), Agencia Camara, ConJur e Migalhas.
# Substitui o curl+regex que o coletor Web improvisava a cada dia (e errava).
#
# - Agencia Camara (www.camara.leg.br/noticias/ultimas, 10 noticias por pagina):
#   o boletim por e-mail falha sem aviso (nenhum em 16 e 17/11/2026, com 23
#   noticias de 16/11 no site; tambem em 31/10-04/11 e 09/11) e a edicao ficava
#   sem as votacoes do Plenario e as sancoes. O site e a fonte do boletim: o
#   script le as paginas ate sair da janela e marca [LEI] (sancao, promulgacao,
#   veto, medida provisoria) e [PLENARIO] (aprovacao/rejeicao em Plenario), com
#   id (cam1, cam2); comissao, projeto apresentado e debate so sao contados.
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
# - Cada item publicavel ganha um id curto (lei15527, mpv1400, cam2, c7, m3): o
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
# (21/11) Cobertura: a 1a pagina do ConJur (15 noticias) e do Migalhas (10) cobria so a tarde da vespera — num
# dia util ~45% das noticias do ConJur e ~80% das do Migalhas ficavam de fora (as segundas, a sexta inteira), com
# status "ok". ConJur: a WP REST API do proprio dominio da a janela inteira numa requisicao, com hora exata, tipo
# (class_list "tipos-noticias|artigos|colunas|estudio"), linha-fina (yoast og_description) e o corpo (lead,
# ficha, nota oficial) — sem abrir pagina de materia. Sem a API, a listagem HTML paginada (?tipo=noticias&
# per_page=15&pg=N; "/noticias/page/N/" devolve a 1a pagina: a trava "pagina sem URL nova" para o laco).
# Migalhas: ?pagina=N, parando no selo de data anterior ao inicio da janela.
URL_CONJUR_API = "https://conjur.com.br/wp-json/wp/v2/posts"
CAMPOS_CONJUR_API = "link,date_gmt,title,class_list,content,yoast_head_json"
POR_PAGINA_CONJUR_API = 100
MAX_PAGINAS_CONJUR_API = 3       # a janela de 72h (segunda-feira) tem ~100 posts
URL_CONJUR_PG = "https://conjur.com.br/noticias/?tipo=noticias&per_page=15&pg=%d"
POR_PAGINA_CONJUR = 15
MAX_PAGINAS_CONJUR = 5           # dia util ~2 paginas; segunda ~4
MAX_PAGINAS_MIGALHAS = 7         # dia util 4-5; segunda 6-7
TIPOS_WP = {"tipos-noticias": "noticia", "tipos-artigos": "artigo", "tipos-colunas": "coluna",
            "tipos-estudio": "estudio"}            # "Estudio ConJur" = conteudo patrocinado (PROMO)
URL_CAMARA = "https://www.camara.leg.br/noticias/ultimas"
MAX_PAGINAS_CAMARA = 8   # 10 noticias por pagina; um dia cheio de Plenario tem ~60
# [LEI]: lei nova, sancao, promulgacao, veto ou medida provisoria. [PLENARIO]: aprovacao ou rejeicao em Plenario.
# Titulo que comeca por "Projeto"/"Comissao"/"Proposta" e projeto apresentado ou votacao de comissao: nao marca
# ("Projeto preve sancao para..." fala de penalidade, nao de lei sancionada).
CAM_LEI = re.compile(r"\bsanciona(?:d[ao]s?|m|r)?\b|\bsan[cç][aã]o (?:d[aeo]|presidencial)\b|\bpromulga(?:d[ao]s?|m|r)?\b|"
                     r"\bpromulga[cç][aã]o\b|\bvetos?\b|\bveta(?:d[ao]s?|m|r)?\b|\bmedidas? provis[oó]rias?\b|"
                     r"\bvira lei\b|\bentra em vigor\b|\blei (?:[eé]|foi) publicada\b|\bpublicada (?:a )?lei\b", re.I)
CAM_PLENARIO = re.compile(r"^(?:C[aâ]mara|Plen[aá]rio|Deputados|Congresso)\b.{0,45}?\b(?:aprova|aprovam|rejeita|rejeitam|"
                          r"conclui|concluem|derruba|derrubam|mant[eé]m|mantêm)\b|"
                          r"\benviam? ao Senado\b|\bseguem? para o Senado\b|"
                          r"\b(?:seguem?|vai|v[aã]o) (?:para|[aà]) (?:a )?san[cç][aã]o\b", re.I)
CAM_NAO_MARCA = re.compile(r"^(?:Projeto|Comiss[aã]o|Comiss[oõ]es|Proposta|Subcomiss[aã]o|Frente|Conselho)\b", re.I)
# (21/11) Ato interno ou honorifico aprovado em Plenario nao e [PLENARIO] (19/11: "Camara aprova criacao de selo de
# respeito a voz do cidadao", PRC 25/26, foi ao card): so contado
CAM_INTERNO = re.compile(r"\bPRC\b|projeto de resolu[çc][ãa]o|\bselos?\b|\bmedalhas?\b|\bcomendas?\b|"
                         r"sess[ãa]o solene|homenage\w*|\bdenomina\w*|\bdiplomas?\b|\bDia Nacional\b|"
                         r"\bSemana Nacional\b|\bM[êe]s Nacional\b|honra ao m[ée]rito|t[íi]tulo de cidad", re.I)
CAM_DUVIDA = re.compile(r"plen[aá]rio|sancion|promulg|\bvetos?\b|medidas? provis[oó]rias?", re.I)
IGNORAR_EXEC = ""   # re-execucao (inicio.py --refazer): a edicao de hoje nao conta como publicada
PROMO = re.compile(r"^\s*sorteio\b|\bsorteio d[aoe]\b|\bpromove (congresso|semin[aá]rio|evento|"
                   r"webin[aá]rio|curso|encontro|jornada)\b|\blan[cç]amento d[eo] livro\b|"
                   # (21/11, Migalhas p. 2-6) cursinho, evento, feira, live, lancamento
                   r"\baula (?:ao vivo|gratuita|inaugural)\b|\b(?:live|webin[aá]rio|videocast|podcast)\b|"
                   r"(?<![-\w])feira d[aeo]s?\b|\b(?:realiza|promove|participa d[aoe]s?|homenage\w*)\b.{0,40}?(?<![-\w])(?:feira|congresso|"
                   r"semin[aá]rio|evento|encontro|jornada|debate|palestra|f[óo]rum|webin[aá]rio|curso|aula|videocast|"
                   r"podcast|live|pr[eê]mio)\b|\b(?:livros?|obras?|biografia)\b.{0,60}?\bser[aáã]o? lan[cç]ad[oa]s?\b|"
                   r"\blan[cç]a (?:livro|obra|biografia)\b", re.I)
# Opiniao disfarcada de noticia (so contada, como PROMO): "Especialista: ...", "Advogado aponta ...",
# "..., alerta advogado"
OPINIAO_DISFARCADA = re.compile(r"^\s*especialistas?\s*:|^\s*(?:especialistas?|advogad[oa]s?|tributaristas?|"
                                r"professor[ae]?s?|juristas?|consultor[ae]?s?)\b.{0,60}?\b(?:aponta|alerta|explica|"
                                r"comenta|analisa|avalia|orienta|esclarece|lista|recomenda)\w*\b|"
                                r",\s*(?:aponta|alerta|explica|avalia|diz|afirma)\s+(?:advogad[oa]|especialista|"
                                r"tributarista|professor[a]?|jurista)s?\s*$", re.I)


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
    # (21/11) o titulo do item de Planalto tambem identifica o ato ("Decreto nº 13.167, de 16/11/2026" com chave
    # gravada fora do formato): o LEGIN nao o traz de volta como HERDADA
    for e in h:
        if e.get("execution_id") == IGNORAR_EXEC:
            continue
        for it in e.get("items") or []:
            if it.get("categoria") == "Planalto/Legislação":
                ident = repeticao.ato_no_titulo(it.get("titulo") or "")
                if ident:
                    atos.add((repeticao.tipo_canonico(ident[0]), ident[1]))
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


# ------------------------------------------------------------ LEGIN (Legislacao Informatizada da Camara)
# (21/11) Decretos e demais atos do Executivo so entravam pela Resenha PUSH, que chega ~10h — depois da execucao das
# 7h —, e o ato do DOU de D saia, por construcao, na edicao de D+1 (decretos 13.167-13.172 do DOU de 17/11 so em
# 18/11); sem a resenha, so a limitacao enganosa "sem ato novo". www.in.gov.br e o Senado sao recusados pela rede; a
# Legislacao Informatizada da Camara (rotas 9 e 15 da referencia operacional) abre: 1 GET na busca ordenada por data
# (20 normas por pagina, todas as especies federais) e 1 GET por ato candidato no detalhe (www2.camara.leg.br/legin),
# que traz "Diario Oficial da Uniao - Secao 1 [- Edicao Extra] - DD/MM/AAAA, Pagina N". Candidato = ato de especie
# publicavel, assinado ate LEGIN_DIAS_ATO dias antes do inicio da janela, que nao esta no historico (atos_pub) nem nas
# listas do Congresso desta execucao (leis e MPVs ficam com o Congresso: ids lei.../mpv... sem colisao). Ids pelo
# tipo e numero (dec13173, lc239, ec141, dleg123; lei/mpv so quando o Congresso nao listou): o mesmo ato tem o mesmo id
# em qualquer execucao; chave planalto|<tipo>|<n>|<ano>|<data do ato> (a mesma do Congresso e do montador: o
# dedupe com a resenha PUSH e pela identidade tipo + numero, repeticao.py).
URL_LEGIN = "https://www.camara.leg.br/legislacao/busca"
MAX_PAGINAS_LEGIN = 2
LEGIN_DIAS_ATO = 3
LEGIN_DIAS_DOU = 7               # DOU anterior ao inicio da janela, ate aqui, e HERDADA (ato que nunca saiu)
MAX_DETALHES_LEGIN = 10
# especie -> (tipo da chave, prefixo do id); as demais (atos da Mesa, resolucoes, pactos) so contadas
TIPOS_LEGIN = {"lei": ("lei", "lei"), "lei complementar": ("lei-complementar", "lc"), "decreto": ("decreto", "dec"),
               "decreto legislativo": ("decreto-legislativo", "dleg"), "medida provisoria": ("mpv", "mpv"),
               "emenda constitucional": ("emenda-constitucional", "ec"), "decreto-lei": ("decreto-lei", "dl")}
MESES_EXTENSO = {m: i + 1 for i, m in enumerate("janeiro fevereiro marco abril maio junho julho agosto setembro "
                                                "outubro novembro dezembro".split())}
_NORMA_LEGIN = re.compile(r"^(.+?)\s+n[ºo°.]*\s*([\d.]+),?\s+de\s+(\d{1,2})[ºo°]?\s+de\s+([a-zç]+)\s+de\s+(\d{4})", re.I)
_DOU_LEGIN = re.compile(r"Di[áa]rio Oficial da Uni[ãa]o\s*-\s*Se[çc][ãa]o\s*(\d)\s*(-\s*Edi[çc][ãa]o Extra(?:\s*-\s*[A-Z])?\s*)?"
                        r"-\s*(\d\d/\d\d/\d{4}),?\s*P[áa]gina\s*(\d+)\s*\(Publica[çc][ãa]o Original\)", re.I)


def url_legin(ano, pagina=1):
    from urllib.parse import urlencode
    q = [("geral", ""), ("ano", str(ano)), ("abrangencia", "Legislação Federal"), ("ordenacao", "data:DESC"),
         ("tipo", ""), ("origem", ""), ("situacao", ""), ("numero", "")]
    if pagina > 1:
        q.append(("pagina", str(pagina)))
    return URL_LEGIN + "?" + urlencode(q)


def norma_legin(titulo):
    """'Decreto nº 13.173, de 19 de Novembro de 2026' -> (especie, numero, date) ou None."""
    m = _NORMA_LEGIN.match((titulo or "").strip())
    if not m:
        return None
    mes = MESES_EXTENSO.get(_sem_acento(m.group(4)))
    if not mes:
        return None
    try:
        dia = date(int(m.group(5)), mes, int(m.group(3)))
    except ValueError:
        return None
    return " ".join(m.group(1).split()), m.group(2).replace(".", ""), dia


def listagem_legin(t):
    """[{titulo, url, ementa}] da pagina de busca."""
    out = []
    for b in re.split(r'<li class="busca-resultados__item', t or "")[1:]:
        a = re.search(r'busca-resultados__cabecalho">\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', b, re.S)
        if not a:
            continue
        em = re.search(r'busca-resultados__descricao[^>]*>(.*?)</p>', b, re.S)
        ementa = limpa(em.group(1)) if em else ""
        out.append({"titulo": limpa(a.group(2)), "url": html.unescape(a.group(1)).strip(),
                    "ementa": re.sub(r"^Ementa:\s*", "", ementa)})
    return out


def detalhe_legin(t):
    """{dou, extra, pagina_dou, apelido, ementa} da pagina de detalhe (vazio se nao abriu)."""
    out = {}
    m = _DOU_LEGIN.search(limpa(t or ""))
    if m:
        out.update(dou=m.group(3), extra=bool(m.group(2)), pagina_dou=m.group(4), secao=m.group(1))
    hs = [limpa(x) for x in re.findall(r"<h1>(.*?)</h1>", t or "", re.S)]
    if len(hs) > 1 and not _NORMA_LEGIN.match(hs[1]):
        out["apelido"] = hs[1]                     # "Jornada de Trabalho 5X2"
    em = re.search(r'class="sessao ementa">\s*<span class="rotulo">EMENTA:</span>(.*?)</p>', t or "", re.S)
    if em:
        out["ementa"] = limpa(em.group(1))
    return out


def legin(inicio, fim, recorte, atos_pub, no_congresso=lambda: set()):
    """Atos federais do LEGIN que faltam (ver o comentario do bloco). no_congresso: funcao que devolve
    {(tipo canonico, numero)} das leis/MPVs listadas pelo Congresso nesta execucao (chamada depois da listagem)."""
    import repeticao
    out = {"fonte": "legin", "http": 0, "tentativas": 0, "paginas": 0, "listadas": 0, "outras_especies": 0,
           "mais_recente": "", "itens": [], "no_congresso": 0, "ja_publicadas": []}
    limite = inicio.date() - timedelta(days=LEGIN_DIAS_ATO)
    vistos, normas = set(), []
    for ano in sorted({limite.year, fim.year}, reverse=True):
        for pag in range(1, MAX_PAGINAS_LEGIN + 1):
            cod, t, n = fetch_n(url_legin(ano, pag))
            if not out["paginas"]:
                out["http"], out["tentativas"] = cod, n
            if cod != 200:
                if out["paginas"]:
                    out["http_pagina"] = {"pagina": pag, "http": cod}
                break
            out["paginas"] += 1
            lista = [x for x in listagem_legin(t) if x["url"] not in vistos]
            if not lista:
                break
            datas = []
            for x in lista:
                vistos.add(x["url"])
                nm = norma_legin(x["titulo"])
                if not nm:
                    continue
                out["listadas"] += 1
                datas.append(nm[2])
                if not out["mais_recente"]:
                    out["mais_recente"] = "%s nº %s, de %s" % (nm[0], nm[1], nm[2].strftime("%d/%m/%Y"))
                normas.append((x, nm))
            if not datas or min(datas) < limite:
                break
        if out["http"] != 200:
            break
    listados_congresso = None
    cand = []
    for x, (especie, numero, dia) in normas:
        tipo = TIPOS_LEGIN.get(_sem_acento(especie))
        if not tipo:
            out["outras_especies"] += 1
            continue
        if dia < limite:
            continue
        ident = (repeticao.tipo_canonico(tipo[0]), numero.lstrip("0") or numero)
        if ident in atos_pub:
            out["ja_publicadas"].append("%s %s" % (especie, numero))
            continue
        if tipo[0] in ("lei", "lei-complementar", "mpv"):
            if listados_congresso is None:
                listados_congresso = no_congresso() or set()
            if ident in listados_congresso:
                out["no_congresso"] += 1
                continue
        cand.append((x, especie, numero, dia, tipo))
    cand = cand[:MAX_DETALHES_LEGIN]
    detalhes = fetch_many([x["url"] for x, *_ in cand])
    for x, especie, numero, dia, (tipo_chave, prefixo) in cand:
        cod, t = detalhes.get(x["url"], (0, ""))
        d = detalhe_legin(t) if cod == 200 else {}
        dou = dmy(d["dou"]) if d.get("dou") else None
        if dou is None:
            sit = "SEM_DATA_OFICIAL"
        elif dou > fim.date():
            continue
        elif dou >= inicio.date():
            sit = "NOVA"
        elif dou >= inicio.date() - timedelta(days=LEGIN_DIAS_DOU):
            sit = "HERDADA"
        else:
            continue
        it = {"situacao": sit, "tipo": especie, "tipo_chave": tipo_chave, "prefixo": prefixo, "numero": numero,
              "data_ato": dia.strftime("%d/%m/%Y"), "dou": dou.strftime("%d/%m/%Y") if dou else "",
              "extra": bool(d.get("extra")), "pagina_dou": d.get("pagina_dou", ""), "secao_dou": d.get("secao", ""),
              "ementa": d.get("ementa") or x["ementa"], "url": x["url"], "http_detalhe": cod,
              "chave": "planalto|%s|%s|%s|%s" % (tipo_chave, numero, dia.year, dia.isoformat())}
        if d.get("apelido"):
            it["apelido"] = d["apelido"]
        out["itens"].append(it)
    return out


def legin_seguro(inicio, fim, recorte, atos_pub, no_congresso=lambda: set()):
    """O LEGIN e reforco: erro aqui nunca derruba as outras fontes."""
    try:
        return legin(inicio, fim, recorte, atos_pub, no_congresso)
    except Exception as e:  # noqa: BLE001
        return {"fonte": "legin", "http": 0, "tentativas": 0, "paginas": 0, "listadas": 0, "itens": [],
                "erro": "%s: %s" % (type(e).__name__, e)}


# ------------------------------------------------------------ Agencia Camara
def marca_camara(titulo):
    """'LEI', 'PLENARIO' ou '' (noticia que nao e lei nova nem votacao de Plenario)."""
    if CAM_NAO_MARCA.match(titulo):
        return ""
    if CAM_LEI.search(titulo):
        return "LEI"
    return "PLENARIO" if CAM_PLENARIO.search(titulo) and not CAM_INTERNO.search(titulo) else ""


def camara(inicio, fim, recorte, urls_pub):
    """Ultimas noticias da Agencia Camara dentro da janela. So as marcadas [LEI]/[PLENARIO] viram
    item; as demais sao contadas ("resto"), com os titulos duvidosos listados para conferencia."""
    out = {"fonte": "camara_noticias", "http": 0, "tentativas": 0, "paginas": 0, "itens": [],
           "lidas": 0, "na_janela": 0, "resto": 0, "duvidosos": [], "completa": False}
    vistos = set()
    for pag in range(1, MAX_PAGINAS_CAMARA + 1):
        cod, t, n_tent = fetch_n(URL_CAMARA + ("?pagina=%d" % pag if pag > 1 else ""))
        if pag == 1:
            out["http"], out["tentativas"] = cod, n_tent
        if cod != 200:
            if pag > 1:
                out["http_pagina"] = {"pagina": pag, "http": cod}    # as primeiras paginas valem; a janela fica incompleta
            break
        out["paginas"] = pag
        antigo = False
        blocos = re.findall(r'<article class="g-chamada[^"]*">(.*?)</article>', t, re.S)
        for b in blocos:
            a = re.search(r'g-chamada__titulo">\s*<a href="([^"]+)"[^>]*>(.*?)</a>', b, re.S)
            d = re.search(r'g-chamada__data">\s*(\d\d/\d\d/\d{4})\s+(\d\d:\d\d)', b)
            if not a or not d:
                continue
            url, titulo = html.unescape(a.group(1)).strip(), limpa(a.group(2))
            if not titulo or url in vistos:
                continue
            vistos.add(url)
            out["lidas"] += 1
            quando = datetime.strptime(d.group(1) + " " + d.group(2), "%d/%m/%Y %H:%M").replace(tzinfo=TZ)
            sit = classifica(quando, inicio, fim, recorte)
            if sit == "FORA":
                antigo = True
                continue
            if sit == "DEPOIS":
                continue
            out["na_janela"] += 1
            marca = marca_camara(titulo)
            if not marca:
                out["resto"] += 1
                if CAM_DUVIDA.search(titulo):
                    out["duvidosos"].append(titulo)
                continue
            ret = re.search(r'g-chamada__retranca">\s*([^<]*)<', b)
            out["itens"].append({
                "situacao": "JA_PUBLICADA" if chave_url(url) in urls_pub else sit, "marca": marca,
                "titulo": titulo, "retranca": limpa(ret.group(1)) if ret else "", "url": url, "quando": quando})
        if antigo or not blocos:
            out["completa"] = bool(blocos)      # chegou ao que e anterior a janela: nada ficou de fora
            break
    return out


def camara_seguro(inicio, fim, recorte, urls_pub):
    """A Agencia Camara e reforco: erro aqui nunca derruba as outras fontes."""
    try:
        return camara(inicio, fim, recorte, urls_pub)
    except Exception as e:  # noqa: BLE001
        return {"fonte": "camara_noticias", "http": 0, "tentativas": 0, "paginas": 0, "itens": [], "lidas": 0,
                "na_janela": 0, "resto": 0, "duvidosos": [], "completa": False, "erro": "%s: %s" % (type(e).__name__, e)}


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


# ------------------------------------------------------------ lead, ficha, nota oficial e autor (21/11)
# O corpo da materia ja esta em maos (API do ConJur; pagina do Migalhas e, no fallback, a do ConJur): nenhum pedido
# a mais. O indice levava so a linha-fina, e orgao, processo/tema e natureza vinculante se perdiam (19/11: "Concessao
# da gratuidade..." saiu em Midia, sem orgao; era tese vinculante da Corte Especial do STJ). lead = os 2 primeiros
# paragrafos, verbatim, cortados em fim de frase (ate MAX_LEAD); ficha = so o 1o acerto de cada campo, tirado do
# lead (tribunal pelo titulo antes): tribunal · orgao · processo/tema · "vinculante" (so no paragrafo do orgao ou do
# processo). Placar e relator NAO saem por regex (17/11 c12: o "empate" era do Carf; 18/11 c14: o "Tema 1.139" era
# precedente de 2022): estao verbatim no lead.
MAX_LEAD = 450
MIN_PARAGRAFO = 40
MAX_FICHA = 60
FIM_CORPO_CONJUR = ("assinante-bio", "assinante-title", "Seja o primeiro a comentar")
_UF = {"acre": "AC", "alagoas": "AL", "amapa": "AP", "amazonas": "AM", "bahia": "BA", "ceara": "CE",
       "distrito federal": "DF", "distrito federal e territorios": "DF", "espirito santo": "ES", "goias": "GO",
       "maranhao": "MA", "mato grosso": "MT", "mato grosso do sul": "MS", "minas gerais": "MG", "para": "PA",
       "paraiba": "PB", "parana": "PR", "pernambuco": "PE", "piaui": "PI", "rio de janeiro": "RJ",
       "rio grande do norte": "RN", "rio grande do sul": "RS", "rondonia": "RO", "roraima": "RR",
       "santa catarina": "SC", "sao paulo": "SP", "sergipe": "SE", "tocantins": "TO"}
_TRIB_NOME = [(re.compile(r"supremo tribunal federal|\bsupremo\b"), "STF"),
              (re.compile(r"superior tribunal de justica"), "STJ"),
              (re.compile(r"tribunal superior do trabalho"), "TST"),
              (re.compile(r"tribunal superior eleitoral"), "TSE"),
              (re.compile(r"conselho nacional de justica"), "CNJ")]
_TRIB_SIGLA = re.compile(r"\b(STF|STJ|TST|TSE|STM|CNJ|CNMP|TCU)\b|\bTJ[-/ ]?([A-Z]{2})\b|\b(TRF|TRT)[-/ ]?(\d{1,2})\b")
_TRIB_EXTENSO = re.compile(r"tribunal de justica d[oae]s? ((?:[a-z]+ ?){1,4})|tribunal regional (federal|do trabalho) "
                           r"da (\d{1,2})[ao]? regiao")
_ORGAO = re.compile(r"\b(\d{1,2})\s*[ªaº]\s+(turma recursal|turma|se[çc][ãa]o|c[âa]mara(?: de direito (?:p[úu]blico|"
                    r"privado|criminal|empresarial))?)\b|\b(corte especial|[óo]rg[ãa]o especial|plen[áa]rio virtual|"
                    r"plen[áa]rio)\b", re.I)
_PROCESSO = re.compile(r"\b(ADIn?|ADPF|ADC|ADO|RE|ARE|REsp|AREsp|HC|RHC|RMS|MS|Rcl|EREsp|IRDR|IAC|Pet|Inq|AP|RO|"
                       r"RR|AIRR|AgRg|EDcl)\s+(?:n[ºo°.]\s*)?(\d[\d.]*\d|\d)\b|\b(Tema)\s+(?:n[ºo°.]\s*)?(\d[\d.]*\d|\d)\b|"
                       r"\bA[çc](?:[ãa]o|[õo]es) Diretas? de Inconstitucionalidade (?:n[ºo°.]\s*)?(\d[\d.]*\d)")
_VINCULANTE = re.compile(r"recursos? repetitivos?|relev[âa]ncia da quest[ãa]o federal|tese vinculante|"
                         r"repercuss[ãa]o geral|s[úu]mula vinculante", re.I)
# "Com informacoes da assessoria de imprensa do STF" (ConJur) / "Informacoes: STF." (Migalhas): a materia
# reproduz comunicacao oficial do orgao — 19/11: a nota da Presidencia do STF (art. 33 da Loman, prazo regimental
# de 15 dias) saiu na Fofoquinha como boato "segundo a Folha".
_NOTA_OFICIAL = re.compile(
    r"com informa[çc][õo]es d[aoe]s?\s+(?:assessoria(?: de imprensa| de comunica[çc][ãa]o)? d[aoe]s?\s+|"
    r"secretaria de comunica[çc][ãa]o(?: social)? d[aoe]s?\s+)?(?P<a>[^.<\n]{2,60})|"
    r"\binforma[çc][õo]es:\s*(?P<b>[^.<\n]{2,40})", re.I)
_ORGAO_OFICIAL = [(re.compile(r"^(?:stf|supremo tribunal federal)\b", re.I), "STF"),
                  (re.compile(r"^(?:stj|superior tribunal de justi[çc]a)\b", re.I), "STJ"),
                  (re.compile(r"^(?:tst|tribunal superior do trabalho)\b", re.I), "TST"),
                  (re.compile(r"^(?:tse|tribunal superior eleitoral)\b", re.I), "TSE"),
                  (re.compile(r"^(?:cnj|conselho nacional de justi[çc]a)\b", re.I), "CNJ"),
                  (re.compile(r"^(?:cnmp|conselho nacional do minist[ée]rio p[úu]blico)\b", re.I), "CNMP"),
                  (re.compile(r"^(?:pgr|procuradoria-geral da rep[úu]blica)\b", re.I), "PGR"),
                  (re.compile(r"^(?:mpf|minist[ée]rio p[úu]blico federal)\b", re.I), "MPF"),
                  (re.compile(r"^(?:agu|advocacia-geral da uni[ãa]o)\b", re.I), "AGU"),
                  (re.compile(r"^presid[êe]ncia da rep[úu]blica\b", re.I), "Presidência"),
                  (re.compile(r"^(TRF|TRT)[-/ ]?(\d{1,2})\b"), None),
                  (re.compile(r"^TJ[-/ ]?([A-Z]{2})\b"), None)]


def _sem_acento_min(s):
    return _sem_acento(s or "")


def _corpo_materia(pagina, fonte):
    """HTML so do corpo da materia: Migalhas = div topico__materia; ConJur = ate a assinatura/comentarios (a API ja
    entrega so o corpo)."""
    p = pagina or ""
    if fonte == "migalhas":
        i = p.find('class="topico__materia"')
        if i < 0:
            return ""
        p = p[i:]
        j = p.find("app-compartilhamento-baixo")
        return p[:j] if j > 0 else p
    for marca in FIM_CORPO_CONJUR:
        j = p.find(marca)
        if j > 0:
            p = p[:j]
    return p


def paragrafos_corpo(pagina, fonte):
    """Paragrafos de texto do corpo (sem os curtos: intertitulo, legenda)."""
    return [x for x in paragrafos(_corpo_materia(pagina, fonte)) if len(x) >= MIN_PARAGRAFO]


def lead_da_pagina(pagina, fonte):
    """(lead, paragrafos_do_lead): os 2 primeiros paragrafos do corpo, verbatim, cortados no fim de frase
    (ate MAX_LEAD caracteres)."""
    pars = paragrafos_corpo(pagina, fonte)[:2]
    texto = " ".join(pars)
    if len(texto) <= MAX_LEAD:
        return texto, pars
    corte = [m.end() for m in FIM_FRASE.finditer(texto) if m.end() <= MAX_LEAD]
    if corte:
        return texto[:corte[-1]].strip(), pars
    return texto[:MAX_LEAD - 1].rsplit(" ", 1)[0] + "…", pars


def _tribunal(texto):
    m = _TRIB_SIGLA.search(texto or "")
    if m:
        if m.group(1):
            return m.group(1)
        if m.group(2):
            return "TJ-" + m.group(2)
        return "%s-%s" % (m.group(3), m.group(4))
    s = _sem_acento_min(texto)
    achados = []
    for rx, sigla in _TRIB_NOME:
        mm = rx.search(s)
        if mm:
            achados.append((mm.start(), sigla))
    mm = _TRIB_EXTENSO.search(s)
    if mm:
        if mm.group(1):
            nome = mm.group(1).strip()
            uf = next((v for k, v in sorted(_UF.items(), key=lambda kv: -len(kv[0])) if nome.startswith(k)), "")
            if uf:
                achados.append((mm.start(), "TJ-" + uf))
        else:
            achados.append((mm.start(), "%s-%s" % ("TRF" if mm.group(2) == "federal" else "TRT", mm.group(3))))
    return min(achados)[1] if achados else ""


def _orgao(m):
    if m.group(1):
        tipo = m.group(2).lower().replace("secao", "seção").replace("camara", "câmara")
        return "%sª %s" % (m.group(1), " ".join(w if w == "de" else w[:1].upper() + w[1:] for w in tipo.split()))
    o = m.group(3).lower()
    return {"corte especial": "Corte Especial", "órgão especial": "Órgão Especial", "orgão especial": "Órgão Especial",
            "orgao especial": "Órgão Especial", "órgao especial": "Órgão Especial"}.get(
        o, "Plenário virtual" if "virtual" in o else "Plenário")


def _processo(m):
    if m.group(5):
        return "ADI " + m.group(5)
    if m.group(3):
        return "Tema " + m.group(4)
    sig = "ADI" if m.group(1) in ("ADIn",) else m.group(1)
    return "%s %s" % (sig, m.group(2))


def ficha_do_lead(titulo, pars):
    """'STJ · Corte Especial · REsp 2.231.680 · vinculante' (so o que achou; ate MAX_FICHA caracteres) ou ''."""
    campos = []
    trib = _tribunal(titulo) or _tribunal(" ".join(pars))
    if trib:
        campos.append(trib)
    orgao = processo = None
    vinc = False
    for p in pars:
        mo = _ORGAO.search(p)
        mp = _PROCESSO.search(p)
        if mo and not orgao:
            orgao = _orgao(mo)
        if mp and not processo:
            processo = _processo(mp)
        if (mo or mp) and _VINCULANTE.search(p):
            vinc = True
    if not processo:
        mp = _PROCESSO.search(titulo or "")
        processo = _processo(mp) if mp else None
    campos += [x for x in (orgao, processo) if x]
    if vinc:
        campos.append("vinculante")
    out = " · ".join(campos)
    while len(out) > MAX_FICHA and len(campos) > 1:
        campos.pop(-2 if campos[-1] == "vinculante" and len(campos) > 2 else -1)
        out = " · ".join(campos)
    return out if len(campos) > 1 or (campos and campos[0] != trib) else ""


def nota_oficial(pagina):
    """Orgao cuja comunicacao oficial a materia reproduz ('STF', 'STJ', 'CNJ', 'TRF-3'...), ou ''."""
    for m in _NOTA_OFICIAL.finditer(limpa(pagina or "")):
        quem = (m.group("a") or m.group("b") or "").strip()
        for rx, sigla in _ORGAO_OFICIAL:
            mm = rx.match(quem)
            if mm:
                if sigla:
                    return sigla
                return ("TJ-%s" % mm.group(1)) if len(mm.groups()) == 1 else "%s-%s" % (mm.group(1), mm.group(2))
    return ""


def autor_da_pagina(pagina):
    """Autor(es) do artigo/coluna do ConJur: <p class="assinante-title"> (pode haver mais de um). Nunca o
    <meta name="author">, que e o editor (20/11: 'Marcos Pereira' em todos)."""
    nomes = [limpa(x) for x in re.findall(r'class="assinante-title"[^>]*>(.*?)</p>', pagina or "", re.S)]
    nomes = list(dict.fromkeys(n for n in nomes if n))
    return " e ".join(nomes) if len(nomes) <= 2 else ", ".join(nomes[:-1]) + " e " + nomes[-1]


def enriquecer(it, corpo, fonte):
    """lead, ficha e nota_oficial do item a partir do corpo ja baixado; linha-fina cortada sem paragrafo que a
    complete passa a ser o lead (resumo_origem='lead'), que e o texto verbatim da materia."""
    lead, pars = lead_da_pagina(corpo, fonte)
    if lead:
        it["lead"] = lead
        f = ficha_do_lead(it.get("titulo"), pars)
        if f:
            it["ficha"] = f
    n = nota_oficial(corpo)
    if n:
        it["nota_oficial"] = n
    if it.get("resumo_truncado") and lead and it.get("tipo", "noticia") == "noticia":
        frases = [m.end() for m in FIM_FRASE.finditer(lead) if m.end() <= MAX_COMPLEMENTO]
        if frases:
            it["resumo"], it["resumo_origem"] = lead[:frases[-1]].strip(), "lead"
            it.pop("resumo_truncado", None)


# ------------------------------------------------------------ ConJur
def _pagina_api(url):
    """(http, [posts] | None, tentativas) de uma pagina da WP REST API."""
    cod, t, n = fetch_n(url, timeout=30)
    if cod != 200:
        return cod, None, n
    try:
        d = json.loads(t)
    except ValueError:
        return cod, None, n
    return cod, (d if isinstance(d, list) else None), n


def conjur_api(inicio, fim):
    """{"ok", "posts", "http", "tentativas", "paginas", "completa"} da WP REST API (janela com folga de 6 h nas duas
    pontas: o fuso do 'after'/'before' e o do site; a classificacao exata e pela date_gmt). ok=False: a API nao
    respondeu 200 com uma lista de posts (o coletor cai na listagem HTML)."""
    folga = timedelta(hours=6)
    base = "%s?after=%s&before=%s&per_page=%d&orderby=date&order=desc&_fields=%s" % (
        URL_CONJUR_API, (inicio - folga).strftime("%Y-%m-%dT%H:%M:%S"), (fim + folga).strftime("%Y-%m-%dT%H:%M:%S"),
        POR_PAGINA_CONJUR_API, CAMPOS_CONJUR_API)
    out = {"ok": False, "posts": [], "http": 0, "tentativas": 0, "paginas": 0, "completa": True}
    for pag in range(1, MAX_PAGINAS_CONJUR_API + 1):
        cod, lote, n = _pagina_api(base + ("&page=%d" % pag if pag > 1 else ""))
        if pag == 1:
            out["http"], out["tentativas"] = cod, n
            if lote is None:
                out["motivo"] = "http=%s" % cod if cod != 200 else "resposta nao e lista de posts"
                return out
            out["ok"] = True
        elif lote is None:
            break                       # pagina alem da ultima (400): o que veio basta
        out["posts"] += lote
        out["paginas"] = pag
        if len(lote) < POR_PAGINA_CONJUR_API:
            break
    else:
        out["completa"] = False         # teto com todas as paginas cheias
    return out


def _item_api(p, inicio, fim, recorte):
    """Item do coleta_web a partir de um post da API (None se faltar o essencial)."""
    try:
        url = p["link"]
        quando = datetime.fromisoformat(p["date_gmt"] + "+00:00").astimezone(TZ)
    except (KeyError, TypeError, ValueError):
        return None
    tipo = next((TIPOS_WP[c] for c in p.get("class_list") or [] if c in TIPOS_WP), "noticia")
    titulo = limpa(((p.get("title") or {}).get("rendered")) or "")
    y = p.get("yoast_head_json") or {}
    corpo = ((p.get("content") or {}).get("rendered")) or ""
    it = {"tipo": "noticia" if tipo == "estudio" else tipo, "titulo": titulo, "url": url, "data": quando.date(),
          "quando": quando, "situacao": classifica(quando, inicio, fim, recorte)}
    if tipo == "estudio" and it["situacao"] in ("NOVA", "HERDADA"):
        it["situacao"], it["promo"] = "PROMO", "estudio"
    desc = y.get("og_description") or y.get("description") or ""
    if it["situacao"] in ("NOVA", "HERDADA") and desc:
        it["resumo"], truncado = resumo_da_pagina(corpo, titulo, url, texto=desc)
        if truncado:
            it["resumo_truncado"] = True
    if it["situacao"] in ("NOVA", "HERDADA"):
        enriquecer(it, corpo, "conjur")
    return it


def conjur(inicio, fim, recorte, urls_pub):
    """ConJur pela WP REST API (a janela inteira, com hora exata e corpo); sem ela, a listagem HTML paginada."""
    api = conjur_api(inicio, fim)
    if not api["ok"]:
        out = conjur_html(inicio, fim, recorte, urls_pub)
        out["api"] = {"http": api["http"], "motivo": api.get("motivo", "")}
        return out
    out = {"fonte": "conjur", "via": "api", "http": {"api": api["http"]}, "tentativas": api["tentativas"],
           "paginas": api["paginas"], "itens": [], "completa": api["completa"]}
    vistos, unicos = set(), []
    itens = [x for x in (_item_api(p, inicio, fim, recorte) for p in api["posts"]) if x]
    for it in sorted(itens, key=lambda i: i["quando"], reverse=True):
        if it["url"] in vistos:
            continue
        vistos.add(it["url"])
        if chave_url(it["url"]) in urls_pub:
            it["situacao"] = "JA_PUBLICADA"
        unicos.append(it)
    # noticias primeiro (ids c1.. como antes), depois artigos e colunas; "pagina" = a da listagem de 15
    nots = [i for i in unicos if i["tipo"] == "noticia"]
    for n, it in enumerate(nots):
        it["pagina"] = n // POR_PAGINA_CONJUR + 1
    out["itens"] = nots + [i for i in unicos if i["tipo"] == "artigo"] + [i for i in unicos if i["tipo"] == "coluna"]
    _cobertura(out, inicio, pela_data=False)        # a consulta cobre a janela; so o teto de paginas corta
    autores_opiniao(out)
    return out


def autores_opiniao(out):
    """Autor dos artigos/colunas que vao ao indice (a API nao traz: so o editor): pagina de cada um (<= MAX_OPINIAO)."""
    abrir = [i["url"] for i in opiniao_escolhidas(out["itens"]) if not i.get("autor")]
    for url, (c, p) in fetch_many(abrir).items():
        a = autor_da_pagina(p) if c == 200 else ""
        if a:
            next(i for i in out["itens"] if i["url"] == url)["autor"] = a


def _cobertura(out, inicio, pela_data=True):
    """'mais_antiga' (data/hora da noticia mais antiga lida) e 'cobertura' ('completa'|'parcial'). pela_data: a leitura
    que nao chegou antes do inicio da janela e parcial (listagem paginada); a API ja consulta a janela inteira."""
    datas = [i.get("quando") or i.get("data") for i in out["itens"] if i.get("tipo", "noticia") == "noticia"]
    datas = [d for d in datas if d]
    if datas:
        mais = min(datas, key=lambda d: d if isinstance(d, datetime) else datetime.combine(d, datetime.min.time(), TZ))
        out["mais_antiga"] = mais
        if pela_data and ((isinstance(mais, datetime) and mais > inicio)
                          or (not isinstance(mais, datetime) and mais >= inicio.date())):
            out["completa"] = False
    out["cobertura"] = "completa" if out.get("completa") else "parcial"


def _listagem_conjur(t):
    padrao = re.compile(r'<h2 class="conjur-posts-tipo-titulo"[^>]*>\s*<a href="'
                        r'(https://conjur\.com\.br/(\d{4})-([a-z]{3})-(\d{2})/[^"]+)"[^>]*>(.*?)</a>', re.S)
    return [(url, date(int(a), MESES[mes], int(d)), limpa(tit)) for url, a, mes, d, tit in padrao.findall(t or "")
            if mes in MESES]


def conjur_html(inicio, fim, recorte, urls_pub):
    """Fallback: listagens HTML. Noticias paginadas (ate MAX_PAGINAS_CONJUR, parando no dia anterior ao inicio da
    janela, em pagina sem URL nova ou em http != 200); artigos e colunas: 1a pagina (ja chegam a itens FORA)."""
    pags = fetch_many(list(URLS_CONJUR.values()))
    out = {"fonte": "conjur", "via": "html", "http": {k: pags[u][0] for k, u in URLS_CONJUR.items()},
           "itens": [], "paginas": 1, "completa": False}
    vistos, abrir = {}, []

    def novo(url, dia, tit, tipo, pagina):
        it = {"tipo": tipo, "titulo": tit, "url": url, "data": dia}
        if tipo == "noticia":
            it["pagina"] = pagina
        vistos[url] = it
        # pelo dia; so os dias de borda (inicio, recorte, fim) sao abertos para a hora decidir. Antes todo dia
        # intermediario virava NOVA: na janela de 72h de 16/11, os itens de 14/11 (antes do recorte) sairam NOVA.
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

    for tipo, u in URLS_CONJUR.items():
        lista = _listagem_conjur(pags[u][1]) if pags[u][0] == 200 else []
        for url, dia, tit in lista:
            if url not in vistos:
                novo(url, dia, tit, tipo, 1)
        if tipo != "noticia" or pags[u][0] != 200:
            continue
        pag, ultima = 1, lista
        while ultima and min(d for _, d, _ in ultima) >= inicio.date():
            if pag >= MAX_PAGINAS_CONJUR:
                break                       # teto: completa=False
            pag += 1
            url_p = URL_CONJUR_PG % pag
            cod, t = fetch_many([url_p])[url_p]
            if cod != 200:
                out["http_pagina"] = {"pagina": pag, "http": cod}
                break
            ultima = [x for x in _listagem_conjur(t) if x[0] not in vistos]
            if not ultima:
                out["sem_url_nova"] = pag   # "/page/N/" devolve a 1a: o laco para
                break
            for url, dia, tit in ultima:
                novo(url, dia, tit, "noticia", pag)
            out["paginas"] = pag
        else:
            out["completa"] = bool(lista)    # chegou ao dia anterior ao inicio
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
            pagina = abertas[it["url"]][1]
            # sem propaganda; frase cortada completada pela pagina ou marcada (volta 3)
            it["resumo"], truncado = resumo_da_pagina(pagina, it["titulo"], it["url"])
            if truncado:
                it["resumo_truncado"] = True
            enriquecer(it, pagina, "conjur")
            if it["tipo"] in ("artigo", "coluna"):
                a = autor_da_pagina(pagina)
                if a:
                    it["autor"] = a
    _cobertura(out, inicio)
    if out.get("sem_url_nova") or out.get("http_pagina"):
        out["completa"], out["cobertura"] = False, "parcial"
    return out


# ------------------------------------------------------------ Migalhas
SELO_MIGALHAS = re.compile(r"(\d{1,2})\.([a-z]{3})\.(\d{4})")


def _listagem_migalhas(t):
    lista = []
    for art in (t or "").split("<article")[1:]:
        m = re.search(r'href="(https://www\.migalhas\.com\.br/quentes/\d+/[^"]+)"', art)
        h2 = re.search(r'class="topico__header">(.*?)</h2>', art, re.S)
        if not m or not h2:
            continue
        h3 = re.search(r'class="topico__body">(.*?)</h3>', art, re.S)
        badge = re.search(r'class="badge badge--\w+">([^<]+)<', art)
        it = {"titulo": limpa(h2.group(1)), "resumo": limpa(h3.group(1)) if h3 else "",
              "badge": limpa(badge.group(1)) if badge else "", "url": m.group(1)}
        sd = SELO_MIGALHAS.search(it["badge"].lower())
        if sd and sd.group(2) in MESES:
            it["data"] = date(int(sd.group(3)), MESES[sd.group(2)], int(sd.group(1)))
        lista.append(it)
    return lista


def migalhas(inicio, fim, recorte, urls_pub):
    """Migalhas paginado (?pagina=N, ate MAX_PAGINAS_MIGALHAS), parando no selo de data anterior ao inicio da janela,
    em pagina sem URL nova ou em http != 200. Selo anterior ao dia do inicio = FORA sem abrir; JA_PUBLICADA (URL)
    tambem nao abre; o resto abre (hora exata, linha-fina limpa, lead, ficha) — 8 em paralelo."""
    out = {"fonte": "migalhas", "http": 0, "tentativas": 0, "itens": [], "paginas": 0, "completa": False}
    unicos = {}
    for pag in range(1, MAX_PAGINAS_MIGALHAS + 1):
        cod, t, n_tent = fetch_n(URL_MIGALHAS + ("?pagina=%d" % pag if pag > 1 else ""))
        if pag == 1:
            out["http"], out["tentativas"] = cod, n_tent
        if cod != 200:
            if pag > 1:
                out["http_pagina"] = {"pagina": pag, "http": cod}
            break
        lista = [i for i in _listagem_migalhas(t) if i["url"] not in unicos]
        if not lista:
            if pag > 1:
                out["sem_url_nova"] = pag
            break
        for i in lista:
            i["pagina"] = pag
            unicos[i["url"]] = i
        out["paginas"] = pag
        datas = [i["data"] for i in lista if i.get("data")]
        if datas and min(datas) < inicio.date():
            out["completa"] = True
            break
    abrir = []
    for url, it in unicos.items():
        if chave_url(url) in urls_pub:
            it["situacao"] = "JA_PUBLICADA"
        elif it.get("data") and it["data"] < inicio.date():
            it["situacao"] = "FORA"
        elif it.get("data") and it["data"] > fim.date():
            it["situacao"] = "DEPOIS"
        else:
            abrir.append(url)
    paginas = fetch_many(abrir)
    for url, it in unicos.items():
        if url in paginas:
            pagina = paginas[url][1]
            if it["resumo"]:          # mesma limpeza da linha-fina do ConJur, com a pagina ja baixada (volta 3)
                it["resumo"], truncado = resumo_da_pagina(pagina, it["titulo"], url, texto=it["resumo"])
                if truncado:
                    it["resumo_truncado"] = True
            quando = publicado_em(pagina)
            it["quando"] = quando
            it["situacao"] = classifica(quando, inicio, fim, recorte)
            if it["situacao"] in ("NOVA", "HERDADA"):
                enriquecer(it, pagina, "migalhas")
        out["itens"].append(it)
    _cobertura(out, inicio)
    if out.get("sem_url_nova") or out.get("http_pagina"):
        out["completa"], out["cobertura"] = False, "parcial"
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
                i["situacao"], i["promo"] = "PROMO", "promo"
                continue
            if OPINIAO_DISFARCADA.search(i["titulo"]) and i.get("tipo", "noticia") == "noticia":
                i["situacao"], i["promo"] = "PROMO", "opiniao_disfarcada"
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


def opiniao_escolhidas(itens, maximo=MAX_OPINIAO):
    """Artigos/colunas publicaveis que entram no indice impresso (pelos termos de prova; empate: a ordem da lista)."""
    cand = [(n, i) for n, i in enumerate(itens)
            if i.get("tipo") in ("artigo", "coluna") and i.get("situacao") in ("NOVA", "HERDADA", "SEM_DATA")]
    return [i for _, i in sorted(cand, key=lambda x: (-nota_prova(x[1]["titulo"]), x[0]))[:maximo]]


def opiniao_no_indice(itens, maximo=MAX_OPINIAO):
    """ids dos artigos/colunas publicaveis que entram no indice impresso."""
    return {i["id"] for i in opiniao_escolhidas(itens, maximo)}


# ------------------------------------------------------------ midia no indice (21/11)
# Ordem por relevancia para prova (nao pelo feed), marcas [CONC] (concurso, edital, exame nacional) e [STJ] (julgado do
# STJ: vai em STJ Noticias), a ficha [tribunal · orgao · processo · vinculante], a mesma historia do dia numa linha so
# (20/11: c3, m5, m7, m9 e m10 eram o mesmo julgamento) e, das paginas seguintes a 1a, so o titulo dos que tem termo de
# prova (o resto contado; tudo continua no JSON com id). Nenhum item some: o id fica citavel.
MAX_SEGUINTES_NO_INDICE = 10     # por fonte: noticias das paginas seguintes a 1a (so titulo)
NOTA_MIN_SEGUINTES = 2
MAX_LINHA_FINA_INDICE = 170
MAX_TIT_MESMA = 50
MIN_COMUM_HISTORIA, PROPORCAO_HISTORIA = 4, 0.3
CONC = re.compile(r"\bconcursos?\b|\bedita(?:l|is)\b(?! de (?:licita|leil|chamamento|credenc))|\bexames? nacional|"
                  r"\benac\b|\benam\b|exame de ordem|\binscri[çc][õo]es (?:abertas|para|at[ée]|v[ãa]o)|\bbanca examinadora\b|"
                  r"\bposse de aprovad|\baprovad[oa]s? em concurso", re.I)
STJ_MARCA = re.compile(r"\bSTJ\b|superior tribunal de justi[çc]a", re.I)
FALA = re.compile(r"\b(?:defende[m]?|critica[m]?|afirma[m]?|diz(?:em)?|elogia[m]?|lamenta[m]?|cobra[m]?|palestra|"
                  r"f[óo]rum|semin[áa]rio|congresso|evento|homenage\w*|entrevista|discurso|abertura|celebra\w*)\b", re.I)
DECISAO = re.compile(r"\b(?:decid\w*|decis[ãa]o|mant[ée]m|mantêm|nega[m]?|anula[m]?|condena\w*|absolve\w*|julga\w*|"
                     r"fixa\w*|define\w*|reconhece\w*|vota\w*|suspende\w*|derruba\w*|determina\w*|concede\w*|afasta\w*|"
                     r"valida\w*|invalida\w*|autoriza\w*|pro[íi]be\w*|libera\w*|rejeita\w*|aprova\w*|arquiva\w*|"
                     r"recebe\w*|tese|maioria|liminar|sanciona\w*|promulga\w*|veta\w*|empate)\b", re.I)
LEGISLATIVO = re.compile(r"^(?:Senado|Congresso|C[âa]mara|Plen[áa]rio)\b.{0,45}?\b(?:aprova|conclui|rejeita|derruba|"
                         r"promulga|mant[ée]m|sanciona)\w*", re.I)
GENERICOS_HISTORIA = set("""stf stj tst tse supremo tribunal tribunai ministro ministra ministros justica decisao
julgamento turma corte lei caso processo acao direito juiz juiza colegiado relator relatora voto votos tese nesta
feira quarta quinta sexta segunda terca sabado domingo brasil federal estado sobre apos mas diz pede faz
segundo ainda anos ano dia dias novo nova pode deve""".split())
PUBLICAVEL = ("NOVA", "HERDADA", "SEM_DATA")


def eh_fala(i):
    """Fala, discurso ou evento sem verbo de decisao ('Em Buenos Aires, Salomao defende...')."""
    t = i.get("titulo") or ""
    return bool(FALA.search(t)) and not DECISAO.search(t)


def marcas_midia(i):
    """Marcas curtas da linha: ficha (ou [STJ] quando so o STJ aparece), [CONC], [ASSESSORIA X]."""
    texto = " ".join([i.get("titulo") or "", i.get("resumo") or "", i.get("url") or ""])
    out = []
    ficha = i.get("ficha") or ""
    if ficha:
        out.append("[%s]" % ficha)
    elif STJ_MARCA.search(texto) or "-stj" in (i.get("url") or "").lower() or "stj-" in (i.get("url") or "").lower():
        out.append("[STJ]")
    if CONC.search(i.get("titulo") or "") or CONC.search(i.get("resumo") or ""):
        out.append("[CONC]")
    if i.get("nota_oficial"):
        out.append("[ASSESSORIA %s]" % i["nota_oficial"])
    return out


def nota_noticia(i):
    """nota_prova do titulo + concurso (+3), vinculante (+3), orgao/processo na ficha (+1), comunicacao oficial
    (+1), aprovacao do Legislativo (+2); fala/evento sem decisao (-3)."""
    n = nota_prova(i.get("titulo"))
    if CONC.search(i.get("titulo") or "") or CONC.search(i.get("resumo") or ""):
        n += 3
    ficha = i.get("ficha") or ""
    if "vinculante" in ficha:
        n += 3
    elif ficha.count(" · ") >= 1:
        n += 1
    if i.get("nota_oficial"):
        n += 1
    if LEGISLATIVO.search(i.get("titulo") or ""):
        n += 2
    if eh_fala(i):
        n -= 3
    return n


def _ts(i):
    q = i.get("quando")
    if isinstance(q, datetime):
        return q.timestamp()
    d = i.get("data")
    return datetime.combine(d, datetime.min.time(), TZ).timestamp() if isinstance(d, date) else 0


def preparar_midia(res):
    """nota (relevancia) e a mesma historia do dia (mesma_historia = id do representante; tambem = [ids]) nas
    noticias publicaveis de ConJur e Migalhas. Precisa dos ids ja atribuidos."""
    nots = [i for r in res if r["fonte"] in ("conjur", "migalhas") for i in r["itens"]
            if i.get("id") and i["situacao"] in PUBLICAVEL and i.get("tipo", "noticia") == "noticia"]
    for i in nots:
        i["nota"] = nota_noticia(i)
        i.pop("mesma_historia", None)
        i.pop("tambem", None)
    import repeticao
    tok = [repeticao.tokens("%s %s" % (i.get("titulo") or "", i.get("resumo") or "")) - GENERICOS_HISTORIA
           for i in nots]
    pai = list(range(len(nots)))

    def raiz(x):
        while pai[x] != x:
            pai[x] = pai[pai[x]]
            x = pai[x]
        return x
    for a in range(len(nots)):
        for b in range(a + 1, len(nots)):
            comum = len(tok[a] & tok[b])
            if comum >= MIN_COMUM_HISTORIA and comum / max(1, min(len(tok[a]), len(tok[b]))) >= PROPORCAO_HISTORIA:
                pai[raiz(a)] = raiz(b)
    grupos = {}
    for n in range(len(nots)):
        grupos.setdefault(raiz(n), []).append(nots[n])
    for g in grupos.values():
        if len(g) < 2:
            continue
        # representante: o mais relevante; empate: o da 1a pagina, o mais recente
        g.sort(key=lambda i: (-i["nota"], i.get("pagina", 1), -_ts(i)))
        g[0]["tambem"] = [x["id"] for x in g[1:]]
        for x in g[1:]:
            x["mesma_historia"] = g[0]["id"]


def _linha_noticia(i, com_linha_fina, ids):
    s = i["situacao"]
    marcas = marcas_midia(i)
    extra = ""
    if com_linha_fina and i.get("resumo") and not eh_fala(i):
        extra = " — " + curto(i["resumo"], MAX_LINHA_FINA_INDICE)
        if i.get("resumo_truncado") and not extra.endswith("…"):
            extra += "…"              # linha-fina cortada na fonte (volta 3)
    rep = " [REPETIDA?~%s]" % i["repetida"] if i.get("repetida") else ""
    tambem = ""
    if i.get("tambem"):
        tambem = " (mesma história: %s)" % "; ".join(
            "%s «%s»" % (x, curto(ids[x].get("titulo"), MAX_TIT_MESMA)) for x in i["tambem"] if x in ids)
    return "[%s|NOT] %s | %s | %s%s%s%s%s" % (s, i["id"], hm(i), i["titulo"],
                                              (" " + " ".join(marcas)) if marcas else "", extra, rep, tambem)


def _aviso_cobertura(r, inicio):
    """AVISO de leitura incompleta (teto, pagina repetida, http na pagina seguinte) — vai a verification_notes."""
    if r.get("cobertura") != "parcial" or not ok(r["http"]) or not r.get("itens"):
        return []
    mais = r.get("mais_antiga")
    if isinstance(mais, datetime):
        quando = "a mais antiga lida é de %s, depois do início %s" % (mais.strftime("%d/%m %H:%M"),
                                                                      inicio.strftime("%d/%m %H:%M"))
    elif isinstance(mais, date):
        quando = "a mais antiga lida é de %s, e o início da janela é %s" % (mais.strftime("%d/%m"),
                                                                            inicio.strftime("%d/%m %H:%M"))
    else:
        quando = "sem data na última página"
    motivo = ("http=%s na página %s" % (r["http_pagina"]["http"], r["http_pagina"]["pagina"]) if r.get("http_pagina")
              else "a página %s repetiu a anterior" % r["sem_url_nova"] if r.get("sem_url_nova")
              else "teto de %s página(s)" % r.get("paginas", "?"))
    return ["AVISO: cobertura parcial do %s (%s; %s): pode faltar notícia mais antiga — leve a verification_notes"
            % ("ConJur" if r["fonte"] == "conjur" else "Migalhas", motivo, quando)]


def imprimir_midia(r, ids):
    """Linhas de noticia de ConJur/Migalhas: por relevancia; 1a pagina com a linha-fina, paginas seguintes so o titulo
    dos que tem termo de prova (ate MAX_SEGUINTES_NO_INDICE), mesma historia dobrada no representante."""
    nots = [i for i in r["itens"] if i["situacao"] in PUBLICAVEL and i.get("tipo", "noticia") == "noticia"
            and i.get("id") and not i.get("mesma_historia")]
    nots.sort(key=lambda i: (-i.get("nota", 0), -_ts(i)))
    seguintes = [i for i in nots if i.get("pagina", 1) > 1]
    escolhidos = {i["id"] for i in [x for x in seguintes if x.get("nota", 0) >= NOTA_MIN_SEGUINTES or x.get("tambem")
                                    or CONC.search(x.get("titulo") or "")][:MAX_SEGUINTES_NO_INDICE]}
    out, fora = [], 0
    for i in nots:
        if i.get("pagina", 1) == 1:
            out.append(_linha_noticia(i, True, ids))
        elif i["id"] in escolhidos:
            out.append(_linha_noticia(i, False, ids))
        else:
            fora += 1
    if fora:
        out.append("(+%d notícia(s) das páginas seguintes fora do índice: sem termo de prova no título; continuam no "
                   "JSON e o id vale)" % fora)
    return out

# Atos de rotina no indice (21/11): o mesmo criterio do montar_email.eh_rotina (G7) — credito orcamentario, aumento
# de capital, acordo de turismo/servicos aereos, nunca cooperacao penal. Numa linha so, com os ids: em 20/11 as 13
# leis de credito do PLN ocupavam 13 linhas (~4,5 KB) do indice. O e-mail nao muda: cada ref continua citado e o
# montador poe a ementa inteira no fim da secao.
ROTINA_ATO = re.compile(r"abre\s+aos?\s+or[çc]amentos?|cr[ée]dito\s+(?:suplementar|especial|extraordin[áa]rio)|"
                        r"aumento\s+(?:do|de)\s+capital|\bacordo\b.{0,160}?\b(?:turismo|servi[çc]os\s+a[ée]reos|"
                        r"transporte\s+a[ée]reo)", re.I)
ROTINA_EXCETO = re.compile(r"coopera[çc][ãa]o\s+jur[íi]dica|mat[ée]ria\s+penal|extradi[çc]|transfer[êe]ncia\s+de\s+"
                           r"(?:pessoas\s+)?(?:presos|condenad|apenad)|assist[êe]ncia\s+jur[íi]dica|crime|penal", re.I)


def eh_rotina_ato(ementa):
    return bool(ROTINA_ATO.search(ementa or "")) and not ROTINA_EXCETO.search(ementa or "")


def linhas_rotina(itens, rotulo):
    """'[NOVA] rotina — 13 lei(s) de credito/orcamento (...): lei15531, ... (DOU 19/11)', uma por situacao."""
    out = []
    for sit in ("NOVA", "HERDADA", "SEM_DATA_OFICIAL"):
        g = [i for i in itens if i["situacao"] == sit]
        if not g:
            continue
        dous = sorted({i.get("dou", "")[:5] for i in g if i.get("dou")})
        out.append("[%s] rotina — %d %s de crédito, orçamento ou acordo de rotina (o montador agrupa no fim, com a "
                   "ementa inteira; cite cada ref): %s%s" % (sit, len(g), rotulo, ", ".join(i["id"] for i in g),
                                                             " (DOU %s)" % ", ".join(dous) if dous else ""))
    return out

def imprimir(res, inicio, fim, recorte, ja_saiu=None):
    """Indice compacto (linhas de texto). Atribui os ids (lei15527, mpv1400, dec13173, c7, m3). ja_saiu: linhas
    da repeticao.ja_saiu (Midia e Fofoquinha das 2 ultimas edicoes), impressas no fim."""
    out = ["JANELA %s -> %s (herdada = antes de %s) | cite o id em {\"ref\": ...}; URL, hora e chave "
           "saem do JSON" % (inicio.isoformat(), fim.isoformat(), recorte.strftime("%d/%m %H:%M"))]
    seq = {"conjur": 0, "migalhas": 0}
    for r in res:                     # ids primeiro (a ordem de sempre: os refs nao mudam)
        for i in r["itens"]:
            if r["fonte"] in seq and i["situacao"] in PUBLICAVEL:
                seq[r["fonte"]] += 1
                i["id"] = "%s%d" % (r["fonte"][0], seq[r["fonte"]])
    preparar_midia(res)
    ids = {i["id"]: i for r in res for i in r["itens"] if i.get("id")}
    for r in res:
        itens = r["itens"]
        if r["fonte"] == "camara_noticias":
            out.extend(imprimir_camara(r))
            continue
        if r["fonte"] == "legin":
            out.extend(imprimir_legin(r))
            continue
        cont = {}
        for i in itens:
            cont[i["situacao"]] = cont.get(i["situacao"], 0) + 1
        cab = ""
        if r["fonte"] in ("conjur", "migalhas"):
            cab = " | %s%d pagina(s), cobertura %s" % (
                "via %s%s, " % (r.get("via", ""), " (API: %s)" % (r["api"].get("motivo") or r["api"].get("http"))
                                if r.get("api") else "") if r.get("via") else "",
                r.get("paginas", 1), r.get("cobertura", "completa"))
        out.append("\n== %s http=%s %s%s" % (r["fonte"].upper(), r["http"],
                                             " ".join("%s=%d" % kv for kv in sorted(cont.items())), cab))
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
        out.extend(_aviso_cobertura(r, inicio))
        ja = ["%s %s (%s)" % ("MPV" if r["fonte"] == "congresso_mpv" else i.get("tipo", "Lei"), i["numero"],
                              curto(i["ementa"], 70))
              for i in itens if i["situacao"] == "JA_PUBLICADA" and r["fonte"].startswith("congresso")]
        if ja:
            out.append("JA PUBLICADAS (nao repetir, nem pelo boletim da Camara): " + "; ".join(ja[:6]))
        if r["fonte"] == "congresso_leis":
            rot = []
            for i in itens:
                if i["situacao"] == "JA_PUBLICADA":
                    continue
                i["id"] = "lei%s" % i["numero"]
                if eh_rotina_ato(i["ementa"]) and not i.get("veto"):
                    rot.append(i)
                    continue
                out.append("[%s] %s | %s nº %s de %s (DOU %s) — %s%s | %s" % (
                    i["situacao"], i["id"], i["tipo"], i["numero"], i["data_ato"], i["dou"], i["ementa"],
                    " | veto: " + i["veto"] if i["veto"] else "", i["materia"]))
            out.extend(linhas_rotina(rot, "lei(s)"))
            continue
        if r["fonte"] == "congresso_mpv":
            for i in itens:
                if i["situacao"] == "JA_PUBLICADA":
                    continue
                i["id"] = "mpv%s" % i["numero"]
                out.append("[%s] %s | MPV %s/%s — DOU %s (detalhe oficial, http %s) — %s" % (
                    i["situacao"], i["id"], i["numero"], i["ano"], i["dou"] or "?", i["http_detalhe"], i["ementa"]))
            continue
        out.extend(imprimir_midia(r, ids))
        fora = 0
        if r["fonte"] == "conjur":
            no_indice = opiniao_no_indice(itens)
            for i in itens:
                if i["situacao"] not in PUBLICAVEL or i.get("tipo") not in ("artigo", "coluna"):
                    continue
                # artigo/coluna: so o titulo, encurtado, e o autor (no maximo 6 vao ao e-mail, sem resumo)
                if i["id"] not in no_indice:
                    fora += 1
                    continue
                out.append("[%s|%s] %s | %s | %s%s%s" % (
                    i["situacao"], i["tipo"][:3].upper(), i["id"], hm(i), curto(i["titulo"], MAX_TIT_OPINIAO),
                    " — " + i["autor"] if i.get("autor") else "",
                    " [REPETIDA?~%s]" % i["repetida"] if i.get("repetida") else ""))
        if fora:
            out.append("(+%d artigos/colunas fora do indice: titulos com menos termos de prova; "
                       "continuam no JSON)" % fora)
    if ja_saiu:
        out.append("\n== JA SAIU (Mídia e Fofoquinha das 2 últimas edições: o mesmo fato, mesmo com outro título, só "
                   "volta como desdobramento dito no título; com desfecho oficial, vira uma frase do item oficial)")
        out.extend(ja_saiu)
    return out


def imprimir_legin(r):
    """Bloco do LEGIN no indice; atribui os ids (dec13173, lc239, ec141, dleg123; lei/mpv quando o Congresso nao
    listou). Rotina (credito, acordo de turismo...) numa linha so."""
    pub = [i for i in r["itens"] if i["situacao"] in ("NOVA", "HERDADA", "SEM_DATA_OFICIAL")]
    out = ["\n== LEGIN (Câmara, Legislação Informatizada: decretos e demais atos do DOU antes da resenha PUSH; "
           "selo OFICIAL ALTERNATIVA; a mesma norma na PLANALTO_ATO é um item só) http=%s listadas=%d%s%s" % (
               r["http"], r.get("listadas", 0), " mais_recente=%s" % r["mais_recente"] if r.get("mais_recente") else "",
               " leis/MPVs com o Congresso=%d" % r["no_congresso"] if r.get("no_congresso") else "")]
    if r.get("erro") or r["http"] != 200 or not r.get("listadas"):
        out.append("ERRO: LEGIN nao lido (%s) — atos do Executivo so pela resenha PUSH; sem WebSearch"
                   % (r.get("erro") or ("http=%s" % r["http"] if r["http"] != 200 else "0 normas extraidas (layout?)")))
        return out
    if r.get("ja_publicadas"):
        out.append("JA PUBLICADOS (nao repetir, nem pela resenha PUSH): " + "; ".join(r["ja_publicadas"][:6]))
    rot = []
    for i in pub:
        i["id"] = "%s%s" % (i["prefixo"], i["numero"])
        if eh_rotina_ato(i["ementa"]):
            rot.append(i)
            continue
        out.append("[%s] %s | %s nº %s de %s (DOU %s%s) — %s%s" % (
            i["situacao"], i["id"], i["tipo"], i["numero"], i["data_ato"], (i["dou"] or "?")[:5],
            " · edição extra" if i.get("extra") else "", "«%s» " % i["apelido"] if i.get("apelido") else "",
            i["ementa"]))
    out.extend(linhas_rotina(rot, "ato(s)"))
    if not pub:
        out.append("NENHUM ATO FORA DO CONGRESSO E DO HISTORICO entre as %d normas listadas (o DOU de hoje pode ainda "
                   "nao estar indexado: nunca escreva \"sem ato novo\") — fonte ok" % r.get("listadas", 0))
    return out


def imprimir_camara(r):
    """Bloco da Agencia Camara no indice; atribui os ids cam1, cam2... aos itens publicaveis."""
    pub = [i for i in r["itens"] if i["situacao"] in ("NOVA", "HERDADA")]
    ja = sum(1 for i in r["itens"] if i["situacao"] == "JA_PUBLICADA")
    out = ["\n== AGENCIA CAMARA (site; a mesma noticia do boletim por e-mail e UM item so, pelo ref) http=%s "
           "paginas=%d na_janela=%d LEI/PLENARIO=%d%s" % (r["http"], r.get("paginas", 0), r.get("na_janela", 0), len(pub),
                                                        " JA_PUBLICADA=%d" % ja if ja else "")]
    if r.get("erro") or r["http"] != 200 or not r.get("lidas"):
        out.append("ERRO: Agencia Camara nao lida no site (%s) — valem as linhas CAMARA do coletor Gmail (boletim); "
                   "sem WebSearch" % (r.get("erro") or ("http=%s" % r["http"] if r["http"] != 200
                                                        else "pagina lida, 0 noticias extraidas (layout?)")))
        return out
    for n, i in enumerate(pub, 1):
        i["id"] = "cam%d" % n
        out.append("[%s|%s] %s | %s | %s%s" % (i["situacao"], i["marca"], i["id"], hm(i), i["titulo"],
                                               " — " + i["retranca"] if i.get("retranca") else ""))
    if not pub:
        out.append("SEM [LEI]/[PLENARIO] NA JANELA: %d noticia(s) lida(s) (comissoes, projetos, debates) — fonte ok"
                   % r["na_janela"])
    if r.get("resto"):
        duv = r.get("duvidosos") or []
        out.append("(+%d noticia(s) sem [LEI]/[PLENARIO]; titulos com \"Plenario\", \"sanciona\", \"promulga\", \"veto\" "
                   "ou \"medida provisoria\" nao marcados: %s)" % (r["resto"], "; ".join(duv[:8]) if duv else "nenhum"))
    if not r.get("completa"):
        out.append("AVISO: a leitura parou antes do inicio da janela (%d paginas%s): pode faltar noticia mais antiga"
                   % (r.get("paginas", 0), ", http=%s na pagina %s" % (r["http_pagina"]["http"], r["http_pagina"]["pagina"])
                      if r.get("http_pagina") else ""))
    return out


# ------------------------------------------------------------ status das fontes
def _entre_parenteses(s):
    return " (%s)" % s if s else ""


def status_fontes(res):
    """{id do source_status: (status, detalhe)} das 5 fontes deste script."""
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
    r = por.get("camara_noticias")
    if r:
        if r.get("erro"):
            st["camara_noticias"] = ("falha", r["erro"][:120])
        elif r["http"] != 200:
            st["camara_noticias"] = ("falha", "http=%s%s" % (r["http"], _entre_parenteses(tentativas_txt(r))))
        elif not r.get("lidas"):
            st["camara_noticias"] = ("falha", "pagina lida, 0 noticias extraidas (layout?)")
        else:
            st["camara_noticias"] = ("ok", "%d [LEI]/[PLENARIO] em %d noticia(s) da janela%s" % (
                sum(1 for i in r["itens"] if i["situacao"] != "JA_PUBLICADA"), r.get("na_janela", 0),
                "" if r.get("completa") else "; leitura incompleta"))
    r = por.get("legin")
    if r:
        if r.get("erro"):
            st["camara_legin"] = ("falha", r["erro"][:120])
        elif r["http"] != 200:
            st["camara_legin"] = ("falha", "http=%s%s" % (r["http"], _entre_parenteses(tentativas_txt(r))))
        elif not r.get("listadas"):
            st["camara_legin"] = ("falha", "pagina lida, 0 normas extraidas (layout?)")
        else:
            st["camara_legin"] = ("ok", "%d ato(s) fora do Congresso e do historico em %d normas listadas" % (
                sum(1 for i in r["itens"] if i["situacao"] != "JA_PUBLICADA"), r["listadas"]))
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
            det = "%d publicaveis" % pub
            if r.get("via") == "html" and r.get("api"):
                det += "; via listagem HTML (API: %s)" % (r["api"].get("motivo") or r["api"].get("http"))
            if r.get("cobertura") == "parcial":
                # status fica "ok" (a lista fechada do source_status nao tem "parcial"); o detalhe e o AVISO dizem
                det += "; parcial: leitura incompleta (%d pagina(s); mais antiga %s > inicio)" % (
                    r.get("paginas", 0), _hm_ou_dia(r.get("mais_antiga")))
            st[fonte] = ("ok", det)
    return st


def _hm_ou_dia(x):
    if isinstance(x, datetime):
        return x.strftime("%d/%m %H:%M")
    if isinstance(x, date):
        return x.strftime("%d/%m")
    return "?"


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


def _resultado(fut):
    try:
        return fut.result()
    except Exception:  # noqa: BLE001
        return {"fonte": "", "itens": []}


def listados_congresso(blocos):
    """{(tipo canonico, numero)} das leis e MPVs que as paginas do Congresso listaram nesta execucao."""
    import repeticao
    out = set()
    for r in blocos:
        for i in r.get("itens") or []:
            if r.get("fonte") == "congresso_leis":
                out.add((repeticao.tipo_canonico(re.sub(r"\s+", "-", i["tipo"].lower())), i["numero"].lstrip("0")))
            elif r.get("fonte") == "congresso_mpv":
                out.add(("mpv", i["numero"].lstrip("0")))
    return out


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

    with ThreadPoolExecutor(max_workers=6) as ex:
        fl = ex.submit(leis, inicio, fim, recorte, atos_pub)
        fm = ex.submit(mpvs, inicio, fim, recorte, atos_pub)
        fa = ex.submit(camara_seguro, inicio, fim, recorte, urls_pub)
        fc = ex.submit(conjur, inicio, fim, recorte, urls_pub)
        fg = ex.submit(migalhas, inicio, fim, recorte, urls_pub)
        # o LEGIN deixa com o Congresso as leis e MPVs que ele listou (espera as duas listas, ja em andamento)
        fn = ex.submit(legin_seguro, inicio, fim, recorte, atos_pub,
                       lambda: listados_congresso([_resultado(fl), _resultado(fm)]))
        res = [fl.result(), fm.result(), fn.result(), fa.result(), fc.result(), fg.result()]

    marcar_promo_e_repetidas(res, historico)
    import repeticao
    for linha in imprimir(res, inicio, fim, recorte,
                          ja_saiu=repeticao.ja_saiu(historico, ignorar_exec_id=IGNORAR_EXEC or None)):
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
