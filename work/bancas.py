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
#
# Para cada concurso juridico do ano corrente (ou do anterior) na listagem:
#   - casa com o registro do ledger pela sigla (tjap26 -> tjap_juiz);
#   - lista os arquivos mais recentes (movimento oficial, com data);
#   - quando o registro ainda nao esta confirmado em fonte oficial (ou o
#     concurso e novo), baixa o edital e copia os trechos de vagas,
#     inscricoes, taxa, remuneracao e prova objetiva.
#
# USO:   python3 work/bancas.py [--janela /tmp/janela.json]   (chamado pelo inicio.py)
# SAIDA: bloco compacto em stdout; JSON em /tmp/bancas.json.
# =====================================================================

import argparse
import html
import json
import os
import re
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime

AQUI = os.path.dirname(os.path.abspath(__file__))
UA = "Mozilla/5.0 (X11; Linux x86_64) Robozinho/1.0"
BASE = "https://conhecimento.fgv.br"
JURIDICO = re.compile(r"Tribunal|Juiz|Magistratura|Procurador|Defensor|Minist[ée]rio P[úu]blico|"
                      r"Assembleia Legislativa|Advocacia|Promotor", re.I)
SUFIXOS = re.compile(r"(juiz|magistratura|servidor(es)?|analista|tecnico|promotor|defensor|procurador)$")
MES = "janeiro|fevereiro|março|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro"
DATA = r"\d{1,2}º?\s+de\s+(?:%s)\s+de\s+\d{4}" % MES
TRECHOS = [  # (rotulo, regex sobre o edital com espacos normalizados)
    ("vagas", r"provimento de \d+ \([^)]{1,40}\) vagas[^.;]{0,90}"),
    ("inscrições", r"das? \d{1,2}h(?:\d{2})?(?:min)? do dia %s at[ée] [àa]s \d{1,2}h(?:\d{2})?(?:min)? do dia %s" % (DATA, DATA)),
    ("taxa", r"taxa de inscrição[^.]{0,90}?R\$\s?[\d.]+,\d{2}"),
    ("remuneração", r"(?:subs[íi]dio|remuneração)[^.]{0,110}?R\$\s?[\d.]+,\d{2}"),
    ("prova objetiva", r"[Pp]rova [Oo]bjetiva[^.]{0,140}?%s" % DATA),
]


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


def pagina(c):
    """Situacao e arquivos (data, titulo, url) da pagina do concurso."""
    codigo, t = fetch(c["url"])
    c["http"] = codigo
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
            arquivos.append({"data": datetime.strptime(l, "%d/%m/%Y").date().isoformat(), "titulo": titulo,
                             "url": links.get(titulo, "")})
    c["arquivos"] = arquivos
    return c


def edital(c):
    """Trechos copiados do edital de abertura (PDF da banca)."""
    alvo = next((a for a in reversed(c["arquivos"]) if a["titulo"].lower().startswith("edital") and a["url"]), None)
    if not alvo:
        return
    codigo, dados = fetch(alvo["url"], binario=True, timeout=60)
    if codigo != 200 or not dados.startswith(b"%PDF"):
        c["edital_erro"] = "http %s" % codigo
        return
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(dados)
        caminho = f.name
    try:
        t = subprocess.run(["pdftotext", "-l", "40", caminho, "-"], capture_output=True,
                           timeout=60).stdout.decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        c["edital_erro"] = "pdftotext: %s" % e
        return
    finally:
        os.unlink(caminho)
    t = re.sub(r"\s+", " ", t)
    c["edital_url"] = alvo["url"]
    c["edital"] = {}
    for rotulo, padrao in TRECHOS:
        m = re.search(padrao, t)
        if m:
            c["edital"][rotulo] = m.group(0).strip()[:230]


def sigla(slug):
    s = re.sub(r"[^a-z0-9]", "", slug.lower())
    s = re.sub(r"\d{2,4}$", "", s)
    return SUFIXOS.sub("", s)


def confirmado(reg):
    """O registro ja se apoia na banca oficial? (entao nao e preciso reler o edital todo dia)"""
    if reg.get("selo") in ("PENDÊNCIA DE VERIFICAÇÃO", "PENDÊNCIA"):
        return False
    if any(not p.get("confirmado") for p in reg.get("prazos") or []):
        return False
    return "conhecimento.fgv.br" in (reg.get("fonte") or "")


