#!/usr/bin/env python3
# =====================================================================
# informativos.py — conteudo dos informativos direto do documento oficial
# (os e-mails do STF e do STJ trazem so o link). Descobre as edicoes novas
# pelo numero seguinte ao ultimo publicado no historico, baixa e extrai os
# destaques. Deterministico, sem tokens; roda no passo 2 da ROTINA.
#
#   Informativo STF  https://www.stf.jus.br/arquivo/cms/informativoSTF/anexo/Informativo_PDF/Informativo_stf_N.pdf
#   RG em Pauta      https://www.stf.jus.br/arquivo/cms/newsletterInformativoRG/anexo/EdioN.pdf
#   Informativo STJ  https://processo.stj.jus.br/jurisprudencia/externo/informativo/?acao=pesquisarumaedicao&livre=0NNN.cod.
#     (o link do e-mail, em ww2.stj.jus.br, redireciona para www.stj.jus.br,
#      que esta fora do allowlist; processo.stj.jus.br serve o mesmo conteudo)
#   O servidor do STF devolve 403 ao user-agent do curl: usa-se o de navegador.
#
# USO:   python3 work/informativos.py                 (edicoes novas, pelo historico)
#        python3 work/informativos.py stf:1232 rg:392 stj:905   (edicoes dadas)
# SAIDA: resumo compacto em stdout; JSON em /tmp/informativos.json.
# =====================================================================

import glob
import html
import json
import os
import re
import subprocess
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")
URL = {
    "stf": "https://www.stf.jus.br/arquivo/cms/informativoSTF/anexo/Informativo_PDF/Informativo_stf_%d.pdf",
    "rg": "https://www.stf.jus.br/arquivo/cms/newsletterInformativoRG/anexo/Edio%d.pdf",
    "stj": "https://processo.stj.jus.br/jurisprudencia/externo/informativo/?acao=pesquisarumaedicao&livre=%04d.cod.",
}
NOME = {"stf": "INFORMATIVO STF", "rg": "REPERCUSSAO GERAL EM PAUTA", "stj": "INFORMATIVO STJ"}
MES = "janeiro|fevereiro|março|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro"
MAX_ITENS, MAX_TXT = 10, 350
MESES = {m: i + 1 for i, m in enumerate(MES.split("|"))}


def chave(r):
    """Chave do historico; e por ela que a proxima execucao acha a edicao seguinte."""
    datas = re.findall(r"(\d{1,2}) de (%s) de (\d{4})" % MES, r.get("data") or "")
    if not datas:
        datas = [(1, None, "")]
    d, m, a = datas[-1]
    iso = "%s-%02d-%02d" % (a, MESES[m], int(d)) if m else ""
    alvo = {"stf": "stf|informativo|%d", "rg": "stf|informativo|repercussao-geral-%d",
            "stj": "stj|informativo|%d"}[r["tipo"]] % r["numero"]
    return "%s|%s|%s" % (alvo, a or "", iso)


def baixar(url):
    """(http, bytes) com user-agent de navegador; (0, b'') em erro de rede."""
    with tempfile.NamedTemporaryFile(delete=False) as f:
        caminho = f.name
    try:
        r = subprocess.run(["curl", "-sL", "-m", "40", "-A", UA, "-H", "Accept-Language: pt-BR,pt;q=0.9",
                            "-o", caminho, "-w", "%{http_code}", url], capture_output=True, timeout=50)
        codigo = int(r.stdout.decode().strip() or 0)
        return codigo, open(caminho, "rb").read()
    except Exception:
        return 0, b""
    finally:
        os.unlink(caminho)


def pdf_texto(dados, layout):
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(dados)
        caminho = f.name
    try:
        args = ["pdftotext"] + (["-layout"] if layout else []) + [caminho, "-"]
        return subprocess.run(args, capture_output=True, timeout=60).stdout.decode("utf-8", "replace")
    finally:
        os.unlink(caminho)


def curto(s, n=MAX_TXT):
    s = re.sub(r"\s+", " ", s or "").strip()
    return s if len(s) <= n else s[:n - 1].rsplit(" ", 1)[0] + "…"


