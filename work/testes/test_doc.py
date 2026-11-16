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
#     ROTINA mais curta que a de 13/11, munger-quotes sem caminhos locais.
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
    }
    achados = ["%s em %s" % (t, rel) for t, onde in proibidos.items() for rel in onde if t in ler(rel)]
    assert not achados, "; ".join(achados)


@teste
def linhas_procuradas_sao_impressas_pelos_scripts():
    esperado = {
        "aguardar_coleta.py": ["SOURCE_STATUS ", "AINDA RODANDO", "--teto"],
        "inicio.py": ["SELO POR DATA", "FERIADO HOJE", "FERIADOS NA JANELA", "dia útil sem execução registrada",
                      "candidato a remoção", "RE-EXECUÇÃO", "--extra", "--refazer", "aguardar_coleta.py"],
        "bancas.py": ["DIVERGE DO REGISTRO", "SEM REGISTRO"],
        "paginas_oficiais.py": ["PAGINA OFICIAL"],
        "informativos.py": ["EM ATRASO", "SEM EDICAO NOVA", "SEGUE SEM CONTEUDO", "ERRO PARSER", "TECNICO",
                            "(com resumo)", "não verificável"],
        "versiculo.py": ["VERSICULO ok |", "VERSICULO ok=false"],
        "coleta_web.py": ["[REPETIDA?~", "JA PUBLICADAS", "SEM_DATA_OFICIAL", "SEM NORMA NOVA NA JANELA",
                          "ERRO: congresso_mpv", "PLANALTO_ATO"],
        "montar_email.py": ["MONTAGEM: OK COM AVISOS", "AVISO ACIONÁVEL", "DESCARTADA", "BYTES: ", "SHA256: ",
                            "CAMINHO: ", "email-com-avisos.html", "execucao.resolvido.json",
                            '<span style="display:none">fim-%s</span>', "\\n</td></tr></table>"],
        "jota_extrair.py": ["JOTA_EXTRAIR", "[L%d]", "jota_urls.tsv"],
        "resolver_jota.py": ["JA_PUBLICADA", "RECUSADO", "SEM_MATCH", "SEM_LINK", "BLOQUEADO", "jota_links.tsv"],
        "finalizar.sh": ["PUSH: FALHOU", "ESTADO:", "STATUS: OK", "execucao.resolvido.json", "--draft-id",
                         "--message-id", "--trailer"],
        "Update-Historico.py": ["ALERTA_ECONOMIA", "modelo do orquestrador mudou", "sem --message-id",
                                "ausente_em_sent"],
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
              "ALERTA: modelo do orquestrador mudou", "allow_large", "larger:", "0,9 × `BYTES`"):
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
    dos_scripts = {"congresso_ultimas_leis", "congresso_mpvs", "conjur", "migalhas", "informativos_docs",
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
def rotina_seis_turnos_e_mais_curta():
    r = ler("ROTINA.md")
    assert "**6 turnos**" in r
    for cab in ("## 1. ", "## 2. ", "## 3. ", "## 4 e 5. ", "## 6. ", "## 7 e 8. "):
        assert cab in r, cab
    n = len(r.encode("utf-8"))
    assert n < ROTINA_ANTERIOR_BYTES, "ROTINA com %d bytes (antes %d)" % (n, ROTINA_ANTERIOR_BYTES)
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
    for t in ("**Ao entrar nela** (inclusive `NOVO`) o escrito prevalece sobre o cálculo",
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
    r = ler("ROTINA.md")
    passo6 = r[r.index("## 6. "):r.index("## 7 e 8. ")]
    erro = passo6[passo6.index("**Erro ou timeout**"):]
    antes = erro[:erro.index("1 nova tentativa")]
    assert '`list_drafts` com `subject:"<ASSUNTO>"`' in antes, "erro do create_draft sem list_drafts"
    assert '`search_threads` com `subject:"<ASSUNTO>" in:sent`' in antes, "erro do create_draft sem in:sent"
    assert "**não recrie**" in antes and "nada nas duas" in antes


@teste
def r4_espera_em_mensagem_propria_e_conta_do_disparo():
    trecho, bloco = bloco_de_codigo("docs/referencia-operacional.md", "### R4.", "### R5.")
    assert "--teto 480" not in trecho and "na mensagem do Write" not in trecho
    for t in ("numa mensagem própria, antes do Write", "timeout: 600000", "`email.limitacoes`", "informativos_docs"):
        assert t in trecho, "§R4 sem %r" % t
    assert "§R4, antes do Write" in ler("ROTINA.md")
    assert "(`timeout: 600000`): `python3 work/aguardar_coleta.py`" in ler("ROTINA.md")
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
