#!/usr/bin/env python3
# =====================================================================
# selos.py — regras deterministicas do registro de concursos, num lugar so,
# usadas pelo helper (work/Update-Historico.py: persistir/validar), pelo
# inicio.py (avisar o orquestrador) e pelo montador (renderizar).
#
# Por que: o selo de prazo era texto gravado que envelhecia. O TJAP ficou
# "ENCERRA HOJE" de 13/11 a 16/11; o TJPB precisaria virar ENCERRA HOJE em
# 18/11 e INSCRICOES ENCERRADAS em 19/11 "se alguem lembrasse". E a regra
# "fonte secundaria nunca promove selo" so existia no texto da ROTINA.
#
# API principal:
#   selo_por_data(reg, hoje, banca_lida_hoje=False, ultima_retificacao=None,
#                 inicio_inscricoes=None, prazos_podados=None) -> (selo, motivo|None)
#     - selo != reg["selo"]  -> mudanca; motivo descreve ("A → B: ...") e vira AVISO;
#     - selo == reg["selo"] e motivo -> ALERTA (motivo comeca por "confirmar");
#     - motivo None          -> nada a fazer.
#   Regras (relatorio, "Corrigir ja" item 8; achados A4/D2/E1/F6/G11 com os ajustes):
#     - so age se o selo atual for da FAMILIA_DATA e so com prazo confirmado:true;
#     - precedencia explicita (PRECEDENCIA): ENCERRA HOJE > ENCERRA EM BREVE >
#       PROVA EM BREVE > INSCRICOES ABERTAS > INSCRICOES ENCERRADAS;
#     - INSCRICOES ABERTAS so com data de inicio conhecida <= hoje;
#     - INSCRICOES ENCERRADAS automatica so com a banca lida hoje E o fim das
#       inscricoes posterior a ultima retificacao (inscricao e prorrogada com
#       frequencia: TJAP). Fora disso, o fim ja passou e o selo dizia ENCERRA
#       HOJE / ENCERRA EM BREVE / INSCRICOES ABERTAS: o selo cai para PENDENCIA
#       DE VERIFICACAO (SELO_SEM_CONFIRMACAO), com o motivo "prorrogação não
#       confirmada" dizendo o que fazer. Antes o selo ficava e o leitor lia
#       "ENCERRA HOJE" dias depois do prazo (DPE-SP, TJAP de 13 a 16/11);
#     - quem chama nunca aplica sobre selo ESCRITO hoje nos ledger_updates
#       (selo_escrito: so conta o que difere do selo do registro antes do
#       update; copiar o selo inalterado nao e decisao) e deriva ANTES de podar
#       prazos vencidos (prazos_podados = os que o update de hoje retirou).
#   classe_prazo: "inscricao definitiva" (2a fase da magistratura) e eventos
#     acessorios da prova (resultado, gabarito, recurso, locais, convocacao...)
#     sao "outro" — nao abrem inscricao nem viram PROVA EM BREVE. O `tipo` escrito
#     prevalece sobre o evento; tipo_contradiz_evento acusa o tipo que tira da
#     classe um evento que, pelo texto (classe_pelo_evento), e o fim/inicio das
#     inscricoes (helper e montador avisam; nada e corrigido sozinho).
#   fonte_oficial: so o que passa em DOMINIOS_OFICIAIS; o dominio_oficial do
#     registro nao vale como prova (era contornavel no mesmo update: E9).
# =====================================================================

import re
from datetime import date, timedelta
from urllib.parse import urlparse

FAMILIA_DATA = ("ENCERRA HOJE", "ENCERRA EM BREVE", "PROVA EM BREVE", "INSCRIÇÕES ABERTAS",
                "INSCRIÇÕES ENCERRADAS")
