#!/usr/bin/env python3
# =====================================================================
# test_informativos.py — testes do work/informativos.py, sem rede e sem pytest.
#   python3 work/testes/test_informativos.py      -> OK/FALHOU por teste; codigo != 0 em falha
# Fixtures (texto, extraidos dos documentos oficiais reais, em fixtures/informativos/):
#   stf1236/1233/1234-layout.txt          pdftotext -layout do Informativo STF (sumario + caixas RESUMO)
#   stf1231-layout.txt                      idem, edicao 1231 (titulos cuja ultima linha e so o processo)
#   rg397/396/394.txt                       pdftotext da RG em Pauta 397 (11 temas), 396 (9) e 394 (13)
#   stj909.html                             pagina do Informativo STJ 909 (inteiro teor reduzido)
#   stj910.html                             pagina de edicao inexistente (sem o cabecalho do numero)
#   stj910-publicada.html                   pagina real do Informativo STJ 910 (17/11/2026), reduzida ao texto
#                                           das notas: 17 notas, 5 afetacoes (PROPOSTA DE RELEVANCIA DA QUESTAO
#                                           FEDERAL, sem "Destaque") e o tema no formato novo "( Tema repetitivo N )"
#   stj912-layout-novo.html                 sintetica: cabecalho presente, rotulos desconhecidos
#   historico/resumo-legislativo-historico.json  sintetico, com as edicoes vazias reais de set-nov/2026
#   historico-real-1611/resumo-legislativo-historico.json  os itens reais stf|stj informativo das execucoes
#                                           ate 16/11/2026, copiados sem alteracao (o P6 lia o historico vivo
#                                           e ficou vermelho em 18/11, quando a RG 394 ganhou conteudo)
# Os downloads sao simulados (informativos.baixar/pdf_texto trocados); tudo o que o script grava vai
# para um ROBOZINHO_TMP temporario.
# Fixture nova nesta pasta precisa de `git add` explicito no commit: um `git commit -a` deixa de fora
# o que o git ainda nao conhece. O 1o teste confere a presenca de todas (FIXTURES) e, num clone com
# .git, imprime "AVISO   fixture fora do git: ..." (aviso, nao falha) para cada uma ainda nao versionada.
# =====================================================================

import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.dirname(AQUI)
FIX = os.path.join(AQUI, "fixtures", "informativos")
sys.path.insert(0, WORK)

TMP = tempfile.mkdtemp(prefix="robozinho-inf-")
os.environ["ROBOZINHO_TMP"] = TMP
os.environ["ROBOZINHO_INF_ESPERA"] = "0"
os.environ["ROBOZINHO_INF_CACHE"] = "0"    # o cache de PDFs da execucao so e ligado no teste dele (t_waf)

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


# todas as fixtures usadas neste arquivo (caminhos relativos a FIX)
FIXTURES = ("stf1231-layout.txt", "stf1233-layout.txt", "stf1234-layout.txt", "stf1236-layout.txt",
            "rg394.txt", "rg396.txt", "rg397.txt", "stj909.html", "stj910.html", "stj912-layout-novo.html",
            "stj910-publicada.html", os.path.join("historico", "resumo-legislativo-historico.json"),
            os.path.join("historico-real-1611", "resumo-legislativo-historico.json"))


