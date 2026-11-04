#!/usr/bin/env python3
# =====================================================================
# concursos_html.py — monta, a partir do registro `concursos` do ledger
# (com os ledger_updates.concursos do /tmp/execucao.json ja aplicados em
# memoria), as duas secoes de Concursos do template v3:
#   - "Concursos jurídicos — Carreira jurídica": quadro "Prazos no radar"
#     (so prazos CONFIRMADOS nos proximos 30 dias) + um bloco por carreira,
#     na ordem do prompt mestre §10, com zebra e selo;
#   - "Concursos jurídicos — Quadro de apoio".
# Regras de texto (deterministicas, para o e-mail nao inflar):
#   - registro criado hoje: "Novo no radar:" em negrito;
#   - registro atualizado hoje: "Atualizado hoje:" em negrito, linha inteira;
#   - verificado ha <= 14 dias: linha inteira + "(herdada; verificado em DD/MM)"
#     quando nao for de hoje;
#   - verificado ha > 14 dias: linha COMPACTA (ate o 1o ";") + "(herdada;
#     verificado em DD/MM)" — o rodizio do coletor reverifica esses.
# Nada de layout novo: estilos copiados do template.
#
# USO (passo 5, depois do --validar OK):
#   python3 work/concursos_html.py --execucao /tmp/execucao.json > /tmp/concursos.html
# =====================================================================

import argparse
import copy
import html
import json
import os
import sys
from datetime import date

AQUI = os.path.dirname(os.path.abspath(__file__))
BLOCOS = ["Magistratura Estadual", "Magistratura Federal", "Promotor de Justiça (Estadual)",
          "MPF/MPU — Procurador da República", "PFN", "AGU — Advogado da União",
          "Procurador do Estado (PGE)", "Procurador do Município (PGM)",
          "Defensor Público Estadual (DPE)", "Defensor Público Federal (DPU)"]
APOIO = "Quadro de apoio"
COMPACTAR_APOS = 14

ESTILO = {
    "OFICIAL": "background:#e8eef7;color:#0b2545",
    "VERDE": "color:#1e6b3a;border:1px solid #bfe3cc",
    "URGENTE": "background:#fdf0f0;color:#a61b1b;border:1px solid #f0c2c2",
    "NEUTRO": "color:#5a6773;border:1px solid #c9ced6",
    "ALERTA": "color:#8a6d1d;border:1px solid #e6d3a3",
    "NAVY": "background:#0b2545;color:#ffffff",
}
SELO_ESTILO = {
    "CONFIRMADO POR FONTE OFICIAL": "OFICIAL", "CONFIRMADO": "OFICIAL", "VERSÍCULO DO DIA": "OFICIAL",
    "CONFIRMADO POR FONTE OFICIAL ALTERNATIVA": "VERDE", "INSCRIÇÕES ABERTAS": "VERDE",
    "EDITAL PUBLICADO": "VERDE", "NOVO": "VERDE",
    "ENCERRA HOJE": "URGENTE", "ENCERRA EM BREVE": "URGENTE", "URGENTE": "URGENTE",
    "PROVA EM BREVE": "URGENTE",
    "MÍDIA ESPECIALIZADA": "NEUTRO", "OPINIÃO/ANÁLISE": "NEUTRO", "EM ANDAMENTO": "NEUTRO",
    "EM PLANEJAMENTO": "NEUTRO", "PROVA REALIZADA": "NEUTRO", "INSCRIÇÕES ENCERRADAS": "NEUTRO",
    "PENDÊNCIA": "ALERTA", "PENDÊNCIA DE VERIFICAÇÃO": "ALERTA", "FORTE INDÍCIO": "ALERTA",
    "RUMOR": "ALERTA", "SEM CONFIRMAÇÃO OFICIAL": "ALERTA", "SABEDORIA DO DIA": "NAVY",
}
FONTE = "font-family:Arial,Helvetica,sans-serif"
CEL = "padding:6px 8px;border-bottom:1px solid #e8edf2"


def esc(s):
    return html.escape(s or "", quote=False)