PRECEDENCIA = FAMILIA_DATA          # ordem de prioridade quando mais de um selo se aplica
# fim das inscricoes vencido sem confirmacao (encerramento ou prorrogacao): selo neutro, fora da familia
SELO_SEM_CONFIRMACAO = "PENDÊNCIA DE VERIFICAÇÃO"
EM_BREVE_DIAS = 7
PROVA_BREVE_DIAS = 14
# selos que um concurso pode ter (lista propria; a lista geral de SELOS do helper vale para noticias)
SELOS_CONCURSO = ("INSCRIÇÕES ABERTAS", "INSCRIÇÕES ENCERRADAS", "ENCERRA EM BREVE", "ENCERRA HOJE",
                  "EDITAL PUBLICADO", "EM ANDAMENTO", "EM PLANEJAMENTO", "PROVA EM BREVE",
                  "PROVA REALIZADA", "PENDÊNCIA", "PENDÊNCIA DE VERIFICAÇÃO")
# selos que so a fonte oficial sustenta (ROTINA: "INSCRICOES ABERTAS/EDITAL PUBLICADO so com fonte oficial")
SELOS_EXIGEM_OFICIAL = ("INSCRIÇÕES ABERTAS", "EDITAL PUBLICADO", "ENCERRA EM BREVE", "ENCERRA HOJE")
TIPOS_PRAZO = ("inscricoes_inicio", "inscricoes_fim", "prova", "outro")

# Dominios oficiais: orgaos publicos (.jus/.gov/.leg/.mp/.def .br) e as bancas organizadoras.
# Acrescente aqui uma banca nova (o mesmo regex vale para o helper, o inicio e o montador).
BANCAS_OFICIAIS = (
    "conhecimento.fgv.br", "fgv.br", "cebraspe.org.br", "concursosfcc.com.br", "fcc.org.br",
    "vunesp.com.br", "ibfc.org.br", "institutoaocp.org.br", "fundatec.org.br", "consulplan.net",
    "institutoconsulplan.org.br", "ibade.org.br", "idecan.org.br", "quadrix.org.br",
    "cesgranrio.org.br", "selecon.org.br", "objetivas.com.br", "fepese.org.br", "iades.com.br",
    "cetapnet.com.br", "institutoaccess.org.br", "avancasp.org.br", "fumarc.com.br",
    "institutomais.org.br", "legalle.com.br", "ibam-concursos.org.br", "rbo.org.br",
    "igeduc.org.br", "nc.ufpr.br", "comperve.ufrn.br", "copeve.ufal.br", "fundep.ufmg.br",
    "cebraspe.org", "fundacaolasalle.org.br", "institutoibest.org.br", "omniconcursos.com.br",
)
DOMINIOS_OFICIAIS = re.compile(
    r"(?:^|\.)(?:[a-z0-9-]+\.)*(?:jus|gov|leg|mp|def)\.br$|(?:^|\.)(?:%s)$"
    % "|".join(re.escape(b) for b in BANCAS_OFICIAIS), re.I)
# sites que nunca sao "dominio oficial", mesmo se o registro disser que sao
SECUNDARIOS = re.compile(r"estrategia|qconcursos|pciconcursos|jcconcursos|ceisc|grancursos|folha|"
                         r"novaconcursos|direcaoconcursos|concursosnobrasil|acheconcursos|"
                         r"editaljuridico|conjur|migalhas|jota|g1\.globo|wikipedia|blog", re.I)
TERMOS_RELATIVOS = re.compile(r"\b(hoje|amanh[ãa]|ontem)\b", re.I)

_INSCR = r"inscri[çc][ãaõo]\w*"
# fim das inscricoes pelo texto do evento (volta 2: "data limite para inscrições", "prazo de inscrição termina",
# "inscrições (prorrogadas)", "prorrogação das inscrições" e "inscrições abertas até" eram "outro" e desligavam
# o selo por data do registro)
RE_FIM = re.compile(r"(fim|t[ée]rmino|encerramento|[úu]ltimo dia|prazo final|encerra|limite|prorroga)\w*.{0,25}inscri|"
                    + _INSCR + r"(?:\s+(?:abertas?|online|prorrogad[ao]s?))?\s+at[ée]\b|"
                    + _INSCR + r"\s*\(\s*(?:fim|prorrogad|encerra)|" + _INSCR + r"\s+prorrogad|"
                    + _INSCR + r".{0,20}?\b(?:termina|encerra|acaba)", re.I)
