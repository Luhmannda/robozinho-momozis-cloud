#!/usr/bin/env python3
# =====================================================================
# bancas.py — leitura deterministica da BANCA OFICIAL dos concursos
# juridicos (sem tokens). Cobre a FGV (conhecimento.fgv.br), que esta no
# allowlist e publica em HTML simples: listagem dos concursos, situacao e
# "Arquivos do concurso" (edital, retificacoes, resultados, com data).
# Cebraspe: www.cebraspe.org.br/concursos e uma SPA (so "habilite o
# javascript"); os dados vem de apis.cebraspe.org.br (JSON) e os arquivos de
# cdn.cebraspe.org.br, os dois recusados pela rede do ambiente (CONNECT 403).
# FCC e Vunesp tambem estao bloqueadas pela rede.
#
# Por que: em 11/11/2026 o registro tinha TJAP, TJSC, TJRS, TRF5 e TJPB
# como "so fonte secundaria / PENDENCIA DE VERIFICACAO" enquanto a pagina
# oficial da banca, legivel daqui, trazia edital, retificacao e datas.
# Em 16/11/2026 o script escondeu a 2a Retificacao do TJAP (prorrogou as
# inscricoes ate 18/11) e a edicao disse "encerradas": (1) arquivo novo era
# "data > verificado_em", e a FGV publicou depois da verificacao, no mesmo
# dia; (2) o "(retificado em 13/11/2026)" do titulo do edital era ignorado;
# (3) o edital nao era relido com o registro "confirmado". Agora:
#   - data efetiva de cada arquivo = max(data da linha, "retificado em");
#   - NOVO = arquivo (URL) ainda nao visto. As URLs vistas ficam em
#     work/concursos-estado.json, gravado pelo helper (Update-Historico.py,
#     so quando a execucao e registrada) e commitado pelo finalizar.sh. Sem
#     estado para o concurso (1a vez): o arquivo com data efetiva ANTERIOR ao
#     verificado_em do registro conta como visto; o do proprio dia do
#     verificado_em continua novo (a FGV publica depois da execucao das 7h:
#     2a Retificacao do TJAP em 13/11, Edital 0056/2026-DMAG do TJRS em 16/11);
#   - o edital e relido quando ha arquivo novo de retificacao/prorrogacao/
#     edital, ou prazo do registro entre -3 e +7 dias (alem dos casos de
#     antes: concurso sem registro ou registro sem confirmacao oficial);
#     retificacao posterior ao edital consolidado tambem e lida (trecho
#     "LEIA-SE" das inscricoes);
#   - "DIVERGE DO REGISTRO" quando o fim das inscricoes do edital difere do
#     registro (prazos ou, sem prazo, a linha).
#
# LISTAGEM (21/11/2026): /concursos tem duas views Drupal no mesmo ?page=N,
# "concursos_em_andamento" (~130 itens, 20 por pagina, os mais novos antes) e
# "concursos_realizados". Antes so se lia a 1a pagina e so href /concursos/
# com ano 25/26 no slug: dperj2026, trf1juiz25, tjpe26, /juiztjba e o ENAM
# (/exames/enam/6exame) ficavam invisiveis. Agora le-se so o bloco da view em
# andamento, paginado (lotes de ?page em paralelo ate a 1a pagina sem linhas),
# aceitando todo href pt-br do bloco, sem filtro de ano (a FGV ja os marca em
# andamento). slug = caminho sem a "/" inicial e sem "concursos/": tjap26,
# juiztjba, exames/enam/6exame.
# Paginas lidas (GETs em paralelo, teto de threads e de tempo; a falha de uma
# nao derruba as outras): titulo JURIDICO, menos "fora de carreira" (processo
# seletivo, juiz leigo, conciliador, cartorio, tribunal de contas: sem bloco no
# registro) e quadro de apoio fora do escopo regional (escopo.py: so SP, RJ, MG,
# ES, PR, SC, RS ou orgao nacional), que ficam so na contagem; a pagina de
# registro com banca_slug e lida sempre, mesmo fora da listagem e mesmo com a
# listagem fora do ar ou ilegivel (200 sem o bloco da view: `erro` diz o que
# houve; http = 200 se alguma pagina respondeu).
#
# VINCULO pagina -> registro (concursos[] do ledger); so o vinculo cobre
# (carimbo verificado_em/fonte/dominio_oficial, selo por data e DIVERGE):
#   - `banca_slug` do registro == slug (gravado em ledger_updates.concursos);
#   - sem banca_slug: `fonte`/`url_oficial` do registro = a pagina ou um arquivo
#     dela, sem cargo contrario no slug/titulo (vinculo "pela fonte": rede de
#     seguranca da transicao e do registro novo gravado sem banca_slug);
#   - duas paginas vinculadas pela fonte ao mesmo registro: nenhuma cobre
#     (`incerto` + AVISO). Com banca_slug isso nao acontece (slug unico).
# Sem vinculo, organizacao normalizada (id sem cargo e sem "_": dpe_rj -> dperj,
# tjpb_apoio -> tjpb; slug sem ano e sem cargo: dperj2026 -> dperj) + cargo
# (slug/titulo; sem cargo, o edital decide entre os registros da organizacao):
#   - registro sem vinculo: CANDIDATO (1 linha pronta para o orquestrador gravar
#     banca_slug; nao cobre). Travas de ciclo: ordinal do titulo/edital diferente
#     do da linha do registro (XXXIX x XL), slug do ano seguinte (SEM REGISTRO,
#     ciclo seguinte) ou de 2+ anos antes, registro EM PLANEJAMENTO x edital de
#     abertura com mais de PLANEJAMENTO_DIAS, exame que nao e a edicao mais nova
#     listada: outra edicao, nao candidato;
#   - registro ja vinculado a outra pagina: ciclo maior (tjscjuiz27, 7exame; ou
#     qualquer ano, salvo 2+ anos antes, se o slug vinculado nao tem ano: trf2juiz
#     -> trf2juiz27) = NOVA EDICAO?; senao, edicao anterior (contagem);
#   - outro cargo do mesmo orgao: SEM REGISTRO (da mesma sigla, e de outro cargo).
# Pagina sem registro (e sem candidato): aparece so com arquivo NAO visto dos
# ultimos JANELA_MOVIMENTO dias — completa, com o edital, se a abertura e recente
# (SEM REGISTRO → avalie como NOVO), senao 1 linha MOVIMENTO; o resto e contagem.
# ENAM (exames/enam/<n>exame) sem registro enam: a edicao mais nova sai como
# CANDIDATO a registro NOVO.
#
# Funcoes usadas por outros scripts (mesmo JSON de $ROBOZINHO_TMP/bancas.json):
#   carimbos(res, concursos, hoje, upd=None) -> {id: {verificado_em, fonte?, dominio_oficial?}}
#   contexto_selos(res, concursos=None, hoje=None, upd=None)
#                                   -> {id: {banca_lida_hoje, ultima_retificacao, inicio_inscricoes}}
#     (com upd/concursos: o registro que ainda DIVERGE DO REGISTRO fica sem carimbo e sem "banca lida")
#   divergencias_pendentes(res, concursos, hoje, upd=None)
#                                   -> {id: {edital, registro, fim_edital, fim_registro, escrito_hoje}}
#     (todo concurso com o trecho de inscricoes lido HOJE, inscricoes_do_dia; inclui o prazo escrito hoje que
#     contradiz o edital — antes so o registro que ja divergia de manha)
#   selo_do_dia(reg, hoje, ctx, pendentes) -> (selo, motivo, suspenso): a regra unica do selo por data para
#     helper, montador e inicio; com divergencia pendente o selo por data fica SUSPENSO (aviso acionavel)
#   novos_por_registro(res)         -> {id: [arquivos novos]}
#   atualizar_estado(estado, res)   -> quantos arquivos passaram a "vistos" (pagina sem registro: so os
#                                      recentes, entrada `parcial`)
#
# USO:   python3 work/bancas.py [--janela $ROBOZINHO_TMP/janela.json]   (o inicio.py chama coletar())
# SAIDA: bloco compacto em stdout; JSON em $ROBOZINHO_TMP/bancas.json.
# =====================================================================

import argparse
import html
import json
import os
import re
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import date, datetime, timedelta

import escopo
import selos

AQUI = os.path.dirname(os.path.abspath(__file__))
UA = "Mozilla/5.0 (X11; Linux x86_64) Robozinho/1.0"
BANCA_ID = "fgv"
DOMINIO = "conhecimento.fgv.br"
BASE = "https://" + DOMINIO
ESTADO_PADRAO = os.path.join(AQUI, "concursos-estado.json")
JURIDICO = re.compile(r"Tribunal|Juiz|Magistratura|Procurador|Defensor|Minist[ée]rio P[úu]blico|"
                      r"Assembleia Legislativa|Advocacia|Promotor", re.I)
# juridico mas fora das carreiras acompanhadas (os 11 blocos; tribunal de contas nao tem bloco): so contagem, sem
# GET. Vale no titulo e no slug (tjrnnotarial: o titulo so diz "Tribunal de Justica do Estado do Rio Grande do Norte")
FORA_CARREIRA = re.compile(r"^Processo Seletivo|Ju[íi]z(?:es)? Leigos?|Conciliador|Notarial|Cart[óo]rio|"
                           r"Tribunal de Contas", re.I)
