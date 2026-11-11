#!/usr/bin/env python3
# =====================================================================
# montar_email.py — passo 5 da ROTINA: do julgamento ao HTML pronto.
#
# O orquestrador escreve so o JULGAMENTO em /tmp/execucao.json (itens,
# selos, resumo executivo, pendencias, ledger_updates). Este script:
#   1. resolve os {"ref": id} com a evidencia dos scripts do passo 2
#      (coleta_web, informativos): titulo, linha-fina, hora, URL e chave
#      sao COPIADOS, nunca redigitados;
#   2. acrescenta o que e deterministico (versiculo, Munger, itens de
#      concurso que mudaram, pendencias do ledger, fontes consultadas);
#   3. valida (Update-Historico.py --validar + checagens do e-mail);
#   4. monta o e-mail INTEIRO no layout do template v4 — cabecalho, indice,
#      as 13 secoes, Concursos a partir do registro do ledger, rodape e
#      carimbo — e o imprime para o create_draft.
#
# Por que: ate 11/11/2026 o orquestrador compunha o HTML a mao e colava no
# meio dele as secoes de Concursos impressas por outro script. Em 05/11 e
# 10/11 o rascunho saiu com o marcador __CONCURSOS__ no lugar das secoes;
# em 11/11 o selo do Munger saiu invisivel. Com o corpo inteiro vindo
# daqui, o create_draft e uma copia: nao ha o que "encaixar".
#
# USO:   python3 work/montar_email.py            (valida, grava /tmp/email.html e imprime o HTML)
#        python3 work/montar_email.py --sem-html (so valida e grava; nao imprime o corpo)
# SAIDA: relatorio curto + "==== HTMLBODY ====" ... "==== FIM HTMLBODY ====";
#        com ERRO, exit 2 e nenhum HTML.
# =====================================================================

import argparse
import copy
import html
import json
import os
import re
import subprocess
import sys
import unicodedata
from datetime import date, datetime

AQUI = os.path.dirname(os.path.abspath(__file__))
DESTINATARIOS = ["pereirafranciscofilho@gmail.com", "luizaxbarreto@gmail.com"]

# ------------------------------------------------------------------ identidade visual (template v4)
FONTE = "font-family:Arial,Helvetica,sans-serif"
NAVY, OURO, TEXTO, APOIO_COR, LINK, LINHA = "#0b2545", "#c5a253", "#2f3a45", "#5a6773", "#0b4f92", "#e8edf2"
ESTILO = {
    "OFICIAL": "background:#e8eef7;color:#0b2545",
    "VERDE": "color:#1e6b3a;border:1px solid #bfe3cc",
    "URGENTE": "background:#fdf0f0;color:#a61b1b;border:1px solid #f0c2c2",
    "NEUTRO": "color:#5a6773;border:1px solid #c9ced6",
    "ALERTA": "color:#8a6d1d;border:1px solid #e6d3a3",
    "NAVY": "background:#0b2545;color:#ffffff",
}
SELO_ESTILO = {
    "CONFIRMADO POR FONTE OFICIAL": "OFICIAL", "CONFIRMADO": "OFICIAL", "VERSÍCULO DO DIA": "OFICIAL",
    "CONFIRMADO POR FONTE OFICIAL ALTERNATIVA": "VERDE", "INSCRIÇÕES ABERTAS": "VERDE",
    "EDITAL PUBLICADO": "VERDE", "NOVO": "VERDE",
    "ENCERRA HOJE": "URGENTE", "ENCERRA EM BREVE": "URGENTE", "URGENTE": "URGENTE",
    "PROVA EM BREVE": "URGENTE",
    "MÍDIA ESPECIALIZADA": "NEUTRO", "OPINIÃO/ANÁLISE": "NEUTRO", "EM ANDAMENTO": "NEUTRO",
    "EM PLANEJAMENTO": "NEUTRO", "PROVA REALIZADA": "NEUTRO", "INSCRIÇÕES ENCERRADAS": "NEUTRO",
    "PENDÊNCIA": "ALERTA", "PENDÊNCIA DE VERIFICAÇÃO": "ALERTA", "FORTE INDÍCIO": "ALERTA",
    "RUMOR": "ALERTA", "SEM CONFIRMAÇÃO OFICIAL": "ALERTA", "SABEDORIA DO DIA": "NAVY",
}
BLOCOS = ["Magistratura Estadual", "Magistratura Federal", "Promotor de Justiça (Estadual)",
          "MPF/MPU — Procurador da República", "PFN", "AGU — Advogado da União",
          "Procurador do Estado (PGE)", "Procurador do Município (PGM)",
          "Defensor Público Estadual (DPE)", "Defensor Público Federal (DPU)"]
APOIO = "Quadro de apoio"
ORDEM_SELO = ["ENCERRA HOJE", "ENCERRA EM BREVE", "INSCRIÇÕES ABERTAS", "EDITAL PUBLICADO",
              "PROVA EM BREVE", "EM ANDAMENTO", "INSCRIÇÕES ENCERRADAS", "PROVA REALIZADA",
              "EM PLANEJAMENTO", "PENDÊNCIA DE VERIFICAÇÃO", "PENDÊNCIA"]
COMPACTAR_APOS = 14          # dias sem verificacao: linha compacta ate o rodizio alcancar
RADAR_DIAS = 30
RADAR_A_CONFIRMAR = True     # prazos so em fonte secundaria entram no quadro, em cinza e rotulados

# secoes de noticia, na ordem do e-mail: (categoria, titulo, linha de apoio quando vazia)
SECOES = [
    ("Planalto/Legislação", "🏛️ Planalto — Resenha Diária e legislação federal", None),
    ("STF Notícias", "⚖️ STF — Notícias", "Nenhuma notícia do STF chegou pelo Push STF nesta janela."),
    ("STF Jurisprudência", "⚖️ STF — Jurisprudência",
     "Nenhum boletim de Repercussão Geral em Pauta na janela; decisões do STF noticiadas só pela mídia "
     "estão em Se saiu na mídia não é fofoca!"),
    ("STJ Notícias", "⚖️ STJ — Notícias",
     "O STJ da janela chegou só pela mídia — ver Se saiu na mídia não é fofoca!"),
    ("STJ Jurisprudência", "⚖️ STJ — Jurisprudência", "Sem teses do CodJu na janela; ver Informativos."),
    ("Informativos", "📚 Informativos",
     "Nenhuma edição nova de informativo (STF, Repercussão Geral em Pauta ou STJ) nesta janela — "
     "a cadência é semanal."),
]
CATEGORIAS_NOTICIA = [c for c, _, _ in SECOES] + ["Mídia", "Opinião/Análise", "Fofoquinha"]
INDICE = ("Planalto/Legislação · STF Notícias · STF Jurisprudência · STJ Notícias · STJ Jurisprudência · "
          "Informativos · Concursos – Carreira · Concursos – Apoio · Se saiu na mídia não é fofoca! · "
          "FOFOQUINHA JURÍDICA · Porque sem Deus, nada é possível · Conhecimento nunca é demais · Pendências.")