# inicio das inscricoes (volta 2: "inscrições a partir de DD/MM", "inscrições abrem em DD/MM")
RE_INICIO = re.compile(r"(in[íi]cio|abertura)\w*.{0,25}inscri|" + _INSCR + r"(?:\s+abertas?)?\s+a\s+partir\s+d|"
                       + _INSCR + r"\s+(?:abrem|come[çc]am|iniciam)\b", re.I)
RE_PROVA = re.compile(r"\bprova", re.I)
RE_PAGAMENTO = re.compile(r"pagamento|boleto|taxa|isen", re.I)
# inscricao DEFINITIVA (2a fase da magistratura: TJRS, TJSC, TJAP, TRF5 em 2027) nao reabre o concurso
RE_DEFINITIVA = re.compile(r"definitiv", re.I)
# evento acessorio da prova (depois dela ou sobre ela): nao e a prova
RE_NAO_PROVA = re.compile(r"resultado|gabarito|recurso|\bloca(?:l|is)\b|convoca|\bvista\b|homolog|edital\s+de|"
                          r"cart[ãa]o|divulga|publica[çc]", re.I)


# ------------------------------------------------------------------ fontes
def host(fonte):
    s = (fonte or "").strip()
    if not s:
        return ""
    if not re.match(r"[a-z]+://", s, re.I):
        m = re.search(r"https?://\S+", s)
        if not m:
            m2 = re.match(r"([a-z0-9-]+(?:\.[a-z0-9-]+)+)(?:/|$)", s, re.I)
            return m2.group(1).lower() if m2 else ""
        s = m.group(0)
    return (urlparse(s).hostname or "").lower()


def dominio_oficial(h):
    """True se o host e de orgao publico ou de banca organizadora conhecida."""
    return bool(h) and bool(DOMINIOS_OFICIAIS.search(h.lower().rstrip(".")))


def fonte_oficial(fonte, dominio_registro=None):
    """A `fonte` do registro e oficial? So pela regex compartilhada (DOMINIOS_OFICIAIS).
    `dominio_registro` fica na assinatura por compatibilidade e NAO vale como prova: o
    dominio_oficial podia ser escrito no mesmo update que promove (ex.: www.dgabc.com.br) e
    a lista SECUNDARIOS nunca cobre todos os sites. Banca nova entra em BANCAS_OFICIAIS."""
    h = host(fonte)
    return bool(h) and dominio_oficial(h)


# ------------------------------------------------------------------ prazos
def _data(v):
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v or "")[:10])
    except ValueError:
        return None


def classe_prazo(pz):
    """inscricoes_inicio | inscricoes_fim | prova | outro. Usa `tipo` quando existir; senao, o `evento`."""
    t = pz.get("tipo")
    if t in TIPOS_PRAZO:
        return t
    return classe_pelo_evento(pz.get("evento"))


def tipo_contradiz_evento(pz):
    """`tipo` escrito que tira um prazo de inscricao da sua classe: o `evento`, pelo texto, e o fim (ou o inicio)
    das inscricoes e o `tipo` diz outra coisa (ex.: 'outro' em "fim das inscrições, 16h (prorrogado)", pela
    leitura "'outro' para tudo que nao e a prova"). O tipo prevalece sobre o evento: o selo por data, o
    rebaixamento e o DIVERGE ignoram o prazo. Devolve a classe do evento (inscricoes_fim|inscricoes_inicio) ou
    None. Nao corrige nada: o tipo existe para o caso em que o regex do evento erra (isencao, outra etapa)."""
    if not isinstance(pz, dict) or pz.get("tipo") not in TIPOS_PRAZO:
        return None
    c = classe_pelo_evento(pz.get("evento"))
    return c if c in ("inscricoes_fim", "inscricoes_inicio") and c != pz["tipo"] else None


