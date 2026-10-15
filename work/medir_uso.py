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
    return {
        "modelo": principal,
        "tokens": lista[-1]["ctx"],
        "chamadas": ferramentas,
        "duracao_ms": int((max(tempos) - min(tempos)).total_seconds() * 1000) if len(tempos) > 1 else 0,
        "chamadas_modelo": len(lista),
        "contexto_total": sum(x["ctx"] for x in lista),
        "cache_gravado": sum(x["grav"] for x in lista),
        "saida": sum(x["saida"] for x in lista),
        "_prompt": primeiro_prompt or "",
        **extra,
    }


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
        out["orquestrador"] = orq
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
        coletores[nome] = u      # relancamento do mesmo coletor: vale o mais recente
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
