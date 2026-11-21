#!/usr/bin/env python3
# =====================================================================
# test_doc.py — a documentacao descreve o que o codigo faz (grupo DOC).
#
# Confere, sem rede:
#   - placeholders dos work/prompts/coletor-*.md existem no inicio.py (ou sao
#     NOTA:/ARMADILHA: de ids do ledger);
#   - arquivos work/... citados na ROTINA, README, referencia, prompt mestre,
#     prompts e agentes existem; flags citadas junto de um script existem nele;
#   - as linhas que a ROTINA e os prompts mandam procurar na saida dos scripts
#     sao mesmo impressas por eles;
#   - formatos que o orquestrador copia dos coletores (resenha, meta do DOU,
#     arquivo de itens do JOTA) sao os que o montador e o resolver entendem;
#   - ids de source_status, ToolSearch do passo 1, agentes com entrega
#     condicional, §R apontados existem, textos contraditorios antigos sairam,
#     ROTINA dentro do teto de tamanho, munger-quotes sem caminhos locais;
#   - (2a rodada) os trechos das linhas do finalizar.sh/aguardar_coleta.py
#     citados na ROTINA e na §R existem no codigo; a 2a notificacao cobre as
#     linhas que pedem "diga na notificacao"; o rebaixamento do selo e o selo
#     copiado descritos batem com o selos.py; o que a ROTINA diz do item escrito
#     bate com o montador; os roteiros dos coletores comecam por Read+ToolSearch.
#   - (volta 2) prazos[].tipo: a ROTINA lista os 4 valores; o AVISO acionavel de tipo x evento citado na ROTINA
#     e na §R12 e o que montador e helper imprimem, e a correcao que eles pedem o resolve; PRAZO VENCIDO (sem
#     ação) citado como o inicio.py imprime; rodape do JOTA recusado (titulo de descadastro) nao vira item.
#   - (volta 3) selo por data suspenso e prazo escrito hoje contra o edital: os modelos da §R12 sao o que helper,
#     montador e inicio imprimem, a correcao que a ROTINA manda resolve e as linhas de gravacao vao a 2a
#     notificacao; linha-fina cortada (resumo_truncado) nao se completa nem se copia; README com as regras novas.
#   - (rodada de 21/11) buscas_gmail -> gmail_* (a ROTINA nao os escreve), STJ_TESES, LEGIN/camara_legin e resenha
#     no ref, banca_slug/movimento, linhas novas do passo 1 e da banca (MOVIMENTO sem registro some no dia seguinte),
#     escopo do apoio, ERRO INTERNO/TRAVA/RESTAURADO/REAPLICACAO e push so na main, migracoes reais sem ALERTA e
#     REGRAS_ATUALIZADAS vivas, marcas do coleta_web e Afetacao, §R1 com window_end, notificacao unica (§R13 nova).
#   - (rodada final) a regra de armadilha que o passo 1 imprime (inicio.regra_impressa) e a que o helper grava
#     (REGRAS_ATUALIZADAS, inclusive cloud_egress_bloqueado sem a medicao fixa de rede) sao o mesmo texto.
# Opcional (rede): DOC_TESTE_INICIO=1 roda o inicio.py numa copia descartavel
# e confere que nenhum placeholder sobra nos prompts gerados.
#
# USO: python3 work/testes/test_doc.py      (imprime OK/FALHOU; exit 1 em falha)
# =====================================================================

import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.dirname(AQUI)
RAIZ = os.path.dirname(WORK)
sys.path.insert(0, WORK)

ROTINA_ANTERIOR_BYTES = 19253          # ROTINA.md de b80a3bd (execucao de 16/11)
# Teto da ROTINA (lida inteira em toda execucao). A 2a rodada acrescentou o que ela tem de dizer na hora
# (linhas novas do finalizar.sh, rebaixamento do selo, regras novas do montador) e levou o procedimento
# para a referencia (§R10-§R12): +~1,5 KB sobre a de 16/11, ainda abaixo da de 10/11 (22.805).
# Volta 3 (+~640 bytes, o procedimento na §R12): selo por data suspenso no passo 1, o que fazer com ele e com o
# prazo escrito hoje contra o edital no passo 3, as duas linhas de gravacao na 2a notificacao e a linha-fina cortada
# no passo 2. Era 21.000.
# Rodada de 21/11/2026 (+~1,35 KB, o maximo combinado com o dono): as regras das frentes bancas, concursos, montador,
# informativos, fontes, persistencia e migracao (banca_slug/CANDIDATO, PAGINA OFICIAL, escopo do apoio, buscas_gmail,
# STJ_TESES, LEGIN e marcas de relevancia, JA SAIU, movimento, resenha no ref, pendencia para o leitor, notificacao
# unica depois do finalizar.sh, ERRO INTERNO/TRAVA). Para caber, o ramo raro do create_draft com erro foi para a §R13,
# o Agent em segundo plano para a §R3 e o detalhe do DIVERGE/prazo escrito hoje ficou so na §R12; o que a propria linha
# do script ja manda fazer (JA PUBLICADAS, ERRO dos informativos, rotina, NENHUM ATO FORA, cobertura parcial) e o que
# a armadilha do ledger ja diz (link do JOTA, MPV SEM_DATA_OFICIAL) sairam do texto. Era 21.650.
ROTINA_TETO_BYTES = 23000
DOCS = ["ROTINA.md", "README.md", "docs/referencia-operacional.md", "robozinho-dos-momozis-prompt.md"] + \
    sorted(os.path.relpath(p, RAIZ) for p in glob.glob(os.path.join(WORK, "prompts", "coletor-*.md"))) + \
    sorted(os.path.relpath(p, RAIZ) for p in glob.glob(os.path.join(RAIZ, ".claude", "agents", "coletor-*.md")))
# arquivos citados que podem nao existir no clone (criados em execucao)
CRIADOS_EM_EXECUCAO = {"work/concursos-estado.json"}

falhas = []


def ler(rel):
    with open(os.path.join(RAIZ, rel), encoding="utf-8") as f:
        return f.read()


def teste(fn):
    try:
        fn()
        print("OK      %s" % fn.__name__)
    except AssertionError as e:
        falhas.append(fn.__name__)
        print("FALHOU  %s: %s" % (fn.__name__, e))
    except Exception as e:  # noqa: BLE001
        falhas.append(fn.__name__)
        print("FALHOU  %s: %s: %s" % (fn.__name__, type(e).__name__, e))
    return fn


def ledger():
    with open(os.path.join(WORK, "robozinho-aprendizado.json"), encoding="utf-8") as f:
        return json.load(f)


@teste
def placeholders_dos_prompts_existem_no_inicio():
    fonte = ler("work/inicio.py")
    ini = fonte.index("vars_ = {")
    bloco = fonte[ini:fonte.index("\n    }\n", ini)]
    chaves = set(re.findall(r'"([A-Z_]+)":', bloco))
    led = ledger()
    fontes = {f["id"] for f in led.get("fontes", [])}
    armad = {a["id"] for a in led.get("armadilhas", [])}
    for p in glob.glob(os.path.join(WORK, "prompts", "coletor-*.md")):
        for ph in re.findall(r"\{\{([^}]+)\}\}", open(p, encoding="utf-8").read()):
            if ph.startswith("NOTA:"):
                assert ph[5:] in fontes, "%s: fonte %s fora do ledger" % (os.path.basename(p), ph)
            elif ph.startswith("ARMADILHA:"):
                assert ph[10:] in armad, "%s: armadilha %s fora do ledger" % (os.path.basename(p), ph)
            else:
                assert re.fullmatch(r"[A-Z_]+", ph) and ph in chaves, \
                    "%s: {{%s}} nao e preenchido pelo inicio.py" % (os.path.basename(p), ph)


@teste
def arquivos_citados_existem():
    faltando = []
    for rel in DOCS:
        for m in re.findall(r"(?<![\w/.-])((?:work|docs|\.claude)/[^\s`)\"',;:|]+)", ler(rel)):
            m = m.rstrip(".")
            if m.endswith("/") or m in CRIADOS_EM_EXECUCAO:
                continue
            # padroes genericos: coletor-*.md, coletor-X.md, test_<grupo>.py, ...-arquivo-*.json
            padrao = re.sub(r"<[^>]*>|\*|(?<=coletor-)X(?=\.md)", "*", m)
            if not glob.glob(os.path.join(RAIZ, padrao)):
                faltando.append("%s -> %s" % (rel, m))
    assert not faltando, "; ".join(sorted(set(faltando)))


@teste
def flags_citadas_existem_no_script():
    erros = []
    for rel in DOCS:
        for trecho in re.findall(r"`([^`]*)`", ler(rel)):
            m = re.search(r"work/([\w-]+\.(?:py|sh))", trecho)
            if not m:
                continue
            caminho = os.path.join(WORK, m.group(1))
            if not os.path.exists(caminho):
                continue
            codigo = open(caminho, encoding="utf-8").read()
            for flag in re.findall(r"(?<![\w-])(--[a-z][\w-]*)", trecho[m.end():]):
                if flag not in codigo:
                    erros.append("%s: %s %s" % (rel, m.group(1), flag))
    assert not erros, "; ".join(sorted(set(erros)))


@teste
def ps1_so_como_inexistente():
    for rel in DOCS:
        for linha in ler(rel).splitlines():
            if "Update-Historico.ps1" in linha:
                assert rel == "README.md" and "não faz parte" in linha, "%s cita o .ps1: %s" % (rel, linha[:80])


@teste
def textos_contraditorios_antigos_sairam():
    proibidos = {
        "concursos_html.py": DOCS,
        "executa aquela fonte ele mesmo": DOCS,
        "pela manchete, publicar só se o": DOCS,
        "ROTINA passo 5": DOCS,
        "Corpo < ~100 KB": DOCS,
        "==== HTMLBODY ====": ["ROTINA.md"],
        "até ~6": ["ROTINA.md"],
        "até ~8": ["ROTINA.md"],
        "\"ok\": false": ["ROTINA.md"],
        "python3 work/coleta_web.py; python3 work/informativos.py": ["ROTINA.md"],
        "cada seção limitada aos ~10 itens": DOCS,
        "(situação atual)": DOCS,
        # 2a rodada
        "não republique o que ela já trouxe": ["ROTINA.md"],          # sem criterio executavel (§R10 da)
        "AINDA RODANDO após": DOCS,                                     # formato antigo do aguardar_coleta
        "--teto\", str(teto)": DOCS,                                    # heredoc antigo da §R4
        "timeout: 600000": ["ROTINA.md", "docs/referencia-operacional.md"],
        "ALERTA para confirmar prorrogação": DOCS,                     # virou PENDÊNCIA DE VERIFICAÇÃO
        "e selo INSCRIÇÕES ABERTAS": DOCS,                             # texto antigo do selos.py
        "`ENCERRA HOJE` → `INSCRIÇÕES ENCERRADAS`": ["ROTINA.md"],     # ENCERRADAS nao e automatico sem banca
        "o escrito prevalece sobre o cálculo": ["ROTINA.md"],          # so o selo DIFERENTE do registro
        "a busca por item da armadilha": ["ROTINA.md"],
        "Roteiro de 3 mensagens": DOCS,
        "`errata_…` é correção para o leitor": DOCS,                  # a errata nao chega mais a fila
        "sem ele, Read de `/tmp/email.html`": DOCS,                    # §R6: o arquivo e o da linha CAMINHO
        "Armadilhas desatualizadas no ledger": ["README.md"],          # migradas pelo helper
        # volta 2
        "inscrição definitiva: `outro`)": ["ROTINA.md"],               # lido como "'outro' para tudo menos a prova"
        "(`RECUSADO … titulo generico: …` = linha de rodapé": ["work/prompts/coletor-jota.md"],  # so o generico
        # volta 3 (CORE P2/P3): o DIVERGE nao corrigido suspende o selo por data (antes: so tirava a "banca lida")
        "corrija `prazos`/`linha` (senão: sem carimbo e AVISO ACIONÁVEL)": ["ROTINA.md"],
        "não conta como banca lida no selo": ["docs/referencia-operacional.md"],
        "tira do carimbo e do selo por data o registro": ["README.md"],
        # rodada de 21/11/2026
        "Corpo por anexo de referência": ["README.md"],                # o Apps Script nao muda (decisao do dono)
        "2ª notificação": ["ROTINA.md", "docs/referencia-operacional.md", "README.md"],   # uma notificacao so
        "robozinho/socorro": DOCS,                                     # push so na main
        "Limitação ao leitor só para edição anunciada": ["ROTINA.md"],  # informativos_docs e do montador
        "STJ Jurisprudência | só oficial: teses do CodJu": ["ROTINA.md"],
        "Decisão pendente do dono: modelo do orquestrador": ["README.md"],   # Fable, decidido
        "acima de 1,3 × a mediana das 10 execuções": ["README.md"],    # ALERTA_ECONOMIA antigo
        "some os do Gmail (linhas `BUSCAS` dos coletores)": ["ROTINA.md"],   # os gmail_* saem de buscas_gmail
        "e a nota de confirmação (STJ Jurisprudência": ["robozinho-dos-momozis-prompt.md"],   # sem nota por item
        "uma sonda só: `presidencia.gov.br": ["docs/referencia-operacional.md"],   # agora from:presidencia.gov.br
    }
    achados = ["%s em %s" % (t, rel) for t, onde in proibidos.items() for rel in onde if t in ler(rel)]
    assert not achados, "; ".join(achados)


