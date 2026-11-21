#!/usr/bin/env python3
# =====================================================================
# informativos.py — conteudo dos informativos direto do documento oficial
# (os e-mails do STF e do STJ trazem so o link). Deterministico, sem tokens;
# roda no passo 2 da ROTINA. Procura, por produto:
#   - as edicoes NOVAS (numeros seguintes ao maior ja publicado; um numero
#     que falhe nao interrompe a busca: o seguinte ainda e tentado). A
#     numeracao e sequencial: depois de um "ainda nao publicada" (404, ou
#     pagina do STJ sem o cabecalho do numero), um 403/0 no numero seguinte
#     e "nao verificavel", nunca ERRO (em 16/11/2026 o 1238 deu 403 depois do
#     404 do 1237 e virou "limitacao" falsa no e-mail). 403/0 sem 404 antes:
#     o script INSISTE ate uma resposta definitiva (200 ou 404) — exceto a
#     SONDA CURTA (MAX_TENTATIVAS_SONDA) do STF/RG quando a edicao anterior
#     saiu ha menos de CADENCIA_SONDA_DIAS dias: a cadencia e semanal e o 403
#     esconde o 404 de numero que ainda nao saiu de forma sistematica (60 de 60
#     pedidos ao stf1238/rg399 em 18-20/11/2026, 24 pedidos e ~45 s por dia).
#     Persistindo, e ERRO (cite so com o e-mail da edicao) — ver "WAF do STF";
#     documento que nao abriu NAO derruba a fonte (status_fonte): a edicao
#     anunciada por e-mail que sai sem conteudo quem acusa e o montador;
#   - as edicoes ATRASADAS: as duas ultimas que sairam so com numero/data/link
#     ("conteudo nao acessivel") ou que foram puladas — o conteudo entra
#     quando o documento abrir (em 11/11/2026 o 1236 do STF e o 909 do STJ
#     tinham saido sem destaques e nunca mais seriam buscados; o 908 nem saiu);
#   - as REVISITAS: ate MAX_REVISITAS_ANTIGAS edicoes mais antigas do STF/RG e,
#     a parte, MAX_REVISITAS_STJ do STJ (ate JANELA_REVISITA numeros para tras)
#     anunciadas sem conteudo, as mais recentes primeiro, parando no 404 — saem
#     no sub-bloco EM ATRASO.
#     Na RG em Pauta, o tema "em votacao"/"em pauta" de uma edicao que ja tem
#     dois boletins posteriores publicados sai de "itens" (vai para
#     "itens_superados"): a situacao dele e de semanas atras e o resultado ja
#     saiu (em 17/11/2026 a RG 394, de 14 a 19/10, ia ao leitor com o Tema 118
#     "Pauta do Plenario 21/10 (resultado no proximo boletim)" depois de o
#     julgamento ter saido no e-mail de 16/11). Idem o tema de uma edicao
#     herdada que tambem esta numa edicao posterior aberta na mesma execucao,
#     e o tema que ja saiu com uma RG posterior: pelo campo `temas` do item
#     do historico; sem ele, pelos temas citados no texto gravado do item de
#     RG; e, no item do montador anterior a 17/11/2026 (so "k de M destaques
#     publicados", sem a lista), conferindo no documento dessa RG posterior
#     (no maximo MAX_CONSULTAS_TEMAS por execucao). Em 17/11/2026 o Tema
#     1.483, publicado com a RG 397 em 16/11, voltava na revisita da RG 394.
# Cada edicao ganha um id (stf1236, rg397, stj909): o orquestrador escolhe os
# destaques pelo indice e o work/montar_email.py copia o texto oficial
# (STF: titulo do sumario + RESUMO oficial; RG: tema, estagio, previsao, tese;
#  STJ: tema, tipo/orgao, destaque completo; a afetacao — secao PROPOSTA DE
#  RELEVANCIA DA QUESTAO FEDERAL ou PROPOSTA DE AFETACAO, sem "Destaque" — sai
#  com a controversia afetada, tipo "Afetação"). A linha TECNICO acusa o que o
# parser perdeu: "resumo k/N" (RESUMO do STF recusado) e "k de N notas lidas" (STJ).
#
#   Informativo STF  https://www.stf.jus.br/arquivo/cms/informativoSTF/anexo/Informativo_PDF/Informativo_stf_N.pdf
#   RG em Pauta      https://www.stf.jus.br/arquivo/cms/newsletterInformativoRG/anexo/EdioN.pdf
#   Informativo STJ  https://processo.stj.jus.br/jurisprudencia/externo/informativo/?acao=pesquisarumaedicao&livre=0NNN.cod.
#     (o link do e-mail, em ww2.stj.jus.br, redireciona para www.stj.jus.br,
#      que esta fora do allowlist; processo.stj.jus.br serve o mesmo conteudo)
#   O servidor do STF devolve 403 ao user-agent do curl: usa-se o de navegador
#   E um Referer de portal.stf.jus.br (sem o Referer o PDF da RG 394 deu 403 em 22/10/2026).
#
# WAF do STF (medido em 17/11/2026, ~75 pedidos): o firewall do STF (F5, pagina
#   "The requested URL was rejected ... F5 site: dc12-ash") recusa com 403 cerca
#   de 4 em cada 5 pedidos vindos desta nuvem, AO ACASO — o mesmo pedido, segundos
#   depois, abre. Nao depende do intervalo (3 s ou 20 s), do host (www.stf.jus.br
#   ou portal.stf.jus.br, que servem o mesmo arquivo) nem dos cabecalhos (o curl
#   puro passou na mesma proporcao); e o 403 esconde ate o 404 de edicao ainda nao
#   publicada (a RG 398 dava 403 no script e 404 quando o pedido passava) — para
#   numero que ainda nao existe, de forma sistematica, nao ao acaso (60 de 60
#   pedidos em 18-20/11/2026): insistir nele nao converge (sonda curta). Uma
#   tentativa por execucao deixava a edicao nova sem destaques na maioria dos dias
#   e as revisitas (1233, RG 394) paradas ha um mes. Por isso:
#   - baixar_documento() repete o pedido, com espera curta e alternando os dois
#     hosts, ate 200 (PDF) ou 404 do endereco oficial: MAX_TENTATIVAS para edicao
#     nova ou anunciada sem conteudo, MAX_TENTATIVAS_SONDA na sonda curta,
#     MAX_TENTATIVAS_REVISITA para revisita antiga,
#     MAX_TENTATIVAS_MONTADOR na segunda tentativa do montador; por execucao, no
#     maximo ORCAMENTO_EXTRAS pedidos a mais e nenhum depois de PRAZO_S segundos.
#     Erro que nao e 403 (rede, 5xx) so ganha 2 pedidos a mais;
#   - o PDF que abriu fica em $ROBOZINHO_TMP/informativos-cache/<execution_id>/:
#     o montador (segunda tentativa e cada nova rodada) le dali, sem rede. Em
#     17/11/2026 o 1237 abriu numa rodada do montador, voltou a dar 403 nas
#     seguintes e o e-mail saiu com "Conteudo nao acessivel".
#
# USO:   python3 work/informativos.py                 (edicoes novas, atrasadas e revisitas, pelo historico)
#        python3 work/informativos.py stf:1232 rg:392 stj:905   (edicoes dadas; nao grava fontes_status.json)
# SAIDA: indice compacto em stdout (id, data, destaques numerados e curtos, uma
#        linha SEM EDICAO por produto, uma linha TECNICO com os codigos http e a
#        linha SOURCE_STATUS {"informativos_docs": "ok|falha"}); texto integral em $ROBOZINHO_TMP/informativos.json
#        e o status da fonte (id informativos_docs, com sem_abrir e falhas: ids) mesclado em
#        $ROBOZINHO_TMP/fontes_status.json (ROBOZINHO_TMP padrao: /tmp); o montador grava ali
#        a decisao final (status_script guarda o deste script).
# AMBIENTE: ROBOZINHO_TMP (pasta dos arquivos temporarios, padrao /tmp);
#        ROBOZINHO_INF_ESPERA (segundos entre as tentativas do mesmo documento, padrao 2);
#        ROBOZINHO_INF_CACHE=0 desliga o cache de PDFs (os testes desligam).
# =====================================================================

import fcntl
import glob
import html
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unicodedata
from datetime import date

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
MESES = {m: i + 1 for i, m in enumerate(MES.split("|"))}
MAX_TXT = 520                 # so para o indice impresso: o JSON guarda o texto sem corte
MAX_INDICE = 25               # linhas de destaque impressas por edicao (o JSON guarda todas)
JANELA_REVISITA = 8           # revisita edicoes sem conteudo ate base-8 (~2 meses no STF)
MAX_REVISITAS_ANTIGAS = 2     # por execucao, somando STF e RG (as mais recentes primeiro)
MAX_REVISITAS_STJ = 1         # idem, STJ, em vaga propria (sem firewall: 1 pedido; o STF barrado nao a toma)
HOSTS_STF = ("https://www.stf.jus.br/", "https://portal.stf.jus.br/")   # o mesmo PDF nos dois (conferido em 17/11/2026)
MAX_TENTATIVAS = 12           # pedidos por documento (edicao nova ou anunciada sem conteudo), ate 200 ou 404
MAX_TENTATIVAS_SONDA = 2      # idem, numero novo do STF/RG com a edicao anterior de menos de CADENCIA_SONDA_DIAS
CADENCIA_SONDA_DIAS = 6       # STF e RG em Pauta sao semanais: antes disso a edicao seguinte quase nunca saiu
MAX_TENTATIVAS_REVISITA = 4   # idem, revisita antiga e conferencia de temas
MAX_TENTATIVAS_MONTADOR = 8   # idem, na segunda tentativa do montador
MAX_OUTROS_ERROS = 3          # pedidos com erro que nao e 403 (rede, 5xx) antes de desistir do documento
ORCAMENTO_EXTRAS = 30         # pedidos alem do 1o de cada documento, por execucao (~75 s no pior caso)
PRAZO_S = 90                  # nenhuma nova tentativa depois disto, contado do 1o pedido da execucao
PRAZO_MONTADOR_S = 30         # idem, na segunda tentativa do montador
MAX_CONSULTAS_TEMAS = 2       # RGs posteriores baixadas so para conferir temas (item sem a lista), por processo
RESUMO_MIN, RESUMO_MAX = 100, 900
FONTE_ID = "informativos_docs"
SCRIPT = "informativos.py"
dormir = time.sleep           # os testes trocam por um no-op
relogio = time.monotonic      # os testes trocam por um relogio falso


