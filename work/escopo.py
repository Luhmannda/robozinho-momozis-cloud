#!/usr/bin/env python3
# =====================================================================
# escopo.py — escopo regional dos concursos acompanhados (decisão do dono,
# 20/11/2026):
#   - Quadro de apoio (analista/técnico de TJ, TRF, TRT, MP, Defensoria,
#     Procuradoria): só órgãos com lotação no Sul e no Sudeste, incluindo
#     Minas Gerais (SP, RJ, MG, ES, PR, SC, RS), ou nacionais com vagas nessas
#     UFs (MPU, DPU, AGU...).
#   - Carreiras finais (magistratura, MP, defensoria, procuradorias, AGU, PFN,
#     DPU, MPF): todo o território nacional.
# Funções puras, sem rede: usadas por bancas.py, inicio.py e migracoes.py.
# =====================================================================

import re
import unicodedata

BLOCO_APOIO = "Quadro de apoio"
UFS_APOIO = ("SP", "RJ", "MG", "ES", "PR", "SC", "RS")
TEXTO_ESCOPO_APOIO = ("Quadro de apoio: só órgãos com lotação em SP, RJ, MG, ES, PR, SC ou RS "
                      "(ou nacionais com vagas nelas, como MPU e DPU); carreiras finais: todo o país")

UFS = ("AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA",
       "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO")

# Regiões da Justiça do Trabalho (TRT n -> UFs da sede/jurisdição)
TRT = {1: {"RJ"}, 2: {"SP"}, 3: {"MG"}, 4: {"RS"}, 5: {"BA"}, 6: {"PE"}, 7: {"CE"},
       8: {"PA", "AP"}, 9: {"PR"}, 10: {"DF", "TO"}, 11: {"AM", "RR"}, 12: {"SC"},
       13: {"PB"}, 14: {"RO", "AC"}, 15: {"SP"}, 16: {"MA"}, 17: {"ES"}, 18: {"GO"},
       19: {"AL"}, 20: {"SE"}, 21: {"RN"}, 22: {"PI"}, 23: {"MT"}, 24: {"MS"}}
# Regiões da Justiça Federal (desde a criação do TRF6, MG saiu do TRF1)
TRF = {1: {"DF", "GO", "TO", "MT", "BA", "PI", "MA", "PA", "AM", "AC", "RR", "RO", "AP"},
       2: {"RJ", "ES"}, 3: {"SP", "MS"}, 4: {"RS", "PR", "SC"},
       5: {"PE", "AL", "CE", "PB", "RN", "SE"}, 6: {"MG"}}

NOMES_UF = {
    "acre": "AC", "alagoas": "AL", "amapa": "AP", "amazonas": "AM", "bahia": "BA",
    "ceara": "CE", "distrito federal": "DF", "espirito santo": "ES", "goias": "GO",
    "maranhao": "MA", "mato grosso do sul": "MS", "mato grosso": "MT", "minas gerais": "MG",
    "para": "PA", "paraiba": "PB", "parana": "PR", "pernambuco": "PE", "piaui": "PI",
    "rio de janeiro": "RJ", "rio grande do norte": "RN", "rio grande do sul": "RS",
    "rondonia": "RO", "roraima": "RR", "santa catarina": "SC", "sao paulo": "SP",
    "sergipe": "SE", "tocantins": "TO",
}

# Órgãos nacionais: vagas em todo o país (entram no escopo do apoio)
NACIONAIS = re.compile(r"\b(MPU|DPU|AGU|PFN|MPF|MPT|MPM|STF|STJ|TST|TSE|STM|CNJ|CNMP|CJF|"
                       r"ENFAM|ENAM|JUSTI[CÇ]A FEDERAL)\b")
SIGLA_UF = re.compile(r"\b(TJ|MP|DPE|DP|PGE|TCE|TCM|TRE|TRT|ALE|SEFAZ|PC|PM)[\s\-/]?([A-Z]{2})\b")
TJDFT = re.compile(r"\b(TJDFT|MPDFT|DPDF|TJDF|PGDF)\b")
TRT_RE = re.compile(r"\bTRT[\s\-]?(\d{1,2})(?!\d)|\bTRIBUNAL REGIONAL DO TRABALHO DA (\d{1,2})")
TRF_RE = re.compile(r"\bTRF[\s\-]?(\d)(?!\d)|\bTRIBUNAL REGIONAL FEDERAL DA (\d)")
UF_SOLTA = re.compile(r"(?:\(|/|\s-\s)([A-Z]{2})\b")


def _sem_acento(s):
    return "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))


