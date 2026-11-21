#!/usr/bin/env python3
# =====================================================================
# montar_email.py — passos 4/5 da ROTINA: do julgamento ao HTML pronto.
#
# O orquestrador escreve so o JULGAMENTO em $ROBOZINHO_TMP/execucao.json
# (itens, selos, resumo executivo, pendencias, ledger_updates). Este script:
#   1. resolve os {"ref": id} com a evidencia dos scripts do passo 2
#      (coleta_web, informativos): titulo, linha-fina, hora, URL e chave
#      sao COPIADOS, nunca redigitados; informativo sai com TODOS os
#      destaques (resumo oficial do STF, estagio da RG, tipo do STJ);
#   2. acrescenta o que e deterministico: versiculo, Munger, itens de
#      concurso que mudaram, pendencias do ledger, fontes consultadas, selo
#      por data e carimbo da banca (work/selos.py, work/bancas.py), grupo do
#      Planalto a partir da resenha, "impacto" pre-preenchido pela ementa,
#      linhas de apoio, rotulo "sem link";
#   3. descarta sozinho, nas secoes de apoio (Midia, Opiniao, Fofoquinha), o
#      repetido certo — REPUBLICADA (chave exata) e POSSIVEL_REPETIDA da mesma
#      fonte — e lista o descarte (linha DESCARTADA);
#   4. valida (Update-Historico.py --validar + checagens do e-mail);
#   5. monta o e-mail INTEIRO no layout do template v4 e GRAVA em arquivo.
#
# Por que: ate 11/11/2026 o orquestrador compunha o HTML a mao e colava no
# meio dele as secoes de Concursos impressas por outro script. Em 05/11 e
# 10/11 o rascunho saiu com o marcador __CONCURSOS__ no lugar das secoes;
# em 11/11 o selo do Munger saiu invisivel. Com o corpo inteiro vindo
# daqui, o create_draft e uma copia: nao ha o que "encaixar".
# 16/11/2026 (revisao): o corpo nao vai mais ao stdout (acima de ~30 KB a
# saida do Bash vira uma previa de 2 KB); o execucao.json do orquestrador
# nao e mais sobrescrito (a 2a rodada ignorava a correcao de "destaques");
# o tamanho nunca e ERRO (o corte do Gmail em ~102 KB e so visual).
#
# USO:   python3 work/montar_email.py [--execucao F] [--janela F] [--ledger F]
#            [--historico F] [--saida F] [--resolvido F] [--bancas F]
#            [--fontes-status F] [--com-html]
#        --com-html: imprime tambem o corpo entre "==== HTMLBODY ====" e
#        "==== FIM HTMLBODY ====" (so depuracao). --sem-html: aceito, e o padrao.
# SAIDA (stdout, < 3 KB), nesta ordem:
#        VALIDACAO: ... / MONTAGEM: OK|OK COM AVISOS ... / ASSUNTO: / PARA: /
#        DESCARTADA ... / AVISO ACIONÁVEL: ... / AVISO: ... / BYTES: / SHA256: / CAMINHO:
#        com ERRO: linhas "ERRO: ..." + "MONTAGEM: ERRO ...", exit 2, nenhum HTML.
# ARQUIVOS ($ROBOZINHO_TMP, padrao /tmp): le execucao.json, janela.json,
#        coleta_web.json, informativos.json, versiculo.json, bancas.json,
#        fontes_status.json, migracoes-hoje.json (work/migracoes.py: o que as
#        migracoes de dado aplicadas hoje mudaram — marcas do dia e itens do
#        historico, sem reaplicar); grava execucao.resolvido.json (o passo 7 usa) e
#        email.html — ou email-com-avisos.html quando houver AVISO ACIONÁVEL
#        (os dois sao apagados no inicio de cada rodada).
# =====================================================================

import argparse
import copy
import hashlib
import html
import json
import os
import re
import subprocess
import sys
import unicodedata
from datetime import date, datetime

AQUI = os.path.dirname(os.path.abspath(__file__))
if AQUI not in sys.path:
    sys.path.insert(0, AQUI)

import bancas  # noqa: E402
import feriados  # noqa: E402
import selos  # noqa: E402

DESTINATARIOS = ["pereirafranciscofilho@gmail.com", "luizaxbarreto@gmail.com"]


def tmp(nome):
    """$ROBOZINHO_TMP/<nome> (padrao /tmp), lido a cada chamada."""
    return os.path.join(os.environ.get("ROBOZINHO_TMP") or "/tmp", nome)