def tmp(nome):
    """Caminho temporario: $ROBOZINHO_TMP/<nome> (padrao /tmp), lido a cada chamada."""
    return os.path.join(os.environ.get("ROBOZINHO_TMP") or "/tmp", nome)


def espera_retentativa():
    try:
        return max(0.0, float(os.environ.get("ROBOZINHO_INF_ESPERA", "2")))
    except ValueError:
        return 2.0


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


# ------------------------------------------------------------------ cache de PDFs e insistencia (WAF do STF)
def caminho_cache(rid):
    """Onde fica o PDF ja baixado nesta execucao, ou None (cache desligado, ou sem execution_id no
    janela.json: fora da rotina nao ha como saber se o arquivo e desta execucao)."""
    if os.environ.get("ROBOZINHO_INF_CACHE", "1") == "0":
        return None
    eid = re.sub(r"[^\w.-]", "_", str(janela().get("execution_id") or ""))
    if not eid:
        return None
    return os.path.join(tmp("informativos-cache"), eid, rid + ".pdf")


def cache_ler(rid):
    caminho = caminho_cache(rid)
    if not caminho:
        return None
    try:
        with open(caminho, "rb") as f:
            dados = f.read()
    except OSError:
        return None
    return dados if dados.startswith(b"%PDF") else None


def cache_gravar(rid, dados):
    caminho = caminho_cache(rid)
    if not caminho:
        return
    try:
        os.makedirs(os.path.dirname(caminho), exist_ok=True)
        temp = caminho + ".%d.tmp" % os.getpid()
        with open(temp, "wb") as f:
            f.write(dados)
        os.replace(temp, caminho)
    except OSError:
        pass                                # o cache e reforco, nunca derruba a coleta


def enderecos(tipo, n):
    """(endereco oficial, o mesmo arquivo no outro host do STF ou None)."""
    url = URL[tipo] % n
    alt = HOSTS_STF[1] + url[len(HOSTS_STF[0]):] if url.startswith(HOSTS_STF[0]) else None
    return url, alt


def baixar_documento(tipo, n, tentativas=1, prazo=None):
    """Baixa o documento insistindo ate uma resposta definitiva — 200 com o documento, ou 404 do
    endereco oficial (o 404 do host alternativo nao prova inexistencia). Devolve
    (http, bytes, pedidos feitos, http do 1o pedido, veio do cache).
    tentativas: maximo de pedidos; prazo: instante de relogio() depois do qual nao ha novo pedido
    (o 1o sempre e feito). PDF que abriu vai para o cache da execucao; o que esta la nao e pedido de novo."""
    rid = "%s%d" % (tipo, n)
    dados = cache_ler(rid)
    if dados:
        return 200, dados, 0, None, True
    url, alt = enderecos(tipo, n)
    codigo, dados, primeiro, feitos, outros = 0, b"", None, 0, 0
    for i in range(max(1, tentativas)):
        if i:
            if prazo is not None and relogio() >= prazo:
                break
            dormir(espera_retentativa())
        no_alt = bool(alt) and i % 2 == 1
        c, d = baixar(alt if no_alt else url)
        feitos += 1
        if primeiro is None:
            primeiro = c
        if no_alt and c == 404:
            continue                        # so o 404 do endereco oficial vale como "ainda nao publicada"
        codigo, dados = c, d
        if c == 404 or (c == 200 and d and (tipo == "stj" or d.startswith(b"%PDF"))):
            break
        if c != 403:                        # rede caida, 5xx, resposta que nao e o documento: insistir pouco
            outros += 1
            if outros >= MAX_OUTROS_ERROS:
                break
    if codigo == 200 and dados.startswith(b"%PDF"):
        cache_gravar(rid, dados)
    return codigo, dados, feitos, primeiro, False


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


def espacos(s):
    return re.sub(r"\s+", " ", s or "").strip()


def caixa_alta(s):
    """Texto so com maiusculas (palavras-chave da coluna esquerda do Informativo STF)."""
    s = (s or "").strip()
    return any(c.isupper() for c in s) and not any(c.islower() for c in s if c not in "ºª")


# palavra composta com hifen que cai no fim da linha: o hifen e da palavra, nao da hifenizacao (no STF 1237
# saiu "licençasprêmio"). 1a parte (antes do hifen) ou 2a parte (comeco da linha seguinte), sem acento e em
# minusculas; so palavras que nao sao pedaco de outra na hifenizacao
COMPOSTA_1A = {"licenca", "licencas", "auxilio", "auxilios", "salario", "salarios"}
COMPOSTA_2A = {"premio", "premios", "maternidade", "paternidade", "familia", "doenca", "reclusao", "alimentacao",
               "transporte", "refeicao", "geral", "gerais", "membro", "membros", "moradia", "saude", "creche",
               "funeral", "acidente", "natalidade", "presidente", "presidentes"}