@teste
def linhas_procuradas_sao_impressas_pelos_scripts():
    esperado = {
        "aguardar_coleta.py": ["SOURCE_STATUS ", "AINDA RODANDO", "--teto", "--mais", "s desde o disparo",
                               "saída já impressa inteira na chamada anterior"],
        "inicio.py": ["SELO POR DATA", "PRAZO VENCIDO (sem ação): ", "FERIADO HOJE", "FERIADOS NA JANELA",
                      "dia útil sem execução registrada",
                      "(feriado: a edição sai em feriado)", "ALERTA: selo por data — ",
                      "candidato a remoção", "RE-EXECUÇÃO", "--extra", "--refazer", "aguardar_coleta.py"],
        "bancas.py": ["DIVERGE DO REGISTRO", "SEM REGISTRO", "da mesma sigla, é de outro cargo", "registro incerto",
                      "AVISO: página não cobre", "def divergencias_pendentes"],
        "selos.py": ["prorrogação não confirmada", "encerradas → selo INSCRIÇÕES ENCERRADAS",
                     "o selo que a nova data dá", "def selo_escrito", "BANCAS_OFICIAIS", "def tipo_contradiz_evento"],
        "feriados.py": ["def dia_de_edicao"],
        "paginas_oficiais.py": ["PAGINA OFICIAL"],
        "informativos.py": ["EM ATRASO", "SEM EDICAO NOVA", "SEGUE SEM CONTEUDO", "ERRO PARSER", "TECNICO",
                            "(com resumo)", "não verificável"],
        "versiculo.py": ["VERSICULO ok |", "VERSICULO ok=false"],
        "coleta_web.py": ["[REPETIDA?~", "JA PUBLICADAS", "SEM_DATA_OFICIAL", "SEM NORMA NOVA NA JANELA",
                          "ERRO: congresso_mpv", "PLANALTO_ATO"],
        "montar_email.py": ["MONTAGEM: OK COM AVISOS", "AVISO ACIONÁVEL", "DESCARTADA", "BYTES: ", "SHA256: ",
                            "CAMINHO: ", "email-com-avisos.html", "execucao.resolvido.json", "num prazo cujo evento é",
                            '<span style="display:none">fim-%s</span>', "\\n</td></tr></table>"],
        "jota_extrair.py": ["JOTA_EXTRAIR", "[L%d]", "jota_urls.tsv"],
        "resolver_jota.py": ["JA_PUBLICADA", "RECUSADO", "SEM_MATCH", "SEM_LINK", "BLOQUEADO", "jota_links.tsv",
                             "titulo de descadastro ou preferencias (%s)"],
        "finalizar.sh": ["PUSH: FALHOU", "ESTADO:", "STATUS: OK", "execucao.resolvido.json", "--draft-id",
                         "--message-id", "--trailer", "REMONTAGEM: ", "PERSISTENCIA ABORTADA",
                         "o execucao.json editado depois da montagem mudou os itens", "NAO commite"],
        "Update-Historico.py": ["ALERTA_ECONOMIA", "modelo do orquestrador mudou", "sem --message-id",
                                "ausente_em_sent", "contradiz o selo por data", "contadores ja aplicados",
                                "num prazo cujo evento é"],
    }
    faltando = []
    for script, textos in esperado.items():
        codigo = open(os.path.join(WORK, script), encoding="utf-8").read()
        faltando += ["%s: %r" % (script, t) for t in textos if t not in codigo]
    assert not faltando, "; ".join(faltando)


@teste
def rotina_cita_o_que_os_scripts_imprimem():
    r = ler("ROTINA.md")
    for t in ("python3 work/inicio.py", "python3 work/aguardar_coleta.py", "python3 work/montar_email.py",
              "bash work/finalizar.sh", "SOURCE_STATUS", "AINDA RODANDO", "EM ATRASO", "SEM EDICAO NOVA",
              "SEGUE SEM CONTEUDO", "ERRO PARSER", "VERSICULO ok=false", "MONTAGEM: OK COM AVISOS",
              "AVISO ACIONÁVEL", "DESCARTADA", "BYTES", "SHA256", "CAMINHO", "/tmp/email-com-avisos.html",
              "/tmp/execucao.resolvido.json", "fim-<execution_id>", "SELO POR DATA", "DIVERGE DO REGISTRO",
              "dia útil sem execução registrada", "PUSH: FALHOU", "ALERTA_ECONOMIA",
              "ALERTA: modelo do orquestrador mudou", "allow_large", "larger:", "0,9 × `BYTES`", "REMONTAGEM:",
              "ALERTA: o execucao.json editado depois da montagem mudou os itens", "PERSISTENCIA ABORTADA",
              "AVISO: diferenca local … NAO commite", "PENDÊNCIA DE VERIFICAÇÃO", "prorrogação não confirmada",
              "cita item descartado", "contradiz o selo por data", "num prazo cujo evento é", "inscricoes_fim",
              "§R10", "§R11", "§R12"):
        assert t in r, "ROTINA nao cita %r" % t


@teste
def formatos_copiados_dos_coletores_sao_entendidos():
    import montar_email as m
    g = ler("work/prompts/coletor-gmail.md")
    assert "resenha: <assunto exato do e-mail> | recebida <DD/MM HH:MM>" in g
    assert "DOU <DD/MM/AAAA>[ (edição extra)]" in g
    exemplo = "Resenha Diária PUSH Legislação - 13/11/2026 (edição extra) | recebida 14/11 01:43"
    assert m.grupo_resenha(exemplo) == "Resenha Diária PUSH Legislação de 13/11 — edição extra (recebida em 14/11, 01h43)", \
        m.grupo_resenha(exemplo)
    assert m.norm_meta("DOU 13/11/2026 (edição extra)") == "DOU 13/11 · edição extra"
    assert m.norm_meta("DOU 13/11 · edição extra") == "DOU 13/11 · edição extra"       # o formato da ROTINA
    assert "`meta` = `DOU DD/MM[ · edição extra]`" in ler("ROTINA.md")


@teste
def arquivo_de_itens_do_jota_e_lido_pelo_resolver():
    import resolver_jota
    j = ler("work/prompts/coletor-jota.md")
    assert "<título exato> [L<n>]" in j and "<título exato><TAB><wrapper t.rdsv2.net>" in j
    assert '"${ROBOZINHO_TMP:-/tmp}/jota_links.tsv"' in j and "python3 work/resolver_jota.py" in j
    d = tempfile.mkdtemp(prefix="test_doc_")
    try:
        p = os.path.join(d, "jota_links.tsv")
        with open(p, "w", encoding="utf-8") as f:
            f.write("STF decide X [L12]\nOutro título\thttps://t.rdsv2.net/ls/click?upn=abc\nClipping só título\n")
        assert resolver_jota.ler_linhas(p) == [("STF decide X", "L12"),
                                              ("Outro título", "https://t.rdsv2.net/ls/click?upn=abc"),
                                              ("Clipping só título", "")]
    finally:
        shutil.rmtree(d, ignore_errors=True)
    # o resolver, sem argumento, le $ROBOZINHO_TMP/jota_links.tsv (o mesmo caminho do heredoc)
    assert 'os.path.join(TMP, "jota_links.tsv")' in ler("work/resolver_jota.py")


@teste
def ids_de_source_status():
    import montar_email as m
    r = ler("ROTINA.md")
    linha = next(l for l in r.splitlines() if l.startswith("- `source_status`"))
    dos_coletores = set(re.findall(r"`(gmail_[a-z_]+)`", linha))
    dos_scripts = {"congresso_ultimas_leis", "congresso_mpvs", "camara_noticias", "camara_legin", "conjur", "migalhas",
                   "informativos_docs",
                   "youversion", "dailyverses"}
    assert dos_coletores | dos_scripts == set(m.ROTULO_FONTE), \
        "ROTINA %s + scripts != montador %s" % (sorted(dos_coletores), sorted(m.ROTULO_FONTE))
    for i in dos_scripts:                    # cada id de script sai na linha SOURCE_STATUS de algum script
        assert any(i in open(os.path.join(WORK, s), encoding="utf-8").read()
                   for s in ("coleta_web.py", "versiculo.py", "informativos.py")), i


@teste
def toolsearch_do_passo_1():
    r = ler("ROTINA.md")
    m = re.search(r"ToolSearch `select:([^`]+)`", r)
    assert m, "ToolSearch do passo 1 ausente"
    ferramentas = set(m.group(1).split(","))
    assert {"mcp__Gmail__search_threads", "mcp__Gmail__list_drafts", "mcp__Gmail__get_draft",
            "mcp__Gmail__create_draft", "WebSearch"} <= ferramentas, ferramentas


@teste
def agentes_e_entrega_condicional():
    r = ler("ROTINA.md")
    for nome, precisa in (("coletor-gmail", ["mcp__Gmail__search_threads", "mcp__Gmail__get_thread"]),
                          ("coletor-jota", ["Bash", "WebSearch", "mcp__Gmail__get_thread"]),
                          ("coletor-concursos", ["Bash", "WebSearch"])):
        txt = ler(".claude/agents/%s.md" % nome)
        fm = txt.split("---")[1]
        assert re.search(r"^name: %s$" % nome, fm, re.M), nome
        assert re.search(r"^model: \w+", fm, re.M), nome
        tools = re.search(r"^tools: (.+)$", fm, re.M).group(1)
        for t in precisa:
            assert t in tools, "%s sem %s" % (nome, t)
        assert "SubagentHandback, quando existir" in txt, nome
        assert "`%s`" % nome in r, "ROTINA nao lanca %s" % nome
        assert "SubagentHandback (quando existir)" in ler("work/prompts/%s.md" % nome), nome
        prompt = ler("work/prompts/%s.md" % nome)
        assert "nunca conclua ausência" not in prompt, "%s: contrato de evidencia duplicado no prompt" % nome
    assert "SubagentHandback, quando existir" in r


@teste
def coletor_concursos_alinhado_ao_codigo():
    import montar_email as m
    import selos
    c = ler("work/prompts/coletor-concursos.md")
    sel = re.search(r"Selos possíveis: (.+?)\.", c).group(1)
    nomes = [re.sub(r"\s*\(.*$", "", x).strip() for x in sel.split(", ")]
    assert set(nomes) <= set(selos.SELOS_CONCURSO), set(nomes) - set(selos.SELOS_CONCURSO)
    carreiras = re.search(r"Carreiras cobertas, na ordem do e-mail: (.+?)\.\n", c).group(1).split(" · ")
    assert carreiras == m.BLOCOS + [m.APOIO], carreiras
    for t in ("URL individual", "data visível", "número do ato", "RADAR |", "URL_OFICIAL |", "?p=",
              "até 7 dias ou vencido há até 3 dias", "raiz do domínio", "inscrição ou prova em até 14 dias"):
        assert t in c, "coletor-concursos sem %r" % t
    assert "[%s]" % "alego_procurador" in "".join("%s [%s]" % ("x", i) for i in ["alego_procurador"])
    assert '"%s [%s]" % (orgao(c), c.get("id"))' in ler("work/inicio.py"), "ids dos acompanhados nao vem prontos"


