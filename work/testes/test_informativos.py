#!/usr/bin/env python3
# =====================================================================
# test_informativos.py — testes do work/informativos.py, sem rede e sem pytest.
#   python3 work/testes/test_informativos.py      -> OK/FALHOU por teste; codigo != 0 em falha
# Fixtures (texto, extraidos dos documentos oficiais reais, em fixtures/informativos/):
#   stf1236/1233/1234-layout.txt          pdftotext -layout do Informativo STF (sumario + caixas RESUMO)
#   rg397/396/394.txt                       pdftotext da RG em Pauta 397 (11 temas), 396 (9) e 394 (13)
#   stj909.html                             pagina do Informativo STJ 909 (inteiro teor reduzido)
#   stj910.html                             pagina de edicao inexistente (sem o cabecalho do numero)
#   stj912-layout-novo.html                 sintetica: cabecalho presente, rotulos desconhecidos
#   historico/resumo-legislativo-historico.json  sintetico, com as edicoes vazias reais de set-nov/2026
# Os downloads sao simulados (informativos.baixar/pdf_texto trocados); tudo o que o script grava vai
# para um ROBOZINHO_TMP temporario.
# =====================================================================

import contextlib
import io
import json
import os
import re
import shutil
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.dirname(AQUI)
FIX = os.path.join(AQUI, "fixtures", "informativos")
sys.path.insert(0, WORK)

TMP = tempfile.mkdtemp(prefix="robozinho-inf-")
os.environ["ROBOZINHO_TMP"] = TMP
os.environ["ROBOZINHO_INF_ESPERA"] = "0"

import informativos as I  # noqa: E402

FALHAS, TOTAL = [], [0]
ESPERAS = []
I.dormir = lambda s: ESPERAS.append(s)
I.AQUI = os.path.join(FIX, "historico")   # o historico dos testes


def checar(nome, cond, detalhe=""):
    TOTAL[0] += 1
    if cond:
        print("OK      %s" % nome)
    else:
        FALHAS.append(nome)
        print("FALHOU  %s%s" % (nome, (" — " + str(detalhe)) if detalhe else ""))


def fx(nome, modo="r"):
    if "b" in modo:
        return open(os.path.join(FIX, nome), "rb").read()
    return open(os.path.join(FIX, nome), encoding="utf-8").read()


# ------------------------------------------------------------------ downloads simulados
PDF = {"stf1236": "stf1236-layout.txt", "stf1233": "stf1233-layout.txt", "rg397": "rg397.txt",
       "rg394": "rg397.txt"}


def url_id(url):
    for tipo, modelo in I.URL.items():
        m = re.fullmatch(re.escape(modelo).replace("%04d", r"(\d+)").replace("%d", r"(\d+)"), url)
        if m:
            return "%s%d" % (tipo, int(m.group(1)))
    raise AssertionError("url inesperada: %s" % url)


class Rede:
    """respostas[id] = lista de (http, conteudo) consumida a cada pedido; o ultimo se repete.
    conteudo: nome de fixture de PDF (vira b'%PDF-FIXTURE:<id>'), b'...' bruto ou nome .html."""

    def __init__(self, respostas, padrao=(404, b"")):
        self.respostas = {k: list(v) for k, v in respostas.items()}
        self.padrao = padrao
        self.pedidos = []

    def baixar(self, url):
        rid = url_id(url)
        self.pedidos.append(rid)
        fila = self.respostas.get(rid)
        if not fila:
            codigo, cont = self.padrao
        else:
            codigo, cont = fila.pop(0) if len(fila) > 1 else fila[0]
        if isinstance(cont, str) and cont.endswith(".html"):
            cont = fx(cont, "rb")
        elif cont == "pdf":
            cont = b"%PDF-FIXTURE:" + rid.encode()
        return codigo, cont


def pdf_texto_falso(dados, layout):
    rid = dados.split(b":", 1)[1].decode()
    return fx(PDF[rid])


I.pdf_texto = pdf_texto_falso


def rodar(rede, argv=(), janela=None):
    """Roda informativos.main() com a rede simulada; devolve (stdout, json, fontes_status)."""
    for nome in ("informativos.json", "janela.json"):
        try:
            os.unlink(os.path.join(TMP, nome))
        except FileNotFoundError:
            pass
    if janela is not None:
        json.dump(janela, open(os.path.join(TMP, "janela.json"), "w"))
    I.baixar = rede.baixar
    ESPERAS.clear()
    saida = io.StringIO()
    velho = sys.argv
    sys.argv = ["informativos.py"] + list(argv)
    try:
        with contextlib.redirect_stdout(saida):
            I.main()
    finally:
        sys.argv = velho
    js = json.load(open(os.path.join(TMP, "informativos.json"), encoding="utf-8"))
    try:
        st = json.load(open(os.path.join(TMP, "fontes_status.json"), encoding="utf-8"))
    except FileNotFoundError:
        st = None
    return saida.getvalue(), js, st


def por_id(js):
    return {r.get("id"): r for r in js if r.get("id")}


def linhas_leitor(out):
    """Linhas que podem chegar ao leitor (tudo menos as tecnicas)."""
    return [l for l in out.splitlines() if not l.startswith(("TECNICO ", "SOURCE_STATUS "))]


