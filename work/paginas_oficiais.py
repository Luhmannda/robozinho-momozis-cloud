#!/usr/bin/env python3
# =====================================================================
# paginas_oficiais.py — leitura deterministica da PAGINA OFICIAL de cada
# concurso que tem `url_oficial` no registro (link profundo: pagina do
# concurso ou listagem de editais do orgao), sem tokens. Chamado pelo
# inicio.py para todos os concursos com url_oficial (no escopo).
#
# Por que (B10): o coletor recebia "pagina oficial <dominio> acessivel: leia
# por curl" e lia a RAIZ do dominio; nada se confirmava e a leitura se
# repetia (pendencias com 26 a 55 execucoes). Cebraspe devolve 200 com 116
# caracteres (pagina so JavaScript).
#
# Para cada url_oficial: baixa a pagina, tira o HTML e guarda os ITENS com
# palavra-chave de concurso (concurso, edital, inscri, resultado, prova,
# homolog, convoca, retifica, nomea) OU com data (DD/MM/AAAA, "18 de novembro
# de 2026"). Item = linha + continuacao: a linha seguinte que comeca por ',',
# '-', '–', '.' ou por "publicado/disponibilizado/retificado" vai junto (o TRF2
# quebra "PORTARIA PRES/TRF2 Nº 578" e ", disponibilizado ... 18/11/2026" em
# duas linhas; a PGE-RJ poe o titulo do ato sem palavra-chave — "DESIGNAÇÃO DE
# MEMBRO DA COMISSÃO EXAMINADORA" — e a data na linha de baixo). Carimbo da
# pagina ("Página atualizada em ...", "Brasília, 21 de novembro de 2026") nao e
# item: so a data nao basta quando o resto e curto ou e "atualizado em". Navegacao
# tambem nao (E-min c): o <title> da pagina, palavra-chave so no meio da palavra
# ("Aprovação"), e — sem data — chamada para clicar, titulo de secao e pedaco de
# frase que comeca por preposicao em minuscula. O inicio.py nao manda para ca a
# url_oficial que e a pagina da banca ja lida pelo bancas.py. O hash dos
# itens e comparado com o da ultima leitura registrada (work/concursos-estado.json,
# secao "paginas", gravada pelo helper quando a execucao e registrada):
#   MUDOU  — ha item novo: os novos impressos, do mais recente (1a data do item)
#            para o mais antigo (ate 5). Reordenar ou retirar item nao e MUDOU;
#   IGUAL  — numa linha so, com os ids e o "desde DD/MM";
#   NOVA   — 1a leitura (sem estado, outra URL ou estado do formato antigo, sem
#            "v": 2): os 5 itens mais recentes, nunca o cabecalho da pagina;
#   SEM_TEXTO — pagina so JavaScript (texto util < 300 caracteres): sai da lista "acessivel";
#   FORA_DA_REDE — dominio que a sonda do inicio.py deu como recusado pelo proxy
#            ou sem resposta hoje: nao e baixado (o TRF3 dava HTTP 0 todo dia);
#   HTTP nnn — nao abriu.
# O inicio.py le TODAS as url_oficial todo dia (nao so as do foco) e poe no foco
# quem der MUDOU ou NOVA.
#
# USO avulso: python3 work/paginas_oficiais.py   (todos os concursos com url_oficial)
# SAIDA: linhas "PAGINA OFICIAL ..." e $ROBOZINHO_TMP/paginas_oficiais.json.
# =====================================================================

import hashlib
import html
import json
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from urllib.parse import urlparse