FORA_CARREIRA_SLUG = re.compile(r"notarial|cartorio|leigo|conciliador|^tce|^tcm")


def fora_de_carreira(c):
    return bool(FORA_CARREIRA.search(c.get("titulo") or "") or FORA_CARREIRA_SLUG.search(norm_slug(c.get("slug"))))
SUFIXOS = re.compile(r"(juiz|magistratura|servidor(es)?|analista|tecnico|promotor|defensor|procurador)$")
MES = "janeiro|fevereiro|março|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro"
MESES = {m: i + 1 for i, m in enumerate(MES.split("|"))}
DATA = r"\d{1,2}º?\s+de\s+(?:%s)\s+de\s+\d{4}" % MES
TRECHOS = [  # (rotulo, regex sobre o edital com espacos normalizados)
    ("vagas", r"provimento de \d+ \([^)]{1,40}\) vagas[^.;]{0,90}"),
    ("inscrições", r"das? \d{1,2}h(?:\d{2})?(?:min)? do dia %s at[ée] [àa]s \d{1,2}h(?:\d{2})?(?:min)? do dia %s" % (DATA, DATA)),
    ("taxa", r"taxa de inscrição[^.]{0,90}?R\$\s?[\d.]+,\d{2}"),
    ("remuneração", r"(?:subs[íi]dio|remuneração)[^.]{0,110}?R\$\s?[\d.]+,\d{2}"),
    ("prova objetiva", r"[Pp]rova [Oo]bjetiva[^.]{0,140}?%s" % DATA),
]
# alternativas, so quando o padrao principal do rotulo nao casa (a saida dos editais que ja casavam, TJSC e TJAP,
# fica igual): edital de apoio (TJPB: "provimento de 50 (cinquenta) cargos", "VENCIMENTO: R$ 7.526,14", "... serão
# realizadas no dia 24 de janeiro de 2027, das 13h às 18h") e ENAM ("será realizada na data provável de 29 de ...")
TRECHOS_ALT = {
    "vagas": r"provimento de \d+ \([^)]{1,40}\) cargos[^.;]{0,90}",
    "remuneração": r"VENCIMENTO:?\s*R\$\s?[\d.]+,\d{2}",
    "prova objetiva": r"[^.;]{0,90}ser(?:[ãa]o|á) realizadas?,? (?:no dia|na data prov[áa]vel de) %s"
                      r"(?:,? (?:com duração de \d+h, )?das \d{1,2}h às \d{1,2}h)?" % DATA,
}
RE_RETIFICADO = re.compile(r"\((?:retificad[oa]|atualizad[oa]|consolidad[oa])\s+em\s+(\d{2})/(\d{2})/(\d{4})\)", re.I)
RE_RETIFICACAO = re.compile(r"retifica|prorroga|errata", re.I)
RE_RELEITURA = re.compile(r"retifica|prorroga|errata|\bedital\b", re.I)
MARGEM_SEM_ESTADO = 0        # sem estado: data efetiva >= verificado_em - N dias e novo (0 = so o dia dele e depois)
PRAZO_RELEITURA = (-3, 7)    # prazo do registro nesta faixa (dias) -> reler o edital
# rede (21/11/2026: listagem ~0,4-1 s por pagina; pagina de concurso 0,4-1 s; PDF 0,5-0,8 s)
THREADS = 8                  # GETs simultaneos na FGV (listagem e paginas)
THREADS_PDF = 4
TIMEOUT_PAGINA = 20          # curl -m de cada pagina (listagem e concurso)
TETO_LISTAGEM_S = 30         # teto de tempo de cada lote da listagem
TETO_PAGINAS_S = 45          # teto de tempo das paginas dos concursos (o que nao chegou: "nao lida")
TETO_EDITAIS_S = 75          # teto de tempo da leitura dos editais (PDF)
LISTAGEM_LOTE = 8            # ?page=0..7 num lote; outro lote so se a ultima pagina ainda tinha linhas
LISTAGEM_MAX = 24
JANELA_MOVIMENTO = 7         # dias: arquivo nao visto ate N dias atras = movimento (pagina sem registro)
JANELA_ABERTURA = 60         # dias: edital de abertura ate N dias atras = concurso novo (le o edital)
PLANEJAMENTO_DIAS = 120      # registro EM PLANEJAMENTO nao e candidato de pagina com edital mais velho que isso
EXAMES_REGISTRO = {"enam": "Magistratura Estadual"}    # exames/<org>/... sem registro <org>: candidato a NOVO


def tmp(nome):
    return os.path.join(os.environ.get("ROBOZINHO_TMP", "/tmp"), nome)


def fetch(url, binario=False, timeout=40):
    with tempfile.NamedTemporaryFile(delete=False) as f:
        caminho = f.name
    try:
        r = subprocess.run(["curl", "-sL", "-m", str(timeout), "-A", UA, "-o", caminho, "-w", "%{http_code}", url],
                           capture_output=True, timeout=timeout + 5)
        codigo = int(r.stdout.decode().strip() or 0)
        dados = open(caminho, "rb").read()
        return codigo, dados if binario else dados.decode("utf-8", "replace")
    except Exception:
        return 0, b"" if binario else ""
    finally:
        os.unlink(caminho)


def paralelo(fn, itens, threads, teto):
    """[fn(x) | None] na ordem de `itens`. None = excecao ou nao terminou dentro de `teto` segundos (o que ficou
    rodando acaba sozinho no -m do curl e o resultado e descartado): a falha de um nao derruba os outros."""
    itens = list(itens)
    if not itens:
        return []
    ex = ThreadPoolExecutor(max_workers=max(1, min(threads, len(itens))))
    futs = [ex.submit(fn, x) for x in itens]
    wait(futs, timeout=teto)
    out = [f.result() if f.done() and not f.cancelled() and f.exception() is None else None for f in futs]
    ex.shutdown(wait=False, cancel_futures=True)
    return out