def ufs_de_texto(texto):
    """UFs citadas num texto de concurso ('TRT8 — ...', 'DPE-PB', 'PGM Suzano/SP',
    'TRT4 (RS)'). 'BR' = órgão nacional. Conjunto vazio = não identificado."""
    if not texto:
        return set()
    t = _sem_acento(str(texto)).upper()
    ufs = set()
    if TJDFT.search(t):
        ufs.add("DF")
    for m in TRT_RE.finditer(t):
        n = int(m.group(1) or m.group(2))
        ufs |= TRT.get(n, set())
    for m in TRF_RE.finditer(t):
        n = int(m.group(1) or m.group(2))
        ufs |= TRF.get(n, set())
    for m in SIGLA_UF.finditer(t):
        if m.group(2) in UFS:
            ufs.add(m.group(2))
    for m in UF_SOLTA.finditer(t):
        if m.group(1) in UFS:
            ufs.add(m.group(1))
    # "Pará" sem acento colide com a preposição "para": só com o acento
    if re.search(r"\bPar[áÁ]\b", str(texto)):
        ufs.add("PA")
    baixo = _sem_acento(str(texto)).lower()
    for nome in sorted(NOMES_UF, key=len, reverse=True):
        if nome == "para":
            continue
        if re.search(r"\b%s\b" % re.escape(nome), baixo):
            ufs.add(NOMES_UF[nome])
            baixo = re.sub(r"\b%s\b" % re.escape(nome), " ", baixo)
    if NACIONAIS.search(t):
        ufs.add("BR")
    return ufs


SLUG_UF = re.compile(r"^(tj|mp|dpe|dp|pge|tce|tre|ale)([a-z]{2})(?=[a-z]*\d|[a-z]*$)")
# trt/trf + digitos (regiao e, colado, o ano) + letras (uf, cargo) + digitos (ano)
SLUG_TR = re.compile(r"^(trt|trf)(\d+)([a-z]*)(\d*)")


def regiao_ano(tipo, dig, ano=""):
    """(regiao, ano) dos digitos de um slug de TRT/TRF — a MESMA regra do bancas.partes_slug (rev1 C7: o SLUG_TR
    guloso lia trt225 como TRT22, PI). Com o ano depois de letras (trt2sp25, trf5juiz26), `dig` e so a regiao.
    Senao: TRF tem regiao de 1 digito (trf225 -> 2/25, trf62025 -> 6/2025); TRT: ate 2 digitos = regiao (trt24),
    3 = 1 + ano de 2 (trt225 -> 2/25), 4 = 2 + 2 (trt1526 -> 15/26; trt2025 -> 20/25: "025" nao e ano), mais = o
    resto + ano de 4 (trt22025 -> 2/2025)."""
    if ano:
        return dig, ano
    corte = 1 if tipo == "trf" else (len(dig) if len(dig) <= 2 else 1 if len(dig) == 3
                                     else 2 if len(dig) == 4 else len(dig) - 4)
    return dig[:corte], dig[corte:]


def ufs_de_slug(slug):
    """UFs de um slug de banca ('tjpb26', 'trt2sp25', 'dperj2026', 'trf5juiz26', 'trt225')."""
    s = (slug or "").lower().strip("/").split("/")[-1]
    m = SLUG_TR.match(s)
    if m:
        n = int(regiao_ano(m.group(1), m.group(2), m.group(4))[0])
        return set((TRT if m.group(1) == "trt" else TRF).get(n, set()))
    if s.startswith(("tjdft", "mpdft", "dpdf")):
        return {"DF"}
    m = SLUG_UF.match(s)
    if m and m.group(2).upper() in UFS:
        return {m.group(2).upper()}
    if re.match(r"^(mpu|dpu|agu|pfn|mpf|enam|exames)", s):
        return {"BR"}
    return set()


def apoio_no_escopo(*textos, slug=None):
    """'dentro' | 'fora' | 'indefinido' para um concurso do quadro de apoio.
    Nacional ('BR') conta como dentro; sem UF identificada = 'indefinido'
    (nunca descartar por falta de dado)."""
    ufs = set()
    for t in textos:
        ufs |= ufs_de_texto(t)
    if slug:
        ufs |= ufs_de_slug(slug)
    if not ufs:
        return "indefinido"
    if "BR" in ufs or ufs & set(UFS_APOIO):
        return "dentro"
    return "fora"


def registro_no_escopo(reg):
    """Registro do ledger: carreira final sempre no escopo; apoio pelo órgão
    (id + linha). Devolve 'dentro' | 'fora' | 'indefinido'."""
    if (reg or {}).get("bloco") != BLOCO_APOIO:
        return "dentro"
    linha = reg.get("linha") or ""
    orgao = linha.split("—")[0] if "—" in linha else linha[:80]
    ident = (reg.get("id") or "").replace("_", " ").upper()
    return apoio_no_escopo(orgao, ident, slug=reg.get("banca_slug"))