JANELA = {"ignorar_execucao": "2026-11-16-7h", "execution_id": "2026-11-16-7h"}


# ------------------------------------------------------------------ 1. RESUMO do Informativo STF
def t_stf_resumo():
    data, itens = I.stf_texto(fx("stf1236-layout.txt"))
    checar("stf1236: data e 4 itens do sumário", data == "10 de novembro de 2026" and len(itens) == 4, (data, len(itens)))
    checar("stf1236: 4/4 resumos validados", all(it.get("resumo") for it in itens), [bool(it.get("resumo")) for it in itens])
    r = [it.get("resumo", "") for it in itens]
    checar("stf1236[0]: hifenização desfeita e coluna de palavras-chave fora",
           r[0].startswith("Os efeitos da tese fixada no Tema 1.308 da repercussão geral – que assegura")
           and "contratados temporariamente – devem ser modulados" in r[0]
           and r[0].endswith("para os que ainda não o implementaram.") and "PÚBLICO" not in r[0], r[0])
    checar("stf1236[1]: linha de largura total incluída (prazo de três meses previsto em lei)",
           r[1] == ("É inconstitucional a interpretação de norma estadual que impeça a remuneração de policiais "
                    "penais pelo serviço extraordinário prestado além da jornada legalmente estabelecida quando, "
                    "no interesse da Administração Pública, não for possível usufruir a folga compensatória no "
                    "prazo de três meses previsto em lei."), r[1])
    checar("stf1236[3]: resumo do Tema 118 (ISS) sem a tese da coluna esquerda",
           r[3].startswith("O Imposto sobre Serviços de Qualquer Natureza (ISS) deve ser excluído")
           and "Tese fixada" not in r[3] and r[3].endswith("como receita ou faturamento."), r[3])
    checar("stf1236: títulos do sumário sem corte nem pontilhado",
           itens[0]["titulo"].endswith("ARE 1.487.739 ED-segundos/PE (Tema 1.308 RG)") and "...." not in itens[0]["titulo"],
           itens[0]["titulo"])
    data, itens = I.stf_texto(fx("stf1233-layout.txt"))
    checar("stf1233: 4/4 resumos validados", len(itens) == 4 and all(it.get("resumo") for it in itens),
           [len(it.get("resumo", "")) for it in itens])
    checar("stf1233[3]: resumo de 570 caracteres inteiro (modulação do IPTU)",
           len(itens[3]["resumo"]) == 570 and itens[3]["resumo"].endswith("pendentes de conclusão até 12.08.2026."),
           len(itens[3].get("resumo", "")))
    checar("stf1233[3]: título que quebra em 'ED/' + 'SC' sem espaço",
           itens[3]["titulo"].endswith("ARE 1.593.784 ED/SC (Tema 1.455 RG)"), itens[3]["titulo"])
    checar("stf1233[1]: 'con-' + 'corrente' e 'asse-' + 'gura' juntados",
           "competência legislativa concorrente" in itens[1]["resumo"] and "que assegura às pessoas" in itens[1]["resumo"],
           itens[1]["resumo"])
    data, itens = I.stf_texto(fx("stf1234-layout.txt"))
    checar("stf1234: 4/4 resumos validados (3ª edição real)", data == "26 de outubro de 2026" and len(itens) == 4
           and all(it.get("resumo") for it in itens)
           and itens[3]["resumo"].endswith("data do início da produção de efeitos da Lei nº 13.606/2018."),
           [len(it.get("resumo", "")) for it in itens])
    # numero de RESUMO diferente do de itens -> nenhum resumo (fica so o titulo)
    t = fx("stf1236-layout.txt")
    k = t.find("RESUMO:", t.find("RESUMO:") + 1)
    t2 = t[:k] + "SINOPSE:" + t[k + 7:]
    _, itens = I.stf_texto(t2)
    checar("stf: 3 RESUMO para 4 itens -> nenhum item com resumo", len(itens) == 4 and not any(it.get("resumo") for it in itens))
    checar("resumo_valido: curto, sem ponto final, longo e com palavras-chave vazadas são recusados",
           not I.resumo_valido("É constitucional.") and not I.resumo_valido("x" * 150)
           and not I.resumo_valido(("palavra " * 120).strip() + ".")
           and not I.resumo_valido("É constitucional a norma SEGURANÇA PÚBLICA; POLÍCIA PENAL que dispõe sobre a "
                                   "carreira de policial penal, inclusive quanto à subordinação.")
           and I.resumo_valido("É constitucional lei complementar estadual que dispõe sobre a carreira de policial "
                               "penal (PIS e COFINS), inclusive quanto à subordinação."))
    checar("juntar: hífen de palavra composta mantido (ED-segundos)",
           I.juntar(["RE 1.042.075 ED-", "segundos e tempora-", "riamente"]) == "RE 1.042.075 ED-segundos e temporariamente")