def t_fixtures():
    faltam = [n for n in FIXTURES if not os.path.isfile(os.path.join(FIX, n))]
    checar("fixtures: todas presentes em work/testes/fixtures/informativos/", not faltam,
           "faltam %s (arquivo novo que ficou fora do commit? `git add work/testes/fixtures/informativos/`)"
           % ", ".join(faltam))
    # aviso, nao falha: fixture que o git ainda nao conhece some num `git commit -a`
    repo = os.path.dirname(WORK)
    if not os.path.exists(os.path.join(repo, ".git")):
        return   # copia sem .git (sandbox): nada a conferir
    try:
        r = subprocess.run(["git", "-C", repo, "ls-files", "--others", "--exclude-standard", "--",
                            os.path.relpath(FIX, repo)], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return
    if r.returncode != 0:
        return
    for caminho in (l.strip() for l in r.stdout.splitlines()):
        if caminho:
            print("AVISO   fixture fora do git: %s (um `git commit -a` a deixa de fora; `git add %s` no commit)"
                  % (caminho, caminho))


# ------------------------------------------------------------------ downloads simulados
PDF = {"stf1236": "stf1236-layout.txt", "stf1233": "stf1233-layout.txt", "rg397": "rg397.txt",
       "rg394": "rg397.txt"}


def url_id(url):
    url = url.replace(I.HOSTS_STF[1], I.HOSTS_STF[0], 1)      # host alternativo do STF: o mesmo documento
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
        self.urls = []

    def baixar(self, url):
        rid = url_id(url)
        self.pedidos.append(rid)
        self.urls.append(url)
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
    _, itens = I.stf_texto(fx("stf1233-layout.txt"))
    checar("stf1233[1]: continuação '– ADI 7.901/PR ....7' (travessão + processo) entra no título",
           itens[1]["titulo"] == "Período mínimo de gratuidade em estacionamentos privados para pessoas com deficiência "
                                 "– ADI 7.901/PR", itens[1]["titulo"])
    checar("PROCESSO_STF: classe processual + número (com travessão opcional); palavra-chave 'LEI 8.112/1990' não",
           all(I.PROCESSO_STF.match(s) for s in ("ADI 7.069/GO ....7", "– ADI 7.901/PR ....7", "RE 990.115/SP",
                                                "ADPF 1.234/DF", "HC 245.678/SP"))
           and not any(I.PROCESSO_STF.match(s) for s in ("LEI 8.112/1990; SERVIDOR PÚBLICO", "IMPOSTOS; ICMS",
                                                        "EC Nº 29/2000", "REPARTIÇÃO DE COMPETÊNCIAS")))
    sint = ("SUMÁRIO\n\nDIREITO TRIBUTÁRIO\n IMPOSTOS; ICMS\n\n » Título que acaba no travessão –\n"
            "   ADI 1.234/SP ..........5\n IMPOSTOS; IPTU\n\nEdição 1/2026\n")
    _, itens = I.stf_texto(sint)
    checar("stf: palavra-chave em maiúsculas logo depois do título continua fora dele",
           [it["titulo"] for it in itens] == ["Título que acaba no travessão – ADI 1.234/SP"], itens)
    t_stf_titulo_processo_1231()


def t_stf_titulo_processo_1231():
    # funcao propria: se a fixture faltar, so estas verificacoes caem (as demais do STF rodam)
    try:
        texto = fx("stf1231-layout.txt")
    except OSError as e:
        checar("stf1231: fixture legível", False, e)
        return
    # linha de continuacao so com o processo, toda em maiusculas (antes descartada: "Polícia Penal –.")
    data, itens = I.stf_texto(texto)
    tit = [it["titulo"] for it in itens]
    checar("stf1231: título que termina em '–' ganha o processo da linha seguinte (ADI 7.069/GO, ADI 7.935/ES)",
           data == "05 de outubro de 2026" and len(itens) == 6
           and tit[1] == "Contratação de agentes temporários para o desempenho de atribuições da Polícia Penal – ADI 7.069/GO"
           and tit[5] == "Majoração de custas judiciais no Estado do Espírito Santo e anterioridade nonagesimal – ADI 7.935/ES"
           and not any(t.rstrip().endswith(("–", "-")) for t in tit), tit)
    checar("stf1231: lista de processos com minúscula ('e') e os 6 resumos validados",
           tit[3].endswith("– ADI 7.822/SP, ADI 7.830/SP, ADI 7.844/SP e ADI 7.848/SP")
           and [bool(it.get("resumo")) for it in itens] == [True] * 6, (tit[3], [len(it.get("resumo", "")) for it in itens]))
    t_stf_resumo_sem_linha_em_branco(texto, itens)


def t_stf_resumo_sem_linha_em_branco(texto, itens):
    """20/11/2026: na ADI 7.495 (STF 1231) a caixa RESUMO nao terminava em linha em branco (a coluna das
    palavras-chave seguia ao lado) e o "No caso, ..." (recuo 37, corpo na 41) puxava a coluna para 37: o resumo
    engolia a nota (2.559 caracteres), era recusado e a tese nao saia."""
    r0 = itens[0].get("resumo") or ""
    checar("stf1231[0]: RESUMO da ADI 7.495 inteiro e só ele (para antes do 'No caso')",
           r0.startswith("A licença-maternidade deve ser assegurada de forma isonômica às mães biológicas e adotantes")
           and r0.endswith("vínculo laboral ou funcional da beneficiária.") and "No caso" not in r0 and len(r0) == 214, r0)
    # a rede sozinha: sem a regra do recuo (linhas do corpo todas na mesma coluna), o texto acima de RESUMO_MAX
    # e cortado antes do "No caso"
    corpo = (["                    A tese em uma frase curta que termina aqui, com mais de cem caracteres para "
              "passar no mínimo do resumo."]
             + ["                    No caso, foram questionadas normas que " + "x" * 60 + "."] * 15)
    s = I.corpo_resumo(corpo)
    checar("corpo_resumo: acima de RESUMO_MAX, corta antes de '. No caso' (rede)",
           s.endswith("passar no mínimo do resumo.") and I.resumo_valido(s), s[:200])
    longo = ["                    " + ("Frase longa do resumo que segue sem a expressão de corte " * 2) + "."] * 12
    checar("corpo_resumo: sem a expressão de corte, o texto longo fica longo (recusado; sai só o título)",
           not I.resumo_valido(I.corpo_resumo(longo)))
    # a perda fica na linha TECNICO (antes: '6 de 6 destaques publicados' e nada no TECNICO)
    PDF["stf1231"] = "stf1231-layout.txt"
    t2 = texto.replace("ou funcional da beneficiária.", "ou funcional da beneficiária", 1)
    velho = I.pdf_texto
    try:
        I.pdf_texto = lambda dados, layout: t2
        I.baixar = Rede({"stf1231": [(200, "pdf")]}).baixar
        r = I.obter("stf", 1231, "nova")
    finally:
        I.pdf_texto = velho
        PDF.pop("stf1231", None)
    saida = io.StringIO()
    with contextlib.redirect_stdout(saida):
        I.imprimir([r])
    checar("TECNICO: resumo recusado aparece (stf1231=200(resumo 5/6; recusados: 0 (N car.)))",
           r.get("resumos", "").startswith("5/6; recusados: 0 (") and "stf1231=200(resumo 5/6; recusados: 0 (" in saida.getvalue(),
           (r.get("resumos"), saida.getvalue()[-200:]))


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
    checar("rg394: número quebrado em duas linhas ('ARE 1.487.739-' + 'ED-segundos') reunido; os outros iguais",
           t["1.308"]["processo"] == "ARE 1.487.739-ED-segundos" and t["488"]["processo"] == "RE 646.104ED-ED-ED"
           and t["1.483"]["processo"] == "RE 1.616.922; RE 1.616.090"
           and t["1.308"]["titulo"].startswith("Incidência do piso salarial"), t["1.308"]["processo"])
    try:
        import montar_email
        checar("rg394: o montador mostra o processo inteiro do Tema 1.308",
               montar_email._tema_rg(t["1.308"]) == "<b>Tema 1.308</b> (ARE 1.487.739-ED-segundos)",
               montar_email._tema_rg(t["1.308"]))
    except (ImportError, AttributeError) as e:
        print("AVISO   montar_email._tema_rg indisponível (%s) — conferência pulada" % e)
    sint = ("PAUTA DO PLENÁRIO\nTEMA: 1 PROCESSOS: RE 1.000.001- RELATOR: Min. Fulano\nED-ED-ED\nTítulo: Um.\n"
            "TEMA: 2 PROCESSOS: RE 1.000.002/\nSP RELATORA: Min. Fulana\nRE 1.000.003\nTítulo: Dois.\n"
            "TEMA: 3 PROCESSOS: RE 1.000.004-\nRELATOR: Min. Beltrano\nTítulo: Três.\n"
            "TEMA: 4 PROCESSOS: RE 1.000.005-\nTítulo: Quatro.\n")
    _, it = I.rg_texto(sint)
    checar("rg: sufixo quebrado em maiúsculas não vira seção; RELATOR e 'Título:' depois do '-' não entram no processo",
           [(x["tema"], x["processo"], x["estagio"], x["titulo"]) for x in it] ==
           [("1", "RE 1.000.001-ED-ED-ED", "pauta do Plenário", "Um."),
            ("2", "RE 1.000.002/SP; RE 1.000.003", "pauta do Plenário", "Dois."),
            ("3", "RE 1.000.004-", "pauta do Plenário", "Três."), ("4", "RE 1.000.005-", "pauta do Plenário", "Quatro.")],
           [(x["tema"], x["processo"], x["estagio"], x["titulo"]) for x in it])
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
    t_stj_910_publicada()


def t_stj_910_publicada():
    """17/11/2026 (Informativo STJ 910): 17 notas; as 5 da secao nova PROPOSTA DE RELEVÂNCIA DA QUESTÃO FEDERAL
    (afetacao, sem 'Destaque') eram descartadas e o e-mail dizia '12 de 12 destaques publicados'; o tema mudou de
    formato ('( Tema repetitivo 1180 )', '(Tema de Relevância 1334)') e o cabecalho saia 'Repetitivo · ramo'."""
    try:
        pagina = fx("stj910-publicada.html", "rb")
    except OSError as e:
        checar("stj910-publicada: fixture legível", False, e)
        return
    info = {}
    data, itens, cab = I.stj_html(pagina.decode("cp1252"), 910, info)
    afet = [i for i in itens if i["tipo"] == "Afetação"]
    checar("stj910: 17 notas lidas, 5 afetações (Temas de Relevância 1480, 1481, 1483, 1484 e 1485)",
           len(itens) == 17 and info.get("notas") == 17 and cab and data == "17 de novembro de 2026"
           and sorted(i["precedente"] for i in afet) == ["Tema 1480", "Tema 1481", "Tema 1483", "Tema 1484", "Tema 1485"],
           (len(itens), info, [(i["tipo"], i["precedente"]) for i in itens]))
    a = next(i for i in afet if i["precedente"] == "Tema 1484")
    checar("stj910: afetação — o destaque é a controvérsia da nota; órgão, ramo e processo lidos",
           a["destaque"].startswith("A Corte Especial acolheu a proposta de submissão do REsp 2.263.604-SP")
           and "impenhorabilidade da quantia de até 40 (quarenta) salários mínimos" in a["destaque"]
           and a["orgao"] == "Corte Especial" and a["ramo"] == "DIREITO DO TRABALHO, DIREITO PROCESSUAL CIVIL"
           and a["processo"].startswith("ProRQF no REsp 2.263.604-SP, Rel. Ministra"), a)
    checar("stj910: tema no formato novo — '( Tema repetitivo 1180 )' e '(Tema de Relevância 1334)'",
           (itens[0]["tipo"], itens[0]["precedente"]) == ("Repetitivo", "Tema 1180")
           and any((i["tipo"], i["precedente"]) == ("RQF", "Tema 1334") for i in itens)
           and not any(i["tipo"] in ("Repetitivo", "RQF", "Afetação") and not i["precedente"] for i in itens),
           [(i["tipo"], i["precedente"]) for i in itens])
    checar("stj910: rótulo do índice da afetação",
           I.linha_item("stj", a).startswith("[Afetação · Tema 1484 · Corte Especial] DIREITO DO TRABALHO"), I.linha_item("stj", a))
    t1352 = next(i for i in itens if i["precedente"] == "Tema 1352")
    checar("stj910: processos que só diferem no número numa linha só (Tema 1352: 4 REsps)",
           t1352["processo"] == "REsp 2.189.004-SP, REsp 2.188.858-SP, REsp 2.188.859-SP e REsp 2.171.338-SP, Rel. "
                                "Ministro Paulo Sérgio Domingues, Primeira Seção, por unanimidade, julgado em 11/11/2026 "
                                "(Tema repetitivo 1352).", t1352["processo"])
    checar("processo_stj: linha repetida sai uma vez (904: REsp 2.250.086-SP duas vezes); resto diferente não junta",
           I.processo_stj(["REsp 1-SP , Rel. X, julgado em 1/1/2026 ( Tema 1 ).", "REsp 1-SP , Rel. X, julgado em 1/1/2026 ( Tema 1 )."])
           == "REsp 1-SP, Rel. X, julgado em 1/1/2026 (Tema 1)."
           and I.processo_stj(["REsp 1-SP, Rel. X, julgado em 1/1/2026.", "REsp 2-RJ, Rel. Y, julgado em 1/1/2026."])
           == "REsp 1-SP, Rel. X, julgado em 1/1/2026. REsp 2-RJ, Rel. Y, julgado em 1/1/2026."
           and I.processo_stj(["Processo em segredo de justiça, Rel. X."]) == "Processo em segredo de justiça, Rel. X."
           and I.processo_stj(["AgInt nos EDcl no AREsp 1-SP, Rel. X.", "AgInt nos EDcl no AREsp 2-SP, Rel. X."])
           == "AgInt nos EDcl no AREsp 1-SP e AgInt nos EDcl no AREsp 2-SP, Rel. X.")
    t1469 = next(i for i in itens if i["precedente"] == "Tema 1469")
    checar("stj910: índice sem o ramo (Tema 1469) não deixa '  — ' solto",
           I.linha_item("stj", t1469).startswith("[Repetitivo · Tema 1469 · Primeira Seção] Exigência de regularidade"),
           I.linha_item("stj", t1469)[:90])
    try:
        import montar_email as M
        html_a = M.texto_destaque("stj", a)
        sem_ramo = next(i for i in itens if i["precedente"] == "Tema 1469")
        html_r = M.texto_destaque("stj", sem_ramo)
        checar("montador: cabeçalho 'Afetação · Tema 1484' · ramo — controvérsia, processo em itálico",
               html_a.startswith("<b>Afetação · Tema 1484</b> · Direito do Trabalho, Direito Processual Civil — A Corte "
                                 "Especial acolheu") and "<i>ProRQF no REsp 2.263.604-SP" in html_a, html_a[:160])
        checar("montador: sem o ramo (Tema 1469), sem o separador solto ('Repetitivo · — i)')",
               not sem_ramo["ramo"] and html_r.startswith("<b>Repetitivo · Tema 1469</b> — i) Nos termos"), html_r[:120])
        checar("montador: Turma sem ramo nem órgão não abre com '<b></b>'",
               M.texto_destaque("stj", {"tipo": "", "ramo": "", "orgao": "", "destaque": "Tese.", "processo": ""}) == "Tese.")
    except ImportError as e:
        print("AVISO   montar_email não importou (%s) — conferência do HTML pulada" % e)
    # guarda: nota que o parser nao le aparece na linha TECNICO ("k de N notas lidas")
    sem_destaque = pagina.replace(b"<p>Destaque</p>", b"<p>Destaque removido</p>", 1)
    rede = Rede({"stj910": [(200, sem_destaque)]})
    I.baixar = rede.baixar
    r = I.obter("stj", 910, "nova")
    saida = io.StringIO()
    with contextlib.redirect_stdout(saida):
        I.imprimir([r])
    checar("guarda: nota sem 'Destaque' fora de seção de afetação não some em silêncio — TECNICO '16 de 17 notas lidas'",
           r["ok"] and len(r["itens"]) == 16 and r.get("notas") == 17 and "stj910=200(16 de 17 notas lidas)" in saida.getvalue(),
           (len(r.get("itens") or []), r.get("notas"), saida.getvalue()[-160:]))
    rede = Rede({"stj910": [(200, pagina)]})
    I.baixar = rede.baixar
    r = I.obter("stj", 910, "nova")
    checar("guarda: todas as notas lidas -> sem 'notas' no registro (nada a acusar)", r["ok"] and "notas" not in r, r.get("notas"))


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
    checar("replay: revisitas antigas = 2 do STF/RG, as mais recentes primeiro (rg394 de 21/10, stf1233 de 19/10), "
           "e a do STJ na vaga própria (stj904 de 06/10; 404 para o STJ: o stj903 não é pedido)",
           [p for p in rede.pedidos if p in ("rg394", "stf1233", "stf1231", "stf1230", "stj904", "stj903")]
           == ["rg394"] * I.MAX_TENTATIVAS_REVISITA + ["stf1233", "stj904"], rede.pedidos)
    checar("replay: revisita que não abriu fica só na linha TECNICO",
           "rg394" not in "\n".join(linhas_leitor(out))
           and "rg394=403(indeterminado, %d tentativas, 1a=403, revisita)" % I.MAX_TENTATIVAS_REVISITA in out, out)
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
    checar("403 sem 404: insiste até MAX_TENTATIVAS pedidos, depois ERRO",
           rede.pedidos.count("stf1237") == I.MAX_TENTATIVAS and r["stf1237"]["tentativas"] == I.MAX_TENTATIVAS
           and r["stf1237"]["http_1a_tentativa"] == 403
           and any(l.startswith("ERRO INFORMATIVO STF 1237 [id stf1237]: documento não abriu") for l in out.splitlines()),
           (rede.pedidos, out))
    checar("403 sem 404: os pedidos alternam www.stf.jus.br e portal.stf.jus.br (o mesmo documento)",
           [u.split("/")[2] for u in rede.urls if "Informativo_stf_1237" in u][:4]
           == ["www.stf.jus.br", "portal.stf.jus.br", "www.stf.jus.br", "portal.stf.jus.br"], rede.urls)
    checar("403 sem 404: linha TECNICO com o número de tentativas",
           "stf1237=403(indeterminado, %d tentativas, 1a=403)" % I.MAX_TENTATIVAS in out, out)
    checar("403 sem 404: ERRO sem código http e com instrução de não reportar sem e-mail",
           "não cite nem reporte ao leitor" in out and not any(re.search(r"\b403\b", l) for l in linhas_leitor(out)))
    checar("403 sem 404: espera entre as tentativas", ESPERAS.count(0) >= I.MAX_TENTATIVAS - 1, ESPERAS)
    checar("403 sem 404: não sonda 1238 nem imprime SEM EDICAO do STF",
           "stf1238" not in rede.pedidos and "SEM EDICAO NOVA INFORMATIVO STF" not in out)
    # 21/11/2026: documento que nao abriu nao derruba a fonte no script (quem acusa a edicao anunciada que saiu sem
    # conteudo e o montador); antes, "falha" e o leitor via "falhou" com os informativos completos ao lado
    checar("403 sem 404: SOURCE_STATUS ok; o número que não abriu fica no detalhe e em sem_abrir",
           st["informativos_docs"]["status"] == "ok" and "nova sem abrir: stf1237 http 403" in st["informativos_docs"]["detalhe"]
           and st["informativos_docs"]["sem_abrir"] == ["stf1237"] and st["informativos_docs"]["falhas"] == []
           and 'SOURCE_STATUS {"informativos_docs": "ok"}' in out, st)
    checar("403 sem 404: edição anterior há 6 dias (stf1236 de 10/11, hoje 16/11) — insistência inteira, sem 'sonda curta'",
           not por_id(js)["stf1237"].get("sonda_curta") and "sonda curta" not in out.split("stf1237=")[1].split(" · ")[0],
           out)
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
    # orcamento da insistencia: ORCAMENTO_EXTRAS pedidos alem do 1o de cada documento, por execucao
    velho = I.ORCAMENTO_EXTRAS
    I.ORCAMENTO_EXTRAS = 5
    try:
        rede = Rede(dict(base, stf1237=[(403, b"")], rg398=[(403, b"")], rg394=[(403, b"")]))
        out, js, st = rodar(rede, janela=JANELA)
    finally:
        I.ORCAMENTO_EXTRAS = velho
    r = por_id(js)
    checar("orçamento: no máximo ORCAMENTO_EXTRAS pedidos a mais por execução; depois, 1 pedido por documento",
           sum(max(0, x.get("tentativas", 1) - 1) for x in js) == 5 and rede.pedidos.count("stf1237") == 6
           and rede.pedidos.count("rg398") == 1 and rede.pedidos.count("rg394") == 1, rede.pedidos)
    # prazo: nenhum pedido novo depois de PRAZO_S (o 1o de cada documento sempre e feito)
    t = [0.0]
    velho_relogio, velha_espera = I.relogio, I.dormir
    I.relogio = lambda: t[0]
    I.dormir = lambda seg: t.__setitem__(0, t[0] + 40)      # cada espera "dura" 40 s
    try:
        rede = Rede(dict(base, stf1237=[(403, b"")], rg398=[(403, b"")]))
        out, js, st = rodar(rede, janela=JANELA)
    finally:
        I.relogio, I.dormir = velho_relogio, velha_espera
    checar("prazo: depois de PRAZO_S não há nova tentativa (stf1237: 3 pedidos; rg398: 1)",
           rede.pedidos.count("stf1237") == 3 and rede.pedidos.count("rg398") == 1, rede.pedidos)
    # erro que nao e 403 (rede caida, 5xx): so MAX_OUTROS_ERROS pedidos
    rede = Rede(dict(base, stf1237=[(0, b"")], stj910=[(503, b"")]))
    out, js, st = rodar(rede, janela=JANELA)
    checar("erro de rede/5xx: no máximo MAX_OUTROS_ERROS pedidos por documento",
           rede.pedidos.count("stf1237") == I.MAX_OUTROS_ERROS and rede.pedidos.count("stj910") == I.MAX_OUTROS_ERROS,
           rede.pedidos)


# ------------------------------------------------------------------ 6b. WAF do STF: 404 escondido, host alternativo, cache
def t_waf():
    base = {"stf1236": [(200, "pdf")], "rg397": [(200, "pdf")], "stj910": [(200, "stj910.html")],
            "rg394": [(200, "pdf")], "stf1233": [(200, "pdf")]}
    # 17/11/2026: a RG 398 dava 403 no script e 404 quando o pedido passava pelo firewall (a RG 397 era de 11/11:
    # 6 dias, insistencia inteira; com a anterior de menos de 6 dias seria a sonda curta, t_sonda_curta)
    rede = Rede(dict(base, stf1237=[(403, b""), (403, b""), (404, b"")], rg398=[(403, b""), (404, b"")]))
    out, js, st = rodar(rede, janela=dict(JANELA, data="2026-11-17"))
    r = por_id(js)
    checar("WAF: 403 e depois 404 = ainda não publicada (sem ERRO, fonte ok)",
           r["stf1237"]["estado"] == "inexistente" and r["stf1237"]["tentativas"] == 3 and "ERRO" not in out
           and st["informativos_docs"]["status"] == "ok"
           and any(l.startswith("SEM EDICAO NOVA INFORMATIVO STF (1237 ainda não publicada") for l in out.splitlines()), out)
    checar("WAF: o 404 do host alternativo não vale; o do endereço oficial, sim (rg398: 403, 404 no portal, 404 no www)",
           r["rg398"]["estado"] == "inexistente" and rede.pedidos.count("rg398") == 3
           and [u.split("/")[2] for u in rede.urls if "Edio398" in u] == ["www.stf.jus.br", "portal.stf.jus.br", "www.stf.jus.br"],
           rede.urls)
    velho = I.baixar
    antes = dict(PDF)
    PDF["stf1237"] = "stf1233-layout.txt"
    try:
        I.baixar = lambda url: (404, b"") if url.startswith(I.HOSTS_STF[1]) else (403, b"<html>Error 403</html>")
        c = I.baixar_documento("stf", 1237, tentativas=6)
        checar("WAF: só o host alternativo responde 404 -> segue indeterminado (403), todos os pedidos feitos",
               c[0] == 403 and c[2] == 6 and c[4] is False, c[:1] + c[2:])
        rede = Rede({"stf1237": [(403, b"")] * 4 + [(200, "pdf")]})
        I.baixar = rede.baixar
        r5 = I.obter("stf", 1237, "nova", tentativas=I.MAX_TENTATIVAS)
        checar("WAF: abre no 5º pedido (tentativas e 1ª resposta no registro)",
               r5["ok"] and r5["tentativas"] == 5 and r5["http_1a_tentativa"] == 403 and rede.pedidos == ["stf1237"] * 5,
               (r5.get("estado"), rede.pedidos))
        rede = Rede({"stf1237": [(403, b""), (200, "pdf")]})
        I.baixar = rede.baixar
        r1 = I.obter("stf", 1237)
        checar("WAF: obter() sem `tentativas` faz 1 pedido só (compatível)",
               r1["estado"] == "indeterminado" and rede.pedidos == ["stf1237"] and "http_1a_tentativa" not in r1, rede.pedidos)
        rede = Rede({"stf1237": [(200, b"<html>desafio do firewall</html>")]})
        I.baixar = rede.baixar
        rh = I.obter("stf", 1237, "nova", tentativas=I.MAX_TENTATIVAS)
        checar("WAF: 200 que não é PDF não é resposta definitiva (insiste pouco, como erro que não é 403)",
               rh["estado"] == "indeterminado" and rh["motivo"] == "resposta não é PDF"
               and rede.pedidos == ["stf1237"] * I.MAX_OUTROS_ERROS, (rh.get("motivo"), rede.pedidos))

        # cache da execucao: o PDF que abriu nao e pedido de novo (montador, rodadas seguintes)
        os.environ["ROBOZINHO_INF_CACHE"] = "1"
        json.dump({"execution_id": "2026-11-17-7h"}, open(os.path.join(TMP, "janela.json"), "w"))
        arq = os.path.join(TMP, "informativos-cache", "2026-11-17-7h", "stf1237.pdf")
        rede = Rede({"stf1237": [(403, b""), (200, "pdf")]})
        I.baixar = rede.baixar
        ra = I.obter("stf", 1237, "nova", tentativas=4)
        checar("cache: PDF que abriu é gravado em informativos-cache/<execution_id>/<id>.pdf",
               ra["ok"] and ra["tentativas"] == 2 and os.path.isfile(arq) and open(arq, "rb").read().startswith(b"%PDF"), arq)
        rede = Rede({"stf1237": [(403, b"")]})
        I.baixar = rede.baixar
        rb = I.obter("stf", 1237, "nova", tentativas=4)
        checar("cache: 2ª leitura sem nenhum pedido, com os mesmos destaques (17/11: abriu numa rodada, 403 nas seguintes)",
               rb["ok"] and rb.get("cache") is True and rb["tentativas"] == 0 and rede.pedidos == []
               and rb["itens"] == ra["itens"] and rb["chave"] == ra["chave"], (rb.get("estado"), rede.pedidos))
        out, js, st = rodar(Rede(dict(base, stf1237=[(403, b"")])), janela={"execution_id": "2026-11-17-7h"})
        checar("cache: a coleta lê do cache e a linha TECNICO diz 'cache'",
               por_id(js)["stf1237"]["ok"] and "stf1237=200(cache)" in out and "INFORMATIVO STF 1237 [id stf1237]" in out, out)
        json.dump({"execution_id": "2026-11-18-7h"}, open(os.path.join(TMP, "janela.json"), "w"))
        rede = Rede({"stf1237": [(403, b"")]})
        I.baixar = rede.baixar
        rc = I.obter("stf", 1237, "nova", tentativas=3)
        checar("cache: arquivo de outra execução não é usado",
               rc["estado"] == "indeterminado" and rede.pedidos == ["stf1237"] * 3, rede.pedidos)
        os.unlink(os.path.join(TMP, "janela.json"))
        rede = Rede({"stf1238": [(200, "pdf")]})
        I.baixar = rede.baixar
        PDF["stf1238"] = "stf1233-layout.txt"
        I.obter("stf", 1238, "nova")
        checar("cache: sem execution_id (fora da rotina) nada é gravado",
               I.caminho_cache("stf1238") is None
               and not any("stf1238" in f for _, _, fs in os.walk(os.path.join(TMP, "informativos-cache")) for f in fs))
        json.dump({"execution_id": "2026-11-17-7h"}, open(os.path.join(TMP, "janela.json"), "w"))
        rede = Rede({"stj909": [(200, "stj909.html")], "stf1239": [(403, b"")], "stf1240": [(404, b"")]})
        I.baixar = rede.baixar
        I.obter("stj", 909, "nova"); I.obter("stf", 1239, "nova", tentativas=2); I.obter("stf", 1240, "nova")
        checar("cache: só PDF aberto vai para o cache (página do STJ, 403 e 404 não)",
               "stf1237.pdf" in os.listdir(os.path.dirname(arq))
               and not any(f.startswith(("stj909", "stf1239", "stf1240")) for f in os.listdir(os.path.dirname(arq))),
               os.listdir(os.path.dirname(arq)))
    finally:
        I.baixar = velho
        os.environ["ROBOZINHO_INF_CACHE"] = "0"
        PDF.clear(); PDF.update(antes)
        shutil.rmtree(os.path.join(TMP, "informativos-cache"), ignore_errors=True)
        try:
            os.unlink(os.path.join(TMP, "janela.json"))
        except FileNotFoundError:
            pass


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
    checar("revisita: parar no 404 (rg397 404 -> rg394 não é pedida; as vagas do STF/RG vão para stf1233 de 19/10 e "
           "stf1231 de 05/10; a do STJ, para stj904 de 06/10)",
           "rg394" not in rede.pedidos
           and [p for p in rede.pedidos if p in ("stf1233", "stj904", "stf1231", "stf1230")] == ["stf1233", "stj904", "stf1231"],
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


# ------------------------------------------------------------------ 7b. `temas` gravado pelo montador (INF-rev-1c)
def t_temas_do_montador():
    """O item RG que o montador resolve (e grava no histórico) traz `temas`; o historico() o lê como contratado e
    a revisita de uma RG anterior tira o tema já publicado. O helper não mexe no campo (conferido na sandbox
    ponta a ponta e no test_mon); aqui vale a passagem montador -> limpar_para_gravar -> historico() -> obter()."""
    try:
        import montar_email as M
        M.resolver, M.limpar_para_gravar  # noqa: B018
    except Exception as e:  # noqa: BLE001
        print("AVISO   montar_email indisponível (%s) — conferência do `temas` pulada" % e)
        return
    PDF_ANTES = dict(PDF)
    I.baixar = Rede({"rg397": [(200, "pdf")]}).baixar
    r397 = I.obter("rg", 397, "atrasada", anuncio={"anunciada_em": "2026-11-11", "anunciada_na_edicao": "2026-11-12"},
                   hist_produto={})
    ev = {"rg397": dict(r397, _fonte="informativo")}
    erros, avisos = [], []
    item = M.resolver({"ref": "rg397", "destaques": {"excluir": [1]}, "temas": ["9.999"]}, ev, erros, avisos, None)
    grav = M.limpar_para_gravar({"items": [item]})["items"][0]
    esperado = [it["tema"] for i, it in enumerate(r397["itens"]) if i != 1]
    checar("montador: item RG resolvido grava `temas` (strings do documento, sem o excluído; o escrito à mão é ignorado)",
           not erros and grav.get("temas") == esperado and "1.487" not in grav["temas"] and "9.999" not in grav["temas"]
           and all(isinstance(t, str) for t in grav["temas"])
           and grav["chave"] == "stf|informativo|repercussao-geral-397-conteudo|2026|2026-11-09"
           and not grav.get("sem_conteudo"), (erros, grav.get("temas"), grav.get("chave")))
    # historico com o item de 16/11 como o montador o resolveu (no lugar do registro sintetico)
    hdir = tempfile.mkdtemp(prefix="hist-mon-", dir=TMP)
    base_h = json.load(open(os.path.join(FIX, "historico", "resumo-legislativo-historico.json"), encoding="utf-8"))
    for e in base_h["executions"]:
        if e["execution_id"] == "2026-11-16-7h":
            e["items"] = [grav if it.get("chave", "").startswith("stf|informativo|repercussao-geral-397-conteudo")
                          else it for it in e["items"]]
    json.dump(base_h, open(os.path.join(hdir, "resumo-legislativo-historico.json"), "w", encoding="utf-8"),
              ensure_ascii=False)
    json.dump(JANELA_1711, open(os.path.join(TMP, "janela.json"), "w"))
    aqui = I.AQUI
    I.AQUI = hdir
    try:
        h = I.historico()["rg"]
        PDF["rg394"] = "rg394.txt"
        I.baixar = Rede({"rg394": [(200, "pdf")]}).baixar
        r394 = I.obter("rg", 394, "atrasada")
    finally:
        I.AQUI = aqui
        PDF.clear(); PDF.update(PDF_ANTES)
        os.unlink(os.path.join(TMP, "janela.json"))
    checar("historico(): `temas` do montador vira {tema: data da execução} na RG 397",
           h[397].get("temas") == {t: "2026-11-16" for t in esperado} and h[397]["vazio"] is False, h[397])
    sup = {it["tema"]: it["superado_motivo"] for it in r394.get("itens_superados", [])}
    checar("revisita da RG 394 em 17/11: Tema 1.483 fora ('já publicado com a RG 397 em 16/11'); ficam 7",
           r394["ok"] and len(r394["itens"]) == 7 and "1.483" not in [it["tema"] for it in r394["itens"]]
           and sup.get("1.483") == "tema já publicado com a RG 397 em 16/11", sup)


# ------------------------------------------------------------------ 7c. P6: tema ja publicado por item SEM o campo `temas`
def limpar_consultas():
    getattr(I, "TEMAS_DOC", {}).clear()     # conferencias de documento ficam em cache por processo


def hist_real_ate_397():
    """historico() real congelado em 16/11 (fixtures/informativos/historico-real-1611: os itens stf|stj informativo
    do repositorio ate a execucao de 16/11, sem alteracao), so a RG. Antes lia o historico vivo e filtrava pelo numero
    da RG: em 18/11 a RG 394 ganhou conteudo e o teste ficou vermelho sem bug."""
    json.dump(JANELA_1711, open(os.path.join(TMP, "janela.json"), "w"))
    aqui = I.AQUI
    I.AQUI = os.path.join(FIX, "historico-real-1611")
    try:
        h = I.historico()
    finally:
        I.AQUI = aqui
    return {"stf": {}, "rg": h["rg"], "stj": {}}


def t_p6_historico_real():
    """P6: o registro da RG 397 de 16/11 foi gravado pelo montador antigo, sem `temas` ("6 de 10 destaques
    publicados"); na revisita da RG 394 o Tema 1.483 (saído em 16/11) voltava. O texto gravado não traz o número
    do tema: a lista é conferida no documento da RG 397 (1 pedido), e o tema sai da revisita."""
    h = hist_real_ate_397()
    r397 = h["rg"].get(397) or {}
    checar("P6 histórico real congelado em 16/11: RG 397 reconhecida como publicada com destaques, lista não gravada",
           r397.get("vazio") is False and r397.get("temas_desconhecidos") == "2026-11-16" and max(h["rg"]) == 397, r397)
    checar("P6 histórico real congelado em 16/11: RG 394 sem conteúdo (é revisitada)",
           (h["rg"].get(394) or {}).get("vazio") is True, h["rg"].get(394))
    PDF_ANTES = dict(PDF)
    PDF["rg394"] = "rg394.txt"
    PDF["rg397"] = "rg397.txt"
    limpar_consultas()
    try:
        rede = Rede({"rg394": [(200, "pdf")], "rg397": [(200, "pdf")]})
        I.baixar = rede.baixar
        r = I.obter("rg", 394, "atrasada", h["rg"].get(394), h["rg"])
    finally:
        PDF.clear(); PDF.update(PDF_ANTES)
        limpar_consultas()
    temas = [it["tema"] for it in r.get("itens") or []]
    sup = {it["tema"]: it["superado_motivo"] for it in r.get("itens_superados") or []}
    checar("P6 histórico real congelado:revisita da RG 394 sem o Tema 1.483 (saiu com a RG 397 em 16/11)",
           r.get("ok") and "1.483" not in temas and sup.get("1.483") == "tema também na RG 397, publicada em 16/11",
           (temas, sup))
    checar("P6 histórico real congelado:ficam 7 temas; os 5 em votação/pauta continuam fora pela data",
           temas == ["1.016", "106", "1.479", "1.480", "1.490", "1.491", "1.492"]
           and sorted(t for t, v in sup.items() if "boletins seguintes" in v) == sorted(["1.493", "1.494", "118", "488", "1.308"]),
           (temas, sup))
    checar("P6 histórico real congelado:1 pedido a mais (o documento da RG 397), registrado em temas_consultados",
           rede.pedidos == ["rg394", "rg397"] and r.get("temas_consultados") == {"rg397": 200},
           (rede.pedidos, r.get("temas_consultados")))
    # execucao automatica de 17/11 (so a RG, historico real congelado ate a 397)
    PDF["rg394"] = "rg394.txt"
    PDF["rg397"] = "rg397.txt"
    limpar_consultas()
    try:
        rede = Rede({"rg394": [(200, "pdf")], "rg397": [(200, "pdf")]})
        I.baixar = rede.baixar
        res = I.coletar(h)
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida):
            I.imprimir(res)
    finally:
        PDF.clear(); PDF.update(PDF_ANTES)
        limpar_consultas()
        os.unlink(os.path.join(TMP, "janela.json"))
    out = saida.getvalue()
    checar("P6 replay 17/11 (histórico real congelado): RG 394 no EM ATRASO com 7 destaques, sem o Tema 1.483 no índice",
           "REPERCUSSAO GERAL EM PAUTA 394 [id rg394] (14 a 19 de outubro de 2026) — ATRASADA, revisita (anunciada em 21/10) "
           "— 7 destaques" in out and not re.search(r"(?m)^  \d+ \[.*\] Tema 1\.483 ", out), out)
    checar("P6 replay 17/11: linha 'fora do e-mail' do Tema 1.483 e TECNICO com a conferência",
           "  fora do e-mail — tema também na RG 397, publicada em 16/11: Tema 1.483" in out.splitlines()
           and "rg394=200(6 superados, revisita, temas de rg397=200)" in out
           and rede.pedidos == ["rg398", "rg399", "rg394", "rg397"], (rede.pedidos, out))


def t_p6_temas_do_texto():
    """P6: item de RG gravado sem `temas` (orquestrador, ou montador antigo): os temas citados no texto gravado
    (destaques_texto, titulo, resumo, observacao) contam como publicados. Tema citado de passagem em item de outro
    tipo (Mídia, Opinião, Informativo STF, STF Jurisprudência) ou em anúncio vazio não bloqueia."""
    hdir = tempfile.mkdtemp(prefix="hist-p6-", dir=TMP)
    rg = "stf|informativo|repercussao-geral-%s|2026|%s"
    execs = [
        {"execution_id": "2026-10-22-7h", "date": "2026-10-22", "items": [
            {"chave": rg % ("394", "2026-10-21"), "observacao": "conteudo nao acessivel nesta execucao (http 403)"}]},
        {"execution_id": "2026-11-05-7h", "date": "2026-11-05", "items": [
            {"chave": rg % ("396", "2026-11-03"), "titulo": "Repercussão Geral em Pauta nº 396 (27/10 a 03/11/2026)",
             "observacao": "Temas 1.258 e 1.486 publicados; TEMA: 488 com acórdão"},
            {"chave": "stf|tese|tema-1490|2026|2026-11-03", "categoria": "STF Jurisprudência",
             "titulo": "Tema 1.490 (RE 1.555.476): gratificação — repercussão geral negada"},
            {"chave": "midia|jota|stf-julga-tema-1016|2026|2026-11-05", "categoria": "Mídia",
             "titulo": "STF conclui o Tema 1.016 dos expurgos inflacionários"},
            {"chave": "conjur|opiniao|tema-1479|2026|2026-11-05", "categoria": "Opinião/Análise",
             "titulo": "O que muda com o Tema 1.479"}]},
        {"execution_id": "2026-11-12-7h", "date": "2026-11-12", "items": [
            {"chave": rg % ("397", "2026-11-11"), "sem_conteudo": True,
             "titulo": "Repercussão Geral em Pauta nº 397 — Tema 1.491"},
            {"chave": "stf|informativo|1236-conteudo|2026|2026-11-10", "titulo": "Informativo STF nº 1236",
             "observacao": "ISS na base do PIS/COFINS (Tema 118 RG); Tema 1.480"}]},
        {"execution_id": "2026-11-16-7h", "date": "2026-11-16", "items": [
            {"chave": rg % ("397-conteudo", "2026-11-09"), "titulo": "Repercussão Geral em Pauta nº 397",
             "resumo": "Tema 1483: redução da validade do CR e do CRAF.",
             "destaques_texto": ["<b>Tema 977</b> (RE 1.234.567) · <i>Pauta</i> — x"]}]},
    ]
    json.dump({"executions": execs}, open(os.path.join(hdir, "resumo-legislativo-historico.json"), "w", encoding="utf-8"),
              ensure_ascii=False)
    aqui = I.AQUI
    I.AQUI = hdir
    try:
        h = I.historico()
    finally:
        I.AQUI = aqui
    checar("P6 texto: temas da RG derivados do texto gravado e normalizados como o campo novo ('1483' → '1.483')",
           h["rg"][397].get("temas") == {"1.483": "2026-11-16", "977": "2026-11-16"}
           and h["rg"][396].get("temas") == {"1.258": "2026-11-05", "1.486": "2026-11-05", "488": "2026-11-05"},
           (h["rg"][397].get("temas"), h["rg"][396].get("temas")))
    checar("P6 texto: 'nº 397' não é tema; anúncio vazio ('Tema 1.491') não conta; RG 394 sem conteúdo segue vazia",
           "397" not in h["rg"][397].get("temas", {}) and "1.491" not in h["rg"][397].get("temas", {})
           and h["rg"][394]["vazio"] is True and "temas" not in h["rg"][394], h["rg"])
    checar("P6 texto: item de outro tipo não cria nem completa RG (Informativo STF, STF Jurisprudência, Mídia, Opinião)",
           sorted(h["rg"]) == [394, 396, 397] and "temas" not in h["stf"].get(1236, {}), (sorted(h["rg"]), h["stf"].get(1236)))
    _, i394 = I.rg_texto(fx("rg394.txt"))
    m = I.superados_por_historico(394, i394, h["rg"])
    sup = {i394[i]["tema"]: v for i, v in m.items()}
    checar("P6 texto: na RG 394 saem só 1.483 (RG 397 em 16/11) e 488 (RG 396 em 05/11)",
           sup == {"1.483": "tema já publicado com a RG 397 em 16/11", "488": "tema já publicado com a RG 396 em 05/11"}, sup)
    checar("P6 texto: Temas 1.016, 1.479, 1.480 e 1.490 (citados só em itens de outro tipo) e 1.491 (anúncio) ficam",
           not {"1.016", "1.479", "1.480", "1.490", "1.491"} & set(sup), sup)
    checar("P6 texto: registro sem a marca do montador ('k de M destaques publicados') não pede conferência no documento",
           not any(v.get("temas_desconhecidos") for v in h["rg"].values()), h["rg"])


def t_p6_conferencia():
    """P6: conferência no documento da RG posterior — cache por processo, teto de documentos, falha permissiva."""
    if not hasattr(I, "superados_por_documento"):
        checar("P6 conferência: informativos.superados_por_documento existe", False)
        return
    checar("P6 normalizar_tema: '1483' / '01.483' / '1.483' → '1.483'; '977' e '118' iguais",
           [I.normalizar_tema(x) for x in ("1483", "01.483", "1.483", "977", "118", " 1.016 ")] ==
           ["1.483", "1.483", "1.483", "977", "118", "1.016"])
    checar("P6 temas_do_texto: plural, 'TEMA:', 'nº', HTML; sem número de edição nem processo",
           I.temas_do_texto({"titulo": "Repercussão Geral em Pauta nº 397 — RE 1.616.922",
                             "observacao": "Temas 1.493, 1.494 e 118; TEMA: 977; Tema nº 1483.",
                             "destaques_texto": ["<b>Tema 1.016</b> (RE 1) — x"]})
           == ["1.016", "1.493", "1.494", "118", "977", "1.483"])
    _, i394 = I.rg_texto(fx("rg394.txt"))
    h = {394: {"vazio": True}, 395: {"vazio": False, "temas_desconhecidos": "2026-10-29"},
         396: {"vazio": False, "temas_desconhecidos": "2026-11-05"}, 397: {"vazio": False, "temas_desconhecidos": "2026-11-16"}}
    PDF_ANTES = dict(PDF)
    PDF.update({"rg396": "rg396.txt", "rg397": "rg397.txt"})
    limpar_consultas()
    try:
        rede = Rede({"rg395": [(200, "pdf")], "rg396": [(200, "pdf")], "rg397": [(200, "pdf")]})
        I.baixar = rede.baixar
        cons = {}
        m = I.superados_por_documento(394, i394, h, {}, cons)
        sup = {i394[i]["tema"]: v for i, v in m.items()}
        checar("P6 conferência: as posteriores mais recentes primeiro, até MAX_CONSULTAS_TEMAS (%d) documentos"
               % I.MAX_CONSULTAS_TEMAS,
               I.MAX_CONSULTAS_TEMAS == 2 and rede.pedidos == ["rg397", "rg396"] and cons == {"rg397": 200, "rg396": 200}
               and sup == {"1.483": "tema também na RG 397, publicada em 16/11",
                           "488": "tema também na RG 396, publicada em 05/11"}, (rede.pedidos, cons, sup))
        m2 = I.superados_por_documento(394, i394, h, {i: "x" for i in m}, {})
        checar("P6 conferência: documento já conferido não é baixado de novo; índice já superado não é refeito",
               rede.pedidos == ["rg397", "rg396"] and m2 == {}, (rede.pedidos, m2))
        limpar_consultas()
        rede = Rede({"rg397": [(403, b"")]})
        I.baixar = rede.baixar
        cons = {}
        m3 = I.superados_por_documento(394, i394, {397: h[397]}, {}, cons)
        checar("P6 conferência: documento que não abre não tira tema nenhum (fica como antes) e fica registrado",
               m3 == {} and cons == {"rg397": 403} and rede.pedidos == ["rg397"] * I.MAX_TENTATIVAS_REVISITA,
               (m3, cons, rede.pedidos))
        limpar_consultas()
        rede = Rede({})
        I.baixar = rede.baixar
        checar("P6 conferência: sem tema a conferir (todos já superados) nada é baixado",
               I.superados_por_documento(394, i394, h, {i: "x" for i in range(len(i394))}, {}) == {} and rede.pedidos == [],
               rede.pedidos)
        checar("P6 conferência: histórico sem a marca (registros novos, com `temas`) não baixa nada",
               I.superados_por_documento(394, i394, {397: {"vazio": False, "temas": {"1.483": "2026-11-16"}}}, {}, {}) == {}
               and rede.pedidos == [], rede.pedidos)
    finally:
        PDF.clear(); PDF.update(PDF_ANTES)
        limpar_consultas()
    # TECNICO com a conferencia que falhou; a fonte nao cai por ela
    r = {"tipo": "rg", "numero": 394, "id": "rg394", "http": 200, "situacao": "atrasada", "ok": True, "revisita": True,
         "data": "14 a 19 de outubro de 2026", "itens": i394[:1], "temas_consultados": {"rg397": 403}}
    saida = io.StringIO()
    with contextlib.redirect_stdout(saida):
        I.imprimir([r])
    checar("P6 conferência: TECNICO mostra 'temas de rg397=403'; fonte ok",
           "rg394=200(revisita, temas de rg397=403)" in saida.getvalue() and I.status_fonte([r])["status"] == "ok",
           saida.getvalue())


# ------------------------------------------------------------------ 7d. sonda curta, vagas de revisita, status da fonte
def t_sonda_curta():
    """18 a 20/11/2026: stf1238 e rg399 (ainda nao publicados) davam 403 em todos os 12 pedidos (o firewall esconde
    o 404), 24 pedidos e ~45 s por dia, e a fonte virava 'falha' ('falhou' ao leitor ao lado de 5 edicoes abertas).
    Com a edicao anterior de menos de CADENCIA_SONDA_DIAS dias, a sonda do numero novo do STF/RG e curta."""
    hist = {"stf": {1237: {"vazio": False, "anunciada_em": "2026-11-16", "anunciada_na_edicao": "2026-11-17"}},
            "rg": {398: {"vazio": False, "anunciada_em": "2026-11-17", "anunciada_na_edicao": "2026-11-18"}},
            "stj": {910: {"vazio": False, "anunciada_em": "2026-11-17", "anunciada_na_edicao": "2026-11-18"}}}
    json.dump({"execution_id": "2026-11-20-7h", "data": "2026-11-20"}, open(os.path.join(TMP, "janela.json"), "w"))
    try:
        rede = Rede({"stf1238": [(403, b"")], "rg399": [(403, b"")], "stj911": [(200, "stj910.html")]})
        I.baixar = rede.baixar
        res = I.coletar(hist)
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida):
            I.imprimir(res)
        out = saida.getvalue()
        st = I.status_fonte(res)
    finally:
        os.unlink(os.path.join(TMP, "janela.json"))
    checar("sonda curta (20/11): stf1238 e rg399 com %d pedidos cada (antes %d), sem sondar o número seguinte"
           % (I.MAX_TENTATIVAS_SONDA, I.MAX_TENTATIVAS),
           rede.pedidos.count("stf1238") == I.MAX_TENTATIVAS_SONDA == rede.pedidos.count("rg399")
           and "stf1239" not in rede.pedidos and "rg400" not in rede.pedidos and rede.pedidos.count("stj911") == 1,
           rede.pedidos)
    checar("sonda curta: fonte ok, números em sem_abrir; TECNICO diz 'sonda curta'",
           st["status"] == "ok" and st["sem_abrir"] == ["stf1238", "rg399"]
           and "nova sem abrir: stf1238 http 403, rg399 http 403" in st["detalhe"]
           and "stf1238=403(indeterminado, sonda curta, 2 tentativas, 1a=403)" in out, (st, out))
    checar("sonda curta: ERRO segue (com o e-mail da edição, o orquestrador cita o ref) e diz que pode não ter saído",
           any(l.startswith("ERRO INFORMATIVO STF 1238 [id stf1238]: documento não abriu (sonda curta; talvez ainda não "
                            "publicada) — sem e-mail desta edição, não cite nem reporte ao leitor") for l in out.splitlines()), out)
    checar("tentativas_novo: STF/RG com a anterior de 5 dias = sonda curta; de 6 dias, sem data ou STJ = insistência inteira",
           (I.tentativas_novo("stf", "2026-11-15", "2026-11-20"), I.tentativas_novo("rg", "2026-11-14", "2026-11-20"),
            I.tentativas_novo("stf", "", "2026-11-20"), I.tentativas_novo("stj", "2026-11-19", "2026-11-20"))
           == (I.MAX_TENTATIVAS_SONDA, I.MAX_TENTATIVAS, I.MAX_TENTATIVAS, I.MAX_TENTATIVAS))
    # a edicao nova que abre muda a referencia: a seguinte se mede pela data dela
    hist2 = {"stf": {1235: {"vazio": False, "anunciada_em": "2026-11-04", "anunciada_na_edicao": "2026-11-05"}},
             "rg": {}, "stj": {}}
    json.dump({"execution_id": "2026-11-16-7h", "data": "2026-11-16"}, open(os.path.join(TMP, "janela.json"), "w"))
    try:
        rede = Rede({"stf1236": [(200, "pdf")], "stf1237": [(403, b"")]})
        I.baixar = rede.baixar
        res = I.coletar(hist2)
    finally:
        os.unlink(os.path.join(TMP, "janela.json"))
    checar("sonda curta: 1236 (anterior de 12 dias) com insistência inteira e aberta; 1237 medida pela data do 1236 "
           "(10/11, 6 dias): insistência inteira",
           rede.pedidos.count("stf1236") == 1 and rede.pedidos.count("stf1237") == I.MAX_TENTATIVAS
           and not any(r.get("sonda_curta") for r in res if r.get("tipo") == "stf"), rede.pedidos)
    t0 = len(rede.pedidos)
    json.dump({"execution_id": "2026-11-12-7h", "data": "2026-11-12"}, open(os.path.join(TMP, "janela.json"), "w"))
    try:
        rede = Rede({"stf1236": [(200, "pdf")], "stf1237": [(403, b"")]})
        I.baixar = rede.baixar
        res = I.coletar(hist2)
    finally:
        os.unlink(os.path.join(TMP, "janela.json"))
    checar("sonda curta: 1236 de 10/11 aberto hoje (12/11) -> o 1237 só ganha a sonda curta",
           rede.pedidos.count("stf1237") == I.MAX_TENTATIVAS_SONDA and t0 > len(rede.pedidos), rede.pedidos)