def coletar(hoje, concursos, ja_visto=None):
    codigo, lista = listagem()
    res = {"banca": "FGV", "http": codigo, "concursos": []}
    if codigo != 200 or not lista:
        return res
    anos = {"%02d" % (hoje.year % 100), "%02d" % ((hoje.year - 1) % 100), str(hoje.year), str(hoje.year - 1)}
    alvo = [c for c in lista if JURIDICO.search(c["titulo"]) and re.search(r"(\d{2,4})$", c["slug"])
            and re.search(r"(\d{2,4})$", c["slug"]).group(1) in anos]
    with ThreadPoolExecutor(max_workers=4) as ex:
        alvo = list(ex.map(pagina, alvo))
    por_sigla = {}
    for r in concursos:
        por_sigla.setdefault(r["id"].split("_")[0], []).append(r)
    for c in alvo:
        regs = por_sigla.get(sigla(c["slug"]), [])
        ult = max((r.get("verificado_em") or "" for r in regs), default="")
        c["novos_arquivos"] = [a for a in c["arquivos"] if not regs or a["data"] > ult]
        if not regs or not all(confirmado(r) for r in regs):
            edital(c)
        regs = desambiguar(c, regs)
        c["registros"] = [r["id"] for r in regs]
        # coberto = a pagina oficial deste registro foi lida hoje: o coletor nao gasta busca com ele
        c["coberto"] = c["registros"] if (len(regs) == 1 and c.get("http") == 200) else []
    res["concursos"] = alvo
    return res


CARGO_BLOCO = [(r"Juiz|Magistratura", "Magistratura"), (r"Promotor", "Promotor"), (r"Defensor", "Defensor"),
               (r"Procurador", "Procurador")]


def desambiguar(c, regs):
    """Duas linhas do registro com a mesma sigla (ex.: tjpb_juiz e tjpb_apoio): decide pelo cargo
    do titulo da banca; sem cargo no titulo, edital que fala em Analista/Tecnico e do quadro de apoio."""
    if len(regs) < 2:
        return regs
    for padrao, bloco in CARGO_BLOCO:
        if re.search(padrao, c["titulo"], re.I):
            so = [r for r in regs if (r.get("bloco") or "").startswith(bloco)]
            return so or regs
    if re.search(r"Analista|T[ée]cnico", " ".join((c.get("edital") or {}).values())):
        so = [r for r in regs if r.get("bloco") == "Quadro de apoio"]
        return so or regs
    return regs


def imprimir(res):
    cs = res["concursos"]
    if res["http"] != 200 or not cs:
        print("BANCA FGV: página não lida (http %s) — concursos da FGV seguem pela busca do coletor." % res["http"])
        return
    print("BANCA FGV (fonte OFICIAL, lida por script — promove selo e confirma prazo; cite a URL em `fonte`; "
          "os trechos do edital são do texto consolidado: retificação listada depois dele pode alterá-los): "
          "%d concursos jurídicos" % len(cs))
    for c in cs:
        reg = ("registro " + " ou ".join(c["registros"])) if c["registros"] else "SEM REGISTRO → avalie como NOVO"
        print("- %s | %s | %s | %s | %s" % (c["slug"], c.get("situacao") or "?", c["titulo"], reg, c["url"]))
        arqs = c["novos_arquivos"] or c["arquivos"][:1]
        rot = "arquivos novos desde a última verificação" if c["novos_arquivos"] else "sem arquivo novo; último"
        if arqs:
            print("  %s: %s" % (rot, "; ".join("%s %s" % (a["data"][8:] + "/" + a["data"][5:7], a["titulo"])
                                                 for a in arqs[:5])))
        if c.get("edital"):
            print("  edital: " + " · ".join('%s "%s"' % kv for kv in c["edital"].items()))
        elif c.get("edital_erro"):
            print("  edital não lido (%s)" % c["edital_erro"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--janela", default="/tmp/janela.json")
    a = ap.parse_args()
    try:
        hoje = date.fromisoformat(json.load(open(a.janela, encoding="utf-8"))["data"])
    except Exception:
        hoje = date.today()
    led = json.load(open(os.path.join(AQUI, "robozinho-aprendizado.json"), encoding="utf-8"))
    res = coletar(hoje, led.get("concursos") or [])
    with open("/tmp/bancas.json", "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    imprimir(res)


if __name__ == "__main__":
    main()