# ------------------------------------------------------------------ 2. RG em Pauta
def t_rg():
    periodo, itens = I.rg_texto(fx("rg397.txt"))
    temas = [it["tema"] for it in itens]
    checar("rg397: 11 temas (o 1.338 não some pelo teto)", len(itens) == 11 and "1.338" in temas, temas)
    t = {it["tema"]: it for it in itens}
    checar("rg397: nenhum tema rotulado 'Temas Finalizados' (a seção diz 'Não houve')",
           not any(it["secao"] == "Temas Finalizados" for it in itens), [it["secao"] for it in itens])
    checar("rg397: estágios", (t["1.483"]["estagio"], t["1.427"]["estagio"], t["1.499"]["estagio"],
                               t["1.324"]["estagio"], t["977"]["estagio"]) ==
           ("tese publicada", "trânsito em julgado", "em votação no PV até 13/11", "pauta do Plenário 11/11",
            "pauta da sessão virtual de 06/11 a 13/11"),
           [(k, v["estagio"]) for k, v in t.items()])
    checar("rg397: 'Data prevista…' fora do título, em previsao",
           t["1.500"]["previsao"] == "2026-11-13" and "Data prevista" not in t["1.500"]["titulo"]
           and t["1.500"]["titulo"].endswith("não atingidos pela prescrição."), t["1.500"])
    checar("rg397: previsao das pautas = data da sessão", (t["1.218"]["previsao"], t["1.338"]["previsao"]) ==
           ("2026-11-11", "2026-11-13"))
    checar("rg397: título do Tema 977 sem truncar",
           t["977"]["titulo"].endswith("relacionados à conduta delitiva e hábeis a identificar o agente do crime.")
           and "…" not in t["977"]["titulo"], t["977"]["titulo"])
    checar("rg397: sem repercussão geral detectado pelo texto da tese (1.487 e 1.478)",
           [k for k, v in t.items() if v["sem_repercussao_geral"]] == ["1.487", "1.478"])
    checar("rg397: segundo processo do Tema 1.483 e tese inteira",
           t["1.483"]["processo"] == "RE 1.616.922; RE 1.616.090" and t["1.483"]["tese"].endswith("pertinentes.”"),
           t["1.483"]["processo"])
    checar("rg397: notícias da RG ignoradas", not any("Fachin participou" in it["titulo"] + it["tese"] for it in itens))
    _, itens = I.rg_texto(fx("rg396.txt"))
    t = {it["tema"]: it for it in itens}
    checar("rg396: 9 temas; rótulo do placar (REAFIRMAÇÃO DE JURISPRUDÊNCIA) não vira seção",
           len(itens) == 9 and t["1.496"]["secao"] == "Temas Finalizados", [it["tema"] for it in itens])
    checar("rg396: temas finalizados com o resultado da 'Decisão:'",
           t["1.495"]["estagio"] == "repercussão geral reconhecida" and t["1.496"]["estagio"] == "repercussão geral reconhecida"
           and t["1.495"]["decisao"].endswith("questão constitucional suscitada."), t["1.495"])
    checar("rg396: acórdão publicado sem tese não é 'tese publicada'",
           t["488"]["estagio"] == "acórdão publicado" and t["1.258"]["estagio"] == "tese publicada", t["488"]["estagio"])
    checar("rg396: RELATOR na mesma linha do processo fica fora do processo",
           (t["989"]["processo"], t["1.253"]["processo"]) == ("RE 1.093.553", "RE 1.163.774-ED"))
    checar("rg396: pauta presencial e sessão virtual que cruza o mês",
           (t["989"]["estagio"], t["1.253"]["estagio"]) == ("pauta do Plenário 04/11", "pauta da sessão virtual de 30/10 a 10/11"))
    _, itens = I.rg_texto(fx("rg394.txt"))
    t = {it["tema"]: it for it in itens}
    checar("rg394: 13 temas; TEMAS CANCELADOS reconhecida", len(itens) == 13 and t["106"]["estagio"] == "tema cancelado"
           and t["106"]["decisao"].startswith("O Tribunal, por unanimidade e nos termos do voto da Ministra Cármen Lúcia, cancelou"),
           [(it["tema"], it["estagio"]) for it in itens])
    checar("rg394: 'ausência da repercussão geral' (com 'da') também é sem RG",
           t["1.480"]["sem_repercussao_geral"] and t["1.479"]["sem_repercussao_geral"] and not t["1.483"]["sem_repercussao_geral"])
    checar("rg394: finalizados negados e reconhecido pela 'Decisão:'",
           (t["1.490"]["estagio"], t["1.491"]["estagio"], t["1.492"]["estagio"]) ==
           ("repercussão geral negada", "repercussão geral reconhecida", "repercussão geral negada")
           and t["1.490"]["sem_repercussao_geral"] and not t["1.491"]["sem_repercussao_geral"]
           and t["1.491"]["decisao"].endswith("Fux, Nunes Marques e André Mendonça."), t["1.491"]["decisao"])
    checar("rg394: tese de mérito (Tema 1.016) inteira e 'RED. ACÓRD.' fora do processo",
           t["1.016"]["estagio"] == "tese fixada" and t["1.016"]["tese"].endswith("e as situações consolidadas.”")
           and t["1.016"]["processo"] == "RE 1.141.156", t["1.016"]["processo"])
    checar("rg: cabeçalho de sessão virtual que cruza o mês",
           I.contexto_rg("TRIBUNAL PLENO – SESSÃO VIRTUAL DE 27.11 A 4.12.2026") ==
           ("Pauta da sessão virtual", "pauta da sessão virtual de 27/11 a 04/12", "2026-12-04"))
    checar("rg: seção desconhecida em caixa alta não herda o estágio anterior",
           I.contexto_rg("TEMAS COM MÉRITO REAFIRMADO") == ("", "", "")
           and I.contexto_rg("QUESTÃO CONSTITUCIONAL") is None and I.contexto_rg("RELATOR: Min. Fulano") is None)