@teste
def coletor_jota_e_gmail_alinhados():
    j = ler("work/prompts/coletor-jota.md")
    for t in ("**até 8**", "**até 4**", "BASTIDOR |", "JA_PUBLICADA |", "DESCARTADOS |", "RECUSADO",
              "python3 work/jota_extrair.py", "não leia o arquivo"):
        assert t in j, "coletor-jota sem %r" % t
    assert "DESCARTADO |" not in j, "DESCARTADO por item voltou"
    g = ler("work/prompts/coletor-gmail.md")
    for t in ("CAMARA_RESTO |", "PLANALTO_ATO |", "só das threads da janela", "messageCount"):
        assert t in g, "coletor-gmail sem %r" % t
    assert "Descartados" not in g


@teste
def ramos_R_apontados_existem():
    r = ler("ROTINA.md")
    d = ler("docs/referencia-operacional.md")
    for n in sorted(set(re.findall(r"§R(\d+)", r + ler("robozinho-dos-momozis-prompt.md")))):
        assert "### R%s." % n in d, "§R%s nao existe na referencia" % n


@teste
def rotina_seis_turnos_e_enxuta():
    r = ler("ROTINA.md")
    assert "**6 turnos**" in r
    for cab in ("## 1. ", "## 2. ", "## 3. ", "## 4 e 5. ", "## 6. ", "## 7 e 8. "):
        assert cab in r, cab
    n = len(r.encode("utf-8"))
    assert n <= ROTINA_TETO_BYTES, "ROTINA com %d bytes (teto %d; em 16/11, %d)" % (
        n, ROTINA_TETO_BYTES, ROTINA_ANTERIOR_BYTES)
    for imutavel in ("**Imutável:**", "identidade visual", "padrão de prova", "não existe \"depois eu corrijo\"",
                     "Economizar **verificação**, nunca", "**Rascunho mínimo viável:**", "Nunca `update_draft`",
                     "**nunca** o execute \"à mão\"", "descarte o que os coletores trouxeram e não crie rascunho"):
        assert imutavel in r, "ROTINA perdeu %r" % imutavel


@teste
def munger_sem_caminhos_locais():
    with open(os.path.join(WORK, "munger-quotes.json"), encoding="utf-8") as f:
        q = json.load(f)
    assert all("arquivo" not in x for x in q.get("fontes", []))
    texto = open(os.path.join(WORK, "munger-quotes.json"), encoding="utf-8").read()
    assert "C:\\\\" not in texto and "Downloads" not in texto
    assert len(q["quotes"]) == 200 and all(x.get("tipo") in ("licao", "aforismo") for x in q["quotes"])


def codigo_unido(rel):
    """Fonte com as mensagens partidas em varias linhas juntadas: `echo "a" \\` + `"b"` (bash, com espaco) e
    literais Python adjacentes (sem espaco), para procurar o texto que o script de fato imprime."""
    s = ler(rel)
    s = re.sub(r'"\s*\\\n\s*"', " ", s)
    return re.sub(r'"\s*\n\s*"', "", s)


def secao(rel, titulo, proxima):
    s = ler(rel)
    return s[s.index(titulo):s.index(proxima) if proxima else len(s)]


def bloco_de_codigo(rel, secao, proxima):
    """Primeiro bloco ``` ... ``` entre os titulos `secao` e `proxima` do arquivo."""
    s = ler(rel)
    trecho = s[s.index(secao):s.index(proxima)]
    m = re.search(r"```\n(.*?)```", trecho, re.S)
    assert m, "%s: %s sem bloco de codigo" % (rel, secao)
    return trecho, m.group(1)


@teste
def informativo_resumo_nao_e_tese():
    # o informativos.py extrai a caixa RESUMO do Informativo STF, nao a "Tese fixada" (contrato INF §9)
    for rel in DOCS:
        assert "tese oficial" not in ler(rel), "%s chama o resumo do Informativo de tese oficial" % rel
    r = ler("ROTINA.md")
    assert "`(com resumo)` = resumo oficial do julgado, **não** a tese fixada" in r
    assert "estágio e tese por tema" in r
    codigo = ler("work/informativos.py")
    assert '" (com resumo)" if it.get("resumo")' in codigo and '" (com tese)" if it["tese"]' in codigo
    assert "resumo oficial de cada julgado (STF) e a tese de cada tema (RG em Pauta)" in \
        ler("robozinho-dos-momozis-prompt.md")


@teste
def selo_ao_entrar_na_familia_bate_com_selos_py():
    """A regra que a ROTINA e o coletor dao para o selo escrito ao entrar na familia de datas e a mesma do
    selos.selo_por_data: escrito assim, o calculo nao o contradiz (o escrito prevalece no montador)."""
    import selos
    from datetime import date, timedelta
    r = ler("ROTINA.md")
    for t in ("**Ao entrar nela** (inclusive `NOVO`), escreva o que a data dá hoje",
              "copiar o selo do registro é inofensivo, selo **diferente** dele é decisão e prevalece",
              "fim das inscrições hoje `ENCERRA HOJE`", "em até %d dias `ENCERRA EM BREVE`" % selos.EM_BREVE_DIAS,
              "prova em até %d dias `PROVA EM BREVE`" % selos.PROVA_BREVE_DIAS, "senão (já abertas) `INSCRIÇÕES ABERTAS`",
              "aviso `… contradiz o selo por data` = corrija"):
        assert t in r, "ROTINA sem %r" % t
    assert "(`EM PLANEJAMENTO` → `INSCRIÇÕES ABERTAS`" not in r, "exemplo antigo de entrada na familia voltou"
    assert "contradiz o selo por data" in ler("work/Update-Historico.py"), "AVISO citado nao existe no helper"
    c = ler("work/prompts/coletor-concursos.md")
    assert "Selo de data sugerido = o que a data dá hoje" in c and "um script recalcula" not in c
    for t in ("fim das inscrições hoje → ENCERRA HOJE", "em até %d dias → ENCERRA EM BREVE" % selos.EM_BREVE_DIAS,
              "prova em até %d dias → PROVA EM BREVE" % selos.PROVA_BREVE_DIAS):
        assert t in c, "coletor-concursos sem %r" % t

    def regra(fim, prova, hoje):           # a regra escrita na ROTINA, na ordem dela
        if fim == hoje:
            return "ENCERRA HOJE"
        if fim and 0 < (fim - hoje).days <= selos.EM_BREVE_DIAS:
            return "ENCERRA EM BREVE"
        if prova and 0 <= (prova - hoje).days <= selos.PROVA_BREVE_DIAS:
            return "PROVA EM BREVE"
        return "INSCRIÇÕES ABERTAS"

    hoje = date(2026, 11, 17)
    for d_fim, d_prova in ((0, 60), (1, 60), (7, 60), (8, 60), (30, 60), (20, 10), (3, 10)):
        fim, prova = hoje + timedelta(d_fim), hoje + timedelta(d_prova)
        selo = regra(fim, prova, hoje)
        reg = {"id": "x", "selo": selo, "fonte": "https://www.trf2.jus.br/concurso/edital", "prazos": [
            {"data": (hoje - timedelta(7)).isoformat(), "evento": "início das inscrições", "confirmado": True,
             "tipo": "inscricoes_inicio"},
            {"data": fim.isoformat(), "evento": "fim das inscrições", "confirmado": True, "tipo": "inscricoes_fim"},
            {"data": prova.isoformat(), "evento": "prova objetiva", "confirmado": True, "tipo": "prova"}]}
        novo, motivo = selos.selo_por_data(reg, hoje)
        assert (novo, motivo) == (selo, None), "fim +%d, prova +%d: regra %r, selos.py %r (%s)" % (
            d_fim, d_prova, selo, novo, motivo)


@teste
def create_draft_com_erro_confere_rascunho_e_enviada():
    # (21/11) o ramo foi para a §R13; o passo 6 guarda o ponteiro e a proibicao de recriar sem conferir
    r = ler("ROTINA.md")
    passo6 = r[r.index("## 6. "):r.index("## 7 e 8. ")]
    assert "**Erro ou timeout** → §R13 antes de qualquer nova tentativa" in passo6 and "**não recrie**" in passo6
    r13 = secao("docs/referencia-operacional.md", "### R13.", None)
    antes = r13[:r13.index("1 nova tentativa")]
    assert '`list_drafts` com `subject:"<ASSUNTO>"`' in antes, "erro do create_draft sem list_drafts"
    assert '`search_threads` com `subject:"<ASSUNTO>" in:sent`' in antes, "erro do create_draft sem in:sent"
    assert "**não recrie**" in antes and "nada nas duas" in antes
    assert "**não** rode o `finalizar.sh`" in r13


@teste
def r4_espera_em_mensagem_propria_e_conta_do_disparo():
    trecho, bloco = bloco_de_codigo("docs/referencia-operacional.md", "### R4.", "### R5.")
    assert "--teto 480" not in trecho and "na mensagem do Write" not in trecho
    for t in ("numa mensagem própria, antes do Write", "timeout: 300000", "`email.limitacoes`", "informativos_docs"):
        assert t in trecho, "§R4 sem %r" % t
    assert bloco.strip() == "python3 work/aguardar_coleta.py --mais 240", bloco
    assert "§R4, antes do Write" in ler("ROTINA.md")
    assert "(`timeout: 300000`): `python3 work/aguardar_coleta.py`" in ler("ROTINA.md")
    # os formatos citados na §R4 sao os que o script imprime
    codigo = codigo_unido("work/aguardar_coleta.py")
    for t in ("s desde o disparo): saída parcial abaixo; a fonte fica sem status",
              "s desde o disparo) — para esperar mais: python3 work/aguardar_coleta.py --mais N",
              "saída já impressa inteira na chamada anterior"):
        assert t in trecho and t in codigo, "§R4 x aguardar_coleta.py: %r" % t
    assert re.search(r"CHAMADA_S = (\d+)", codigo).group(1) == "90" and "até 90 s" in ler("ROTINA.md")
    # disparo ha 10 min, informativos vivo que so termina daqui a 6 s (> os 5 s do teto ja vencido)
    import time
    from datetime import datetime, timedelta, timezone
    d = tempfile.mkdtemp(prefix="test_doc_r4_")
    try:
        ex = "2026-11-17-7h"
        json.dump({"execution_id": ex, "data": "2026-11-17"}, open(os.path.join(d, "janela.json"), "w"))
        for nome in ("coleta_web", "versiculo"):
            open(os.path.join(d, "passo2-%s.out" % nome), "w").write("SOURCE_STATUS {}\n")
            open(os.path.join(d, "passo2-%s.rc" % nome), "w").write("0\n")
        dummy = subprocess.Popen([sys.executable, "-c",
                                  "import os,sys,time\ntime.sleep(6)\nd=sys.argv[1]\n"
                                  "open(os.path.join(d,'passo2-informativos.out'),'w').write('stf1237 NOVA\\n')\n"
                                  "open(os.path.join(d,'passo2-informativos.rc'),'w').write('0\\n')\n", d])
        disparo = (datetime.now(timezone(timedelta(hours=-3))) - timedelta(seconds=600)).isoformat(timespec="seconds")
        json.dump({"execution_id": ex, "disparado_em": disparo, "pids": {"informativos": dummy.pid}},
                  open(os.path.join(d, "passo2-disparo.json"), "w"))
        t0 = time.time()
        r = subprocess.run(["bash", "-c", bloco], cwd=RAIZ, env=dict(os.environ, ROBOZINHO_TMP=d),
                           capture_output=True, text=True, timeout=120)
        dummy.wait()
        assert r.returncode == 0, r.stderr[-300:]
        assert "AINDA RODANDO" not in r.stdout and "stf1237 NOVA" in r.stdout, r.stdout[-400:]
        assert time.time() - t0 >= 5.5, "nao esperou o script"
    finally:
        shutil.rmtree(d, ignore_errors=True)