AQUI = os.path.dirname(os.path.abspath(__file__))
UA = "Mozilla/5.0 (X11; Linux x86_64) Robozinho/1.0"
# palavra-chave no comeco da palavra: "Certificado de Aprovação" (link do rodape do ENAM) nao e "prova"
CHAVE = re.compile(r"\b(?:concurso|edital|inscri[çc]|resultado|prova|homolog|convoca|retifica|nomea)", re.I)
MESES = {"janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4, "maio": 5, "junho": 6,
         "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12}
# data de ato: DD/MM/AAAA ou "18 de novembro de 2026" ("Atualizado em: 19 Novembro, 2026" nao casa)
DATA = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b|\b(\d{1,2})º?\s+de\s+(%s)\s+de\s+(\d{4})\b" % "|".join(MESES), re.I)
# continuacao da linha de cima: ", disponibilizado ...", "- Edital de ...", "– torna público ...", "Publicado no ..."
CONTINUA = re.compile(r"[,.;:]|[-–—]\s*\w|(?:publicad|disponibiliz|retificad)\w*\b", re.I)
# carimbo da propria pagina ("Página atualizada em 20/11/2026", "Brasília, 21 de novembro de 2026"): muda sem ato
# novo; so a data nao faz dele item (com palavra-chave, continua item, como antes)
RUIDO = re.compile(r"\b(?:atualizad[ao]|[úu]ltima\s+atualiza[çc][ãa]o|postad[ao]|acessad[ao]|acesso)\s+em\b|^\W*hoje\b",
                   re.I)
# navegacao do site que casa CHAVE e nao e ato (so item SEM data: o datado e sempre ato) — E-min c: chamada para
# clicar ("Solicite aqui...", "Acesse...", "Faça sua inscrição"), titulo de secao ("Arquivos do concurso") e pedaco
# de frase quebrada pelo HTML, que comeca por preposicao/artigo em minuscula ("da FGV para concursos e provas
# realizadas."; "prova escrita geral - questões", da PGE-RJ, fica). O <title> da pagina ("Concursos Públicos - Portal
# DPESP") sai em texto_util.
NAVEGACAO = (re.compile(r"^(?:solicite|clique|acesse|cadastre|fa[çc]a\s+(?:sua|seu|a|o)\b)", re.I),
             re.compile(r"^(?:arquivos|documentos|editais|publica[çc][õo]es|links)(?:\s+(?:do|dos|e)\s+\w+)?\W*$", re.I),
             re.compile(r"^(?:de|da|do|das|dos|e|a|o|as|os|para|que|com|em|no|na|nos|nas|pelo|pela)\s"))
MIN_TEXTO = 300
MAX_TRECHOS = 200
MAX_IMPRESSOS = 5
VERSAO = 2              # formato dos itens no estado (1 = linha solta so com palavra-chave)


def tmp(nome):
    return os.path.join(os.environ.get("ROBOZINHO_TMP", "/tmp"), nome)


def baixar(url, timeout=20):
    try:
        r = subprocess.run(["curl", "-sL", "-m", str(timeout), "-A", UA, "-w", "\n%{http_code}", url],
                           capture_output=True, timeout=timeout + 5)
        corpo, _, codigo = r.stdout.decode("utf-8", "replace").rpartition("\n")
        return int(codigo or 0), corpo
    except Exception:  # noqa: BLE001
        return 0, ""


def texto_util(pagina):
    t = re.sub(r"(?s)<!--.*?-->", " ", pagina or "")
    # <head>/<title>: o titulo da pagina ("19º Concurso ... | PGE", "Concursos Públicos - Portal DPESP") nao e ato
    t = re.sub(r"(?is)<(head|title|script|style|noscript|svg|nav|footer|header)\b.*?</\1>", " ", t)
    t = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</tr>|</h\d>|</a>|</td>", "\n", t)
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    return [l for l in (re.sub(r"\s+", " ", x).strip() for x in t.split("\n")) if l]


def _carimbo(item):
    """Item que so tem data (e pouco texto) ou e o "atualizado em" da pagina: nao e ato."""
    return bool(RUIDO.search(item)) or len(DATA.sub(" ", item).strip(" ,.;:-–—|")) < 12


def _continua(linha):
    return len(linha) <= 400 and bool(CONTINUA.match(linha))


def trechos(linhas):
    """Itens (linha + ate 2 continuacoes) com palavra-chave ou data, sem repetir o item JUNTO (o mesmo titulo
    com outra data e outro item), ate MAX_TRECHOS, na ordem da pagina; cada item ate 300 caracteres."""
    out, i, n = [], 0, len(linhas)
    while i < n and len(out) < MAX_TRECHOS:
        item = linhas[i]
        i += 1
        if len(item) > 400:
            continue
        partes = 1
        while i < n and partes < 3 and _continua(linhas[i]):
            c = linhas[i]
            item += c if c[0] in ",.;:" else (" " if c[0] in "-–—" else " — ") + c
            i += 1
            partes += 1
        if len(item) < 12 or not (CHAVE.search(item) or (DATA.search(item) and not _carimbo(item))):
            continue
        if not DATA.search(item) and any(r.search(item) for r in NAVEGACAO):
            continue
        item = item[:300]
        if item not in out:
            out.append(item)
    return out


def data_item(t):
    """A data mais recente citada no item (None sem data): ordena os impressos do mais novo ao mais antigo."""
    ds = []
    for m in DATA.finditer(t or ""):
        try:
            ds.append(date(int(m.group(3)), int(m.group(2)), int(m.group(1))) if m.group(1) else
                      date(int(m.group(6)), MESES[m.group(5).lower()], int(m.group(4))))
        except ValueError:
            continue
    return max(ds) if ds else None


def recentes(itens, n=MAX_IMPRESSOS):
    """Os `n` itens mais recentes pela data; os sem data depois, na ordem da pagina."""
    datados = sorted((x for x in itens if data_item(x)), key=data_item, reverse=True)
    return (datados + [x for x in itens if not data_item(x)])[:n]


def sha(s):
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:12]