# ------------------------------------------------------------------ 3. STJ
def t_stj():
    data, itens, cab = I.stj_html(fx("stj909.html", "rb").decode("cp1252"), 909)
    checar("stj909: 10 destaques e cabeçalho", len(itens) == 10 and cab and data == "10 de novembro de 2026", (len(itens), cab, data))
    rep = itens[1]
    checar("stj909: destaque do repetitivo com as 3 teses (antes só a 1ª)",
           rep["destaque"].startswith("1) É cabível a remição") and "2) A obtenção da pontuação mínima" in rep["destaque"]
           and "3) O acréscimo de 1/3" in rep["destaque"], rep["destaque"][:200])
    checar("stj909: processo com os dois REsp do repetitivo", rep["processo"].count("REsp") == 2, rep["processo"])
    checar("stj909: tipo/órgão/precedente", [(i["tipo"], i["orgao"], i["precedente"]) for i in itens[:4]] ==
           [("RQF", "Terceira Seção", "Tema 1403"), ("Repetitivo", "Terceira Seção", "Tema 1270"),
            ("Corte Especial", "Corte Especial", ""), ("Turma", "Primeira Turma", "")],
           [(i["tipo"], i["orgao"], i["precedente"]) for i in itens[:4]])
    checar("stj909: rótulo do índice", [I.linha_item("stj", i).split("]")[0] + "]" for i in itens[:4]] ==
           ["[RQF · Tema 1403 · Terceira Seção]", "[Repetitivo · Tema 1270 · Terceira Seção]", "[Corte Especial]",
            "[Primeira Turma]"], [I.linha_item("stj", i)[:60] for i in itens[:4]])
    checar("stj909: tema sem corte", all("…" not in i["tema"] for i in itens) and len(max((i["tema"] for i in itens), key=len)) > 220)
    _, itens, cab = I.stj_html(fx("stj910.html", "rb").decode("cp1252"), 910)
    checar("stj910: página sem o cabeçalho do número", not itens and not cab)
    _, itens, cab = I.stj_html(fx("stj912-layout-novo.html", "rb").decode("cp1252"), 912)
    checar("stj912: cabeçalho presente, 0 destaques (layout novo)", not itens and cab)
    checar("tipo_stj: Seção sem repetitivo", I.tipo_stj("Segunda Seção", "REsp 1-SP, Segunda Seção, julgado") ==
           ("Seção", "Segunda Seção", ""))


# ------------------------------------------------------------------ 4. historico e datas do anuncio
def t_historico():
    json.dump(JANELA, open(os.path.join(TMP, "janela.json"), "w"))
    h = I.historico()
    checar("historico: execução de hoje (ignorar_execucao) não conta", h["stf"][1236]["vazio"] and h["rg"][397]["vazio"])
    checar("historico: anunciada_em = 5º campo da chave; anunciada_na_edicao = data da execução",
           (h["rg"][397]["anunciada_em"], h["rg"][397]["anunciada_na_edicao"]) == ("2026-11-11", "2026-11-12")
           and h["stf"][1233]["anunciada_em"] == "2026-10-19", h["rg"][397])
    checar("historico: '-conteudo' vence o anúncio vazio (stj909)", h["stj"][909]["vazio"] is False)
    pub = I.publicados()
    checar("publicados(): formato antigo {produto: {numero: bool}} (usado pelo montador)",
           pub["stf"][1236] is True and pub["stf"][1235] is False and pub["stj"][909] is False)
    os.unlink(os.path.join(TMP, "janela.json"))
    checar("historico: sem janela.json a execução de hoje conta (1236 com conteúdo)", I.historico()["stf"][1236]["vazio"] is False)