# ------------------------------------------------------------------ STF
def stf(dados):
    t = pdf_texto(dados, layout=True)
    data = re.search(r"\d{1,2} de (?:%s) de \d{4}" % MES, t)
    ini = t.find("SUMÁRIO")
    fim = t.find("Edição", ini + 1) if ini >= 0 else -1
    bloco = t[ini:fim if fim > ini else len(t)] if ini >= 0 else ""
    itens, secao, ramo, atual = [], "", "", None
    for linha in bloco.splitlines():
        s = linha.strip()
        m = re.match(r"^\d+\s+([A-ZÁÉÍÓÚÂÊÔÃÕÇ ]{4,})$", s)
        if m:
            secao = m.group(1).title()
            continue
        # ramo comeca na coluna 0; as palavras-chave (ex.: " DIREITO DE OPCAO") vem recuadas
        if re.match(r"^DIREITO [A-ZÁÉÍÓÚÂÊÔÃÕÇ ]+$", linha.rstrip()):
            ramo = s
            continue
        if s.startswith("»"):
            atual = {"secao": secao, "ramo": ramo, "titulo": s.lstrip("» ").strip()}
            itens.append(atual)
        elif atual is not None and s and not s.isupper():
            atual["titulo"] += " " + s
        else:
            atual = None
        if atual is not None and re.search(r"\.{4,}\s*\d*\s*$", atual["titulo"]):
            atual["titulo"] = re.sub(r"\s*\.{4,}\s*\d*\s*$", "", atual["titulo"])
            atual = None
    for it in itens:
        it["titulo"] = curto(re.sub(r"\s*\.{4,}.*$", "", it["titulo"]))
    return (data.group(0) if data else ""), itens[:MAX_ITENS]


def rg(dados):
    linhas = [l.strip() for l in pdf_texto(dados, layout=False).splitlines() if l.strip()]
    periodo = next((l for l in linhas[:5] if re.search(r"\d{4}$", l) and " de " in l), "")
    secoes = ("JULGAMENTOS", "ACÓRDÃOS PUBLICADOS", "TEMAS COM TRÂNSITO EM JULGADO",
              "TEMAS EM JULGAMENTO", "TEMAS FINALIZADOS", "REPERCUSSÃO GERAL RECONHECIDA",
              "REPERCUSSÃO GERAL NEGADA")
    itens, secao, atual, campo = [], "", None, None
    for l in linhas:
        if l in secoes:
            secao, campo = l.title(), None
            continue
        m = re.match(r"^TEMA:\s*([\d.]+)(?:\s+PROCESSOS?:\s*(.+))?$", l)
        if m:
            atual = {"secao": secao, "tema": m.group(1), "processo": m.group(2) or "", "titulo": "", "tese": ""}
            itens.append(atual)
            campo = None
            continue
        if atual is None:
            continue
        m = re.match(r"^PROCESSOS?:\s*(.+)$", l)
        if m:
            atual["processo"] = m.group(1)
            campo = None
        elif l.startswith("Título:"):
            atual["titulo"], campo = l[7:].strip(), "titulo"
        elif "seguinte tese:" in l:
            atual["tese"], campo = l.split("seguinte tese:", 1)[1].strip(), "tese"
        elif re.match(r"^(RELATORA?:|Agenda 2030|Página \d|INTEIRO TEOR|Decisão:|\(Presidente\))", l):
            campo = None
        elif campo:
            atual[campo] += " " + l
            if campo == "tese" and "”" in l:
                campo = None
    vistos, unicos = set(), []
    for it in itens:                       # "Temas finalizados" repete temas ja listados
        if it["tema"] in vistos:
            continue
        vistos.add(it["tema"])
        it["titulo"], it["tese"] = curto(it["titulo"], 220), curto(it["tese"])
        unicos.append(it)
    return periodo, unicos[:MAX_ITENS]


# ------------------------------------------------------------------ STJ
def stj(dados, numero):
    t = dados.decode("cp1252", "replace")
    if "Destaque" not in t:
        return "", []
    t = re.sub(r"(?is)<(script|style).*?</\1>", " ", t)
    t = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</h\d>|</li>", "\n", t)
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    L = [re.sub(r"\s+", " ", l).strip() for l in t.split("\n")]
    L = [l for l in L if l]
    cab = re.compile(r"^Informativo de Jurisprud\S* n\. %d - (\d{1,2} de \w+ de \d{4})\.\s*(.*)$" % numero)
    secoes = re.compile(r"^(RECURSOS REPETITIVOS|CORTE ESPECIAL|PRIMEIRA SEÇÃO|SEGUNDA SEÇÃO|TERCEIRA SEÇÃO|"
                        r"PRIMEIRA TURMA|SEGUNDA TURMA|TERCEIRA TURMA|QUARTA TURMA|QUINTA TURMA|SEXTA TURMA|"
                        r"EDIÇÃO EXTRAORDINÁRIA|PROCESSO EM SEGREDO DE JUSTIÇA|ÁREAS DO DIREITO)$")
    data, itens, secao, atual = "", [], "", None
    for i, l in enumerate(L):
        if secoes.match(l):
            secao = l.title()
            continue
        m = cab.match(l)
        if m:
            data = data or m.group(1)
            if m.group(2):
                atual = {"secao": secao, "tema": curto(m.group(2), 220), "processo": "", "ramo": "", "destaque": ""}
                itens.append(atual)
            continue
        if atual is None or i + 1 >= len(L):
            continue
        if l == "Processo" and not atual["processo"]:
            atual["processo"] = curto(L[i + 1], 170)
        elif l == "Ramo do Direito" and not atual["ramo"]:
            atual["ramo"] = L[i + 1]
        elif l == "Destaque" and not atual["destaque"]:
            atual["destaque"] = curto(L[i + 1])
    return data, [it for it in itens if it["destaque"]][:MAX_ITENS]


