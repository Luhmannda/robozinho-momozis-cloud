#!/usr/bin/env python3
# =====================================================================
# medir_uso.py — mede o uso REAL de tokens da sessao atual, sem custo de
# tokens, a partir das transcricoes locais do Claude Code
# (~/.claude/projects/<projeto>/<sessao>.jsonl e .../subagents/*.jsonl).
#
# Por chamada ao modelo: contexto = entrada + cache lido + cache gravado.
# "contexto_total" soma todas as chamadas (e o que de fato e processado);
# "tokens" e o contexto da ultima chamada (mesma semantica do
# subagent_tokens que o Agent devolve, para comparar com o historico).
# Tambem registra o modelo efetivamente servido (ex.: claude-haiku-5-5).
#
# Tokens por tipo (A3/K5): "contexto_total" e quase so LEITURA de cache, que
# e o tipo mais barato; o custo do orquestrador esta na GRAVACAO de cache e na
# SAIDA. Por isso cada uso traz tambem entrada, cache_lido, cache_gravado
# (com cache_gravado_1h quando a transcricao separa) e saida, e duas medidas
# de custo:
#   - "custo_relativo": o custo em unidades do preco do token de ENTRADA do
#     proprio modelo, com os multiplicadores DO MODELO tirados da tabela de
#     precos abaixo (verified[19]: os antigos 0,1/1,25 fixos nao valem para
#     estes modelos):
#       entrada x 1 + cache_lido x L + gravacao_5min x 1,25 + gravacao_1h x 2 + saida x 5
#     L = 0,025 no Fable/Mythos 5.1 e 5.2, 0,05 no Opus 5.5 e no Sonnet 5.5,
#     0,1 nos demais. Modelo fora da tabela: L = 0,1 (pesos antigos). Serve
#     para comparar o COMPORTAMENTO (turnos, gravacao, saida) num mesmo modelo;
#     nao enxerga troca de modelo.
#   - "custo_usd": o custo em dolar pelo preco de LISTA da API (tabela abaixo),
#     chamada a chamada (o Haiku 5.5 acima de 100 mil tokens de prompt cobra 5x;
#     speed "fast" cobra 2x). Equivalente de API: nao e a cobranca da
#     assinatura do dono, mas e a unidade comum que soma orquestrador e
#     coletores e enxerga troca de modelo. Modelo fora da tabela: None (nunca
#     chutar) e o helper avisa.
# Buscas: "websearch" conta os tool_use WebSearch de cada agente (critic_verified[4]):
# cada busca e cobrada a parte (US$ 10 por mil) e o resumo que volta e escrito
# por outra chamada de modelo que NAO aparece na transcricao. "websearch_usd_est"
# = n x (BUSCA_USD + RESUMO_BUSCA_USD_EST), rotulado como estimativa.
# Esforco: "esforco" = o `effort` mais frequente dos registros do assistente
# (xhigh, high...), quando a transcricao o traz (verified[21]).
#
# A ultima chamada do orquestrador (a notificacao/resposta final, depois do
# finalizar.sh) ainda nao existe quando o helper mede: entra como
# "fechamento_estimado" (leitura = contexto da ultima chamada medida,
# gravacao ~2 mil tokens da saida do finalizar, saida ~700) e e somada ao
# custo_relativo.
#
# Coletor relancado (mesmo nome): os usos sao SOMADOS ("relancamentos": n);
# antes valia so o ultimo, o que subcontava.
#
# Mensagem sintetica (model "<synthetic>" ou uso todo zero: erro de API ou aviso
# que o proprio Claude Code escreve na transcricao) nao e chamada ao modelo e nao
# conta: nem anula o custo_usd nem gera o AVISO de preco.
#
# Usado por Update-Historico.py --medir-uso (preenche `coletores` e
# `orquestrador` da execucao). USO avulso, para conferencia:
#   python3 work/medir_uso.py [--desde 2026-10-14T07:19:53-03:00]
# =====================================================================