@teste
def r5_versiculo_gravado_por_bash():
    import montar_email as m
    trecho, bloco = bloco_de_codigo("docs/referencia-operacional.md", "### R5.", "### R6.")
    assert "**Bash**" in trecho and "**antes** do Bash do montador" in trecho
    r = ler("ROTINA.md")
    assert "grave `/tmp/versiculo.json` pelo Bash da §R5, antes do montador" in r
    d = tempfile.mkdtemp(prefix="test_doc_r5_")
    try:
        p = os.path.join(d, "versiculo.json")
        tent = [{"fonte": "YouVersion", "http": 403, "motivo": "desafio anti-bot ou pagina vazia"}]
        json.dump({"ok": False, "tentativas": tent, "source_status": {"youversion": "falha", "dailyverses": "falha"}},
                  open(p, "w", encoding="utf-8"))          # o versiculo.py grava o arquivo tambem com ok=false
        cheio = (bloco.replace("<site de onde veio>", "DailyVerses.net").replace("João 16:28", "Salmos 23:1")
                 .replace("<copiado da página>", 'O Senhor é o meu \\"pastor\\"; nada me faltará.')
                 .replace("AAAA-MM-DD", "2026-11-17").replace("<página do dia>", "https://dailyverses.net/pt/2026/11/17"))
        r = subprocess.run(["bash", "-c", cheio], cwd=RAIZ, env=dict(os.environ, ROBOZINHO_TMP=d),
                           capture_output=True, text=True, timeout=30)
        assert r.returncode == 0, r.stderr[-300:]
        v = json.load(open(p, encoding="utf-8"))
        assert v["ok"] is True and v["texto"] == 'O Senhor é o meu "pastor"; nada me faltará.', v
        assert v["tentativas"] == tent and v["source_status"]["youversion"] == "falha"
        html = m.sec_versiculo(v, "reflexão")
        assert "nada me faltará" in html and "Salmos 23:1" in html and "não recuperado" not in html
        os.remove(p)                                          # sem arquivo (script morto): grava assim mesmo
        r = subprocess.run(["bash", "-c", cheio], cwd=RAIZ, env=dict(os.environ, ROBOZINHO_TMP=d),
                           capture_output=True, text=True, timeout=30)
        assert r.returncode == 0 and json.load(open(p, encoding="utf-8"))["ok"] is True, r.stderr[-300:]
    finally:
        shutil.rmtree(d, ignore_errors=True)


@teste
def linhas_do_finalizar_citadas_existem_no_codigo():
    """Os trechos das linhas do finalizar.sh que a §R9/§R11 e a ROTINA citam sao impressos por ele."""
    fin = codigo_unido("work/finalizar.sh")
    r9 = secao("docs/referencia-operacional.md", "### R9.", "### R10.")
    r11 = secao("docs/referencia-operacional.md", "### R11.", "### R12.")
    for t, onde in (("execucao.json é mais novo que a última montagem", r11),
                    ("REMONTAGEM: itens iguais aos da montagem anterior (", r11),
                    ("REMONTAGEM: corpo ", r11),
                    ("ALERTA: o execucao.json editado depois da montagem mudou os itens (", r11),
                    ("PERSISTENCIA ABORTADA: ", r11), ("a remontagem deu ERRO (acima) — corrija o ", r11),
                    ("rode python3 work/montar_email.py e repita o finalizar.sh", r11),
                    ("o helper nao terminou com STATUS: OK", r11), ("nao encontrado", r11),
                    ("PUSH: recusado (main andou no remoto) — reaplicando o helper sobre origin/main", r11),
                    ("AVISO: reset --keep recusado (alteracao local fora do estado)", r11),
                    ("AVISO: diferenca local depois da reaplicacao em ", r11),
                    ("nao e da execucao de hoje: NAO commite", r11),
                    ("— para reaplicar: tar -xzf", r9), ("da 1a rodada, sobre a main anterior a mudanca concorrente) — "
                                                       "NAO aplique o tar sobre a main atual (apagaria a mudanca "
                                                       "concorrente): rode bash work/finalizar.sh de novo com os "
                                                       "mesmos argumentos (entrada em", r9)):
        assert t in onde, "referencia nao cita %r" % t
        assert t in fin, "finalizar.sh nao imprime %r" % t
    # "REMONTAGEM: MONTAGEM: OK[ COM AVISOS]" e montada na hora: echo "REMONTAGEM: $(grep ... MONTAGEM: OK...)"
    assert "`REMONTAGEM: MONTAGEM: OK[ COM AVISOS]`" in r11
    assert re.search(r'echo "REMONTAGEM: \$\(grep -m1 -oE \'\^MONTAGEM: OK\( COM AVISOS\)\?\'', fin), "REMONTAGEM: MONTAGEM"
    # a recusa de hook do servidor nao conta como "main andou" (o que a §R9 diz)
    assert "[remote rejected]" in r9 and 'non-fast-forward|fetch first|\\[rejected\\]' in fin
    # o finalizar repetido substitui o registro de hoje sem repetir os contadores (o que a §R11 promete)
    assert "contadores ja aplicados" in r11 and "contadores ja aplicados" in ler("work/Update-Historico.py")


@teste
def segunda_notificacao_cobre_o_que_os_scripts_mandam_notificar():
    r = ler("ROTINA.md")
    ultima = r[r.index("**Última mensagem: a notificação**"):r.index("## Regras editoriais")]
    for t in ("PERSISTENCIA ABORTADA", "PUSH: FALHOU", "ALERTA: o execucao.json editado depois da montagem mudou os itens",
              "ALERTA: modelo do orquestrador mudou", "ALERTA_ECONOMIA", "ALERTA: edicao anterior … sem --message-id",
              "AVISO: diferenca local", "§R6",
              # (21/11, persistencia) linhas novas que vao ao dono
              "STATUS: ERRO INTERNO", "TRAVA:", "ALERTA: mecânico dos concursos com fallback",
              "ALERTA: migracao … recusada", "`USO:`"):
        assert t in ultima, "notificacao sem %r" % t
    # toda linha de script que pede "diga/avise na notificacao" esta na lista, pelo comeco fixo dela
    achadas = 0
    for rel in ("work/finalizar.sh", "work/Update-Historico.py"):
        for lit in re.findall(r'"((?:ALERTA|AVISO)[^"]*notifica[^"]*)"', codigo_unido(rel)):
            fixo = re.split(r"%| \(", lit, maxsplit=1)[0].strip().rstrip(":")      # o comeco fixo da linha
            assert fixo in ultima, "%s: %r pede notificacao e nao esta na 2a" % (rel, fixo)
            achadas += 1
    assert achadas >= 2, "nenhuma linha 'notificacao' achada nos scripts (o teste ficou cego)"
    # (21/11) uma notificacao so, na mensagem seguinte a do finalizar.sh: antes ela ia junto e saia otimista (o ALERTA
    # do finalizar.sh so chegava ao dono por uma 2a notificacao)
    p78 = r[r.index("## 7 e 8. "):r.index("**Última mensagem")]
    assert "bash work/finalizar.sh" in p78 and "PushNotification" not in p78, "notificacao na mensagem do finalizar.sh"
    assert "depois de ler a saída do `finalizar.sh`" in ultima and "a única do dia" in ultima
    assert "**6 turnos** (passo 1 · 2 · 3–5 · 6 · 7 · 8)" in r and "Bash (`timeout: 300000`): `bash work/finalizar.sh" in p78
    # o finalizar.sh cabe no timeout: as esperas do push mais 5 tentativas de ROBOZINHO_LIMITE_REDE s ficam abaixo de 300 s
    fin = ler("work/finalizar.sh")
    esperas = re.search(r'ROBOZINHO_PUSH_ESPERAS:-([\d ]+)', fin).group(1).split()
    limite = int(re.search(r'ROBOZINHO_LIMITE_REDE:-(\d+)', fin).group(1))
    assert sum(map(int, esperas)) + len(esperas) * limite < 300, (esperas, limite)


@teste
def rebaixamento_e_selo_copiado_batem_com_selos_py():
    """O que a ROTINA/§R12 mandam fazer com o selo vencido e com o selo copiado e o que o selos.py faz."""
    import selos
    from datetime import date, timedelta
    r = ler("ROTINA.md")
    r12 = secao("docs/referencia-operacional.md", "### R12.", None)
    for t in ("não vira `INSCRIÇÕES ENCERRADAS`: cai para `PENDÊNCIA DE VERIFICAÇÃO` e lá fica",
              "encerradas → `INSCRIÇÕES ENCERRADAS`", "**e** o selo que a nova data dá", "sem confirmação, nada (§R12)"):
        assert t in r, "ROTINA sem %r" % t
    hoje = date(2026, 11, 19)
    fonte = "https://www.tjap.jus.br/concurso"
    venc = {"id": "x", "selo": "ENCERRA HOJE", "fonte": fonte, "prazos": [
        {"data": "2026-11-18", "evento": "fim das inscrições", "confirmado": True, "tipo": "inscricoes_fim"}]}
    # 1) sem a banca lida: cai para PENDENCIA DE VERIFICACAO com o texto que a ROTINA resume
    novo, motivo = selos.selo_por_data(venc, hoje)
    assert novo == selos.SELO_SEM_CONFIRMACAO == "PENDÊNCIA DE VERIFICAÇÃO", (novo, motivo)
    for no_codigo, na_doc in (("prorrogação não confirmada", "`prorrogação não confirmada`"),
                              ("encerradas → selo INSCRIÇÕES ENCERRADAS", "encerradas → `INSCRIÇÕES ENCERRADAS`"),
                              ("o selo que a nova data dá (ENCERRA HOJE / ENCERRA EM BREVE / INSCRIÇÕES ABERTAS)",
                               "o selo que a nova data dá (`ENCERRA HOJE` / `ENCERRA EM BREVE` / `INSCRIÇÕES ABERTAS`")):
        assert no_codigo in motivo, "selos.py mudou o texto: %r" % no_codigo
        assert na_doc in r + r12, "ROTINA/§R12 sem %r" % na_doc
    # com a banca lida (sem retificacao posterior), ENCERRADAS e automatico
    assert selos.selo_por_data(venc, hoje, banca_lida_hoje=True)[0] == "INSCRIÇÕES ENCERRADAS"
    # 2) de PENDENCIA nada muda sozinho: prazo novo SEM selo escrito deixa o selo -> a ROTINA manda escrever
    pend = dict(venc, selo="PENDÊNCIA DE VERIFICAÇÃO", prazos=[
        {"data": (hoje + timedelta(2)).isoformat(), "evento": "fim das inscrições (prorrogado)", "confirmado": True}])
    assert selos.selo_por_data(pend, hoje) == ("PENDÊNCIA DE VERIFICAÇÃO", None)
    assert "PENDÊNCIA DE VERIFICAÇÃO" not in selos.FAMILIA_DATA and "fora da família de datas" in r12
    # 3) o que a ROTINA manda escrever nao e contradito pelo selo por data (sem AVISO "contradiz")
    assert selos.selo_por_data(dict(pend, selo="ENCERRA EM BREVE"), hoje) == ("ENCERRA EM BREVE", None)
    assert selos.selo_por_data(dict(venc, selo="INSCRIÇÕES ENCERRADAS"), hoje) == ("INSCRIÇÕES ENCERRADAS", None)
    assert selos.selo_por_data(dict(pend, selo="INSCRIÇÕES ABERTAS"), hoje)[0] == "ENCERRA EM BREVE"  # o erro
    assert "INSCRIÇÕES ENCERRADAS" not in selos.SELOS_EXIGEM_OFICIAL and "não exige fonte oficial" in r12
    # 4) copia do selo nao e decisao; selo diferente (ou concurso novo) e
    assert not selos.selo_escrito({"selo": "ENCERRA HOJE"}, {"selo": "ENCERRA HOJE"})
    assert selos.selo_escrito({"selo": "INSCRIÇÕES ENCERRADAS"}, {"selo": "ENCERRA HOJE"})
    assert selos.selo_escrito({"selo": "ENCERRA HOJE"}, None)
    # 5) prazos[].tipo: os valores da ROTINA e da §R12 sao os do selos.py (volta 2: a ROTINA so listava `prova` e
    #    `outro`, lido como "'outro' para tudo que nao e a prova"), e os exemplos classificam como dito
    item_tipo = r[r.index("- `prazos[].tipo`"):r.index("ERRO na validação", r.index("- `prazos[].tipo`"))]
    assert set(re.findall(r"`(inscricoes_inicio|inscricoes_fim|prova|outro)`", item_tipo)) == set(selos.TIPOS_PRAZO), \
        item_tipo
    assert set(re.findall(r"`(inscricoes_inicio|inscricoes_fim|prova|outro)`", r12)) == set(selos.TIPOS_PRAZO)
    for t in ("(opcional; prevalece sobre o `evento`)", "`prova` (só a data da prova)", "na dúvida, omita"):
        assert t in item_tipo, "ROTINA, prazos[].tipo, sem %r" % t
    for ev, cl in (("resultado preliminar da prova objetiva", "outro"), ("gabarito da prova objetiva", "outro"),
                   ("edital de convocação para as provas", "outro"), ("locais de prova", "outro"),
                   ("inscrição definitiva", "outro"), ("prova objetiva", "prova"),
                   ("fim das inscrições, 16h (prorrogado)", "inscricoes_fim"),
                   ("data limite para inscrições", "inscricoes_fim"),
                   ("inscrições a partir de 10/12", "inscricoes_inicio")):
        assert selos.classe_prazo({"evento": ev, "data": "2026-12-01"}) == cl, ev
    # 6) dominio oficial: a regra descrita (so a fonte, so orgao ou banca da lista)
    assert selos.fonte_oficial("https://conhecimento.fgv.br/concursos/tjap26")
    assert not selos.fonte_oficial("https://www.estrategiaconcursos.com.br/blog/tjap", "tjap.jus.br")


