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
# (com cache_gravado_1h quando a transcricao separa) e saida, e o
# "custo_relativo": o custo em unidades do preco do token de ENTRADA do
# proprio modelo (vale para qualquer modelo, sem tabela de precos em dolar):
#     custo_relativo = entrada x 1 + cache_lido x 0,1 + cache_gravado x 1,25 + saida x 5
# Pesos (PESOS abaixo) = multiplicadores da tabela da Anthropic em relacao a
# entrada: leitura de cache 0,1x, gravacao de cache (TTL 5 min) 1,25x, saida
# 5x. A gravacao com TTL de 1 h custa 2x; ela e contada a 1,25x para o numero
# ficar comparavel com as execucoes antigas, que nao separam o TTL
# (cache_gravado_1h fica registrado para quem quiser recalcular). Para dolar:
# custo_relativo x preco do token de entrada do modelo.
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
PESOS = {"entrada": 1.0, "cache_lido": 0.1, "cache_gravado": 1.25, "saida": 5.0}
FECHAMENTO = {"cache_gravado": 2000, "saida": 700}   # estimativa da chamada final do orquestrador


def custo_relativo(entrada, cache_lido, cache_gravado, saida):
    """Custo em tokens-equivalentes de ENTRADA do modelo (ver o cabecalho)."""
    return int(round(entrada * PESOS["entrada"] + cache_lido * PESOS["cache_lido"] +
                     cache_gravado * PESOS["cache_gravado"] + saida * PESOS["saida"]))


def _ts(s):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


def uso_transcricao(caminho, desde=None, ate=None):
    """Agrega o uso de uma transcricao. Linhas repetidas do mesmo
    message.id contam uma vez (saida = maior valor visto)."""
    msgs, ferramentas, tempos, primeiro_prompt, modelos = {}, 0, [], None, {}
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
            if quando:
                tempos.append(quando)
            u = m["usage"]
            ctx = (u.get("input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0) + \
                (u.get("cache_creation_input_tokens") or 0)
            ant = msgs.get(m["id"])
            if ant is None:
                msgs[m["id"]] = {"ctx": ctx, "grav": u.get("cache_creation_input_tokens") or 0,
                                 "ent": u.get("input_tokens") or 0, "lido": u.get("cache_read_input_tokens") or 0,
                                 "grav1h": ((u.get("cache_creation") or {}).get("ephemeral_1h_input_tokens") or 0),
                                 "saida": u.get("output_tokens") or 0}
            else:
                ant["saida"] = max(ant["saida"], u.get("output_tokens") or 0)
            ferramentas += sum(1 for b in m.get("content") or [] if b.get("type") == "tool_use")
            if m.get("model") and ant is None:
                modelos[m["model"]] = modelos.get(m["model"], 0) + 1
    if not msgs:
        return None
    lista = list(msgs.values())
    principal = max(modelos, key=modelos.get) if modelos else None
    extra = {"modelos": modelos} if len(modelos) > 1 else {}
    tot = {k: sum(x[k] for x in lista) for k in ("ent", "lido", "grav", "grav1h", "saida")}
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
        "custo_relativo": custo_relativo(tot["ent"], tot["lido"], tot["grav"], tot["saida"]),
        "_prompt": primeiro_prompt or "",
        **extra,
    }


SOMAVEIS = ("chamadas", "duracao_ms", "chamadas_modelo", "contexto_total", "entrada", "cache_lido",
            "cache_gravado", "cache_gravado_1h", "saida", "custo_relativo")


def somar(a, b):
    """Uso de um coletor relancado: soma os contadores; tokens/modelo ficam os do mais recente (b)."""
    out = dict(b)
    for k in SOMAVEIS:
        out[k] = int(a.get(k) or 0) + int(b.get(k) or 0)
    out["relancamentos"] = int(a.get("relancamentos") or 0) + 1
    return out


def com_fechamento(orq):
    """Soma ao orquestrador a chamada final estimada (ver o cabecalho)."""
    est = {"cache_lido": int(orq.get("tokens") or 0), "cache_gravado": FECHAMENTO["cache_gravado"],
           "saida": FECHAMENTO["saida"]}
    est["custo_relativo"] = custo_relativo(0, est["cache_lido"], est["cache_gravado"], est["saida"])
    orq["fechamento_estimado"] = est
    orq["custo_relativo"] = int(orq.get("custo_relativo") or 0) + est["custo_relativo"]
    return orq


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