def classe_pelo_evento(ev):
    """Classe do prazo so pelo texto do `evento` (sem o `tipo`)."""
    ev = ev if isinstance(ev, str) else ""
    if RE_DEFINITIVA.search(ev):
        return "outro"          # inscricao definitiva: etapa de quem ja passou, nao reabre inscricao
    if RE_INICIO.search(ev):
        return "inscricoes_inicio"
    if RE_FIM.search(ev) and not RE_PAGAMENTO.search(re.split(r"inscri", ev, maxsplit=1, flags=re.I)[0]):
        return "inscricoes_fim"
    m = RE_PROVA.search(ev)
    # so o que vem ANTES de "prova" decide: "resultado preliminar da prova" e outro; "prova objetiva
    # (data divulgada pela banca)" continua prova
    if m and not RE_NAO_PROVA.search(ev[:m.start()]):
        return "prova"
    return "outro"


def _prazos(reg, extras=None):
    out = [p for p in (reg.get("prazos") or []) if isinstance(p, dict)]
    for p in extras or []:
        if isinstance(p, dict) and p not in out:
            out.append(p)
    return out


def fim_inscricoes(reg, so_confirmado=True, extras=None):
    """(data, prazo) do fim das inscricoes: o mais tardio dos prazos dessa classe (prorrogacao
    soma um prazo novo); None se nao houver."""
    cands = [(_data(p.get("data")), p) for p in _prazos(reg, extras)
             if classe_prazo(p) == "inscricoes_fim" and (p.get("confirmado") or not so_confirmado)]
    cands = [x for x in cands if x[0]]
    return max(cands, key=lambda x: x[0]) if cands else (None, None)


DM = r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?"
RE_LINHA_INI = re.compile(r"inscri[çc][õo]es[^;]{0,40}?\bd[eao]s?\s+(?:\d{1,2}h\d{0,2}\s+de\s+)?" + DM, re.I)
RE_LINHA_FIM = re.compile(r"inscri[çc][õo]es[^;]{0,80}?(?:\bat[ée]|\ba|encerrad[ao]s?\s+em|terminaram\s+em|"
                          r"encerram\s+em|terminam\s+em)\s+(?:[àa]s\s+)?(?:\d{1,2}h\d{0,2}\s+(?:de|do dia)\s+)?"
                          + DM, re.I)


def _dm(m, ref):
    """DD/MM[/AAAA] -> date, com o ano mais proximo de `ref` quando falta."""
    d, mth, y = int(m.group(1)), int(m.group(2)), m.group(3)
    try:
        if y:
            y = int(y)
            return date(y + 2000 if y < 100 else y, mth, d)
        cands = [date(ref.year + k, mth, d) for k in (-1, 0, 1)]
    except ValueError:
        return None
    return min(cands, key=lambda x: abs((x - ref).days))


def inicio_inscricoes(reg, hoje):
    """Data de inicio das inscricoes: prazo confirmado da classe, senao o "inscricoes das ... de DD/MM"
    da linha (texto copiado da fonte oficial quando o selo e da familia de datas)."""
    cands = [_data(p.get("data")) for p in _prazos(reg)
             if classe_prazo(p) == "inscricoes_inicio" and p.get("confirmado")]
    cands = [c for c in cands if c]
    if cands:
        return min(cands)
    m = RE_LINHA_INI.search(reg.get("linha") or "")
    return _dm(m, hoje) if m else None


def fim_inscricoes_registro(reg, hoje):
    """(data, texto) do fim das inscricoes segundo o registro, para comparar com o edital:
    prazos (qualquer confirmacao) e, sem prazo, a `linha`. (None, "sem fim das inscrições") se nada."""
    d, p = fim_inscricoes(reg, so_confirmado=False)
    if d:
        return d, "prazo %s %s%s" % (d.strftime("%d/%m/%Y"), p.get("evento") or "",
                                     "" if p.get("confirmado") else " (a confirmar)")
    m = RE_LINHA_FIM.search(reg.get("linha") or "")
    if m:
        return _dm(m, hoje), "linha: " + m.group(0)
    return None, "sem fim das inscrições"