# ------------------------------------------------------------------ 5. execucao completa (replay de 16/11)
def t_replay_1611():
    rede = Rede({"stf1236": [(200, "pdf")], "stf1237": [(404, b"")], "stf1238": [(403, b"<html>Error 403</html>")],
                 "rg397": [(200, "pdf")], "rg398": [(404, b"")], "rg399": [(404, b"")],
                 "stj910": [(200, "stj910.html")], "stj911": [(200, "stj910.html")],
                 "rg394": [(403, b"")], "stf1233": [(200, "pdf")]})
    json.dump({"conjur": {"status": "ok", "detalhe": "x", "script": "coleta_web.py"}},
              open(os.path.join(TMP, "fontes_status.json"), "w"))
    out, js, st = rodar(rede, janela=JANELA)
    r = por_id(js)
    checar("replay: 1238 (403 depois do 404 do 1237) não vira ERRO", "ERRO" not in out, out)
    checar("replay: SEM EDICAO do STF diz 'não verificável', sem código http",
           "SEM EDICAO NOVA INFORMATIVO STF (1237 ainda não publicada; 1238 não verificável)" in out.splitlines(), out)
    checar("replay: uma linha SEM EDICAO por produto",
           [l for l in out.splitlines() if l.startswith("SEM EDICAO")] ==
           ["SEM EDICAO NOVA INFORMATIVO STF (1237 ainda não publicada; 1238 não verificável)",
            "SEM EDICAO NOVA REPERCUSSAO GERAL EM PAUTA (398 ainda não publicada)",
            "SEM EDICAO NOVA INFORMATIVO STJ (910 ainda não publicada)"], out)
    checar("replay: STJ sem cabeçalho = ainda não publicada (sem ERRO PARSER)",
           r["stj910"]["estado"] == "inexistente" and "ERRO PARSER" not in out)
    checar("replay: sem 'chave=' e sem código http nas linhas do leitor",
           "chave=" not in out and not any(re.search(r"\bhttp\b|\b40[34]\b", l) for l in linhas_leitor(out)),
           [l for l in linhas_leitor(out) if re.search(r"\bhttp\b|\b40[34]\b", l)])
    checar("replay: bloco EM ATRASO com stf1236, rg397 e a revisita stf1233",
           "EM ATRASO —" in out and out.index("EM ATRASO —") < out.index("INFORMATIVO STF 1236 [id stf1236]")
           and "INFORMATIVO STF 1236 [id stf1236] (10 de novembro de 2026) — ATRASADA (anunciada em 10/11) — 4 destaques" in out
           and "REPERCUSSAO GERAL EM PAUTA 397 [id rg397] (4 a 9 de novembro de 2026) — ATRASADA (anunciada em 11/11) — 11 destaques" in out
           and "INFORMATIVO STF 1233 [id stf1233] (19 de outubro de 2026) — ATRASADA, revisita (anunciada em 19/10) — 4 destaques" in out,
           out)
    checar("replay: revisitas antigas = 2, as mais recentes primeiro (rg394 de 21/10, stf1233 de 19/10)",
           [p for p in rede.pedidos if p in ("rg394", "stf1233", "stf1231", "stf1230", "stj904", "stj903")] == ["rg394", "stf1233"],
           rede.pedidos)
    checar("replay: revisita que não abriu fica só na linha TECNICO",
           "rg394" not in "\n".join(linhas_leitor(out)) and "rg394=403(indeterminado, revisita)" in out, out)
    checar("replay: índice com '(com resumo)' e '(com tese)' e estágio",
           "  0 [Plenário] DIREITO ADMINISTRATIVO — Incidência do piso salarial" in out and "(com resumo)" in out
           and "  10 [pauta da sessão virtual de 06/11 a 13/11] Tema 1.338 — Cabimento de ação rescisória" in out
           and "[tese publicada · sem RG] Tema 1.487" in out and "(com tese)" in out, out)
    checar("replay: JSON — chave '-conteudo', anunciada_em, revisita, resumo e estagio",
           r["stf1236"]["chave"] == "stf|informativo|1236-conteudo|2026|2026-11-10"
           and r["stf1236"]["anunciada_em"] == "2026-11-10" and r["stf1236"]["anunciada_na_edicao"] == "2026-11-11"
           and r["rg397"]["anunciada_em"] == "2026-11-11" and r["stf1233"].get("revisita") is True
           and all(it.get("resumo") for it in r["stf1236"]["itens"]) and len(r["rg397"]["itens"]) == 11
           and r["rg397"]["itens"][10]["estagio"].startswith("pauta da sessão virtual"),
           {k: (v.get("chave"), v.get("anunciada_em")) for k, v in r.items()})
    checar("replay: estados no JSON", (r["stf1237"]["estado"], r["stf1238"]["estado"], r["rg394"]["estado"]) ==
           ("inexistente", "nao_verificavel", "indeterminado"))
    sl = [l for l in out.splitlines() if l.startswith("SOURCE_STATUS ")]
    ss = json.loads(sl[0][len("SOURCE_STATUS "):]) if sl else {}
    checar("replay: SOURCE_STATUS é a última linha, {id: status} (formato do coleta_web/versiculo)",
           len(sl) == 1 and out.rstrip().endswith(sl[0]) and ss == {"informativos_docs": "ok"}, sl)
    fs = (st or {}).get("informativos_docs") or {}
    checar("replay: fontes_status.json — ok, detalhe com a revisita que falhou, script e execution_id",
           fs.get("status") == "ok" and fs.get("script") == "informativos.py" and fs.get("execution_id") == "2026-11-16-7h"
           and "revisita sem abrir: rg394 http 403" in fs.get("detalhe", ""), fs)
    checar("replay: fontes_status.json mesclado (chave de outro script preservada)",
           st and st.get("conjur", {}).get("script") == "coleta_web.py", st)
    checar("replay: sem nova tentativa depois de 404 (nenhuma espera longa)", ESPERAS and max(ESPERAS) <= 1.5, ESPERAS)