import argparse
import glob
import json
import os
from datetime import datetime, timezone

RAIZ = os.path.expanduser("~/.claude/projects")
COLETORES = (("coletor-gmail", "gmail"), ("coletor-jota", "jota"),
             ("coletor-concursos", "concursos"))
# Pesos antigos (modelo fora da tabela; tambem os da serie anterior a 21/11/2026).
PESOS = {"entrada": 1.0, "cache_lido": 0.1, "cache_gravado": 1.25, "saida": 5.0}
FECHAMENTO = {"cache_gravado": 2000, "saida": 700}   # estimativa da chamada final do orquestrador

# Precos de LISTA da API da Anthropic, em US$ por milhao de tokens:
#   (entrada, cache lido, gravacao de cache 5 min, gravacao de cache 1 h, saida)
# Fonte: skill claude-api do Claude Code (SKILL.md, tabela "Current Models", cache de 2026-11-03;
# shared/models.md e shared/prompt-caching.md: leitura 0,025x no Fable/Mythos 5.1 e 5.2, 0,05x no
# Opus 5.5 e no Sonnet 5.5, 0,1x nos demais; gravacao 1,25x (5 min) e 2x (1 h) da entrada), conferida
# em 2026-11-21. Haiku 5.5: a tabela da skill traz so entrada/saida (ate 100 mil tokens de prompt; acima, 5x:
# HAIKU_LONGO); o cache dele segue os multiplicadores gerais (0,1x / 1,25x / 2x). Revise quando o
# modelo mudar ou a Anthropic mudar a tabela (https://platform.claude.com/docs/en/about-claude/pricing).
PRECOS_EM = "2026-11-03"
PRECOS_USD_MTOK = {
    "claude-fable-5-2": (8.00, 0.20, 10.00, 16.00, 40.00),
    "claude-mythos-5-2": (8.00, 0.20, 10.00, 16.00, 40.00),
    "claude-fable-5-1": (10.00, 0.25, 12.50, 20.00, 50.00),
    "claude-mythos-5-1": (10.00, 0.25, 12.50, 20.00, 50.00),
    "claude-opus-5-5": (4.00, 0.20, 5.00, 8.00, 20.00),
    "claude-sonnet-5-5": (2.00, 0.10, 2.50, 4.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.01, 0.125, 0.20, 0.50),
}
HAIKU_LONGO = {"claude-haiku-5-5": (100000, 5.0)}     # prompt acima do limite: todos os precos x fator
FAST = 2.0                                            # speed "fast" (Opus 5.5 e Fable/Mythos 5.2): 2x
# Busca na web (ferramenta WebSearch): US$ 10 por mil buscas (skill claude-api, managed-agents-core.md, lista
# de custos). O resumo de cada busca e escrito por outra chamada de modelo que a transcricao nao mostra:
# RESUMO_BUSCA_USD_EST e uma ESTIMATIVA (~15 mil tokens de entrada + ~1,5 mil de saida a preco de Sonnet 5.5),
# nao conferida na fatura — recalibrar se o dono trouxer o valor cobrado.
BUSCA_USD = 0.01
RESUMO_BUSCA_USD_EST = 0.045


def base_modelo(modelo):
    """Id do modelo sem sufixo de contexto/data ('claude-fable-5-2[1m]' -> 'claude-fable-5-2')."""
    m = str(modelo or "").strip().lower()
    for sep in ("[", "@"):
        m = m.split(sep)[0]
    return m


def preco(modelo):
    return PRECOS_USD_MTOK.get(base_modelo(modelo))


def pesos(modelo):
    """(entrada, cache_lido, gravacao_5min, gravacao_1h, saida) em multiplos da entrada do modelo."""
    p = preco(modelo)
    if not p:
        return (PESOS["entrada"], PESOS["cache_lido"], PESOS["cache_gravado"], 2.0, PESOS["saida"])
    return tuple(x / p[0] for x in p)