# ------------------------------------------------------------------ orquestracao
def ultimos():
    """Maior numero ja publicado por produto (historico principal + arquivos)."""
    maior = {"stf": 0, "rg": 0, "stj": 0}
    for f in glob.glob(os.path.join(AQUI, "resumo-legislativo-historico*.json")):
        try:
            execs = json.load(open(f, encoding="utf-8"))["executions"]
        except Exception:
            continue
        for e in execs:
            for it in e.get("items") or []:
                p = (it.get("chave") or "").split("|")
                if len(p) < 3 or p[1] != "informativo":
                    continue
                m = re.fullmatch(r"repercussao-geral-(\d+)", p[2])
                if p[0] == "stf" and m:
                    maior["rg"] = max(maior["rg"], int(m.group(1)))
                elif p[0] in ("stf", "stj") and p[2].isdigit():
                    maior[p[0]] = max(maior[p[0]], int(p[2]))
    return maior


def obter(tipo, n):
    url = URL[tipo] % n
    codigo, dados = baixar(url)
    if codigo != 200 or not dados:
        return {"tipo": tipo, "numero": n, "url": url, "http": codigo, "ok": False}
    if tipo in ("stf", "rg"):
        if not dados.startswith(b"%PDF"):
            return {"tipo": tipo, "numero": n, "url": url, "http": codigo, "ok": False, "motivo": "nao e PDF"}
        data, itens = (stf if tipo == "stf" else rg)(dados)
    else:
        data, itens = stj(dados, n)
    return {"tipo": tipo, "numero": n, "url": url, "http": codigo, "ok": bool(itens), "data": data,
            "itens": itens, "motivo": "" if itens else "edicao sem itens (inexistente ou nao publicada)"}


def linha_item(tipo, it):
    if tipo == "stf":
        return "[%s] %s — %s" % (it["secao"], it["ramo"], it["titulo"])
    if tipo == "rg":
        tese = (" — Tese: " + it["tese"]) if it["tese"] else ""
        return "[%s] Tema %s — %s — %s%s" % (it["secao"], it["tema"], it["processo"], it["titulo"], tese)
    return "[%s] %s — %s — %s — Destaque: %s" % (it["secao"], it["processo"], it["ramo"], it["tema"], it["destaque"])


def main():
    pedidos = [a.split(":", 1) for a in sys.argv[1:] if ":" in a]
    resultados = []
    if pedidos:
        for tipo, n in pedidos:
            resultados.append(obter(tipo, int(n)))
    else:
        base = ultimos()
        for tipo in ("stf", "rg", "stj"):
            if not base[tipo]:
                resultados.append({"tipo": tipo, "ok": False, "motivo": "nenhuma edicao no historico"})
                continue
            for n in range(base[tipo] + 1, base[tipo] + 4):   # ate 3 edicoes novas de uma vez
                r = obter(tipo, n)
                resultados.append(r)
                if not r["ok"]:
                    break
    for r in resultados:
        if r.get("ok"):
            print("%s %d (%s) — %d destaques — %s — chave=%s" % (NOME[r["tipo"]], r["numero"], r["data"],
                                                                len(r["itens"]), r["url"], chave(r)))
            for it in r["itens"]:
                print("  " + linha_item(r["tipo"], it))
        elif r.get("http") in (0, 403):
            print("ERRO %s %s: http %s — acesso bloqueado; publicar numero, data e link do e-mail e dizer que o "
                  "conteudo nao foi acessivel" % (NOME[r["tipo"]], r.get("numero", ""), r.get("http")))
        else:
            print("SEM EDICAO NOVA %s (%s: %s)" % (NOME[r["tipo"]], r.get("numero", "-"),
                                                 r.get("motivo") or "http %s" % r.get("http")))
    with open("/tmp/informativos.json", "w", encoding="utf-8") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