def selo(texto):
    if texto not in SELO_ESTILO:
        sys.exit("ERRO: selo fora da lista fechada: %r" % texto)
    return ('<span style="display:inline-block;%s;font-size:9px;font-weight:bold;padding:2px 6px;'
            'border-radius:3px">%s</span>' % (ESTILO[SELO_ESTILO[texto]], esc(texto)))


def titulo(t, topo=22):
    return ('<tr><td style="padding:%dpx 20px 8px 20px;%s"><div style="border-left:4px solid #c5a253;'
            'padding-left:10px;font-size:16px;font-weight:bold;color:#0b2545">%s</div></td></tr>'
            % (topo, FONTE, t))


def aplicar(concursos, upd):
    """Copia do registro com ledger_updates.concursos aplicados. Devolve (lista, novos, alterados)."""
    regs = copy.deepcopy(concursos)
    por_id = {c["id"]: c for c in regs}
    novos, alterados = set(), set()
    for ident, campos in (upd or {}).items():
        if campos.get("remover"):
            regs = [c for c in regs if c["id"] != ident]
            por_id.pop(ident, None)
            continue
        if ident in por_id:
            antes = dict(por_id[ident])
            por_id[ident].update({k: v for k, v in campos.items() if k != "desfecho"})
            # so verificado_em novo (RODIZIO IGUAL) nao e novidade para o leitor
            if any(antes.get(k) != v for k, v in campos.items() if k not in ("verificado_em", "desfecho")):
                alterados.add(ident)
        else:
            c = dict(campos, id=ident)
            regs.append(c)
            por_id[ident] = c
            novos.add(ident)
    return regs, novos, alterados


def texto_linha(c, hoje, novos, alterados):
    linha = c.get("linha", "")
    try:
        ver = date.fromisoformat(c.get("verificado_em", ""))
    except ValueError:
        ver = None
    idade = (hoje - ver).days if ver else 999
    if c["id"] in novos:
        return "<b>Novo no radar:</b> <b>%s</b>." % esc(linha.rstrip("."))
    if c["id"] in alterados and idade == 0:
        return "<b>Atualizado hoje:</b> %s." % esc(linha.rstrip("."))
    if idade == 0:
        return esc(linha.rstrip(".")) + "."
    if idade > COMPACTAR_APOS:
        linha = linha.split(";")[0]
    return "%s <i>(herdada; verificado em %s)</i>." % (esc(linha.rstrip(".")), ver.strftime("%d/%m") if ver else "?")


def tabela_bloco(nome, regs, hoje, novos, alterados):
    rows = ['<tr bgcolor="#0b2545"><td colspan="2" style="color:#ffffff;font-weight:bold;padding:6px 8px;'
            'font-size:11px">%s</td></tr>' % esc(nome)]
    if not regs:
        rows.append('<tr><td colspan="2" style="%s;color:#5a6773">Nenhum concurso acompanhado neste bloco; '
                    'a varredura de descoberta segue no rodízio semanal.</td></tr>' % CEL)
    for n, c in enumerate(regs):
        zebra = ' bgcolor="#f9fafc"' if n % 2 else ""
        rows.append('<tr%s><td style="%s" width="72%%">%s</td><td style="%s;text-align:right;'
                    'vertical-align:top">%s</td></tr>' % (
                        zebra, CEL, texto_linha(c, hoje, novos, alterados), CEL, selo(c.get("selo"))))
    return rows