FRASE_PLANALTO = "isso aqui só existe porque eles não param de inventar moda..."
ROTULO_FONTE = {  # id do source_status -> como aparece em "Fontes consultadas"
    "gmail_push_stf": "Push STF (notícias)", "gmail_push_stf_informativos": "Push STF (informativos)",
    "gmail_stj_codju": "STJ CodJu", "gmail_push_planalto": "PUSH Planalto (Resenha Diária)",
    "gmail_camara": "boletim da Agência Câmara", "congresso_ultimas_leis": "Congresso Nacional (últimas leis)",
    "congresso_mpvs": "Congresso Nacional (medidas provisórias)",
    "gmail_jota": "JOTA (clipping, opinião e bastidores)", "conjur": "ConJur (mídia especializada)",
    "migalhas": "Migalhas (mídia especializada)", "youversion": "YouVersion (versículo)",
    "dailyverses": "DailyVerses.net (versículo)",
}
OFICIAIS = ["gmail_push_planalto", "congresso_ultimas_leis", "congresso_mpvs", "gmail_camara",
            "gmail_push_stf", "gmail_push_stf_informativos", "gmail_stj_codju"]
SECUNDARIAS = ["gmail_jota", "conjur", "migalhas", "youversion", "dailyverses"]
WRAPPER = re.compile(r"t\.rdsv2\.net|google\.com/url|[?&]utm_")
MESES = {m: i + 1 for i, m in enumerate("janeiro fevereiro março abril maio junho julho agosto setembro "
                                        "outubro novembro dezembro".split())}
DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]