def limpa(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


# ------------------------------------------------------------------ listagem
def norm_slug(s):
    """Slug da FGV a partir do caminho, da URL ou do banca_slug: '/concursos/tjap26' -> 'tjap26';
    '/juiztjba' -> 'juiztjba'; '/exames/enam/6exame' -> 'exames/enam/6exame'."""
    s = str(s or "").strip()
    if s.lower().startswith(("http://", "https://")):
        s = re.sub(r"^https?://[^/]+", "", s)
    s = s.split("#")[0].split("?")[0].strip("/").lower()
    return s[len("concursos/"):] if s.startswith("concursos/") else s


def url_de_slug(slug):
    """URL da pagina de um slug fora da listagem: com '/', na raiz; senao em /concursos/ (alternativa: raiz)."""
    return BASE + ("/" if "/" in slug else "/concursos/") + slug


def itens_em_andamento(t):
    """[{slug, titulo, url}] do bloco da view 'concursos_em_andamento' de uma pagina da listagem (todo href pt-br:
    /concursos/x, /juiztjba, /exames/enam/6exame); None sem o bloco (pagina com erro)."""
    i = (t or "").find("view-id-concursos_em_andamento")
    if i < 0:
        return None
    j = t.find("view-id-concursos_realizados", i)
    j = j if j > 0 else t.find("view-id-", i + 30)
    bloco = t[i:j if j > 0 else len(t)]
    out = []
    for attrs, x in re.findall(r"<a\s([^>]*)>(.*?)</a>", bloco, flags=re.S | re.I):
        m = re.search(r'href="([^"]+)"', attrs)
        if not m or 'hreflang="pt-br"' not in attrs:
            continue
        u = html.unescape(m.group(1))
        if u.startswith(BASE):
            u = u[len(BASE):]
        if not u.startswith("/") or u.startswith("//"):
            continue
        slug, titulo = norm_slug(u), limpa(x)
        if slug and titulo:
            out.append({"slug": slug, "titulo": titulo, "url": BASE + "/" + u.split("#")[0].split("?")[0].strip("/")})
    return out


def listagem(buscar=None):
    """(http, [itens], [paginas da listagem com falha]). Lotes de LISTAGEM_LOTE paginas em paralelo ate a 1a pagina
    com o bloco vazio. http = 200 quando ao menos uma pagina trouxe o bloco."""
    buscar = buscar or fetch
    itens, vistos, falhas, http0, algum = [], set(), [], 0, False
    inicio = 0
    while inicio < LISTAGEM_MAX:
        lote = list(range(inicio, min(inicio + LISTAGEM_LOTE, LISTAGEM_MAX)))
        rs = paralelo(lambda p: buscar(BASE + "/concursos" + ("?page=%d" % p if p else ""), timeout=TIMEOUT_PAGINA),
                      lote, THREADS, TETO_LISTAGEM_S)
        fim, lote_ok = False, False
        for p, r in zip(lote, rs):
            codigo, t = r if r else (0, "")
            if p == 0:
                http0 = codigo
            achados = itens_em_andamento(t) if codigo == 200 else None
            if achados is None:
                falhas.append(p)
                continue
            algum = lote_ok = True
            if not achados:
                fim = True
                break
            for it in achados:
                if it["slug"] not in vistos:
                    vistos.add(it["slug"])
                    itens.append(it)
        if fim or not lote_ok:
            break
        inicio += LISTAGEM_LOTE
    return (200 if algum else http0), itens, falhas


# ------------------------------------------------------------------ pagina do concurso
def data_efetiva(a):
    """max(data da linha, data do "(retificado em DD/MM/AAAA)" do titulo)."""
    d = a.get("data") or ""
    m = RE_RETIFICADO.search(a.get("titulo") or "")
    if m:
        d = max(d, "%s-%s-%s" % (m.group(3), m.group(2), m.group(1)))
    return d


def chave_arquivo(a):
    """Identidade do arquivo: a URL (a FGV repete titulos no mesmo dia); sem URL, data|titulo."""
    return a.get("url") or "%s|%s" % (a.get("data"), a.get("titulo"))


def analisar_pagina(c, t):
    """Situacao e arquivos (data, data_efetiva, titulo, url) a partir do HTML da pagina do concurso; titulo do
    <h1> quando a listagem nao o deu (pagina de registro fora da listagem)."""
    corpo = re.sub(r"(?is)<(script|style|nav|footer|header).*?</\1>", " ", t)
    m = re.search(r"(?is)<main.*?</main>", corpo)
    corpo = m.group(0) if m else corpo
    if not c.get("titulo"):
        h = re.search(r"(?is)<h1[^>]*>(.*?)</h1>", corpo)
        c["titulo"] = limpa(h.group(1)) if h else ""
    sit = re.search(r"(Em Andamento|Encerrado|Inscri[çc][õo]es Abertas|Homologado|Suspenso)", limpa(corpo[:6000]), re.I)
    c["situacao"] = sit.group(1) if sit else ""
    links = {limpa(x): (u if u.startswith("http") else BASE + u)
             for u, x in re.findall(r'href="([^"]+\.pdf[^"]*)"[^>]*>(.*?)</a>', corpo, flags=re.S)}
    txt = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</tr>|</h\d>|</span>|</a>", "\n", corpo)
    linhas = [l for l in (limpa(x) for x in txt.split("\n")) if l]
    arquivos = []
    for n, l in enumerate(linhas[:-1]):
        if re.fullmatch(r"\d{2}/\d{2}/\d{4}", l):
            titulo = linhas[n + 1]
            a = {"data": datetime.strptime(l, "%d/%m/%Y").date().isoformat(), "titulo": titulo,
                 "url": links.get(titulo, "")}
            a["data_efetiva"] = data_efetiva(a)
            arquivos.append(a)
    c["arquivos"] = arquivos
    return c


def pagina(c, buscar=None):
    """Copia de `c` com http, situacao e arquivos (nao muda `c`: roda em thread com teto de tempo). Pagina de
    registro fora da listagem: tenta /concursos/<slug> e, sem 200, /<slug>."""
    buscar = buscar or fetch
    novo = dict(c)
    codigo, t = buscar(novo["url"], timeout=TIMEOUT_PAGINA)
    if codigo != 200 and novo.get("url_alt"):
        codigo2, t2 = buscar(novo["url_alt"], timeout=TIMEOUT_PAGINA)
        if codigo2 == 200:
            codigo, t, novo["url"] = codigo2, t2, novo["url_alt"]
    novo["http"] = codigo
    return analisar_pagina(novo, t if codigo == 200 else "")


# ------------------------------------------------------------------ edital (PDF)
def texto_pdf(url):
    """(texto com espacos normalizados | None, erro)."""
    codigo, dados = fetch(url, binario=True, timeout=60)
    if codigo != 200 or not dados.startswith(b"%PDF"):
        return None, "http %s" % codigo
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(dados)
        caminho = f.name
    try:
        t = subprocess.run(["pdftotext", "-l", "40", caminho, "-"], capture_output=True,
                           timeout=60).stdout.decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        return None, "pdftotext: %s" % e
    finally:
        os.unlink(caminho)
    return re.sub(r"\s+", " ", t), ""


def trechos(t):
    out = {}
    for rotulo, padrao in TRECHOS:
        m = re.search(padrao, t)
        if not m and rotulo in TRECHOS_ALT:
            m = re.search(TRECHOS_ALT[rotulo], t)
        if m:
            out[rotulo] = m.group(0).strip()[:230]
    return out


def trecho_leia_se(t):
    """Ultimo trecho de inscricoes dentro de um bloco LEIA-SE (retificacao do tipo 'onde se le / leia-se')."""
    achado = None
    for bloco in re.split(r"LEIA-SE", t, flags=re.I)[1:]:
        bloco = re.split(r"ONDE SE L", bloco, flags=re.I)[0]
        for m in re.finditer(TRECHOS[1][1], bloco):
            achado = m.group(0).strip()[:230]
    return achado


def datas_trecho(trecho):
    """[date, ...] das datas por extenso do trecho, na ordem."""
    out = []
    for m in re.finditer(r"(\d{1,2})º?\s+de\s+(%s)\s+de\s+(\d{4})" % MES, trecho or ""):
        try:
            out.append(date(int(m.group(3)), MESES[m.group(2)], int(m.group(1))))
        except ValueError:
            pass
    return out


def ler_edital(c, ler=texto_pdf):
    """{campos} do edital de abertura (PDF da banca) e, se houver retificacao posterior ao texto consolidado, do
    trecho de inscricoes do LEIA-SE dela: edital_url, edital, retificacao_inscricoes, inscricoes | edital_erro.
    Nao muda `c` (roda em thread com teto de tempo)."""
    out = {}
    alvo = next((a for a in reversed(c["arquivos"]) if a["titulo"].lower().startswith("edital") and a["url"]), None)
    if not alvo:
        return out
    t, erro = ler(alvo["url"])
    if t is None:
        return {"edital_erro": erro}
    out["edital_url"] = alvo["url"]
    out["edital"] = trechos(t)
    consolidado = data_efetiva(alvo) if RE_RETIFICADO.search(alvo["titulo"]) else ""
    rets = [a for a in c["arquivos"] if RE_RETIFICACAO.search(a["titulo"]) and a["url"]
            and not a["titulo"].lower().startswith("edital") and a.get("data_efetiva", a["data"]) > consolidado]
    if rets:
        ult = max(rets, key=lambda a: a.get("data_efetiva", a["data"]))
        tr, erro = ler(ult["url"])
        if tr is not None:
            achado = trecho_leia_se(tr)
            if achado:
                out["retificacao_inscricoes"] = {"titulo": ult["titulo"], "data": ult["data"], "url": ult["url"],
                                                 "trecho": achado}
    ins = (out.get("retificacao_inscricoes") or {}).get("trecho") or out["edital"].get("inscrições")
    ds = datas_trecho(ins)
    if ds:
        out["inscricoes"] = {"inicio": ds[0].isoformat(), "fim": ds[-1].isoformat(), "trecho": ins,
                             "origem": "retificação" if out.get("retificacao_inscricoes") else "edital"}
    return out


def edital(c, ler=texto_pdf):
    """Grava em `c` os trechos copiados do edital de abertura e do LEIA-SE da retificacao posterior (ler_edital)."""
    c.update(ler_edital(c, ler))


def confirmado(reg):
    """O registro ja se apoia na banca oficial?"""
    if reg.get("selo") in ("PENDÊNCIA DE VERIFICAÇÃO", "PENDÊNCIA"):
        return False
    if any(not p.get("confirmado") for p in reg.get("prazos") or []):
        return False
    return DOMINIO in (reg.get("fonte") or "")


# ------------------------------------------------------------------ estado (URLs vistas)
def carregar_estado(caminho=ESTADO_PADRAO):
    try:
        with open(caminho, encoding="utf-8") as f:
            e = json.load(f)
        return e if isinstance(e, dict) else {}
    except (OSError, ValueError):
        return {}


def vistos_da_banca(estado):
    return ((estado.get("bancas") or {}).get(BANCA_ID)) or {}


def novos_arquivos(c, regs, vistos, hoje):
    """(arquivos novos, base). Com estado: URL nao vista (ou vista hoje: re-execucao do mesmo dia).
    Sem estado (1a vez do concurso): data efetiva >= verificado_em - MARGEM_SEM_ESTADO dias, isto e, o
    anterior ao verificado_em conta como visto (a linha ja o traz) e o do proprio dia continua novo (a
    banca publica depois da execucao da manha: o caso de 16/11)."""
    hj = hoje.isoformat()
    if vistos is not None:
        return [a for a in c["arquivos"] if (vistos.get(chave_arquivo(a)) or hj) >= hj], "urls_vistas"
    if not regs:
        return list(c["arquivos"]), "sem_registro"
    ult = max((r.get("verificado_em") or "" for r in regs), default="")
    try:
        corte = (date.fromisoformat(ult) - timedelta(days=MARGEM_SEM_ESTADO)).isoformat()
    except ValueError:
        corte = ""
    return [a for a in c["arquivos"] if a.get("data_efetiva", a["data"]) >= corte], "data (sem estado)"


def movimento(c, vistos, hoje):
    """Arquivos de pagina SEM registro ainda nao vistos (vistos hoje continuam novos) com data efetiva nos ultimos
    JANELA_MOVIMENTO dias: o mais velho nunca e movimento, entao o estado dessas paginas guarda so os recentes."""
    hj, corte = hoje.isoformat(), (hoje - timedelta(days=JANELA_MOVIMENTO)).isoformat()
    vistos = vistos or {}
    return [a for a in c.get("arquivos") or [] if a.get("data_efetiva", a.get("data") or "") >= corte
            and (vistos.get(chave_arquivo(a)) or hj) >= hj]


def ultima_retificacao(c):
    ds = [a.get("data_efetiva", a["data"]) for a in c.get("arquivos") or []
          if RE_RETIFICACAO.search(a["titulo"]) or RE_RETIFICADO.search(a["titulo"])]
    return max(ds) if ds else None


def prazo_proximo(regs, hoje):
    for r in regs:
        for p in r.get("prazos") or []:
            try:
                d = (date.fromisoformat(p.get("data", "")) - hoje).days
            except ValueError:
                continue
            if PRAZO_RELEITURA[0] <= d <= PRAZO_RELEITURA[1]:
                return "prazo do registro em %s" % date.fromisoformat(p["data"]).strftime("%d/%m")
    return ""


def abertura_recente(c, hoje):
    """Concurso que abriu ha pouco: situacao 'Inscricoes Abertas' ou edital de abertura (o 'Edital...' mais antigo
    da pagina) com data da linha nos ultimos JANELA_ABERTURA dias."""
    if re.search(r"Inscri[çc][õo]es Abertas", c.get("situacao") or "", re.I):
        return True
    ab = next((a for a in reversed(c.get("arquivos") or []) if a["titulo"].lower().startswith("edital")), None)
    return bool(ab) and (ab.get("data") or "") >= (hoje - timedelta(days=JANELA_ABERTURA)).isoformat()


def motivo_releitura(c, regs, hoje):
    if not regs:
        # sem registro: so o candidato sem cargo (o edital decide) e o concurso novo com arquivo novo
        if c.get("candidatos") and c.get("cargo_incerto"):
            return "cargo do candidato não identificado"
        if c.get("novos_arquivos") and (c.get("ciclo_seguinte") or abertura_recente(c, hoje)) and not apoio_fora(c):
            return "concurso sem registro"
        return ""
    if not all(confirmado(r) for r in regs):
        return "registro sem confirmação oficial"
    mov = [a for a in c["novos_arquivos"] if RE_RELEITURA.search(a["titulo"])]
    if mov:
        return "arquivo novo: %s" % mov[0]["titulo"]
    return prazo_proximo(regs, hoje)


def divergencias(c, regs, hoje):
    """[{id, edital, registro}] quando o fim das inscricoes do edital (ou da retificacao) difere do registro."""
    ins = c.get("inscricoes") or {}
    if not ins.get("fim") or len(regs) != 1:
        return []
    fim = date.fromisoformat(ins["fim"])
    r = regs[0]
    d, txt = selos.fim_inscricoes_registro(r, hoje)
    if d == fim:
        return []
    if d is None and (fim - hoje).days < -3:
        return []          # inscricoes encerradas ha tempo e o registro nao fala nelas: nada a acusar
    return [{"id": r["id"], "edital": ins["trecho"], "registro": txt, "origem": ins.get("origem")}]


# ------------------------------------------------------------------ organizacao, cargo e ciclo
# cargo da pagina da banca (sufixo do slug ou titulo) x bloco do registro. Com \b: "Defensoria",
# "Procuradoria" e "Promotoria" sao o orgao, nao o cargo.
CARGOS = [(r"\bJu[íi]z(?:es|a|as)?\b|\bMagistratura\b", "magistratura"), (r"\bPromotor(?:es|a|as)?\b", "promotor"),
          (r"\bDefensor(?:es|a|as)?\b", "defensor"), (r"\bProcurador(?:es|a|as)?\b|\bAdvogad[oa]s?\b", "procurador"),
          (r"\bServidor(?:es)?\b|\bAnalista|\bT[ée]cnico|\bOficial\b", "apoio")]
SUFIXO_CARGO = {"juiz": "magistratura", "magistratura": "magistratura", "servidor": "apoio", "servidores": "apoio",
                "analista": "apoio", "tecnico": "apoio", "promotor": "promotor", "defensor": "defensor",
                "procurador": "procurador"}
# cargo antes do orgao (juiztjba -> tjba); so antes de sigla de orgao ("defensoria..." e "procuradoria..." nao)
PREFIXO_CARGO = re.compile(r"^(juiz|promotor|defensor|procurador)(?=(?:tj|tr[ft]|mp|dpe?|pg[em]|al|tc)[a-z0-9])")
SUFIXO_ID = re.compile(r"_(juiz|promotor|procurador|defensor|apoio|oficial|servidor(?:es)?|analista|tecnico)$")


def cargos_texto(t):
    return {cl for padrao, cl in CARGOS if re.search(padrao, t or "", re.I)}


def cargo_slug(slug):
    s = re.sub(r"[^a-z0-9]", "", norm_slug(slug).split("/")[-1])
    m = PREFIXO_CARGO.match(s)
    if m:
        return {SUFIXO_CARGO[m.group(1)]}
    s = re.sub(r"\d{2,4}$", "", s)
    m = SUFIXOS.search(s)
    return {SUFIXO_CARGO[m.group(1)]} if m and m.group(1) in SUFIXO_CARGO else set()


def cargo_registro(r):
    b = r.get("bloco") or ""
    if b.startswith("Magistratura"):
        return "magistratura"
    if b == "Quadro de apoio":
        return "apoio"
    if "Promotor" in b:
        return "promotor"
    if "Defensor" in b:
        return "defensor"
    if "Procurador" in b or b in ("PFN", "AGU — Advogado da União"):
        return "procurador"
    return ""


def _ano(dig):
    if not dig:
        return None
    n = int(dig)
    n = 2000 + n if len(dig) == 2 else n
    return n if 1990 <= n <= 2099 else None


def partes_slug(slug):
    """(organizacao, ano|None) do slug da FGV, sem cargo nem ano: tjscjuiz26 -> ('tjsc', 2026); mpes25promotor ->
    ('mpes', 2025); juiztjba -> ('tjba', None); dperj2026 -> ('dperj', 2026); trt24 -> ('trt24', None) (24a
    regiao); trf1juiz25 -> ('trf1', 2025); dpe-pe -> ('dpepe', None); exames/enam/6exame -> ('enam', None)."""
    partes = norm_slug(slug).split("/")
    if partes[0] == "exames" and len(partes) > 1:
        return partes[1], None
    s = PREFIXO_CARGO.sub("", re.sub(r"[^a-z0-9]", "", partes[-1]))
    m = re.match(r"^(trt|trf)(\d+)([a-z]*)(\d*)$", s)
    if m:                                   # a regiao e numero: trt24 (24a), trt225 (2a, 2025), trf5juiz26
        dig, ano = m.group(2), m.group(4)
        if not ano:
            corte = 1 if m.group(1) == "trf" else (len(dig) if len(dig) <= 2 else 1 if len(dig) == 3
                                                    else 2 if len(dig) == 4 else len(dig) - 4)
            dig, ano = dig[:corte], dig[corte:]
        return m.group(1) + dig, _ano(ano)
    ano = None
    for _ in range(2):                      # mpes25promotor: cargo e depois o ano
        m = re.search(r"(?<=[a-z])(\d{4}|\d{2})$", s)
        if m:
            ano = ano or _ano(m.group(1))
            s = s[:m.start()]
        s = SUFIXOS.sub("", s)
    return s, ano


def org_slug(slug):
    return partes_slug(slug)[0]


def org_id(ident):
    """Organizacao do id do registro: dpe_rj -> dperj; tjpb_apoio -> tjpb; pge_rj_apoio -> pgerj; enam -> enam."""
    return re.sub(r"[^a-z0-9]", "", SUFIXO_ID.sub("", str(ident or "").lower()))


def ciclo(slug):
    """Numero comparavel do ciclo: ano do slug ou a edicao do exame (exames/enam/6exame -> 6); None sem ele."""
    s = norm_slug(slug)
    if s.startswith("exames/"):
        m = re.match(r"(\d+)", s.split("/")[-1])
        return int(m.group(1)) if m else None
    return partes_slug(s)[1]


ROMANO = re.compile(r"M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})")
RE_ORDINAL = re.compile(r"\b([IVXLC]{1,8}|\d{1,3}\s?[ºª°])\s+(?i:concurso|exame|edi[çc][ãa]o)\b")
VALOR_ROMANO = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def ordinais(texto):
    """{numero: como esta no texto} das edicoes citadas ('XXXIX Concurso', '19º concurso')."""
    out = {}
    for m in RE_ORDINAL.finditer(texto or ""):
        tok = m.group(1).replace(" ", "")
        if tok[-1] in "ºª°":
            out.setdefault(int(tok[:-1]), tok)
        elif ROMANO.fullmatch(tok):
            vals = [VALOR_ROMANO[ch] for ch in tok]
            out.setdefault(sum(-v if i + 1 < len(vals) and v < vals[i + 1] else v for i, v in enumerate(vals)), tok)
    return out


def trava_ciclo(c, r, hoje):
    """'' ou por que a pagina NAO e candidata ao registro `r` do mesmo orgao e cargo (outra edicao): slug de 2+
    anos antes; ordinal do titulo/edital diferente do da linha do registro (XXXIX x XL); registro EM PLANEJAMENTO
    (o concurso dele ainda nao tem edital) e pagina com edital de abertura de mais de PLANEJAMENTO_DIAS dias
    (dpero25 x dpe_ro, VI concurso com comissao de 05/2026)."""
    ano = partes_slug(c["slug"])[1]
    if ano and ano < hoje.year - 1:
        return "edição de %d" % ano
    pag = ordinais(" ".join([c.get("titulo") or ""] + [a["titulo"] for a in c.get("arquivos") or []
                                                         if a["titulo"].lower().startswith("edital")]))
    reg = ordinais(r.get("linha"))
    if pag and reg and not set(pag) & set(reg):
        return "%s × %s" % ("/".join(pag.values()), "/".join(reg.values()))
    ab = next((a for a in reversed(c.get("arquivos") or []) if a["titulo"].lower().startswith("edital")), None)
    if r.get("selo") == "EM PLANEJAMENTO" and ab and (ab.get("data") or "9") < (
            hoje - timedelta(days=PLANEJAMENTO_DIAS)).isoformat():
        return "registro em planejamento × edital de %s" % datetime.strptime(ab["data"], "%Y-%m-%d").strftime("%m/%Y")
    return ""


def apoio_fora(c):
    """Pagina do quadro de apoio (cargo do slug/titulo ou, sem eles, do edital: Analista/Tecnico) fora do escopo
    regional (escopo.apoio_no_escopo: so Sul/Sudeste com MG ou orgao nacional)."""
    cl = cargo_slug(c.get("slug")) | cargos_texto(c.get("titulo"))
    if not cl and re.search(r"Analista|T[ée]cnico", " ".join((c.get("edital") or {}).values())):
        cl = {"apoio"}
    return cl == {"apoio"} and escopo.apoio_no_escopo(c.get("titulo") or "", slug=c.get("slug")) == "fora"


def _url_norm(u):
    return re.sub(r"^https?://", "", str(u or "").strip().lower().split("#")[0].split("?")[0].rstrip("/"))


def fonte_aponta(r, c):
    """A `fonte` ou a `url_oficial` do registro e esta pagina ou um arquivo dela?"""
    alvos = {_url_norm(r.get("fonte")), _url_norm(r.get("url_oficial"))} - {""}
    if not alvos:
        return False
    return _url_norm(c.get("url")) in alvos or any(_url_norm(a.get("url")) in alvos
                                                   for a in c.get("arquivos") or [] if a.get("url"))


def desambiguar(c, regs, usar_edital=False):
    """(registros da mesma organizacao que sao DESTE concurso, certo?). Decide pelo cargo do slug e do titulo da
    banca contra o bloco do registro — tambem com um registro so (tjapservidores26 nao e o tjap_juiz).
    Sem cargo no slug/titulo: com `usar_edital`, o edital que fala em Analista/Tecnico e do quadro de apoio
    (senao, o cargo unico que o edital citar). Sem nada: (regs, False)."""
    if not regs:
        return regs, True
    cl = cargo_slug(c.get("slug")) | cargos_texto(c.get("titulo"))
    if not cl and usar_edital:
        ed = " ".join((c.get("edital") or {}).values())
        if re.search(r"Analista|T[ée]cnico", ed):
            cl = {"apoio"}
        else:
            cl = cargos_texto(ed)
            cl = cl if len(cl) == 1 else set()
    if not cl:
        return regs, False
    so = [r for r in regs if cargo_registro(r) in cl]
    return so, len(so) <= 1 or len(cl) == 1


def casar(alvo, concursos, hoje):
    """Vinculo de cada pagina (c['registros'], c['vinculo'] = 'banca_slug' | 'fonte') e, sem ele, candidatos e
    travas (c['candidatos'], c['cargo_incerto'], c['mesma_sigla'], c['edicao'], c['nova_edicao'],
    c['ciclo_seguinte'], c['exame_sem_registro']). Ver o cabecalho."""
    concursos = [r for r in concursos or [] if isinstance(r, dict) and r.get("id")]
    por_slug, por_org = {}, {}
    for r in concursos:
        s = norm_slug(r.get("banca_slug"))
        if s:
            por_slug.setdefault(s, []).append(r)
        por_org.setdefault(org_id(r["id"]), []).append(r)
    for c in alvo:
        for k in ("mesma_sigla", "edicao", "nova_edicao", "ciclo_seguinte", "incerto", "cargo_incerto",
                  "exame_sem_registro"):
            c.pop(k, None)
        c["registros"] = [r["id"] for r in por_slug.get(c["slug"], [])]
        c["vinculo"] = "banca_slug" if c["registros"] else ""
        c["candidatos"] = []
    # pela fonte: so registro sem banca_slug, sem cargo contrario no slug/titulo da pagina
    for r in concursos:
        if norm_slug(r.get("banca_slug")):
            continue
        for c in alvo:
            if c["vinculo"] == "banca_slug" or not fonte_aponta(r, c):
                continue
            cl = cargo_slug(c["slug"]) | cargos_texto(c.get("titulo"))
            if cl and cargo_registro(r) and cargo_registro(r) not in cl:
                continue
            c["registros"].append(r["id"])
            c["vinculo"] = "fonte"
    ligado = {}                              # id -> slugs a que o registro ja esta vinculado
    for r in concursos:
        if norm_slug(r.get("banca_slug")):
            ligado.setdefault(r["id"], []).append(norm_slug(r["banca_slug"]))
    for c in alvo:
        for i in c["registros"]:
            if c["slug"] not in ligado.setdefault(i, []):
                ligado[i].append(c["slug"])
    exame_novo = {}                          # exames/<org>/: so a edicao mais nova listada pode ser candidata
    for c in alvo:
        if c["slug"].startswith("exames/"):
            o = org_slug(c["slug"])
            exame_novo[o] = max(exame_novo.get(o, 0), ciclo(c["slug"]) or 0)
    for c in alvo:
        if c["registros"]:
            continue
        ano = partes_slug(c["slug"])[1]
        if ano and ano > hoje.year:
            c["ciclo_seguinte"] = ano        # nunca e o registro do ciclo atual (tjscjuiz27 x tjsc_juiz)
        mesma = por_org.get(org_slug(c["slug"]), [])
        if not mesma:
            continue
        if c["slug"].startswith("exames/") and (ciclo(c["slug"]) or 0) < exame_novo.get(org_slug(c["slug"]), 0):
            c["edicao"] = "edição anterior de %s" % "/".join(r["id"] for r in mesma)
            continue
        so, certo = desambiguar(c, mesma)
        if not so:
            c["mesma_sigla"] = [r["id"] for r in mesma]          # outro cargo do mesmo orgao: SEM REGISTRO
            continue
        for r in so:
            outra = ligado.get(r["id"])
            if outra:
                cp, cv = ciclo(c["slug"]), max((ciclo(s) or 0) for s in outra)
                # vinculado sem ano (trf2juiz): a pagina com ano e edicao nova (trf2juiz27), nao "edicao anterior"
                # (rev1 C4) — salvo o ano de 2+ anos antes, a mesma trava do candidato (trava_ciclo)
                velha = not cv and cp and 1990 <= cp < hoje.year - 1
                if cp and (not cv or cp > cv) and not velha:
                    c["nova_edicao"] = {"id": r["id"], "vinculada": outra[0]}
                else:
                    c["edicao"] = "edição anterior ou outra página de %s (vinculado a %s)" % (r["id"], outra[0])
                continue
            if c.get("ciclo_seguinte"):
                c["edicao"] = "não é %s: ciclo %d" % (r["id"], ano)
                continue
            trava = trava_ciclo(c, r, hoje)
            if trava:
                c["edicao"] = "não é %s: %s" % (r["id"], trava)
                continue
            c["candidatos"].append(r["id"])
        if c["candidatos"] and not certo:
            c["cargo_incerto"] = True
    for org, bloco in EXAMES_REGISTRO.items():
        exs = [c for c in alvo if c["slug"].startswith("exames/%s/" % org)]
        if exs and not por_org.get(org):
            max(exs, key=lambda c: ciclo(c["slug"]) or 0)["exame_sem_registro"] = {"id": org, "bloco": bloco}
    return alvo


def categoria(c):
    """Como a pagina sai: registro (completa, como antes) | candidato | exame | nova_edicao (1 linha) | novo
    (completa, SEM REGISTRO → avalie como NOVO) | movimento (1 linha) | fora_escopo | nao_lida | outros
    (contagem)."""
    if c.get("registros") or c.get("incerto"):
        return "registro"
    if c.get("http") != 200:
        return "nao_lida"
    if c.get("candidatos"):
        return "candidato"
    if c.get("exame_sem_registro"):
        return "exame"
    if c.get("nova_edicao"):
        return "nova_edicao"
    if not c.get("arquivos"):
        return "outros"            # pagina-indice sem arquivos datados (tjrjservidores25: links para outras paginas)
    if apoio_fora(c):
        return "fora_escopo"
    if c.get("novos_arquivos"):
        return "novo" if c.get("releitura") == "concurso sem registro" else "movimento"
    return "outros"


def coletar(hoje, concursos, estado=None, buscar=None, ler=texto_pdf):
    """Listagem + paginas + analise. Listagem fora do ar ou ilegivel (200 sem o bloco da view em andamento: view
    renomeada) nao derruba as paginas com banca_slug, lidas sempre (rev1 C3: antes voltava cedo, sem nenhuma, e o
    "http 200" enganava); `erro` diz o que houve com a listagem e `http` e 200 se alguma pagina respondeu."""
    codigo, lista, falhas = listagem(buscar)
    res = {"banca": "FGV", "dominio": DOMINIO, "http": codigo, "data": hoje.isoformat(), "concursos": []}
    vinculados = {norm_slug(r.get("banca_slug")) for r in concursos or [] if isinstance(r, dict)} - {""}
    if codigo != 200 or not lista:
        res["erro"] = ("listagem ilegível: http 200 sem o bloco de concursos em andamento" if codigo == 200 and falhas
                       else "listagem vazia: http 200 sem concursos em andamento" if codigo == 200 else
                       "http %s" % codigo)
        lista = []
        if not vinculados:
            return res
    fontes = {_url_norm(r.get(k)) for r in concursos or [] if isinstance(r, dict) for k in ("fonte", "url_oficial")}
    alvo, fora = [], {"escopo": [], "carreira": []}
    for c in lista:
        sempre = c["slug"] in vinculados or _url_norm(c["url"]) in fontes
        if not sempre and not JURIDICO.search(c["titulo"]):
            continue
        if not sempre and fora_de_carreira(c):
            fora["carreira"].append(c["slug"])
        elif not sempre and apoio_fora(c):
            fora["escopo"].append(c["slug"])
        else:
            alvo.append(c)
    listados = {c["slug"] for c in lista}
    for s in sorted(vinculados - listados):          # registro vinculado que saiu da listagem: le a pagina assim mesmo
        alvo.append({"slug": s, "titulo": "", "url": url_de_slug(s), "fora_da_listagem": bool(lista),
                     "url_alt": None if "/" in s else BASE + "/" + s})
    lidas = paralelo(lambda c: pagina(c, buscar), alvo, THREADS, TETO_PAGINAS_S)
    alvo = [r if r is not None else dict(c, http=0, arquivos=[], erro="sem resposta em %d s" % TETO_PAGINAS_S)
            for c, r in zip(alvo, lidas)]
    res["concursos"] = analisar(alvo, hoje, concursos, estado, ler)
    res["listagem"] = {"itens": len(lista), "paginas_com_falha": falhas, "fora_escopo": fora["escopo"],
                       "fora_carreira": fora["carreira"], "http": codigo}
    if res.get("erro"):
        res["listagem"]["erro"] = res["erro"]
        if any(c.get("http") == 200 for c in res["concursos"]):
            res["http"] = 200
        else:                                         # nem a listagem nem as paginas vinculadas: "nao lida", como antes
            res["http"], res["concursos"] = (codigo if codigo != 200 else 0), []
    return res


def analisar(alvo, hoje, concursos, estado=None, ler=texto_pdf):
    """Casa cada concurso da banca com o registro (casar), marca os arquivos novos, rele o edital quando preciso
    (em paralelo) e aponta divergencias. `alvo` = concursos com `arquivos` (pagina() ja rodou)."""
    estado = carregar_estado() if estado is None else estado
    vistos = vistos_da_banca(estado)
    por_id = {r.get("id"): r for r in concursos or [] if isinstance(r, dict)}
    for c in alvo:
        c.setdefault("arquivos", [])
        for a in c["arquivos"]:
            a.setdefault("data_efetiva", data_efetiva(a))
    casar(alvo, concursos, hoje)
    for c in alvo:
        regs = [por_id[i] for i in c["registros"] if i in por_id]
        ent = vistos.get(c["slug"]) if isinstance(vistos.get(c["slug"]), dict) else {}
        if regs:   # entrada `parcial` (pagina que era sem registro) nao serve de URLs vistas: base pela data
            v = ent.get("urls") if c["slug"] in vistos and not ent.get("parcial") else None
            c["novos_arquivos"], c["base_novos"] = novos_arquivos(c, regs, v, hoje)
        else:
            c["novos_arquivos"], c["base_novos"] = movimento(c, ent.get("urls"), hoje), "movimento"
        c["ultima_retificacao"] = ultima_retificacao(c)
        c["releitura"] = motivo_releitura(c, regs, hoje)
    lidos = [c for c in alvo if c["releitura"]]
    for c, r in zip(lidos, paralelo(lambda c: ler_edital(c, ler), lidos, THREADS_PDF, TETO_EDITAIS_S)):
        c.update(r if r is not None else {"edital_erro": "sem resposta em %d s" % TETO_EDITAIS_S})
        if c.get("inscricoes"):
            c["inscricoes"]["lido_em"] = hoje.isoformat()     # trecho lido HOJE (nao ha cache entre dias)
    for c in alvo:
        if c.get("cargo_incerto") and c.get("edital"):        # o edital decide o cargo do candidato
            cand = [por_id[i] for i in c["candidatos"] if i in por_id]
            so, certo = desambiguar(c, cand, usar_edital=True)
            if so != cand or certo:
                c["candidatos"] = [r["id"] for r in so]
                if not so:
                    c["mesma_sigla"] = [r["id"] for r in cand]
                c["cargo_incerto"] = bool(so) and not certo
        regs = [por_id[i] for i in c["registros"] if i in por_id]
        # coberto = a pagina oficial deste registro foi lida hoje: o coletor nao gasta busca com ele
        c["coberto"] = c["registros"] if (len(c["registros"]) == 1 and c.get("http") == 200
                                          and c.get("arquivos")) else []
        c["divergencias"] = divergencias(c, regs, hoje) if regs else []
        c["chaves_arquivos"] = [chave_arquivo(a) for a in c.get("arquivos") or []]
    # duas paginas para o mesmo registro (so pela fonte: o banca_slug e unico): nenhuma cobre (a ultima
    # sobrescreveria carimbo, selo e DIVERGE)
    paginas = {}
    for c in alvo:
        for ident in c["coberto"]:
            paginas.setdefault(ident, []).append(c)
    for ident, cs in paginas.items():
        if len(cs) < 2:
            continue
        slugs = ", ".join(x["slug"] for x in cs)
        for c in cs:
            c["coberto"], c["divergencias"] = [], []
            c["registros"] = [i for i in c["registros"] if i != ident]
            c["incerto"] = {"ids": [ident], "motivo": "%d páginas da FGV casam com o registro (%s)" % (len(cs), slugs)}
    for c in alvo:
        c["exibir"] = categoria(c)
        if c["exibir"] in ("outros", "fora_escopo", "nao_lida"):        # so contagem: sem a lista de arquivos
            arqs = c.get("arquivos") or []
            if arqs:
                c["ultimo"] = {"data": arqs[0].get("data_efetiva") or arqs[0]["data"], "titulo": arqs[0]["titulo"]}
            c["n_arquivos"], c["arquivos"], c["chaves_arquivos"], c["novos_arquivos"] = len(arqs), [], [], []
    return alvo


# ------------------------------------------------------------------ usados pelo helper e pelo montador
def _concursos_lidos(res):
    if not res or res.get("http") != 200:
        return []
    return [c for c in res.get("concursos") or [] if c.get("http") == 200 and c.get("arquivos")]


def inscricoes_do_dia(res, c, hoje):
    """O trecho de inscricoes do edital/retificacao LIDO HOJE ({"inicio","fim","trecho","origem"[,"lido_em"]}) ou
    None. `inscricoes` so existe quando analisar() releu o PDF nesta execucao (nao ha cache entre dias); por
    seguranca recusa: bancas.json de outro dia, concurso com releitura vazia ou erro no edital, trecho com
    `lido_em` de outro dia. Base de toda comparacao registro x edital (divergencias_pendentes)."""
    hj = hoje.isoformat() if isinstance(hoje, date) else str(hoje)[:10]
    ins = c.get("inscricoes") or {}
    if not isinstance(ins, dict) or not ins.get("fim") or c.get("edital_erro"):
        return None
    if (res or {}).get("data") not in (None, hj) or ("releitura" in c and not c["releitura"]):
        return None
    if ins.get("lido_em") not in (None, hj):
        return None
    return ins


def divergencias_pendentes(res, concursos, hoje, upd=None):
    """{id: {"edital", "registro", "fim_edital", "fim_registro", "escrito_hoje"}} dos registros lidos hoje na banca
    cujo fim das inscricoes difere do edital/retificacao lido HOJE (inscricoes_do_dia) depois do update de hoje
    (registro + ledger_updates.concursos[id]). Examina todo concurso com o trecho lido hoje, nao so o que ja
    divergia de manha: um prazo ESCRITO hoje que contradiz o edital (registro igual ao edital, update com outra
    data) tambem fica pendente — `escrito_hoje` = o update mudou o fim das inscricoes que o registro diz (so e
    exato quando `concursos` e o registro de ANTES do update, como no --validar do helper). Sem `upd`, vale o
    registro como esta (o DIVERGE DO REGISTRO do inicio.py). Remocao no update resolve; edital nao relido hoje,
    nada (sem comparacao)."""
    hj = hoje if isinstance(hoje, date) else date.fromisoformat(str(hoje)[:10])
    por_id = {c.get("id"): c for c in concursos or []}
    out = {}
    for c in _concursos_lidos(res):
        ins = inscricoes_do_dia(res, c, hj)
        if not ins:
            continue
        for ident in c.get("coberto") or []:
            u = (upd or {}).get(ident) or {}
            if ident not in por_id or not isinstance(u, dict) or u.get("remover"):
                continue
            reg = dict(por_id[ident])
            reg.update({k: v for k, v in u.items() if k != "desfecho"})
            for d in divergencias(dict(c, inscricoes=ins), [reg], hj):
                fim_reg, _ = selos.fim_inscricoes_registro(reg, hj)
                fim_antes, _ = selos.fim_inscricoes_registro(por_id[ident], hj)
                out[ident] = {"edital": d["edital"], "registro": d["registro"], "fim_edital": ins["fim"],
                              "fim_registro": fim_reg.isoformat() if fim_reg else None,
                              "escrito_hoje": bool(u) and fim_reg != fim_antes}
    return out


def aviso_selo_suspenso(ident, selo, pend):
    """Texto (acionavel) do selo por data SUSPENSO: as duas datas e o que fazer. Mesmo texto no helper (ALERTA),
    no montador (AVISO ACIONÁVEL) e no inicio (ALERTA)."""
    fr = pend.get("fim_registro")
    fe = pend.get("fim_edital") or ""
    reg = ("o registro diz fim das inscrições em %s" % dm(fr)) if fr else "o registro não traz o fim das inscrições"
    return ("selo por data suspenso em %s: %s e o edital lido hoje, %s — o selo %s fica como está (sem recálculo nem "
            "carimbo da banca) até prazos/linha baterem com o edital: corrija-os em ledger_updates.concursos.%s ou "
            "escreva o selo" % (ident, reg, dm(fe) if fe else "outra data", selo, ident))


def selo_do_dia(reg, hoje, ctx=None, pendentes=None):
    """A regra UNICA do selo por data com a banca lida hoje, usada pelo helper (aplicar_mecanicos_concursos), pelo
    montador (estado_concursos) e pelo inicio.py: (selo, motivo|None, suspenso|None).
    - `ctx` = contexto_selos(...) e `pendentes` = divergencias_pendentes(...), os dois com o update de hoje;
    - registro com divergencia pendente (o edital lido hoje contesta o fim das inscricoes do registro, inclusive o
      prazo escrito hoje) e selo da familia de datas: o selo por data fica SUSPENSO — devolve o selo atual, motivo
      None e, em `suspenso`, o aviso (aviso_selo_suspenso). Antes so se tirava o "banca lida" do contexto e o selo
      saia da data contestada (TJSC fim 25/11 x edital 26/11: ENCERRA EM BREVE em 18/11, a oficial dava ABERTAS);
    - senao: selos.selo_por_data com o contexto da banca (motivo como la) e suspenso None.
    Quem chama continua sem aplicar sobre selo ESCRITO hoje (selos.selo_escrito)."""
    ident = reg.get("id")
    p = (pendentes or {}).get(ident)
    if p and reg.get("selo") in selos.FAMILIA_DATA:
        return reg.get("selo"), None, aviso_selo_suspenso(ident, reg.get("selo"), p)
    x = (ctx or {}).get(ident) or {}
    novo, motivo = selos.selo_por_data(reg, hoje, banca_lida_hoje=x.get("banca_lida_hoje", False),
                                       ultima_retificacao=x.get("ultima_retificacao"),
                                       inicio_inscricoes_banca=x.get("inicio_inscricoes"))
    return novo, motivo, None


def contexto_selos(res, concursos=None, hoje=None, upd=None):
    """{id: {banca_lida_hoje, ultima_retificacao, inicio_inscricoes}} para selos.selo_por_data.
    Com `concursos` e `hoje`: o registro que AINDA diverge do edital (divergencias_pendentes, com o
    `upd` de hoje) fica de fora — a banca lida hoje contradiz o registro e nao sustenta o selo."""
    fora = divergencias_pendentes(res, concursos, hoje, upd) if concursos is not None and hoje else {}
    out = {}
    for c in _concursos_lidos(res):
        ret = c.get("ultima_retificacao")
        if ret is None and "ultima_retificacao" not in c:      # bancas.json antigo
            ret = ultima_retificacao(c)
        for ident in c.get("coberto") or []:
            if ident in fora:
                continue
            out[ident] = {"banca_lida_hoje": True, "ultima_retificacao": ret,
                          "inicio_inscricoes": (c.get("inscricoes") or {}).get("inicio")}
    return out


def carimbos(res, concursos, hoje, upd=None):
    """Campos mecanicos dos registros lidos hoje na banca: verificado_em = hoje; fonte = pagina da
    banca so quando a fonte atual nao e oficial (nunca troca fonte oficial, de nenhum dominio);
    dominio_oficial quando falta ou quando a fonte passou a ser a da banca.
    Com `upd` (ledger_updates.concursos de hoje; {} = nenhum): o registro que AINDA diverge do edital
    (DIVERGE DO REGISTRO nao corrigido em linha/prazos) nao e carimbado — senao o leitor o veria como
    "verificado hoje na banca oficial" com o dado que a banca contradiz (TJAP de b80a3bd). Sem `upd`
    (None), o comportamento antigo, sem esse filtro."""
    hj = hoje.isoformat() if isinstance(hoje, date) else str(hoje)
    por_id = {c.get("id"): c for c in concursos or []}
    fora = divergencias_pendentes(res, concursos, hoje, upd) if upd is not None else {}
    out = {}
    for c in _concursos_lidos(res):
        for ident in c.get("coberto") or []:
            reg = por_id.get(ident)
            if reg is None or ident in fora:
                continue
            campos = {}
            if (reg.get("verificado_em") or "") < hj:
                campos["verificado_em"] = hj
            dom = res.get("dominio") or DOMINIO
            if not selos.fonte_oficial(reg.get("fonte"), reg.get("dominio_oficial")):
                campos["fonte"] = c["url"]
                if reg.get("dominio_oficial") != dom:
                    campos["dominio_oficial"] = dom
            elif not reg.get("dominio_oficial"):
                campos["dominio_oficial"] = selos.host(reg.get("fonte")) or dom
            if campos:
                out[ident] = campos
    return out


def novos_por_registro(res):
    out = {}
    for c in _concursos_lidos(res):
        if c.get("novos_arquivos"):
            for ident in c.get("coberto") or []:
                out[ident] = c["novos_arquivos"]
    return out


def base_dos_novos(res, ident):
    """'urls_vistas' | 'data (sem estado)' | 'sem_registro' do concurso da banca ligado ao registro."""
    for c in _concursos_lidos(res):
        if ident in (c.get("coberto") or []):
            return c.get("base_novos")
    return None


def atualizar_estado(estado, res, hoje):
    """Marca como vistos (data da 1a vez) os arquivos dos concursos lidos hoje. Devolve quantos novos.
    Pagina sem registro (exibir candidato/movimento/novo...): so os arquivos dos ultimos JANELA_MOVIMENTO dias,
    numa entrada `parcial` podada a cada dia (o mais velho nunca e movimento; o estado nao cresce com as ~60
    paginas da listagem). Pagina com registro (ou bancas.json antigo, sem `exibir`): todas as URLs, como antes."""
    hj = hoje.isoformat() if isinstance(hoje, date) else str(hoje)[:10]
    hd = date.fromisoformat(hj)
    corte_mov = (hd - timedelta(days=JANELA_MOVIMENTO)).isoformat()
    corte_poda = (hd - timedelta(days=JANELA_MOVIMENTO + 3)).isoformat()
    fgv = estado.setdefault("bancas", {}).setdefault(BANCA_ID, {})
    n = 0
    for c in _concursos_lidos(res):
        ent = fgv.get(c["slug"]) if isinstance(fgv.get(c["slug"]), dict) else None
        completo = c.get("exibir") in (None, "registro") or (ent is not None and not ent.get("parcial"))
        if completo:
            reg = fgv.setdefault(c["slug"], {"urls": {}})
            reg.pop("parcial", None)
            urls = reg.setdefault("urls", {})
            chaves = c.get("chaves_arquivos") or [chave_arquivo(a) for a in c["arquivos"]]
        else:
            chaves = [chave_arquivo(a) for a in c["arquivos"]
                      if (a.get("data_efetiva") or a.get("data") or "") >= corte_mov]
            if not chaves and ent is None:
                continue                         # nada recente: nem cria a entrada
            reg = fgv.setdefault(c["slug"], {"urls": {}, "parcial": True})
            urls = reg.setdefault("urls", {})
        for k in chaves:
            if k not in urls:
                urls[k] = hj
                n += 1
        reg["lido_em"] = hj
    for slug in list(fgv):                       # poda das entradas parciais
        ent = fgv[slug]
        if isinstance(ent, dict) and ent.get("parcial"):
            ent["urls"] = {k: d for k, d in (ent.get("urls") or {}).items() if d >= corte_poda}
            if not ent["urls"] and (ent.get("lido_em") or "") < corte_poda:
                del fgv[slug]
    return n


def gravar_estado(caminho, estado):
    estado["aviso"] = ("Gerado por work/Update-Historico.py (bancas.atualizar_estado) e commitado pelo "
                       "finalizar.sh. Nao editar a mao.")
    texto = json.dumps(estado, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    with open(caminho, "w", encoding="utf-8", newline="") as f:
        f.write(texto)


# ------------------------------------------------------------------ saida
def dm(iso):
    return iso[8:10] + "/" + iso[5:7]


def _arq(a):
    d = a.get("data_efetiva") or a["data"]
    return "%s %s" % (dm(d), a["titulo"]) + (" [data da linha %s]" % dm(a["data"]) if d != a["data"] else "")


def _curto(s, n):
    s = s or ""
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def _arqs_curtos(arqs, n=3):
    return "; ".join("%s %s" % (dm(a.get("data_efetiva") or a["data"]), _curto(a["titulo"], 55)) for a in arqs[:n]) \
        + (" (+%d)" % (len(arqs) - n) if len(arqs) > n else "")


def _completo(c):
    """Linhas do concurso completo (registro, ou SEM REGISTRO → avalie como NOVO), no formato de antes."""
    inc = c.get("incerto")
    if c.get("registros"):
        reg = "registro " + " ou ".join(c["registros"])
        if c.get("vinculo") == "fonte":
            reg += ' [vínculo pela fonte: grave banca_slug="%s"]' % c["slug"]
    elif inc:
        reg = "registro incerto: %s" % " ou ".join(inc["ids"])
    elif c.get("mesma_sigla"):
        reg = "SEM REGISTRO (%s, da mesma sigla, é de outro cargo) → avalie como NOVO" % ", ".join(c["mesma_sigla"])
    elif c.get("ciclo_seguinte"):
        reg = "SEM REGISTRO (ciclo %d) → avalie como NOVO" % c["ciclo_seguinte"]
    else:
        reg = "SEM REGISTRO → avalie como NOVO"
    if c.get("edicao") and not c.get("registros"):
        reg += " [%s]" % c["edicao"]
    print("- %s | %s | %s | %s | %s" % (c["slug"], c.get("situacao") or "?", c.get("titulo") or "?", reg, c["url"]))
    if c.get("http") != 200 and c.get("registros"):
        print("  página não lida (http %s%s): sem carimbo, selo por data e DIVERGE daqui hoje — o registro segue pelo "
              "coletor" % (c.get("http"), "; fora da listagem em andamento" if c.get("fora_da_listagem") else ""))
    elif c.get("fora_da_listagem"):
        print("  fora da listagem de concursos em andamento da FGV (lida pelo banca_slug): confira se o concurso acabou")
    if inc:
        print("  AVISO: página não cobre %s (%s): sem carimbo, sem selo por data e sem DIVERGE daqui — "
              "confira o cargo antes de levar estes arquivos ao registro" % (" ou ".join(inc["ids"]), inc["motivo"]))
    novos = c.get("novos_arquivos") or []
    if novos:
        print("  arquivos novos (%s): %s%s" % (
            "não vistos antes" if c.get("base_novos") in ("urls_vistas", "movimento") else "desde a última verificação",
            "; ".join(_arq(a) for a in novos[:5]), " (+%d)" % (len(novos) - 5) if len(novos) > 5 else ""))
    elif c.get("arquivos"):
        ult = c["arquivos"][0]
        ret = c.get("ultima_retificacao")
        ret_a = next((a for a in c["arquivos"] if ret and a.get("data_efetiva") == ret
                      and (RE_RETIFICACAO.search(a["titulo"]) or RE_RETIFICADO.search(a["titulo"]))), None)
        print("  sem arquivo novo; último: %s%s" % (_arq(ult), "; última retificação: " + _arq(ret_a)
                                                     if ret_a and ret_a is not ult else ""))
    if c.get("edital"):
        print("  edital%s: %s" % (" (relido: %s)" % c["releitura"] if c.get("releitura") else "",
                                  " · ".join('%s "%s"' % kv for kv in c["edital"].items())))
        ri = c.get("retificacao_inscricoes")
        if ri:
            print('  %s (%s), LEIA-SE: inscrições "%s"' % (ri["titulo"], dm(ri["data"]), ri["trecho"]))
    elif c.get("edital_erro"):
        print("  edital não lido (%s)" % c["edital_erro"])
    for d in c.get("divergencias") or []:
        print('DIVERGE DO REGISTRO: %s edital="%s" registro="%s"' % (d["id"], d["edital"], d["registro"]))


def _ult(c):
    a = (c.get("arquivos") or [None])[0]
    return ("últ. %s %s" % (dm(a.get("data_efetiva") or a["data"]), _curto(a["titulo"], 60))) if a else "sem arquivos"


def imprimir(res):
    cs = res.get("concursos") or []
    if res.get("http") != 200 or not cs:
        print("BANCA FGV: página não lida (%s) — concursos da FGV seguem pela busca do coletor."
              % (res.get("erro") or "http %s" % res.get("http")))
        return
    grupos = {}
    for c in cs:                                  # bancas.json antigo (sem `exibir`): tudo completo, como antes
        grupos.setdefault(c.get("exibir") or "registro", []).append(c)
    lst = res.get("listagem") or {}
    print("BANCA FGV (fonte OFICIAL, lida por script — promove selo e confirma prazo; verificado_em, fonte e "
          "dominio_oficial dos registros lidos aqui são gravados sozinhos): %d concursos jurídicos%s" % (
              len(cs), (" lidos dos %d em andamento na listagem; %d com registro" % (lst["itens"], len(grupos.get(
                  "registro", [])))) if lst.get("itens") else ""))
    for c in grupos.get("registro", []):
        _completo(c)
    for c in grupos.get("candidato", []):
        ids = c["candidatos"]
        print('CANDIDATO %s ← %s | %s | %s | %s | %s%s → confirme o ciclo (ordinal/ano) e grave '
              'ledger_updates.concursos.%s.banca_slug="%s"' % (
                  " ou ".join(ids), c["slug"], c.get("situacao") or "?", _curto(c.get("titulo"), 90), _ult(c),
                  c["url"], (" (cargo não identificado: confirme qual)" if len(ids) > 1 else
                             " (cargo não identificado no título nem no edital)") if c.get("cargo_incerto") else "",
                  ids[0] if len(ids) == 1 else "<id>", c["slug"]))
    for c in grupos.get("exame", []):
        x = c["exame_sem_registro"]
        print('CANDIDATO a registro NOVO %s ← %s | %s | %s | %s | %s → exame nacional sem registro: crie '
              'ledger_updates.concursos.%s (bloco %s; prazos do cronograma; fonte = a página) com banca_slug="%s"' % (
                  x["id"], c["slug"], c.get("situacao") or "?", _curto(c.get("titulo"), 90), _ult(c), c["url"],
                  x["id"], x["bloco"], c["slug"]))
    for c in grupos.get("nova_edicao", []):
        x = c["nova_edicao"]
        print('NOVA EDIÇÃO? %s | %s | %s | %s | %s — %s está vinculado a %s: se é o ciclo seguinte, atualize o registro '
              '(linha, prazos e banca_slug="%s") ou avalie como NOVO' % (
                  c["slug"], c.get("situacao") or "?", _curto(c.get("titulo"), 90), _ult(c), c["url"], x["id"],
                  x["vinculada"], c["slug"]))
    for c in grupos.get("novo", []):
        _completo(c)
    for c in grupos.get("movimento", []):
        nota = [("mesma sigla de %s, outro cargo" % ", ".join(c["mesma_sigla"])) if c.get("mesma_sigla") else "",
                ("ciclo %d" % c["ciclo_seguinte"]) if c.get("ciclo_seguinte") else "", c.get("edicao") or ""]
        nota = "; ".join(x for x in nota if x)
        print("- MOVIMENTO sem registro: %s | %s | %s | %s%s" % (
            c["slug"], _curto(c.get("titulo"), 80), _arqs_curtos(c["novos_arquivos"], 2), c["url"],
            " [%s]" % nota if nota else ""))
    conta = [(len(grupos.get("outros", [])), "sem arquivo novo nos últimos %d dias" % JANELA_MOVIMENTO),
             (len(grupos.get("fora_escopo", [])) + len(lst.get("fora_escopo") or []),
              "fora do escopo (apoio só Sul/Sudeste)"),
             (len(lst.get("fora_carreira") or []), "fora de carreira (seletivo, juiz leigo, cartório)"),
             (len(grupos.get("nao_lida", [])), "páginas não lidas (rede/tempo)")]
    conta = [("%d %s" % (n, txt)) for n, txt in conta if n]
    if conta:
        print("  sem linha (só contagem, sem registro): " + "; ".join(conta))
    if lst.get("erro"):
        print("  sem a listagem hoje (%s): só as páginas com banca_slug foram lidas — candidatos, movimento e "
              "concurso novo da FGV seguem pelo coletor" % lst["erro"])
    elif lst.get("paginas_com_falha"):
        print("  listagem incompleta: ?page=%s não lida(s) — concursos dela seguem pelo coletor"
              % ",".join(str(p) for p in lst["paginas_com_falha"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--janela", default=tmp("janela.json"))
    a = ap.parse_args()
    try:
        hoje = date.fromisoformat(json.load(open(a.janela, encoding="utf-8"))["data"])
    except Exception:
        hoje = date.today()
    led = json.load(open(os.path.join(AQUI, "robozinho-aprendizado.json"), encoding="utf-8"))
    res = coletar(hoje, led.get("concursos") or [])
    with open(tmp("bancas.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    imprimir(res)


if __name__ == "__main__":
    main()
