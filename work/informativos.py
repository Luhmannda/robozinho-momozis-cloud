#!/usr/bin/env python3
# =====================================================================
# informativos.py — conteudo dos informativos direto do documento oficial
# (os e-mails do STF e do STJ trazem so o link). Deterministico, sem tokens;
# roda no passo 2 da ROTINA. Procura, por produto:
#   - as edicoes NOVAS (numeros seguintes ao maior ja publicado; um numero
#     que falhe nao interrompe a busca: o seguinte ainda e tentado);
#   - as edicoes ATRASADAS: as duas ultimas que sairam so com numero/data/link
#     ("conteudo nao acessivel") ou que foram puladas — o conteudo entra
#     quando o documento abrir (em 11/11/2026 o 1236 do STF e o 909 do STJ
#     tinham saido sem destaques e nunca mais seriam buscados; o 908 nem saiu).
# Cada edicao ganha um id (stf1236, rg397, stj909): o orquestrador escolhe os
# destaques pelo indice e o work/montar_email.py copia o texto oficial.
#
#   Informativo STF  https://www.stf.jus.br/arquivo/cms/informativoSTF/anexo/Informativo_PDF/Informativo_stf_N.pdf
#   RG em Pauta      https://www.stf.jus.br/arquivo/cms/newsletterInformativoRG/anexo/EdioN.pdf
#   Informativo STJ  https://processo.stj.jus.br/jurisprudencia/externo/informativo/?acao=pesquisarumaedicao&livre=0NNN.cod.
#     (o link do e-mail, em ww2.stj.jus.br, redireciona para www.stj.jus.br,
#      que esta fora do allowlist; processo.stj.jus.br serve o mesmo conteudo)
#   O servidor do STF devolve 403 ao user-agent do curl: usa-se o de navegador
#   E um Referer de portal.stf.jus.br (sem o Referer o PDF da RG 394 deu 403 em 22/10/2026).
#
# USO:   python3 work/informativos.py                 (edicoes novas e atrasadas, pelo historico)
#        python3 work/informativos.py stf:1232 rg:392 stj:905   (edicoes dadas)
# SAIDA: indice compacto em stdout (id, data, destaques numerados e curtos);
#        texto integral dos destaques em /tmp/informativos.json.
# =====================================================================

