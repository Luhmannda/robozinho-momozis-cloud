# Coletor Gmail oficial — Robozinho dos Momozis até Passar

Janela: {{INICIO}} → {{FIM}} (America/Sao_Paulo). Hoje: {{HOJE_BR}} ({{DIA_SEMANA}}). Recesso forense: {{RECESSO}}.

Roteiro de 4 mensagens — junte as chamadas independentes, porque cada turno reenvia seu contexto inteiro: (1) Read deste arquivo + ToolSearch; (2) as 5 buscas juntas; (3) todos os `get_thread` das threads da janela, juntos; (4) a entrega: SubagentHandback (quando existir) com todas as linhas do formato abaixo.

Horários sempre em America/Sao_Paulo: a data do e-mail vem em UTC (−3h). Notícia sem horário interno: use só o dia.

**Passo 1 — numa única mensagem, 5 × `mcp__Gmail__search_threads` (pageSize 20).** `after:{{GMAIL_APOS}}` é uma **data** (com epoch numérico o Gmail devolve `{}` — armadilha `gmail_after_epoch`). A busca pode trazer e-mails do mesmo dia anteriores à janela: **filtre pela data/hora de cada mensagem** (America/Sao_Paulo) contra {{INICIO_BR}}. Busca vazia com data é resultado válido; nunca troque por epoch.
- a) `from:naoresponda@stf.jus.br after:{{GMAIL_APOS}}` — STF Notícias
- b) `from:nao_responda@stf.jus.br after:{{GMAIL_APOS}}` — Informativo STF **e** Repercussão Geral em Pauta (produtos distintos; esta busca cobre os dois)
- c) `from:stj.codju@stj.jus.br after:{{GMAIL_APOS}}` — STJ CodJu: Informativo (semanal) e Jurisprudência em Teses (assunto "Jurisprudência Em Teses - EDIÇÃO N. …"); vazio é normal
- d) `from:presidencia.gov.br in:anywhere after:{{GMAIL_APOS}}` — PUSH Planalto (o domínio cobre `no-reply-push-legislacao@` e o legado `sistemapushsaj@`). Só esta sonda; `PLANALTO_ATO` só de remetente `@presidencia.gov.br` (edição do Robozinho ou do Migalhas que cite a resenha não é fonte).
- e) `from:boletins@camara.gov.br in:anywhere after:{{GMAIL_APOS}} -subject:"Acompanhe seu Deputado"` — boletim da Agência Câmara de Notícias. `in:anywhere` de propósito: o boletim às vezes vai para a lixeira.

**Passo 2 — numa única mensagem, `mcp__Gmail__get_thread` (`messageFormat: PLAIN_TEXT`) só das threads da janela.** Não abra a thread cujas mensagens listadas na busca são todas anteriores a {{INICIO_BR}} (a busca mostra só as 5 mensagens mais antigas de cada thread: com `messageCount` maior que as listadas, abra). As não abertas só contam no `BUSCAS`. Thread na lixeira cujo `get_thread` for negado: use o resumo da busca e marque "lista incompleta (lixeira)".

**Entrega — uma linha por item, neste formato:**
```
STF_NOTICIA | <DD/MM HH:MM interno da notícia> | <título exato> | <URL da notícia (noticias.stf.jus.br / portal.stf.jus.br) ou "sem URL"> | <1ª frase do texto, copiada>
STF_RG | <número pelo slug do PDF> | <data do e-mail> | <URL do PDF>
STF_INFORMATIVO | <número, conferido com o assunto> | <data do e-mail> | <URL do e-mail>
STF_OUTRO | <assunto> | <data> | <por que não é informativo (ex.: andamento processual)>
STJ_INFORMATIVO | <número> | <data — ambos do ASSUNTO> | <URL do documento>
STJ_TESES | <número da edição> | <tema da edição, exato> | <data do e-mail> | <URL do documento, ou "sem URL">
PLANALTO_ATO | <tipo e número/ano do ato> | <data do ato, DD/MM/AAAA> | DOU <DD/MM/AAAA>[ (edição extra)] | <ementa copiada da resenha> | <link do ato na resenha, ou "sem link"> | resenha: <assunto exato do e-mail> | recebida <DD/MM HH:MM>
PLANALTO | <assunto e data de cada e-mail que não for resenha (ex.: confirmação de inscrição — não abra links com token), ou "sonda vazia">
CAMARA | <[LEI] ou [PLENARIO]> | <DD/MM HH:MM do boletim> | <seção do boletim> | <título exato> | <URL camara.leg.br do item>
CAMARA_RESTO | <DD/MM HH:MM do boletim> | <n> itens sem [LEI]/[PLENARIO] | seções: <nomes> | títulos com "Plenário", "sanciona", "promulga", "veto" ou "medida provisória" não marcados: <títulos exatos, ou "nenhum">
BUSCAS | a=<na janela>/<total> b=… c=… d=… e=… | abertas=<n> | anteriores à janela, não abertas=<n> | erros: <mensagem literal, ou "nenhum">
```
- **STF:** o push de um dia repete notícias dos dias anteriores: liste **todas** as notícias de cada e-mail recebido na janela, cada uma com o próprio horário interno, e prefixe `[ANTES]` as anteriores a {{INICIO_BR}}. A mesma URL em mais de um e-mail é **uma** linha. Sem boletim de Repercussão Geral na janela: `STF_RG | nenhum na janela`.
- **Informativos:** o conteúdo não é com você (`work/informativos.py` baixa o documento oficial e extrai os destaques), mas número, data e link de cada e-mail de informativo são indispensáveis: é por eles que a edição sai quando o documento não abre. Jurisprudência em Teses vai em `STJ_TESES`, **nunca** em `STJ_INFORMATIVO`.
- **BUSCAS:** por busca, threads com mensagem na janela / total devolvido (ex.: `a=2/3 b=0/1 c=0/0 d=1/1 e=0/2`).
- **Planalto:** uma linha `PLANALTO_ATO` por ato de cada Resenha Diária PUSH Legislação; `resenha:` é o assunto exato do e-mail de onde o ato veio (ex.: `Resenha Diária PUSH Legislação - 13/11/2026 (edição extra)`) e `recebida`, o horário interno desse e-mail.
- **Câmara:** linha própria só para `[LEI]` (lei nova, sanção, promulgação, veto ou medida provisória) e `[PLENARIO]` (aprovação ou rejeição em Plenário); o resto do boletim vai contado em `CAMARA_RESTO`, com os títulos duvidosos listados ali para conferência.
- E-mail anterior a {{INICIO_BR}} não se lista (só conta no `BUSCAS`) — exceto as notícias de um push recebido **dentro** da janela, que vão todas, com `[ANTES]` quando for o caso.