# ------------------------------------------------------------------ 6. 403 sem 404 antes
def t_403():
    base = {"stf1236": [(200, "pdf")], "rg397": [(200, "pdf")], "stj910": [(200, "stj910.html")],
            "rg394": [(200, "pdf")], "stf1233": [(200, "pdf")]}
    rede = Rede(dict(base, stf1237=[(403, b""), (403, b"")]))
    out, js, st = rodar(rede, janela=JANELA)
    r = por_id(js)
    checar("403 sem 404: 1 nova tentativa, depois ERRO", rede.pedidos.count("stf1237") == 2 and r["stf1237"]["tentativas"] == 2
           and any(l.startswith("ERRO INFORMATIVO STF 1237 [id stf1237]: documento não abriu") for l in out.splitlines()),
           (rede.pedidos, out))
    checar("403 sem 404: ERRO sem código http e com instrução de não reportar sem e-mail",
           "não cite nem reporte ao leitor" in out and not any(re.search(r"\b403\b", l) for l in linhas_leitor(out)))
    checar("403 sem 404: espera antes da nova tentativa", 0 in ESPERAS)
    checar("403 sem 404: não sonda 1238 nem imprime SEM EDICAO do STF",
           "stf1238" not in rede.pedidos and "SEM EDICAO NOVA INFORMATIVO STF" not in out)
    checar("403 sem 404: SOURCE_STATUS falha", st["informativos_docs"]["status"] == "falha"
           and "stf1237 http 403" in st["informativos_docs"]["detalhe"], st)
    rede = Rede(dict(base, stf1237=[(403, b""), (200, "pdf")]))
    I_PDF = dict(PDF)
    PDF["stf1237"] = "stf1233-layout.txt"
    try:
        out, js, st = rodar(rede, janela=JANELA)
    finally:
        PDF.clear(); PDF.update(I_PDF)
    r = por_id(js)
    checar("403 e depois 200: edição nova aberta na 2ª tentativa", r["stf1237"]["ok"] and r["stf1237"]["tentativas"] == 2
           and r["stf1237"]["chave"].startswith("stf|informativo|1237|") and "INFORMATIVO STF 1237 [id stf1237]" in out
           and st["informativos_docs"]["status"] == "ok", out)
    # orcamento de novas tentativas: no maximo MAX_RETENTATIVAS por execucao
    rede = Rede(dict(base, stf1237=[(0, b"")], rg398=[(403, b"")], stj910=[(0, b"")]))
    out, js, st = rodar(rede, janela=JANELA)
    checar("orçamento: no máximo 2 novas tentativas por execução",
           sum(1 for r in js if r.get("tentativas") == 2) == 2 and rede.pedidos.count("stj910") == 1, rede.pedidos)


# ------------------------------------------------------------------ 7. parser do STJ, 404 na revisita, pulada
def t_parser_e_404():
    layout_novo_910 = fx("stj912-layout-novo.html", "rb").replace(b"912", b"910")
    rede = Rede({"stf1236": [(200, "pdf")], "rg397": [(404, b"")], "stj910": [(200, layout_novo_910)],
                 "stf1233": [(200, "pdf")], "stj904": [(200, "stj910.html")]})
    out, js, st = rodar(rede, janela=JANELA)
    r = por_id(js)
    checar("STJ: cabeçalho do número com 0 destaques vira ERRO PARSER",
           r["stj910"]["estado"] == "parser" and any(l.startswith("ERRO PARSER INFORMATIVO STJ 910 [id stj910]") for l in out.splitlines())
           and "SEM EDICAO NOVA INFORMATIVO STJ" not in out and st["informativos_docs"]["status"] == "falha", out)
    checar("revisita: parar no 404 (rg397 404 -> rg394 não é pedida; vagas vão para stf1233 de 19/10 e stj904 de 06/10)",
           "rg394" not in rede.pedidos
           and [p for p in rede.pedidos if p in ("stf1233", "stj904", "stf1231")] == ["stf1233", "stj904"],
           rede.pedidos)
    # edicao pulada (base-1 ausente do historico) que da 404: so na linha TECNICO
    hist = {"stf": {1236: {"vazio": False, "anunciada_em": "2026-11-10", "anunciada_na_edicao": "2026-11-11"}},
            "rg": {}, "stj": {}}
    rede = Rede({"stf1235": [(404, b"")]})
    I.baixar = rede.baixar
    res = I.coletar(hist)
    saida = io.StringIO()
    with contextlib.redirect_stdout(saida):
        I.imprimir(res)
    out = saida.getvalue()
    checar("pulada com 404 não pede para citar; produto sem histórico avisa",
           "SEGUE SEM CONTEUDO" not in out and "stf1235=404(inexistente)" in out
           and "SEM EDICAO NOVA REPERCUSSAO GERAL EM PAUTA (nenhuma edição no histórico" in out, out)


# ------------------------------------------------------------------ 7b. revisita: temas em votacao/pauta superados
JANELA_1711 = {"ignorar_execucao": "2026-11-17-7h", "execution_id": "2026-11-17-7h"}