def analisar(ident, url, http, pagina, anterior, hoje):
    """Resultado de uma pagina. `anterior` = estado["paginas"][ident] (ou None)."""
    r = {"id": ident, "url": url, "http": http}
    if http != 200:
        r["situacao"] = "HTTP"
        return r
    linhas = texto_util(pagina)
    if sum(len(l) for l in linhas) < MIN_TEXTO:
        r["situacao"] = "SEM_TEXTO"
        return r
    tr = trechos(linhas)
    r["hash"] = sha("\n".join(tr))
    r["trechos_hash"] = [sha(t) for t in tr]
    if not anterior or anterior.get("url") != url or anterior.get("v") != VERSAO:
        # estado do formato antigo (v1): outros hashes; comparar daria MUDOU falso com atos antigos
        r.update(situacao="NOVA", novos=recentes(tr), desde=hoje,
                 releitura=bool(anterior) and anterior.get("url") == url)
        return r
    novos = [t for t in tr if sha(t) not in set(anterior.get("trechos_hash") or [])]
    if anterior.get("hash") == r["hash"] or not novos:
        # sem item novo (igual, ou so reordenado/retirado): IGUAL, com o hash de hoje gravado
        r.update(situacao="IGUAL", desde=anterior.get("desde") or hoje)
    else:
        r.update(situacao="MUDOU", novos=recentes(novos), desde=hoje)
    return r


def host(url):
    return (urlparse(url or "").hostname or "").lower()