def t_revisitas_stj():
    """20/11/2026: o stj903 (sem conteudo desde 29/09) nunca era tentado: stf1231 e stf1230, barrados pelo firewall,
    levavam as duas vagas. O STJ (sem firewall, 1 pedido) tem vagas proprias."""
    hist = {"stf": {1229: {"vazio": False, "anunciada_em": "2026-09-21", "anunciada_na_edicao": "2026-09-22"},
                    1230: {"vazio": True, "anunciada_em": "2026-09-29", "anunciada_na_edicao": "2026-09-30"},
                    1231: {"vazio": True, "anunciada_em": "2026-10-05", "anunciada_na_edicao": "2026-10-06"},
                    1236: {"vazio": False, "anunciada_em": "2026-11-10", "anunciada_na_edicao": "2026-11-11"},
                    1237: {"vazio": False, "anunciada_em": "2026-11-16", "anunciada_na_edicao": "2026-11-17"}},
            "rg": {397: {"vazio": False, "anunciada_em": "2026-11-11", "anunciada_na_edicao": "2026-11-12"},
                   398: {"vazio": False, "anunciada_em": "2026-11-17", "anunciada_na_edicao": "2026-11-18"}},
            "stj": {903: {"vazio": True, "anunciada_em": "2026-09-29", "anunciada_na_edicao": "2026-09-30"},
                    909: {"vazio": False, "anunciada_em": "2026-11-10", "anunciada_na_edicao": "2026-11-11"},
                    910: {"vazio": False, "anunciada_em": "2026-11-17", "anunciada_na_edicao": "2026-11-18"}}}
    rede = Rede({"stf1231": [(403, b"")], "stf1230": [(403, b"")], "stf1238": [(403, b"")],
                 "stj903": [(200, "stj909.html")], "stj911": [(200, "stj910.html")]})
    I.baixar = rede.baixar
    json.dump({"execution_id": "2026-11-20-7h", "data": "2026-11-20"}, open(os.path.join(TMP, "janela.json"), "w"))
    try:
        res = I.coletar(hist)
        st = I.status_fonte(res)
    finally:
        os.unlink(os.path.join(TMP, "janela.json"))
    checar("revisitas: stf1231 e stf1230 barrados levam as vagas do STF; o stj903 tem a sua (1 pedido)",
           rede.pedidos.count("stj903") == 1 and rede.pedidos.count("stf1231") == I.MAX_TENTATIVAS_REVISITA
           and rede.pedidos.count("stf1230") == I.MAX_TENTATIVAS_REVISITA, rede.pedidos)
    checar("revisitas: a do STJ que não abriu não derruba a fonte; as do STF ficam no detalhe",
           st["status"] == "ok" and "revisita sem abrir: stf1231 http 403, stf1230 http 403" in st["detalhe"], st)