def t_superados():
    json.dump(JANELA_1711, open(os.path.join(TMP, "janela.json"), "w"))
    h = I.historico()["rg"]
    _, itens = I.rg_texto(fx("rg394.txt"))
    m = I.superados_por_data(394, itens, h)
    checar("superados: RG 394 com 3 boletins posteriores — os 5 em votação/pauta (até 23/10) saem",
           sorted(itens[i]["tema"] for i in m) == sorted(["1.493", "1.494", "118", "488", "1.308"])
           and all("boletins seguintes (395 a 397)" in v for v in m.values()), {itens[i]["tema"]: v for i, v in m.items()})
    checar("superados: com 1 só boletim posterior nada sai (o resultado pode não ter saído ainda)",
           I.superados_por_data(396, I.rg_texto(fx("rg396.txt"))[1], h) == {}
           and I.superados_por_data(397, I.rg_texto(fx("rg397.txt"))[1], h) == {})
    tardio = dict(itens[5], previsao="2026-11-05", estagio="em votação no PV até 05/11")
    checar("superados: previsão depois do anúncio da penúltima posterior (03/11) fica",
           I.superados_por_data(394, [tardio, dict(itens[5], previsao="")], h) == {1: m[5]})
    checar("superados: tema com tese ou com desfecho nunca é superado",
           not any(itens[i]["tese"] or not I.PENDENTE_RG.match(itens[i]["estagio"]) for i in m))
    # replay de 17/11: historico com a execucao de 16/11, revisitas rg394 (texto real) e stf1233
    PDF_ANTES = dict(PDF)
    PDF["rg394"] = "rg394.txt"
    try:
        rede = Rede({"rg394": [(200, "pdf")], "stf1233": [(200, "pdf")]})
        out, js, st = rodar(rede, janela=JANELA_1711)
    finally:
        PDF.clear(); PDF.update(PDF_ANTES)
    r = por_id(js)
    rg = r.get("rg394") or {}
    checar("replay 17/11: RG 394 sai com 8 destaques; os 5 superados fora do índice, numa linha só",
           "REPERCUSSAO GERAL EM PAUTA 394 [id rg394] (14 a 19 de outubro de 2026) — ATRASADA, revisita (anunciada em 21/10) — 8 destaques" in out
           and "  fora do e-mail — em votação/pauta nesta edição; situação superada pelos boletins seguintes (395 a 397): "
               "Temas 1.493, 1.494, 118, 488, 1.308" in out.splitlines()
           and not re.search(r"(?m)^  \d+ \[(em votação|pauta)", out), out)
    checar("replay 17/11: JSON — itens sem os superados; itens_superados com superado/superado_motivo; chave -conteudo",
           rg.get("ok") and len(rg["itens"]) == 8 and [it["tema"] for it in rg.get("itens_superados", [])] ==
           ["1.493", "1.494", "118", "488", "1.308"] and all(it["superado"] is True and it["superado_motivo"]
                                                           for it in rg["itens_superados"])
           and rg["chave"] == "stf|informativo|repercussao-geral-394-conteudo|2026|2026-10-19"
           and not any(I.pendente_rg(it) for it in rg["itens"]), rg.get("chave"))
    checar("replay 17/11: TECNICO conta os superados; fonte ok",
           "rg394=200(5 superados, revisita)" in out and st["informativos_docs"]["status"] == "ok", out)
    try:
        import montar_email
        import datetime
        html_rg = " ".join(montar_email.destaques_html("rg", rg["itens"], datetime.date(2026, 11, 17)))
        checar("replay 17/11: o montador não escreve 'resultado no próximo boletim' na RG 394",
               "próximo boletim" not in html_rg and "Tema 118" not in html_rg and "Tema 1.016" in html_rg, html_rg[:300])
    except ImportError as e:
        print("AVISO   montar_email não importou (%s) — conferência do HTML pulada" % e)
    # obter() sem historico (segunda_tentativa do montador, modo manual): le o historico sozinho
    PDF["rg394"] = "rg394.txt"
    try:
        I.baixar = Rede({"rg394": [(200, "pdf")]}).baixar
        r1 = I.obter("rg", 394, "atrasada")
    finally:
        PDF.clear(); PDF.update(PDF_ANTES)
    checar("obter() sem hist_produto também separa os superados", r1["ok"] and len(r1["itens"]) == 8
           and len(r1["itens_superados"]) == 5, (len(r1.get("itens") or []), r1.get("estado")))
    # todos superados: estado 'superada', sem chave, so na linha TECNICO, nao derruba a fonte
    r2 = I.aplicar_superados(dict(r1, itens=list(r1["itens"]), itens_superados=[], chave="x", revisita=True),
                             {i: "teste" for i in range(len(r1["itens"]))})
    saida = io.StringIO()
    with contextlib.redirect_stdout(saida):
        I.imprimir([r2])
    out2 = saida.getvalue()
    checar("todos superados: estado superada, sem chave, só na linha TECNICO, fonte ok",
           (r2["ok"], r2["estado"], "chave" in r2, len(r2["itens"]), len(r2["itens_superados"])) == (False, "superada", False, 0, 8)
           and [l for l in out2.splitlines() if "rg394" in l] == ["TECNICO informativos: rg394=200(superada, 8 superados, revisita)"]
           and I.status_fonte([r2])["status"] == "ok" and "superadas: rg394" in I.status_fonte([r2])["detalhe"], out2)
    # mesma execucao: tema da RG herdada que tambem esta numa RG posterior aberta agora
    _, i397 = I.rg_texto(fx("rg397.txt"))
    _, i394 = I.rg_texto(fx("rg394.txt"))
    res = [{"tipo": "rg", "numero": 397, "id": "rg397", "ok": True, "situacao": "atrasada", "itens": list(i397)},
           {"tipo": "rg", "numero": 394, "id": "rg394", "ok": True, "situacao": "atrasada", "revisita": True,
            "itens": list(i394)},
           {"tipo": "rg", "numero": 398, "id": "rg398", "ok": True, "situacao": "nova", "itens": [dict(i397[0])]}]
    I.deduplicar_temas(res)
    a, b, c = res[0], res[1], res[2]
    checar("mesma execução: Tema 1.483 só na RG mais recente (398 > 397 > 394); a nova fica inteira",
           [it["tema"] for it in a.get("itens_superados", [])] == ["1.483"]
           and "1.483" not in [it["tema"] for it in b["itens"]] and len(c["itens"]) == 1
           and b["itens_superados"][0]["superado_motivo"] == "tema também na RG 398, aberta nesta execução",
           (a.get("itens_superados"), b.get("itens_superados")))
    # campo opcional `temas` no item do historico (gravado pelo montador): tema ja publicado com RG posterior
    hdir = tempfile.mkdtemp(prefix="hist-", dir=TMP)
    base_h = json.load(open(os.path.join(FIX, "historico", "resumo-legislativo-historico.json"), encoding="utf-8"))
    for e in base_h["executions"]:
        for it in e.get("items") or []:
            if it.get("chave", "").startswith("stf|informativo|repercussao-geral-397-conteudo"):
                it["temas"] = ["1.483", "1.487"]
            if it.get("chave", "").startswith("stf|informativo|repercussao-geral-397|"):
                it["temas"] = ["9.999"]              # anuncio vazio: nao conta
    json.dump(base_h, open(os.path.join(hdir, "resumo-legislativo-historico.json"), "w", encoding="utf-8"))
    aqui = I.AQUI
    I.AQUI = hdir
    try:
        h2 = I.historico()["rg"]
        PDF["rg394"] = "rg394.txt"
        I.baixar = Rede({"rg394": [(200, "pdf")]}).baixar
        r3 = I.obter("rg", 394, "atrasada")
    finally:
        I.AQUI = aqui
        PDF.clear(); PDF.update(PDF_ANTES)
    checar("historico: campo `temas` lido só do registro com conteúdo", h2[397].get("temas") == {
        "1.483": "2026-11-16", "1.487": "2026-11-16"} and "temas" not in h2[396], h2[397])
    checar("histórico com `temas`: Tema 1.483 (saiu com a RG 397 em 16/11) fica fora da RG 394",
           len(r3["itens"]) == 7 and "1.483" not in [it["tema"] for it in r3["itens"]]
           and {it["tema"]: it["superado_motivo"] for it in r3["itens_superados"]}.get("1.483")
           == "tema já publicado com a RG 397 em 16/11", [(it["tema"], it["superado_motivo"]) for it in r3["itens_superados"]])
    checar("histórico sem `temas` (formato atual): nada muda", I.superados_por_historico(394, i394, h) == {})
    os.unlink(os.path.join(TMP, "janela.json"))