# ------------------------------------------------------------------ identidade visual (template v4)
FONTE = "font-family:Arial,Helvetica,sans-serif"
NAVY, OURO, TEXTO, APOIO_COR, LINK, LINHA = "#0b2545", "#c5a253", "#2f3a45", "#5a6773", "#0b4f92", "#e8edf2"
# 21/11/2026 (tamanho, sem mudar a renderizacao): dentro de style="..." o branco vai em 3 digitos (#fff = #ffffff, a
# mesma cor em qualquer cliente) e margem zero sem unidade (0 = 0px). O atributo bgcolor="#ffffff" fica como esta
# (o parser legado de cor do HTML tambem aceita 3 digitos, mas o atributo nao e CSS). Prova: work/testes/test_mon.py
# (t_mon_tamanho_equivalente) e as capturas de tela da edicao de 20/11 (Chromium, deviceScaleFactor 1, larguras 360,
# 700 e 1024, com e sem doctype), identicas pixel a pixel. Ganho pequeno (53.357 -> 53.305 B): o estilo inline ja nao
# tem declaracao redundante, fora o text-decoration:underline dos links, mantido de proposito (cliente que tira o
# sublinhado padrao). O tamanho cai de verdade pelo conteudo: compactacao pela regra do radar, rotina do orcamento,
# STJ sem nota por item e pendencias fora do quadro (20/11: 53.357 -> 51.335 B).
BRANCO = "#fff"
ESTILO = {
    "OFICIAL": "background:#e8eef7;color:#0b2545",
    "VERDE": "color:#1e6b3a;border:1px solid #bfe3cc",
    "URGENTE": "background:#fdf0f0;color:#a61b1b;border:1px solid #f0c2c2",
    "NEUTRO": "color:#5a6773;border:1px solid #c9ced6",
    "ALERTA": "color:#8a6d1d;border:1px solid #e6d3a3",
    "NAVY": "background:#0b2545;color:" + BRANCO,
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
BLOCOS = ["Magistratura Estadual", "Magistratura Federal", "Promotor de Justiça (Estadual)",
          "MPF/MPU — Procurador da República", "PFN", "AGU — Advogado da União",
          "Procurador do Estado (PGE)", "Procurador do Município (PGM)",
          "Defensor Público Estadual (DPE)", "Defensor Público Federal (DPU)"]
APOIO = "Quadro de apoio"
ORDEM_SELO = ["ENCERRA HOJE", "ENCERRA EM BREVE", "INSCRIÇÕES ABERTAS", "EDITAL PUBLICADO",
              "PROVA EM BREVE", "EM ANDAMENTO", "INSCRIÇÕES ENCERRADAS", "PROVA REALIZADA",
              "EM PLANEJAMENTO", "PENDÊNCIA DE VERIFICAÇÃO", "PENDÊNCIA"]
RADAR_DIAS = 30
RADAR_A_CONFIRMAR = True     # prazos so em fonte secundaria entram no quadro, em cinza e rotulados
A_CONFIRMAR_DIAS = 14        # ... so inscricao ou prova em ate 14 dias, sem divergencia pendente (decisao 16)
# Concursos compactos (decisao 4): de terca a sexta, registro sem mudanca desde antes da edicao
# anterior e sem prazo em destaque (prazo_em_destaque, a mesma regra do radar) sai numa linha por bloco;
# dormente sai compacto todo dia. A linha compacta mostra a inscricao/prova a confirmar de 15 a 30 dias.
DORMENCIA_DIAS_UTEIS = 15
SELOS_DORMENCIA = ("EM PLANEJAMENTO", "PENDÊNCIA DE VERIFICAÇÃO", "PENDÊNCIA")
NUNCA_COMPACTAR = ("ENCERRA HOJE", "ENCERRA EM BREVE", "INSCRIÇÕES ABERTAS", "PROVA EM BREVE", "EDITAL PUBLICADO")
TAMANHO_AVISO = 80_000       # bytes: AVISO com o tamanho por secao (nunca ERRO; o Gmail corta a exibicao ~102 KB)
IMPACTO_MAX = 160

# secoes de noticia, na ordem do e-mail: (categoria, titulo, linha de apoio quando vazia)
SECOES = [
    ("Planalto/Legislação", "🏛️ Planalto — Resenha Diária e legislação federal", None),
    ("STF Notícias", "⚖️ STF — Notícias", "Nenhuma notícia do STF chegou pelo Push STF nesta janela."),
    ("STF Jurisprudência", "⚖️ STF — Jurisprudência",
     "Nenhum boletim de Repercussão Geral em Pauta na janela; decisões do STF noticiadas só pela mídia "
     "estão em Se saiu na mídia não é fofoca!"),
    ("STJ Notícias", "⚖️ STJ — Notícias",
     "O STJ da janela chegou só pela mídia — ver Se saiu na mídia não é fofoca!"),
    ("STJ Jurisprudência", "⚖️ STJ — Jurisprudência", "Sem teses do CodJu na janela; ver Informativos."),
    ("Informativos", "📚 Informativos",
     "Nenhuma edição nova de informativo (STF, Repercussão Geral em Pauta ou STJ) nesta janela — "
     "a cadência é semanal."),
]
CATEGORIAS_NOTICIA = [c for c, _, _ in SECOES] + ["Mídia", "Opinião/Análise", "Fofoquinha"]
SECOES_APOIO = ("Mídia", "Opinião/Análise", "Fofoquinha")     # descarte automatico de repetido (decisao 8)
INDICE = ("Planalto/Legislação · STF Notícias · STF Jurisprudência · STJ Notícias · STJ Jurisprudência · "
          "Informativos · Concursos – Carreira · Concursos – Apoio · Se saiu na mídia não é fofoca! · "
          "FOFOQUINHA JURÍDICA · Porque sem Deus, nada é possível · Conhecimento nunca é demais · Pendências.")
FRASE_PLANALTO = "isso aqui só existe porque eles não param de inventar moda..."
ROTULO_FONTE = {  # id do source_status -> como aparece em "Fontes consultadas" e no rodape
    "gmail_push_stf": "Push STF (notícias)", "gmail_push_stf_informativos": "Push STF (informativos)",
    "gmail_stj_codju": "STJ CodJu", "gmail_push_planalto": "PUSH Planalto (Resenha Diária)",
    "gmail_camara": "boletim da Agência Câmara", "camara_noticias": "Agência Câmara (site)",
    "congresso_ultimas_leis": "Congresso Nacional (últimas leis)",
    "congresso_mpvs": "Congresso Nacional (medidas provisórias)",
    "camara_legin": "Câmara (Legislação Informatizada)",
    "informativos_docs": "documentos oficiais dos informativos (STF/STJ)",
    "gmail_jota": "JOTA (clipping, opinião e bastidores)", "conjur": "ConJur (mídia especializada)",
    "migalhas": "Migalhas (mídia especializada)", "youversion": "YouVersion (versículo)",
    "dailyverses": "DailyVerses.net (versículo)",
}
OFICIAIS = ["gmail_push_planalto", "congresso_ultimas_leis", "congresso_mpvs", "camara_legin", "camara_noticias",
            "gmail_camara", "gmail_push_stf", "gmail_push_stf_informativos", "gmail_stj_codju", "informativos_docs"]
SECUNDARIAS = ["gmail_jota", "conjur", "migalhas", "youversion", "dailyverses"]
STATUS_FONTE = ("ok", "vazio", "falha", "nao_tentada")
WRAPPER = re.compile(r"t\.rdsv2\.net|google\.com/url|[?&]utm_")
MESES = {m: i + 1 for i, m in enumerate("janeiro fevereiro março abril maio junho julho agosto setembro "
                                        "outubro novembro dezembro".split())}
DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
HOST_OFICIAL = re.compile(r"(?:^|\.)(?:jus|gov|leg|mp|def)\.br$", re.I)
# rotulo de fonte oficial sem URL (item_oficial): ao menos uma palavra de ROTULO_OFICIAL e nenhuma fora do
# vocabulario (sem acento, minusculas; numeros e datas nao contam). "via", "jota", "decisao"... derrubam.
ROTULO_OFICIAL = set("stf stj codju planalto push congresso camara senado presidencia dou".split())
VOCAB_ROTULO_OFICIAL = ROTULO_OFICIAL | set("""
noticias noticia informativo informativos jurisprudencia tese teses boletim agencia portal resenha diaria
legislacao oficial documento pagina edicao extra rota ultimas leis publicadas rg repercussao geral pauta
andamento processual superior tribunal supremo federal justica nacional diario uniao imprensa gmail
de da do das dos e o a em no na
""".split())

# AVISO que pede decisao do orquestrador antes do rascunho: com algum deles o corpo vai para
# email-com-avisos.html (o Read de email.html na mesma mensagem falha barato; quem aceita o aviso
# le o outro arquivo, sem rodar de novo). Os demais AVISOs sao informativos.
# "contradiz o selo por data" (helper: selo escrito hoje diferente do que a data da) e "prorrogação não
# confirmada" (selos.py: prazo vencido sem a banca confirmar; o selo caiu para PENDÊNCIA DE VERIFICAÇÃO) pedem
# o selo ou os prazos certos: sem isso o e-mail saia "INSCRIÇÕES ABERTAS" para inscricao que acaba em 2 dias.
# "prazos[n].tipo" (montador, tipo_contra_evento; e o do helper com o mesmo prefixo): `tipo` 'outro'/'prova' num
# prazo que o evento diz ser de inscricao desligava o selo por data sem alerta (INSCRIÇÕES ABERTAS a 2 dias do fim).
# "selo por data suspenso" (bancas.selo_do_dia: o edital lido hoje contesta a data do registro; o selo nao foi
# recalculado) e "prazo escrito hoje difere do edital" (helper: o update de hoje contradiz o edital lido hoje)
# pedem prazos/linha certos ou a decisao do selo.
ACIONAVEL = re.compile(r"REPUBLICADA|POSSIVEL_REPETIDA|POSSIVEL_DUPLICATA|movimento oficial não refletido|"
                       r"relacionado a |nenhum card do resumo|citam? item descartado|contradiz o selo por data|"
                       r"prorrogação não confirmada|\.prazos\[\d+\]\.tipo\b|selo por data suspenso|"
                       r"prazo escrito hoje difere do edital")

# G7: atos de rotina do Planalto (agrupados no fim da secao; nada e omitido, a ementa sai inteira)
# 21/11/2026: tambem LOA, LDO e PPA e as leis que os alteram ("estima a receita e fixa a despesa", "diretrizes para a
# elaboracao e a execucao da Lei Orcamentaria", 20/11) e o credito em valor das noticias da Agencia Camara ("credito
# de R$ 6,6 bi", "credito extra de R$ 360 milhoes", 18/11). "Linha de credito de R$" (politica de merito, criada por
# MP) e "credito consignado" nao sao rotina. Lei de materia PLN (congresso_leis) e rotina pelo campo, ver _pln.
ROTINA_ATO = re.compile(
    r"abre\s+aos?\s+or[çc]amentos?|cr[ée]dito\s+(?:suplementar|especial|extraordin[áa]rio)|"
    r"aumento\s+(?:do|de)\s+capital|\bacordo\b.{0,160}?\b(?:turismo|servi[çc]os\s+a[ée]reos|transporte\s+a[ée]reo)|"
    r"estima\s+a\s+receita\s+e\s+fixa\s+a\s+despesa|"
    r"diretrizes\s+para\s+a\s+elabora[çc][ãa]o\s+e\s+(?:a\s+)?execu[çc][ãa]o\s+da\s+Lei\s+Or[çc]ament|"
    r"\bplano\s+plurianual\b|(?<!linha de )(?<!linhas de )cr[ée]dito\s+(?:extra\s+)?de\s+R\$",
    re.I)
SUBTITULO_ROTINA = ("Atos de rotina — orçamento (créditos, LOA, LDO e PPA), cargos, capital de estatais e acordos de "
                    "turismo ou serviços aéreos")
ROTINA_EXCETO = re.compile(r"coopera[çc][ãa]o\s+jur[íi]dica|mat[ée]ria\s+penal|extradi[çc]|transfer[êe]ncia\s+de\s+"
                           r"(?:pessoas\s+)?(?:presos|condenad|apenad)|assist[êe]ncia\s+jur[íi]dica|crime|penal",
                           re.I)
# cargos: so cargo em comissao/funcao de confianca (e "remaneja"). Cargo de carreira juridica ("transforma
# cargos vagos em cargos de Juiz Federal Substituto") e criacao de cargo efetivo nunca sao rotina.
ROTINA_CARGOS = re.compile(r"\bremaneja|cargos?\s+em\s+comiss[ãa]o|fun[çc][õo]es\s+(?:de\s+confian[çc]a|comissionadas|"
                           r"gratificadas)", re.I)
CARGOS_EXCETO = re.compile(r"\bju[íi]z(?:es|a|as)?\b|magistrad|desembargador|\bprocurador(?!ia)|\bpromotor(?!ia)|"
                           r"\bdefensor(?!ia)|\bmembros?\s+d[oa]s?\b|\bcri(?:a|am|a[çc][ãa]o)\b.{0,40}?cargos\s+efetivos|"
                           r"\bvagas\b", re.I)

# K6: "impacto" pre-preenchido pela ementa ("Altera ... Codigo Penal" -> "Altera: Código Penal")
_N = r"\s+n[ºo°.]*\s*"
CODIGOS = [(re.compile(p, re.I), rot) for p, rot in (
    (r"C[óo]digo\s+Penal(?!\s+Militar)|Decreto-Lei" + _N + r"2\.848\b", "Código Penal"),
    (r"C[óo]digo\s+de\s+Processo\s+Penal|Decreto-Lei" + _N + r"3\.689\b", "Código de Processo Penal"),
    (r"C[óo]digo\s+Penal\s+Militar|Decreto-Lei" + _N + r"1\.001\b", "Código Penal Militar"),
    (r"C[óo]digo\s+Civil|\bLei" + _N + r"10\.406\b", "Código Civil"),
    (r"C[óo]digo\s+de\s+Processo\s+Civil|\bLei" + _N + r"13\.105\b", "Código de Processo Civil"),
    (r"Consolida[çc][ãa]o\s+das\s+Leis\s+do\s+Trabalho|\bCLT\b|Decreto-Lei" + _N + r"5\.452\b", "CLT"),
    (r"C[óo]digo\s+Tribut[áa]rio\s+Nacional|\bLei" + _N + r"5\.172\b", "Código Tributário Nacional"),
    (r"C[óo]digo\s+de\s+Defesa\s+do\s+Consumidor|\bLei" + _N + r"8\.078\b", "Código de Defesa do Consumidor"),
    (r"Estatuto\s+da\s+Crian[çc]a|\bLei" + _N + r"8\.069\b", "Estatuto da Criança e do Adolescente"),
    (r"Lei\s+de\s+Execu[çc][ãa]o\s+Penal|\bLei" + _N + r"7\.210\b", "Lei de Execução Penal"),
    (r"\bLei" + _N + r"8\.429\b|Lei\s+de\s+Improbidade\s+Administrativa", "Lei de Improbidade Administrativa"),
    (r"\bLei" + _N + r"14\.133\b", "Lei de Licitações e Contratos (14.133/2021)"),
    (r"\bLei" + _N + r"11\.340\b|Lei\s+Maria\s+da\s+Penha", "Lei Maria da Penha"),
    (r"C[óo]digo\s+de\s+Tr[âa]nsito|\bLei" + _N + r"9\.503\b", "Código de Trânsito Brasileiro"),
    (r"C[óo]digo\s+Eleitoral|\bLei" + _N + r"4\.737\b", "Código Eleitoral"),
    (r"\bLei" + _N + r"9\.504\b", "Lei das Eleições"),
    (r"\bLei" + _N + r"11\.343\b", "Lei de Drogas"),
    (r"\bLei" + _N + r"8\.072\b|Lei\s+dos\s+Crimes\s+Hediondos", "Lei dos Crimes Hediondos"),
    (r"\bLei" + _N + r"8\.112\b", "Estatuto dos Servidores Federais (Lei 8.112/1990)"),
    (r"\bLei" + _N + r"7\.347\b", "Lei da Ação Civil Pública"),
    (r"\bLei" + _N + r"12\.016\b", "Lei do Mandado de Segurança"),
    (r"\bLei" + _N + r"13\.709\b|Lei\s+Geral\s+de\s+Prote[çc][ãa]o\s+de\s+Dados|\bLGPD\b", "LGPD"),
    (r"Lei\s+Complementar" + _N + r"101\b|Lei\s+de\s+Responsabilidade\s+Fiscal", "Lei de Responsabilidade Fiscal"),
    (r"\bLei" + _N + r"9\.099\b", "Lei dos Juizados Especiais"),
    (r"\bLei" + _N + r"8\.906\b|Estatuto\s+da\s+Advocacia", "Estatuto da Advocacia e da OAB"),
    (r"\bLei" + _N + r"9\.784\b", "Lei do Processo Administrativo Federal"),
    (r"\bLei" + _N + r"12\.850\b|Lei\s+d[ae]s?\s+Organiza[çc](?:[ãa]o|[õo]es)\s+Criminosas?", "Lei das Organizações Criminosas"),
    (r"\bLei" + _N + r"9\.613\b|Lei\s+de\s+Lavagem", "Lei de Lavagem de Dinheiro"),
    (r"\bLei" + _N + r"10\.826\b|Estatuto\s+do\s+Desarmamento", "Estatuto do Desarmamento"),
    (r"\bLei" + _N + r"10\.741\b|Estatuto\s+d[ao]\s+(?:Pessoa\s+)?Idos", "Estatuto da Pessoa Idosa"),
    (r"\bLei" + _N + r"13\.146\b|Estatuto\s+da\s+Pessoa\s+com\s+Defici[êe]ncia", "Estatuto da Pessoa com Deficiência"),
    (r"\bLei" + _N + r"11\.101\b", "Lei de Recuperação Judicial e Falência"),
    (r"Decreto-Lei" + _N + r"4\.657\b|Lei\s+de\s+Introdu[çc][ãa]o", "LINDB"),
    (r"\bLei" + _N + r"9\.605\b", "Lei de Crimes Ambientais"),
    (r"\bLei" + _N + r"6\.015\b|Lei\s+de\s+Registros\s+P[úu]blicos", "Lei de Registros Públicos"),
    (r"\bLei" + _N + r"12\.527\b", "Lei de Acesso à Informação"),
    (r"\bLei" + _N + r"12\.846\b", "Lei Anticorrupção"),
    (r"\bLei" + _N + r"8\.625\b", "Lei Orgânica Nacional do Ministério Público"),
    (r"Lei\s+Complementar" + _N + r"80\b", "Lei Orgânica da Defensoria Pública (LC 80/1994)"),
    (r"Lei\s+Complementar" + _N + r"75\b", "Lei Orgânica do MPU (LC 75/1993)"),
    (r"Lei\s+Complementar" + _N + r"35\b", "LOMAN (LC 35/1979)"),
    (r"Lei\s+Complementar" + _N + r"73\b", "Lei Orgânica da AGU (LC 73/1993)"),
    (r"Constitui[çc][ãa]o\s+Federal|Ato\s+das\s+Disposi[çc][õo]es\s+Constitucionais", "Constituição Federal"),
)]
VERBO_ALTERA = re.compile(r"^\s*(Altera|Acrescenta|Inclui|Modifica|Revoga|D[áa]\s+nova\s+reda[çc][ãa]o)", re.I)
# So o objeto do verbo conta: o trecho acaba na finalidade ("para", "a fim de", "nos termos") ou na oracao
# que descreve o diploma alterado ("o Decreto nº 11.615, que regulamenta a Lei nº 10.826" nao altera a Lei).
FIM_OBJETO = re.compile(
    r"[;:]|,?\s+(?:que|para|nos\s+termos|a\s+fim\s+de|com\s+(?:o\s+|a\s+)?(?:objetivo|fim|finalidade|vistas)|"
    r"conforme|(?:institu[íi]d|criad|regulamentad|aprovad|previst|referid|mencionad|disciplinad|estabelecid|"
    r"editad)[oa]s?)\b", re.I)
# especie que nao altera lei nem codigo: decreto regulamentar, decreto legislativo, resolucao, portaria
ATO_INFRALEGAL = re.compile(r"^\s*(?:Decreto(?![\s-]+Lei\b)|Resolu[çc][ãa]o|Portaria|Instru[çc][ãa]o)", re.I)
ATO_EC = re.compile(r"^\s*(?:Emenda\s+Constitucional|EC)\b", re.I)

# G3b: palavras que nao distinguem materia (mais as PARADAS do repeticao.py)
GENERICOS = set("""
stf stj supremo tribunal tribunai federal justica lei leis tema julgamento julga julgar julgou decisao decide
decidiu recurso geral repercussao ministro ministra plenario corte direito publico publica prazo quando ainda
segundo base acao caso valor valore processo norma regra constitucional inconstitucional constituicao estado
estadual municipal uniao nacional demai artigo art inciso texto dia dias ano anos sobre maioria voto voto
relator relatora reconhece confirma nega mantem pode deve
""".split())


# ------------------------------------------------------------------ utilitarios
def ler(caminho, padrao=None):
    try:
        with open(caminho, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError, TypeError):
        return padrao


def esc(s):
    """Texto -> HTML. So <b>, <i> e <br> escritos pelo orquestrador sobrevivem."""
    t = html.escape(str(s or ""), quote=False)
    return re.sub(r"&lt;(/?(?:b|i)|br ?/?)&gt;", r"<\1>", t)


def attr(u):
    return html.escape(str(u or ""), quote=True)


def slug(s, n=60):
    t = unicodedata.normalize("NFKD", str(s or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:n].strip("-")


FECHA_ASPAS = "”\"'’»"


def ponto(s):
    """'texto' -> 'texto.' sem duplicar a pontuacao final. Aspa de fechamento nao e pontuacao:
    '... do "milagre"' -> '... do "milagre".'; '... previstas.”' fica como esta."""
    s = (s or "").strip()
    if not s or s.endswith(("</b>", "</i>")) or s[-1] in ".!?…":
        return s
    if s[-1] in FECHA_ASPAS:
        antes = s[:-1].rstrip()
        return s if antes and antes[-1] in ".!?…" else s + "."
    return s + "."


def br_data(iso, ano=False):
    try:
        d = date.fromisoformat((iso or "")[:10])
    except (ValueError, TypeError):
        return ""
    return d.strftime("%d/%m/%Y" if ano else "%d/%m")


def _data(v):
    try:
        return date.fromisoformat(str(v or "")[:10])
    except ValueError:
        return None


def selo(texto, pequeno=False):
    if texto not in SELO_ESTILO:
        raise SystemExit("ERRO: selo fora da lista fechada: %r" % texto)
    return ('<b style="%s;font-size:%dpx;padding:2px %dpx;border-radius:3px;white-space:nowrap">%s</b>'
            % (ESTILO[SELO_ESTILO[texto]], 9 if pequeno else 10, 6 if pequeno else 7, esc(texto)))


def link(url, texto, extra=""):
    if not url:
        return texto
    return '<a href="%s" style="color:%s%s">%s</a>' % (attr(url), LINK, extra, texto)


def px(n):
    """Medida CSS: 0 sem unidade ("0"), o resto em px."""
    return "%dpx" % n if n else "0"


def h2(titulo, margem=10):
    return ('<div style="border-left:4px solid %s;padding-left:10px;font-size:16px;line-height:22px;'
            'font-weight:bold;color:%s;margin-bottom:%dpx">%s</div>' % (OURO, NAVY, margem, titulo))


def secao(titulo, corpo, topo=22, margem_titulo=10):
    return ('<tr><td style="padding:%dpx 20px 0;%s;font-size:13px;line-height:19px;color:%s">%s\n%s</td></tr>'
            % (topo, FONTE, TEXTO, h2(titulo, margem_titulo), corpo))


def apoio(texto):
    return '<div style="font-size:12px;line-height:18px;color:%s">%s</div>' % (APOIO_COR, esc(texto))


def subtitulo(texto, topo=14):
    """Subtitulo dentro de uma secao (o mesmo da Opiniao/Analise)."""
    return ('<p style="margin:%s 0 6px;font-size:12px;font-weight:bold;color:%s">%s</p>'
            % ("%dpx" % topo if topo else "0", NAVY, esc(texto)))


def host(url):
    return selos.host(url)


# ------------------------------------------------------------------ 1. evidencia e refs
def evidencias(coleta=None, informativos=None):
    """{id: registro} do que os scripts do passo 2 coletaram."""
    ev = {}
    for bloco in ler(coleta or tmp("coleta_web.json"), []) or []:
        for it in bloco.get("itens") or []:
            if it.get("id"):
                ev[it["id"]] = dict(it, _fonte=bloco.get("fonte"))
    for r in ler(informativos or tmp("informativos.json"), []) or []:
        if r.get("id"):
            ev[r["id"]] = dict(r, _fonte="informativo")
    return ev


def data_extenso(s):
    """'4 a 9 de novembro de 2026' -> '2026-11-09' (ultima data do texto)."""
    datas = re.findall(r"(\d{1,2}) de (%s) de (\d{4})" % "|".join(MESES), s or "")
    if not datas:
        return ""
    d, m, a = datas[-1]
    return "%s-%02d-%02d" % (a, MESES[m], int(d))


NOME_INF = {"stf": "Informativo STF nº %d", "rg": "Repercussão Geral em Pauta nº %d",
            "stj": "Informativo STJ nº %d"}


MINUSCULAS = {"de", "da", "do", "das", "dos", "e", "em", "a", "o", "à", "ao"}


def caixa_titulo(s):
    """'DIREITO DO CONSUMIDOR' -> 'Direito do Consumidor'."""
    p = (s or "").lower().split()
    return " ".join(w if (n and w in MINUSCULAS) else w[:1].upper() + w[1:] for n, w in enumerate(p))


def curto(s, n=60):
    """Texto (titulo, evento, resenha) numa mensagem de ERRO/AVISO: ate n caracteres, cortado em fronteira de
    palavra e com "…" (23/11, ensaio: "STJ vai julgar se ANPP deve ser rescindido por juiz que homo" — o corte no
    meio da palavra parecia o titulo). Palavra unica maior que n: corte seco com "…"."""
    t = re.sub(r"\s+", " ", str(s or "")).strip()
    if len(t) <= n:
        return t
    corte = t[:n] if t[n] == " " else t[:n].rsplit(" ", 1)[0] if " " in t[:n] else t[:n - 1]
    return corte.rstrip(" ,;:.—–-") + "…"


def limpo(s):
    """Espacos que a extracao do documento deixa antes de pontuacao e dentro de parenteses."""
    s = re.sub(r"\s+([,.;:)])", r"\1", s or "")
    return re.sub(r"\(\s+", "(", s).strip()


def _verdade(v):
    return v is True or str(v).strip().lower() in ("true", "1", "sim")


def rotulo_rg(d, hoje=None):
    """Estagio do tema para o leitor (informativos.py grava `estagio`): 'Tese publicada',
    'Repercussão geral em votação (PV, até 13/11)', 'Pauta do Plenário 11/11' etc. Vazio = sem rotulo."""
    est = re.sub(r"\s+", " ", str(d.get("estagio") or "")).strip()
    if not est:
        return ""
    passou = False
    prev = _data(d.get("previsao"))
    if hoje and prev:
        passou = prev < (hoje if isinstance(hoje, date) else _data(hoje) or prev)
    nota = "resultado no próximo boletim" if passou else ""
    m = re.fullmatch(r"em votação no PV(?: até (\d{2}/\d{2}))?", est, re.I)
    if m:
        dentro = ", ".join(x for x in ("PV", ("até " + m.group(1)) if m.group(1) else "") if x)
        return "Repercussão geral em votação (%s%s)" % (dentro, "; " + nota if nota else "")
    m = re.fullmatch(r"pauta do plen[áa]rio(?: (\d{2}/\d{2}))?", est, re.I)
    if m:
        return "Pauta do Plenário%s%s" % ((" " + m.group(1)) if m.group(1) else "", " (%s)" % nota if nota else "")
    m = re.fullmatch(r"pauta da sess[ãa]o virtual(?: de (\d{2}/\d{2}) a (\d{2}/\d{2}))?", est, re.I)
    if m:
        base = ("Sessão virtual de %s a %s" % (m.group(1), m.group(2))) if m.group(1) else "Pauta da sessão virtual"
        return base + (" (%s)" % nota if nota else "")
    if est.lower() == "finalizado":
        return "Votação finalizada"
    return est[:1].upper() + est[1:]


def _pendente_rg(d):
    return re.match(r"(?i)em votação|pauta", str(d.get("estagio") or "")) is not None


def _tema_rg(d):
    return "<b>Tema %s</b> (%s)" % (esc(d.get("tema")), esc(limpo(d.get("processo"))))


def texto_destaque(tipo, d, hoje=None):
    """Um destaque do informativo em HTML (texto copiado do documento oficial, sem corte)."""
    if tipo == "stf":
        resumo = (" <i>Resumo:</i> " + esc(limpo(d["resumo"]))) if d.get("resumo") else ""
        return "<b>%s</b> — %s%s" % (esc(caixa_titulo(d["ramo"])), esc(ponto(limpo(d["titulo"]))), resumo)
    if tipo == "rg":
        rot = rotulo_rg(d, hoje)
        rot = (" · <i>%s</i>" % esc(rot)) if rot else ""
        if d.get("tese"):
            cauda = " <i>Tese:</i> " + esc(limpo(d["tese"]))
        elif d.get("decisao") and not _pendente_rg(d):
            cauda = " <i>Decisão:</i> " + esc(ponto(limpo(d["decisao"])))
        else:
            cauda = ""
        return "%s%s — %s%s" % (_tema_rg(d), rot, esc(ponto(limpo(d["titulo"]))), cauda)
    # stj: o tipo do precedente vem antes (Afetação/Repetitivo/RQF com o tema; Corte Especial). Afetação (nota da
    # secao PROPOSTA DE ..., desde o 910): "Afetação · Tema 1484" e a controversia afetada. Sem o ramo (o 910 nao
    # trouxe o do Tema 1469), sem o separador solto ("Repetitivo · — i) Nos termos...")
    ramo = esc(caixa_titulo(d.get("ramo")))
    t = d.get("tipo") or ""
    if t in ("Repetitivo", "RQF", "Afetação"):
        rot = " · ".join(x for x in (t, d.get("precedente") or "") if x)
    elif t == "Corte Especial":
        rot = "Corte Especial"
    else:
        rot = ""
    if rot:
        cab = "<b>%s</b>%s" % (esc(rot), (" · " + ramo) if ramo else "")
    else:
        cab = "<b>%s</b>" % (ramo or esc(d.get("orgao") or "")) if (ramo or d.get("orgao")) else ""
    proc = esc(ponto(limpo(d.get("processo"))))
    corpo = esc(ponto(limpo(d["destaque"]))) + ((" <i>%s</i>" % proc) if proc else "")
    return ("%s — %s" % (cab, corpo)) if cab else corpo


def grupo_rg(d):
    """Estagio do tema da RG para a ordem do bloco: 0 = com tese ou desfecho, 1 = em votacao ou em pauta
    (sem tese ainda), 2 = sem repercussao geral (numa linha so, no fim)."""
    if _verdade(d.get("sem_repercussao_geral")):
        return 2
    return 1 if _pendente_rg(d) and not d.get("tese") else 0


def aviso_ordem_rg(spec, itens, idx, ref, avisos):
    """Na RG a "ordem" do orquestrador vale DENTRO de cada estagio (grupo_rg): o bloco sempre traz primeiro
    os temas com tese ou desfecho. Quando a ordem pedida poe um tema de estagio posterior antes, AVISO
    informativo (antes a ordem era ignorada em silencio)."""
    if not isinstance(spec, dict):        # a lista antiga ja tem o seu AVISO (selecionar)
        return
    pedidos = [i for i in spec.get("ordem") or [] if isinstance(i, int) and not isinstance(i, bool) and i in idx]
    sai = sorted(pedidos, key=lambda i: (grupo_rg(itens[i]), pedidos.index(i)))
    if sai != pedidos:
        k = next(n for n, (a, b) in enumerate(zip(sai, pedidos)) if a != b)
        avisos.append("%s: na Repercussão Geral a \"ordem\" vale dentro de cada estágio (com tese ou desfecho → em "
                      "votação ou pauta → sem repercussão geral): Tema %s sai depois do Tema %s" % (
                          ref, itens[pedidos[k]].get("tema"), itens[sai[k]].get("tema")))


def destaques_html(tipo, itens, hoje=None):
    """Lista de <p> do bloco de destaques. RG (G5): primeiro os temas com tese ou desfecho, depois os em
    votacao ou em pauta (sem tese ainda), e os sem repercussao geral numa linha so; dentro de cada estagio,
    a ordem recebida (a do orquestrador, ver aviso_ordem_rg)."""
    if tipo != "rg":
        return [texto_destaque(tipo, d, hoje) for d in itens]
    cheios = [d for d in itens if grupo_rg(d) == 0]
    pendentes = [d for d in itens if grupo_rg(d) == 1]
    sem_rg = [d for d in itens if grupo_rg(d) == 2]
    out = [texto_destaque("rg", d, hoje) for d in cheios + pendentes]
    if sem_rg:
        out.append("<i>Sem repercussão geral:</i> " + "; ".join(
            "%s — %s" % (_tema_rg(d), esc(limpo(d["titulo"]).rstrip("."))) for d in sem_rg) + ".")
    return out


def selecionar(spec, n, ref, erros, avisos):
    """'destaques' do orquestrador -> indices. Ausente ou "todos": todos, na ordem do documento (G5).
    Lista (formato antigo): esses primeiro, na ordem dada, e depois o resto — nada sai.
    {"ordem": [...], "excluir": [...]}: ordem e exclusao explicitas."""
    todos = list(range(n))
    if spec in (None, "", "todos", []):
        return todos
    if isinstance(spec, dict):
        ordem, excluir = list(spec.get("ordem") or []), list(spec.get("excluir") or [])
    elif isinstance(spec, list):
        ordem, excluir = list(spec), []
        if len(set(spec)) < n:
            avisos.append("%s: \"destaques\" em lista agora só ordena (saem os %d); para tirar um, "
                          "{\"excluir\": [i]}" % (ref, n))
    else:
        erros.append("ref %s: \"destaques\" deve ser lista de índices ou {\"ordem\": [...], \"excluir\": [...]}" % ref)
        return todos
    ruins = [i for i in ordem + excluir if isinstance(i, bool) or not isinstance(i, int) or not 0 <= i < n]
    if ruins:
        erros.append("ref %s: destaques %s fora de 0..%d" % (ref, ruins, n - 1))
    fora = {i for i in excluir if i not in ruins}
    vistos, sel = set(), []
    for i in ordem + todos:
        if i in ruins or i in fora or i in vistos:
            continue
        vistos.add(i)
        sel.append(i)
    return sel


# temas (so RG): os temas que sairam no e-mail, gravados no historico; o informativos.py tira da revisita de
# uma RG anterior o tema ja publicado com uma RG posterior (INF-rev-1c: o Tema 1.483 da RG 397 voltava na 394)
# resumo_truncado (coleta_web.json, P5): a coleta marca o resumo que veio cortado; so o script decide (o escrito
# pelo orquestrador e ignorado) e nao vai ao resolvido nem ao historico
DERIVADOS = {"destaques_texto", "observacao", "herdada", "chave", "sem_conteudo", "temas", "resumo_truncado"}
RESUMO_TRUNCADO_MIN = 40     # resumo cortado mais curto que isto (sem as reticencias) e omitido
FIM_CORTADO = re.compile(r"(?:\[\s*(?:…|\.\.\.)\s*\]|…|[\s,;:.\-–—(])+$")


def resumo_cortado(s):
    """Resumo que a coleta marcou como cortado: sem a pontuacao/reticencias soltas do fim e terminado em "…" (o
    ponto() nao acrescenta ponto depois dele); com menos de RESUMO_TRUNCADO_MIN caracteres, "" (omitido)."""
    t = FIM_CORTADO.sub("", str(s or "").strip())
    return t + "…" if len(t) >= RESUMO_TRUNCADO_MIN else ""


def resolver(it, ev, erros, avisos=None, hoje=None):
    """Completa o item com a evidencia do ref. Campo escrito pelo orquestrador vence; campo DERIVADO
    (destaques_texto, observacao, herdada, chave...) que venha no arquivo e ignorado e recalculado —
    o execucao.json de uma rodada anterior nunca congela a montagem seguinte (K2)."""
    avisos = [] if avisos is None else avisos
    ref = it.get("ref")
    if not ref:
        return it
    e = ev.get(ref)
    base = {}
    m = re.fullmatch(r"(stf|rg|stj)(\d+)", ref)
    if e and e["_fonte"] == "congresso_leis":
        n = int(e["numero"])
        veto = "; com veto — %s" % e["veto"] if e.get("veto") else ""
        base = {"categoria": "Planalto/Legislação", "status": "CONFIRMADO POR FONTE OFICIAL ALTERNATIVA",
                "titulo": "%s nº %s, de %s" % (e["tipo"], "{:,}".format(n).replace(",", "."), e["data_ato"]),
                "meta": "DOU %s%s" % (e["dou"][:5], veto), "resumo": e["ementa"], "url": e["url"],
                "data": datetime.strptime(e["data_ato"], "%d/%m/%Y").date().isoformat(),
                "fonte": "Congresso Nacional", "grupo": "Congresso Nacional — últimas leis publicadas",
                "chave": e["chave"],
                # PLN = materia orcamentaria do Congresso (PPA, LDO, LOA, creditos): ato de rotina pela materia
                "_pln": str(e.get("materia") or "").strip().upper().startswith("PLN")}
    elif e and e["_fonte"] == "congresso_mpv":
        n = int(e["numero"])
        dou = e.get("dou") or ""
        base = {"categoria": "Planalto/Legislação",
                "status": "CONFIRMADO POR FONTE OFICIAL ALTERNATIVA" if dou else "PENDÊNCIA DE VERIFICAÇÃO",
                "titulo": "Medida Provisória nº %s/%s" % ("{:,}".format(n).replace(",", "."), e["ano"]),
                "meta": ("DOU %s" % dou[:5]) if dou else "data do DOU não confirmada na página oficial",
                "resumo": e["ementa"], "url": e["url"], "fonte": "Congresso Nacional",
                "data": datetime.strptime(dou, "%d/%m/%Y").date().isoformat() if dou else "",
                "grupo": "Congresso Nacional — medidas provisórias", "chave": e["chave"] if dou else ""}
    elif e and e["_fonte"] == "legin":
        # ato do DOU lido na Legislacao Informatizada da Camara pelo coleta_web.py (dec13173, lc239, ec141, dleg12;
        # lei/mpv so quando o Congresso nao listou): o formato do ato do Congresso; sem a data do DOU no detalhe,
        # PENDENCIA DE VERIFICACAO. A chave e a do Congresso/PUSH (planalto|tipo|numero|ano|data do ato)
        n = int(e["numero"])
        dou = e.get("dou") or ""
        base = {"categoria": "Planalto/Legislação",
                "status": "CONFIRMADO POR FONTE OFICIAL ALTERNATIVA" if dou else "PENDÊNCIA DE VERIFICAÇÃO",
                "titulo": "%s nº %s, de %s" % (e["tipo"], "{:,}".format(n).replace(",", "."), e["data_ato"]),
                "meta": ("DOU %s%s" % (dou[:5], " · edição extra" if e.get("extra") else "")) if dou
                else "data do DOU não confirmada na página oficial",
                "resumo": e["ementa"], "url": e["url"], "fonte": "Câmara dos Deputados (Legislação Informatizada)",
                "data": datetime.strptime(e["data_ato"], "%d/%m/%Y").date().isoformat(),
                # o selo sai uma vez por grupo (_grupos_planalto): o ato sem DOU confirmado fica num grupo proprio
                "grupo": "Câmara dos Deputados — Legislação Informatizada%s" % ("" if dou else " (DOU a confirmar)"),
                "chave": e["chave"]}
    elif e and e["_fonte"] == "camara_noticias":
        # noticia da Agencia Camara lida no site (cam1, cam2): sancao/veto/MP ([LEI]) ou votacao de Plenario
        # a chave e a automatica (agencia-camara|ato|<titulo>|ano|data): a mesma do item escrito a partir do
        # boletim por e-mail, para a noticia que ja saiu por um caminho nao voltar pelo outro
        q = str(e.get("quando") or "")
        dia = q[:10]
        base = {"categoria": "Planalto/Legislação", "status": "CONFIRMADO POR FONTE OFICIAL ALTERNATIVA",
                "titulo": e["titulo"], "url": e["url"], "fonte": "Agência Câmara",
                "grupo": "Agência Câmara — Plenário, sanções e vetos",
                "meta": "%s/%s%s" % (dia[8:10], dia[5:7], " " + q[11:16] if len(q) > 15 else "") if dia else "",
                "data": dia, "hora": q[11:16] if len(q) > 15 else ""}
    elif e and e["_fonte"] in ("conjur", "migalhas"):
        veic = "ConJur" if e["_fonte"] == "conjur" else "Migalhas"
        q = e.get("quando") or ""
        dia = (q or str(e.get("data") or ""))[:10]
        opiniao = e.get("tipo") in ("artigo", "coluna")
        mid = re.search(r"/quentes/(\d+)/", e["url"])
        sl = (mid.group(1) + "-" if mid else "") + slug(e["url"].rstrip("/").rsplit("/", 1)[-1], 50)
        base = {"categoria": "Opinião/Análise" if opiniao else "Mídia",
                "status": "OPINIÃO/ANÁLISE" if opiniao else "MÍDIA ESPECIALIZADA",
                "titulo": e["titulo"], "resumo": "" if opiniao else (e.get("resumo") or ""),
                "url": e["url"], "fonte": veic, "data": dia, "hora": q[11:16] if len(q) > 15 else "",
                "chave": "%s|%s|%s|%s|%s" % (e["_fonte"], "opiniao" if opiniao else "noticia", sl, dia[:4], dia)}
        if opiniao and e.get("autor"):
            base["autor"] = e["autor"]          # assinatura da pagina (coleta_web), nunca o meta author do editor
    elif e and e["_fonte"] == "informativo" and e.get("ok"):
        idx = selecionar(it.get("destaques"), len(e["itens"]), ref, erros, avisos)
        anunciada = e.get("anunciada_em") or e.get("anunciada_na_edicao") or ""
        base = {"categoria": "Informativos", "status": "CONFIRMADO POR FONTE OFICIAL",
                "titulo": NOME_INF[e["tipo"]] % e["numero"], "meta": e.get("data") or "",
                "url": e["url"], "data": data_extenso(e.get("data")),
                "fonte": "STJ — página oficial do informativo" if e["tipo"] == "stj" else "STF — documento oficial",
                "chave": e["chave"],
                "destaques_texto": destaques_html(e["tipo"], [e["itens"][i] for i in idx], hoje),
                "observacao": "%d de %d destaques publicados" % (len(idx), len(e["itens"])),
                "herdada": e.get("situacao") in ("atrasada", "pulada"),
                "_revisita": bool(e.get("revisita")),
                "_nota_auto": ("destaques da edição anunciada em %s" % br_data(anunciada))
                if e.get("situacao") == "atrasada" and br_data(anunciada) else ""}
        if e["tipo"] == "rg":
            base["temas"] = [str(e["itens"][i]["tema"]) for i in idx if e["itens"][i].get("tema")]
            aviso_ordem_rg(it.get("destaques"), e["itens"], idx, ref, avisos)
    elif m:
        # edicao anunciada por e-mail cujo documento nao abriu: numero, data e link, sem destaques
        tipo, n = m.group(1), int(m.group(2))
        dia = it.get("data") or ""
        base = {"categoria": "Informativos", "status": "CONFIRMADO POR FONTE OFICIAL",
                "titulo": NOME_INF[tipo] % n, "sem_conteudo": True,
                "fonte": "STJ CodJu" if tipo == "stj" else "Push STF Informativo",
                "resumo": "Conteúdo não acessível nesta execução; os destaques entram quando o documento abrir.",
                "chave": "%s|informativo|%s%d|%s|%s" % ("stj" if tipo == "stj" else "stf",
                                                       "repercussao-geral-" if tipo == "rg" else "", n,
                                                       dia[:4], dia)}
        if not dia:
            erros.append("ref %s: documento não lido pelo script — informe \"data\" (AAAA-MM-DD do e-mail) "
                         "e \"url\" (link do e-mail)" % ref)
    else:
        erros.append("ref desconhecido: %r (use um id impresso por coleta_web.py ou informativos.py)" % ref)
        return None
    novo = dict(base)
    novo.update({k: v for k, v in it.items()
                 if k != "destaques" and k not in DERIVADOS and not k.startswith("_") and v not in (None, "")})
    resenha_no_ref(novo, it, e, ref, avisos)
    # P5: resumo que a coleta marcou como cortado (ConJur): "…" no fim, ou nada se ficar curto. Vale tambem quando o
    # orquestrador copiou o mesmo texto no item; resumo proprio dele fica como escrito. coleta_web.json antigo (sem o
    # campo): nada muda
    if e and e.get("resumo_truncado") and novo.get("resumo") \
            and str(novo["resumo"]).strip() == str(e.get("resumo") or "").strip():
        novo["resumo"] = resumo_cortado(novo["resumo"])
        if not novo["resumo"]:
            del novo["resumo"]
    return novo


# fontes de ato federal lidas em pagina oficial (ALTERNATIVA) cujo ref aceita `resenha` (o mesmo ato na Resenha do
# PUSH): outra fonte de lei/ato lida por script entra aqui. Noticia (Agencia Camara) nao: nao e o ato.
FONTES_ATO_RESENHA = ("congresso_leis", "congresso_mpv", "legin")


def resenha_no_ref(novo, it, e, ref, avisos):
    """Lei ou MPV do Congresso (lei…/mpv…) que tambem veio na Resenha Diaria do PUSH: `resenha` no ref da o grupo, a
    fonte ("PUSH Planalto") e o selo CONFIRMADO POR FONTE OFICIAL (ROTINA: PUSH -> oficial); grupo, fonte e status
    escritos vencem. Sem resenha, fica a pagina do Congresso (ALTERNATIVA). Antes (20/11) a resenha era descartada em
    silencio e o selo do PUSH saia sob "Congresso Nacional — últimas leis publicadas". A chave nao muda."""
    if not (e and e.get("_fonte") in FONTES_ATO_RESENHA and it.get("resenha")) or it.get("grupo"):
        return
    g = grupo_resenha(it["resenha"])
    if not g:
        avisos.append("ref %s: \"resenha\" sem data reconhecível (%s) — escreva \"grupo\"" % (
            ref, curto(it["resenha"])))
        return
    novo["grupo"] = g
    novo["fonte"] = it.get("fonte") or "PUSH Planalto"
    if not it.get("status"):
        novo["status"] = "CONFIRMADO POR FONTE OFICIAL"


SELO_PADRAO = {"STF Notícias": "CONFIRMADO POR FONTE OFICIAL", "STF Jurisprudência": "CONFIRMADO POR FONTE OFICIAL",
               "STJ Notícias": "CONFIRMADO POR FONTE OFICIAL", "STJ Jurisprudência": "CONFIRMADO POR FONTE OFICIAL",
               "Informativos": "CONFIRMADO POR FONTE OFICIAL", "Mídia": "MÍDIA ESPECIALIZADA",
               "Opinião/Análise": "OPINIÃO/ANÁLISE"}
ATO = re.compile(r"^(Lei Complementar|Lei|Decreto Legislativo|Decreto|Medida Provis[óo]ria|Emenda Constitucional|"
                 r"Resolu[çc][ãa]o|Portaria)\s+n[ºo°.]*\s*([\d.]+)", re.I)
TIPO_CHAVE = {"Planalto/Legislação": "ato", "STF Notícias": "noticia", "STF Jurisprudência": "tese",
              "STJ Notícias": "noticia", "STJ Jurisprudência": "tese", "Informativos": "informativo",
              "Mídia": "noticia", "Opinião/Análise": "opiniao", "Fofoquinha": "fofoca"}
SEM_CONFIRMACAO = "sem confirmação oficial localizada nesta execução"
# STJ Noticias vinda da midia (21/11/2026): sem a nota por item acima, que sugeria uma busca oficial que nao acontece
# (a lista de noticias e o RSS do STJ vem de res.stj.jus.br, recusado pela rede do ambiente); uma linha fixa no topo
# da secao explica o selo MÍDIA ESPECIALIZADA. A nota por item continua so onde o orquestrador a escreve (Midia,
# Fofoquinha), para fato que exige ato oficial.
SO_SEM_CONFIRMACAO = re.compile(r"^\s*sem\s+confirma[çc][ãa]o\s+oficial(?:\s+localizada)?(?:\s+nesta\s+execu[çc][ãa]o)?"
                                r"\s*\.?\s*$", re.I)
# Verdadeira tambem na secao mista (um item oficial achado por outra via ao lado dos de midia): fala da lista de
# noticias do portal, que a rotina nao le, e nao "das noticias do STJ" em geral.
LINHA_STJ_MIDIA = ("Julgados do STJ noticiados pela mídia especializada, sem confirmação oficial nesta edição: a "
                   "rotina não lê a lista de notícias do portal do STJ. As teses oficiais vêm do CodJu e do "
                   "Informativo STJ.")


def chave_auto(it):
    """fonte|tipo|slug|ano|data quando o orquestrador nao escreveu a chave."""
    dia = it.get("data") or ""
    cat = it.get("categoria")
    m = ATO.match(it.get("titulo") or "")
    if cat == "Planalto/Legislação" and m:
        tipo = slug(m.group(1))
        tipo = "mpv" if tipo.startswith("medida-prov") else tipo
        return "planalto|%s|%s|%s|%s" % (tipo, m.group(2).replace(".", ""), dia[:4], dia)
    fonte = slug((it.get("fonte") or cat or "fonte").split("(")[0], 24) or "fonte"
    return "%s|%s|%s|%s|%s" % (fonte, TIPO_CHAVE.get(cat, "item"), slug(it.get("titulo"), 56), dia[:4], dia)


# ------------------------------------------------------------------ campos deterministicos dos itens
SO_SEM_LINK = re.compile(r"^\s*(?:clipping\s+)?sem\s+link(?:\s+pr[óo]prio)?\s*\.?\s*$", re.I)
TEM_SEM_LINK = re.compile(r"sem\s+link", re.I)


def limpar_nota(nota):
    """'clipping sem link; sem confirmação...' -> 'sem confirmação...': o rotulo 'sem link' e automatico."""
    partes = [p.strip() for p in str(nota or "").split(";")]
    return "; ".join(p for p in partes if p and not SO_SEM_LINK.match(p))


def sem_parenteses(texto):
    """Texto que sai ENTRE parenteses (nota do item, nota do Planalto) sem parenteses dentro (lows[3], 20/11: "(o
    ConJur noticiou … para julgamento (ver Mídia))"): o de dentro vira aposto com travessao — "(… para julgamento —
    ver Mídia)". O mesmo cuidado de norm_meta e nome_feriado. 23/11 (ensaio): no meio da frase o aposto fecha com
    outro travessao ("a pauta oficial (STF Notícias) mantém" -> "a pauta oficial — STF Notícias — mantém"; antes
    ficava "— STF Notícias mantém", travessao sem par); no fim ou antes de pontuacao, um so. Parentese sem par e
    "()" vazio saem; travessao repetido ou solto nas pontas tambem."""
    s = str(texto or "")

    def aposto(m):
        dentro = m.group(1).strip()
        if not dentro:
            return ""
        resto = m.string[m.end():]
        fecha = resto.strip() and not re.match(r"\s*[,;:.!?…)\]]", resto)
        return " — " + dentro + (" — " if fecha else "")
    for _ in range(3):                                  # ate aninhados
        s = re.sub(r"\s*\(\s*([^()]*?)\s*\)", aposto, s)
    s = re.sub(r"\s*[()]\s*", " ", s)                    # parentese sem par
    s = re.sub(r"—(?:\s*—)+", "—", s)                   # travessao repetido
    s = re.sub(r"[ \t]{2,}", " ", s)                      # o aposto fechado antes de um espaco
    return re.sub(r"^[\s—]+|[\s—]+$", "", s)


EXTRA_META = re.compile(r"\(\s*(?:edi[çc][ãa]o\s+)?extra\s*\)|(?:edi[çc][ãa]o\s+)?\bextra\b", re.I)
DATA_ATO_META = re.compile(r"\s*(?:(?:do\s+)?ato\s+(?:de\s+)?)?\d{1,2}/\d{1,2}(?:/\d{2,4})?\s*[,;·]?\s*", re.I)


def norm_meta(meta):
    """Metadado do Planalto no formato 'DOU DD/MM[ · edição extra][; <resto>]'. Aceita o antigo
    'DD/MM, DOU DD/MM (edição extra)' e o do coletor 'ato DD/MM/AAAA; DOU DD/MM/AAAA (edição extra)'.
    So sai a data do ato antes do DOU (o titulo ja a traz) e a marca de edicao extra (vira ' · edição extra');
    todo o resto escrito pelo orquestrador fica, depois de '; ', sem parenteses aninhados: veto, republicacao,
    retificacao, vigencia ('DOU 13/11 (republicação por incorreção)' -> 'DOU 13/11; republicação por incorreção')."""
    m = str(meta or "").strip()
    if not m:
        return ""
    dou = re.search(r"\bDOU\s+(?:de\s+)?(\d{1,2})/(\d{1,2})(?:/\d{2,4})?", m)
    if not dou:
        return re.sub(r"\s*\(([^()]*)\)", r" · \1", m)
    out = "DOU %02d/%02d" % (int(dou.group(1)), int(dou.group(2)))
    if EXTRA_META.search(m):
        out += " · edição extra"
    antes = m[:dou.start()]
    if DATA_ATO_META.fullmatch(antes) or not antes.strip():
        antes = ""
    partes = []
    for s in (antes, m[dou.end():]):
        s = EXTRA_META.sub("", s)
        for _ in range(3):                         # parenteses (ate aninhados) viram separador
            s = re.sub(r"\(([^()]*)\)", r"; \1;", s)
        for p in re.split(r"\s*[;·]\s*", s):
            p = p.strip(" ,:;·-–—()")
            if p:
                partes.append(p)
    return out + "".join("; " + p for p in partes)


def grupo_resenha(r):
    """'Resenha Diária PUSH Legislação - 13/11/2026 (edição extra) | recebida 14/11 01h43' ->
    'Resenha Diária PUSH Legislação de 13/11 — edição extra (recebida em 14/11, 01h43)'. '' se nao reconhecer."""
    s = str(r or "")
    m = re.search(r"Legisla\w*\s*(?:[-–—:]|de)?\s*(\d{1,2})/(\d{1,2})", s, re.I)
    if not m:
        return ""
    g = "Resenha Diária PUSH Legislação de %02d/%02d" % (int(m.group(1)), int(m.group(2)))
    if re.search(r"extra", s, re.I):
        g += " — edição extra"
    rec = re.search(r"recebida\s+(?:em\s+)?(\d{1,2})/(\d{1,2})(?:/\d{2,4})?,?\s*(?:[àa]s\s+)?(\d{1,2})\s*[h:]\s*(\d{2})",
                    s, re.I)
    if rec:
        g += " (recebida em %02d/%02d, %02dh%s)" % (int(rec.group(1)), int(rec.group(2)), int(rec.group(3)),
                                                    rec.group(4))
    return g


def eh_rotina(it):
    """G7: credito orcamentario, remanejamento de cargos, aumento de capital, acordo de turismo ou de
    servicos aereos — nunca cooperacao juridica penal, extradicao, transferencia de presos."""
    texto = "%s %s" % (it.get("titulo") or "", it.get("resumo") or "")
    if ROTINA_EXCETO.search(texto):
        return False
    return bool(ROTINA_ATO.search(texto)) or bool(ROTINA_CARGOS.search(texto) and not CARGOS_EXCETO.search(texto))


def impacto_auto(ementa, titulo=""):
    """'Altera o Decreto-Lei nº 2.848 (Código Penal) e a Lei nº 7.210' -> 'Altera: Código Penal; Lei de
    Execução Penal'. So o objeto do verbo conta (ate a finalidade ou a oracao "que regulamenta..."); decreto,
    resolucao e portaria nunca alteram lei; Constituicao so em emenda constitucional. '' na duvida (o AVISO
    "Planalto sem impacto" segue pedindo ao orquestrador)."""
    m = VERBO_ALTERA.match(ementa or "")
    if not m or ATO_INFRALEGAL.match(titulo or ""):
        return ""
    objeto = ementa[m.end():]
    fim = FIM_OBJETO.search(objeto)
    if fim:
        objeto = objeto[:fim.start()]
    achados = []
    for rx, rot in CODIGOS:
        if rot == "Constituição Federal" and not ATO_EC.match(titulo or ""):
            continue
        x = rx.search(objeto)
        if x and rot not in [r for _, r in achados]:
            achados.append((x.start(), rot))
    if not achados:
        return ""
    verbo = "Revoga" if m.group(1).lower().startswith("revoga") else "Altera"
    out = verbo + ":"
    for _, rot in sorted(achados):
        cand = out + (" " if out.endswith(":") else "; ") + rot
        if len(cand) > IMPACTO_MAX:
            break
        out = cand
    return out if not out.endswith(":") else ""


def item_oficial(it):
    """O item vem de fonte oficial? Pela URL (orgao publico) e, sem URL, pelo rotulo da fonte: lista fechada
    ("Push STF", "STJ CodJu", "PUSH Planalto", "Congresso Nacional", "boletim da Agência Câmara"...). Basta uma
    palavra fora do vocabulario oficial ("STJ (via JOTA)", "JOTA (decisão do STJ)") para o rotulo nao valer."""
    h = host(it.get("url"))
    if h:
        return bool(HOST_OFICIAL.search(h))
    t = unicodedata.normalize("NFKD", str(it.get("fonte") or "").lower())
    palavras = {p for p in re.split(r"[^a-z0-9]+", "".join(c for c in t if not unicodedata.combining(c)))
                if p and not p.isdigit()}
    return bool(palavras & ROTULO_OFICIAL) and palavras <= VOCAB_ROTULO_OFICIAL


# ------------------------------------------------------------------ 2. ledger em memoria
def sem_movimento(campos):
    """ledger_updates.concursos.<id>.movimento = false: a linha foi reescrita sem fato novo para o leitor (enriquecida
    com fato antigo, nota de busca): grava, mas sem "Atualizado hoje", fundo creme, item 'atualizado' nem mudou_em
    (o helper faz o mesmo). O campo nao vai ao registro. Ausente ou true: linha/selo/prazos mudados = movimento.
    Com selo ou prazos mudados no mesmo update o opt-out e ignorado (movimento_ignorado, em estado_concursos)."""
    v = (campos or {}).get("movimento")
    return v is False or str(v).strip().lower() in ("false", "0", "nao", "não")


def movimento_ignorado(upd, antes):
    """E-min (e), ensaio de 23/11: `movimento: false` e para a linha reescrita sem fato novo. Junto com selo ou prazos
    mudados (selo igual ao do registro e copia, nao mudanca) o leitor perderia a marca de um fato que ele ve: o
    opt-out sai do update NO LUGAR — o execucao.resolvido.json leva o update sem ele e o helper grava o mudou_em, como
    o e-mail mostra — e sai AVISO (comum). Devolve os AVISOs."""
    out = []
    for ident, campos in (upd or {}).items():
        if not isinstance(campos, dict) or campos.get("remover") or not sem_movimento(campos) or ident not in antes:
            continue
        mudados = [k for k in ("selo", "prazos") if k in campos and campos[k] != antes[ident].get(k)]
        if mudados:
            del campos["movimento"]
            out.append("ledger_updates.concursos.%s.movimento: false ignorado — %s mudou hoje: sai \"Atualizado hoje\" "
                       "e o registro conta como mudado (movimento: false vale só para a linha reescrita sem fato novo)"
                       % (ident, " e ".join(mudados)))
    return out


def aplicar_concursos(concursos, upd):
    """Copia do registro com ledger_updates.concursos. Devolve (lista, novos, alterados).
    Alterado = linha, selo ou prazos mudaram (selos.mudou, o mesmo criterio do mudou_em do helper), salvo
    "movimento": false (sem_movimento)."""
    regs = copy.deepcopy(concursos)
    por_id = {c["id"]: c for c in regs}
    novos, alterados = set(), set()
    for ident, campos in (upd or {}).items():
        if campos.get("remover"):
            regs = [c for c in regs if c["id"] != ident]
            por_id.pop(ident, None)
            continue
        gravar = {k: v for k, v in campos.items() if k not in ("desfecho", "movimento")}
        if ident in por_id:
            antes = dict(por_id[ident])
            por_id[ident].update(gravar)
            # so verificado_em novo (RODIZIO IGUAL) ou fonte/dominio nao e novidade para o leitor
            if selos.mudou(antes, por_id[ident]) and not sem_movimento(campos):
                alterados.add(ident)
        else:
            c = dict(gravar, id=ident)
            regs.append(c)
            por_id[ident] = c
            novos.add(ident)
    return regs, novos, alterados


def aplicar_pendencias(vivas, upd):
    pend = copy.deepcopy(vivas)
    por_id = {p["id"]: p for p in pend}
    for ident, campos in (upd or {}).items():
        if campos.get("remover"):
            pend = [p for p in pend if p["id"] != ident]
        elif ident in por_id:
            por_id[ident].update({k: v for k, v in campos.items() if k != "desfecho"})
        else:
            pend.append(dict(campos, id=ident, _nova=True))
    return pend


def orgao(c):
    return (c.get("linha") or c.get("id") or "").split(":")[0].split(" — ")[0].strip()


def ler_banca(caminho, hoje):
    """bancas.json de HOJE (o inicio.py grava `data`); outro dia, formato antigo ou ausente = None."""
    res = ler(caminho)
    if not isinstance(res, dict) or res.get("data") != hoje:
        return None
    return res


MIGRACOES_HOJE = "migracoes-hoje.json"


def migracoes_do_dia(j, led, caminho=None):
    """O RESUMO que o work/migracoes.py grava em $ROBOZINHO_TMP/migracoes-hoje.json (formato no cabecalho de la):
    {"migracoes": [ids], "concursos": {id: "novo"|"alterado"|{"removido": desfecho, "linha", "bloco"}},
    "pendencias": {id: "alterado"|{"removido": desfecho, "texto", "faixa"[, "concurso"]}}}. 23/11/2026 (ensaio): o
    ledger chega ao montador ja migrado e o ledger_updates do dia nao traz a migracao, entao o ENAM criado por ela
    saia sem NOVO, PGE-RJ/DPE-SP sem "Atualizado hoje" e as remocoes sem "Saiu do acompanhamento". Vale so o de
    HOJE (janela.data) e so enquanto o ledger nao foi gravado por outra execucao depois da migracao (base_execucao:
    a edicao extra na mesma maquina nao repete o NOVO da diaria; o --refazer da mesma execucao repete). Ausente,
    ilegivel ou de outro dia: nada."""
    vazio = {"migracoes": [], "concursos": {}, "pendencias": {}}
    r = ler(caminho or tmp(MIGRACOES_HOJE))
    if not isinstance(r, dict) or r.get("data") != j.get("data"):
        return vazio
    if "base_execucao" in r and (led or {}).get("atualizado_por_execucao") not in (r.get("base_execucao"),
                                                                                   j.get("execution_id")):
        return vazio
    return {"migracoes": [str(x) for x in r.get("migracoes") or [] if x],
            "concursos": r["concursos"] if isinstance(r.get("concursos"), dict) else {},
            "pendencias": r["pendencias"] if isinstance(r.get("pendencias"), dict) else {}}


def removido_na_migracao(m):
    return isinstance(m, dict) and "removido" in m


def execucoes_historico(caminho, com_arquivos=False):
    """Execucoes do historico principal (e, se pedido, dos arquivos mensais listados em archive_files)."""
    h = ler(caminho, {}) or {}
    out = list(h.get("executions") or [])
    if com_arquivos:
        pasta = os.path.dirname(os.path.abspath(caminho))
        for nome in h.get("archive_files") or []:
            out += (ler(os.path.join(pasta, nome), {}) or {}).get("executions") or []
    return out


CLASSE_INSCRICAO = {"inscricoes_fim": "o fim das inscrições", "inscricoes_inicio": "o início das inscrições"}
RE_AVISO_TIPO = re.compile(r"^ledger_updates\.concursos\.(\S+?)\.prazos\[(\d+)\]\.tipo\b")


def tipo_contra_evento(upd, por_id, hoje, ctx_banca):
    """AVISOs (acionaveis) para `prazos[n].tipo` do update de hoje que esconde um prazo de inscricao: o `evento`
    (so o texto; selos.tipo_contradiz_evento, a regra do helper) diz inscricoes_fim/inscricoes_inicio e o tipo
    escrito da outra classe. O tipo
    prevalece sobre o evento, e com 'outro' o selo por data ignora o prazo: o e-mail saia INSCRIÇÕES ABERTAS (ou
    ENCERRA HOJE de ontem) para inscricao que acaba em 2 dias, sem ENCERRA EM BREVE nem rebaixamento. Nao muda
    o selo: o tipo pode ser decisao (o regex do evento erra); diz o que a data daria com a classe do evento."""
    out = []
    for ident, campos in (upd or {}).items():
        if not isinstance(campos, dict) or campos.get("remover") or not isinstance(campos.get("prazos"), list):
            continue
        for n, p in enumerate(campos["prazos"]):
            if not isinstance(p, dict) or "tipo" not in p:
                continue
            if hasattr(selos, "tipo_contradiz_evento"):     # a mesma regra do helper (avisos_tipo_prazo)
                pelo_evento = selos.tipo_contradiz_evento(p)
            else:
                pelo_evento = selos.classe_prazo({k: v for k, v in p.items() if k != "tipo"})
                if selos.classe_prazo(p) == pelo_evento:
                    pelo_evento = None
            if pelo_evento not in CLASSE_INSCRICAO:
                continue
            daria = ""
            c = por_id.get(ident)
            if c is not None:
                alt = dict(c, prazos=[dict(q, tipo=pelo_evento) if i == n and isinstance(q, dict) else q
                                      for i, q in enumerate(campos["prazos"])])
                x = ctx_banca.get(ident) or {}
                try:
                    novo, motivo = selos.selo_por_data(alt, hoje, banca_lida_hoje=x.get("banca_lida_hoje", False),
                                                       ultima_retificacao=x.get("ultima_retificacao"),
                                                       inicio_inscricoes_banca=x.get("inicio_inscricoes"))
                except (KeyError, ValueError, TypeError, AttributeError):
                    novo, motivo = c.get("selo"), None
                if novo != c.get("selo") and motivo:
                    porque = motivo.split(": ", 1)[-1].split(": ")[0].split(" — ")[0]
                    daria = " (com '%s', o selo por data daria '%s': %s)" % (pelo_evento, novo, porque)
            out.append("ledger_updates.concursos.%s.prazos[%d].tipo: %r num prazo cujo evento é %s («%s») — com "
                       "esse tipo o selo por data ignora o prazo%s; se é %s, escreva tipo '%s' ou omita o tipo; "
                       "se não é, aceite o aviso" % (
                           ident, n, p.get("tipo"), CLASSE_INSCRICAO[pelo_evento], curto(p.get("evento"), 80),
                           daria, CLASSE_INSCRICAO[pelo_evento], pelo_evento))
    return out


def sem_tipo_repetido(do_helper, proprios):
    """AVISOs do helper (--validar) sem o de prazos[n].tipo que o montador ja deu para o mesmo prazo: fica o do
    montador, que diz o selo que a data daria com o mesmo estado do e-mail. Prazo so do helper continua."""
    meus = {m.groups() for m in map(RE_AVISO_TIPO.match, proprios) if m}
    out = []
    for a in do_helper:
        m = RE_AVISO_TIPO.match(a)
        if not (m and m.groups() in meus):
            out.append(a)
    return out


def estado_concursos(ex, j, led, op, avisos):
    """Registro de concursos como sai no e-mail: ledger + ledger_updates de hoje + carimbo da banca lida
    hoje + selo por data (work/selos.py; nunca sobre selo escrito hoje) + mudou_em (migracao em memoria).
    Mesma regra do helper (aplicar_mecanicos_concursos), para o e-mail e o ledger nao divergirem:
    - selo ESCRITO hoje = selos.selo_escrito (difere do registro de antes); a copia do selo nao e decisao;
    - carimbo e contexto da banca com o update de hoje: o registro que AINDA diverge do edital nao e
      carimbado nem conta como banca lida (bancas.divergencias_pendentes);
    - selo por data por bancas.selo_do_dia (a regra unica): com divergencia pendente — inclusive o prazo escrito
      hoje que contradiz o edital lido hoje — fica SUSPENSO (o selo do registro) e sai AVISO ACIONÁVEL;
    - migracao aplicada hoje (migracoes_do_dia): os ids dela entram nas marcas do dia como os do ledger_updates
      (NOVO, "Atualizado hoje", "Saiu do acompanhamento") sem reaplicar nada — o ledger ja esta migrado; id que o
      update do dia tambem toca nao se repete (novo prevalece sobre alterado)."""
    hoje = date.fromisoformat(j["data"])
    upd = (ex.get("ledger_updates") or {}).get("concursos") or {}
    antes = {c.get("id"): c for c in led.get("concursos") or []}
    avisos += movimento_ignorado(upd, antes)
    regs, novos, alterados = aplicar_concursos(led.get("concursos") or [], upd)
    por_id = {c["id"]: c for c in regs}
    banca = ler_banca(op.get("bancas") or tmp("bancas.json"), j["data"])
    if banca:
        try:
            carimbos = bancas.carimbos(banca, regs, hoje, upd=upd)
        except (KeyError, ValueError, TypeError):
            carimbos = {}
        for ident, campos in carimbos.items():
            if ident in por_id:      # o julgamento de hoje prevalece; carimbo nao e novidade para o leitor
                por_id[ident].update({k: v for k, v in campos.items() if k not in (upd.get(ident) or {})})
    try:
        ctx_banca = bancas.contexto_selos(banca, regs, hoje, upd) if banca else {}
        pendentes = bancas.divergencias_pendentes(banca, regs, hoje, upd) if banca else {}
    except (KeyError, ValueError, TypeError):
        ctx_banca, pendentes = {}, {}
    avisos += tipo_contra_evento(upd, por_id, hoje, ctx_banca)
    selo_mudou = set()
    for c in regs:
        if selos.selo_escrito(upd.get(c["id"]), antes.get(c["id"])):
            continue
        # a mesma regra do helper (bancas.selo_do_dia): com divergencia pendente (o edital lido hoje contesta a data
        # do registro ou o prazo escrito hoje) o selo por data fica SUSPENSO, com aviso acionavel
        novo, motivo, suspenso = bancas.selo_do_dia(c, hoje, ctx_banca, pendentes)
        if suspenso:
            avisos.append(suspenso)
            continue
        if novo != c.get("selo"):
            if novo == selos.SELO_SEM_CONFIRMACAO:
                # o motivo pede ao orquestrador o selo/os prazos (encerradas ou prorrogadas): nada de
                # "nao escreva o selo"; casa ACIONAVEL ("prorrogação não confirmada")
                avisos.append("selo por data: %s %s" % (c["id"], motivo))
            else:
                avisos.append("selo por data: %s %s (automático; não escreva o selo)" % (c["id"], motivo))
            c["selo"] = novo
            c["mudou_em"] = j["data"]
            selo_mudou.add(c["id"])
        elif motivo:
            avisos.append("%s: %s" % (c["id"], motivo))
    if any(not c.get("mudou_em") for c in regs):
        ignorar = {j.get("execution_id"), j.get("ignorar_execucao")} - {None, ""}
        selos.garantir_mudou_em(regs, lambda: [e for e in execucoes_historico(op.get("historico"), True)
                                               if e.get("execution_id") not in ignorar])
    mig = migracoes_do_dia(j, led, op.get("migracoes"))
    for ident, m in mig["concursos"].items():
        c = por_id.get(ident)
        if c is None or m not in ("novo", "alterado"):
            continue
        if m == "novo":
            novos.add(ident)
            alterados.discard(ident)
        elif ident not in novos:
            alterados.add(ident)
        c["_migracao"] = m                    # so em memoria (linha_concurso): a verificacao pode ser de outro dia
    for ident in novos | alterados:
        por_id[ident]["mudou_em"] = j["data"]
    # concurso removido hoje: sai do bloco com uma linha "Saiu do acompanhamento" e o desfecho (so neste dia)
    removidos = [{"id": ident, "orgao": orgao(antes[ident]), "bloco": antes[ident].get("bloco"),
                  "desfecho": str(campos.get("desfecho") or "").strip()}
                 for ident, campos in upd.items()
                 if isinstance(campos, dict) and campos.get("remover") and ident in antes and ident not in por_id]
    ja = {r["id"] for r in removidos}
    removidos += [{"id": ident, "orgao": orgao({"id": ident, "linha": m.get("linha")}), "bloco": m.get("bloco"),
                   "desfecho": str(m.get("removido") or "").strip()}
                  for ident, m in mig["concursos"].items()
                  if removido_na_migracao(m) and ident not in por_id and ident not in ja]
    return {"regs": regs, "novos": novos, "alterados": alterados, "selo_mudou": selo_mudou,
            "banca": banca or {}, "pendentes": set(pendentes), "removidos": removidos, "migracoes": mig}


# ------------------------------------------------------------------ 3. secoes do e-mail
def item_padrao(it):
    """Selo + titulo em negrito + resumo + fonte (com link) e data/hora."""
    quando = br_data(it.get("data"))
    if it.get("hora"):
        quando += " " + it["hora"]
    fonte = link(it.get("url"), esc(it.get("fonte") or "fonte"))
    cauda = ", ".join(x for x in (fonte, quando) if x)
    nota = it.get("nota") or ""
    extras = "; ".join(x for x in (it.get("_nota_auto") or ("herdada" if it.get("herdada") else ""), nota,
                                   "" if it.get("url") or TEM_SEM_LINK.search(nota) else "sem link") if x)
    titulo = it["titulo"] + (" — " + it["meta"] if it.get("meta") else "")
    resumo = (esc(ponto(it["resumo"])) + " ") if it.get("resumo") else ""
    impacto = (" <i>Para a prova</i> — %s" % esc(ponto(it["impacto"]))) if it.get("impacto") else ""
    return '<p style="margin:0 0 12px">%s <b>%s</b> %s<i>Fonte: %s%s.</i>%s</p>' % (
        selo(it["status"]), esc(ponto(titulo)), resumo, cauda, " (%s)" % esc(sem_parenteses(extras)) if extras else "",
        impacto)


def _grupos_planalto(itens, topo):
    partes, grupo = [], object()
    for n, it in enumerate(itens):
        g = it.get("grupo") or it.get("fonte") or ""
        if g != grupo:
            grupo = g
            partes.append('<div style="margin:%s 0 4px">%s <span style="font-size:12px;color:%s">— %s</span></div>'
                          % (px(14 if (partes or topo) else 0), selo(it["status"]), APOIO_COR, esc(ponto(g))))
        ultimo = n + 1 == len(itens) or (itens[n + 1].get("grupo") or itens[n + 1].get("fonte") or "") != g
        meta = (' <span style="font-size:11px;color:%s">· %s</span>' % (APOIO_COR, esc(it["meta"]))
                if it.get("meta") else "")
        nota = (" <i>(%s)</i>" % esc(sem_parenteses(it["nota"]))) if it.get("nota") else ""
        corpo_ato = ("<br>" + esc(ponto(it["resumo"]))) if it.get("resumo") else ""
        impacto = ("<br><i>Para a prova</i> — %s" % esc(ponto(it["impacto"]))) if it.get("impacto") else ""
        partes.append('<div style="padding:6px 0%s">%s%s%s%s%s</div>' % (
            "" if ultimo else ";border-bottom:1px solid " + LINHA,
            link(it.get("url"), "<b>%s</b>" % esc(it["titulo"]), ";text-decoration:underline"),
            meta, nota, corpo_ato, impacto))
    return partes


def sec_planalto(itens, ss, ex):
    if not itens:
        sem_push = ss.get("gmail_push_planalto") in ("vazio", "falha", "nao_tentada", None)
        corpo = apoio(ex["email"].get("apoio", {}).get("Planalto/Legislação") or (
            "PUSH Planalto não recuperado nesta execução; nenhuma lei ou medida provisória nova na página do "
            "Congresso." if sem_push else "Nenhum ato novo na janela (PUSH Planalto e página do Congresso "
                                          "consultados)."))
    else:
        normais = [it for it in itens if not it.get("_rotina")]
        rotina = [it for it in itens if it.get("_rotina")]
        partes = _grupos_planalto(normais, False)
        if rotina:   # G7: no fim da secao, completos (com ementa e link) — so a ordem muda
            partes.append(subtitulo(SUBTITULO_ROTINA, 14 if partes else 0))
            partes += _grupos_planalto(rotina, False)
        corpo = "\n".join(partes)
    # lows[4]: sem margem negativa (cliente de e-mail que a recusa descarta a declaracao inteira, e a frase perdia o
    # recuo de 14px e o espaco de 12px). O mesmo desenho sem ela: o titulo da secao com 6px embaixo (antes 10px do
    # titulo + -4px da frase, margens colapsadas = 6px). Captura de tela identica pixel a pixel.
    frase = ('<div style="font-size:12px;color:#8a8f5c;font-style:italic;margin:0 0 12px 14px">%s</div>'
             % FRASE_PLANALTO)
    return secao("🏛️ Planalto — Resenha Diária e legislação federal", frase + "\n" + corpo, margem_titulo=6)


def _itens_html(itens):
    partes = []
    for it in itens:
        partes.append(item_padrao(it))
        if it.get("destaques_texto"):
            partes[-1] = partes[-1].replace("margin:0 0 12px", "margin:0 0 6px", 1)
            partes.append('<div style="margin:0 0 14px 14px;font-size:12px;line-height:18px">%s</div>' % "\n".join(
                '<p style="margin:0 0 6px">▸ %s</p>' % d for d in it["destaques_texto"]))
    return partes


def sec_itens(cat, titulo, vazio, itens, ex):
    if not itens:
        return secao(titulo, apoio(ex["email"].get("apoio", {}).get(cat) or vazio))
    partes = _itens_html(itens)
    if cat == "STJ Notícias" and any(not item_oficial(it) for it in itens):
        # linha fixa no topo, no lugar da nota por item (ver LINHA_STJ_MIDIA)
        partes.insert(0, '<div style="font-size:12px;line-height:18px;color:%s;margin-bottom:10px">%s</div>'
                      % (APOIO_COR, esc(LINHA_STJ_MIDIA)))
    return secao(titulo, "\n".join(partes))


def sec_informativos(titulo, vazio, itens, ex):
    """Informativos; as edicoes antigas revisitadas (C5) num sub-bloco "Em atraso"."""
    if not itens:
        return secao(titulo, apoio(ex["email"].get("apoio", {}).get("Informativos") or vazio))
    atuais = [it for it in itens if not it.get("_revisita")]
    atraso = [it for it in itens if it.get("_revisita")]
    partes = _itens_html(atuais)
    if atraso:
        partes.append(subtitulo("Em atraso — edições anteriores cujo documento só agora abriu", 14 if partes else 0))
        partes += _itens_html(atraso)
    return secao(titulo, "\n".join(partes))


def apoio_calculado(cat, por_cat):
    """D5/G3/A8: a linha de apoio de secao vazia confere o que a edicao traz (email.apoio sobrescreve)."""
    infs = por_cat.get("Informativos") or []

    def edicoes(prefixos, com_conteudo=True):
        """Edicoes da secao Informativos; com_conteudo: so as que trazem destaques (a "sem_conteudo", cujo
        documento nao abriu, sai la como "Conteúdo não acessível" e nao tem teses para apontar)."""
        return [it for it in infs if re.match(r"(%s)\d+$" % prefixos, str(it.get("ref") or ""))
                and not (com_conteudo and it.get("sem_conteudo"))]

    def nao_abriu(lista):
        nomes = " e ".join(("da " if it["titulo"].startswith("Repercussão") else "do ") + it["titulo"] for it in lista)
        return "%s %s não %s nesta execução (número, data e link em 📚 Informativos)" % (
            "os documentos" if len(lista) > 1 else "o documento", nomes, "abriram" if len(lista) > 1 else "abriu")
    if cat == "STF Jurisprudência":
        todas = edicoes("rg|stf", False)
        stf = edicoes("rg|stf")
        if not todas:
            return None
        if not stf:
            return "Teses e julgados do STF desta edição ainda não legíveis: %s." % nao_abriu(todas)
        # "sem RG nova" so quando nenhuma RG da edicao e nova, mesmo a anunciada sem conteudo
        rg_novo = any(str(it.get("ref")).startswith("rg") and not it.get("herdada") for it in todas)
        nomes = "; ".join(it["titulo"] for it in sorted(stf, key=lambda x: not str(x.get("ref")).startswith("rg")))
        if rg_novo:
            return "Teses e julgados do STF desta edição estão em 📚 Informativos (%s)." % nomes
        return "Sem Repercussão Geral em Pauta nova na janela; teses e julgados do STF desta edição estão em " \
               "📚 Informativos (%s)." % nomes
    stj = edicoes("stj")
    if cat == "STJ Notícias":
        na_midia = any(re.search(r"\bSTJ\b|Superior Tribunal de Justiça", "%s %s" % (it.get("titulo"), it.get("resumo")))
                       for c in ("Mídia", "Fofoquinha") for it in por_cat.get(c) or [])
        if na_midia:
            return None          # a linha padrao ("chegou so pela midia") e verdadeira
        return "Nenhuma notícia do STJ localizada nesta janela%s." % (
            "; o %s está em 📚 Informativos" % stj[0]["titulo"] if stj else "")
    if cat == "STJ Jurisprudência":
        if stj:
            return "Sem teses do CodJu na janela; as do STJ desta edição estão em 📚 Informativos (%s)." % (
                "; ".join(it["titulo"] for it in stj))
        vazias = edicoes("stj", False)
        if vazias:
            return "Sem teses do CodJu na janela; %s." % nao_abriu(vazias)
        return "Sem teses do CodJu nem Informativo STJ novo na janela."
    return None


def partes_linha(linha):
    """'Órgão — Cargo: detalhes' -> ('Órgão — Cargo', 'detalhes'); sem ':' antes do 1º ';', corta no ' — '."""
    cabeca = linha.split(";")[0]
    m = re.match(r"^(.{2,110}?):\s+(.+)$", cabeca)
    if m:
        return m.group(1), linha[len(m.group(1)) + 1:].strip()
    if " — " in cabeca:
        a, b = linha.split(" — ", 1)
        return a.strip(), b.strip()
    return "", linha


def linha_concurso(c, hoje, novos, alterados, zebra):
    """Uma linha: órgão — cargo em negrito + selo; abaixo, os detalhes. Novidade em fundo creme. Registro mudado
    pela migracao de hoje (_migracao, de estado_concursos) e novidade para o leitor mesmo verificado antes (a
    migracao e escrita fora da rotina): "Atualizado hoje" e, sem verificacao de hoje, "(verificado em DD/MM)", sem
    "herdada"."""
    try:
        ver = date.fromisoformat(c.get("verificado_em", ""))
    except ValueError:
        ver = None
    idade = (hoje - ver).days if ver else 999
    linha = (c.get("linha") or "").rstrip(".")
    migrou = bool(c.get("_migracao")) and (c["id"] in novos or c["id"] in alterados)
    novo, mudou = c["id"] in novos, c["id"] in alterados and (idade == 0 or migrou)
    cabeca, corpo = partes_linha(linha)
    corpo = corpo[:1].upper() + corpo[1:]
    selos_html = (selo("NOVO", True) + " " if novo else "") + selo(c.get("selo"), True)
    marca = '<b style="color:#8a6d1d">Atualizado hoje:</b> ' if mudou else ""
    quando = ver.strftime("%d/%m") if ver else "?"
    cauda = "" if idade == 0 else (" <i>(verificado em %s)</i>" % quando if migrou
                                   else " <i>(herdada; verificado em %s)</i>" % quando)
    fundo = ' bgcolor="#fdf6e9"' if (novo or mudou) else (' bgcolor="#f4f6fa"' if zebra else "")
    topo = ("<b>%s</b> " % esc(cabeca)) if cabeca else ""
    return "<tr%s><td>%s%s<br>%s%s.%s</td></tr>" % (fundo, topo, selos_html, marca, esc(corpo), cauda)


ROTULO_CLASSE = {"inscricoes_inicio": "início das inscrições", "inscricoes_fim": "fim das inscrições", "prova": "prova"}


def proximo_a_confirmar(c, hoje):
    """'prova 13/12, a confirmar': a proxima inscricao/prova nao confirmada nos proximos RADAR_DIAS dias que nao esta
    em destaque (de A_CONFIRMAR_DIAS a RADAR_DIAS dias). A linha compacta a mostra: sem isso a data saia do e-mail de
    terca a sexta (o registro compacta e o radar so mostra o nao confirmado ate 14 dias). '' sem hoje ou sem prazo."""
    if hoje is None:
        return ""
    cands = []
    for pz in c.get("prazos") or []:
        d = _data(pz.get("data")) if isinstance(pz, dict) else None
        cl = selos.classe_prazo(pz) if d else None
        if d and cl in ROTULO_CLASSE and not pz.get("confirmado") and 0 <= (d - hoje).days <= RADAR_DIAS \
                and not prazo_em_destaque(pz, hoje):
            cands.append((d, ROTULO_CLASSE[cl]))
    if not cands:
        return ""
    d, rot = min(cands)
    return "%s %s, a confirmar" % (rot, d.strftime("%d/%m"))


def linha_compacta(regs, zebra, hoje=None):
    """Uma linha por bloco: órgão — selo (desde DD/MM[; prova DD/MM, a confirmar]), separados por ' · ' (G6/D7/E6)."""
    def cauda(c):
        partes = [x for x in ("desde " + br_data(c.get("mudou_em")) if c.get("mudou_em") else "",
                              proximo_a_confirmar(c, hoje)) if x]
        return " (%s)" % "; ".join(partes) if partes else ""
    itens = " · ".join("<b>%s</b> — %s%s" % (esc(orgao(c)), esc(c.get("selo") or ""), esc(cauda(c))) for c in regs)
    return '<tr%s><td style="color:%s">Sem mudança recente — selo e data da última mudança: %s.</td></tr>' % (
        ' bgcolor="#f4f6fa"' if zebra else "", APOIO_COR, itens)


def linha_removido(r, zebra):
    """Concurso removido hoje (ledger_updates.concursos.<id>.remover): uma linha esmaecida no bloco, so no dia.
    Sem desfecho (o helper o exige; montagem fora do fluxo): so o orgao, sem travessao solto."""
    desfecho = str(r.get("desfecho") or "").strip()
    return '<tr%s><td style="color:%s">Saiu do acompanhamento: <b>%s</b>%s</td></tr>' % (
        ' bgcolor="#f4f6fa"' if zebra else "", APOIO_COR, esc(r.get("orgao") or r.get("id")),
        (" — " + esc(ponto(desfecho))) if desfecho else ".")


TABELA_CONCURSOS = ('<table width="100%" cellpadding="7" cellspacing="0" style="border-collapse:collapse;'
                    'font-size:12px;line-height:18px">')


def bloco_concursos(nome, regs, hoje, novos, alterados, primeiro, compacto=None, removidos=()):
    out = [] if primeiro else ["<tr><td></td></tr>"]
    out.append('<tr><td bgcolor="%s" style="color:%s;font-weight:bold;font-size:11px">%s</td></tr>'
               % (NAVY, BRANCO, esc(nome)))
    if not regs:
        out.append('<tr><td style="color:%s">Nenhum concurso acompanhado neste bloco; a varredura de descoberta '
                   'segue no rodízio semanal.</td></tr>' % APOIO_COR)
    compacto = compacto or (lambda c: None)
    cheios = [c for c in regs if not compacto(c)]
    comp = [c for c in regs if compacto(c)]
    out += [linha_concurso(c, hoje, novos, alterados, n % 2) for n, c in enumerate(cheios)]
    n = len(cheios)
    if comp:
        out.append(linha_compacta(comp, n % 2, hoje))
        n += 1
    for r in removidos or ():
        out.append(linha_removido(r, n % 2))
        n += 1
    return out


def prazos(regs, hoje):
    itens = []
    for c in regs:
        for pz in c.get("prazos") or []:
            try:
                d = date.fromisoformat(pz.get("data", ""))
            except ValueError:
                continue
            if 0 <= (d - hoje).days <= RADAR_DIAS:
                itens.append((d, (d - hoje).days, c, pz))
    return sorted(itens, key=lambda x: (x[0], not x[3].get("confirmado")))


def quando_txt(n):
    return {0: "hoje", 1: "amanhã"}.get(n, "em %d dias" % n)


def com_divergencia(regs, pend, banca):
    """Ids de concurso com divergencia pendente: pendencia ligada que fala em divergencia ou
    DIVERGE DO REGISTRO da banca lida hoje (decisao 16)."""
    textos = {p.get("id"): "%s %s" % (p.get("id"), p.get("texto") or "") for p in pend or []}
    out = {c["id"] for c in regs if c.get("pendencia")
           and re.search(r"(?i)diverg|inconsist|conflit|contradi|retirar", textos.get(c["pendencia"], ""))}
    for b in (banca or {}).get("concursos") or []:
        for d in b.get("divergencias") or []:
            if d.get("id"):
                out.add(d["id"])
    return out


def prazo_em_destaque(pz, hoje):
    """Regra unica do radar e da compactacao (21/11/2026): prazo confirmado nos proximos RADAR_DIAS dias, ou inscricao
    ou prova NAO confirmada em ate A_CONFIRMAR_DIAS dias. Antes a compactacao contava qualquer prazo em 30 dias
    (confirmado ou nao, de qualquer classe) e repetia todo dia linhas cheias que o radar nem mostrava (ALEPA, PGM
    Curitiba, TRT8 em 20/11). Sem o filtro de divergencia: o radar o aplica so para publicar no quadro; na
    compactacao, a linha inteira e que explica a divergencia."""
    d = _data(pz.get("data")) if isinstance(pz, dict) else None
    if d is None:
        return False
    dias = (d - hoje).days
    if not 0 <= dias <= RADAR_DIAS:
        return False
    if pz.get("confirmado"):
        return True
    return dias <= A_CONFIRMAR_DIAS and selos.classe_prazo(pz) in ("inscricoes_inicio", "inscricoes_fim", "prova")


def radar(regs, hoje, divergentes=()):
    itens = prazos(regs, hoje)
    conf = [x for x in itens if x[3].get("confirmado")]
    aconf = [x for x in itens if not x[3].get("confirmado") and prazo_em_destaque(x[3], hoje)
             and x[2]["id"] not in divergentes] if RADAR_A_CONFIRMAR else []
    if not conf and not aconf:
        return ""

    def linhas(lista, confirmado):
        out = []
        for d, dias, c, pz in lista:
            cor = ("#a61b1b" if dias <= 7 else NAVY) if confirmado else APOIO_COR
            evento = re.sub(r"\s*\((?:fonte )?secund[áa]ria[^)]*\)", "", pz.get("evento") or "")
            out.append('<tr><td width="118" valign="top" style="padding:3px 0;font-weight:bold;color:%s;'
                       'white-space:nowrap">%s · %s</td><td style="padding:3px 0%s">%s — %s</td></tr>' % (
                           cor, d.strftime("%d/%m"), quando_txt(dias), "" if confirmado else ";color:" + APOIO_COR,
                           esc(orgao(c)), esc(evento)))
        return out
    tab = ('<table width="100%%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;font-size:12px;'
           'line-height:17px;color:%s">' % TEXTO)
    out = ['<div style="background:#fdf6e9;border-left:4px solid %s;padding:10px 12px;margin-bottom:12px">' % OURO,
           '<div style="font-size:12px;font-weight:bold;color:%s;margin-bottom:6px">⏰ Prazos no radar '
           '<span style="font-weight:normal;color:%s">· próximos %d dias</span></div>' % (NAVY, APOIO_COR, RADAR_DIAS)]
    if conf:
        out += [tab] + linhas(conf, True) + ["</table>"]
    if aconf:
        out.append('<div style="font-size:11px;color:%s;margin:%s 0 2px">A confirmar — inscrição ou prova em até %d '
                   'dias vista só em fonte secundária:</div>' % (APOIO_COR, px(8 if conf else 0), A_CONFIRMAR_DIAS))
        out += [tab] + linhas(aconf, False) + ["</table>"]
    out.append("</div>")
    return "\n".join(out)


def criterio_compacto(j, hoje, novos, alterados, selo_mudou):
    """Funcao c -> None | 'sem_mudanca' | 'dormente' (decisao 4). Novo, alterado, selo mudado hoje,
    selo de prazo vivo e prazo em destaque (prazo_em_destaque: confirmado em 30 dias, ou inscricao/prova a
    confirmar em 14 — a regra do radar) nunca compactam."""
    anterior = _data((j.get("execucao_anterior") or "")[:10])
    primeira = bool(j.get("primeira_semana"))

    def f(c):
        if c["id"] in novos or c["id"] in alterados or c["id"] in selo_mudou or c.get("selo") in NUNCA_COMPACTAR:
            return None
        if any(prazo_em_destaque(p, hoje) for p in c.get("prazos") or []):
            return None
        mud = _data(c.get("mudou_em"))
        if mud is None:
            return None
        if c.get("selo") in SELOS_DORMENCIA and feriados.dias_uteis_entre(mud, hoje) > DORMENCIA_DIAS_UTEIS:
            return "dormente"
        if not primeira and anterior and mud < anterior:
            return "sem_mudanca"
        return None
    return f


def sec_concursos(regs, hoje, novos, alterados, compacto=None, divergentes=(), removidos=()):
    def do_bloco(b):
        return sorted((c for c in regs if c.get("bloco") == b),
                      key=lambda c: (c["id"] not in novos,
                                     ORDEM_SELO.index(c.get("selo")) if c.get("selo") in ORDEM_SELO else 99))

    def saiu(b):
        return [r for r in removidos or () if r.get("bloco") == b]
    carreira = [radar(regs, hoje, divergentes), TABELA_CONCURSOS]
    for n, b in enumerate(BLOCOS):
        carreira += bloco_concursos(b, do_bloco(b), hoje, novos, alterados, n == 0, compacto, saiu(b))
    carreira.append("</table>")
    apoio_html = [TABELA_CONCURSOS] + bloco_concursos(
        "Analista e técnico (TJ, TRF, TRT, MP, Defensoria)", do_bloco(APOIO), hoje, novos, alterados, True,
        compacto, saiu(APOIO)) + ["</table>"]
    return (secao("💼 Concursos jurídicos — Carreira jurídica", "\n".join(x for x in carreira if x)) + "\n" +
            secao("🗂️ Concursos jurídicos — Quadro de apoio", "\n".join(apoio_html)))


def sec_midia(midia, opiniao, ex, ev):
    usados = {it.get("ref") for it in ex["items"] if it.get("ref")} | set(ex.get("_refs_descartadas") or ())
    sobra = {"conjur": 0, "migalhas": 0}
    for e in ev.values():
        if e.get("_fonte") in sobra and e.get("situacao") in ("NOVA", "HERDADA") and e["id"] not in usados:
            sobra[e["_fonte"]] += 1
    partes = [item_padrao(it) for it in midia] or [apoio(ex["email"].get("apoio", {}).get("Mídia")
                                                         or "Nenhuma matéria selecionada nesta janela.")]
    mais = [link(u, "%s (%d)" % (n, sobra[k])) for k, n, u in (
        ("conjur", "ConJur", "https://conjur.com.br/noticias/"),
        ("migalhas", "Migalhas", "https://www.migalhas.com.br/quentes")) if sobra[k]]
    if mais:
        partes.append('<p style="margin:0;font-size:12px;color:%s">Ver mais, entre as outras matérias da janela: '
                      '%s.</p>' % (APOIO_COR, " · ".join(mais)))
    if opiniao:
        partes.append('<p style="margin:14px 0 6px;font-size:12px;font-weight:bold;color:%s">Opinião/Análise</p>' % NAVY)
        for it in opiniao:
            quem = " — ".join(x for x in (esc(it.get("autor") or ""),) if x)
            onde = ", ".join(x for x in (esc(it.get("fonte") or ""), br_data(it.get("data"))) if x)
            partes.append('<p style="margin:0 0 6px;font-size:12px;line-height:18px">%s %s%s (%s%s).</p>' % (
                selo("OPINIÃO/ANÁLISE", True),
                link(it.get("url"), esc(it["titulo"])) if it.get("url") else "“%s”" % esc(it["titulo"]),
                (" — " + quem) if quem else "", onde, "" if it.get("url") else "; sem link"))
    return secao("📰 Se saiu na mídia não é fofoca!", "\n".join(partes))


def caixa(fundo, corpo):
    return '<div style="background:%s;padding:14px 16px">%s</div>' % (fundo, corpo)


def sec_versiculo(v, reflexao):
    if not v or not v.get("ok"):
        return secao("🙏 Porque sem Deus, nada é possível", apoio(
            "Versículo do dia não recuperado nesta execução (fontes indisponíveis); a seção volta na próxima edição."))
    corpo = ('%s<p style="margin:8px 0 6px;font-size:14px;line-height:21px;color:#3d3113;font-style:italic">“%s”</p>'
             '<p style="margin:0 0 10px;font-size:12px;color:#8a6d1d;font-weight:bold">%s (%s) — %s, confirmado '
             'para %s</p><p style="margin:0;font-size:12px;line-height:18px;color:%s">%s</p>' % (
                 selo("VERSÍCULO DO DIA"), esc(v["texto"]), esc(v["referencia"]), esc(v.get("versao") or ""),
                 '<a href="%s" style="color:#8a6d1d">%s</a>' % (attr(v.get("url")), esc(v["fonte"])),
                 br_data(v.get("data_pagina"), True), APOIO_COR, esc(reflexao)))
    return secao("🙏 Porque sem Deus, nada é possível", caixa("#fdf6e9", corpo))


def sec_munger(m):
    """K1: 'licao' (sintese propria, 187 de 200 itens do banco) sai sem aspas e assinada como licao
    inspirada; 'aforismo' mantem as aspas. Mesma caixa, mesma cor."""
    obs = (" · " + esc(m["obs"])) if m.get("obs") else ""
    if m.get("tipo") == "licao":
        texto, assinatura = esc(ponto(m["texto"])), "— lição inspirada em Charlie Munger"
    else:
        texto, assinatura = "“%s”" % esc(m["texto"]), "— Charlie Munger"
    corpo = ('%s<p style="margin:8px 0 6px;font-size:14px;line-height:21px;color:%s;font-style:italic">%s</p>'
             '<p style="margin:0;font-size:12px;color:%s">%s · <i>%s</i>%s</p>' % (
                 selo("SABEDORIA DO DIA"), TEXTO, texto, APOIO_COR, assinatura, esc(m["fonte"]), obs))
    return secao("💡 Conhecimento nunca é demais", caixa("#f4f6fa", corpo))


def fontes_consultadas(ss, ex, v):
    def lista(ids):
        usados, out = set(), []
        for i in ids:
            st = ss.get(i)
            if st in (None, "nao_tentada"):
                continue
            rot = rotulo_fonte(i, ex) if st == "falha" else ROTULO_FONTE[i]
            if i.startswith("congresso_"):
                rot = "Congresso Nacional (últimas leis e MPVs)"
            if rot in usados:
                continue
            usados.add(rot)
            out.append(rot + {"falha": " — falhou", "vazio": " — sem e-mail na janela"}.get(st, ""))
        return out
    of = lista(OFICIAIS)
    if "informativos_docs" not in ss and any(it.get("destaques_texto") for it in ex["items"]):
        of.append(ROTULO_FONTE["informativos_docs"])
    if ex["email"].get("fontes_extra"):
        of.append(esc(ex["email"]["fontes_extra"]))
    sec = lista(SECUNDARIAS) + ["portais e blogs de concursos (prazos e editais, sempre sujeitos a confirmação oficial)"]
    sub = '<div style="font-size:14px;font-weight:bold;color:%s;margin:%s 0 6px">%s</div>'
    est = '<div style="font-size:12px;line-height:19px;color:#3d4b59">%s</div>'
    return (sub % (NAVY, px(0), "Fontes oficiais consultadas") + est % (" · ".join(of) or "nenhuma respondeu") +
            sub % (NAVY, px(14), "Fontes secundárias consultadas") + est % " · ".join(sec))


def _tokens(texto):
    import repeticao
    return set(repeticao.tokens(texto)) - GENERICOS


def ja_em_limitacoes(obs, limitacoes):
    """G8: a observacao repete uma frase das Limitacoes (mesmo assunto, 3+ termos e 40% em comum)?"""
    if not limitacoes:
        return False
    t = _tokens(obs)
    for frase in re.split(r"(?<=[.;])\s+", limitacoes):
        f = _tokens(frase)
        comum = len(t & f)
        if comum >= 3 and comum / max(1, min(len(t), len(f))) >= 0.4:
            return True
    return False


# Decisao 5 (do dono): pendencia interna/operacional nao vai ao leitor. Vocabulario estreito de operacao da rotina
# ("manter 1 sonda por dia", 10 a 20/11); "execução", "protocolo" e "rodízio" soltos sao vocabulario juridico e nao
# contam. Mais o detalhe tecnico do G8 (TECNICO: codigo http, nome de script, id com "_").
OPERACIONAL = re.compile(r"\b(?:sondas?|protocolo\s+completo|coletor(?:es)?|ledger|scripts?|CDN|firewall)\b", re.I)


def pendencia_operacional(texto):
    return bool(OPERACIONAL.search(str(texto or "")) or tecnico_para_leitor(texto))


def pendencia_no_quadro(p, quadro):
    """Pendencia sem concurso (nem errata, nem 'cronica') vai ao quadro do leitor so (verified[3]): com faixa 'ativa',
    ou com o texto mudado hoje (inclusive a criada hoje), ou na 1a execucao da semana — longo_prazo nao se repete
    igual todo dia —; e nunca quando repete item, limitacao ou observacao da edicao (ja_em_limitacoes: o Caso Master
    saia na Fofoquinha e de novo aqui) nem quando e texto operacional (decisao 5)."""
    texto = str(p.get("texto") or "")
    if not texto.strip() or pendencia_operacional(texto):
        return False
    antes = (quadro.get("antes") or {}).get(p["id"]) or {}
    mudou = p.get("_nova") or p.get("_migracao") or texto.strip() != str(antes.get("texto") or "").strip()
    if not (p.get("faixa") == "ativa" or mudou or quadro.get("primeira")):
        return False
    return not any(ja_em_limitacoes(texto, t) for t in quadro.get("textos") or ())


def rotulo_pendencia(texto):
    """'PUSH Planalto: resenha de …' -> 'PUSH Planalto' (o trecho antes do 1o ':'; sem ele, o 1o trecho ate ';' ou
    '.', ate 80 caracteres). Nunca o id."""
    t = re.sub(r"\s+", " ", str(texto or "")).strip()
    m = re.match(r"^([^:;]{2,80}?):\s", t)
    if m:
        return m.group(1).strip()
    t = re.split(r"[;.]\s", t)[0].strip()
    return t if len(t) <= 80 else t[:79].rsplit(" ", 1)[0] + "…"


def sec_pendencias(pend, regs, ex, ss, quadro=None):
    """quadro (montar): {"antes": {id: pendencia do ledger}, "primeira": 1a execucao da semana, "textos": [texto dos
    itens, limitacoes e observacoes da edicao], "removidas": [(rotulo, desfecho)]}. Sem ele, o quadro antigo (toda
    pendencia sem concurso, errata nem faixa 'cronica')."""
    # errata: a de hoje vem em email.errata; a herdada do ledger (errata_*) sai uma vez e e removida
    errata = [p for p in pend if p["id"].startswith("errata_") and not p.get("_nova")]
    if ex["email"].get("errata"):
        errata.insert(0, {"id": "errata_hoje", "texto": ex["email"]["errata"]})
    lim = ex["email"].get("limitacoes") or ""
    linhas = [esc(o) for o in ex["email"].get("observacoes") or [] if not ja_em_limitacoes(o, lim)]
    falhas = [rotulo_fonte(i, ex) for i, st in ss.items() if st == "falha"]
    if falhas and not linhas and not lim:
        linhas.append("Falha técnica nesta execução: " + "; ".join(falhas) + ".")
    ids_conc = {c.get("pendencia") for c in regs if c.get("pendencia")}
    adiadas = 0
    for p in pend:
        if p["id"].startswith("errata_") or p["id"] in ids_conc or p.get("faixa") == "cronica":
            continue
        if quadro is not None and not pendencia_no_quadro(p, quadro):
            adiadas += not pendencia_operacional(p.get("texto"))
            continue
        linhas.append(esc(ponto(p.get("texto"))))
    for rot, desfecho in (quadro or {}).get("removidas") or ():
        linhas.append("Saiu do acompanhamento: %s — %s" % (esc(rot), esc(ponto(desfecho))))
    vazio = "Sem pendências novas nesta execução." if adiadas else "Sem pendências registradas nesta execução."
    out = ['<div style="font-size:14px;font-weight:bold;color:%s;margin:14px 0 6px">📋 Observações de verificação, '
           'lacunas e pendências</div>' % NAVY]
    for p in errata:
        out.append('<div style="background:#fdf0f0;border:1px solid #f0c2c2;color:#5c1a1a;padding:10px 12px;'
                   'margin-bottom:8px;font-size:12px;line-height:19px"><b>Errata:</b> %s</div>'
                   % esc(re.sub(r"^Errata[^:]*:\s*", "", p.get("texto") or "")))
    out.append('<div style="background:#fdf6e9;border:1px solid #e6d3a3;padding:10px 12px;font-size:12px;'
               'line-height:19px;color:#3d4b59">%s</div>'
               % ("<br>".join("• " + l for l in linhas) or vazio))
    return "\n".join(out)


# G8: detalhe tecnico que nao e para o leitor (codigo http/erro, nome de script, id interno com "_").
# Nao e apagado do texto (apagar embaralhava a frase: "scripts coleta_web, informativos e x" virava
# "scripts,, e x"): o montador avisa (tecnico_para_leitor) e o orquestrador reescreve.
TECNICO = re.compile(r"\b(?:https?|erro|status|c[óo]digo)\s*[=:]?\s*[1-5]\d\d\b|\(\s*[45]\d\d\s*\)|"
                     r"\b[\w-]+\.(?:py|sh)\b|\b[a-z]+(?:_[a-z0-9]+)+\b", re.I)


def tecnico_para_leitor(texto):
    """Trechos tecnicos (TECNICO) do texto, sem repeticao, na ordem; [] = linguagem simples."""
    out = []
    for m in TECNICO.finditer(str(texto or "")):
        if m.group(0) not in out:
            out.append(m.group(0))
    return out


def fontes_que_falharam(ss, ex=None):
    """Rotulos (rotulo_fonte) das fontes com 'falha' no source_status, na ordem do rodape, sem repeticao."""
    falhas = []
    for i in OFICIAIS + SECUNDARIAS:
        if ss.get(i) == "falha":
            rot = rotulo_fonte(i, ex)
            if rot not in falhas:
                falhas.append(rot)
    return falhas


# E-min (f), ensaio de 23/11: o rodape sai do source_status ("Nenhuma fonte falhou nesta execução") e as limitacoes e
# observacoes sao texto livre do orquestrador; quando o texto diz que uma fonte falhou e nenhum status e 'falha', o
# leitor ve as duas coisas. Vocabulario de falha de acesso; "sem falha"/"nenhuma falha" nao contam.
FALHA_NO_TEXTO = re.compile(r"\b(?:falh(?:ou|aram|as?)|fora\s+do\s+ar|indispon[íi]ve(?:l|is)|inacess[íi]ve(?:l|is)|"
                            r"n[ãa]o\s+(?:respondeu|responderam|abriu|abriram|carregou|carregaram)|recusou|recusaram|"
                            r"bloquead[oa]s?|sem\s+resposta)\b", re.I)
NEGA_FALHA = re.compile(r"\b(?:sem|nenhuma?)\s+(?:\w+\s+){0,2}falh", re.I)


def falha_no_texto(texto):
    """A 1a frase do texto que fala de falha de fonte (FALHA_NO_TEXTO, sem negacao); '' se nenhuma."""
    for frase in re.split(r"(?<=[.;])\s+", str(texto or "")):
        if FALHA_NO_TEXTO.search(frase) and not NEGA_FALHA.search(frase):
            return frase.strip()
    return ""


def suporte_txt(ss, em=None, ex=None):
    """G8: rodape para o leitor — o que foi usado e, em linguagem simples, que fonte falhou (sem codigo http
    nem nome de script; o detalhe tecnico fica em errors/verification_notes no historico). Sempre o texto
    calculado: o email.suporte escrito a mao e ignorado (AVISO em preparar), porque a limpeza automatica
    embaralhava a frase e deixava codigo e nome de script. ex: para o rotulo por produto (rotulo_fonte)."""
    falhas = fontes_que_falharam(ss, ex)
    base = ("Leitura automática dos e-mails oficiais (Push STF, PUSH Planalto, CodJu, Câmara) e do JOTA, das páginas "
            "do Congresso, do ConJur e do Migalhas, dos documentos oficiais dos informativos e das páginas das bancas "
            "de concurso; e-mail montado automaticamente")
    return base + (". Fontes que falharam nesta execução: " + "; ".join(falhas) if falhas
                   else ". Nenhuma fonte falhou nesta execução")


def nome_feriado(nome):
    """'Recesso da Justiça Federal (20/12 a 06/01)' -> 'Recesso da Justiça Federal, 20/12 a 06/01': o nome entra
    entre parenteses na frase da janela, e parenteses aninhados ficam ilegiveis."""
    s = str(nome or "")
    for _ in range(3):
        s = re.sub(r"\s*\(\s*([^()]*?)\s*\)", r", \1", s)
    return re.sub(r"\s*,\s*(,\s*)+", ", ", s).strip(" ,")


def janela_txt(j, limitacoes):
    ini, fim = datetime.fromisoformat(j["inicio"]), datetime.fromisoformat(j["fim"])
    dias = (fim.date() - ini.date()).days
    rot = "ontem" if dias == 1 else ("hoje" if dias == 0 else DIAS[ini.weekday()])
    hm = lambda d: "%dh%02d" % (d.hour, d.minute)
    fds = any((ini.date().toordinal() + n) % 7 in (5, 6) for n in range(1, dias))   # sabado/domingo no meio
    # feriado em dia util dentro da janela (antes de hoje): o silencio das fontes oficiais e esperado
    fer = [f for f in j.get("feriados_na_janela") or [] if isinstance(f, dict) and f.get("data")
           and f.get("data") < j["data"] and (_data(f["data"]) or date.min).weekday() < 5
           and f.get("tipo") == "nacional"]
    cobre = []
    if fds:
        cobre.append("o fim de semana")
    if fer:
        cobre.append("o feriado de " + " e ".join("%s (%s)" % (br_data(f["data"]), nome_feriado(f.get("nome")))
                                                  for f in fer))
    t = "Janela de cobertura: das %s de %s (%s) às %s de hoje (%s)%s, fuso América/São Paulo." % (
        hm(ini), rot, ini.strftime("%d/%m"), hm(fim), fim.strftime("%d/%m/%Y"),
        (", cobrindo " + " e ".join(cobre)) if cobre else "")
    fh = j.get("feriado_hoje")
    if isinstance(fh, dict) and fh.get("nome"):
        qual = {"nacional": "feriado nacional", "justica_federal": "feriado na Justiça Federal",
                "ponto_facultativo": "ponto facultativo"}.get(fh.get("tipo"), "feriado")
        t += " Hoje é %s (%s)." % (qual, nome_feriado(fh["nome"]))
    if limitacoes:
        t += " Limitações: " + ponto(limitacoes)
    return t


# ------------------------------------------------------------------ 4. montagem
def quadro_pendencias(led, upd_pend, regs, ex, j, mig=None):
    """Contexto do quadro de pendencias (sec_pendencias): o ledger de antes (texto mudou hoje?), a 1a execucao da
    semana, o texto da edicao (itens de noticia, limitacoes, observacoes: pendencia que o repete nao sai) e as
    pendencias removidas hoje que o leitor via — sem concurso ligado, sem errata, fora da 'cronica' e sem texto
    operacional —, ditas uma vez com o desfecho ("Saiu do acompanhamento"). mig (migracoes_do_dia): as removidas
    pela migracao de hoje, com o texto/faixa/vinculo de antes guardados no resumo (o ledger ja chega sem elas)."""
    antes = {p.get("id"): p for p in led.get("pendencias_vivas") or []}
    em = ex.get("email") or {}
    textos = ["%s. %s" % (it.get("titulo") or "", it.get("resumo") or "") for it in ex.get("items") or []
              if it.get("categoria") in CATEGORIAS_NOTICIA]
    textos += [em.get("limitacoes") or ""] + [str(o) for o in em.get("observacoes") or []]
    ligadas = {c.get("pendencia") for c in list(regs or []) + list(led.get("concursos") or []) if c.get("pendencia")}
    removidas = []
    for ident, campos in (upd_pend or {}).items():
        p = antes.get(ident)
        if not (isinstance(campos, dict) and campos.get("remover") and p) or ident.startswith("errata_") \
                or ident in ligadas or p.get("faixa") == "cronica" or pendencia_operacional(p.get("texto")):
            continue
        if str(campos.get("desfecho") or "").strip():
            removidas.append((rotulo_pendencia(p.get("texto")), str(campos["desfecho"]).strip()))
    vivas = antes.keys() | set(upd_pend or ())
    for ident, m in ((mig or {}).get("pendencias") or {}).items():
        if not removido_na_migracao(m) or ident in vivas or ident.startswith("errata_") or m.get("concurso") \
                or ident in ligadas or m.get("faixa") == "cronica" or pendencia_operacional(m.get("texto")):
            continue
        if str(m.get("removido") or "").strip():
            removidas.append((rotulo_pendencia(m.get("texto")), str(m["removido"]).strip()))
    return {"antes": antes, "primeira": bool(j.get("primeira_semana")), "textos": [t for t in textos if t.strip()],
            "removidas": removidas}


def montar(ex, j, led, ev, v, agora, ctx=None):
    """Devolve (corpo, secoes [(nome, html)], regs, novos, alterados, pend)."""
    hoje = date.fromisoformat(j["data"])
    em = ex["email"]
    ss = ex.get("source_status") or {}
    upd = ex.get("ledger_updates") or {}
    if ctx is None:
        ctx = estado_concursos(ex, j, led, {"historico": os.path.join(AQUI, "resumo-legislativo-historico.json")}, [])
    regs, novos, alterados = ctx["regs"], ctx["novos"], ctx["alterados"]
    # a remocao automatica da errata herdada (agendada em preparar) vale para o ledger, nao para esta
    # edicao: sem esta excecao a errata era retirada antes de ser renderizada e nunca saia
    upd_pend = {k: c for k, c in (upd.get("pendencias") or {}).items()
                if not (k.startswith("errata_") and c.get("remover")
                        and str(c.get("desfecho", "")).startswith("Errata publicada na edição de"))}
    pend = aplicar_pendencias(led.get("pendencias_vivas") or [], upd_pend)
    mig = ctx.get("migracoes") or {}
    for p in pend:
        if (mig.get("pendencias") or {}).get(p["id"]) == "alterado":
            p["_migracao"] = True            # criada ou reescrita pela migracao de hoje: texto novo para o leitor
    por_cat = {}
    for it in ex["items"]:
        por_cat.setdefault(it["categoria"], []).append(it)
    quadro = quadro_pendencias(led, upd_pend, regs, ex, j, mig)

    pre = ('<div style="display:none;font-size:1px;color:#eef1f4;line-height:1px;max-height:0;max-width:0;opacity:0;'
           'overflow:hidden">%s%s</div>' % (esc(em["preheader"]), "&#847;&zwnj;&nbsp;" * 12))
    edicao = (j.get("cabecalho_extra") or "Edição extra") if j.get("edicao_extra") else "Edição das 7h"
    cab = ('<tr><td bgcolor="%s" align="center" style="padding:26px 20px;%s">'
           '<div style="font-size:34px;line-height:38px;margin-bottom:6px">🤖📜</div>'
           '<div style="font-size:22px;line-height:28px;color:%s;font-weight:bold">Robozinho dos Momozis até Passar</div>'
           '<div style="font-size:13px;line-height:19px;color:%s;font-weight:bold;margin-top:8px">Legislação, '
           'jurisprudência e concursos jurídicos sem drama. Ou quase.</div>'
           '<div style="font-size:12px;line-height:17px;color:#a9b7cc;margin-top:10px">%s · %s (%s) · '
           'América/São Paulo</div></td></tr>' % (NAVY, FONTE, BRANCO, OURO, esc(edicao), j["hoje_br"],
                                                  j["dia_semana"]))
    indice = ('<tr><td bgcolor="#f4f6fa" style="padding:14px 20px;%s;font-size:12px;line-height:20px;color:%s">'
              '<b>Nesta edição:</b> %s</td></tr>' % (FONTE, NAVY, INDICE))
    cards = "\n".join(
        '<div style="background:#f4f6fa;border-left:4px solid %s;padding:10px 12px;margin-bottom:8px">'
        '<b>%s %s:</b> %s</div>' % (NAVY, esc(c[0]), esc(c[1].rstrip(":")), esc(ponto(c[2]))) for c in em["resumo"])
    resumo = secao("Resumo executivo", cards, 20)
    janela = ('<tr><td style="padding:10px 20px 0;%s;font-size:12px;line-height:18px;color:%s"><i>%s</i></td></tr>'
              % (FONTE, APOIO_COR, esc(janela_txt(j, em.get("limitacoes")))))
    divisor = ('<tr><td style="padding:16px 20px 0"><div style="border-top:1px solid #e4e9ef;font-size:1px;'
               'line-height:1px">&nbsp;</div></td></tr>')

    apoio_em = em.setdefault("apoio", {})
    secoes = [("Cabeçalho e resumo", "\n".join([cab, indice, resumo, janela, divisor])),
              ("Planalto/Legislação", sec_planalto(por_cat.get("Planalto/Legislação", []), ss, ex))]
    for cat, titulo, vazio in SECOES[1:]:
        if not por_cat.get(cat) and not apoio_em.get(cat):
            vazio = apoio_calculado(cat, por_cat) or vazio
        if cat == "Informativos":
            secoes.append((cat, sec_informativos(titulo, vazio, por_cat.get(cat, []), ex)))
        else:
            secoes.append((cat, sec_itens(cat, titulo, vazio, por_cat.get(cat, []), ex)))
    compacto = criterio_compacto(j, hoje, novos, alterados, ctx.get("selo_mudou") or set())
    secoes.append(("Concursos", sec_concursos(regs, hoje, novos, alterados, compacto,
                                              com_divergencia(regs, pend, ctx.get("banca"))
                                              | set(ctx.get("pendentes") or ()), ctx.get("removidos") or ())))
    secoes.append(("Mídia e Opinião", sec_midia(por_cat.get("Mídia", []), por_cat.get("Opinião/Análise", []), ex, ev)))
    secoes.append(("Fofoquinha", sec_itens("Fofoquinha", "🤫 FOFOQUINHA JURÍDICA",
                                           "Nenhuma fofoquinha jurídica relevante localizada nesta execução.",
                                           por_cat.get("Fofoquinha", []), ex)))
    secoes.append(("Versículo", sec_versiculo(v, em.get("reflexao") or "")))
    secoes.append(("Munger", sec_munger(j["munger"])))
    secoes.append(("Fontes e pendências", '<tr><td style="padding:22px 20px 0;%s">%s\n%s</td></tr>' % (
        FONTE, fontes_consultadas(ss, ex, v), sec_pendencias(pend, regs, ex, ss, quadro))))
    rodape = ('<tr><td style="padding:22px 0 0"><div style="background:%s;padding:20px;%s;text-align:center">'
              '<div style="font-size:13px;color:%s;font-weight:bold">🤖 Robozinho dos Momozis até Passar</div>'
              '<div style="font-size:11px;color:#a9b7cc;margin-top:6px;line-height:16px">Newsletter jurídica '
              'automatizada · conteúdo informativo, não substitui a consulta às fontes oficiais nem assessoria '
              'jurídica.<br>Próxima edição: %s, às 7h.</div></div></td></tr>' % (NAVY, FONTE, BRANCO, j["rodape"]))
    sup = ('<tr><td style="padding:16px 20px 22px;%s"><div style="font-size:13px;font-weight:bold;color:%s;'
           'margin-bottom:6px">Suporte usado na execução</div><div style="font-size:11px;line-height:17px;color:%s">'
           '%s</div><div style="font-size:10px;line-height:15px;color:#8b95a1;margin-top:8px">Gerado em %s '
           '(América/São Paulo) · execução %s</div></td></tr>' % (
               FONTE, NAVY, APOIO_COR, esc(ponto(suporte_txt(ss, em, ex))), agora.strftime("%d/%m/%Y %H:%M"),
               j["execution_id"]))
    secoes.append(("Rodapé", rodape + "\n" + sup))
    # sentinela oculta no fim do corpo: conferencia barata de completude da copia (decisao 2)
    sentinela = '<span style="display:none">fim-%s</span>' % esc(j["execution_id"])
    corpo = (pre + '\n<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" '
             'bgcolor="#eef1f4" style="border-collapse:collapse"><tr><td align="center" style="padding:20px 8px">\n'
             '<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" bgcolor="#ffffff" '
             'style="width:100%;max-width:600px;border-collapse:collapse">\n' + "\n".join(h for _, h in secoes) +
             "\n</table>\n" + sentinela + "\n</td></tr></table>")
    return corpo, secoes, regs, novos, alterados, pend


# ------------------------------------------------------------------ 5. preparo e validacao
def descartar_repetidos(itens, execucoes, ignorar_ids):
    """Decisao 8: nas secoes de apoio, REPUBLICADA (chave exata ja publicada) e POSSIVEL_REPETIDA da
    MESMA fonte saem sozinhas. Devolve (ficam, [(item, motivo)]). "desdobramento": true mantem o item
    (o --validar segue avisando). O resto (outra fonte, secoes centrais) continua AVISO."""
    import repeticao
    anteriores = [e for e in execucoes if e.get("execution_id") not in ignorar_ids]
    data_de = {}
    for e in anteriores:
        for it in e.get("items") or []:
            if it.get("chave"):
                data_de[it["chave"]] = e.get("date") or ""
    idx = None
    ficam, fora = [], []
    for it in itens:
        ch = it.get("chave") or ""
        if it.get("categoria") not in SECOES_APOIO or it.get("desdobramento") or not ch or repeticao.ignorar(it):
            ficam.append(it)
            continue
        if ch in data_de:
            fora.append((it, "REPUBLICADA: a chave já saiu na edição de %s" % br_data(data_de[ch])))
            continue
        if idx is None:
            idx = repeticao.indice(anteriores)
        m = repeticao.procurar(repeticao.tokens_item(ch.lower(), it.get("titulo")), idx, excluir=ch.lower())
        if m and m.split("|")[0] == ch.lower().split("|")[0]:
            fora.append((it, "POSSIVEL_REPETIDA da mesma fonte (%s) ~ %s, publicada em %s"
                         % (m.split("|")[0], m, br_data(data_de.get(m)) or "edição anterior")))
            continue
        ficam.append(it)
    return ficam, fora


def cards_citam_descartados(em, ficam, fora, regs=()):
    """Decisao 8: card do resumo executivo ou trecho do preheader que trata de item descartado sozinho
    -> AVISO ACIONÁVEL (o e-mail sairia com um card sobre algo que nao esta em secao nenhuma). Cada trecho
    (frase do card, partes separadas por ';'; partes do preheader por ' · ') e comparado com o descartado e
    com o que ficou (itens, destaques dos informativos, linhas dos concursos): se um que ficou explica o
    trecho tao bem quanto o descartado, nada a pedir."""
    if not fora:
        return []
    import repeticao

    def tk(txt):
        return set(repeticao.tokens(re.sub(r"<[^>]+>", " ", str(txt or "")))) - GENERICOS

    def nota(t, tf):                     # numero distintivo (ato, processo; ano nao conta) vale como forte
        num = {x for x in t & tf if x.isdigit() and len(x) >= 3}
        return len(t & tf) + (5 if num else 0), bool(num)

    ficou = [tk(" ".join(str(it.get(k) or "") for k in ("titulo", "resumo", "destaques_texto", "nota")))
             for it in ficam]
    ficou += [tk(c.get("linha")) for c in regs or ()]
    descart = [(it, motivo, tk("%s %s" % (it.get("titulo") or "", it.get("resumo") or ""))) for it, motivo in fora]
    trechos = []
    for c in em.get("resumo") or []:
        if isinstance(c, list) and len(c) == 3:
            trechos += [("card do resumo «%s»" % limpo(str(c[1]))[:30], p) for p in re.split(r";|\s·\s", str(c[2]))]
    trechos += [("preheader", p) for p in str(em.get("preheader") or "").split(" · ")]
    achados = {}
    for onde, txt in trechos:
        t = tk(txt)
        if not t:
            continue
        melhor = None
        for i, (_, _, tf) in enumerate(descart):
            pontos, forte = nota(t, tf)
            comum = len(t & tf)
            if (forte or (comum >= 3 and comum / len(t) >= 0.5)) and (not melhor or pontos > melhor[0]):
                melhor = (pontos, i)
        if not melhor or any(nota(t, tf)[0] >= melhor[0] for tf in ficou):
            continue
        achados.setdefault(melhor[1], [])
        if onde not in achados[melhor[1]]:
            achados[melhor[1]].append(onde)
    out = []
    for i in sorted(achados):
        it, motivo, _ = descart[i]
        ondes = achados[i]
        out.append("%s %s item descartado («%s», %s): troque o card/o trecho ou marque \"desdobramento\": true "
                   "no item" % (" e ".join(ondes), "citam" if len(ondes) > 1 else "cita",
                                curto(it.get("titulo")), motivo.split(":")[0].split(" ")[0]))
    return out


def relacionados_informativos(itens, ev):
    """G3b: item de Midia que trata de tema de informativo/RG desta edicao -> AVISO 'cite o tema'
    (o resultado noticiado continua so da midia; a nota de confirmacao nao muda)."""
    import repeticao
    edicoes = [(it["ref"], ev[it["ref"]]) for it in itens
               if it.get("categoria") == "Informativos" and it.get("ref") in ev and ev[it["ref"]].get("ok")]
    if not edicoes:
        return []
    dest = []
    for ref, e in edicoes:
        for i, d in enumerate(e.get("itens") or []):
            txt = " ".join(str(d.get(k) or "") for k in ("titulo", "tese", "resumo", "destaque", "tema"))
            nums = {re.sub(r"\D", "", x) for x in re.findall(r"\b\d{1,3}(?:\.\d{3})+\b", str(d.get("processo") or ""))}
            dest.append((ref, i, e["tipo"], d, set(repeticao.tokens(txt)) - GENERICOS, nums))
    avisos = []
    for it in itens:
        if it.get("categoria") != "Mídia" and not (it.get("categoria") == "STJ Notícias" and not item_oficial(it)):
            continue
        texto = " ".join(str(it.get(k) or "") for k in ("titulo", "resumo"))
        t = set(repeticao.tokens(texto)) - GENERICOS
        nums = {re.sub(r"\D", "", x) for x in re.findall(r"\b\d{1,3}(?:\.\d{3})+\b", texto)}
        com_nota = texto + " " + str(it.get("nota") or "")
        temas = {re.sub(r"\D", "", x) for x in re.findall(r"(?i)\bTema\s+(\d[\d.]*)", com_nota)}
        citadas = {int(x) for x in re.findall(r"(?i)informativo\s+st[fj]\D{0,6}(\d{3,4})\b", com_nota)}
        melhor = None
        for ref, i, tipo, d, td, dn in dest:
            tema = re.sub(r"\D", "", str(d.get("tema") or ""))
            if (tipo == "rg" and tema and tema in temas) or (tipo != "rg" and int(ref[3:]) in citadas):
                continue                       # ja cita o tema/o informativo: nada a pedir
            comum = len(t & td)
            forte = bool(nums & dn) or (tipo == "rg" and tema and tema in nums)
            if forte or (comum >= 3 and comum / max(1, min(len(t), len(td))) >= 0.2):
                nota = (99 if forte else comum)
                if not melhor or nota > melhor[0]:
                    melhor = (nota, ref, i, tipo, d)
        if melhor:
            _, ref, i, tipo, d = melhor
            if tipo == "rg":
                rot = rotulo_rg(d) or "estágio não informado"
                desc = "Tema %s, %s" % (d.get("tema"), rot[:1].lower() + rot[1:])
                pede = "cite o tema; o resultado segue só na mídia"
            else:
                desc = curto(limpo(d.get("titulo") or d.get("tema") or ""), 70)
                pede = "cite o informativo; a nota de confirmação não muda"
            avisos.append("Mídia «%s» relacionado a %s[%d] (%s): %s" % (
                curto(it.get("titulo")), ref, i, desc, pede))
    return avisos


def legislacao_so_rotina(em, itens):
    """G7: card/preheader de Legislacao que so cita (pelo numero) ato de rotina -> AVISO informativo."""
    plan = [it for it in itens if it.get("categoria") == "Planalto/Legislação"]
    num = lambda it: (ATO.match(it.get("titulo") or "") or [None, None, ""])[2].replace(".", "")
    rotina = {num(it) for it in plan if it.get("_rotina")} - {""}
    outros = [it for it in plan if not it.get("_rotina")]
    if not rotina:
        return []
    out = []
    textos = [("card de Legislação", c[2]) for c in em.get("resumo") or []
              if isinstance(c, list) and len(c) == 3 and re.search(r"(?i)legisla|planalto", str(c[1]))]
    textos += [("preheader", p) for p in str(em.get("preheader") or "").split(" · ")
               if re.search(r"\b(Lei|Decreto|MP|MPV|Medida)\b", p)]
    onde_rotina, citados_todos = [], set()
    for onde, txt in textos:
        citados = {re.sub(r"\D", "", x) for x in re.findall(r"\b\d{1,2}\.?\d{3}\b", str(txt))
                   if not re.fullmatch(r"(?:19|20)\d\d", x)}       # ano solto nao e numero de ato
        if citados and citados <= rotina:
            onde_rotina.append(onde)
            citados_todos |= citados
    if onde_rotina:
        alt = ", ".join(it["titulo"].split(",")[0] for it in outros[:2])
        out.append("%s %s só ato de rotina (%s)%s" % (
            " e ".join(onde_rotina), "citam" if len(onde_rotina) > 1 else "cita", ", ".join(sorted(citados_todos)),
            ("; prefira " + alt) if alt else "; sem ato fora da rotina hoje, a vaga pode ir para concursos ou teses"))
    return out


def agrupar_avisos(avisos):
    """Mesma mensagem do helper para varias fontes vira uma linha so (stdout < 3 KB)."""
    out, grupos = [], {}
    for a in avisos:
        m = re.match(r"ledger_updates\.fontes\.(\S+?)\.nota: (.*)$", a)
        if m:
            if m.group(2) not in grupos:
                grupos[m.group(2)] = []
                out.append(("grupo", m.group(2)))
            grupos[m.group(2)].append(m.group(1))
        else:
            out.append(("linha", a))
    return [("ledger_updates.fontes.{%s}.nota: %s" % (", ".join(grupos[x]), x) if len(grupos[x]) > 1 else
             "ledger_updates.fontes.%s.nota: %s" % (grupos[x][0], x)) if tipo == "grupo" else x for tipo, x in out]


def mesclar_status(ex, j, caminho, v, avisos):
    """source_status do orquestrador + o dos scripts ($ROBOZINHO_TMP/fontes_status.json desta execucao,
    e o source_status do versiculo.json): o do script vale, como no helper. YouVersion barrado pelo
    anti-bot e a falha esperada da sonda das segundas: nao_tentada, nunca falha (decisao 14)."""
    ss = ex.setdefault("source_status", {})
    try:
        import aguardar_coleta
        st = aguardar_coleta.ler_fontes_status(caminho, j.get("execution_id"))
    except Exception:  # noqa: BLE001 — acessorio
        st = {}
    # status_script: o que o script gravou, antes da decisao do montador sobre informativos_docs (status_informativos)
    script = {k: (x or {}).get("status_script") or (x or {}).get("status") for k, x in st.items()}
    for k, s in ((v or {}).get("source_status") or {}).items():
        script.setdefault(k, s)
    trocas = []
    for fid, s in sorted(script.items()):
        if s not in STATUS_FONTE:
            continue
        if ss.get(fid) not in (None, s):
            trocas.append("%s %s→%s" % (fid, ss[fid], s))
        ss[fid] = s
    if ss.get("youversion") == "falha" and (v or {}).get("ok"):
        t = next((x for x in (v.get("tentativas") or []) if x.get("fonte") == "YouVersion"), {})
        if t.get("esperado") or t.get("http") in (403, 429, 503) or re.search(r"anti-bot|challenge|vazia",
                                                                              str(t.get("motivo") or ""), re.I):
            trocas.append("youversion falha→nao_tentada (anti-bot esperado)")
            ss["youversion"] = "nao_tentada"
    if trocas:
        avisos.append("source_status: vale o do script — " + "; ".join(trocas))


# source_status dos e-mails oficiais (verified[37]): sai da linha BUSCAS do coletor-gmail, que o orquestrador copia
# em execucao.json "buscas_gmail" ("a=<na janela>/<total> b=… c=… d=… e=…"), e nao do julgamento do modelo (o mesmo
# silencio saia 'ok' num dia e 'vazio' no outro). Letra -> id, na ordem das buscas do coletor-gmail.
BUSCA_GMAIL = {"a": "gmail_push_stf", "b": "gmail_push_stf_informativos", "c": "gmail_stj_codju",
               "d": "gmail_push_planalto", "e": "gmail_camara"}
# cadencia semanal ou intermitente: nenhum e-mail na janela e o normal (ok)
GMAIL_SEM_CADENCIA_DIARIA = ("gmail_push_stf_informativos", "gmail_stj_codju", "gmail_camara")
RE_BUSCA_GMAIL = re.compile(r"(?<![\w=])([a-e])\s*=\s*(\d+)(?:\s*/\s*(\d+))?")


def janela_com_folga(j):
    """A janela tem fim de semana, feriado (qualquer tipo, inclusive o de hoje) ou recesso forense? Entao o silencio
    de fonte diaria e normal."""
    if j.get("recesso") or j.get("feriados_na_janela") or j.get("feriado_hoje"):
        return True
    try:
        d, fim = datetime.fromisoformat(j["inicio"]).date(), datetime.fromisoformat(j["fim"]).date()
    except (KeyError, TypeError, ValueError):
        return False
    while d <= fim:
        if d.weekday() >= 5:
            return True
        d = date.fromordinal(d.toordinal() + 1)
    return False


def status_gmail(ex, j, avisos):
    """Deriva gmail_push_stf, gmail_push_stf_informativos, gmail_stj_codju, gmail_push_planalto e gmail_camara de
    ex["buscas_gmail"]: e-mail na janela -> ok; nenhum -> ok em fonte de cadencia semanal ou intermitente
    (GMAIL_SEM_CADENCIA_DIARIA) e em janela com fim de semana, feriado ou recesso; senao 'vazio'. 'falha' so o
    orquestrador escreve (coletor que falhou, §R3), e o que ele escrever em source_status prevalece. Sem buscas_gmail,
    nada muda (o escrito). Contagem sem '/<total>' (o formato antigo contava tambem as threads anteriores a janela)
    so decide quando e 0."""
    texto = ex.get("buscas_gmail")
    if not texto:
        return
    achados = {m.group(1): int(m.group(2)) for m in RE_BUSCA_GMAIL.finditer(str(texto))
               if m.group(3) is not None or m.group(2) == "0"}
    if not achados:
        avisos.append("buscas_gmail sem contagem reconhecível (a=<na janela>/<total> …): fica o source_status escrito")
        return
    ss = ex.setdefault("source_status", {})
    folga = janela_com_folga(j)
    for letra, fid in BUSCA_GMAIL.items():
        if fid in ss or letra not in achados:
            continue
        ss[fid] = "ok" if achados[letra] > 0 or fid in GMAIL_SEM_CADENCIA_DIARIA or folga else "vazio"


def status_informativos(ex, itens, caminho, j):
    """informativos_docs depois da segunda tentativa: "falha" so quando o leitor fica sem conteudo — um informativo
    citado saiu sem destaques (edicao anunciada por e-mail cujo documento nao abriu) — ou quando o informativos.py
    acusou falha de leitura (parser, produto sem historico: o status do script). A sonda de numero ainda nao
    anunciado (403 do firewall: 18 a 20/11/2026 o leitor viu "falhou" ao lado dos informativos completos) e a
    revisita que nao abriu ficam "ok". Na falha, o rotulo nomeia o produto (ex["_falha_informativos"], lido por
    rotulo_fonte). A decisao tambem vai ao fontes_status.json — o helper faz o status de script prevalecer — com
    o do script guardado em status_script, de onde a rodada seguinte do montador parte."""
    ss = ex.setdefault("source_status", {})
    try:
        import aguardar_coleta
        e = aguardar_coleta.ler_fontes_status(caminho, j.get("execution_id")).get("informativos_docs")
    except Exception:  # noqa: BLE001 — acessorio
        e = None
    base = ((e.get("status_script") or e.get("status")) if e else ss.get("informativos_docs"))
    sem = [it["titulo"] for it in itens if it.get("categoria") == "Informativos" and it.get("sem_conteudo")
           and it.get("titulo")]
    nomes = list(sem)
    if base == "falha" and e:
        nomes += [x for x in (nome_informativo(i) for i in e.get("falhas") or []) if x and x not in nomes]
    final = "falha" if (sem or base == "falha") else base
    ex.pop("_falha_informativos", None)
    if final == "falha" and nomes:
        ex["_falha_informativos"] = "%s %s" % ("documentos oficiais" if len(nomes) > 1 else "documento oficial", " e ".join(
            ("da " if n.startswith("Repercussão") else "do ") + n for n in nomes))
    if final:
        ss["informativos_docs"] = final
    if e and final and final != e.get("status"):
        try:
            import informativos
            detalhe = re.sub(r"^citada sem conteúdo: [^;]*; ", "", str(e.get("detalhe") or ""))
            if sem:
                detalhe = ("citada sem conteúdo: %s; %s" % (", ".join(sem), detalhe))[:200]
            informativos.gravar_fontes_status({"informativos_docs": dict(e, status=final, status_script=base,
                                                                         detalhe=detalhe)}, caminho)
        except Exception:  # noqa: BLE001 — o e-mail ja diz a verdade; o fontes_status e reforco
            pass


def nome_informativo(rid):
    """'stj910' -> 'Informativo STJ nº 910'; 'stj' (produto sem historico) -> 'Informativo STJ'; outro -> ''."""
    m = re.fullmatch(r"(stf|rg|stj)(\d*)", str(rid or ""))
    if not m:
        return ""
    return NOME_INF[m.group(1)] % int(m.group(2)) if m.group(2) else NOME_INF[m.group(1)].replace(" nº %d", "")


JT_TITULO = re.compile(r"(?i)^\s*jurisprud[êe]ncia em teses\b")
JT_FONTE = "Jurisprudência em Teses (STJ)"


def teses_stj(it, avisos):
    """Jurisprudência em Teses (linha STJ_TESES do coletor-gmail, e-mail do CodJu) vai em STJ Jurisprudência — a secao
    feita para ela —, nunca em Informativos nem em STJ Notícias; sem "fonte", a dela (oficial também sem URL). Item
    de mídia (fonte não oficial) fica onde está."""
    if it.get("ref") or not JT_TITULO.match(str(it.get("titulo") or "")):
        return
    if it.get("categoria") in ("Informativos", "STJ Notícias") and it.get("status") != "MÍDIA ESPECIALIZADA" \
            and (not it.get("fonte") or item_oficial(it)):
        avisos.append("%s: Jurisprudência em Teses vai em STJ Jurisprudência (era %s)" % (
            curto(it["titulo"]), it["categoria"]))
        it["categoria"] = "STJ Jurisprudência"
    if it.get("categoria") == "STJ Jurisprudência" and not it.get("fonte"):
        it["fonte"] = JT_FONTE


def rotulo_fonte(fid, ex=None):
    """Como a fonte aparece ao leitor; informativos_docs em falha nomeia o produto (status_informativos)."""
    if fid == "informativos_docs" and ex and ex.get("_falha_informativos"):
        return ex["_falha_informativos"]
    return ROTULO_FONTE.get(fid, fid)


def preparar(ex, j, led, ev, v, op=None):
    """Resolve refs, completa campos deterministicos e devolve (erros, avisos, ctx)."""
    op = dict(op or {})
    op.setdefault("historico", os.path.join(AQUI, "resumo-legislativo-historico.json"))
    erros, avisos = [], []
    em = ex.setdefault("email", {})
    hoje = j["data"]
    hj = date.fromisoformat(hoje)
    mesclar_status(ex, j, op.get("fontes_status") or tmp("fontes_status.json"), v, avisos)
    status_gmail(ex, j, avisos)
    itens = []
    descartar = segunda_tentativa(ex.get("items") or [], ev, avisos)
    for it in ex.get("items") or []:
        if it.get("ref") in descartar:
            continue
        it = resolver(dict(it), ev, erros, avisos, hj)
        if it is None:
            continue
        if it.get("categoria") in ("Versículo", "Munger", "Concursos - Carreira", "Concursos - Apoio"):
            continue                    # gerados aqui; versao escrita a mao e descartada
        teses_stj(it, avisos)           # Jurisprudência em Teses -> STJ Jurisprudência
        cat = it.get("categoria")
        if cat not in CATEGORIAS_NOTICIA:
            erros.append("%s: categoria %r fora de %s" % (curto(it.get("titulo") or it.get("ref") or "item", 50),
                                                          cat, " | ".join(CATEGORIAS_NOTICIA)))
            continue
        if not it.get("titulo"):
            erros.append("item sem titulo: %s" % json.dumps(it, ensure_ascii=False)[:120])
            continue
        rot = curto(it["titulo"])
        if "nota" in it:
            it["nota"] = limpar_nota(it["nota"])          # D10: "sem link" e automatico
            if not it["nota"]:
                del it["nota"]
        # G4.3/decisao 12: STJ Noticias aceita julgado noticiado pela midia, com o selo dela; STJ Jurisprudencia
        # continua so oficial. Sem nota por item (21/11): a linha fixa LINHA_STJ_MIDIA no topo da secao explica; a
        # nota "sem confirmação oficial…" escrita a mao sai (repetia a linha), o resto da nota fica
        if cat == "STJ Notícias" and not item_oficial(it):
            if not it.get("status") or it["status"].startswith("CONFIRMADO"):
                if it.get("status"):
                    avisos.append("%s: STJ Notícias de mídia sai como MÍDIA ESPECIALIZADA (era %s)" % (rot, it["status"]))
                it["status"] = "MÍDIA ESPECIALIZADA"
            if it.get("nota"):
                it["nota"] = "; ".join(p for p in (x.strip() for x in str(it["nota"]).split(";"))
                                       if p and not SO_SEM_CONFIRMACAO.match(p))
                if not it["nota"]:
                    del it["nota"]
        if cat == "STJ Jurisprudência" and (not item_oficial(it) or it.get("status") == "MÍDIA ESPECIALIZADA"):
            erros.append("%s: STJ Jurisprudência só aceita fonte oficial (teses do CodJu/STJ: URL *.jus.br ou, sem "
                         "URL, \"fonte\": \"STJ CodJu\"); julgado noticiado pela mídia vai em STJ Notícias, com selo "
                         "MÍDIA ESPECIALIZADA" % rot)
            continue
        if not it.get("status") and cat in SELO_PADRAO:
            it["status"] = SELO_PADRAO[cat]
        if not it.get("status"):
            erros.append("%s: falta \"status\" (selo) — obrigatório em %s" % (rot, cat))
            continue
        if not it.get("data"):
            erros.append("%s: falta \"data\" (AAAA-MM-DD da fonte)" % rot)
            continue
        if cat == "Planalto/Legislação":
            if not it.get("grupo") and it.get("resenha"):
                it["grupo"] = grupo_resenha(it["resenha"])
                if not it["grupo"]:
                    del it["grupo"]
                    avisos.append("%s: \"resenha\" sem data reconhecível (%s) — escreva \"grupo\"" % (
                        rot, curto(it["resenha"])))
            if it.get("meta"):
                it["meta"] = norm_meta(it["meta"])
            it["_rotina"] = eh_rotina(it) or bool(it.get("_pln"))
            if not it.get("impacto") and not it["_rotina"]:
                auto = impacto_auto(it.get("resumo") or "", it["titulo"])
                if auto:
                    it["impacto"] = auto
        if it.get("impacto") and len(str(it["impacto"])) > IMPACTO_MAX:
            erros.append("%s: \"impacto\" com %d caracteres (máximo %d)" % (rot, len(str(it["impacto"])), IMPACTO_MAX))
            continue
        if not it.get("chave"):
            it["chave"] = chave_auto(it)
        it.setdefault("url", "")
        it.setdefault("fonte", "")
        for campo in ("titulo", "resumo", "url", "nota", "meta", "grupo", "impacto"):
            if WRAPPER.search(str(it.get(campo) or "")):
                erros.append("%s: wrapper/rastreio em %s" % (it["chave"], campo))
        itens.append(it)
    status_informativos(ex, itens, op.get("fontes_status") or tmp("fontes_status.json"), j)
    # decisao 8: repetido certo nas secoes de apoio sai sozinho (listado como DESCARTADA)
    ignorar = {j.get("execution_id"), j.get("ignorar_execucao")} - {None, ""}
    descartadas, fora = [], []
    if any(it.get("categoria") in SECOES_APOIO for it in itens):
        itens, fora = descartar_repetidos(itens, execucoes_historico(op["historico"]), ignorar)
        for it, motivo in fora:
            descartadas.append("DESCARTADA %s — %s" % (it.get("ref") or "«%s»" % curto(it.get("titulo"), 70), motivo))
            if it.get("ref"):
                ex.setdefault("_refs_descartadas", []).append(it["ref"])
    avisos += relacionados_informativos(itens, ev)
    sem_impacto = [it["titulo"].split(",")[0] for it in itens if it["categoria"] == "Planalto/Legislação"
                   and not it.get("_rotina") and not it.get("impacto") and str(it.get("status")).startswith("CONFIRMADO")]
    if sem_impacto:
        avisos.append("Planalto sem \"impacto\" (Para a prova): %s — escreva \"impacto\" (até %d caracteres) quando "
                      "a ementa não bastar" % ("; ".join(sem_impacto), IMPACTO_MAX))
    avisos += legislacao_so_rotina(em, itens)
    # concursos: registro do dia (com carimbo da banca e selo por data); os que mudaram hoje vao ao historico
    ctx = estado_concursos(ex, j, led, op, avisos)
    regs, novos, alterados = ctx["regs"], ctx["novos"], ctx["alterados"]
    avisos += marcas_da_migracao(ctx)
    avisos += cards_citam_descartados(em, itens, fora, regs)
    for c in regs:
        if c["id"] in novos or c["id"] in alterados:
            cabeca, _ = partes_linha(c.get("linha") or "")
            fonte = c.get("fonte") or ""
            # E13: so id e selo (a linha ja esta em ledger_updates.concursos)
            itens.append({"chave": "concurso|%s|%s|%s|%s" % (c["id"], "novo" if c["id"] in novos else "atualizado",
                                                             hoje[:4], hoje),
                          "fonte": "Coletor concursos",
                          "categoria": "Concursos - Apoio" if c.get("bloco") == APOIO else "Concursos - Carreira",
                          "titulo": cabeca or c["id"], "data": hoje, "status": c.get("selo"),
                          "url": fonte if fonte.startswith("http") and not WRAPPER.search(fonte) else ""})
    if v and v.get("ok"):
        itens.append({"chave": "%s|versiculo|%s|%s|%s" % (slug(v["fonte"].split(".")[0], 20), slug(v["referencia"]),
                                                          hoje[:4], hoje),
                      "fonte": v["fonte"], "categoria": "Versículo", "status": "VERSÍCULO DO DIA",
                      "titulo": "%s (%s)" % (v["referencia"], v.get("versao") or ""), "data": hoje,
                      "url": v.get("url") or ""})
        if not em.get("reflexao"):
            erros.append("email.reflexao ausente (reflexão própria de 2–3 linhas ligada ao dia)")
    m = j.get("munger") or {}
    itens.append({"chave": "munger|citacao|%s|%s|%s" % (m.get("idx"), hoje[:4], hoje), "fonte": m.get("fonte") or "",
                  "categoria": "Munger", "status": "SABEDORIA DO DIA", "titulo": m.get("texto") or "", "data": hoje,
                  "url": ""})
    ex["items"] = itens
    # pendencias: as do ledger, ja com os updates de hoje (o orquestrador nao as redigita)
    pend = aplicar_pendencias(led.get("pendencias_vivas") or [], (ex.get("ledger_updates") or {}).get("pendencias"))
    ex["pendencias"] = [{"id": p["id"], "texto": p.get("texto", ""), "faixa": p.get("faixa", "")} for p in pend]
    # errata publicada sai do ledger sozinha
    for p in pend:
        if p["id"].startswith("errata_") and not p.get("_nova"):
            ex.setdefault("ledger_updates", {}).setdefault("pendencias", {}).setdefault(
                p["id"], {"remover": True, "desfecho": "Errata publicada na edição de %s." % br_data(hoje)})
    # e-mail
    if not (em.get("preheader") or "").strip():
        erros.append("email.preheader ausente (2–3 destaques do dia separados por ' · ')")
    cards = em.get("resumo") or []
    if not 3 <= len(cards) <= 5 or any(not isinstance(c, list) or len(c) != 3 for c in cards):
        erros.append("email.resumo: use de 3 a 5 cards no formato [emoji, título curto, frase]")
    op_itens = [i for i in itens if i["categoria"] == "Opinião/Análise"]
    if len(op_itens) > 6:
        erros.append("Opinião/Análise: %d itens (máximo 6)" % len(op_itens))
    # "alvo" so nas secoes de noticia comum; nunca nas centrais (Planalto/Legislação, Informativos, Concursos), que
    # entram completas: o aviso de 18/11 cortou 4 atos da Legislacao. AVISO comum: nao pede rodada sozinho
    for cat in ("STF Notícias", "Mídia", "Fofoquinha"):
        n = sum(1 for i in itens if i["categoria"] == cat)
        if n > 12:
            avisos.append("%s com %d itens (alvo ~10): numa nova rodada, enxugue os menos relevantes" % (cat, n))
    # G8: o leitor nao ve codigo http nem nome de script. O rodape e sempre o calculado; limitacoes e
    # observacoes saem como escritas, entao o montador aponta o trecho tecnico (sem apagar: apagar embaralha)
    if str(em.get("suporte") or "").strip():
        avisos.append("email.suporte ignorado: o rodapé \"Suporte usado na execução\" é automático (fontes que "
                      "falharam vêm do source_status); detalhe técnico vai em errors/verification_notes")
    lim = em.get("limitacoes") or ""
    textos = [("email.limitacoes", lim)] + [("email.observacoes[%d]" % i, o)
                                           for i, o in enumerate(em.get("observacoes") or [])
                                           if not ja_em_limitacoes(o, lim)]      # a repetida nem sai
    for onde, txt in textos:
        tec = tecnico_para_leitor(txt)
        if tec:
            avisos.append("%s traz detalhe técnico ao leitor (%s): reescreva em linguagem simples (o técnico vai em "
                          "errors)" % (onde, ", ".join(tec[:4])))
    # E-min (f): o rodape calculado diria "Nenhuma fonte falhou" ao lado de um texto que diz que uma falhou
    if not fontes_que_falharam(ex.get("source_status") or {}, ex):
        for onde, txt in textos:
            frase = falha_no_texto(txt)
            if frase:
                avisos.append("rodapé diz \"Nenhuma fonte falhou nesta execução\" (nenhuma fonte com 'falha' no "
                              "source_status), mas %s fala em falha («%s»): se a fonte falhou, marque \"falha\" no "
                              "source_status dela; senão, reescreva o texto" % (onde, curto(frase, 80)))
                break
    urgente = [x for x in prazos(regs, hj) if x[1] <= 7]
    if (urgente or novos) and not any(re.search(r"(?i)concurs|inscri|edital|prova", " ".join(map(str, c[1:])))
                                      for c in cards if isinstance(c, list)):
        avisos.append("há prazo de concurso em até 7 dias ou concurso novo e nenhum card do resumo executivo trata disso")
    ctx["descartadas"] = descartadas
    return erros, avisos, ctx


def marcas_da_migracao(ctx):
    """AVISO (comum) com o que a migracao de hoje pos no e-mail sozinha: o orquestrador nao a escreveu e o resumo
    executivo pode querer cita-la. Vazio sem migracao hoje."""
    mig = ctx.get("migracoes") or {}
    if not mig.get("migracoes"):
        return []
    por_id = {c["id"]: c for c in ctx.get("regs") or []}
    grupos = [("NOVO", [orgao(por_id[i]) for i, m in mig["concursos"].items() if m == "novo" and i in ctx["novos"]
                        and i in por_id]),
              ("Atualizado hoje", [orgao(por_id[i]) for i, m in mig["concursos"].items()
                                   if m == "alterado" and i in ctx["alterados"] and i in por_id]),
              ("Saiu do acompanhamento", [r.get("orgao") or r["id"] for r in ctx.get("removidos") or ()
                                          if removido_na_migracao(mig["concursos"].get(r["id"]))])]
    partes = ["%s: %s" % (rot, ", ".join(nomes)) for rot, nomes in grupos if nomes]
    if not partes:
        return []
    return ["migração de hoje (%s) já nas marcas do dia — %s; itens do histórico automáticos, não repita em "
            "ledger_updates" % (", ".join(mig["migracoes"]), "; ".join(partes))]


def segunda_tentativa(itens, ev, avisos):
    """Informativo citado por ref cujo documento nao abriu no passo 2 (o firewall do STF recusa a
    maior parte dos pedidos, ao acaso): insiste agora, minutos depois, ate MAX_TENTATIVAS_MONTADOR
    pedidos por documento e PRAZO_MONTADOR_S no total. Abriu -> entra na evidencia e sai com
    destaques; o PDF fica no cache da execucao, entao a proxima rodada do montador (depois de um
    Edit) e a remontagem do passo 7 leem dali, sem rede — em 17/11/2026 o 1237 abriu numa rodada,
    deu 403 nas seguintes e o e-mail saiu sem destaques. Nao abriu -> edicao nova segue como
    numero/data/link; edicao que ja tinha sido anunciada sem destaques e descartada (devolvida no
    conjunto), sem repetir o aviso."""
    descartar = set()
    alvos = [(it["ref"], re.fullmatch(r"(stf|rg|stj)(\d+)", str(it.get("ref") or ""))) for it in itens
             if it.get("ref")]
    alvos = [(ref, m) for ref, m in alvos if m and not (ev.get(ref) or {}).get("ok")]
    if not alvos:
        return descartar
    try:
        import informativos
        pub = informativos.publicados()
    except Exception as e:  # noqa: BLE001 — a segunda tentativa e reforco, nunca bloqueia
        avisos.append("segunda tentativa dos informativos indisponível (%s)" % e)
        return descartar
    prazo = informativos.relogio() + informativos.PRAZO_MONTADOR_S
    for ref, m in alvos:
        tipo, n = m.group(1), int(m.group(2))
        anunciada = pub.get(tipo, {}).get(n) is True
        try:
            r = informativos.obter(tipo, n, "atrasada" if anunciada else "nova",
                                   tentativas=informativos.MAX_TENTATIVAS_MONTADOR, prazo=prazo)
        except Exception:  # noqa: BLE001
            r = {}
        if r.get("ok"):
            ev[ref] = dict(r, _fonte="informativo")
            avisos.append("%s: documento abriu na segunda tentativa — %d destaques (saem todos)" % (ref, len(r["itens"])))
        elif anunciada:
            descartar.add(ref)
            avisos.append("%s: documento segue sem abrir; já anunciado antes — fica para a próxima execução" % ref)
    return descartar


def com_avisos(saida):
    base, ext = os.path.splitext(saida)
    return base + "-com-avisos" + (ext or ".html")


def limpar_para_gravar(ex):
    """Versao resolvida para o passo 7: sem os campos internos (_*) e os so de exibicao."""
    out = copy.deepcopy(ex)
    out.pop("_refs_descartadas", None)
    out.pop("_falha_informativos", None)       # rotulo da falha dos informativos, so para o e-mail
    for it in out.get("items") or []:
        for k in [k for k in it if k.startswith("_") or k in ("resenha", "impacto", "desdobramento", "resumo_truncado")]:
            del it[k]
    return out


def tamanho_secoes(secoes):
    return sorted(((nome, len(h.encode("utf-8"))) for nome, h in secoes), key=lambda x: -x[1])


def kb(n):
    return ("%.1f KB" % (n / 1000)).replace(".", ",")


def main():
    ap = argparse.ArgumentParser(description="Monta o e-mail do Robozinho a partir do julgamento (passos 4/5).")
    ap.add_argument("--execucao", default=tmp("execucao.json"))
    ap.add_argument("--janela", default=tmp("janela.json"))
    ap.add_argument("--ledger", default=os.path.join(AQUI, "robozinho-aprendizado.json"))
    ap.add_argument("--historico", default=os.path.join(AQUI, "resumo-legislativo-historico.json"))
    ap.add_argument("--saida", default=tmp("email.html"))
    ap.add_argument("--resolvido", default=tmp("execucao.resolvido.json"),
                    help="versao resolvida, lida pelo finalizar.sh (o execucao.json nunca e sobrescrito)")
    ap.add_argument("--bancas", default=tmp("bancas.json"))
    ap.add_argument("--fontes-status", dest="fontes_status", default=tmp("fontes_status.json"))
    ap.add_argument("--com-html", action="store_true", help="imprime tambem o corpo (so depuracao)")
    ap.add_argument("--sem-html", action="store_true", help=argparse.SUPPRESS)   # compatibilidade: ja e o padrao
    a = ap.parse_args()

    saida_avisos = com_avisos(a.saida)
    for p in (a.saida, saida_avisos):           # nada de HTML velho depois de uma rodada com ERRO
        if os.path.exists(p):
            os.remove(p)

    def falhar(linhas):
        if os.path.exists(a.resolvido):
            os.remove(a.resolvido)
        print("\n".join(linhas))
        print("MONTAGEM: ERRO — corrija %s e rode de novo (nada foi gravado)." % a.execucao)
        sys.exit(2)

    ex = ler(a.execucao)
    j = ler(a.janela)
    led = ler(a.ledger, {})
    if not isinstance(ex, dict) or not isinstance(j, dict) or "munger" not in j:
        falhar(["ERRO: faltam %s ou %s (rode work/inicio.py e escreva o julgamento antes)" % (a.execucao, a.janela)])
    ev = evidencias()
    v = ler(tmp("versiculo.json"), {})

    erros, avisos, ctx = preparar(ex, j, led, ev, v, {"historico": a.historico, "bancas": a.bancas,
                                                     "fontes_status": a.fontes_status})
    if erros:
        falhar(["ERRO: " + e for e in erros])
    ex.setdefault("execution_id", j.get("execution_id"))
    with open(a.resolvido, "w", encoding="utf-8") as f:
        json.dump(limpar_para_gravar(ex), f, ensure_ascii=False, indent=1)
    r = subprocess.run([sys.executable, os.path.join(AQUI, "Update-Historico.py"), "--validar", "--nova-execucao",
                        a.resolvido, "--ledger", a.ledger, "--janela", a.janela, "--historico", a.historico,
                        "--bancas", a.bancas, "--fontes-status", a.fontes_status], capture_output=True, text=True)
    linhas = r.stdout.splitlines()
    validacao = [l for l in linhas if l.startswith("VALIDACAO")]
    if r.returncode != 0:
        falhar([l for l in linhas if l.startswith("ERRO")] + [x for x in [r.stderr.strip()[-400:]] if x] + validacao)
    do_helper = [l[len("AVISO: "):] for l in linhas if l.startswith("AVISO: ")]
    avisos = agrupar_avisos(sem_tipo_repetido(do_helper, avisos) + avisos)

    try:
        from zoneinfo import ZoneInfo
        agora = datetime.now(ZoneInfo("America/Sao_Paulo"))
    except Exception:  # noqa: BLE001
        agora = datetime.now()
    corpo, secoes, regs, novos, alterados, pend = montar(ex, j, led, ev, v, agora, ctx)
    problemas = []
    if "{{" in corpo or re.search(r"__[A-Z_]{3,}__", corpo):
        problemas.append("marcador/placeholder no corpo")
    if WRAPPER.search(corpo):
        problemas.append("wrapper/rastreio no corpo")
    if problemas:
        falhar(["ERRO: " + p for p in problemas])
    dados = corpo.encode("utf-8")
    if len(dados) >= TAMANHO_AVISO:          # D6: nunca ERRO; a alavanca e Concursos, nao a Midia
        maiores = tamanho_secoes(secoes)[:4]
        # 1o dos informativos: diz como ler o arquivo (allow_large) e nao pode cair no montagem-avisos.txt
        avisos.insert(0, "corpo com %s (≥ %d KB; o Gmail corta a exibição perto de 102 KB, sem perder conteúdo) — "
                         "maiores seções: %s%s; leia o arquivo com allow_large" % (
                             kb(len(dados)), TAMANHO_AVISO // 1000, ", ".join("%s %s" % (n, kb(b)) for n, b in maiores),
                             "; a alavanca é Concursos (compactação e remoção de encerrados)"
                             if maiores and maiores[0][0] == "Concursos" else ""))
    acionaveis = [x for x in avisos if ACIONAVEL.search(x)]
    informativos_av = [x for x in avisos if not ACIONAVEL.search(x)]
    destino = saida_avisos if acionaveis else a.saida
    with open(destino, "wb") as f:
        f.write(dados)
    n_not = sum(1 for i in ex["items"] if i["categoria"] not in ("Concursos - Carreira", "Concursos - Apoio",
                                                                  "Versículo", "Munger"))
    compacto = criterio_compacto(j, date.fromisoformat(j["data"]), novos, alterados, ctx.get("selo_mudou") or set())
    n_comp = sum(1 for c in regs if compacto(c))
    resumo = "%d itens de notícia, %d concursos (%d novos, %d atualizados hoje, %d em linha compacta), %d pendências" % (
        n_not, len(regs), len(novos), len(alterados), n_comp, len(pend))
    if ctx["descartadas"]:
        resumo += ", %d descartada(s)" % len(ctx["descartadas"])
    saida = validacao[-1:]
    if acionaveis:
        saida.append("MONTAGEM: OK COM AVISOS — %s; %d aviso(s) acionável(is): corrija o execucao.json e rode de "
                     "novo, ou aceite os avisos e use o arquivo de CAMINHO" % (resumo, len(acionaveis)))
    else:
        saida.append("MONTAGEM: OK — %s" % resumo)
    saida += ["ASSUNTO: %s" % j["assunto"], "PARA: %s" % json.dumps(DESTINATARIOS)]
    detalhe = ctx["descartadas"] + ["AVISO ACIONÁVEL: " + x for x in acionaveis] + ["AVISO: " + x for x in informativos_av]
    cabe, usado = [], 0
    for l in detalhe:                        # stdout < 3 KB: o excedente vai para um arquivo
        # o fim diz o que fazer: corta o meio. O acionavel (pede decisao; o meio pode ser o que fazer, como em
        # "encerradas → … ; prorrogadas → …") so e cortado acima de 600 caracteres
        lim = 600 if l.startswith("AVISO ACIONÁVEL: ") else 320
        l = l if len(l) <= lim else l[:lim - 120] + " … " + l[-117:]
        if usado + len(l) > 2100:
            break
        cabe.append(l)
        usado += len(l) + 1
    if len(cabe) < len(detalhe):
        resto = tmp("montagem-avisos.txt")
        with open(resto, "w", encoding="utf-8") as f:
            f.write("\n".join(detalhe) + "\n")
        cabe.append("(+%d linha(s): lista completa em %s)" % (len(detalhe) - len(cabe), resto))
    saida += cabe
    saida += ["BYTES: %d" % len(dados), "SHA256: %s" % hashlib.sha256(dados).hexdigest(), "CAMINHO: %s" % destino]
    print("\n".join(saida))
    if a.com_html:
        print("==== HTMLBODY ====")
        print(corpo)
        print("==== FIM HTMLBODY ====")


if __name__ == "__main__":
    main()