@teste
def item_escrito_e_avisos_alinhados_ao_montador():
    """O que a ROTINA diz do item escrito, do e-mail e dos avisos acionaveis e o que o montador faz."""
    import montar_email as m
    r = ler("ROTINA.md")
    # fonte sem URL: so o rotulo oficial puro vale
    assert 'sem `url`, oficial só o rótulo puro, como "STJ CodJu": "X (via JOTA)" é mídia' in r
    assert m.item_oficial({"fonte": "STJ CodJu"}) and m.item_oficial({"fonte": "PUSH Planalto"})
    assert not m.item_oficial({"fonte": "STJ (via JOTA)"}) and not m.item_oficial({"fonte": "JOTA (decisão do STJ)"})
    # meta: o resto depois do DOU fica
    assert "`meta` = `DOU DD/MM[ · edição extra]` (o resto, após `; `, fica)" in r
    assert m.norm_meta("DOU 13/11 (republicação por incorreção)") == "DOU 13/11; republicação por incorreção"
    # email.suporte e ignorado; limitacoes com detalhe tecnico dao AVISO
    assert "`email.suporte`; nem código http, script ou id com `_` em `limitacoes`/`observacoes`" in r
    codigo = ler("work/montar_email.py")
    assert "email.suporte ignorado" in codigo and "traz detalhe técnico ao leitor" in codigo
    # RG: a ordem vale dentro de cada estagio
    assert "(na RG, dentro de cada estágio)" in r and "vale dentro de cada estágio" in codigo
    # avisos acionaveis citados na ROTINA casam o ACIONAVEL do montador
    for aviso in ("card do resumo «Concursos» cita item descartado («x», REPUBLICADA): troque o card",
                  "ledger_updates.concursos.x.selo: 'INSCRIÇÕES ABERTAS' escrito hoje contradiz o selo por data "
                  "'ENCERRA EM BREVE' (…)",
                  "selo por data: x ENCERRA HOJE → PENDÊNCIA DE VERIFICAÇÃO: … prorrogação não confirmada — …"):
        assert m.ACIONAVEL.search(aviso), aviso
    assert "`card … cita item descartado` → outro item no card (ou no preheader), ou `\"desdobramento\": true`" in r


def modelo_para_regex(modelo):
    """Texto citado na doc com marcadores (<id>, <n>, '<tipo>', «<evento>», …, <porquê>) -> regex do texto real."""
    partes = re.split(r"<[^<>]+>|…", modelo)
    return ".+?".join(re.escape(p) for p in partes)


@teste
def tipo_de_prazo_e_aviso_acionavel_batem_com_o_codigo():
    """(volta 2) A ROTINA:59 listava so `prova`/`outro`; com `tipo: "outro"` no fim das inscricoes o selo por data
    se desligava sem aviso (INSCRIÇÕES ABERTAS a 2 dias do fim). Confere: o tipo errado da o AVISO acionavel que a
    ROTINA e a §R12 citam (montador = helper); a correcao que eles mandam fazer resolve; o que eles mandam marcar
    como `outro` nao gera o aviso; a linha PRAZO VENCIDO (sem ação) da §R12 e a que o inicio.py imprime."""
    import importlib.util
    from datetime import date
    import montar_email as m
    import selos
    r = ler("ROTINA.md")
    r12 = secao("docs/referencia-operacional.md", "### R12.", None)
    spec = importlib.util.spec_from_file_location("update_historico_test_doc", os.path.join(WORK, "Update-Historico.py"))
    h = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(h)
    hoje = date(2026, 11, 19)                     # o cenario do reteste: TJAP prorrogado ate 21/11, banca nao lida
    reg = {"id": "tjap_juiz", "selo": "INSCRIÇÕES ABERTAS", "fonte": "https://conhecimento.fgv.br/concursos/tjap26",
           "prazos": [{"data": "2026-11-18", "evento": "fim das inscrições, 16h", "confirmado": True}]}
    por_id = {"tjap_juiz": reg}

    def upd(tipo):
        p = {"data": "2026-11-21", "evento": "fim das inscrições, 16h (prorrogado)", "confirmado": True}
        if tipo:
            p["tipo"] = tipo
        return {"tjap_juiz": {"prazos": [p, {"data": "2027-01-24", "evento": "prova objetiva (prevista)",
                                             "confirmado": True, "tipo": "prova"}]}}

    # 1) o defeito: com 'outro' o selo por data ignora o prazo
    assert selos.selo_por_data(dict(reg, prazos=upd("outro")["tjap_juiz"]["prazos"]), hoje) == \
        ("INSCRIÇÕES ABERTAS", None)
    # 2) o aviso: uma linha, a mesma no montador e no helper, acionavel, no formato citado
    av = m.tipo_contra_evento(upd("outro"), por_id, hoje, {})
    assert len(av) == 1 and av == h.avisos_tipo_prazo(upd("outro"), por_id, hoje), (av, h.avisos_tipo_prazo(
        upd("outro"), por_id, hoje))
    a = av[0]
    assert m.ACIONAVEL.search("AVISO ACIONÁVEL: " + a) and m.ACIONAVEL.search(a), a
    assert "o selo por data daria 'ENCERRA EM BREVE'" in a, a
    citado = re.search(r"`AVISO ACIONÁVEL: (ledger_updates\.concursos\.<id>\.prazos\[<n>\]\.tipo: [^`]+)`", r12)
    assert citado, "§R12 sem o AVISO de prazos[<n>].tipo"
    assert re.fullmatch(modelo_para_regex(citado.group(1)), a), (citado.group(1), a)
    assert "`prazos[n].tipo: … num prazo cujo evento é …` → o `tipo` que ele diz, ou omita o `tipo`" in r
    assert re.search(modelo_para_regex("prazos[n].tipo: … num prazo cujo evento é …").replace(r"\[n\]", r"\[\d+\]"), a)
    # 3) a correcao que a ROTINA/§R12 mandam (tipo que o aviso diz, ou sem tipo) resolve e religa o selo por data
    for t in ("inscricoes_fim", None):
        assert m.tipo_contra_evento(upd(t), por_id, hoje, {}) == [] == h.avisos_tipo_prazo(upd(t), por_id, hoje), t
        assert selos.selo_por_data(dict(reg, prazos=upd(t)["tjap_juiz"]["prazos"]), hoje)[0] == "ENCERRA EM BREVE", t
    assert selos.tipo_contradiz_evento({"evento": "início das inscrições", "tipo": "outro"}) == "inscricoes_inicio"
    # 4) o que a ROTINA e a §R12 mandam marcar como `outro` (e a prova como `prova`) nao da aviso falso
    for ev in ("resultado preliminar da prova objetiva", "gabarito da prova objetiva", "recurso contra o gabarito",
               "edital de convocação para as provas", "locais de prova", "inscrição definitiva",
               "pagamento da taxa de inscrição"):
        assert selos.tipo_contradiz_evento({"evento": ev, "tipo": "outro"}) is None, ev
    assert selos.tipo_contradiz_evento({"evento": "prova objetiva", "tipo": "prova"}) is None
    # 5) PRAZO VENCIDO (sem ação): citado na §R12 como o inicio.py imprime
    c = re.search(r"`(PRAZO VENCIDO \(sem ação\): [^`]+)`", r12)
    assert c, "§R12 sem a linha PRAZO VENCIDO (sem ação)"
    assert "PRAZO VENCIDO (sem ação): %s — encerramento confirmado pela banca oficial lida hoje (%s): " \
           "selo INSCRIÇÕES ENCERRADAS automático" in codigo_unido("work/inicio.py")
    exemplo = ("PRAZO VENCIDO (sem ação): 18/11 (ontem) TJAP — fim das inscrições, 16h (prorrogado) [confirmado] "
               "(id tjap_juiz) — encerramento confirmado pela banca oficial lida hoje (última retificação 13/11): "
               "selo INSCRIÇÕES ENCERRADAS automático")
    assert re.fullmatch(modelo_para_regex(c.group(1)), exemplo), c.group(1)


@teste
def rodape_do_jota_recusado_nao_vira_item():
    """(volta 2, WEB) A linha cujo titulo e o proprio rodape sai `RECUSADO … titulo de descadastro ou preferencias
    (…)`, sem pedido nem ao wrapper; o coletor-jota.md diz que ela nao vira item (antes so citava `titulo
    generico`). Manchete parecida com rodape passa."""
    import resolver_jota as rj
    j = ler("work/prompts/coletor-jota.md")
    assert "`RECUSADO … titulo de descadastro ou preferencias (…)`, inclusive `titulo generico: …` = linha de " \
           "rodapé copiada" in j and "não vira item" in j
    ctx = rj.Contexto()
    for titulo in ("Você recebeu este e-mail porque se cadastrou no JOTA. Para sair, clique aqui", "clique aqui",
                   "Caso não queira mais receber estes e-mails, cancele sua inscrição",
                   "Obrigado pela leitura. Para sair, clique aqui"):
        out = rj.resolve((titulo, "https://t.rdsv2.net/ls/click?upn=teste"), ctx)
        assert out.startswith("RECUSADO\t") and "\ttitulo de descadastro ou preferencias (" in out, out
    out = rj.resolve(("Você recebeu este e-mail? Golpe usa o nome do STF", ""), ctx)
    assert out.startswith("SEM_LINK\t"), out          # sem link, mas e item (o coletor publica "sem link")


@teste
def roteiros_dos_coletores_comecam_por_read_e_toolsearch():
    """O prompt do Agent (ROTINA passo 2) obriga a 1a mensagem com Read + ToolSearch: todo roteiro a conta."""
    r = ler("ROTINA.md")
    assert "Na sua primeira mensagem, juntos: Read de /tmp/coletor-X.md e ToolSearch" in r
    for nome in ("gmail", "jota", "concursos"):
        c = ler("work/prompts/coletor-%s.md" % nome)
        m = re.search(r"Roteiro de (\d+) mensagens[^\n]*", c)
        assert m, "coletor-%s sem roteiro" % nome
        passos = re.findall(r"\((\d+)\) ", m.group(0))
        assert passos and passos == [str(i) for i in range(1, int(m.group(1)) + 1)], (nome, m.group(1), passos)
        assert "(1) Read deste arquivo + ToolSearch" in m.group(0), "coletor-%s: 1a mensagem nao e Read+ToolSearch" % nome
    c = ler("work/prompts/coletor-concursos.md")
    assert "confirmação da mensagem 3" in c and "turno 2" not in c


@teste
def r6_r10_criterios_executaveis():
    r = ler("ROTINA.md")
    r6 = secao("docs/referencia-operacional.md", "### R6.", "### R7.")
    # recriar do arquivo da linha CAMINHO (com avisos aceitos, o email.html nem existe) e repetir com e sem larger:
    assert "arquivo da linha `CAMINHO`" in r6 and "/tmp/email-com-avisos.html" in r6
    assert "com `subject:\"<ASSUNTO>\" larger:<N>`" in r6 and "`subject:\"<ASSUNTO>\" in:sent larger:<N>`" in r6
    assert "atraso de indexação" in r6
    codigo = ler("work/montar_email.py")
    assert '"email-com-avisos.html"' in codigo or "email-com-avisos.html" in codigo
    # dia util sem registro: criterio pela hora do envio da edicao achada, sem get_thread
    assert "achou → §R10 (o que tem data e hora até o envio dela já saiu nela)" in r
    r10 = secao("docs/referencia-operacional.md", "### R10.", "### R11.")
    for t in ("data **e** hora até esse envio", "nem como herdado", "`verification_notes`", "Não abra a enviada",
              "(feriado: a edição sai em feriado)"):
        assert t in r10, "§R10 sem %r" % t
    assert "get_thread" not in re.search(r"ToolSearch `select:([^`]+)`", r).group(1)   # nao e carregado no passo 1