def t_status_fonte():
    base = {"tipo": "stf", "numero": 1237, "id": "stf1237", "http": 403, "ok": False}
    st = I.status_fonte([dict(base, situacao="atrasada", estado="indeterminado")])
    checar("status_fonte: anunciada sem conteúdo que não abriu = ok (quem acusa a citada é o montador)",
           st["status"] == "ok" and "anunciada sem abrir: stf1237 http 403" in st["detalhe"] and st["sem_abrir"] == ["stf1237"], st)
    st = I.status_fonte([{"tipo": "stj", "numero": 910, "id": "stj910", "http": 200, "ok": False, "situacao": "nova",
                          "estado": "parser"}, {"tipo": "rg", "ok": False, "situacao": "nova", "estado": "sem_historico"}])
    checar("status_fonte: parser e produto sem histórico = falha, com os ids em 'falhas' (o montador nomeia o produto)",
           st["status"] == "falha" and st["falhas"] == ["stj910", "rg"] and st["detalhe"].startswith("falha: stj910 parser"), st)


def t_parser_miudos():
    """Defeitos de parser visiveis ao leitor (revisao de 18/11/2026)."""
    checar("juntar: hífen de palavra composta no fim da linha fica ('licenças-' + 'prêmio'; 'auxílio-' + 'doença')",
           I.juntar(["férias e licenças-", "prêmio não gozadas"]) == "férias e licenças-prêmio não gozadas"
           and I.juntar(["o salário-", "maternidade e o auxílio-", "doença"]) == "o salário-maternidade e o auxílio-doença"
           and I.juntar(["os Estados-", "membros e o Procurador-", "Geral"]) == "os Estados-membros e o Procurador-Geral"
           and I.juntar(["tempora-", "riamente e licen-", "ça"]) == "temporariamente e licença",
           [I.juntar(["férias e licenças-", "prêmio"]), I.juntar(["Estados-", "membros"])])
    sint = ("PAUTA DO PLENÁRIO\nTEMA: 1.491 PROCESSOS: RE\nRE1.612.904 RELATOR: Min. Fulano\nTítulo: Um.\n"
            "TEMA: 2 PROCESSOS: ARE\n1.000.002\nRE 1.000.003\nTítulo: Dois.\n"
            "TEMA: 3 PROCESSOS: RE1.000.004\nTítulo: Três.\n")
    _, it = I.rg_texto(sint)
    checar("rg: só a classe na linha do TEMA e o número na seguinte = um processo ('RE 1.612.904', não 'RE; RE1.612.904')",
           [x["processo"] for x in it] == ["RE 1.612.904", "ARE 1.000.002; RE 1.000.003", "RE 1.000.004"],
           [x["processo"] for x in it])


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
        for t in (t_fixtures, t_stf_resumo, t_rg, t_stj, t_historico, t_replay_1611, t_403, t_waf, t_parser_e_404, t_superados,
                  t_temas_do_montador, t_p6_historico_real, t_p6_temas_do_texto, t_p6_conferencia, t_sonda_curta,
                  t_revisitas_stj, t_status_fonte, t_parser_miudos, t_manual_e_compat):
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
