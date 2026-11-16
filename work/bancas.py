#!/usr/bin/env python3
# =====================================================================
# bancas.py — leitura deterministica da BANCA OFICIAL dos concursos
# juridicos (sem tokens). Hoje cobre a FGV (conhecimento.fgv.br/concursos),
# que esta no allowlist e publica em HTML simples: listagem dos concursos,
# situacao e "Arquivos do concurso" (edital, retificacoes, resultados, com
# data). Cebraspe carrega a lista por JavaScript; FCC e Vunesp estao
# bloqueadas pela rede do ambiente.
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
# Para cada concurso juridico do ano corrente (ou do anterior) na listagem:
#   - casa com o registro do ledger pela sigla (tjap26 -> tjap_juiz) E pelo
#     cargo (sufixo do slug ou titulo: Juiz/Magistratura, Promotor, Defensor,
#     Procurador, Servidores/Analista/Tecnico) contra o bloco do registro:
#     outro concurso do mesmo orgao (tjapservidores26) nao cai no tjap_juiz.
#     Sem cargo identificavel (titulo, slug e edital) ou com duas paginas para
#     o mesmo registro: nao cobre (campo `incerto` + AVISO na saida);
#   - lista os arquivos novos (movimento oficial, com data);
#   - quando preciso (acima), baixa o edital e copia os trechos de vagas,
#     inscricoes, taxa, remuneracao e prova objetiva.
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
#   atualizar_estado(estado, res)   -> quantos arquivos passaram a "vistos"
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
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

import selos

AQUI = os.path.dirname(os.path.abspath(__file__))
UA = "Mozilla/5.0 (X11; Linux x86_64) Robozinho/1.0"
BANCA_ID = "fgv"
DOMINIO = "conhecimento.fgv.br"
BASE = "https://" + DOMINIO
ESTADO_PADRAO = os.path.join(AQUI, "concursos-estado.json")
JURIDICO = re.compile(r"Tribunal|Juiz|Magistratura|Procurador|Defensor|Minist[ée]rio P[úu]blico|"
                      r"Assembleia Legislativa|Advocacia|Promotor", re.I)
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
RE_RETIFICADO = re.compile(r"\((?:retificad[oa]|atualizad[oa]|consolidad[oa])\s+em\s+(\d{2})/(\d{2})/(\d{4})\)", re.I)
RE_RETIFICACAO = re.compile(r"retifica|prorroga|errata", re.I)
RE_RELEITURA = re.compile(r"retifica|prorroga|errata|\bedital\b", re.I)
MARGEM_SEM_ESTADO = 0        # sem estado: data efetiva >= verificado_em - N dias e novo (0 = so o dia dele e depois)
PRAZO_RELEITURA = (-3, 7)    # prazo do registro nesta faixa (dias) -> reler o edital


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