# ------------------------------------------------------------------ volta 3 (CORE P2/P3, WEB P5, INF P6)
TRECHO_EDITAL = "das 16h do dia 19 de outubro de 2026 até às 16h do dia 26 de novembro de 2026"
FONTE_TJSC = "https://conhecimento.fgv.br/concursos/tjscjuiz26"


def helper():
    import importlib.util
    spec = importlib.util.spec_from_file_location("update_historico_test_doc", os.path.join(WORK, "Update-Historico.py"))
    h = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(h)
    return h


def linha_tjsc(fim):
    return "TJSC — Juiz Substituto: 50 vagas, FGV; inscrições de 19/10 até 16h de %s; prova em 24/01/2027" % fim


def prazos_tjsc(fim, evento="fim das inscrições, 16h"):
    return [{"data": fim, "evento": evento, "confirmado": True},
            {"data": "2027-01-24", "evento": "prova objetiva", "confirmado": True, "tipo": "prova"}]


def cenario_tjsc(hoje, fim_registro, selo):
    """Registro com o fim das inscricoes em `fim_registro` e o bancas.json de `hoje` com o edital relido hoje (fim
    26/11), como o bancas.analisar o grava (inscricoes.lido_em = hoje)."""
    import bancas
    reg = {"id": "tjsc_juiz", "bloco": "Magistratura", "selo": selo, "verificado_em": "2026-11-16",
           "fonte": FONTE_TJSC, "linha": linha_tjsc(fim_registro[8:10] + "/11"), "prazos": prazos_tjsc(fim_registro)}
    banca = {"banca": "FGV", "dominio": bancas.DOMINIO, "http": 200, "data": hoje, "concursos": [{
        "slug": "tjscjuiz26", "url": FONTE_TJSC, "http": 200, "coberto": ["tjsc_juiz"], "registros": ["tjsc_juiz"],
        "ultima_retificacao": None, "releitura": "prazo do registro", "divergencias": [],
        "inscricoes": {"inicio": "2026-10-19", "fim": "2026-11-26", "trecho": TRECHO_EDITAL, "origem": "edital",
                       "lido_em": hoje},
        "arquivos": [{"data": "2026-10-01", "titulo": "Edital de abertura", "url": FONTE_TJSC + "/edital.pdf"}]}]}
    return reg, banca


def mecanico_do_helper(h, reg, banca, upd, hoje):
    """O que a gravacao (finalizar.sh -> helper) faz com o registro: aplicar_updates + aplicar_mecanicos_concursos.
    Devolve (registro gravado, linhas do relatorio)."""
    import copy
    led, u, log = {"concursos": [copy.deepcopy(reg)]}, {"concursos": copy.deepcopy(upd)}, []
    h.aplicar_updates(led, u, hoje, log.append)
    h.aplicar_mecanicos_concursos(led, u, hoje, banca, log.append)
    return led["concursos"][0], log


@teste
def selo_suspenso_e_prazo_contra_edital_batem_com_o_codigo():
    """(volta 3, CORE P2/P3) Com o edital lido hoje contestando o fim das inscricoes do registro (DIVERGE) ou o prazo
    escrito hoje, o selo por data fica SUSPENSO (bancas.selo_do_dia, a regra unica de helper, montador e inicio) e
    saem dois avisos acionaveis novos. Confere: os modelos citados na §R12 sao o que o codigo imprime; o que a ROTINA
    manda fazer resolve (prazos E linha; so a linha nao basta; selo escrito so com ato oficial mais novo, e entao o
    que a data da); as linhas de gravacao estao na 2a notificacao; o passo 1 as cita como o inicio.py imprime."""
    import bancas
    import montar_email as m
    import selos
    from datetime import date
    h = helper()
    r = ler("ROTINA.md")
    r12 = secao("docs/referencia-operacional.md", "### R12.", None)
    ultima = r[r.index("**Última mensagem: a notificação**"):r.index("## Regras editoriais")]
    passo1 = r[r.index("- **`ALERTA:`**"):r.index("- **Ledger:**")]
    concursos = r[r.index("**Concursos — a seção sai"):r.index("## 4 e 5. ")]

    # 1) P2: DIVERGE da manha (registro 25/11, edital lido hoje 26/11): o selo por data sairia da data contestada
    hoje = date(2026, 11, 18)
    reg, b = cenario_tjsc("2026-11-18", "2026-11-25", "INSCRIÇÕES ABERTAS")
    assert selos.selo_por_data(reg, hoje)[0] == "ENCERRA EM BREVE"          # o defeito que a suspensao evita
    pend = bancas.divergencias_pendentes(b, [reg], hoje, {})
    assert set(pend) == {"tjsc_juiz"} and not pend["tjsc_juiz"]["escrito_hoje"], pend
    ctx = bancas.contexto_selos(b, [reg], hoje, {})
    selo, motivo, susp = bancas.selo_do_dia(reg, hoje, ctx, pend)
    assert (selo, motivo) == ("INSCRIÇÕES ABERTAS", None) and susp, (selo, motivo, susp)
    assert m.ACIONAVEL.search(susp), susp
    citado = re.search(r"`(selo por data suspenso em <id>: [^`]+)`", r12)
    assert citado, "§R12 sem o modelo da linha do selo suspenso"
    assert re.fullmatch(modelo_para_regex(citado.group(1)), susp), (citado.group(1), susp)
    # a mesma linha nos tres scripts, com o prefixo que a doc diz
    assert 'out.append("ALERTA: " + s)' in ler("work/inicio.py") and \
        "bancas.selo_do_dia(c, hoje, ctx_selo, pend_selo)" in ler("work/inicio.py")
    assert 'add_log("ALERTA: " + suspenso)' in ler("work/Update-Historico.py")
    assert "bancas.selo_do_dia(c, hoje, ctx_banca, pendentes)" in ler("work/montar_email.py")
    for t in ("`AVISO ACIONÁVEL: selo por data suspenso em <id>", "`ALERTA: selo por data suspenso em <id>"):
        assert t in r12, "§R12 sem %r" % t
    # passo 1: o ALERTA vem com o DIVERGE e no lugar do SELO POR DATA desse id
    for t in ("`selo por data suspenso em <id>`", "`DIVERGE DO REGISTRO`", "`SELO POR DATA`"):
        assert t in passo1, "ROTINA, passo 1 (ALERTA), sem %r" % t
    # so a linha nao basta (os prazos prevalecem no fim das inscricoes do registro); prazos e linha resolvem
    so_linha = {"tjsc_juiz": {"linha": linha_tjsc("26/11")}}
    assert set(bancas.divergencias_pendentes(b, [reg], hoje, so_linha)) == {"tjsc_juiz"}
    certo = {"tjsc_juiz": {"linha": linha_tjsc("26/11"), "prazos": prazos_tjsc("2026-11-26")}}
    assert bancas.divergencias_pendentes(b, [reg], hoje, certo) == {}
    gravado, log = mecanico_do_helper(h, reg, b, certo, "2026-11-18")
    assert gravado["verificado_em"] == "2026-11-18" and gravado["selo"] == "INSCRIÇÕES ABERTAS" and \
        not any("suspenso" in x for x in log), (gravado, log)                # carimbo e selo por data de volta
    for t in ("corrija `prazos` **e** `linha`", "só a `linha` não basta"):
        assert t in concursos, "ROTINA, concursos, sem %r" % t
    # sem correcao: na gravacao, ALERTA (2a notificacao) e o registro fica sem carimbo, com o selo de antes
    gravado, log = mecanico_do_helper(h, reg, b, {}, "2026-11-18")
    assert any(x.startswith("ALERTA: selo por data suspenso em tjsc_juiz") for x in log), log
    assert gravado["verificado_em"] == "2026-11-16" and gravado["selo"] == "INSCRIÇÕES ABERTAS", gravado
    # data do registro vinda de ato oficial mais novo: o selo escrito (diferente do registro) prevalece e encerra a
    # suspensao; a copia do selo atual nao conta (o aviso continua: aceite-o)
    gravado, log = mecanico_do_helper(h, reg, b, {"tjsc_juiz": {"selo": "ENCERRA EM BREVE"}}, "2026-11-18")
    assert gravado["selo"] == "ENCERRA EM BREVE" and not any("suspenso" in x for x in log), (gravado, log)
    gravado, log = mecanico_do_helper(h, reg, b, {"tjsc_juiz": {"selo": "INSCRIÇÕES ABERTAS"}}, "2026-11-18")
    assert any(x.startswith("ALERTA: selo por data suspenso") for x in log), log
    assert "ato oficial mais novo que o edital" in concursos and "igual ao atual é cópia" in r12

    # 2) P3: registro = edital (26/11); o update de hoje escreve 05/12 (retificacao que a leitura das 7h nao trazia)
    hoje = date(2026, 11, 20)
    reg, b = cenario_tjsc("2026-11-20", "2026-11-26", "ENCERRA EM BREVE")
    assert bancas.divergencias_pendentes(b, [reg], hoje, {}) == {}, "pré-condição: registro igual ao edital"
    novo = {"tjsc_juiz": {"prazos": prazos_tjsc("2026-12-05", "fim das inscrições, 16h (prorrogado)"),
                          "linha": linha_tjsc("05/12"), "fonte": "https://conhecimento.fgv.br/concursos/tjscjuiz26"}}
    pend = bancas.divergencias_pendentes(b, [reg], hoje, novo)
    assert pend["tjsc_juiz"]["escrito_hoje"], pend
    av = h.avisos_ledger_updates({"concursos": novo}, {"concursos": [reg]}, "2026-11-20", b)
    p3 = [a for a in av if a.startswith(h.PRAZO_CONTRA_EDITAL)]
    assert len(p3) == 1 and not any(a.startswith("DIVERGE DO REGISTRO em tjsc_juiz") for a in av), av
    assert m.ACIONAVEL.search(p3[0]), p3[0]
    citado = re.search(r"`(prazo escrito hoje difere do edital lido hoje: <id> [^`]+)`", r12)
    assert citado, "§R12 sem o modelo da linha do prazo escrito hoje"
    assert re.fullmatch(modelo_para_regex(citado.group(1)), p3[0]), (citado.group(1), p3[0])
    assert "`prazo escrito hoje difere do edital lido hoje`" in concursos
    # gravacao: o mesmo texto como ALERTA (o --validar fica AVISO, que o montador mostra como acionavel)
    assert re.search(r'add_log\(\("ALERTA: " if not args\.validar and a\.startswith\(PRAZO_CONTRA_EDITAL\) '
                     r'else "AVISO: "\) \+ a\)', ler("work/Update-Historico.py"))
    # aceitar sem o selo deixa o selo da data antiga (ENCERRA EM BREVE para 05/12): a doc manda escrever o que a
    # nova data da; escrito, prevalece, nao "contradiz o selo por data" e nao ha suspensao
    gravado, log = mecanico_do_helper(h, reg, b, novo, "2026-11-20")
    assert gravado["selo"] == "ENCERRA EM BREVE" and any("ALERTA: selo por data suspenso" in x for x in log), log
    com_selo = {"tjsc_juiz": dict(novo["tjsc_juiz"], selo="INSCRIÇÕES ABERTAS")}
    av = h.avisos_ledger_updates({"concursos": com_selo}, {"concursos": [reg]}, "2026-11-20", b)
    assert not any("contradiz o selo por data" in a for a in av) and any(a.startswith(h.PRAZO_CONTRA_EDITAL)
                                                                       for a in av), av
    gravado, log = mecanico_do_helper(h, reg, b, com_selo, "2026-11-20")
    assert gravado["selo"] == "INSCRIÇÕES ABERTAS" and not any("suspenso" in x for x in log), (gravado, log)
    assert "retificação" in concursos and "o selo que a nova data dá" in secao(
        "docs/referencia-operacional.md", "- **Selo por data suspenso", "- **Domínio oficial.")

    # 3) 2a notificacao: as duas linhas de gravacao (o registro ficou contestado pela banca)
    for t in ("ALERTA: prazo escrito hoje difere do edital lido hoje", "ALERTA: selo por data suspenso"):
        assert t in ultima, "2a notificacao sem %r" % t