def custo_relativo(entrada, cache_lido, cache_gravado, saida, modelo=None, cache_gravado_1h=0):
    """Custo em tokens-equivalentes de ENTRADA do modelo (ver o cabecalho). Sem modelo e sem gravacao de 1 h:
    os pesos antigos (entrada 1, leitura 0,1, gravacao 1,25, saida 5)."""
    pe, pl, p5, p1, ps = pesos(modelo)
    g1 = min(int(cache_gravado_1h or 0), int(cache_gravado or 0))
    return int(round(entrada * pe + cache_lido * pl + (cache_gravado - g1) * p5 + g1 * p1 + saida * ps))


def custo_usd(entrada, cache_lido, cache_gravado, saida, modelo, cache_gravado_1h=0, fator=1.0):
    """US$ pelo preco de lista (tabela acima); None para modelo fora da tabela."""
    p = preco(modelo)
    if not p:
        return None
    g1 = min(int(cache_gravado_1h or 0), int(cache_gravado or 0))
    return fator * (entrada * p[0] + cache_lido * p[1] + (cache_gravado - g1) * p[2] + g1 * p[3] +
                    saida * p[4]) / 1e6


def fator_chamada(modelo, contexto, speed=None):
    f = FAST if speed == "fast" else 1.0
    lim = HAIKU_LONGO.get(base_modelo(modelo))
    return f * (lim[1] if lim and contexto > lim[0] else 1.0)


def buscas_usd_est(n):
    return round(int(n or 0) * (BUSCA_USD + RESUMO_BUSCA_USD_EST), 4)


def _ts(s):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


def sintetica(m):
    """Mensagem que o proprio Claude Code escreve na transcricao (erro de API, aviso de limite...): model "<synthetic>"
    e uso todo zero. Nao e chamada ao modelo: contada, anulava o custo_usd (modelo fora da tabela) e gerava o AVISO
    de preco enganoso."""
    if m.get("model") == "<synthetic>":
        return True
    u = m.get("usage") or {}
    return not any(u.get(k) for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens",
                                      "output_tokens"))