import glob
import html
import json
import os
import re
import subprocess
import sys
import tempfile
import time

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
MAX_ITENS, MAX_TXT = 10, 520
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
        r = subprocess.run(["curl", "-sL", "-m", "40", "-A", UA, "-e", "https://portal.stf.jus.br/", "-H", "Accept-Language: pt-BR,pt;q=0.9",
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
    # ate 10/2026 o cabecalho era "n. 907"; desde o 908 e "nº 908" (o script deixou de achar a edicao)
    cab = re.compile(r"^Informativo de Jurisprud\S* n(?:\.|º|°|o\.?)\s*%d - (\d{1,2} de \w+ de \d{4})\.\s*(.*)$" % numero)
    secoes = re.compile(r"^(RECURSOS REPETITIVOS|CORTE ESPECIAL|PRIMEIRA SEÇÃO|SEGUNDA SEÇÃO|TERCEIRA SEÇÃO|"
                        r"PRIMEIRA TURMA|SEGUNDA TURMA|TERCEIRA TURMA|QUARTA TURMA|QUINTA TURMA|SEXTA TURMA|"
                        r"EDIÇÃO EXTRAORDINÁRIA|PROCESSO EM SEGREDO DE JUSTIÇA|ÁREAS DO DIREITO|"
                        r"RELEVÂNCIA DA QUESTÃO FEDERAL)$")
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
SEM_CONTEUDO = re.compile(r"(?i)n[aã]o (foi |estava )?(acess|lid)|inacess|\b403\b|sem teses|link gen[eé]rico|"
                          r"s[oó] n[uú]mero")


def publicados():
    """{produto: {numero: sem_conteudo}} do historico principal e dos arquivos.
    sem_conteudo=True: a edicao saiu so com numero/data/link e os destaques ainda nao."""
    pub = {"stf": {}, "rg": {}, "stj": {}}
    ignorar = ""
    try:
        ignorar = json.load(open("/tmp/janela.json", encoding="utf-8")).get("ignorar_execucao") or ""
    except Exception:
        pass
    for f in glob.glob(os.path.join(AQUI, "resumo-legislativo-historico*.json")):
        try:
            execs = json.load(open(f, encoding="utf-8"))["executions"]
        except Exception:
            continue
        for e in execs:
            if e.get("execution_id") == ignorar:
                continue
            for it in e.get("items") or []:
                p = (it.get("chave") or "").split("|")
                if len(p) < 3 or p[1] != "informativo" or p[0] not in ("stf", "stj"):
                    continue
                m = re.fullmatch(r"(repercussao-geral-)?(\d+)(-conteudo)?", p[2])
                if not m:
                    continue
                tipo = "rg" if m.group(1) else p[0]
                if tipo == "rg" and p[0] != "stf":
                    continue
                n = int(m.group(2))
                vazio = bool(it.get("sem_conteudo")) or (
                    "sem_conteudo" not in it and not m.group(3)
                    and bool(SEM_CONTEUDO.search(it.get("observacao") or "")))
                # um registro com conteudo (ou o "-conteudo" posterior) vence o anuncio vazio
                pub[tipo][n] = pub[tipo].get(n, True) and vazio
    return pub


def candidatos(pub):
    """[(numero, situacao)] — 'atrasada' (ja anunciada sem destaques), 'pulada' (numero
    anterior ao ultimo que nunca saiu) e 'nova'. So as duas ultimas edicoes sao revisitadas."""
    if not pub:
        return []
    base = max(pub)
    lista = []
    for n in (base - 1, base):
        if n not in pub:
            lista.append((n, "pulada"))
        elif pub[n]:
            lista.append((n, "atrasada"))
    return lista + [(n, "nova") for n in range(base + 1, base + 4)]


def obter(tipo, n, situacao="nova"):
    url = URL[tipo] % n
    codigo, dados = baixar(url)
    r = {"tipo": tipo, "numero": n, "id": "%s%d" % (tipo, n), "url": url, "http": codigo,
         "situacao": situacao, "ok": False}
    if codigo != 200 or not dados:
        return r
    if tipo in ("stf", "rg"):
        if not dados.startswith(b"%PDF"):
            return dict(r, motivo="nao e PDF")
        data, itens = (stf if tipo == "stf" else rg)(dados)
    else:
        data, itens = stj(dados, n)
    r.update(ok=bool(itens), data=data, itens=itens,
             motivo="" if itens else "edicao sem itens (inexistente ou nao publicada)")
    if itens:
        r["chave"] = chave(r)
        if situacao == "atrasada":      # a chave do anuncio ja existe no historico: o conteudo ganha a sua
            p = r["chave"].split("|")
            r["chave"] = "|".join(p[:2] + [p[2] + "-conteudo"] + p[3:])
    return r


def linha_item(tipo, it):
    """Indice curto para o orquestrador escolher; o texto integral fica no JSON."""
    if tipo == "stf":
        return "[%s] %s — %s" % (it["secao"], it["ramo"], curto(it["titulo"], 150))
    if tipo == "rg":
        return "[%s] Tema %s — %s%s" % (it["secao"], it["tema"], curto(it["titulo"], 150),
                                       " (com tese)" if it["tese"] else "")
    return "[%s] %s — %s" % (it["secao"], it["ramo"], curto(it["tema"], 150))


def main():
    pedidos = [a.split(":", 1) for a in sys.argv[1:] if ":" in a]
    resultados = []
    if pedidos:
        for tipo, n in pedidos:
            resultados.append(obter(tipo, int(n)))
    else:
        pub = publicados()
        for tipo in ("stf", "rg", "stj"):
            if not pub[tipo]:
                resultados.append({"tipo": tipo, "ok": False, "situacao": "nova",
                                   "motivo": "nenhuma edicao no historico"})
                continue
            falhas = 0
            for n, situacao in candidatos(pub[tipo]):
                if situacao == "nova" and falhas >= 2:
                    break                       # dois numeros novos seguidos sem edicao: parar
                if resultados:
                    time.sleep(1.5)             # sem rajada no mesmo servidor
                r = obter(tipo, n, situacao)
                resultados.append(r)
                if situacao == "nova":
                    falhas = 0 if r["ok"] else falhas + 1
                    if r["http"] in (0, 403):
                        break                   # servidor recusou: nao insistir nos numeros seguintes
    for r in resultados:
        nome, sit = NOME[r["tipo"]], r.get("situacao")
        if r.get("ok"):
            aviso = {"atrasada": " — ATRASADA: ja anunciada sem destaques; publique os destaques agora (herdada)",
                     "pulada": " — PULADA: nunca saiu; publique como herdada"}.get(sit, "")
            print("%s %d [id %s] (%s)%s — %d destaques — chave=%s" % (
                nome, r["numero"], r["id"], r["data"], aviso, len(r["itens"]), r["chave"]))
            for n, it in enumerate(r["itens"]):
                print("  %d %s" % (n, linha_item(r["tipo"], it)))
        elif sit in ("atrasada", "pulada"):
            print("SEGUE SEM CONTEUDO %s %s [id %s]: %s — inclua {\"ref\": \"%s\"} mesmo assim: o montador tenta "
                  "abrir de novo; se nao abrir, descarta o item sozinho"
                  % (nome, r.get("numero", ""), r.get("id"), r.get("motivo") or "http %s" % r.get("http"), r.get("id")))
        elif r.get("http") in (0, 403):
            print("ERRO %s %s [id %s]: http %s — so publique se o coletor Gmail trouxe o e-mail desta edicao: "
                  "{\"ref\": \"%s\", \"data\": \"AAAA-MM-DD\", \"url\": \"<link do e-mail>\"}; o montador tenta abrir "
                  "de novo e, sem sucesso, publica numero, data e link"
                  % (nome, r.get("numero", ""), r.get("id"), r.get("http"), r.get("id")))
        else:
            print("SEM EDICAO NOVA %s (%s: %s)" % (nome, r.get("numero", "-"),
                                                 r.get("motivo") or "http %s" % r.get("http")))
    with open("/tmp/informativos.json", "w", encoding="utf-8") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