@teste
def resumo_cortado_nao_se_completa_nem_se_copia():
    """(volta 3, WEB/CORE P5) A linha de noticia do coleta_web termina em "…" quando a linha-fina passa de 170
    caracteres (so o indice e cortado; o JSON tem a inteira) ou veio cortada da fonte (resumo_truncado). Pelo `ref`, o
    montador poe a inteira ou fecha a cortada com "…"; o texto copiado do indice para `resumo` sairia cortado."""
    import coleta_web as cw
    import montar_email as m
    r = ler("ROTINA.md")
    passo2 = r[r.index("- **`coleta_web`**"):r.index("- **`informativos`**")]
    assert "Linha-fina terminada em `…`: não a complete nem a copie para o `resumo`" in passo2, passo2
    inteira = ("A 2ª Turma do STJ decidiu que a busca domiciliar sem mandado exige fundadas razões, registradas antes "
               "do ingresso, e anulou as provas obtidas quando os policiais fazem a invasão de domicílio sem elas.")
    ev = {"c1": {"_fonte": "conjur", "titulo": "STJ anula provas de busca domiciliar", "resumo": inteira,
                 "url": "https://www.conjur.com.br/2026-nov-17/stj-anula-provas/", "quando": "2026-11-17T10:00:00",
                 "tipo": "noticia"}}
    indice = cw.curto(inteira, 170)
    assert indice.endswith("…") and len(indice) <= 170
    assert m.resolver({"ref": "c1"}, ev, [])["resumo"] == inteira                   # pelo ref: a inteira
    assert m.resolver({"ref": "c1", "resumo": indice}, ev, [])["resumo"] == indice  # copiado: sai cortado
    cortada = dict(ev["c1"], resumo="O STJ vai avaliar se policiais que entram sem mandado fazem a invasão de",
                   resumo_truncado=True)
    assert m.resolver({"ref": "c1"}, {"c1": cortada}, [])["resumo"].endswith("invasão de…")
    assert 'extra += "…"' in ler("work/coleta_web.py")


@teste
def readme_cita_as_regras_novas_da_volta_3():
    """(volta 3) O README descreve a regra unica do selo por data e a origem do trecho de inscricoes (CORE), a
    linha-fina cortada (WEB), a conferencia de temas da RG (INF) e a regra unica de descadastro do JOTA (WEB); e o
    codigo tem cada nome citado."""
    rd = ler("README.md")
    linha = {nome: next(l for l in rd.splitlines() if l.startswith("- `work/%s`" % nome))
             for nome in ("bancas.py", "selos.py", "coleta_web.py", "informativos.py", "jota_extrair.py",
                          "montar_email.py")}
    for nome, textos in (("bancas.py", ["`selo_do_dia`", "`inscricoes_do_dia`", "`inscricoes.lido_em`",
                                        "`divergencias_pendentes`", "prazo escrito hoje"]),
                         ("selos.py", ["`bancas.selo_do_dia`"]),
                         ("coleta_web.py", ["`resumo_truncado`"]),
                         ("montar_email.py", ["`…`"]),
                         ("informativos.py", ["`temas de rg<m>=<http>`", "`TECNICO`"]),
                         ("jota_extrair.py", ["`descadastro_no_texto`"])):
        for t in textos:
            assert t in linha[nome], "README, %s, sem %r" % (nome, t)
    for script, textos in (("bancas.py", ["def selo_do_dia", "def inscricoes_do_dia", '["lido_em"]']),
                           ("coleta_web.py", ['"resumo_truncado"']),
                           ("montar_email.py", ["def resumo_cortado"]),
                           ("informativos.py", ["temas de "]),
                           ("jota_extrair.py", ["def descadastro_no_texto"])):
        codigo = ler("work/" + script)
        for t in textos:
            assert t in codigo, "%s sem %r" % (script, t)


# ------------------------------------------------------------------ rodada de 21/11/2026 (integracao das frentes)
@teste
def buscas_gmail_deriva_os_gmail_oficiais():
    """A ROTINA manda copiar a linha BUSCAS do coletor-gmail em `buscas_gmail` e NAO escrever os gmail_* oficiais: o
    montador so os deriva quando o id nao foi escrito (status_gmail), entao um 'ok' escrito esconderia o silencio."""
    import montar_email as m
    r = ler("ROTINA.md")
    linha = next(l for l in r.splitlines() if l.startswith("- `source_status`"))
    derivados = set(re.findall(r"`(gmail_[a-z_]+)`", linha.split("saem de `buscas_gmail`")[0])) - {"gmail_jota"}
    assert derivados == set(m.BUSCA_GMAIL.values()), (derivados, m.BUSCA_GMAIL)
    assert "gmail_jota" not in m.BUSCA_GMAIL.values() and "não os escreva" in linha and "só `falha`" in linha
    assert '"buscas_gmail": "<linha BUSCAS do coletor-gmail>"' in r
    assert "A linha `BUSCAS` do coletor-gmail vai inteira em `\"buscas_gmail\"`" in r
    g = ler("work/prompts/coletor-gmail.md")
    assert "BUSCAS | a=<na janela>/<total> b=… c=… d=… e=…" in g and "`a=2/3 b=0/1 c=0/0 d=1/1 e=0/2`" in g
    achados = {x.group(1): x.group(3) for x in m.RE_BUSCA_GMAIL.finditer("a=2/3 b=0/1 c=0/0 d=1/1 e=0/2")}
    assert set(achados) == set("abcde") and all(achados.values()), achados
    # quarta-feira a quinta-feira, sem feriado nem recesso: silencio do push diario e 'vazio', o semanal e 'ok'
    j = {"inicio": "2026-11-18T07:05:00-03:00", "fim": "2026-11-19T07:05:00-03:00", "data": "2026-11-19"}
    ex = {"buscas_gmail": "a=0/2 b=0/0 c=0/0 d=0/1 e=0/0 | abertas=0"}
    m.status_gmail(ex, j, [])
    assert ex["source_status"] == {"gmail_push_stf": "vazio", "gmail_push_stf_informativos": "ok",
                                   "gmail_stj_codju": "ok", "gmail_push_planalto": "vazio", "gmail_camara": "ok"}, \
        ex["source_status"]
    escrito = {"buscas_gmail": ex["buscas_gmail"], "source_status": {"gmail_push_stf": "ok"}}
    m.status_gmail(escrito, j, [])
    assert escrito["source_status"]["gmail_push_stf"] == "ok", "o escrito prevalece (por isso a ROTINA nao o escreve)"


@teste
def stj_teses_vai_para_stj_jurisprudencia():
    import montar_email as m
    r = ler("ROTINA.md")
    linha = next(l for l in r.splitlines() if l.startswith("| STJ Jurisprudência |"))
    modelo = re.search(r'`titulo` "([^"]+)"', linha).group(1)
    assert "`STJ_TESES`" in linha and modelo == "Jurisprudência em Teses nº N — <tema>", linha
    assert "STJ_TESES | <número da edição> | <tema da edição, exato> | <data do e-mail> |" in ler(
        "work/prompts/coletor-gmail.md")
    it = {"categoria": "Informativos", "titulo": modelo.replace("N", "270").replace("<tema>", "Direito Penal"),
          "data": "2026-11-20"}
    m.teses_stj(it, [])
    assert it["categoria"] == "STJ Jurisprudência" and it["fonte"] == m.JT_FONTE, it
    assert "Jurisprudência em Teses" in m.ROTULO_FONTE["gmail_stj_codju"] or m.item_oficial({"fonte": m.JT_FONTE})


@teste
def legin_e_resenha_no_ref():
    """Os ids do LEGIN citados na ROTINA sao os que o coleta_web atribui, a fonte do status e camara_legin, e o ref
    de lei/MPV/decreto com `resenha` do PUSH sai com grupo, fonte e selo do PUSH (FONTES_ATO_RESENHA)."""
    import montar_email as m
    r = ler("ROTINA.md")
    for t in ("`dec13173`", "`lc239`", "`ec141`", "`dleg…`", "fonte `camara_legin`",
              '`lei…`/`mpv…`/`dec…` que também veio na resenha do PUSH: `{"ref", "resenha"}`'):
        assert t in r, "ROTINA sem %r" % t
    cw = ler("work/coleta_web.py")
    assert '"camara_legin"' in cw and "dec13173, lc239, ec141, dleg123" in cw
    assert {"congresso_leis", "congresso_mpv", "legin"} <= set(m.FONTES_ATO_RESENHA)
    novo = {}
    m.resenha_no_ref(novo, {"ref": "dec13173", "resenha": "Resenha Diária PUSH Legislação - 19/11/2026 (edição "
                                                          "extra) | recebida 19/11 21:10"},
                     {"_fonte": "legin"}, "dec13173", [])
    assert novo.get("grupo") and novo.get("fonte") == "PUSH Planalto" and \
        novo.get("status") == "CONFIRMADO POR FONTE OFICIAL", novo
    assert "rotina (créditos, LOA, LDO, PPA, PLN)" in r and "ementa inteira" in r


@teste
def concursos_campos_novos_e_movimento():
    import montar_email as m
    h = helper()
    r = ler("ROTINA.md")
    esquema = r[r.index('"concursos": {id: {'):r.index('| {remover: true, desfecho}}, "armadilhas_detectadas"')]
    assert "banca_slug" in esquema and "movimento" in esquema, esquema
    assert {"banca_slug", "movimento"} <= h.CAMPOS_EDITAVEIS["concursos"] and "movimento" in h.NAO_GRAVA
    assert '`"movimento": false`' in r and "`ENCERRADO` → `remover` com `desfecho`" in r
    for v, esperado in ((False, True), ("false", True), (True, False), (None, False)):
        campos = {} if v is None else {"movimento": v}
        assert m.sem_movimento(campos) is esperado and h.sem_movimento(campos) is esperado, v
    assert h.RE_BANCA_SLUG.fullmatch("exames/enam/6exame") and not h.RE_BANCA_SLUG.fullmatch("Tjap26")
    assert "RODIZIO | <id do registro> | IGUAL|MUDOU|ENCERRADO" in ler("work/prompts/coletor-concursos.md")
    assert "<tipo: inscricoes_inicio|inscricoes_fim|prova|outro>" in ler("work/prompts/coletor-concursos.md")


@teste
def linhas_novas_do_passo_1_e_da_banca_existem():
    """O que a ROTINA e a §R12 mandam procurar na saida do passo 1 e o que os scripts imprimem; a linha MOVIMENTO
    sem registro some no dia seguinte (por isso a ROTINA manda avaliar no mesmo dia)."""
    import bancas
    from datetime import date
    r = ler("ROTINA.md")
    r12 = secao("docs/referencia-operacional.md", "### R12.", "### R13.")
    for t in ("`vínculo pela fonte`", "`CANDIDATO`", "`CANDIDATO a registro NOVO`", "`NOVA EDIÇÃO?`",
              "`- MOVIMENTO sem registro` → avalie hoje como NOVO", "`PAGINA OFICIAL`", "`LIDA (1ª vez)`", "`RELIDA`",
              "`FORA DO ESCOPO`", "`REDE do ambiente: LIBERADO…`", "`MIGRACAO … aplicada`",
              "`ALERTA: migracao … recusada`", "passadas as inscrições, `EM ANDAMENTO`"):
        assert t in r, "ROTINA sem %r" % t
    for script, textos in (
            ("bancas.py", ['[vínculo pela fonte: grave banca_slug="%s"]', "CANDIDATO %s ← %s |",
                           "'CANDIDATO a registro NOVO %s ← %s |", "'NOVA EDIÇÃO? %s |", '"- MOVIMENTO sem registro: ']),
            ("paginas_oficiais.py", ['"MUDOU"', '"LIDA (1ª vez)"', '"RELIDA (formato novo: confira com o registro)"']),
            ("inicio.py", ["FORA DO ESCOPO (apoio só", '"REDE do ambiente: "', "LIBERADO pelo proxy",
                           "COBERTA PELO PRAZO de %s (acima)", "SÓ VIGIAR MOVIMENTO NOVO",
                           "PRAZO VENCIDO (só secundária; desfecho já buscado pelo coletor, sem busca hoje)"]),
            ("migracoes.py", ['"MIGRACAO %s: aplicada (%d concursos, %d pendências)%s"',
                              '"ALERTA: migracao %s recusada: %s"'])):
        codigo = codigo_unido("work/" + script)
        for t in textos:
            assert t in codigo, "%s nao imprime %r" % (script, t)
    for t in ("[vínculo pela fonte: grave banca_slug=", "`CANDIDATO <id> ← <slug>", "`NOVA EDIÇÃO? <slug>",
              "`- MOVIMENTO sem registro: <slug>", "**no mesmo dia**", "`COBERTA PELO PRAZO de <id>`",
              "`SÓ VIGIAR MOVIMENTO NOVO`", "`RELIDA (formato novo: confira com o registro)`"):
        assert t in r12, "§R12 sem %r" % t
    a = {"data": "2026-11-20", "titulo": "Resultado da Prova Oral", "url": "https://conhecimento.fgv.br/x.pdf"}
    c, hoje = {"arquivos": [a]}, date(2026, 11, 23)
    assert bancas.movimento(c, {}, hoje) == [a]                                       # nunca visto: aparece
    assert bancas.movimento(c, {bancas.chave_arquivo(a): "2026-11-23"}, hoje) == [a]  # visto hoje: ainda novo
    assert bancas.movimento(c, {bancas.chave_arquivo(a): "2026-11-22"}, hoje) == []   # visto ontem: sumiu