# ------------------------------------------------------------------ utilitarios
def ler(caminho, padrao=None):
    try:
        with open(caminho, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return padrao


def esc(s):
    """Texto -> HTML. So <b>, <i> e <br> escritos pelo orquestrador sobrevivem."""
    t = html.escape(str(s or ""), quote=False)
    return re.sub(r"&lt;(/?(?:b|i)|br ?/?)&gt;", r"<\1>", t)


def attr(u):
    return html.escape(str(u or ""), quote=True)


def slug(s, n=60):
    t = unicodedata.normalize("NFKD", str(s or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:n].strip("-")


def ponto(s):
    """'texto' -> 'texto.' sem duplicar a pontuacao final."""
    s = (s or "").strip()
    return s if not s or s[-1] in ".!?…”\"" or s.endswith(("</b>", "</i>")) else s + "."


def br_data(iso, ano=False):
    try:
        d = date.fromisoformat((iso or "")[:10])
    except ValueError:
        return ""
    return d.strftime("%d/%m/%Y" if ano else "%d/%m")


def selo(texto, pequeno=False):
    if texto not in SELO_ESTILO:
        raise SystemExit("ERRO: selo fora da lista fechada: %r" % texto)
    return ('<b style="%s;font-size:%dpx;padding:2px %dpx;border-radius:3px;white-space:nowrap">%s</b>'
            % (ESTILO[SELO_ESTILO[texto]], 9 if pequeno else 10, 6 if pequeno else 7, esc(texto)))


def link(url, texto, extra=""):
    if not url:
        return texto
    return '<a href="%s" style="color:%s%s">%s</a>' % (attr(url), LINK, extra, texto)


def h2(titulo):
    return ('<div style="border-left:4px solid %s;padding-left:10px;font-size:16px;line-height:22px;'
            'font-weight:bold;color:%s;margin-bottom:10px">%s</div>' % (OURO, NAVY, titulo))


def secao(titulo, corpo, topo=22):
    return ('<tr><td style="padding:%dpx 20px 0;%s;font-size:13px;line-height:19px;color:%s">%s\n%s</td></tr>'
            % (topo, FONTE, TEXTO, h2(titulo), corpo))


def apoio(texto):
    return '<div style="font-size:12px;line-height:18px;color:%s">%s</div>' % (APOIO_COR, esc(texto))


# ------------------------------------------------------------------ 1. evidencia e refs
def evidencias():
    """{id: registro} do que os scripts do passo 2 coletaram."""
    ev = {}
    for bloco in ler("/tmp/coleta_web.json", []) or []:
        for it in bloco.get("itens") or []:
            if it.get("id"):
                ev[it["id"]] = dict(it, _fonte=bloco.get("fonte"))
    for r in ler("/tmp/informativos.json", []) or []:
        if r.get("id"):
            ev[r["id"]] = dict(r, _fonte="informativo")
    return ev


def data_extenso(s):
    """'4 a 9 de novembro de 2026' -> '2026-11-09' (ultima data do texto)."""
    datas = re.findall(r"(\d{1,2}) de (%s) de (\d{4})" % "|".join(MESES), s or "")
    if not datas:
        return ""
    d, m, a = datas[-1]
    return "%s-%02d-%02d" % (a, MESES[m], int(d))


NOME_INF = {"stf": "Informativo STF nº %d", "rg": "Repercussão Geral em Pauta nº %d",
            "stj": "Informativo STJ nº %d"}


MINUSCULAS = {"de", "da", "do", "das", "dos", "e", "em", "a", "o", "à", "ao"}


def caixa_titulo(s):
    """'DIREITO DO CONSUMIDOR' -> 'Direito do Consumidor'."""
    p = (s or "").lower().split()
    return " ".join(w if (n and w in MINUSCULAS) else w[:1].upper() + w[1:] for n, w in enumerate(p))


def limpo(s):
    """Espacos que a extracao do documento deixa antes de pontuacao e dentro de parenteses."""
    s = re.sub(r"\s+([,.;:)])", r"\1", s or "")
    return re.sub(r"\(\s+", "(", s).strip()


def texto_destaque(tipo, d):
    if tipo == "stf":
        return "<b>%s</b> — %s" % (esc(caixa_titulo(d["ramo"])), esc(ponto(limpo(d["titulo"]))))
    if tipo == "rg":
        tese = (" <i>Tese:</i> " + esc(limpo(d["tese"]))) if d.get("tese") else ""
        return "<b>Tema %s</b> (%s) — %s%s" % (esc(d["tema"]), esc(limpo(d["processo"])),
                                               esc(ponto(limpo(d["titulo"]))), tese)
    return "<b>%s</b> — %s <i>%s</i>" % (esc(caixa_titulo(d["ramo"])), esc(ponto(limpo(d["destaque"]))),
                                         esc(ponto(limpo(d["processo"]))))


def resolver(it, ev, erros):
    """Completa o item com a evidencia do ref. Campo escrito pelo orquestrador vence."""
    ref = it.get("ref")
    if not ref:
        return it
    e = ev.get(ref)
    base = {}
    m = re.fullmatch(r"(stf|rg|stj)(\d+)", ref)
    if e and e["_fonte"] == "congresso_leis":
        n = int(e["numero"])
        veto = "; com veto — %s" % e["veto"] if e.get("veto") else ""
        base = {"categoria": "Planalto/Legislação", "status": "CONFIRMADO POR FONTE OFICIAL ALTERNATIVA",
                "titulo": "%s nº %s, de %s" % (e["tipo"], "{:,}".format(n).replace(",", "."), e["data_ato"]),
                "meta": "DOU %s%s" % (e["dou"][:5], veto), "resumo": e["ementa"], "url": e["url"],
                "data": datetime.strptime(e["data_ato"], "%d/%m/%Y").date().isoformat(),
                "fonte": "Congresso Nacional", "grupo": "Congresso Nacional — últimas leis publicadas",
                "chave": e["chave"]}
    elif e and e["_fonte"] == "congresso_mpv":
        n = int(e["numero"])
        dou = e.get("dou") or ""
        base = {"categoria": "Planalto/Legislação",
                "status": "CONFIRMADO POR FONTE OFICIAL ALTERNATIVA" if dou else "PENDÊNCIA DE VERIFICAÇÃO",
                "titulo": "Medida Provisória nº %s/%s" % ("{:,}".format(n).replace(",", "."), e["ano"]),
                "meta": ("DOU %s" % dou[:5]) if dou else "data do DOU não confirmada na página oficial",
                "resumo": e["ementa"], "url": e["url"], "fonte": "Congresso Nacional",
                "data": datetime.strptime(dou, "%d/%m/%Y").date().isoformat() if dou else "",
                "grupo": "Congresso Nacional — medidas provisórias", "chave": e["chave"] if dou else ""}
    elif e and e["_fonte"] in ("conjur", "migalhas"):
        veic = "ConJur" if e["_fonte"] == "conjur" else "Migalhas"
        q = e.get("quando") or ""
        dia = (q or str(e.get("data") or ""))[:10]
        opiniao = e.get("tipo") in ("artigo", "coluna")
        mid = re.search(r"/quentes/(\d+)/", e["url"])
        sl = (mid.group(1) + "-" if mid else "") + slug(e["url"].rstrip("/").rsplit("/", 1)[-1], 50)
        base = {"categoria": "Opinião/Análise" if opiniao else "Mídia",
                "status": "OPINIÃO/ANÁLISE" if opiniao else "MÍDIA ESPECIALIZADA",
                "titulo": e["titulo"], "resumo": "" if opiniao else (e.get("resumo") or ""),
                "url": e["url"], "fonte": veic, "data": dia, "hora": q[11:16] if len(q) > 15 else "",
                "chave": "%s|%s|%s|%s|%s" % (e["_fonte"], "opiniao" if opiniao else "noticia", sl, dia[:4], dia)}
    elif e and e["_fonte"] == "informativo" and e.get("ok"):
        idx = it.get("destaques")
        if idx is None:
            idx = list(range(min(6, len(e["itens"]))))
        ruins = [i for i in idx if not isinstance(i, int) or not 0 <= i < len(e["itens"])]
        if ruins:
            erros.append("ref %s: destaques %s fora de 0..%d" % (ref, ruins, len(e["itens"]) - 1))
            idx = [i for i in idx if i not in ruins]
        base = {"categoria": "Informativos", "status": "CONFIRMADO POR FONTE OFICIAL",
                "titulo": NOME_INF[e["tipo"]] % e["numero"], "meta": e.get("data") or "",
                "url": e["url"], "data": data_extenso(e.get("data")),
                "fonte": "STJ — página oficial do informativo" if e["tipo"] == "stj" else "STF — documento oficial",
                "chave": e["chave"], "destaques_texto": [texto_destaque(e["tipo"], e["itens"][i]) for i in idx],
                "observacao": "%d de %d destaques publicados" % (len(idx), len(e["itens"])),
                "herdada": e.get("situacao") in ("atrasada", "pulada")}
    elif m:
        # edicao anunciada por e-mail cujo documento nao abriu: numero, data e link, sem destaques
        tipo, n = m.group(1), int(m.group(2))
        dia = it.get("data") or ""
        base = {"categoria": "Informativos", "status": "CONFIRMADO POR FONTE OFICIAL",
                "titulo": NOME_INF[tipo] % n, "sem_conteudo": True,
                "fonte": "STJ CodJu" if tipo == "stj" else "Push STF Informativo",
                "resumo": "Conteúdo não acessível nesta execução; os destaques entram quando o documento abrir.",
                "chave": "%s|informativo|%s%d|%s|%s" % ("stj" if tipo == "stj" else "stf",
                                                       "repercussao-geral-" if tipo == "rg" else "", n,
                                                       dia[:4], dia)}
        if not dia:
            erros.append("ref %s: documento não lido pelo script — informe \"data\" (AAAA-MM-DD do e-mail) "
                         "e \"url\" (link do e-mail)" % ref)
    else:
        erros.append("ref desconhecido: %r (use um id impresso por coleta_web.py ou informativos.py)" % ref)
        return None
    novo = dict(base)
    novo.update({k: v for k, v in it.items() if k not in ("destaques",) and v not in (None, "")})
    return novo


SELO_PADRAO = {"STF Notícias": "CONFIRMADO POR FONTE OFICIAL", "STF Jurisprudência": "CONFIRMADO POR FONTE OFICIAL",
               "STJ Notícias": "CONFIRMADO POR FONTE OFICIAL", "STJ Jurisprudência": "CONFIRMADO POR FONTE OFICIAL",
               "Informativos": "CONFIRMADO POR FONTE OFICIAL", "Mídia": "MÍDIA ESPECIALIZADA",
               "Opinião/Análise": "OPINIÃO/ANÁLISE"}
ATO = re.compile(r"^(Lei Complementar|Lei|Decreto Legislativo|Decreto|Medida Provis[óo]ria|Emenda Constitucional|"
                 r"Resolu[çc][ãa]o|Portaria)\s+n[ºo°.]*\s*([\d.]+)", re.I)
TIPO_CHAVE = {"Planalto/Legislação": "ato", "STF Notícias": "noticia", "STF Jurisprudência": "tese",
              "STJ Notícias": "noticia", "STJ Jurisprudência": "tese", "Informativos": "informativo",
              "Mídia": "noticia", "Opinião/Análise": "opiniao", "Fofoquinha": "fofoca"}


def chave_auto(it):
    """fonte|tipo|slug|ano|data quando o orquestrador nao escreveu a chave."""
    dia = it.get("data") or ""
    cat = it.get("categoria")
    m = ATO.match(it.get("titulo") or "")
    if cat == "Planalto/Legislação" and m:
        tipo = slug(m.group(1))
        tipo = "mpv" if tipo.startswith("medida-prov") else tipo
        return "planalto|%s|%s|%s|%s" % (tipo, m.group(2).replace(".", ""), dia[:4], dia)
    fonte = slug((it.get("fonte") or cat or "fonte").split("(")[0], 24) or "fonte"
    return "%s|%s|%s|%s|%s" % (fonte, TIPO_CHAVE.get(cat, "item"), slug(it.get("titulo"), 56), dia[:4], dia)


# ------------------------------------------------------------------ 2. ledger em memoria
def aplicar_concursos(concursos, upd):
    """Copia do registro com ledger_updates.concursos. Devolve (lista, novos, alterados)."""
    regs = copy.deepcopy(concursos)
    por_id = {c["id"]: c for c in regs}
    novos, alterados = set(), set()
    for ident, campos in (upd or {}).items():
        if campos.get("remover"):
            regs = [c for c in regs if c["id"] != ident]
            por_id.pop(ident, None)
            continue
        if ident in por_id:
            antes = dict(por_id[ident])
            por_id[ident].update({k: v for k, v in campos.items() if k != "desfecho"})
            # so verificado_em novo (RODIZIO IGUAL) nao e novidade para o leitor
            if any(antes.get(k) != v for k, v in campos.items() if k not in ("verificado_em", "desfecho")):
                alterados.add(ident)
        else:
            c = dict(campos, id=ident)
            regs.append(c)
            por_id[ident] = c
            novos.add(ident)
    return regs, novos, alterados


def aplicar_pendencias(vivas, upd):
    pend = copy.deepcopy(vivas)
    por_id = {p["id"]: p for p in pend}
    for ident, campos in (upd or {}).items():
        if campos.get("remover"):
            pend = [p for p in pend if p["id"] != ident]
        elif ident in por_id:
            por_id[ident].update({k: v for k, v in campos.items() if k != "desfecho"})
        else:
            pend.append(dict(campos, id=ident, _nova=True))
    return pend


def orgao(c):
    return (c.get("linha") or c.get("id") or "").split(":")[0].split(" — ")[0].strip()


# ------------------------------------------------------------------ 3. secoes do e-mail
def item_padrao(it):
    """Selo + titulo em negrito + resumo + fonte (com link) e data/hora."""
    quando = br_data(it.get("data"))
    if it.get("hora"):
        quando += " " + it["hora"]
    fonte = link(it.get("url"), esc(it.get("fonte") or "fonte"))
    cauda = ", ".join(x for x in (fonte, quando) if x)
    extras = "; ".join(x for x in (("herdada" if it.get("herdada") else ""), it.get("nota") or "",
                                   "" if it.get("url") else "sem link") if x)
    titulo = it["titulo"] + (" — " + it["meta"] if it.get("meta") else "")
    resumo = (esc(ponto(it["resumo"])) + " ") if it.get("resumo") else ""
    return '<p style="margin:0 0 12px">%s <b>%s</b> %s<i>Fonte: %s%s.</i></p>' % (
        selo(it["status"]), esc(ponto(titulo)), resumo, cauda, " (%s)" % esc(extras) if extras else "")


def sec_planalto(itens, ss, ex):
    if not itens:
        sem_push = ss.get("gmail_push_planalto") in ("vazio", "falha", "nao_tentada", None)
        corpo = apoio(ex["email"].get("apoio", {}).get("Planalto/Legislação") or (
            "PUSH Planalto não recuperado nesta execução; nenhuma lei ou medida provisória nova na página do "
            "Congresso." if sem_push else "Nenhum ato novo na janela (PUSH Planalto e página do Congresso "
                                          "consultados)."))
    else:
        partes, grupo = [], object()
        for n, it in enumerate(itens):
            g = it.get("grupo") or it.get("fonte") or ""
            if g != grupo:
                grupo = g
                partes.append('<div style="margin:%dpx 0 4px">%s <span style="font-size:12px;color:%s">— %s</span></div>'
                              % (14 if partes else 0, selo(it["status"]), APOIO_COR, esc(ponto(g))))
            ultimo = n + 1 == len(itens) or (itens[n + 1].get("grupo") or itens[n + 1].get("fonte") or "") != g
            meta = (' <span style="font-size:11px;color:%s">(%s)</span>' % (APOIO_COR, esc(it["meta"]))
                    if it.get("meta") else "")
            nota = (" <i>(%s)</i>" % esc(it["nota"])) if it.get("nota") else ""
            corpo_ato = ("<br>" + esc(ponto(it["resumo"]))) if it.get("resumo") else ""
            partes.append('<div style="padding:6px 0%s">%s%s%s%s</div>' % (
                "" if ultimo else ";border-bottom:1px solid " + LINHA,
                link(it.get("url"), "<b>%s</b>" % esc(it["titulo"]), ";text-decoration:underline"),
                meta, nota, corpo_ato))
        corpo = "\n".join(partes)
    frase = ('<div style="font-size:12px;color:#8a8f5c;font-style:italic;margin:-4px 0 12px 14px">%s</div>'
             % FRASE_PLANALTO)
    return secao("🏛️ Planalto — Resenha Diária e legislação federal", frase + "\n" + corpo)


def sec_itens(cat, titulo, vazio, itens, ex):
    if not itens:
        return secao(titulo, apoio(ex["email"].get("apoio", {}).get(cat) or vazio))
    partes = []
    for it in itens:
        partes.append(item_padrao(it))
        if it.get("destaques_texto"):
            partes[-1] = partes[-1].replace("margin:0 0 12px", "margin:0 0 6px", 1)
            partes.append('<div style="margin:0 0 14px 14px;font-size:12px;line-height:18px">%s</div>' % "\n".join(
                '<p style="margin:0 0 6px">▸ %s</p>' % d for d in it["destaques_texto"]))
    return secao(titulo, "\n".join(partes))


def partes_linha(linha):
    """'Órgão — Cargo: detalhes' -> ('Órgão — Cargo', 'detalhes'); sem ':' antes do 1º ';', corta no ' — '."""
    cabeca = linha.split(";")[0]
    m = re.match(r"^(.{2,110}?):\s+(.+)$", cabeca)
    if m:
        return m.group(1), linha[len(m.group(1)) + 1:].strip()
    if " — " in cabeca:
        a, b = linha.split(" — ", 1)
        return a.strip(), b.strip()
    return "", linha


def linha_concurso(c, hoje, novos, alterados, zebra):
    """Uma linha: órgão — cargo em negrito + selo; abaixo, os detalhes. Novidade em fundo creme."""
    try:
        ver = date.fromisoformat(c.get("verificado_em", ""))
    except ValueError:
        ver = None
    idade = (hoje - ver).days if ver else 999
    linha = (c.get("linha") or "").rstrip(".")
    novo, mudou = c["id"] in novos, c["id"] in alterados and idade == 0
    if idade > COMPACTAR_APOS and not novo:
        linha = linha.split(";")[0]
    cabeca, corpo = partes_linha(linha)
    corpo = corpo[:1].upper() + corpo[1:]
    selos = (selo("NOVO", True) + " " if novo else "") + selo(c.get("selo"), True)
    marca = '<b style="color:#8a6d1d">Atualizado hoje:</b> ' if mudou else ""
    cauda = "" if idade == 0 else " <i>(herdada; verificado em %s)</i>" % (ver.strftime("%d/%m") if ver else "?")
    fundo = ' bgcolor="#fdf6e9"' if (novo or mudou) else (' bgcolor="#f4f6fa"' if zebra else "")
    topo = ("<b>%s</b> " % esc(cabeca)) if cabeca else ""
    return "<tr%s><td>%s%s<br>%s%s.%s</td></tr>" % (fundo, topo, selos, marca, esc(corpo), cauda)


TABELA_CONCURSOS = ('<table width="100%" cellpadding="7" cellspacing="0" style="border-collapse:collapse;'
                    'font-size:12px;line-height:18px">')


def bloco_concursos(nome, regs, hoje, novos, alterados, primeiro):
    out = [] if primeiro else ["<tr><td></td></tr>"]
    out.append('<tr><td bgcolor="%s" style="color:#ffffff;font-weight:bold;font-size:11px">%s</td></tr>'
               % (NAVY, esc(nome)))
    if not regs:
        out.append('<tr><td style="color:%s">Nenhum concurso acompanhado neste bloco; a varredura de descoberta '
                   'segue no rodízio semanal.</td></tr>' % APOIO_COR)
    out += [linha_concurso(c, hoje, novos, alterados, n % 2) for n, c in enumerate(regs)]
    return out


def prazos(regs, hoje):
    itens = []
    for c in regs:
        for pz in c.get("prazos") or []:
            try:
                d = date.fromisoformat(pz.get("data", ""))
            except ValueError:
                continue
            if 0 <= (d - hoje).days <= RADAR_DIAS:
                itens.append((d, (d - hoje).days, c, pz))
    return sorted(itens, key=lambda x: (x[0], not x[3].get("confirmado")))


def quando_txt(n):
    return {0: "hoje", 1: "amanhã"}.get(n, "em %d dias" % n)


def radar(regs, hoje):
    itens = prazos(regs, hoje)
    conf = [x for x in itens if x[3].get("confirmado")]
    aconf = [x for x in itens if not x[3].get("confirmado")] if RADAR_A_CONFIRMAR else []
    if not conf and not aconf:
        return ""

    def linhas(lista, confirmado):
        out = []
        for d, dias, c, pz in lista:
            cor = ("#a61b1b" if dias <= 7 else NAVY) if confirmado else APOIO_COR
            evento = re.sub(r"\s*\((?:fonte )?secund[áa]ria[^)]*\)", "", pz.get("evento") or "")
            out.append('<tr><td width="118" valign="top" style="padding:3px 0;font-weight:bold;color:%s;'
                       'white-space:nowrap">%s · %s</td><td style="padding:3px 0%s">%s — %s</td></tr>' % (
                           cor, d.strftime("%d/%m"), quando_txt(dias), "" if confirmado else ";color:" + APOIO_COR,
                           esc(orgao(c)), esc(evento)))
        return out
    tab = ('<table width="100%%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;font-size:12px;'
           'line-height:17px;color:%s">' % TEXTO)
    out = ['<div style="background:#fdf6e9;border-left:4px solid %s;padding:10px 12px;margin-bottom:12px">' % OURO,
           '<div style="font-size:12px;font-weight:bold;color:%s;margin-bottom:6px">⏰ Prazos no radar '
           '<span style="font-weight:normal;color:%s">· próximos %d dias</span></div>' % (NAVY, APOIO_COR, RADAR_DIAS)]
    if conf:
        out += [tab] + linhas(conf, True) + ["</table>"]
    if aconf:
        out.append('<div style="font-size:11px;color:%s;margin:%dpx 0 2px">A confirmar — data vista só em fonte '
                   'secundária:</div>' % (APOIO_COR, 8 if conf else 0))
        out += [tab] + linhas(aconf, False) + ["</table>"]
    out.append("</div>")
    return "\n".join(out)


def sec_concursos(regs, hoje, novos, alterados):
    def do_bloco(b):
        return sorted((c for c in regs if c.get("bloco") == b),
                      key=lambda c: (c["id"] not in novos,
                                     ORDEM_SELO.index(c.get("selo")) if c.get("selo") in ORDEM_SELO else 99))
    carreira = [radar(regs, hoje), TABELA_CONCURSOS]
    for n, b in enumerate(BLOCOS):
        carreira += bloco_concursos(b, do_bloco(b), hoje, novos, alterados, n == 0)
    carreira.append("</table>")
    apoio_html = [TABELA_CONCURSOS] + bloco_concursos(
        "Analista e técnico (TJ, TRF, TRT, MP, Defensoria)", do_bloco(APOIO), hoje, novos, alterados, True) + ["</table>"]
    return (secao("💼 Concursos jurídicos — Carreira jurídica", "\n".join(x for x in carreira if x)) + "\n" +
            secao("🗂️ Concursos jurídicos — Quadro de apoio", "\n".join(apoio_html)))


def sec_midia(midia, opiniao, ex, ev):
    usados = {it.get("ref") for it in ex["items"] if it.get("ref")}
    sobra = {"conjur": 0, "migalhas": 0}
    for e in ev.values():
        if e.get("_fonte") in sobra and e.get("situacao") in ("NOVA", "HERDADA") and e["id"] not in usados:
            sobra[e["_fonte"]] += 1
    partes = [item_padrao(it) for it in midia] or [apoio(ex["email"].get("apoio", {}).get("Mídia")
                                                         or "Nenhuma matéria selecionada nesta janela.")]
    mais = [link(u, "%s (%d)" % (n, sobra[k])) for k, n, u in (
        ("conjur", "ConJur", "https://conjur.com.br/noticias/"),
        ("migalhas", "Migalhas", "https://www.migalhas.com.br/quentes")) if sobra[k]]
    if mais:
        partes.append('<p style="margin:0;font-size:12px;color:%s">Ver mais, entre as outras matérias da janela: '
                      '%s.</p>' % (APOIO_COR, " · ".join(mais)))
    if opiniao:
        partes.append('<p style="margin:14px 0 6px;font-size:12px;font-weight:bold;color:%s">Opinião/Análise</p>' % NAVY)
        for it in opiniao:
            quem = " — ".join(x for x in (esc(it.get("autor") or ""),) if x)
            onde = ", ".join(x for x in (esc(it.get("fonte") or ""), br_data(it.get("data"))) if x)
            partes.append('<p style="margin:0 0 6px;font-size:12px;line-height:18px">%s %s%s (%s%s).</p>' % (
                selo("OPINIÃO/ANÁLISE", True),
                link(it.get("url"), esc(it["titulo"])) if it.get("url") else "“%s”" % esc(it["titulo"]),
                (" — " + quem) if quem else "", onde, "" if it.get("url") else "; sem link próprio"))
    return secao("📰 Se saiu na mídia não é fofoca!", "\n".join(partes))


def caixa(fundo, corpo):
    return '<div style="background:%s;padding:14px 16px">%s</div>' % (fundo, corpo)


def sec_versiculo(v, reflexao):
    if not v or not v.get("ok"):
        return secao("🙏 Porque sem Deus, nada é possível", apoio(
            "Versículo do dia não recuperado nesta execução (fontes indisponíveis); a seção volta na próxima edição."))
    corpo = ('%s<p style="margin:8px 0 6px;font-size:14px;line-height:21px;color:#3d3113;font-style:italic">“%s”</p>'
             '<p style="margin:0 0 10px;font-size:12px;color:#8a6d1d;font-weight:bold">%s (%s) — %s, confirmado '
             'para %s</p><p style="margin:0;font-size:12px;line-height:18px;color:%s">%s</p>' % (
                 selo("VERSÍCULO DO DIA"), esc(v["texto"]), esc(v["referencia"]), esc(v.get("versao") or ""),
                 '<a href="%s" style="color:#8a6d1d">%s</a>' % (attr(v.get("url")), esc(v["fonte"])),
                 br_data(v.get("data_pagina"), True), APOIO_COR, esc(reflexao)))
    return secao("🙏 Porque sem Deus, nada é possível", caixa("#fdf6e9", corpo))


def sec_munger(m):
    obs = (" · " + esc(m["obs"])) if m.get("obs") else ""
    corpo = ('%s<p style="margin:8px 0 6px;font-size:14px;line-height:21px;color:%s;font-style:italic">“%s”</p>'
             '<p style="margin:0;font-size:12px;color:%s">— Charlie Munger · <i>%s</i>%s</p>' % (
                 selo("SABEDORIA DO DIA"), TEXTO, esc(m["texto"]), APOIO_COR, esc(m["fonte"]), obs))
    return secao("💡 Conhecimento nunca é demais", caixa("#f4f6fa", corpo))


def fontes_consultadas(ss, ex, v):
    def lista(ids):
        usados, out = set(), []
        for i in ids:
            st = ss.get(i)
            if st in (None, "nao_tentada"):
                continue
            rot = ROTULO_FONTE[i]
            if i.startswith("congresso_"):
                rot = "Congresso Nacional (últimas leis e MPVs)"
            if rot in usados:
                continue
            usados.add(rot)
            out.append(rot + {"falha": " — falhou", "vazio": " — sem e-mail na janela"}.get(st, ""))
        return out
    of = lista(OFICIAIS)
    if any(it.get("destaques_texto") for it in ex["items"]):
        of.append("documentos oficiais dos informativos (STF/STJ)")
    if ex["email"].get("fontes_extra"):
        of.append(esc(ex["email"]["fontes_extra"]))
    sec = lista(SECUNDARIAS) + ["portais e blogs de concursos (prazos e editais, sempre sujeitos a confirmação oficial)"]
    sub = '<div style="font-size:14px;font-weight:bold;color:%s;margin:%dpx 0 6px">%s</div>'
    est = '<div style="font-size:12px;line-height:19px;color:#3d4b59">%s</div>'
    return (sub % (NAVY, 0, "Fontes oficiais consultadas") + est % (" · ".join(of) or "nenhuma respondeu") +
            sub % (NAVY, 14, "Fontes secundárias consultadas") + est % " · ".join(sec))


def sec_pendencias(pend, regs, ex, ss):
    # errata: a de hoje vem em email.errata; a herdada do ledger (errata_*) sai uma vez e e removida
    errata = [p for p in pend if p["id"].startswith("errata_") and not p.get("_nova")]
    if ex["email"].get("errata"):
        errata.insert(0, {"id": "errata_hoje", "texto": ex["email"]["errata"]})
    linhas = [esc(o) for o in ex["email"].get("observacoes") or []]
    falhas = [ROTULO_FONTE.get(i, i) for i, st in ss.items() if st == "falha"]
    if falhas and not linhas:
        linhas.append("Falha técnica nesta execução: " + "; ".join(falhas) + ".")
    ids_conc = {c.get("pendencia") for c in regs if c.get("pendencia")}
    for p in pend:
        if p["id"].startswith("errata_") or p["id"] in ids_conc or p.get("faixa") == "cronica":
            continue
        linhas.append(esc(ponto(p.get("texto"))))
    aguardando = sorted({orgao(c) for c in regs if c.get("selo") in ("PENDÊNCIA DE VERIFICAÇÃO", "PENDÊNCIA")})
    if aguardando:
        linhas.append("Concursos com confirmação oficial pendente (%d): %s — detalhes na seção de Concursos."
                      % (len(aguardando), ", ".join(esc(a) for a in aguardando)))
    out = ['<div style="font-size:14px;font-weight:bold;color:%s;margin:14px 0 6px">📋 Observações de verificação, '
           'lacunas e pendências</div>' % NAVY]
    for p in errata:
        out.append('<div style="background:#fdf0f0;border:1px solid #f0c2c2;color:#5c1a1a;padding:10px 12px;'
                   'margin-bottom:8px;font-size:12px;line-height:19px"><b>Errata:</b> %s</div>'
                   % esc(re.sub(r"^Errata[^:]*:\s*", "", p.get("texto") or "")))
    out.append('<div style="background:#fdf6e9;border:1px solid #e6d3a3;padding:10px 12px;font-size:12px;'
               'line-height:19px;color:#3d4b59">%s</div>'
               % ("<br>".join("• " + l for l in linhas) or "Sem pendências registradas nesta execução."))
    return "\n".join(out)


def janela_txt(j, limitacoes):
    ini, fim = datetime.fromisoformat(j["inicio"]), datetime.fromisoformat(j["fim"])
    dias = (fim.date() - ini.date()).days
    rot = "ontem" if dias == 1 else ("hoje" if dias == 0 else DIAS[ini.weekday()])
    hm = lambda d: "%dh%02d" % (d.hour, d.minute)
    fds = any((ini.date().toordinal() + n) % 7 in (5, 6) for n in range(1, dias))   # sabado/domingo no meio
    t = "Janela de cobertura: das %s de %s (%s) às %s de hoje (%s)%s, fuso América/São Paulo." % (
        hm(ini), rot, ini.strftime("%d/%m"), hm(fim), fim.strftime("%d/%m/%Y"),
        ", cobrindo o fim de semana" if fds else "")
    if limitacoes:
        t += " Limitações: " + ponto(limitacoes)
    return t


# ------------------------------------------------------------------ 4. montagem
def montar(ex, j, led, ev, v, agora):
    hoje = date.fromisoformat(j["data"])
    em = ex["email"]
    ss = ex.get("source_status") or {}
    upd = ex.get("ledger_updates") or {}
    regs, novos, alterados = aplicar_concursos(led.get("concursos") or [], upd.get("concursos"))
    pend = aplicar_pendencias(led.get("pendencias_vivas") or [], upd.get("pendencias"))
    por_cat = {}
    for it in ex["items"]:
        por_cat.setdefault(it["categoria"], []).append(it)

    pre = ('<div style="display:none;font-size:1px;color:#eef1f4;line-height:1px;max-height:0;max-width:0;opacity:0;'
           'overflow:hidden">%s%s</div>' % (esc(em["preheader"]), "&#847;&zwnj;&nbsp;" * 12))
    cab = ('<tr><td bgcolor="%s" align="center" style="padding:26px 20px;%s">'
           '<div style="font-size:34px;line-height:38px;margin-bottom:6px">🤖📜</div>'
           '<div style="font-size:22px;line-height:28px;color:#ffffff;font-weight:bold">Robozinho dos Momozis até Passar</div>'
           '<div style="font-size:13px;line-height:19px;color:%s;font-weight:bold;margin-top:8px">Legislação, '
           'jurisprudência e concursos jurídicos sem drama. Ou quase.</div>'
           '<div style="font-size:12px;line-height:17px;color:#a9b7cc;margin-top:10px">Edição das 7h · %s (%s) · '
           'América/São Paulo</div></td></tr>' % (NAVY, FONTE, OURO, j["hoje_br"], j["dia_semana"]))
    indice = ('<tr><td bgcolor="#f4f6fa" style="padding:14px 20px;%s;font-size:12px;line-height:20px;color:%s">'
              '<b>Nesta edição:</b> %s</td></tr>' % (FONTE, NAVY, INDICE))
    cards = "\n".join(
        '<div style="background:#f4f6fa;border-left:4px solid %s;padding:10px 12px;margin-bottom:8px">'
        '<b>%s %s:</b> %s</div>' % (NAVY, esc(c[0]), esc(c[1].rstrip(":")), esc(ponto(c[2]))) for c in em["resumo"])
    resumo = secao("Resumo executivo", cards, 20)
    janela = ('<tr><td style="padding:10px 20px 0;%s;font-size:12px;line-height:18px;color:%s"><i>%s</i></td></tr>'
              % (FONTE, APOIO_COR, esc(janela_txt(j, em.get("limitacoes")))))
    divisor = ('<tr><td style="padding:16px 20px 0"><div style="border-top:1px solid #e4e9ef;font-size:1px;'
               'line-height:1px">&nbsp;</div></td></tr>')

    corpo = [sec_planalto(por_cat.get("Planalto/Legislação", []), ss, ex)]
    for cat, titulo, vazio in SECOES[1:]:
        corpo.append(sec_itens(cat, titulo, vazio, por_cat.get(cat, []), ex))
    corpo.append(sec_concursos(regs, hoje, novos, alterados))
    corpo.append(sec_midia(por_cat.get("Mídia", []), por_cat.get("Opinião/Análise", []), ex, ev))
    corpo.append(sec_itens("Fofoquinha", "🤫 FOFOQUINHA JURÍDICA",
                           "Nenhuma fofoquinha jurídica relevante localizada nesta execução.",
                           por_cat.get("Fofoquinha", []), ex))
    corpo.append(sec_versiculo(v, em.get("reflexao") or ""))
    corpo.append(sec_munger(j["munger"]))
    corpo.append('<tr><td style="padding:22px 20px 0;%s">%s\n%s</td></tr>' % (
        FONTE, fontes_consultadas(ss, ex, v), sec_pendencias(pend, regs, ex, ss)))
    rodape = ('<tr><td style="padding:22px 0 0"><div style="background:%s;padding:20px;%s;text-align:center">'
              '<div style="font-size:13px;color:#ffffff;font-weight:bold">🤖 Robozinho dos Momozis até Passar</div>'
              '<div style="font-size:11px;color:#a9b7cc;margin-top:6px;line-height:16px">Newsletter jurídica '
              'automatizada · conteúdo informativo, não substitui a consulta às fontes oficiais nem assessoria '
              'jurídica.<br>Próxima edição: %s, às 7h.</div></div></td></tr>' % (NAVY, FONTE, j["rodape"]))
    falhas = "; ".join(ex.get("errors") or [])
    suporte = em.get("suporte") or (
        "Coletores Gmail, JOTA e Concursos; scripts coleta_web, informativos, versiculo e montar_email. "
        + ("Falhas: " + falhas if falhas else "Sem falha técnica registrada."))
    sup = ('<tr><td style="padding:16px 20px 22px;%s"><div style="font-size:13px;font-weight:bold;color:%s;'
           'margin-bottom:6px">Suporte usado na execução</div><div style="font-size:11px;line-height:17px;color:%s">'
           '%s</div><div style="font-size:10px;line-height:15px;color:#8b95a1;margin-top:8px">Gerado em %s '
           '(América/São Paulo) · execução %s</div></td></tr>' % (
               FONTE, NAVY, APOIO_COR, esc(ponto(suporte)), agora.strftime("%d/%m/%Y %H:%M"), j["execution_id"]))
    miolo = [cab, indice, resumo, janela, divisor] + corpo + [rodape, sup]
    return (pre + '\n<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" '
            'bgcolor="#eef1f4" style="border-collapse:collapse"><tr><td align="center" style="padding:20px 8px">\n'
            '<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" bgcolor="#ffffff" '
            'style="width:100%;max-width:600px;border-collapse:collapse">\n' + "\n".join(miolo) +
            "\n</table>\n</td></tr></table>"), regs, novos, alterados, pend


# ------------------------------------------------------------------ 5. preparo e validacao
def preparar(ex, j, led, ev, v):
    """Resolve refs, completa campos deterministicos e devolve (erros, avisos)."""
    erros, avisos = [], []
    em = ex.setdefault("email", {})
    hoje = j["data"]
    itens = []
    descartar = segunda_tentativa(ex.get("items") or [], ev, avisos)
    for it in ex.get("items") or []:
        if it.get("ref") in descartar:
            continue
        it = resolver(dict(it), ev, erros)
        if it is None:
            continue
        if it.get("categoria") in ("Versículo", "Munger", "Concursos - Carreira", "Concursos - Apoio"):
            continue                    # gerados aqui; versao escrita a mao e descartada
        if it.get("categoria") not in CATEGORIAS_NOTICIA:
            erros.append("%s: categoria %r fora de %s" % ((it.get("titulo") or it.get("ref") or "item")[:50],
                                                          it.get("categoria"), " | ".join(CATEGORIAS_NOTICIA)))
            continue
        if not it.get("titulo"):
            erros.append("item sem titulo: %s" % json.dumps(it, ensure_ascii=False)[:120])
            continue
        if not it.get("status") and it.get("categoria") in SELO_PADRAO:
            it["status"] = SELO_PADRAO[it["categoria"]]
        if not it.get("status"):
            erros.append("%s: falta \"status\" (selo) — obrigatório em %s" % (it["titulo"][:60], it["categoria"]))
            continue
        if not it.get("data"):
            erros.append("%s: falta \"data\" (AAAA-MM-DD da fonte)" % it["titulo"][:60])
            continue
        if not it.get("chave"):
            it["chave"] = chave_auto(it)
        it.setdefault("url", "")
        it.setdefault("fonte", "")
        for campo in ("titulo", "resumo", "url", "nota", "meta", "grupo"):
            if WRAPPER.search(str(it.get(campo) or "")):
                erros.append("%s: wrapper/rastreio em %s" % (it["chave"], campo))
        itens.append(it)
    # concursos que mudaram hoje, versiculo e Munger: itens do historico gerados aqui
    upd = (ex.get("ledger_updates") or {}).get("concursos") or {}
    regs, novos, alterados = aplicar_concursos(led.get("concursos") or [], upd)
    for c in regs:
        if c["id"] in novos or c["id"] in alterados:
            cabeca, _ = partes_linha(c.get("linha") or "")
            fonte = c.get("fonte") or ""
            itens.append({"chave": "concurso|%s|%s|%s|%s" % (c["id"], "novo" if c["id"] in novos else "atualizado",
                                                             hoje[:4], hoje),
                          "fonte": "Coletor concursos",
                          "categoria": "Concursos - Apoio" if c.get("bloco") == APOIO else "Concursos - Carreira",
                          "titulo": cabeca or c["id"], "data": hoje, "status": c.get("selo"),
                          "url": fonte if fonte.startswith("http") and not WRAPPER.search(fonte) else "",
                          "observacao": (c.get("linha") or "")[:300]})
    if v and v.get("ok"):
        itens.append({"chave": "%s|versiculo|%s|%s|%s" % (slug(v["fonte"].split(".")[0], 20), slug(v["referencia"]),
                                                          hoje[:4], hoje),
                      "fonte": v["fonte"], "categoria": "Versículo", "status": "VERSÍCULO DO DIA",
                      "titulo": "%s (%s)" % (v["referencia"], v.get("versao") or ""), "data": hoje,
                      "url": v.get("url") or ""})
        if not em.get("reflexao"):
            erros.append("email.reflexao ausente (reflexão própria de 2–3 linhas ligada ao dia)")
    m = j.get("munger") or {}
    itens.append({"chave": "munger|citacao|%s|%s|%s" % (m.get("idx"), hoje[:4], hoje), "fonte": m.get("fonte") or "",
                  "categoria": "Munger", "status": "SABEDORIA DO DIA", "titulo": m.get("texto") or "", "data": hoje,
                  "url": ""})
    ex["items"] = itens
    # pendencias: as do ledger, ja com os updates de hoje (o orquestrador nao as redigita)
    pend = aplicar_pendencias(led.get("pendencias_vivas") or [], (ex.get("ledger_updates") or {}).get("pendencias"))
    ex["pendencias"] = [{"id": p["id"], "texto": p.get("texto", ""), "faixa": p.get("faixa", "")} for p in pend]
    # errata publicada sai do ledger sozinha
    for p in pend:
        if p["id"].startswith("errata_") and not p.get("_nova"):
            ex.setdefault("ledger_updates", {}).setdefault("pendencias", {}).setdefault(
                p["id"], {"remover": True, "desfecho": "Errata publicada na edição de %s." % br_data(hoje)})
    # e-mail
    if not (em.get("preheader") or "").strip():
        erros.append("email.preheader ausente (2–3 destaques do dia separados por ' · ')")
    cards = em.get("resumo") or []
    if not 3 <= len(cards) <= 5 or any(not isinstance(c, list) or len(c) != 3 for c in cards):
        erros.append("email.resumo: use de 3 a 5 cards no formato [emoji, título curto, frase]")
    op = [i for i in itens if i["categoria"] == "Opinião/Análise"]
    if len(op) > 6:
        erros.append("Opinião/Análise: %d itens (máximo 6)" % len(op))
    for cat in ("Planalto/Legislação", "STF Notícias", "Mídia", "Fofoquinha", "Informativos"):
        n = sum(1 for i in itens if i["categoria"] == cat)
        if n > 12:
            avisos.append("%s com %d itens (alvo ~10): corte os menos relevantes" % (cat, n))
    hj = date.fromisoformat(hoje)
    urgente = [x for x in prazos(regs, hj) if x[1] <= 7]
    if (urgente or novos) and not any(re.search(r"(?i)concurs|inscri|edital|prova", " ".join(c[1:]))
                                      for c in cards if isinstance(c, list)):
        avisos.append("há prazo de concurso em até 7 dias ou concurso novo e nenhum card do resumo executivo trata disso")
    return erros, avisos


def segunda_tentativa(itens, ev, avisos):
    """Informativo citado por ref cujo documento nao abriu no passo 2 (o servidor do STF recusa
    de forma intermitente): tenta mais uma vez agora, minutos depois. Abriu -> entra na evidencia
    e sai com destaques. Nao abriu -> edicao nova segue como numero/data/link; edicao que ja
    tinha sido anunciada sem destaques e descartada (devolvida no conjunto), sem repetir o aviso."""
    descartar = set()
    alvos = [(it["ref"], re.fullmatch(r"(stf|rg|stj)(\d+)", str(it.get("ref") or ""))) for it in itens
             if it.get("ref")]
    alvos = [(ref, m) for ref, m in alvos if m and not (ev.get(ref) or {}).get("ok")]
    if not alvos:
        return descartar
    try:
        import informativos
        pub = informativos.publicados()
    except Exception as e:  # noqa: BLE001 — a segunda tentativa e reforco, nunca bloqueia
        avisos.append("segunda tentativa dos informativos indisponível (%s)" % e)
        return descartar
    for ref, m in alvos:
        tipo, n = m.group(1), int(m.group(2))
        anunciada = pub.get(tipo, {}).get(n) is True
        try:
            r = informativos.obter(tipo, n, "atrasada" if anunciada else "nova")
        except Exception:  # noqa: BLE001
            r = {}
        if r.get("ok"):
            ev[ref] = dict(r, _fonte="informativo")
            avisos.append("%s: documento abriu na segunda tentativa — %d destaques (sem \"destaques\", saem os 6 "
                          "primeiros)" % (ref, len(r["itens"])))
        elif anunciada:
            descartar.add(ref)
            avisos.append("%s: documento segue sem abrir (http %s); já anunciado antes — fica para a próxima "
                          "execução" % (ref, r.get("http")))
    return descartar


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--execucao", default="/tmp/execucao.json")
    ap.add_argument("--janela", default="/tmp/janela.json")
    ap.add_argument("--ledger", default=os.path.join(AQUI, "robozinho-aprendizado.json"))
    ap.add_argument("--saida", default="/tmp/email.html")
    ap.add_argument("--sem-html", action="store_true", help="nao imprime o corpo (so valida e grava)")
    a = ap.parse_args()

    ex = ler(a.execucao)
    j = ler(a.janela)
    led = ler(a.ledger, {})
    if ex is None or j is None or "munger" not in j:
        sys.exit("ERRO: faltam %s ou %s (rode work/inicio.py e escreva o julgamento antes)" % (a.execucao, a.janela))
    ev = evidencias()
    v = ler("/tmp/versiculo.json", {})

    erros, avisos = preparar(ex, j, led, ev, v)
    if erros:
        print("\n".join("ERRO: " + e for e in erros))
        print("MONTAGEM: ERRO — corrija /tmp/execucao.json e rode de novo (nada foi gravado).")
        sys.exit(2)
    resolvido = a.execucao + ".resolvido"
    with open(resolvido, "w", encoding="utf-8") as f:
        json.dump(ex, f, ensure_ascii=False, indent=1)
    r = subprocess.run([sys.executable, os.path.join(AQUI, "Update-Historico.py"), "--validar", "--nova-execucao",
                        resolvido, "--ledger", a.ledger, "--janela", a.janela], capture_output=True, text=True)
    relatorio = [l for l in r.stdout.splitlines() if l.startswith(("ERRO", "AVISO", "VALIDACAO"))]
    print("\n".join(relatorio + ["AVISO: " + x for x in avisos]))
    if r.returncode != 0:
        print(r.stderr.strip()[-400:])
        print("MONTAGEM: ERRO — corrija /tmp/execucao.json e rode de novo (nada foi gravado).")
        sys.exit(2)

    try:
        from zoneinfo import ZoneInfo
        agora = datetime.now(ZoneInfo("America/Sao_Paulo"))
    except Exception:
        agora = datetime.now()
    corpo, regs, novos, alterados, pend = montar(ex, j, led, ev, v, agora)
    problemas = []
    if "{{" in corpo or re.search(r"__[A-Z_]{3,}__", corpo):
        problemas.append("marcador/placeholder no corpo")
    if WRAPPER.search(corpo):
        problemas.append("wrapper/rastreio no corpo")
    tamanho = len(corpo.encode("utf-8"))
    if tamanho > 100_000:
        problemas.append("corpo com %d bytes (> 100 KB: o Gmail corta) — reduza itens de Mídia/Opinião" % tamanho)
    if problemas:
        print("\n".join("ERRO: " + p for p in problemas))
        print("MONTAGEM: ERRO — corrija /tmp/execucao.json e rode de novo.")
        sys.exit(2)
    os.replace(resolvido, a.execucao)          # o passo 7 grava a versao resolvida
    with open(a.saida, "w", encoding="utf-8") as f:
        f.write(corpo)
    n_not = sum(1 for i in ex["items"] if i["categoria"] not in ("Concursos - Carreira", "Concursos - Apoio",
                                                                  "Versículo", "Munger"))
    print("MONTAGEM: OK — %d itens de notícia, %d concursos (%d novos, %d atualizados hoje), %d pendências, "
          "%d bytes → %s" % (n_not, len(regs), len(novos), len(alterados), len(pend), tamanho, a.saida))
    print("ASSUNTO: %s" % j["assunto"])
    print("PARA: %s" % json.dumps(DESTINATARIOS))
    if not a.sem_html:
        print("Copie para o htmlBody do create_draft o texto entre os dois marcadores, inteiro e sem alteração:")
        print("==== HTMLBODY ====")
        print(corpo)
        print("==== FIM HTMLBODY ====")


if __name__ == "__main__":
    main()