def proxima_prova(reg, hoje, extras=None):
    cands = [_data(p.get("data")) for p in _prazos(reg, extras)
             if classe_prazo(p) == "prova" and p.get("confirmado")]
    futuras = [c for c in cands if c and c >= hoje]
    passadas = [c for c in cands if c and c < hoje]
    return (min(futuras) if futuras else None), (max(passadas) if passadas else None)


# ------------------------------------------------------------------ selo por data
def selo_por_data(reg, hoje, banca_lida_hoje=False, ultima_retificacao=None, inicio_inscricoes_banca=None,
                  prazos_podados=None):
    """(selo, motivo|None). Ver o cabecalho do modulo. `hoje` e date (ou AAAA-MM-DD)."""
    hoje = _data(hoje)
    atual = reg.get("selo")
    if atual not in FAMILIA_DATA or hoje is None:
        return atual, None
    fim, pz_fim = fim_inscricoes(reg, extras=prazos_podados)
    prova, prova_passada = proxima_prova(reg, hoje, extras=prazos_podados)
    ini = _data(inicio_inscricoes_banca) or inicio_inscricoes(reg, hoje)
    ret = _data(ultima_retificacao)
    cands, porque = [], {}
    if fim:
        d = (fim - hoje).days
        if d == 0:
            cands.append("ENCERRA HOJE")
            porque["ENCERRA HOJE"] = "fim das inscrições hoje (%s)" % fim.strftime("%d/%m")
        elif 1 <= d <= EM_BREVE_DIAS:
            cands.append("ENCERRA EM BREVE")
            porque["ENCERRA EM BREVE"] = "fim das inscrições em %d dia%s (%s)" % (d, "s" if d > 1 else "",
                                                                                  fim.strftime("%d/%m"))
        elif d > EM_BREVE_DIAS:
            if ini and ini <= hoje:
                cands.append("INSCRIÇÕES ABERTAS")
                porque["INSCRIÇÕES ABERTAS"] = "inscrições de %s a %s" % (ini.strftime("%d/%m"),
                                                                           fim.strftime("%d/%m"))
        else:
            seguro = banca_lida_hoje and (ret is None or fim > ret)
            if atual == "INSCRIÇÕES ENCERRADAS" or seguro:
                cands.append("INSCRIÇÕES ENCERRADAS")
                porque["INSCRIÇÕES ENCERRADAS"] = "fim das inscrições em %s%s" % (
                    fim.strftime("%d/%m"), ", banca oficial lida hoje" + (
                        " (última retificação %s)" % ret.strftime("%d/%m") if ret else "") if seguro else "")
            elif atual in ("ENCERRA HOJE", "ENCERRA EM BREVE", "INSCRIÇÕES ABERTAS"):
                # o selo dizia "abertas/encerra" e o prazo passou sem confirmacao: nao fica mais (o leitor lia
                # ENCERRA HOJE dias depois); tambem nao vira ENCERRADAS sozinho (a prorrogacao e frequente)
                if not banca_lida_hoje:
                    razao = "a banca oficial não foi lida hoje"
                else:
                    razao = "a banca publicou retificação em %s, no dia do prazo ou depois" % ret.strftime("%d/%m")
                cands.append(SELO_SEM_CONFIRMACAO)
                porque[SELO_SEM_CONFIRMACAO] = (
                    "o fim das inscrições (%s) já passou e %s: prorrogação não confirmada — confirme na fonte "
                    "oficial e escreva em ledger_updates.concursos: encerradas → selo INSCRIÇÕES ENCERRADAS; "
                    "prorrogadas → prazos com a data nova (confirmado, fonte oficial) e o selo que a nova data dá "
                    "(ENCERRA HOJE / ENCERRA EM BREVE / INSCRIÇÕES ABERTAS)"
                    % (fim.strftime("%d/%m"), razao))
    if prova is not None and (prova - hoje).days <= PROVA_BREVE_DIAS:
        cands.append("PROVA EM BREVE")
        porque["PROVA EM BREVE"] = "prova em %s" % prova.strftime("%d/%m")
    if not cands:
        if atual == "PROVA EM BREVE" and prova_passada and prova is None:
            return atual, ("confirmar: a prova de %s já passou — atualize o selo (PROVA REALIZADA?)"
                           % prova_passada.strftime("%d/%m"))
        return atual, None
    novo = min(cands, key=(PRECEDENCIA + (SELO_SEM_CONFIRMACAO,)).index)
    if novo == atual:
        return atual, None
    return novo, "%s → %s: %s" % (atual, novo, porque[novo])