def verificar(concursos, estado, hoje, ids=None, pular=None):
    """Lista de resultados para os concursos com url_oficial (so os `ids`, se dado). `pular` = {host: motivo}:
    dominio fora da rede hoje (sonda do inicio.py) nao e baixado — situacao FORA_DA_REDE."""
    alvos = [(c["id"], c["url_oficial"]) for c in concursos
             if c.get("url_oficial") and (ids is None or c["id"] in ids)]
    pags = (estado or {}).get("paginas") or {}
    pular = pular or {}
    baixar_ = [a for a in alvos if host(a[1]) not in pular]
    with ThreadPoolExecutor(max_workers=6) as ex:
        baixadas = dict(zip(baixar_, ex.map(lambda a: baixar(a[1]), baixar_)))
    res = []
    for i, u in alvos:
        if (i, u) in baixadas:
            http, corpo = baixadas[(i, u)]
            res.append(analisar(i, u, http, corpo, pags.get(i), hoje))
        else:
            res.append({"id": i, "url": u, "http": 0, "situacao": "FORA_DA_REDE", "motivo": pular[host(u)]})
    return res


def _dm(iso):
    return "%s/%s" % (iso[8:10], iso[5:7]) if iso and len(iso) >= 10 else (iso or "?")


def linhas_saida(res):
    """Uma linha por pagina com novidade (MUDOU/NOVA, com os itens), SEM_TEXTO ou HTTP; as IGUAL numa linha so e
    as FORA_DA_REDE noutra."""
    out, iguais, fora = [], [], []
    for r in res:
        sit = r["situacao"]
        if sit == "IGUAL":
            iguais.append("%s desde %s" % (r["id"], _dm(r.get("desde"))))
        elif sit == "FORA_DA_REDE":
            fora.append("%s (%s: %s)" % (r["id"], host(r.get("url")), r.get("motivo") or "fora da rede"))
        elif sit in ("MUDOU", "NOVA"):
            rot = "MUDOU" if sit == "MUDOU" else ("RELIDA (formato novo: confira com o registro)" if r.get("releitura")
                                                  else "LIDA (1ª vez)")
            out.append("PAGINA OFICIAL %s %s | %s%s" % (r["id"], rot, r["url"],
                                                         "".join("\n  · " + t for t in r.get("novos") or [])))
        elif sit == "SEM_TEXTO":
            out.append("PAGINA OFICIAL %s SEM TEXTO (página só JavaScript): fora do 'acessível' | %s" % (r["id"], r["url"]))
        else:
            out.append("PAGINA OFICIAL %s HTTP %s | %s" % (r["id"], r["http"], r["url"]))
    if iguais:
        out.insert(0, "PAGINA OFICIAL sem item novo: " + "; ".join(iguais))
    if fora:
        out.append("PAGINA OFICIAL não lida (domínio fora da rede hoje): " + "; ".join(fora))
    return out


def atualizar_estado(estado, res, hoje):
    """Usado pelo helper: grava hash/itens/desde das paginas lidas, com "v": VERSAO (nao mexe nas que nao abriram
    nem nas FORA_DA_REDE)."""
    pags = estado.setdefault("paginas", {})
    n = 0
    for r in res or []:
        if r.get("situacao") in ("IGUAL", "MUDOU", "NOVA"):
            ant = pags.get(r["id"]) or {}
            pags[r["id"]] = {"v": VERSAO, "url": r["url"], "hash": r["hash"], "trechos_hash": r["trechos_hash"],
                             "desde": r.get("desde") or ant.get("desde") or hoje, "lido_em": hoje}
            n += r["situacao"] != "IGUAL"
    return n


def main():
    import bancas
    hoje = date.today().isoformat()
    try:
        hoje = json.load(open(tmp("janela.json"), encoding="utf-8"))["data"]
    except Exception:  # noqa: BLE001
        pass
    led = json.load(open(os.path.join(AQUI, "robozinho-aprendizado.json"), encoding="utf-8"))
    res = verificar(led.get("concursos") or [], bancas.carregar_estado(), hoje)
    with open(tmp("paginas_oficiais.json"), "w", encoding="utf-8") as f:
        json.dump({"data": hoje, "paginas": res}, f, ensure_ascii=False, indent=1)
    print("\n".join(linhas_saida(res)) or "PAGINA OFICIAL: nenhum concurso com url_oficial no registro")


if __name__ == "__main__":
    main()