# ------------------------------------------------------------------ 8. modo manual, indice e compatibilidade
def t_manual_e_compat():
    try:
        os.unlink(os.path.join(TMP, "fontes_status.json"))
    except FileNotFoundError:
        pass
    rede = Rede({"stf1233": [(200, "pdf")]})
    out, js, st = rodar(rede, argv=["stf:1233"])
    checar("manual: edição dada é lida; fontes_status.json não é gravado",
           js[0]["ok"] and js[0]["situacao"] == "nova" and st is None and "SOURCE_STATUS " in out)
    checar("ROBOZINHO_TMP: informativos.json gravado na pasta indicada", os.path.exists(os.path.join(TMP, "informativos.json")))
    it = {"secao": "Plenário", "ramo": "DIREITO", "titulo": "x"}
    r = {"tipo": "stf", "numero": 1, "id": "stf1", "data": "d", "situacao": "nova", "itens": [it] * 30}
    saida = io.StringIO()
    with contextlib.redirect_stdout(saida):
        I.imprimir_edicao(r)
    checar("índice: teto de %d linhas só na impressão" % I.MAX_INDICE,
           len(re.findall(r"(?m)^  \d+ ", saida.getvalue())) == I.MAX_INDICE and "+5 destaques só no JSON (índices 25 a 29)" in saida.getvalue())
    # o montador (outro grupo) continua lendo os campos antigos; teste brando: so falha por KeyError nos nossos itens
    try:
        import montar_email
    except Exception as e:  # noqa: BLE001
        print("AVISO   montar_email não importou (%s) — compatibilidade não conferida" % e)
        return
    _, stf_i = I.stf_texto(fx("stf1236-layout.txt"))
    _, rg_i = I.rg_texto(fx("rg397.txt"))
    _, stj_i, _ = I.stj_html(fx("stj909.html", "rb").decode("cp1252"), 909)
    erro = None
    try:
        for tipo, lista in (("stf", stf_i), ("rg", rg_i), ("stj", stj_i)):
            for d in lista:
                montar_email.texto_destaque(tipo, d)
    except KeyError as e:
        erro = e
    checar("montar_email.texto_destaque aceita os itens novos (campos antigos presentes)", erro is None, erro)


def main():
    try:
        for t in (t_stf_resumo, t_rg, t_stj, t_historico, t_replay_1611, t_403, t_parser_e_404, t_superados,
                  t_manual_e_compat):
            try:
                t()
            except Exception as e:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                checar("%s sem exceção" % t.__name__, False, e)
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print("%s: %d de %d" % ("FALHOU" if FALHAS else "OK", TOTAL[0] - len(FALHAS), TOTAL[0]))
    sys.exit(1 if FALHAS else 0)


if __name__ == "__main__":
    main()