def uso_transcricao(caminho, desde=None, ate=None):
    """Agrega o uso de uma transcricao. Linhas repetidas do mesmo
    message.id contam uma vez (saida = maior valor visto)."""
    msgs, ferramentas, tempos, primeiro_prompt, modelos, esforcos, buscas = {}, 0, [], None, {}, {}, 0
    with open(caminho, encoding="utf-8", errors="replace") as f:
        for linha in f:
            try:
                o = json.loads(linha)
            except ValueError:
                continue
            quando = _ts(o.get("timestamp"))
            if quando and ((desde and quando < desde) or (ate and quando > ate)):
                continue
            m = o.get("message") or {}
            if o.get("type") == "user" and primeiro_prompt is None:
                c = m.get("content")
                primeiro_prompt = c if isinstance(c, str) else json.dumps(c, ensure_ascii=False)[:4000]
            if o.get("type") != "assistant" or not m.get("usage") or not m.get("id"):
                continue
            if sintetica(m):
                continue
            if quando:
                tempos.append(quando)
            u = m["usage"]
            ctx = (u.get("input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0) + \
                (u.get("cache_creation_input_tokens") or 0)
            ant = msgs.get(m["id"])
            pensou = (u.get("output_tokens_details") or {}).get("thinking_tokens") or 0
            if ant is None:
                msgs[m["id"]] = {"ctx": ctx, "grav": u.get("cache_creation_input_tokens") or 0,
                                 "ent": u.get("input_tokens") or 0, "lido": u.get("cache_read_input_tokens") or 0,
                                 "grav1h": ((u.get("cache_creation") or {}).get("ephemeral_1h_input_tokens") or 0),
                                 "saida": u.get("output_tokens") or 0, "pensou": pensou,
                                 "modelo": m.get("model"), "speed": u.get("speed"),
                                 "buscas_api": (u.get("server_tool_use") or {}).get("web_search_requests") or 0}
                if o.get("effort"):
                    esforcos[o["effort"]] = esforcos.get(o["effort"], 0) + 1
            else:
                ant["saida"] = max(ant["saida"], u.get("output_tokens") or 0)
                ant["pensou"] = max(ant["pensou"], pensou)
            blocos = [b for b in m.get("content") or [] if isinstance(b, dict)]
            ferramentas += sum(1 for b in blocos if b.get("type") == "tool_use")
            buscas += sum(1 for b in blocos if b.get("type") == "tool_use" and b.get("name") == "WebSearch")
            if m.get("model") and ant is None:
                modelos[m["model"]] = modelos.get(m["model"], 0) + 1
    if not msgs:
        return None
    lista = list(msgs.values())
    principal = max(modelos, key=modelos.get) if modelos else None
    extra = {"modelos": modelos} if len(modelos) > 1 else {}
    if esforcos:
        extra["esforco"] = max(esforcos, key=esforcos.get)
        if len(esforcos) > 1:
            extra["esforcos"] = esforcos
    tot = {k: sum(x[k] for x in lista) for k in ("ent", "lido", "grav", "grav1h", "saida", "pensou", "buscas_api")}
    usd = 0.0
    for x in lista:              # chamada a chamada: o modelo servido, o Haiku acima de 100 mil e o speed fast
        c = custo_usd(x["ent"], x["lido"], x["grav"], x["saida"], x["modelo"] or principal, x["grav1h"],
                      fator_chamada(x["modelo"] or principal, x["ctx"], x["speed"]))
        if c is None:
            usd = None
            break
        usd += c
    n_buscas = buscas + tot["buscas_api"]
    return {
        "modelo": principal,
        "tokens": lista[-1]["ctx"],
        "chamadas": ferramentas,
        "duracao_ms": int((max(tempos) - min(tempos)).total_seconds() * 1000) if len(tempos) > 1 else 0,
        "chamadas_modelo": len(lista),
        "contexto_total": sum(x["ctx"] for x in lista),
        "entrada": tot["ent"],
        "cache_lido": tot["lido"],
        "cache_gravado": tot["grav"],
        "cache_gravado_1h": tot["grav1h"],
        "saida": tot["saida"],
        "saida_raciocinio": tot["pensou"],
        "custo_relativo": custo_relativo(tot["ent"], tot["lido"], tot["grav"], tot["saida"], principal, tot["grav1h"]),
        "custo_usd": round(usd, 4) if usd is not None else None,
        "websearch": n_buscas,
        "websearch_usd_est": buscas_usd_est(n_buscas),
        "_prompt": primeiro_prompt or "",
        **extra,
    }


SOMAVEIS = ("chamadas", "duracao_ms", "chamadas_modelo", "contexto_total", "entrada", "cache_lido",
            "cache_gravado", "cache_gravado_1h", "saida", "saida_raciocinio", "custo_relativo", "websearch")


def somar(a, b):
    """Uso de um coletor relancado: soma os contadores; tokens/modelo ficam os do mais recente (b)."""
    out = dict(b)
    for k in SOMAVEIS:
        out[k] = int(a.get(k) or 0) + int(b.get(k) or 0)
    out["custo_usd"] = (round(a["custo_usd"] + b["custo_usd"], 4)
                        if a.get("custo_usd") is not None and b.get("custo_usd") is not None else None)
    out["websearch_usd_est"] = buscas_usd_est(out.get("websearch"))
    out["relancamentos"] = int(a.get("relancamentos") or 0) + 1
    return out


def com_fechamento(orq):
    """Soma ao orquestrador a chamada final estimada (ver o cabecalho). A gravacao dela tem o TTL das
    gravacoes do orquestrador (1 h quando todas foram de 1 h, como desde 17/11/2026)."""
    est = {"cache_lido": int(orq.get("tokens") or 0), "cache_gravado": FECHAMENTO["cache_gravado"],
           "saida": FECHAMENTO["saida"]}
    g1 = est["cache_gravado"] if orq.get("cache_gravado") and orq.get("cache_gravado_1h") == orq["cache_gravado"] else 0
    if g1:
        est["cache_gravado_1h"] = g1
    est["custo_relativo"] = custo_relativo(0, est["cache_lido"], est["cache_gravado"], est["saida"], orq.get("modelo"), g1)
    c = custo_usd(0, est["cache_lido"], est["cache_gravado"], est["saida"], orq.get("modelo"), g1)
    orq["fechamento_estimado"] = est
    orq["custo_relativo"] = int(orq.get("custo_relativo") or 0) + est["custo_relativo"]
    if c is not None and orq.get("custo_usd") is not None:
        est["custo_usd"] = round(c, 4)
        orq["custo_usd"] = round(orq["custo_usd"] + c, 4)
    return orq


def custo_execucao(orq, coletores):
    """{'total', 'orquestrador', 'coletores': {nome: US$}, 'buscas', 'buscas_usd_est', 'precos_em'} da execucao
    (None no total se algum agente tem modelo fora da tabela: o helper avisa, sem chutar)."""
    orq, coletores = orq or {}, coletores or {}
    agentes = [("orquestrador", orq)] + sorted(coletores.items())
    buscas = sum(int((u or {}).get("websearch") or 0) for _, u in agentes)
    partes = {n: (u or {}).get("custo_usd") for n, u in agentes}
    sem_preco = sorted(n for n, v in partes.items() if v is None and (n == "orquestrador" or (coletores.get(n) or {})))
    total = None if sem_preco else round(sum(v or 0 for v in partes.values()) + buscas_usd_est(buscas), 4)
    out = {"total": total, "orquestrador": partes.get("orquestrador"),
           "coletores": {n: partes[n] for n, _ in agentes if n != "orquestrador"},
           "buscas": buscas, "buscas_usd_est": buscas_usd_est(buscas), "precos_em": PRECOS_EM}
    if sem_preco:
        out["sem_preco"] = sem_preco
    return out


def sessao_atual():
    """Transcricao principal mais recente (a da sessao em curso)."""
    cands = glob.glob(os.path.join(RAIZ, "*", "*.jsonl"))
    return max(cands, key=os.path.getmtime) if cands else None


def medir(desde=None, ate=None):
    """{'orquestrador': {...}, 'coletores': {'gmail': {...}, ...}} da sessao
    atual; so conta o que ocorreu a partir de `desde` (datetime com fuso)."""
    principal = sessao_atual()
    if not principal:
        return {}
    out = {}
    orq = uso_transcricao(principal, desde, ate)
    if orq:
        orq.pop("_prompt", None)
        out["orquestrador"] = com_fechamento(orq)
    pasta = os.path.join(principal[:-len(".jsonl")], "subagents")
    coletores = {}
    for arq in sorted(glob.glob(os.path.join(pasta, "agent-*.jsonl")), key=os.path.getmtime):
        u = uso_transcricao(arq, desde, ate)
        if not u:
            continue
        nome = next((n for marca, n in COLETORES if marca in u["_prompt"]), None)
        if not nome:
            continue
        u.pop("_prompt", None)
        coletores[nome] = somar(coletores[nome], u) if nome in coletores else u   # relancamento: soma
    if coletores:
        out["coletores"] = coletores
    if out:
        out["custo_usd"] = custo_execucao(out.get("orquestrador"), coletores)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--desde", help="ISO com fuso; padrao: toda a sessao")
    ap.add_argument("--ate", help="ISO com fuso; padrao: agora")
    a = ap.parse_args()
    lim = []
    for v in (a.desde, a.ate):
        t = _ts(v) if v else None
        lim.append(t.replace(tzinfo=timezone.utc) if t and t.tzinfo is None else t)
    print(json.dumps(medir(*lim), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