def limpa(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def listagem():
    codigo, t = fetch(BASE + "/concursos")
    vistos, out = set(), []
    for u, x in re.findall(r'href="(/concursos/[^"#?]+)"[^>]*>(.*?)</a>', t, flags=re.S):
        titulo = limpa(x)
        if u in vistos or not titulo:
            continue
        vistos.add(u)
        out.append({"slug": u.rsplit("/", 1)[-1], "titulo": titulo, "url": BASE + u})
    return codigo, out


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
    """Situacao e arquivos (data, data_efetiva, titulo, url) a partir do HTML da pagina do concurso."""
    corpo = re.sub(r"(?is)<(script|style|nav|footer|header).*?</\1>", " ", t)
    m = re.search(r"(?is)<main.*?</main>", corpo)
    corpo = m.group(0) if m else corpo
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


def pagina(c):
    codigo, t = fetch(c["url"])
    c["http"] = codigo
    return analisar_pagina(c, t)


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


def edital(c, ler=texto_pdf):
    """Trechos copiados do edital de abertura (PDF da banca) e, se houver retificacao posterior
    ao texto consolidado, o trecho de inscricoes do LEIA-SE dela."""
    alvo = next((a for a in reversed(c["arquivos"]) if a["titulo"].lower().startswith("edital") and a["url"]), None)
    if not alvo:
        return
    t, erro = ler(alvo["url"])
    if t is None:
        c["edital_erro"] = erro
        return
    c["edital_url"] = alvo["url"]
    c["edital"] = trechos(t)
    consolidado = data_efetiva(alvo) if RE_RETIFICADO.search(alvo["titulo"]) else ""
    rets = [a for a in c["arquivos"] if RE_RETIFICACAO.search(a["titulo"]) and a["url"]
            and not a["titulo"].lower().startswith("edital") and a.get("data_efetiva", a["data"]) > consolidado]
    if rets:
        ult = max(rets, key=lambda a: a.get("data_efetiva", a["data"]))
        tr, erro = ler(ult["url"])
        if tr is not None:
            achado = trecho_leia_se(tr)
            if achado:
                c["retificacao_inscricoes"] = {"titulo": ult["titulo"], "data": ult["data"], "url": ult["url"],
                                               "trecho": achado}
    ins = (c.get("retificacao_inscricoes") or {}).get("trecho") or c["edital"].get("inscrições")
    ds = datas_trecho(ins)
    if ds:
        c["inscricoes"] = {"inicio": ds[0].isoformat(), "fim": ds[-1].isoformat(), "trecho": ins,
                           "origem": "retificação" if c.get("retificacao_inscricoes") else "edital"}


def sigla(slug):
    s = re.sub(r"[^a-z0-9]", "", slug.lower())
    s = re.sub(r"\d{2,4}$", "", s)
    return SUFIXOS.sub("", s)


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


def motivo_releitura(c, regs, hoje):
    if not regs:
        return "concurso sem registro"
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


def coletar(hoje, concursos, estado=None):
    codigo, lista = listagem()
    res = {"banca": "FGV", "dominio": DOMINIO, "http": codigo, "data": hoje.isoformat(), "concursos": []}
    if codigo != 200 or not lista:
        return res
    anos = {"%02d" % (hoje.year % 100), "%02d" % ((hoje.year - 1) % 100), str(hoje.year), str(hoje.year - 1)}
    alvo = [c for c in lista if JURIDICO.search(c["titulo"]) and re.search(r"(\d{2,4})$", c["slug"])
            and re.search(r"(\d{2,4})$", c["slug"]).group(1) in anos]
    with ThreadPoolExecutor(max_workers=4) as ex:
        alvo = list(ex.map(pagina, alvo))
    res["concursos"] = analisar(alvo, hoje, concursos, estado)
    return res


def analisar(alvo, hoje, concursos, estado=None, ler=texto_pdf):
    """Casa cada concurso da banca com o registro, marca os arquivos novos, rele o edital quando
    preciso e aponta divergencias. `alvo` = concursos com `arquivos` (pagina() ja rodou)."""
    estado = carregar_estado() if estado is None else estado
    vistos = vistos_da_banca(estado)
    por_sigla = {}
    for r in concursos:
        por_sigla.setdefault(r["id"].split("_")[0], []).append(r)
    for c in alvo:
        for a in c.get("arquivos") or []:
            a.setdefault("data_efetiva", data_efetiva(a))
        mesma = por_sigla.get(sigla(c["slug"]), [])
        regs, certo = desambiguar(c, mesma)              # pelo cargo do slug/titulo (antes do edital)
        if regs != mesma and not regs:
            c["mesma_sigla"] = [r["id"] for r in mesma]  # outro cargo do mesmo orgao: SEM REGISTRO
        v = (vistos.get(c["slug"]) or {}).get("urls") if c["slug"] in vistos else None
        c["novos_arquivos"], c["base_novos"] = novos_arquivos(c, regs, v, hoje)
        c["ultima_retificacao"] = ultima_retificacao(c)
        c["releitura"] = motivo_releitura(c, regs, hoje)
        if c["releitura"]:
            edital(c, ler)
            if c.get("inscricoes"):
                c["inscricoes"]["lido_em"] = hoje.isoformat()     # trecho lido HOJE (nao ha cache entre dias)
        if not certo:
            regs, certo = desambiguar(c, regs, usar_edital=True)
        # dois ou mais candidatos sem cargo: como antes ("registro X ou Y", sem cobrir); um so sem cargo: incerto
        c["registros"] = [r["id"] for r in regs] if certo or len(regs) > 1 else []
        if not certo and len(regs) == 1:
            c["incerto"] = {"ids": [regs[0]["id"]],
                            "motivo": "cargo não identificado no título, no slug nem no edital"}
        # coberto = a pagina oficial deste registro foi lida hoje: o coletor nao gasta busca com ele
        c["coberto"] = c["registros"] if (len(c["registros"]) == 1 and c.get("http") == 200
                                          and c.get("arquivos")) else []
        c["divergencias"] = divergencias(c, regs, hoje) if certo else []
        c["chaves_arquivos"] = [chave_arquivo(a) for a in c.get("arquivos") or []]
    # duas paginas para o mesmo registro: nenhuma cobre (a ultima sobrescreveria carimbo, selo e DIVERGE)
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
    return alvo


# cargo da pagina da banca (sufixo do slug ou titulo) x bloco do registro. Com \b: "Defensoria",
# "Procuradoria" e "Promotoria" sao o orgao, nao o cargo.
CARGOS = [(r"\bJu[íi]z(?:es|a|as)?\b|\bMagistratura\b", "magistratura"), (r"\bPromotor(?:es|a|as)?\b", "promotor"),
          (r"\bDefensor(?:es|a|as)?\b", "defensor"), (r"\bProcurador(?:es|a|as)?\b|\bAdvogad[oa]s?\b", "procurador"),
          (r"\bServidor(?:es)?\b|\bAnalista|\bT[ée]cnico|\bOficial\b", "apoio")]
SUFIXO_CARGO = {"juiz": "magistratura", "magistratura": "magistratura", "servidor": "apoio", "servidores": "apoio",
                "analista": "apoio", "tecnico": "apoio", "promotor": "promotor", "defensor": "defensor",
                "procurador": "procurador"}


def cargos_texto(t):
    return {cl for padrao, cl in CARGOS if re.search(padrao, t or "", re.I)}


def cargo_slug(slug):
    s = re.sub(r"\d{2,4}$", "", re.sub(r"[^a-z0-9]", "", (slug or "").lower()))
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


def desambiguar(c, regs, usar_edital=False):
    """(registros da mesma sigla que sao DESTE concurso, certo?). Decide pelo cargo do slug e do titulo da
    banca contra o bloco do registro — tambem com um registro so (tjapservidores26 nao e o tjap_juiz).
    Sem cargo no slug/titulo: com `usar_edital`, o edital que fala em Analista/Tecnico e do quadro de apoio
    (senao, o cargo unico que o edital citar). Sem nada: (regs, False) — quem chama nao cobre."""
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
    """Marca como vistos (data da 1a vez) os arquivos dos concursos lidos hoje. Devolve quantos novos."""
    hj = hoje.isoformat() if isinstance(hoje, date) else str(hoje)
    fgv = estado.setdefault("bancas", {}).setdefault(BANCA_ID, {})
    n = 0
    for c in _concursos_lidos(res):
        reg = fgv.setdefault(c["slug"], {"urls": {}})
        urls = reg.setdefault("urls", {})
        for k in c.get("chaves_arquivos") or [chave_arquivo(a) for a in c["arquivos"]]:
            if k not in urls:
                urls[k] = hj
                n += 1
        reg["lido_em"] = hj
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


def imprimir(res):
    cs = res["concursos"]
    if res["http"] != 200 or not cs:
        print("BANCA FGV: página não lida (http %s) — concursos da FGV seguem pela busca do coletor." % res["http"])
        return
    print("BANCA FGV (fonte OFICIAL, lida por script — promove selo e confirma prazo; verificado_em, fonte e "
          "dominio_oficial dos registros lidos aqui são gravados sozinhos): %d concursos jurídicos" % len(cs))
    for c in cs:
        inc = c.get("incerto")
        if c["registros"]:
            reg = "registro " + " ou ".join(c["registros"])
        elif inc:
            reg = "registro incerto: %s" % " ou ".join(inc["ids"])
        elif c.get("mesma_sigla"):
            reg = "SEM REGISTRO (%s, da mesma sigla, é de outro cargo) → avalie como NOVO" % ", ".join(c["mesma_sigla"])
        else:
            reg = "SEM REGISTRO → avalie como NOVO"
        print("- %s | %s | %s | %s | %s" % (c["slug"], c.get("situacao") or "?", c["titulo"], reg, c["url"]))
        if inc:
            print("  AVISO: página não cobre %s (%s): sem carimbo, sem selo por data e sem DIVERGE daqui — "
                  "confira o cargo antes de levar estes arquivos ao registro" % (" ou ".join(inc["ids"]), inc["motivo"]))
        novos = c.get("novos_arquivos") or []
        if novos:
            print("  arquivos novos (%s): %s%s" % (
                "não vistos antes" if c.get("base_novos") == "urls_vistas" else "desde a última verificação",
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