def selo_escrito(u, antes):
    """O orquestrador DECIDIU o selo hoje? `u` = ledger_updates.concursos[id]; `antes` = o registro antes
    do update (None = concurso novo). Copiar o selo inalterado (a maioria dos updates de concurso traz o
    selo do registro) nao e decisao: o selo por data vale. Mesma regra no helper e no montador."""
    if not isinstance(u, dict) or "selo" not in u or u.get("remover"):
        return False
    return antes is None or u["selo"] != (antes or {}).get("selo")


def relativos(texto):
    """Termos relativos ('hoje', 'amanhã', 'ontem') — proibidos na `linha`: ela envelhece."""
    return sorted({m.group(1).lower() for m in TERMOS_RELATIVOS.finditer(texto or "")})


# ------------------------------------------------------------------ ciclo de vida
def candidato_remocao(reg, hoje, dias=30):
    """Todos os prazos confirmados venceram ha mais de `dias` e nao ha etapa futura (prazo de qualquer
    confirmacao com data >= hoje). Sem prazo confirmado, nunca e candidato."""
    hoje = _data(hoje)
    datas = [(_data(p.get("data")), bool(p.get("confirmado"))) for p in _prazos(reg)]
    datas = [(d, c) for d, c in datas if d]
    conf = [d for d, c in datas if c]
    if not conf or any(d >= hoje for d, _ in datas):
        return False
    return all((hoje - d).days > dias for d in conf)


CAMPOS_MUDANCA = ("linha", "selo", "prazos")


def mudou(antes, depois):
    """O que o leitor ve mudou? (linha, selo ou prazos)."""
    return any((antes or {}).get(k) != (depois or {}).get(k) for k in CAMPOS_MUDANCA)


def ultima_mudanca_por_id(execucoes):
    """{id: AAAA-MM-DD} da ultima execucao cujos ledger_updates tocaram linha/selo/prazos do concurso."""
    out = {}
    for e in sorted(execucoes or [], key=lambda e: (e.get("date") or "", e.get("execution_id") or "")):
        for ident, campos in (((e.get("ledger_updates") or {}).get("concursos")) or {}).items():
            if isinstance(campos, dict) and not campos.get("remover") and any(k in campos for k in CAMPOS_MUDANCA):
                if e.get("date"):
                    out[ident] = e["date"]
    return out


def garantir_mudou_em(concursos, execucoes):
    """Preenche `mudou_em` onde falta (migracao idempotente): data da ultima mudanca no historico;
    sem informacao, o verificado_em. Devolve quantos foram preenchidos."""
    ult, n = None, 0
    for c in concursos or []:
        if c.get("mudou_em"):
            continue
        if ult is None:          # `execucoes` pode ser funcao (carrega o historico so se precisar)
            ult = ultima_mudanca_por_id(execucoes() if callable(execucoes) else execucoes)
        v = ult.get(c.get("id")) or c.get("verificado_em")
        if v:
            c["mudou_em"] = v
            n += 1
    return n


if __name__ == "__main__":
    import json
    import sys
    hoje = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today()
    led = json.load(open(__file__.rsplit("/", 1)[0] + "/robozinho-aprendizado.json", encoding="utf-8"))
    for c in led.get("concursos") or []:
        s, m = selo_por_data(c, hoje)
        if m:
            print("%s: %s" % (c["id"], m))