@teste
def escopo_do_apoio_igual_ao_codigo():
    import escopo
    r = ler("ROTINA.md")
    ufs = re.search(r"Escopo do dono: carreiras finais, todo o país; apoio, só ([A-Z, ]+) ou órgão nacional", r)
    assert ufs and tuple(u.strip() for u in ufs.group(1).split(",")) == escopo.UFS_APOIO, ufs and ufs.group(1)
    for rel in ("robozinho-dos-momozis-prompt.md", "README.md", "docs/referencia-operacional.md"):
        assert "SP, RJ, MG, ES, PR, SC" in ler(rel) and "RS" in ler(rel), rel
    assert "SP, RJ, MG, ES, PR, SC ou RS" in escopo.TEXTO_ESCOPO_APOIO


@teste
def finalizar_e_helper_linhas_novas_e_push_so_na_main():
    """(persistencia) As linhas novas que a ROTINA e a §R11 citam sao impressas; a trava de sanidade nao se repete;
    nenhuma outra branch e empurrada (a tarefa agendada so autoriza push na main)."""
    h = helper()
    r = ler("ROTINA.md")
    r11 = secao("docs/referencia-operacional.md", "### R11.", "### R12.")
    fin = codigo_unido("work/finalizar.sh")
    hl = codigo_unido("work/Update-Historico.py")
    for t in ('"RESTAURADO: os arquivos de estado de work/ voltaram ao que eram antes do helper',
              "PERSISTENCIA ABORTADA: trava de sanidade (linhas TRAVA acima",
              "Não edite o estado nem o código: avise o dono com as linhas TRAVA",
              "REAPLICACAO: ", '"ESTADO: '):
        assert t in fin, "finalizar.sh sem %r" % t
    assert "STATUS: ERRO INTERNO %s — nada foi gravado no estado" in hl and '"USO: custo total US$ %.2f' in hl
    assert h.ALERTA_FALLBACK.startswith("ALERTA: mecânico dos concursos com fallback")
    for t in ("`REAPLICACAO:`", "`RESTAURADO:`", "`STATUS: ERRO INTERNO`", "`ESTADO:`", "`TRAVA:`", "`USO:`"):
        assert t in r, "ROTINA sem %r" % t
    assert "a da trava de sanidade (`TRAVA:`) não: só notifique" in r
    for t in ("**`STATUS: ERRO INTERNO", "**`TRAVA: …`**", "**`RESTAURADO:", "`REAPLICACAO: …`"):
        assert t in r11, "§R11 sem %r" % t
    pushes = re.findall(r"git push[^\n]*", fin)
    assert pushes and all("origin main" in x for x in pushes), pushes
    assert "socorro" not in re.sub(r"(?m)^\s*#.*$", "", fin), "branch de socorro voltou ao finalizar.sh"
    assert "a tarefa agendada só autoriza push na `main`" in r or "só autoriza push nela" in r


@teste
def migracoes_reais_aplicam_sem_alerta_e_regras_de_armadilha_vivas():
    """As migracoes de work/migracoes/ aplicam sobre uma copia do ledger vivo sem ALERTA e uma vez so; toda regra de
    REGRAS_ATUALIZADAS ainda casa o ledger (texto antigo ou ja o novo: senao a migracao morreu calada); a nota de
    fonte das migracoes cabe no limite e o essencial do CodJu aparece no LEDGER impresso (NOTA_CURTA)."""
    import migracoes
    import inicio
    from datetime import date
    h = helper()
    d = tempfile.mkdtemp(prefix="test_doc_migr_")
    try:
        shutil.copy(os.path.join(WORK, "robozinho-aprendizado.json"), d)
        shutil.copytree(os.path.join(WORK, "migracoes"), os.path.join(d, "migracoes"))
        linhas = migracoes.aplicar(date(2026, 11, 23), work_dir=d)
        assert not [x for x in linhas if x.startswith("ALERTA")], linhas
        assert migracoes.aplicar(date(2026, 11, 23), work_dir=d) == [], "reaplicou"
        with open(os.path.join(d, "robozinho-aprendizado.json"), encoding="utf-8") as f:
            led = json.load(f)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ids = {os.path.basename(p)[:-5] for p in glob.glob(os.path.join(WORK, "migracoes", "*.json"))}
    assert ids <= {x["id"] for x in led.get("migracoes_aplicadas") or []}, ids
    vivo = {a["id"]: a.get("regra") for a in ledger().get("armadilhas", [])}
    for ident, mig in h.REGRAS_ATUALIZADAS.items():
        if ident in vivo:
            assert vivo[ident] in mig["antigas"] or vivo[ident] == mig["regra"], "%s: regra antiga mudou" % ident
    for p in glob.glob(os.path.join(WORK, "migracoes", "*.json")):
        with open(p, encoding="utf-8") as f:
            for ident, campos in ((json.load(f).get("ledger_updates") or {}).get("fontes") or {}).items():
                assert len(campos.get("nota") or "") <= h.LIMITE["nota"], ident
    codju = next(x for x in led["fontes"] if x["id"] == "gmail_stj_codju")["nota"]
    assert "Jurisprudência em Teses" in codju[:inicio.NOTA_CURTA] and "STJ Jurisprudência" in codju[:inicio.NOTA_CURTA]


@teste
def regra_de_armadilha_impressa_igual_a_gravada():
    """(rodada final) O LEDGER do passo 1 imprime a regra de armadilha pelo inicio.regra_impressa (sem a medicao fixa
    de rede) depois da migracao em memoria (REGRAS_ATUALIZADAS); o helper grava a regra de REGRAS_ATUALIZADAS. Os
    dois textos sao o mesmo: no dia antes da gravacao (texto antigo no ledger), depois dela (texto novo) e para toda
    armadilha do ledger vivo — senao o orquestrador le uma regra e o ledger guarda outra."""
    import copy
    import inicio
    h = helper()
    for ident, mig in h.REGRAS_ATUALIZADAS.items():
        assert inicio.regra_impressa(mig["regra"]) == mig["regra"], "%s: a regra gravada muda ao imprimir" % ident
        assert len(mig["regra"]) <= h.LIMITE["regra"], ident
    ce = h.REGRAS_ATUALIZADAS["cloud_egress_bloqueado"]
    for antiga in ce["antigas"]:
        assert " Medido em " in antiga and inicio.regra_impressa(antiga) == ce["regra"], \
            "cloud_egress_bloqueado: impressa %r x gravada %r" % (inicio.regra_impressa(antiga), ce["regra"])
    # ledger vivo: o passo 1 migra em memoria e imprime regra_impressa; o helper migra e grava — o mesmo texto
    migrado = copy.deepcopy(ledger())
    feitos = h.migrar_armadilhas(migrado)
    for x in migrado.get("armadilhas", []):
        assert inicio.regra_impressa(x.get("regra", "")) == x.get("regra", ""), \
            "%s: o passo 1 imprime %r e o helper grava %r" % (x["id"], inicio.regra_impressa(x.get("regra", "")),
                                                              x.get("regra"))
    vivo = {x["id"]: x.get("regra") for x in ledger().get("armadilhas", [])}
    assert "cloud_egress_bloqueado" not in vivo or "cloud_egress_bloqueado" in feitos or \
        vivo["cloud_egress_bloqueado"] == ce["regra"], "cloud_egress_bloqueado: o texto do ledger nao e o antigo"
    assert h.migrar_armadilhas(migrado) == [], "migracao nao idempotente"


@teste
def informativos_e_coleta_web_marcas_novas():
    import montar_email as m
    r = ler("ROTINA.md")
    for t in ("`[Afetação · Tema N]`", "`informativos_docs: falha`", "`[CONC]`", "`[STJ]`", "`vinculante`",
              "`[ASSESSORIA X]`", "`(mesma história: …)`", "`JA SAIU`", "`AVISO: cobertura parcial`",
              "`NENHUM ATO FORA…`", "`rotina — …`"):
        assert t in r, "ROTINA sem %r" % t
    inf, cw, rj = ler("work/informativos.py"), codigo_unido("work/coleta_web.py"), ler("work/resolver_jota.py")
    assert '"Afetação"' in inf and "sonda curta" in inf and "def status_informativos" in ler("work/montar_email.py")
    html = m.texto_destaque("stj", {"tipo": "Afetação", "precedente": "Tema 1484", "ramo": "Direito Civil",
                                    "destaque": "Definir se cabe X."})
    assert "Afetação · Tema 1484" in html, html
    for t in ('out.append("[CONC]")', '"[ASSESSORIA %s]"', '" (mesma história: %s)"', "== JA SAIU",
              "AVISO: cobertura parcial do %s", "NENHUM ATO FORA DO CONGRESSO E DO HISTORICO", "] rotina — %d %s"):
        assert t in cw, "coleta_web.py sem %r" % t
    assert "JA SAIU" in rj


@teste
def r1_exige_window_end():
    h = helper()
    trecho, bloco = secao("docs/referencia-operacional.md", "### R1.", "### R2."), None
    assert '"window_end": "<AAAA-MM-DDTHH:MM:SS-03:00>"' in trecho and "Janela de cobertura" in trecho
    erros = h.erros_window_end_r1({"delivery": "draft_ja_existente"}, ["campo obrigatorio ausente: window_end"],
                                  "2026-11-23T07:07:00-03:00")
    assert len(erros) == 1 and "§R1" in erros[0], erros
    ok = h.erros_window_end_r1({"delivery": "draft_ja_existente", "window_start": "2026-11-20T07:07:04-03:00",
                                "window_end": "2026-11-23T07:12:00-03:00"}, [], "2026-11-23T09:30:00-03:00")
    assert ok == [], ok


def inicio_preenche_os_prompts():
    """Opcional (rede: banca FGV e teste de alcance): copia o repositorio e roda o inicio.py."""
    d = tempfile.mkdtemp(prefix="test_doc_inicio_")
    try:
        copia = os.path.join(d, "repo")
        shutil.copytree(RAIZ, copia, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        t = os.path.join(d, "tmp")
        os.makedirs(t)
        env = dict(os.environ, ROBOZINHO_TMP=t, ROBOZINHO_DISPARO="0")
        r = subprocess.run([sys.executable, os.path.join(copia, "work", "inicio.py"), "--sem-disparo",
                            "--agora", "2026-11-17T07:05:00-03:00"], cwd=copia, env=env,
                           capture_output=True, text=True, timeout=300)
        assert r.returncode == 0, r.stderr[-400:]
        assert "PLACEHOLDER SOBRANDO" not in r.stdout
        for nome in ("gmail", "jota", "concursos"):
            txt = open(os.path.join(t, "coletor-%s.md" % nome), encoding="utf-8").read()
            assert "{{" not in txt, nome
        assert "Registro atual dos demais acompanhados" in open(os.path.join(t, "coletor-concursos.md"),
                                                                encoding="utf-8").read()
    finally:
        shutil.rmtree(d, ignore_errors=True)


if os.environ.get("DOC_TESTE_INICIO") == "1":
    teste(inicio_preenche_os_prompts)

print("%d falha(s)" % len(falhas) if falhas else "TODOS OK")
sys.exit(1 if falhas else 0)