def radar(regs, hoje):
    itens = []
    for c in regs:
        for pz in c.get("prazos") or []:
            try:
                d = date.fromisoformat(pz.get("data", ""))
            except ValueError:
                continue
            dias = (d - hoje).days
            if pz.get("confirmado") and 0 <= dias <= 30:
                itens.append((d, dias, c, pz))
    itens.sort(key=lambda x: x[0])
    if not itens:
        return []
    quando = lambda n: {0: "hoje", 1: "amanhã"}.get(n, "em %d dias" % n)
    orgao = lambda c: c.get("linha", c["id"]).split(":")[0].split(" — ")[0].strip()
    linhas = ['<tr><td width="92" style="padding:3px 0;vertical-align:top;font-weight:bold;color:%s">'
              '%s · %s</td><td style="padding:3px 0">%s — %s</td></tr>' % (
                  "#a61b1b" if dias <= 7 else "#0b2545", d.strftime("%d/%m"), quando(dias),
                  esc(orgao(c)), esc(pz.get("evento"))) for d, dias, c, pz in itens]
    return ['<tr><td style="padding:4px 20px 10px 20px;%s">' % FONTE,
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse">',
            '<tr><td bgcolor="#fdf6e9" style="border-left:4px solid #c5a253;padding:10px 12px">',
            '<div style="font-size:12px;font-weight:bold;color:#0b2545;margin-bottom:6px">⏰ Prazos no radar</div>',
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:'
            'collapse;font-size:12px;line-height:17px;color:#2f3a45">'] + linhas + \
           ['</table>', '</td></tr>', '</table>', '</td></tr>']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--execucao", default="/tmp/execucao.json")
    ap.add_argument("--ledger", default=os.path.join(AQUI, "robozinho-aprendizado.json"))
    ap.add_argument("--janela", default="/tmp/janela.json")
    a = ap.parse_args()
    led = json.load(open(a.ledger, encoding="utf-8"))
    upd = {}
    if os.path.exists(a.execucao):
        upd = (json.load(open(a.execucao, encoding="utf-8")).get("ledger_updates") or {}).get("concursos") or {}
    hoje = date.today()
    if os.path.exists(a.janela):
        hoje = date.fromisoformat(json.load(open(a.janela, encoding="utf-8"))["data"])
    regs, novos, alterados = aplicar(led.get("concursos") or [], upd)

    def do_bloco(b):
        # dentro do bloco: inscricoes abertas/encerrando > edital > andamento > planejamento > pendencia
        ordem = ["ENCERRA HOJE", "ENCERRA EM BREVE", "INSCRIÇÕES ABERTAS", "EDITAL PUBLICADO",
                 "PROVA EM BREVE", "EM ANDAMENTO", "INSCRIÇÕES ENCERRADAS", "PROVA REALIZADA",
                 "EM PLANEJAMENTO", "PENDÊNCIA DE VERIFICAÇÃO", "PENDÊNCIA"]
        return sorted((c for c in regs if c.get("bloco") == b),
                      key=lambda c: (c["id"] not in novos, ordem.index(c.get("selo")) if c.get("selo") in ordem else 99))

    fora = [c["id"] for c in regs if c.get("bloco") not in BLOCOS + [APOIO]]
    if fora:
        sys.exit("ERRO: bloco desconhecido em %s" % fora)

    out = ["<!-- CONCURSOS — CARREIRA (gerado por work/concursos_html.py) -->",
           titulo("💼 Concursos jurídicos — Carreira jurídica", 18)]
    out += radar(regs, hoje)
    out.append('<tr><td style="padding:0 20px;%s;font-size:12px;line-height:18px;color:#2f3a45">' % FONTE)
    out.append('<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse">')
    for n, b in enumerate(BLOCOS):
        if n:
            out.append('<tr><td colspan="2" style="height:6px;line-height:6px;font-size:1px">&nbsp;</td></tr>')
        out += tabela_bloco(b, do_bloco(b), hoje, novos, alterados)
    out += ["</table>", "</td></tr>", "<!-- CONCURSOS — APOIO -->",
            titulo("🗂️ Concursos jurídicos — Quadro de apoio"),
            '<tr><td style="padding:0 20px;%s;font-size:12px;line-height:18px;color:#2f3a45">' % FONTE,
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse">']
    out += tabela_bloco("Analista e técnico (TJ, TRF, TRT, MP, Defensoria)", do_bloco(APOIO), hoje, novos, alterados)
    out += ["</table>", "</td></tr>", "<!-- fim CONCURSOS -->"]
    texto = "\n".join(out)
    print(texto)
    sys.stderr.write("concursos_html: %d registros (%d novos, %d atualizados hoje), %d bytes\n"
                     % (len(regs), len(novos), len(alterados), len(texto.encode("utf-8"))))


if __name__ == "__main__":
    main()