def sem_acento(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def hifen_de_composta(antes, depois):
    """'licenças-' + 'prêmio': o hifen e da palavra composta (fica)."""
    a = sem_acento((re.findall(r"[^\W\d_]+(?=-$)", antes) or [""])[-1]).lower()
    d = sem_acento((re.findall(r"^[^\W\d_]+", depois) or [""])[0]).lower()
    return a in COMPOSTA_1A or d in COMPOSTA_2A


def juntar(partes):
    """Junta linhas desfazendo a hifenizacao do fim de linha ('tempora-' + 'riamente'); o hifen da palavra
    composta ('licenças-' + 'prêmio') fica."""
    txt = ""
    for p in partes:
        p = p.strip()
        if not p:
            continue
        if not txt:
            txt = p
        elif txt.endswith("/"):
            txt += p                        # "ARE 1.593.784 ED/" + "SC"
        elif txt.endswith("-") and not txt.endswith(" -"):
            if (re.search(r"[^\W\d_]-$", txt) and txt[-2].islower() and p[:1].islower()
                    and not hifen_de_composta(txt, p)):
                txt = txt[:-1] + p          # hifenizacao: some o hifen
            else:
                txt += p                    # hifen de palavra composta (ED-segundos)
        else:
            txt += " " + p
    return espacos(txt)


def dm(s):
    """'13.11.2026' -> ('13/11', '2026-11-13'); '' se nao for data."""
    m = re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", s or "")
    if not m:
        return "", ""
    d, mes, a = int(m.group(1)), int(m.group(2)), m.group(3)
    return "%02d/%02d" % (d, mes), "%s-%02d-%02d" % (a, mes, d)


# ------------------------------------------------------------------ STF
def stf(dados):
    return stf_texto(pdf_texto(dados, layout=True))


def stf_texto(t, info=None):
    """(data, itens) do texto 'pdftotext -layout'. Item: secao, ramo, titulo e, quando o
    RESUMO oficial foi lido e validado, resumo. info (dict, opcional) recebe "caixas" (RESUMO lidos)
    e "recusados" ({indice: caracteres}) para a linha TECNICO: resumo perdido nao fica em silencio."""
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
        elif atual is not None and s and (not s.isupper() or PROCESSO_STF.match(s)):
            # linha so com o processo ("ADI 7.069/GO .....7", "– ADI 7.901/PR ....7") e toda em
            # maiusculas, mas continua o titulo (no STF 1231 o titulo terminava em "Polícia Penal –")
            atual["titulo"] = juntar([atual["titulo"], s])
        else:
            atual = None
        if atual is not None and re.search(r"\.{4,}\s*\d*\s*$", atual["titulo"]):
            atual["titulo"] = re.sub(r"\s*\.{4,}\s*\d*\s*$", "", atual["titulo"])
            atual = None
    for it in itens:
        it["titulo"] = espacos(re.sub(r"\s*\.{4,}.*$", "", it["titulo"]))
    # RESUMO oficial: so associa se houver um para cada item do sumario, na mesma ordem
    resumos = resumos_stf(t[fim:] if fim > 0 else t)
    recusados = {}
    if itens and len(resumos) == len(itens):
        for i, (it, r) in enumerate(zip(itens, resumos)):
            if resumo_valido(r):
                it["resumo"] = r
            else:
                recusados[i] = len(r or "")
    if info is not None:
        info.update(caixas=len(resumos), recusados=recusados)
    return (data.group(0) if data else ""), itens


# classe processual do STF seguida de numero, com o travessao opcional do titulo (lista fechada: uma
# palavra-chave da coluna esquerda como "LEI 8.112/1990" nao pode virar continuacao do titulo)
PROCESSO_STF = re.compile(r"^(?:[–-]\s*)?(?:ADI|ADC|ADO|ADPF|ACO|AO|AP|AR|ARE|AI|AC|EP|Ext|EXT|HC|HD|IF|Inq|INQ|"
                          r"MI|MS|Pet|PET|PSV|Rcl|RCL|RE|RHC|RMS|SL|SS|STA|STP)\s+\d")
RODAPE_STF = re.compile(r"^\s*(INFORMATIVO STF\b.*|Edição \d+/\d{4}|\d{1,2} de (?:%s) de \d{4})\s*$" % MES)


def resumos_stf(t):
    """Texto de cada caixa 'RESUMO:' do corpo, na ordem. O PDF tem duas colunas: a esquerda
    com as palavras-chave, toda em caixa alta, e a direita com o resumo; depois de a coluna
    esquerda acabar, o resumo segue em largura total ate a primeira linha em branco."""
    L = t.splitlines()
    out = []
    for i, l in enumerate(L):
        k = l.find("RESUMO:")
        if k < 0:
            continue
        linhas = []
        resto = l[k + 7:]
        if resto.strip():
            linhas.append(" " * (k + 7) + resto)
        for m in L[i + 1:i + 60]:
            m = m.replace("\f", "")
            if not m.strip():
                if linhas:
                    break
                continue
            if "RESUMO:" in m:
                break
            if RODAPE_STF.match(m):
                continue
            linhas.append(m)
        out.append(corpo_resumo(linhas))
    return out


# depois da tese, o corpo da nota comeca por uma destas expressoes (rede do corpo_resumo)
DEPOIS_DO_RESUMO = re.compile(r"(?<=\.)\s+(?=(?:No caso|Na espécie|Na hipótese|Com base)\b)")


def corpo_resumo(linhas):
    """Texto da caixa RESUMO. col = coluna da 1a linha do corpo (a 1a com recuo >= 20), nao o menor recuo:
    no STF 1231 a linha "No caso, foram questionadas..." (recuo 37, corpo na 41) vinha logo depois da tese,
    sem linha em branco (a coluna das palavras-chave ocupava a linha), puxava o minimo para 37 e o resumo
    engolia a nota inteira (2.559 caracteres, recusado: a ADI 7.495 saiu sem a tese). A caixa termina na 1a
    linha que abre paragrafo a esquerda da coluna do corpo (recuo entre 20 e col-3), sem ser palavra-chave,
    depois de uma frase terminada em '.'. Rede: texto acima de RESUMO_MAX e cortado antes de "No caso",
    "Na espécie", "Na hipótese" ou "Com base" que venham depois de um ponto (o resto e o corpo da nota)."""
    recuo = lambda m: len(m) - len(m.lstrip())  # noqa: E731
    col = next((recuo(m) for m in linhas if recuo(m) >= 20), None)
    partes = []
    for m in linhas:
        if col is not None and recuo(m) >= col - 2:
            partes.append(m.strip())        # linha so da coluna do corpo
            continue
        mm = re.match(r"^(\s*\S.*?)\s{2,}(\S.*)$", m)
        if mm and caixa_alta(mm.group(1)) and (col is None or abs(mm.start(2) - col) <= 4):
            partes.append(mm.group(2))      # palavra-chave a esquerda + corpo a direita
            continue
        if caixa_alta(m):
            continue                        # so palavra-chave
        if col is not None and 20 <= recuo(m) < col - 2 and juntar(partes).endswith("."):
            break                           # paragrafo novo fora da caixa ("No caso, ..."): o resumo acabou
        partes.append(m.strip())            # largura total
    texto = juntar(partes)
    if len(texto) > RESUMO_MAX:
        m = DEPOIS_DO_RESUMO.search(texto)
        if m:
            texto = texto[:m.start()]
    return texto


def resumo_valido(s):
    """Termina em '.', tem 100-900 caracteres e nao traz palavras-chave vazadas da coluna
    esquerda (duas palavras seguidas em caixa alta). Na duvida, o item fica so com o titulo."""
    return (bool(s) and RESUMO_MIN <= len(s) <= RESUMO_MAX and s.endswith(".")
            and not re.search(r"\b[A-ZÁÉÍÓÚÂÊÔÃÕÇÀÜ]{3,}[;,]?\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇÀÜ]{3,}\b", s))


# ------------------------------------------------------------------ RG em Pauta
def rg(dados):
    return rg_texto(pdf_texto(dados, layout=False))


# (regex do cabecalho, secao para o leitor, estagio). Secao None = ignorar (noticias).
SECOES_RG = [(re.compile(p), s, e) for p, s, e in (
    (r"JULGAMENTOS", "Julgamentos", "tese fixada"),
    (r"ACÓRDÃOS PUBLICADOS", "Acórdãos Publicados", "tese publicada"),
    (r"TEMAS COM TRÂNSITO EM JULGADO", "Temas com Trânsito em Julgado", "trânsito em julgado"),
    (r"TEMAS EM JULGAMENTO", "Temas em Julgamento", "em votação no PV"),
    (r"TEMAS FINALIZADOS", "Temas Finalizados", "finalizado"),
    (r"TEMAS CANCELADOS", "Temas Cancelados", "tema cancelado"),
    (r"REPERCUSSÃO GERAL RECONHECIDA", "Repercussão Geral Reconhecida", "repercussão geral reconhecida"),
    (r"REPERCUSSÃO GERAL NEGADA", "Repercussão Geral Negada", "repercussão geral negada"),
    (r"(DEMAIS QUESTÕES|NOTÍCIAS DA REPERCUSSÃO GERAL).*", None, None),
    (r"PAUTAS? DO PLENÁRIO|PLENÁRIO PRESENCIAL", "Pauta do Plenário", "pauta do Plenário"),
    (r"PREVISTOS? PARA (?P<d>\d{1,2}\.\d{1,2}\.\d{4})", "Pauta do Plenário", "pauta do Plenário"),
    (r"SESSÕES VIRTUAIS DO PLENÁRIO", "Pauta da sessão virtual", "pauta da sessão virtual"),
    (r".*SESSÃO VIRTUAL.*?\bDE (?P<i>\d{1,2}(?:\.\d{1,2})?(?:\.\d{4})?) A (?P<f>\d{1,2}\.\d{1,2}\.\d{4})",
     "Pauta da sessão virtual", "pauta da sessão virtual"),
)]
# linhas em caixa alta que nao mudam de secao (placar, rotulos, super-secoes)
RUIDO_RG = {"INTEIRO TEOR", "MANIFESTAÇÃO DO RELATOR", "QUESTÃO CONSTITUCIONAL", "REPERCUSSÃO GERAL",
            "SUSPENSÃO NACIONAL", "MÉRITO DA REPERCUSSÃO", "MÉRITO DA REPERCUSSÃO GERAL", "PROCEDIMENTOS DE",
            "ADMISSIBILIDADE", "PROCEDIMENTOS DE ADMISSIBILIDADE", "PLACAR DO JULGAMENTO", "PLACAR",
            "REAFIRMAÇÃO DE JURISPRUDÊNCIA"}
SEM_RG = re.compile(r"(?i)(aus[êe]ncia|inexist[êe]ncia) d[ae] repercuss[ãa]o geral|n[ãa]o h[áa] repercuss[ãa]o geral")
PREVISAO = re.compile(r"\s*Data prevista para o fim do julgamento:\s*(\d{1,2}\.\d{1,2}\.\d{4})\.?")
CLASSES_RG = r"RE|ARE|AI|Rcl|RCL|ADI|ADPF|ADC|ADO|MS|MI|HC|RHC|SL|STP|ACO"
PROCESSO_RG = re.compile(r"^(?:%s)\s*\d[\d.]*" % CLASSES_RG)
CLASSE_RG = re.compile(r"(?:%s)" % CLASSES_RG)                     # so a classe, sem o numero
RELATOR_RG = re.compile(r"\s+(RELATORA?|RED\. ACÓRD\.):.*$")       # "PROCESSOS: RE 1.163.774-ED RELATORA: Min. ..." na mesma linha
# resto do numero que quebrou de linha depois de "-" ou "/": "ED-segundos", "AgR", "ED-AgR", "SC" (so letras, sem espaco)
SUFIXO_PROCESSO_RG = re.compile(r"[^\W\d_]{2,15}(?:[-/][^\W\d_]{2,15})*")
RG_RECONHECIDA = re.compile(r"(?i)reconheceu a exist[êe]ncia de repercuss[ãa]o geral")
RG_NEGADA = re.compile(r"(?i)(recusou|n[ãa]o reconheceu|negou)\b.{0,40}repercuss[ãa]o geral")
PENDENTE_RG = re.compile(r"(?i)^(em votação|pauta)\b")     # estagio sem resultado ainda (mesma regra do montador)


def pendente_rg(it):
    return bool(PENDENTE_RG.match(it.get("estagio") or "")) and not it.get("tese")


def faixa(nums):
    nums = sorted(nums)
    return ("%d a %d" % (nums[0], nums[-1])) if len(nums) > 1 else "%d" % nums[0]


def superados_por_data(n, itens, h):
    """Temas 'em votacao'/'em pauta' da RG n cuja situacao os boletins posteriores ja superaram.
    h = historico do produto ({numero: {"anunciada_em", "anunciada_na_edicao", ...}}). Exige DUAS
    edicoes posteriores anunciadas: o periodo da ultima comeca logo depois do da penultima, entao tudo
    o que estava previsto antes do anuncio da penultima ja teve o resultado num boletim publicado.
    Supera o tema com previsao anterior a essa data, ou sem previsao (a pauta e de semanas atras).
    Devolve {indice: motivo}."""
    pend = [i for i, it in enumerate(itens) if pendente_rg(it)]
    if not pend:
        return {}
    posteriores = sorted(m for m in h if m > n)
    datas = sorted(d for d in (h[m].get("anunciada_em") or h[m].get("anunciada_na_edicao") or ""
                               for m in posteriores) if d)
    if len(datas) < 2:
        return {}
    limite = datas[-2]
    motivo = "em votação/pauta nesta edição; situação superada pelos boletins seguintes (%s)" % faixa(posteriores)
    return {i: motivo for i in pend if not itens[i].get("previsao") or itens[i]["previsao"] < limite}


def superados_por_historico(n, itens, h):
    """Tema da RG n que ja saiu no e-mail com uma RG posterior (h[m]["temas"], ver historico()):
    a situacao de la e a mais recente; aqui seria repeticao. {indice: motivo}."""
    ja = {}
    for m in sorted((m for m in h if m > n), reverse=True):       # vale a posterior mais proxima
        for t, quando in (h[m].get("temas") or {}).items():
            ja[normalizar_tema(t)] = (m, quando)
    out = {}
    for i, it in enumerate(itens):
        m, quando = ja.get(normalizar_tema(it.get("tema")), (None, ""))
        if m is not None:
            out[i] = "tema já publicado com a RG %d%s" % (m, (" em " + ddmm(quando)) if ddmm(quando) else "")
    return out


TEMAS_DOC = {}                # {numero: (http, {temas} ou None)}: RGs baixadas so para conferir temas (cache do processo)


def temas_do_documento(m, consultas=None):
    """Temas (normalizados) do documento da RG m, baixado uma vez por processo e, no maximo,
    MAX_CONSULTAS_TEMAS documentos. None: nao abriu, nao leu tema ou o teto acabou (nada e superado).
    consultas (dict): recebe {"rg<m>": http} para a linha TECNICO."""
    if m not in TEMAS_DOC:
        if len(TEMAS_DOC) >= MAX_CONSULTAS_TEMAS:
            return None
        dormir(1.5)                     # sem rajada no mesmo servidor
        codigo, dados = baixar_documento("rg", m, MAX_TENTATIVAS_REVISITA)[:2]   # o que ja abriu vem do cache
        temas = None
        if codigo == 200 and dados and dados.startswith(b"%PDF"):
            try:
                temas = {normalizar_tema(it["tema"]) for it in rg_texto(pdf_texto(dados, layout=False))[1]} or None
            except Exception:  # noqa: BLE001 — a conferencia e reforco, nunca derruba a coleta
                temas = None
        TEMAS_DOC[m] = (codigo, temas)
    codigo, temas = TEMAS_DOC[m]
    if consultas is not None:
        consultas["rg%d" % m] = codigo
    return temas


def superados_por_documento(n, itens, h, ja=(), consultas=None):
    """Tema da RG n que tambem esta numa RG posterior publicada com destaques cujo item do historico nao
    gravou a lista (h[m]["temas_desconhecidos"]: o montador anterior a 17/11/2026 so escrevia "k de M
    destaques publicados"). Confere no documento dessa RG (temas_do_documento), as mais recentes primeiro,
    so para os indices que nao estao em `ja` (ja superados) e so enquanto sobrar algum. A situacao de la e a
    mais recente; aqui seria repeticao. Documento que nao abre: nada sai. {indice: motivo}."""
    resta = [i for i, it in enumerate(itens) if i not in ja and it.get("tema")]
    out = {}
    for m in sorted((m for m in h if m > n and h[m].get("temas_desconhecidos")), reverse=True):
        if not resta:
            break
        temas = temas_do_documento(m, consultas)
        if not temas:
            continue
        quando = ddmm(h[m]["temas_desconhecidos"])
        motivo = "tema também na RG %d, publicada%s" % (m, (" em " + quando) if quando else "")
        for i in [i for i in resta if normalizar_tema(itens[i]["tema"]) in temas]:
            out[i] = motivo
            resta.remove(i)
    return out


def aplicar_superados(r, motivos):
    """Tira de r["itens"] os indices de motivos ({indice: motivo}) e os guarda em r["itens_superados"]
    (superado: true, superado_motivo). Sem nenhum item restante, a edicao vira estado 'superada'
    (ok False, sem chave): nada a publicar."""
    if not motivos:
        return r
    ficam = [it for i, it in enumerate(r["itens"]) if i not in motivos]
    r["itens_superados"] = (r.get("itens_superados") or []) + [
        dict(it, superado=True, superado_motivo=motivos[i]) for i, it in enumerate(r["itens"]) if i in motivos]
    r["itens"] = ficam
    if not ficam:
        r.pop("chave", None)
        r.update(ok=False, estado="superada",
                 motivo="todos os temas já superados por boletins posteriores (nada a publicar)")
    return r


def deduplicar_temas(resultados):
    """Tema de uma RG herdada (atrasada/pulada) que tambem esta numa RG posterior aberta nesta execucao:
    fica so na mais recente (a situacao dela e a atual)."""
    rgs = [r for r in resultados if r.get("tipo") == "rg" and r.get("ok")]
    for r in sorted(rgs, key=lambda x: x["numero"], reverse=True):   # as posteriores ja estao resolvidas
        if r.get("situacao") not in ("atrasada", "pulada"):
            continue
        depois = {}
        for o in sorted(rgs, key=lambda x: x["numero"], reverse=True):
            if o["numero"] > r["numero"] and o.get("ok"):
                for it in o["itens"]:
                    depois[it["tema"]] = o["numero"]
        aplicar_superados(r, {i: "tema também na RG %d, aberta nesta execução" % depois[it["tema"]]
                              for i, it in enumerate(r["itens"]) if it["tema"] in depois})
    return resultados


def contexto_rg(l):
    """(secao, estagio, previsao_iso) se a linha for cabecalho de secao; None se nao for."""
    for rx, secao, estagio in SECOES_RG:
        m = rx.fullmatch(l)
        if not m:
            continue
        g = m.groupdict()
        if g.get("d"):
            ddmm, iso = dm(g["d"])
            return secao, "%s %s" % (estagio, ddmm), iso
        if g.get("f"):
            fim, iso = dm(g["f"])
            i = g["i"].split(".")
            ini = "%02d/%s" % (int(i[0]), ("%02d" % int(i[1])) if len(i) > 1 else fim[3:])
            return secao, "%s de %s a %s" % (estagio, ini, fim), iso
        return secao, estagio, ""
    if l not in RUIDO_RG and ":" not in l and re.fullmatch(r"[A-ZÁÉÍÓÚÂÊÔÃÕÇÜ ,–-]{6,}", l):
        return "", "", ""                    # secao desconhecida: sem estagio (nunca herda o anterior)
    return None


def rg_texto(t):
    """(periodo, itens) do texto 'pdftotext' (sem -layout). Item: secao, tema, processo,
    titulo, tese, decisao, estagio, previsao (AAAA-MM-DD ou ''), sem_repercussao_geral."""
    linhas = [l.strip() for l in t.replace("\f", "\n").splitlines() if l.strip()]
    periodo = next((l for l in linhas[:5] if re.search(r"\d{4}$", l) and " de " in l), "")
    itens, ctx, atual, campo = [], ("", "", ""), None, None
    for l in linhas:
        if re.fullmatch(r"Página \d+ de \d+", l):
            continue                         # quebra de pagina nao interrompe o campo
        if (atual is not None and campo == "processo" and atual["processo"].endswith(("-", "/"))
                and SUFIXO_PROCESSO_RG.fullmatch(RELATOR_RG.sub("", l))):
            # numero quebrado de linha: "ARE 1.487.739-" + "ED-segundos" (RG 394, Tema 1.308). Antes do
            # contexto_rg, para um sufixo em maiusculas ("ED-ED-ED") nao virar cabecalho de secao
            atual["processo"] += RELATOR_RG.sub("", l)
            continue
        c = contexto_rg(l)
        if c is not None:
            ctx, campo = c, None
            if c[0] is None:
                atual = None                 # noticias: nada ali completa o tema anterior
            continue
        m = re.match(r"^TEMA:\s*([\d.]+)(?:\s+PROCESSOS?:\s*(.+))?$", l)
        if m:
            atual = {"secao": ctx[0] or "", "tema": m.group(1), "processo": RELATOR_RG.sub("", m.group(2) or ""),
                     "titulo": "", "tese": "", "estagio": ctx[1] or "", "previsao": ctx[2] or "", "decisao": ""}
            itens.append(atual)
            campo = "processo" if atual["processo"] else None
            continue
        if atual is None:
            continue
        m = PREVISAO.search(l)
        if m:
            atual["previsao"] = dm(m.group(1))[1]
            l = PREVISAO.sub("", l).strip()
            if not l:
                campo = None
                continue
        m = re.match(r"^PROCESSOS?:\s*(.+)$", l)
        num = (re.match(r"^(?:%s)?\s*(\d.*)$" % re.escape(atual["processo"]), l)
               if campo == "processo" and CLASSE_RG.fullmatch(atual["processo"]) else None)
        if m:
            atual["processo"], campo = RELATOR_RG.sub("", m.group(1)), "processo"
        elif num:
            # so a classe na linha do TEMA ("PROCESSOS: RE") e o numero na seguinte ("RE1.612.904" ou "1.612.904"):
            # um processo so (a RG 398 saiu com "Tema 1.491 (RE; RE1.612.904)")
            atual["processo"] += " " + RELATOR_RG.sub("", num.group(1)).strip()
        elif campo == "processo" and PROCESSO_RG.match(l):
            atual["processo"] += "; " + l
        elif l.startswith("Título:"):
            atual["titulo"], campo = l[7:].strip(), "titulo"
        elif "seguinte tese:" in l:
            atual["tese"] = l.split("seguinte tese:", 1)[1].strip()
            campo = None if "”" in atual["tese"] else "tese"
        elif l.startswith("Decisão:") and not atual["decisao"]:
            atual["decisao"] = l[8:].strip()
            campo = None if atual["decisao"].endswith(".") else "decisao"
        elif re.match(r"^(RELATORA?:|RED\. ACÓRD\.:|Agenda 2030|INTEIRO TEOR|Decisão:|\(Presidente\)|MANIFESTAÇÃO|Placar)", l):
            campo = None
        elif campo in ("titulo", "tese", "decisao"):
            atual[campo] += " " + l
            if (campo == "tese" and "”" in l) or (campo == "decisao" and l.endswith(".")):
                campo = None
        else:
            campo = None
    vistos, unicos = {}, []
    for it in itens:                       # tema repetido entre secoes: vale o primeiro, completado
        for k in ("titulo", "tese", "processo", "decisao"):
            it[k] = espacos(it[k])
        it["processo"] = re.sub(r"\b(%s)(?=\d)" % CLASSES_RG, r"\1 ", it["processo"])   # "RE1.612.904"
        if it["tema"] in vistos:
            prim = vistos[it["tema"]]
            for k in ("titulo", "tese", "previsao", "decisao"):
                prim[k] = prim[k] or it[k]
            continue
        vistos[it["tema"]] = it
        unicos.append(it)
    for it in unicos:
        if it["estagio"] == "em votação no PV" and it["previsao"]:
            it["estagio"] += " até %s/%s" % (it["previsao"][8:10], it["previsao"][5:7])
        if not it["tese"] and it["estagio"] in ("tese publicada", "tese fixada"):
            it["estagio"] = {"tese publicada": "acórdão publicado", "tese fixada": "julgado"}[it["estagio"]]
        negada = bool(RG_NEGADA.search(it["decisao"]) or SEM_RG.search(it["decisao"]))
        if it["estagio"] == "finalizado":   # votacao da admissibilidade encerrada: o resultado esta na "Decisão:"
            if RG_RECONHECIDA.search(it["decisao"]):
                it["estagio"] = "repercussão geral reconhecida"
            elif negada:
                it["estagio"] = "repercussão geral negada"
        it["sem_repercussao_geral"] = negada or bool(SEM_RG.search(it["tese"] + " " + it["titulo"]))
    return periodo, unicos


# ------------------------------------------------------------------ STJ
SECOES_STJ = re.compile(r"^(RECURSOS REPETITIVOS|CORTE ESPECIAL|PRIMEIRA SEÇÃO|SEGUNDA SEÇÃO|TERCEIRA SEÇÃO|"
                        r"PRIMEIRA TURMA|SEGUNDA TURMA|TERCEIRA TURMA|QUARTA TURMA|QUINTA TURMA|SEXTA TURMA|"
                        r"EDIÇÃO EXTRAORDINÁRIA|PROCESSO EM SEGREDO DE JUSTIÇA|ÁREAS DO DIREITO|"
                        r"RELEVÂNCIA DA QUESTÃO FEDERAL|PROPOSTAS? DE RELEVÂNCIA DA QUESTÃO FEDERAL|"
                        r"PROPOSTAS? DE AFETAÇÃO)$")
# secao de afetacao (desde o 910, 17/11/2026: "PROPOSTA DE RELEVÂNCIA DA QUESTÃO FEDERAL", Temas de Relevancia
# 1480 a 1485): a nota nao tem o rotulo "Destaque" — o texto e a controversia afetada, no cabecalho da nota
PROPOSTA_STJ = re.compile(r"^PROPOSTAS? DE ", re.I)
ORGAO_STJ = re.compile(r"\b(Corte Especial|(?:Primeira|Segunda|Terceira) Seção|"
                       r"(?:Primeira|Segunda|Terceira|Quarta|Quinta|Sexta) Turma)\b", re.I)
# "(Repetitivo Tema 1270 )" (ate o 909), "( Tema repetitivo 1180 )", "(Tema de Relevância 1334)" (desde o 910)
PRECEDENTE_STJ = re.compile(r"\(\s*(?:(?P<antes>Repetitivo|RQF)\s+)?Tema(?:\s+(?P<depois>repetitivo|de\s+Relev\S*))?"
                            r"\s+(?P<n>[\d.]+)\s*\)", re.I)
ROTULOS_STJ = ("Processo", "Ramo do Direito", "Tema", "Destaque", "Informações do Inteiro Teor",
               "Informações Adicionais", "Compartilhe:")
# uma linha do rotulo "Processo": numero (com "AgInt no", "AgInt nos EDcl no", "ProRQF no"...) e o resto (relator,
# orgao, data, tema)
PROCESSO_STJ = re.compile(r"^(?P<num>(?:[A-Za-z]+\s+n[oa]s?\s+)*[A-Z][A-Za-z]*\s+[\d.]+(?:-[A-Z]{2})?)\s*,\s*"
                          r"(?P<resto>\S.*)$")
NOTA_STJ = re.compile(r"[?&]livre=@CNOT=(\d+)")


def stj(dados, numero):
    data, itens, _ = stj_html(dados.decode("cp1252", "replace"), numero)
    return data, itens


def cabecalho_stj(t, numero):
    return bool(re.search(r"Informativo de Jurisprud\S* n(?:\.|º|°|o\.?)\s*0*%d\b" % numero, t))


def processo_stj(linhas):
    """As linhas do rotulo "Processo" numa so, sem espaco antes da virgula nem dentro dos parenteses
    ("REsp 1.995.908-DF , Rel." / "( Tema repetitivo 1180 )"), sem linha repetida (o 904 trazia o
    REsp 2.250.086-SP duas vezes) e, quando os processos so diferem no numero, juntos: "REsp 1-SP,
    REsp 2-SP e REsp 3-SP, Rel. Ministro ..., julgado em ... (Tema 1281)." — no 904 a mesma linha
    processual saia 4 vezes no Tema 1281."""
    ls = []
    for l in linhas:
        l = re.sub(r"\(\s+", "(", re.sub(r"\s+([,;)])", r"\1", l)).strip()
        if l and l not in ls:
            ls.append(l)
    partes = [PROCESSO_STJ.match(l) for l in ls]
    if len(ls) > 1 and all(partes) and len({p.group("resto") for p in partes}) == 1:
        nums = [p.group("num") for p in partes]
        return "%s e %s, %s" % (", ".join(nums[:-1]), nums[-1], partes[0].group("resto"))
    return " ".join(ls)


def tipo_stj(secao, processo):
    """(tipo, orgao, precedente): Afetação | Repetitivo | RQF | Corte Especial | Seção | Turma."""
    om = ORGAO_STJ.search(processo or "") or ORGAO_STJ.search(secao or "")
    orgao = " ".join(w.capitalize() for w in om.group(1).split()) if om else ""
    pm = PRECEDENTE_STJ.search(processo or "")
    precedente = ("Tema %s" % pm.group("n")) if pm else ""
    rotulo = ""
    if pm and pm.group("antes"):
        rotulo = pm.group("antes").upper()
    elif pm and pm.group("depois"):
        rotulo = "REPETITIVO" if pm.group("depois").lower() == "repetitivo" else "RQF"
    s = (secao or "").upper()
    if PROPOSTA_STJ.match(s):
        tipo = "Afetação"
    elif s == "RECURSOS REPETITIVOS" or rotulo == "REPETITIVO":
        tipo = "Repetitivo"
    elif s == "RELEVÂNCIA DA QUESTÃO FEDERAL" or rotulo == "RQF":
        tipo = "RQF"
    elif orgao == "Corte Especial":
        tipo = "Corte Especial"
    elif orgao.endswith("Seção"):
        tipo = "Seção"
    elif orgao.endswith("Turma"):
        tipo = "Turma"
    else:
        tipo = ""
    return tipo, orgao, precedente


def stj_html(t, numero, info=None):
    """(data, itens, cabecalho_presente) da pagina da edicao. Item: secao, tema, processo,
    ramo, destaque (todas as teses do bloco), tipo, orgao, precedente. Nota de afetacao (secao
    PROPOSTA DE ...) nao tem "Destaque": o destaque e o proprio texto da nota (a controversia).
    info (dict, opcional) recebe "notas": quantas notas a pagina tem (links @CNOT distintos, ou
    cabecalhos de nota), para a linha TECNICO acusar nota que o parser nao leu."""
    cab_presente = cabecalho_stj(t, numero)
    if info is not None:
        info["notas"] = len(set(NOTA_STJ.findall(t)))
    if "Destaque" not in t and not re.search(r"PROPOSTAS? DE ", t):
        return "", [], cab_presente
    t = re.sub(r"(?is)<(script|style).*?</\1>", " ", t)
    t = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</h\d>|</li>", "\n", t)
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    L = [re.sub(r"\s+", " ", l).strip() for l in t.split("\n")]
    L = [l for l in L if l]
    # ate 10/2026 o cabecalho era "n. 907"; desde o 908 e "nº 908" (o script deixou de achar a edicao)
    cab = re.compile(r"^Informativo de Jurisprud\S* n(?:\.|º|°|o\.?)\s*0*%d - (\d{1,2} de \w+ de \d{4})\.\s*(.*)$" % numero)
    fim_bloco = lambda l: bool(SECOES_STJ.match(l) or cab.match(l) or l in ROTULOS_STJ)  # noqa: E731

    def seguintes(i, maximo):
        out = []
        for l in L[i + 1:]:
            if fim_bloco(l):
                break
            out.append(l)
        return out if len(out) <= maximo else out[:1]   # sem rotulo de fim: fica so a 1a linha

    data, itens, secao, atual = "", [], "", None
    for i, l in enumerate(L):
        if SECOES_STJ.match(l):
            secao = l.title()
            continue
        m = cab.match(l)
        if m:
            data = data or m.group(1)
            if m.group(2):
                atual = {"secao": secao, "tema": m.group(2).strip(), "processo": "", "ramo": "", "destaque": ""}
                itens.append(atual)
            continue
        if atual is None or i + 1 >= len(L):
            continue
        if l == "Processo" and not atual["processo"]:
            atual["processo"] = processo_stj(seguintes(i, 6))
        elif l == "Ramo do Direito" and not atual["ramo"]:
            atual["ramo"] = L[i + 1]
        elif l == "Destaque" and not atual["destaque"]:
            atual["destaque"] = " ".join(seguintes(i, 10))
    for it in itens:
        if not it["destaque"] and PROPOSTA_STJ.match(it["secao"]):
            it["destaque"] = it["tema"]     # afetacao: a nota e a controversia ("A Corte Especial acolheu a proposta...")
    if info is not None:
        info["notas"] = max(info.get("notas") or 0, len(itens))
    itens = [it for it in itens if it["destaque"]]
    for it in itens:
        it["tipo"], it["orgao"], it["precedente"] = tipo_stj(it["secao"], it["processo"])
    return data, itens, cab_presente


# ------------------------------------------------------------------ historico
SEM_CONTEUDO = re.compile(r"(?i)n[aã]o (foi |estava )?(acess|lid)|inacess|\b403\b|sem teses|link gen[eé]rico|"
                          r"s[oó] n[uú]mero")
# tema citado no texto gravado de um item de RG: "Tema 1.483", "Tema 1483", "TEMA: 977", "Tema nº 118",
# "Temas 1.493, 1.494 e 118" (nunca "nº 397" da edicao nem o numero de um processo)
TEMA_NUM = r"\d{1,3}(?:\.\d{3})+|\d{1,5}"
TEMAS_TEXTO = re.compile(r"(?i)\bTemas?\b:?\s*(?:n(?:º|°|o\.?|\.)\s*)?((?:%s)(?:(?:\s*,\s*|\s+e\s+)(?:%s))*)(?![\d.]*\d)"
                         % (TEMA_NUM, TEMA_NUM))
# observacao que o montador grava no item com destaques; antes de 17/11/2026 ele nao gravava `temas` junto
PUBLICADOS_SEM_LISTA = re.compile(r"\b\d+ de \d+ destaques publicados\b")


def normalizar_tema(t):
    """'1483', '01.483', '1.483' -> '1.483' (formato do documento e do campo `temas`); o que nao for
    numero volta so sem espacos."""
    s = str(t or "").strip()
    digitos = re.sub(r"\D", "", s)
    if digitos and re.fullmatch(r"[\d.]+", s):
        return "{:,}".format(int(digitos)).replace(",", ".")
    return s


def temas_do_texto(it):
    """Temas citados no texto gravado de um item de RG sem o campo `temas` (destaques_texto, titulo, resumo,
    observacao), normalizados e sem repeticao, na ordem do texto."""
    partes = []
    for k in ("destaques_texto", "titulo", "resumo", "observacao"):
        v = it.get(k)
        partes.extend(v if isinstance(v, list) else [v])
    texto = html.unescape(re.sub(r"<[^>]+>", " ", " ".join(str(p) for p in partes if p)))
    out = []
    for m in TEMAS_TEXTO.finditer(texto):
        for t in re.findall(TEMA_NUM, m.group(1)):
            t = normalizar_tema(t)
            if t not in out:
                out.append(t)
    return out


def historico():
    """{produto: {numero: {"vazio", "anunciada_em", "anunciada_na_edicao"[, "temas"][, "temas_desconhecidos"]}}}
    do historico principal e dos arquivos. vazio=True: a edicao saiu so com numero/data/link e os
    destaques ainda nao. anunciada_em: 5o campo da chave do anuncio (data do e-mail/edicao);
    anunciada_na_edicao: data da execucao que a anunciou. So RG, opcionais, so de itens com conteudo:
    temas = {tema normalizado: data da execucao} dos temas que ja sairam no e-mail, lidos do campo `temas`
    do item (lista gravada pelo montador) ou, sem o campo, dos temas citados no texto gravado do item
    (temas_do_texto); temas_desconhecidos = data da execucao (a mais antiga) de um item sem o campo cuja
    observacao e a do montador ("k de M destaques publicados"): destaques publicados, lista nao gravada.
    So itens da propria RG (chave stf|informativo|repercussao-geral-N): tema citado em item de outro tipo
    (Midia, Opiniao, Informativo STF, STF Jurisprudencia) nao conta."""
    hist = {"stf": {}, "rg": {}, "stj": {}}
    ignorar = janela().get("ignorar_execucao") or ""
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
                info = hist[tipo].setdefault(n, {"vazio": True, "anunciada_em": "", "anunciada_na_edicao": ""})
                # um registro com conteudo (ou o "-conteudo" posterior) vence o anuncio vazio
                info["vazio"] = info["vazio"] and vazio
                edicao = str(e.get("date") or (e.get("execution_id") or "")[:10])
                if tipo == "rg" and not vazio:
                    if isinstance(it.get("temas"), list):
                        lista = it["temas"]
                    else:
                        # item gravado sem o campo (orquestrador, ou montador anterior a 17/11/2026): os temas
                        # citados no texto gravado; o montador que so diz "k de M destaques publicados" deixa a
                        # lista para a conferencia no documento (superados_por_documento)
                        lista = temas_do_texto(it)
                        if PUBLICADOS_SEM_LISTA.search(str(it.get("observacao") or "")) and edicao and (
                                not info.get("temas_desconhecidos") or edicao < info["temas_desconhecidos"]):
                            info["temas_desconhecidos"] = edicao
                    for t in lista:
                        t = normalizar_tema(t)
                        if t:
                            info.setdefault("temas", {}).setdefault(t, edicao)
                if not m.group(3):
                    if not info["anunciada_na_edicao"] or (edicao and edicao < info["anunciada_na_edicao"]):
                        info["anunciada_na_edicao"] = edicao
                        info["anunciada_em"] = p[4] if len(p) > 4 and re.fullmatch(r"\d{4}-\d\d-\d\d", p[4]) else ""
    return hist


def publicados():
    """{produto: {numero: sem_conteudo}} — formato antigo, usado tambem pelo montar_email.py."""
    return {t: {n: i["vazio"] for n, i in d.items()} for t, d in historico().items()}


# ------------------------------------------------------------------ obtencao
def obter(tipo, n, situacao="nova", anuncio=None, hist_produto=None, tentativas=1, prazo=None):
    """Baixa e le uma edicao (ate `tentativas` pedidos, ver baixar_documento). estado: ok | inexistente (404; STJ sem o
    cabecalho do numero) | parser (abriu, tem marcas de destaque, 0 lidos) | sem_temas
    (abriu, sem nenhum destaque) | indeterminado (403, 0, outro codigo, nao e PDF) |
    superada (RG aberta cujos temas os boletins posteriores ja superaram todos).
    hist_produto: historico() do produto (None = le o historico quando precisar).
    No registro: tentativas (pedidos feitos; 0 = veio do cache da execucao), http_1a_tentativa
    (quando houve mais de um pedido) e cache (True quando nao houve pedido)."""
    url = URL[tipo] % n
    codigo, dados, feitos, primeiro, do_cache = baixar_documento(tipo, n, tentativas, prazo)
    r = {"tipo": tipo, "numero": n, "id": "%s%d" % (tipo, n), "url": url, "http": codigo,
         "situacao": situacao, "ok": False, "tentativas": feitos}
    if feitos > 1:
        r["http_1a_tentativa"] = primeiro
    if do_cache:
        r["cache"] = True
    if situacao == "atrasada":
        if anuncio is None:
            try:
                anuncio = historico()[tipo].get(n)
            except Exception:  # noqa: BLE001 — a data do anuncio e enfeite, nunca bloqueia
                anuncio = None
        if anuncio:
            r["anunciada_em"] = anuncio.get("anunciada_em") or anuncio.get("anunciada_na_edicao") or ""
            r["anunciada_na_edicao"] = anuncio.get("anunciada_na_edicao") or ""
    if codigo == 404:
        return dict(r, estado="inexistente", motivo="ainda não publicada (404)")
    if codigo != 200 or not dados:
        return dict(r, estado="indeterminado", motivo="documento não abriu (servidor recusou ou não respondeu)")
    if tipo in ("stf", "rg"):
        if not dados.startswith(b"%PDF"):
            return dict(r, estado="indeterminado", motivo="resposta não é PDF")
        t = pdf_texto(dados, layout=(tipo == "stf"))
        if tipo == "stf":
            info = {}
            data, itens = stf_texto(t, info)
            com = sum(1 for it in itens if it.get("resumo"))
            if itens and com < len(itens):      # resumo perdido nao fica em silencio (TECNICO)
                if info.get("recusados"):
                    motivo = "; recusados: " + ", ".join("%d (%d car.)" % x for x in sorted(info["recusados"].items()))
                elif info.get("caixas") != len(itens):
                    motivo = " (%d caixas RESUMO)" % info.get("caixas", 0)
                else:
                    motivo = ""
                r["resumos"] = "%d/%d%s" % (com, len(itens), motivo)
        else:
            data, itens = rg_texto(t)
        marcas = ("»" in t or "RESUMO:" in t) if tipo == "stf" else bool(re.search(r"(?m)^\s*TEMA:", t))
    else:
        info = {}
        data, itens, marcas = stj_html(dados.decode("cp1252", "replace"), n, info)
        if not itens and not marcas:
            return dict(r, estado="inexistente", data="", itens=[],
                        motivo="ainda não publicada (página sem o cabeçalho do número)")
        if (info.get("notas") or 0) > len(itens):
            r["notas"] = info["notas"]          # nota que o parser nao leu: "k de N notas lidas" no TECNICO
    r.update(ok=bool(itens), data=data, itens=itens)
    if itens:
        r.update(estado="ok", motivo="")
        r["chave"] = chave(r)
        if situacao == "atrasada":      # a chave do anuncio ja existe no historico: o conteudo ganha a sua
            p = r["chave"].split("|")
            r["chave"] = "|".join(p[:2] + [p[2] + "-conteudo"] + p[3:])
        if tipo == "rg":
            if hist_produto is None:
                try:
                    hist_produto = historico()["rg"]
                except Exception:  # noqa: BLE001 — sem historico, nada a superar
                    hist_produto = {}
            motivos = superados_por_historico(n, itens, hist_produto)
            motivos.update(superados_por_data(n, itens, hist_produto))
            consultas = {}
            motivos.update(superados_por_documento(n, itens, hist_produto, motivos, consultas))
            if consultas:
                r["temas_consultados"] = consultas
            aplicar_superados(r, motivos)
    elif marcas:
        r.update(estado="parser", motivo="documento abriu, mas nenhum destaque foi lido (layout mudou?)")
    else:
        r.update(estado="sem_temas", motivo="documento abriu sem nenhum destaque")
    return r


class Coleta:
    """Faz os pedidos espacados e controla o orcamento da insistencia: no maximo ORCAMENTO_EXTRAS
    pedidos alem do 1o de cada documento e nenhum depois de PRAZO_S (contado do 1o pedido)."""

    def __init__(self):
        self.pedidos = 0
        self.extras = ORCAMENTO_EXTRAS
        self.prazo = None

    def pedir(self, tipo, n, situacao, anuncio=None, hist_produto=None, tentativas=1):
        if self.pedidos:
            dormir(1.5)                     # sem rajada no mesmo servidor
        else:
            self.prazo = relogio() + PRAZO_S
        self.pedidos += 1
        r = obter(tipo, n, situacao, anuncio, hist_produto,
                  tentativas=max(1, min(tentativas, 1 + self.extras)), prazo=self.prazo)
        self.extras -= max(0, (r.get("tentativas") or 1) - 1)
        return r


def hoje_iso():
    """Data de hoje (AAAA-MM-DD): a do janela.json (o inicio.py grava "data"); sem ela, a do execution_id;
    fora da rotina, a do relogio."""
    j = janela()
    for d in (str(j.get("data") or ""), str(j.get("execution_id") or "")[:10]):
        if re.fullmatch(r"\d{4}-\d\d-\d\d", d):
            return d
    return date.today().isoformat()


def tentativas_novo(tipo, anterior, hoje):
    """Pedidos para o numero novo: MAX_TENTATIVAS_SONDA no STF e na RG quando a edicao anterior (data
    AAAA-MM-DD do anuncio ou do documento) saiu ha menos de CADENCIA_SONDA_DIAS dias — a cadencia e semanal,
    e o 403 do firewall esconde o 404 do numero que ainda nao saiu (60 de 60 pedidos em 18-20/11/2026):
    insistir nao converge e so gasta pedidos e tempo. Senao (ou STJ, sem firewall), MAX_TENTATIVAS."""
    if tipo in ("stf", "rg"):
        try:
            dias = (date.fromisoformat(hoje) - date.fromisoformat(anterior)).days
        except (TypeError, ValueError):
            dias = None
        if dias is not None and dias < CADENCIA_SONDA_DIAS:
            return MAX_TENTATIVAS_SONDA
    return MAX_TENTATIVAS


def coletar(hist):
    """Plano completo da execucao automatica: por produto, as revisitas recentes (base e
    base-1), as novas (sonda curta no STF/RG logo depois de uma edicao: tentativas_novo) e, no
    fim, as revisitas antigas — ate MAX_REVISITAS_ANTIGAS do STF/RG e, a parte, ate
    MAX_REVISITAS_STJ do STJ (sem firewall, 1 pedido: o STF barrado nao toma a vaga dele;
    em 20/11/2026 o stj903 seguia parado porque o stf1231 e o stf1230 levavam as duas vagas).
    Uma revisita 'superada' (aberta, todos os temas superados) conta como feita. No fim, o tema de
    RG herdada que tambem esta numa RG posterior aberta agora fica so na posterior (deduplicar_temas)."""
    c, resultados, antigas, parado = Coleta(), [], [], set()
    hoje = hoje_iso()
    for tipo in ("stf", "rg", "stj"):
        h = hist.get(tipo) or {}
        if not h:
            resultados.append({"tipo": tipo, "ok": False, "situacao": "nova", "estado": "sem_historico",
                               "motivo": "nenhuma edição no histórico"})
            continue
        base = max(h)
        anterior = h[base].get("anunciada_em") or h[base].get("anunciada_na_edicao") or ""
        for n in (base, base - 1):         # as mais recentes primeiro
            if n not in h:
                situacao = "pulada"
            elif h[n]["vazio"]:
                situacao = "atrasada"
            else:
                continue
            if tipo in parado:
                break
            r = c.pedir(tipo, n, situacao, h.get(n), h, MAX_TENTATIVAS)
            resultados.append(r)
            if r["estado"] == "inexistente":
                parado.add(tipo)            # parar no 404
        falhas, inexistente = 0, None
        for n in range(base + 1, base + 4):
            if falhas >= 2:
                break                       # dois numeros novos seguidos sem edicao: parar
            # depois de um "ainda nao publicada" o numero seguinte nao existe: 1 pedido basta
            tentativas = 1 if inexistente is not None else tentativas_novo(tipo, anterior, hoje)
            r = c.pedir(tipo, n, "nova", None, h, tentativas)
            if inexistente is None and tentativas < MAX_TENTATIVAS:
                r["sonda_curta"] = True
            if r["estado"] == "indeterminado":
                if inexistente is not None:
                    r["estado"] = "nao_verificavel"
                    r["motivo"] = "%d ainda não publicada; %d não verificável" % (inexistente, n)
                resultados.append(r)
                break                       # servidor recusou ate o fim: nao insistir nos numeros seguintes
            resultados.append(r)
            if r["ok"]:
                falhas = 0
                anterior = (r.get("chave") or "").split("|")[-1] or hoje   # a seguinte se mede por esta
            else:
                falhas += 1
                if r["estado"] == "inexistente" and inexistente is None:
                    inexistente = n
        for n in range(base - 2, base - JANELA_REVISITA - 1, -1):
            if n in h and h[n]["vazio"]:
                antigas.append((h[n]["anunciada_em"] or h[n]["anunciada_na_edicao"], tipo, n))
    feitas, teto = {}, {"stf": MAX_REVISITAS_ANTIGAS, "stj": MAX_REVISITAS_STJ}
    for _, tipo, n in sorted(antigas, key=lambda a: (a[0], a[2]), reverse=True):
        vaga = "stj" if tipo == "stj" else "stf"    # STF e RG dividem as vagas; o STJ tem a sua
        if feitas.get(vaga, 0) >= teto[vaga] or tipo in parado:
            continue
        feitas[vaga] = feitas.get(vaga, 0) + 1
        r = c.pedir(tipo, n, "atrasada", hist[tipo].get(n), hist[tipo], MAX_TENTATIVAS_REVISITA)
        r["revisita"] = True
        resultados.append(r)
        if r["estado"] == "inexistente":
            parado.add(tipo)
    return deduplicar_temas(resultados)


# ------------------------------------------------------------------ saida
def linha_item(tipo, it):
    """Indice curto para o orquestrador escolher; o texto integral fica no JSON."""
    if tipo == "stf":
        return "[%s] %s — %s%s" % (it["secao"], it["ramo"], curto(it["titulo"], 150),
                                   " (com resumo)" if it.get("resumo") else "")
    if tipo == "rg":
        rotulo = it.get("estagio") or it.get("secao") or "?"
        if it.get("sem_repercussao_geral"):
            rotulo += " · sem RG"
        return "[%s] Tema %s — %s%s" % (rotulo, it["tema"], curto(it["titulo"], 150),
                                       " (com tese)" if it["tese"] else "")
    if it.get("tipo") in ("Repetitivo", "RQF", "Afetação"):
        partes = (it["tipo"], it.get("precedente"), it.get("orgao"))
    else:
        partes = (it.get("orgao") or it.get("tipo"),)
    rotulo = " · ".join(x for x in partes if x) or it.get("secao") or "?"
    return "[%s] %s%s" % (rotulo, (it["ramo"] + " — ") if it.get("ramo") else "", curto(it["tema"], 150))


def ddmm(iso):
    return "%s/%s" % (iso[8:10], iso[5:7]) if re.fullmatch(r"\d{4}-\d\d-\d\d", iso or "") else ""


def imprimir_edicao(r):
    rot = ""
    if r["situacao"] == "atrasada":
        quando = ddmm(r.get("anunciada_em"))
        rot = " — ATRASADA%s%s" % (", revisita" if r.get("revisita") else "",
                                   (" (anunciada em %s)" % quando) if quando else "")
    elif r["situacao"] == "pulada":
        rot = " — PULADA (nunca saiu)"
    print("%s %d [id %s] (%s)%s — %d destaques" % (NOME[r["tipo"]], r["numero"], r["id"], r["data"], rot,
                                                   len(r["itens"])))
    for n, it in enumerate(r["itens"][:MAX_INDICE]):
        print("  %d %s" % (n, linha_item(r["tipo"], it)))
    if len(r["itens"]) > MAX_INDICE:
        print("  … +%d destaques só no JSON (índices %d a %d)" % (len(r["itens"]) - MAX_INDICE, MAX_INDICE,
                                                                 len(r["itens"]) - 1))
    for motivo, temas in superados_por_motivo(r):
        print("  fora do e-mail — %s: %s %s" % (motivo, "Temas" if len(temas) > 1 else "Tema", ", ".join(temas)))


def superados_por_motivo(r):
    """[(motivo, [temas])] dos itens_superados, na ordem do documento."""
    grupos = {}
    for it in r.get("itens_superados") or []:
        grupos.setdefault(it.get("superado_motivo") or "superado", []).append(str(it.get("tema") or "?"))
    return list(grupos.items())


def ref_email(r):
    return "{\"ref\": \"%s\", \"data\": \"AAAA-MM-DD\", \"url\": \"<link do e-mail>\"}" % r["id"]


def sem_edicao(tipo, rs):
    """Linha unica do produto sem edicao nova (None se houver edicao nova ou erro a relatar)."""
    novas = [r for r in rs if r.get("situacao") == "nova"]
    if any(r.get("ok") or r.get("estado") in ("indeterminado", "parser") for r in novas):
        return None
    if any(r.get("estado") == "sem_historico" for r in novas):
        return "SEM EDICAO NOVA %s (nenhuma edição no histórico: não há de onde partir)" % NOME[tipo]
    partes, ja = [], False
    for r in novas:
        e = r.get("estado")
        if e == "inexistente" and not ja:
            partes.append("%d ainda não publicada" % r["numero"])
            ja = True
        elif e == "nao_verificavel":
            partes.append("%d não verificável" % r["numero"])
        elif e == "sem_temas":
            partes.append("%d aberta, sem destaques" % r["numero"])
    return "SEM EDICAO NOVA %s (%s)" % (NOME[tipo], "; ".join(partes) or "nada a verificar")


def janela():
    try:
        j = json.load(open(tmp("janela.json"), encoding="utf-8"))
        return j if isinstance(j, dict) else {}
    except Exception:
        return {}


def status_fonte(resultados):
    """{"status", "detalhe", "script", "execution_id", "sem_abrir", "falhas"} do id informativos_docs (contrato de
    fontes_status.json; execution_id do janela.json, para descartar entrada velha). "falha" so quando o
    script nao consegue ler: parser (layout mudou) ou produto sem historico. Documento que nao abriu (403
    do firewall) nao derruba a fonte aqui: o numero novo ainda nao anunciado da 403 todo dia (o firewall
    esconde o 404) e virava "falhou" ao leitor (18 a 20/11/2026, stf1238 e rg399); a edicao anunciada por
    e-mail que nao abriu quem acusa e o montador (item citado que sai sem conteudo, montar_email.py).
    sem_abrir: ids novos ou anunciados sem conteudo (base e base-1) que nao abriram; a revisita antiga que
    nao abriu fica so no detalhe. falhas: ids com parser ou o produto sem historico (o montador os nomeia)."""
    falhas, abertas, revisitas, superadas, sem_abrir, ids_falha = [], [], [], [], [], []
    for r in resultados:
        e = r.get("estado")
        if r.get("ok"):
            abertas.append(r["id"])
        elif e == "superada":
            superadas.append(r["id"])                                     # abriu; nada novo a publicar
        elif e == "sem_historico":
            falhas.append("%s sem histórico" % r["tipo"])
            ids_falha.append(r["tipo"])
        elif e == "parser":
            falhas.append("%s parser" % r["id"])
            ids_falha.append(r["id"])
        elif e == "indeterminado" and r.get("revisita"):
            revisitas.append("%s http %s" % (r["id"], r.get("http")))   # passivo antigo: nao derruba a fonte
        elif e == "indeterminado":
            sem_abrir.append(r)
    partes = []
    if falhas:
        partes.append("falha: " + ", ".join(falhas))
    partes.append(("abertas: " + ", ".join(abertas)) if abertas else "sem edição aberta" if falhas
                  else "sem edição nova")
    for sit, rotulo in (("nova", "nova sem abrir"), ("atrasada", "anunciada sem abrir"), ("pulada", "pulada sem abrir")):
        ids = ["%s http %s" % (r["id"], r.get("http")) for r in sem_abrir if r.get("situacao") == sit]
        if ids:
            partes.append("%s: %s" % (rotulo, ", ".join(ids)))
    if superadas:
        partes.append("superadas: " + ", ".join(superadas))
    if revisitas:
        partes.append("revisita sem abrir: " + ", ".join(revisitas))
    return {"status": "falha" if falhas else "ok", "detalhe": "; ".join(partes)[:200], "script": SCRIPT,
            "execution_id": janela().get("execution_id") or "", "sem_abrir": [r["id"] for r in sem_abrir],
            "falhas": ids_falha}


def gravar_fontes_status(chaves, caminho=None):
    """Mescla as chaves deste script em $ROBOZINHO_TMP/fontes_status.json (lido, atualizado e
    regravado sob trava exclusiva em fontes_status.json.lock; troca atomica). caminho: outro arquivo
    (o montador grava ali a decisao final de informativos_docs, montar_email.status_informativos)."""
    caminho = caminho or tmp("fontes_status.json")
    try:
        os.makedirs(os.path.dirname(caminho), exist_ok=True)
        with open(caminho + ".lock", "a") as trava:
            fcntl.flock(trava, fcntl.LOCK_EX)
            try:
                atual = json.load(open(caminho, encoding="utf-8"))
                if not isinstance(atual, dict):
                    atual = {}
            except Exception:
                atual = {}
            atual.update(chaves)
            temp = caminho + ".%d.tmp" % os.getpid()
            with open(temp, "w", encoding="utf-8") as f:
                json.dump(atual, f, ensure_ascii=False, indent=1)
            os.replace(temp, caminho)
    except Exception as e:  # noqa: BLE001 — status e reforco, nunca derruba a coleta
        print("AVISO: fontes_status.json não gravado (%s)" % e)


def imprimir(resultados):
    ok = [r for r in resultados if r.get("ok")]
    for r in ok:
        if r["situacao"] == "nova":
            imprimir_edicao(r)
    atraso = [r for r in ok if r["situacao"] in ("atrasada", "pulada")]
    if atraso:
        print("EM ATRASO — anunciadas antes sem destaques (ou puladas): publique agora, como herdada")
        for r in atraso:
            imprimir_edicao(r)
    for r in resultados:
        if r.get("ok"):
            continue
        nome, sit, e = NOME[r["tipo"]], r.get("situacao"), r.get("estado")
        if (sit == "atrasada" and r.get("revisita")) or e == "superada":
            continue                        # revisita antiga que nao abriu / edicao ja superada: so na linha TECNICO
        if e == "parser":
            print("ERRO PARSER %s %d [id %s]: %s — %s" % (
                nome, r["numero"], r["id"], r["motivo"],
                "já anunciada: não cite; o parser precisa de ajuste" if sit == "atrasada" else
                "só cite se o coletor Gmail trouxe o e-mail desta edição: " + ref_email(r)))
        elif sit == "atrasada":
            quando = ddmm(r.get("anunciada_em"))
            print("SEGUE SEM CONTEUDO %s %d [id %s]%s: documento não abriu — cite {\"ref\": \"%s\"} assim mesmo; "
                  "o montador tenta abrir de novo e, sem sucesso, descarta o item sozinho"
                  % (nome, r["numero"], r["id"], (" (anunciada em %s)" % quando) if quando else "", r["id"]))
        elif e == "indeterminado":
            print("ERRO %s %d [id %s]: documento não abriu (%s) — "
                  "sem e-mail desta edição, não cite nem reporte ao leitor; com o e-mail do coletor Gmail: %s"
                  % (nome, r["numero"], r["id"], "sonda curta; talvez ainda não publicada" if r.get("sonda_curta")
                     else "servidor recusou o acesso; não é inexistência", ref_email(r)))
    for tipo in ("stf", "rg", "stj"):
        linha = sem_edicao(tipo, [r for r in resultados if r.get("tipo") == tipo])
        if linha:
            print(linha)
    tecnico = []
    for r in resultados:
        if "numero" not in r:
            tecnico.append("%s: %s" % (r["tipo"], r.get("motivo")))
            continue
        extra = [] if r.get("ok") else [r.get("estado") or "?"]
        if r.get("sonda_curta") and r.get("estado") == "indeterminado":
            extra.append("sonda curta")
        if r.get("resumos"):
            extra.append("resumo " + r["resumos"])
        if r.get("notas"):
            extra.append("%d de %d notas lidas" % (len(r.get("itens") or []), r["notas"]))
        if r.get("itens_superados"):
            extra.append("%d superados" % len(r["itens_superados"]))
        if (r.get("tentativas") or 0) > 1:
            extra.append("%d tentativas, 1a=%s" % (r["tentativas"], r.get("http_1a_tentativa")))
        if r.get("cache"):
            extra.append("cache")
        if r.get("revisita"):
            extra.append("revisita")
        for rid, cod in (r.get("temas_consultados") or {}).items():
            extra.append("temas de %s=%s" % (rid, cod))
        tecnico.append("%s=%s%s" % (r["id"], r.get("http"), ("(%s)" % ", ".join(extra)) if extra else ""))
    print("TECNICO informativos: " + (" · ".join(tecnico) or "nenhum pedido"))


def main():
    pedidos = [a.split(":", 1) for a in sys.argv[1:] if ":" in a]
    if pedidos:
        resultados = []
        c = Coleta()
        for tipo, n in pedidos:
            resultados.append(c.pedir(tipo, int(n), "nova", tentativas=MAX_TENTATIVAS))
    else:
        resultados = coletar(historico())
    imprimir(resultados)
    st = {FONTE_ID: status_fonte(resultados)}
    if not pedidos:
        gravar_fontes_status(st)
    # mesmo formato do coleta_web/versiculo: {id: status}, pronto para o source_status do execucao.json
    print("SOURCE_STATUS " + json.dumps({k: v["status"] for k, v in st.items()}, ensure_ascii=False))
    os.makedirs(os.path.dirname(tmp("informativos.json")) or ".", exist_ok=True)
    with open(tmp("informativos.json"), "w", encoding="utf-8") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
