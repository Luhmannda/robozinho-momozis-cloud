# Robozinho dos Momozis até Passar — referência operacional

> Duas partes. **§0–§17:** as seções do prompt mestre v10.1 (24/09/2026) que raramente decidem algo numa execução normal, na mesma numeração do prompt mestre (`robozinho-dos-momozis-prompt.md`, que desde a v11 traz só a doutrina editorial), atualizadas em 16/11/2026 para o fluxo atual (onde um script passou a fazer o procedimento, o texto aponta o script). **§R:** os ramos de exceção da `ROTINA.md`, que ela aponta só quando o caso ocorre. Passos da ROTINA (16/11/2026): 1 = âncora (`work/inicio.py`); 2 = conferência anti-duplicata e coleta (coletores + `work/aguardar_coleta.py`); 3 = julgamento; 4–5 = Write do `/tmp/execucao.json` + `work/montar_email.py` + Read do e-mail; 6 = `create_draft`; 7–8 = conferência do rascunho, `work/finalizar.sh` e notificação. Onde algo aqui divergir da ROTINA ou do ledger, valem eles (o ledger acima de todos).

## 0. Pré-requisitos

- Ancoragem de data, resumo do ledger, reconciliação e anti-duplicata: ROTINA passos 1–2 (o `inicio.py` lê o estado e o ledger; o orquestrador não os lê em JSON). **Em conflito entre este documento e o ledger, o ledger vence** — ele é a memória empírica; este é a doutrina (ver Seção 16).
- Ao validar data por leitura web, perguntar de forma **neutra** ("qual data aparece na página?") — nunca sugerir a data esperada, para não induzir a confirmação.
- **PDF/OCR:** skill `pdf` para editais e anexos. Gerar PDF da newsletter e usar Canva **não fazem parte da rotina** — só sob pedido expresso.
- **DOU:** rotas web diretas bloqueadas (Seção 6). INLABS só com credenciais; APP DOU é contingência humana, não executável.
- **Autonomia total:** nunca pausar para pedir confirmação; diante de falha, fallback e seguir. **Sucesso = rascunho criado (ou duplicata legítima detectada) + histórico atualizado.** A execução agendada começa do zero: tudo o que a newsletter precisa está em arquivos do repositório.

## 4. Histórico e não duplicidade

- **Gravação: sempre pelo helper** (`work/Update-Historico.py`, chamado pelo `work/finalizar.sh` no passo 7), a partir do **arquivo** da execução — o `/tmp/execucao.resolvido.json` que o `montar_email.py` grava (com o `/tmp/execucao.json` editado depois da montagem, o `finalizar.sh` remonta antes: §R11; o `execucao.json` sem resolver só entra sem `ref` e com `chave` em todos os itens, como no `draft_ja_existente` da §R1), nunca JSON inline. Em tempo de execução não se lê o histórico nem o estado: a repetição chega marcada pelos scripts — e nunca se conclui "não existe edição do dia X" a partir de leitura truncada.
- **Campos por execução:** `execution_id`, `type` (`diaria`/`extra`), `run_started_at`, `run_finished_at`, `date`, `timezone`, `window_start`, `window_end`, `recipients`, `email_subject`, `delivery` (`sent`/`draft`/`draft_ja_existente`), `gmail_message_id` ou `draft_id`, `items`, `source_status`, `errors`, `pendencias`, `verification_notes`; o helper acrescenta `delivery_check` (`ausente_em_sent` quando a edição não foi achada em `in:sent` — ela só vira `sent` com o message id), `orquestrador`/`coletores` (uso medido, com `custo_relativo`) e `ledger_updates`. Campos extras são permitidos.
- **Por item:** fonte, categoria, título, data, identificador, URL oficial, status e **chave única estável** `fonte|tipo|numero|ano|data`, minúsculas (ex.: `dou|decreto|11999|2026|2026-06-29`). Item que muda de estado (prova marcada → prova realizada; rumor → desfecho) recebe chave nova com o desfecho; nunca reutiliza a chave anterior.
- **Arquivamento (automático):** o principal mantém as 10 execuções mais recentes; o excedente vai para `resumo-legislativo-historico-arquivo-AAAA-MM.json`. **Nunca apagar, apenas mover.**

## 5. Fontes oficiais mínimas

1. **Legislação federal e DOU:** Resenha PUSH do Planalto (Gmail); Portal do Congresso Nacional; Legislação Federal do Senado; Legislação Informatizada da Câmara; fichas de `legislacao.presidencia.gov.br`; Agência Câmara e Agência Senado. *(INLABS só com credenciais; APP DOU e Biblioteca Machado de Assis são contingência humana.)*
2. **STF:** notícias, portal, jurisprudência, informativos, repercussão geral, súmulas e súmulas vinculantes.
3. **STJ:** notícias, informativos, repetitivos, precedentes qualificados e súmulas.
4. **CNJ, CNMP, TSE e TST**, quando houver relevância jurídica.
5. **CJF, TRFs, TJs, TREs, TRTs, MPs, Defensorias, AGU, DPU, PGFN, Procuradorias e bancas oficiais**, quando o assunto envolver concurso, edital, remuneração, ato institucional ou jurisprudência setorial.

## 6. Protocolo obrigatório — DOU, Planalto e leis/atos federais

**Ordem: Gmail primeiro, depois web.**

**1) Gmail PUSH (fonte primária nominal).** Remetentes: `no-reply-push-legislacao@presidencia.gov.br` (atual, assunto `Resenha Diária PUSH Legislação - DD/MM/AAAA`) e `sistemapush.saj@presidencia.gov.br` (legado, `Resenha Diaria DD/MM/AAAA`). Datas reais a partir da âncora — nunca literais `AAAA/MM/DD`. Esforço conforme o ledger:
- Hoje o coletor Gmail faz uma sonda só: `presidencia.gov.br in:anywhere after:<data do início da janela>` (cobre os dois remetentes). Se ela falhar em dia com resenha esperada: (b) `from:sistemapush.saj@presidencia.gov.br in:anywhere after:<data>`; (c) `subject:"Resenha Diaria" in:anywhere after:<data>`.
- **`mudo`** (status no ledger) → **só a sonda ampla**, e direto para a Rota 13 (lida pelo `coleta_web.py`).
- Se a sonda **retornar** resenha: reclassificar `saudavel` no ledger, registrar a data da volta, restaurar o protocolo completo.

Não buscar `no-reply-push-legislacao@…` por `from:` — os hífens quebram o termo. Encontrada a resenha: `get_thread`, extrair os atos, `CONFIRMADO POR FONTE OFICIAL`.

**Regra de não-bloqueio:** sem resenha, **não interromper nem esperar intervenção humana** — Rota 13 → Rotas 7–11 e 15 → se nada confirmar, seção com o quadro de pendências e o aviso `PUSH Planalto não recuperado nesta execução`. **Nunca depender de colagem manual de EML.**

**2) Rotas web.**

| Rota | Fonte | Status |
|---|---|---|
| **1–6** | `planalto.gov.br`, `in.gov.br`, `pesquisa.in.gov.br`, `www4.planalto.gov.br`, `ccivil_03`, `jusbrasil/diarios` | **NÃO TENTAR** — bloqueio estrutural (TCP/403/CAPTCHA) |
| **7** | Portal do Congresso Nacional | Leis, MPs, decretos legislativos, vetos, promulgações |
| **8** | Legislação Federal do Senado | Leis com histórico; conferir "Ver Diário Oficial" |
| **9** | Legislação Informatizada da Câmara | Texto atualizado **não** substitui o original do DOU |
| **10** | Órgão emissor | Atos setoriais, com link ao DOU ou PDF oficial |
| **11** | Agência Câmara / Agência Senado | Alerta oficial; não substitui o DOU |
| **12** | DOUInforme (CJF) | **DESCONTINUADA** desde 01/07/2026 — não tentar |
| **13** | `www.congressonacional.leg.br/materias/ultimas-leis-publicadas` | **Melhor fallback, comprovado.** MPVs em `/materias/medidas-provisorias` — números e datas **exigem checagem cruzada** (armadilha no ledger) |
| **14** | `legislacao.presidencia.gov.br` | Último recurso — ECONNRESET reincidente. Tentar 1 vez e seguir |
| **15** | `www2.camara.leg.br/legin` | Publicação original com a data do DOU |
| — | INLABS | Só com credenciais; sem elas, registrar como não tentada |

Links `planalto.gov.br/ccivil_03/...` podem ser **publicados** como referência mesmo sem fetch.

**Para cada ato:** tipo, número, data, órgão, ementa, seção do DOU, edição, link oficial, rota de confirmação, impacto e status.

**Status:** Gmail PUSH → `CONFIRMADO POR FONTE OFICIAL`. Rotas 7–11 e 13–15 → `CONFIRMADO POR FONTE OFICIAL ALTERNATIVA`. Só notícia/snippet → `PENDÊNCIA DE VERIFICAÇÃO` ou `SEM CONFIRMAÇÃO OFICIAL`.

**Nas pendências, registrar:** se o PUSH retornou e-mail no período e quais rotas foram tentadas (as desabilitadas como `NÃO TENTADA — bloqueio estrutural`).

## 7. Fontes complementares

Dizer o Direito (apoio secundário, sempre conferindo a decisão original); ConJur, Migalhas e JOTA (mídia especializada); Qconcursos, Folha Dirigida, PCI, Gran/Gran Jurídico, Estratégia/Carreira Jurídica, Direção, CERS, Aprovação PGE, Mege, Magistrar (concursos e bastidores). **Regra de ouro:** fonte secundária nunca substitui fonte oficial.

## 8. Protocolo geral de contingência

1. Nunca tratar erro técnico, 403, 502, captcha, JavaScript, manutenção, timeout, DNS, bloqueio de ferramenta, página dinâmica, URL não aberta, resultado vazio, snippet isolado ou homepage defasada como ausência de novidade.
2. Fonte principal falhou → `PENDÊNCIA DE VERIFICAÇÃO`, a falha objetiva, as rotas tentadas, o impacto na confiabilidade e a ação para a próxima execução.
3. Antes de declarar falha final: busca restrita ao domínio oficial, página individual, resultado indexado, diário oficial, portal de transparência, órgão correlato ou banca oficial.
4. **STF:** se `noticias.stf.jus.br` falhar, páginas individuais recentes em `noticias.stf.jus.br` e `portal.stf.jus.br`, informativo, repercussão geral, pauta, agenda, jurisprudência, súmulas, teses e portarias.
5. **STJ:** últimas notícias quando abrir. Informativo/repetitivos/súmulas com captcha/JS → edições indexadas, `processo.stj.jus.br`, precedentes qualificados, PDF/HTML oficial. `stj.jus.br` às vezes devolve cache desatualizado — cruzar com mídia especializada antes de concluir "sem novidade".
6. **ConJur/Migalhas/JOTA:** homepage com datas incompatíveis não é clipping do dia. Buscar por domínio, editoria, data, RSS/newsletter, "Migalhas Quentes", "JOTA STF/Judiciário/Tributário". Só itens com data confirmada.
7. **Recesso forense (2 a 31/jul; 20/dez a 31/jan):** fluxo reduzido de STF/STJ, prazos suspensos e informativos sem edição nova são **normais** — registrar como "fluxo reduzido de recesso", **não** como pendência ou falha. Continuar consultando (monocráticas, plantão e atos administrativos continuam saindo).

## 8-A. Gmail — canal primário e de contingência

Papéis: **primário** (PUSH Planalto — antes de qualquer rota web, Seção 6); **contingência** (STF Push, STJ CodJu — em paralelo com as rotas web, sem esperar falha total); **editorial** (JOTA — sempre, `MÍDIA ESPECIALIZADA`). Caixa de `pereirafranciscofilho@gmail.com`, dentro da janela efetiva (`newer_than:`/`after:` ajustados; segundas e pós-gaps são > 24h).

> **JOTA** envia boletins tipicamente entre 10h e 20h: numa execução às 7h não haverá JOTA do dia D (usar D-1); execução atrasada pode encontrar D — usar normalmente. Ausência de JOTA-D não é falha. Fim de semana sem JOTA é normal.

| Remetente | Conteúdo | Seção |
|---|---|---|
| `no-reply-push-legislacao@presidencia.gov.br` (atual) e `sistemapush.saj@presidencia.gov.br` (legado) | Resenha Diária PUSH Legislação — sempre com `in:anywhere`. **FONTE PRIMÁRIA.** | Planalto |
| `naoresponda@stf.jus.br` | Notícias do STF (boletim diário; consolida dias anteriores após fins de semana e reitera itens de D-1) | STF Notícias |
| `nao_responda@stf.jus.br` | Informativos de jurisprudência e Boletim Repercussão Geral em Pauta (produtos distintos; número pelo slug do PDF; andamento processual não é informativo) | STF Jurisprudência / Informativos |
| `stj.codju@stj.jus.br` | Novidades de jurisprudência do STJ (CodJu) — número e data do ASSUNTO | STJ Jurisprudência / Informativos |
| `contato@jota.info` | Clipping jurídico e bastidores | Se saiu na mídia não é fofoca! |

**Protocolo:** `search_threads` por remetente com `after:` = a **data** do início da janela (epoch devolve `{}`) e filtro pelo horário interno → `get_thread` só das threads da janela → classificar (oficial STF/STJ/Planalto → `CONFIRMADO POR FONTE OFICIAL`; JOTA → `MÍDIA ESPECIALIZADA`) → **links do JOTA** (wrapper `t.rdsv2.net`, nunca publicar): o `work/jota_extrair.py` troca os links do e-mail salvo por marcadores `[L<n>]` (descadastro e preferências ficam fora do índice) e o `work/resolver_jota.py` resolve cada um sem seguir redirecionamento às cegas, só no `jota.info`, e confere o **título da página** com o anunciado; não bateu, `RECUSADO` ou erro → item **sem link** (o rótulo é automático); `BLOQUEADO` (rede) → sondagem curta por WebSearch `site:jota.info` (até 3; nada bateu → todos sem link). O "Suporte usado" do e-mail é escrito pelo montador. Nenhum e-mail → o coletor diz o que buscou, e o orquestrador decide.

## 17. Orquestração e delegação

O modelo principal é **orquestrador e revisor**; o que é determinístico (datas, janela, listagens web, banca, selos por data, contadores, montagem do e-mail) vai para scripts em `work/`; coleta volumosa vai para os coletores de `.claude/agents/` (modelo no frontmatter; prompts em `work/prompts/`, preenchidos pelo `inicio.py`; ROTINA passo 2). **Critério: volume, não dificuldade** — subagente parte do zero e reconstrói contexto; delegar tarefa de 1 chamada custa mais do que executá-la.

**Nunca delegar:** ancoragem de data; checagem cruzada de armadilhas; classificação de status e selos; a escolha do que entra em cada seção (a montagem do HTML é do `work/montar_email.py`); decisões do ledger; e `create_draft` — o rascunho é criado uma única vez, pelo orquestrador, após revisão. Subagente jamais cria, edita ou envia e-mail.

**Contrato de todo subagente** (no `.claude/agents/coletor-*.md`): *devolva evidência — título, data visível na fonte, URL —, relate o que tentou incluindo o que voltou vazio, e nunca conclua ausência de novidade; quem interpreta ausência é o orquestrador.* Existe para evitar o **falso negativo** — coletor diz "nada", orquestrador registra ausência, e a ferramenta é que falhou (Seção 8.1).

**Revisão antes de compor:** ROTINA passo 3. Coletor que falhe: relançar como em §R3 — o orquestrador **não** executa o coletor à mão; se falhar de novo, a falha vai para `errors` e as seções daquele coletor saem com o quadro de pendências e o aviso dito ao leitor. Delegação que falha nunca vira "sem novidade".

**Aprendizado sobre a delegação:** registrar no ledger o coletor que devolveu digest incompleto, afirmou ausência sem listar tentativas ou precisou ser refeito. Falha recorrente → promover de `haiku` para `sonnet`, ou reabsorver. Esta divisão de trabalho é hipótese sujeita à evidência, como qualquer outra.

## R. Ramos de exceção da ROTINA

A `ROTINA.md` traz a regra de parada de cada caso; aqui fica o procedimento. Leia esta seção só quando o caso ocorrer.

### R1. Duplicata no passo 2 (a edição de hoje já existe, sem registro)

`list_drafts` (b) ou `search_threads in:sent` (c) acharam o assunto de hoje, mas o `inicio.py` não imprimiu `RE-EXECUÇÃO` (a edição foi criada por uma sessão que caiu antes do `finalizar.sh`, ou à mão). Não crie rascunho; descarte o que os coletores e scripts trouxeram e, numa mensagem:
1. Write `/tmp/execucao.json` com `{"delivery": "draft_ja_existente", "items": [], "verification_notes": ["<o que foi achado: assunto, id, rascunho ou enviada>"]}` — não rode o montador;
2. `bash work/finalizar.sh --message-id <gmail_message_id da edição anterior>` (sem `--draft-id`): avança a janela; se a execução de hoje já estiver registrada, não toca em nada;
3. `PushNotification`: "duplicata detectada, nada criado".

Limite conhecido: os itens e os `ledger_updates` da edição que já saiu não entram no histórico (o write-ahead que resolveria isso — README, próximos passos — não foi feito).

### R2. Edição anterior ausente de `in:sent`

Antes de registrar "Apps Script não enviou": `get_draft` (`messageFormat: MINIMAL`) com o `draft_id` da linha `ASSUNTO ANTERIOR` e veja `labelIds` — `TRASH` (o dono apagou) vai para `verification_notes`, não vira pendência. Rode o `finalizar.sh` sem `--message-id`: a anterior segue `draft`, com `delivery_check: "ausente_em_sent"` e ALERTA (nunca vira `sent` sem prova); a execução seguinte procura de novo.

### R3. Coletor que falhou ou foi negado

- **`Agent` lançado em segundo plano** (a resposta diz que ele roda em background) → encerre o turno com uma linha de status e espere as notificações dos três, sem `sleep` nem consultas repetidas.
- **Tipo inexistente ou sem a ferramenta** → relance com `subagent_type: "general-purpose"` e `model` `haiku` (gmail) ou `sonnet` (jota, concursos), o mesmo prompt da ROTINA e, no fim dele, o contrato que o agente próprio traria: *"Você só lê; nunca cria, edita ou envia e-mail. Devolva evidência (título, data visível, URL), liste item a item, relate o que tentou — inclusive o que voltou vazio ou com erro — e nunca conclua ausência de novidade."*
- **Negado pelo classificador** → não contorne nem execute o coletor à mão: confira com `diff` o `/tmp/coletor-X.md` contra `work/prompts/coletor-X.md` (só a janela e os dados do ledger podem diferir) e relance o **mesmo** `Agent` citando a conferência. Negado de novo → `errors`, quadro de pendências no lugar das seções daquele coletor e aviso na notificação.
- **Relatório incompleto** (totais sem itens, item sem horário ou sem a URL que a fonte tinha) → `SendMessage` (ToolSearch `select:SendMessage`) ao mesmo agente, pedindo só o que falta.
- **Coletor Gmail ou JOTA vazio em dia útil** → refaça só as buscas dele (`search_threads`, já carregado) com o `after:` de data do passo 1 e filtre pelo horário interno.
- Falha recorrente de um coletor → registre no ledger (`fontes` ou pendência); promover `haiku` → `sonnet` no frontmatter é decisão a tomar com evidência de várias execuções.

### R4. Script do passo 2 ainda rodando ou sem saída

Sem flag, o `aguardar_coleta.py` espera no máximo 90 s por chamada (cabe no timeout padrão do Bash) e nunca além de 240 s contados do **disparo** do passo 1: como os coletores rodam antes dele, em geral esse teto já passou e ele só confere (5 s). Script que não terminou sai como `== <script>.py (exit ?; segundo plano) — AINDA RODANDO (<s> s desde o disparo): saída parcial abaixo; a fonte fica sem status` e, antes da `SOURCE_STATUS`, numa linha `AINDA RODANDO <script>.py (<s> s desde o disparo) — para esperar mais: python3 work/aguardar_coleta.py --mais N (…)`. Espere por ele **numa mensagem própria, antes do Write** do `/tmp/execucao.json` (a dos WebSearch de fallback, se houver: os ids e as linhas `ERRO` dele só servem se você os vir antes de julgar), com **um** Bash de `timeout: 300000` (o padrão de 2 min mataria a espera):

```
python3 work/aguardar_coleta.py --mais 240
```

O `--mais 240` espera até mais 4 min **a partir desta chamada** e volta assim que os três terminarem (o `--teto`, que conta do disparo, ficou só por compatibilidade). Script já impresso inteiro na chamada anterior sai numa linha só, `== <script>.py (exit N; saída já impressa inteira na chamada anterior)`: para ele vale a saída de antes. Processo morto sem resultado é disparado de novo ali. A linha `SOURCE_STATUS` desta chamada substitui a anterior.
- **Terminou** → julgue com essa saída e cite os `ref` dele normalmente.
- **Ainda rodando** → as fontes dele vão como `falha` em `source_status` e em `errors` (`coleta_web`: `congresso_ultimas_leis`, `congresso_mpvs`, `camara_noticias`, `conjur`, `migalhas`; `informativos`: `informativos_docs`; `versiculo`: `youversion`, `dailyverses`, e o versículo segue pela §R5), nenhum `ref` dele é citado (o montador recusaria o id sem evidência) e a lacuna vai ao leitor em `email.limitacoes` (ex.: "Informativos do STF e do STJ não lidos nesta execução: a coleta não terminou a tempo; voltam na próxima edição"). Seção do centro da edição vazia sem aviso é falso negativo. Se o script terminar entre o Write e o montador, o montador troca o status (`AVISO: source_status: vale o do script`); a limitação continua verdadeira para esta edição.

`rodado aqui (sem disparo do inicio.py)` não é falha: o disparo estava desligado (`--sem-disparo`, `ROBOZINHO_DISPARO=0`) ou foi perdido, e o script rodou ali.

### R5. Versículo pelo fallback de WebSearch

Até 2 WebSearch (`bible.com verse-of-the-day`, `dailyverses.net/AAAA/M/D`). Só com o texto do dia, a referência e a data **visíveis** na página (nunca de memória, nunca do resumo do buscador sem a página datada). O `versiculo.py` sempre grava `/tmp/versiculo.json` (também com `ok: false`) e você não o leu: o Write pode recusá-lo (a ferramenta recusa sobrescrever arquivo existente não lido). Grave por **Bash**, na mensagem do Write do `/tmp/execucao.json`, **antes** do Bash do montador, rotulando a fonte REAL. O script troca só os campos do versículo; `tentativas` e `source_status` continuam os do `versiculo.py`:

```
python3 - <<'FIM'
import json, os
p = os.path.join(os.environ.get("ROBOZINHO_TMP", "/tmp"), "versiculo.json")
v = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {"tentativas": []}
v.update(json.loads(r'''{"ok": true, "fonte": "<site de onde veio>", "referencia": "João 16:28", "versao": "ARC",
 "texto": "<copiado da página>", "data_pagina": "AAAA-MM-DD", "url": "<página do dia>"}'''))
json.dump(v, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("VERSICULO gravado pelo fallback: %s · %s · %s" % (v["referencia"], v["fonte"], v["data_pagina"]))
FIM
```

O que fica entre `r'''` e `'''` é JSON: aspas dentro do texto vão como `\"`. Nada achado → não grave nada; a seção sai pendente sozinha.

### R6. Conferência do rascunho vazia (passo 7)

O `larger:` do Gmail conta a mensagem inteira (cabeçalhos e codificação), maior que o corpo: em 16/11 o corpo de 59.301 bytes deu uma mensagem entre 68.000 e 74.000 bytes. Com N = 0,9 × `BYTES`, o corpo completo sempre passa; o filtro pega corte de cerca de um quarto ou mais do corpo (como o de 05/11 e 10/11, em que faltou a seção de Concursos).
1. Numa mensagem, as quatro buscas: `list_drafts` com `subject:"<ASSUNTO>"` e com `subject:"<ASSUNTO>" larger:<N>`; `search_threads` com `subject:"<ASSUNTO>" in:sent` e com `subject:"<ASSUNTO>" in:sent larger:<N>` (o mesmo N). Achou **com** `larger:` em qualquer uma → a 1ª conferência pegou atraso de indexação, não corte: nada a fazer (a última mensagem volta a ser `OK · rascunho <id>`). Só é "menor que o esperado" o que aparece **sem** `larger:` e não aparece com ele.
2. **Rascunho menor que o esperado**: se a próxima varredura do Apps Script (:13, :28, :43, :58) estiver a mais de 3 min, `delete_draft` (ToolSearch `select:mcp__Gmail__delete_draft`) desse id e `create_draft` de novo com o conteúdo do Read do passo 4–5 (já no contexto; sem ele, Read, com `allow_large`, do arquivo da linha `CAMINHO` da montagem aceita — `/tmp/email-com-avisos.html` quando ela foi `OK COM AVISOS`: o `/tmp/email.html` nem existe nesse caso), na mesma mensagem e na ordem delete → create; varredura perto → não mexa (o Apps Script pode enviar no meio da troca). Nos dois casos, notificação urgente ao dono, com o que foi feito e o id novo (o histórico fica com o `draft_id` antigo — inofensivo: a reconciliação do dia seguinte procura pelo assunto em `in:sent`).
3. **Só a enviada, menor que o esperado**: notificação urgente; o dono decide a errata (pendência `errata_AAAA_MM_DD` na próxima execução).
4. **Nada achado**: o rascunho sumiu sem envio — notificação urgente; a próxima execução detecta pelo anti-duplicata.

### R7. Edição extra (a pedido do dono)

`python3 work/inicio.py --extra` no lugar do passo 1: `execution_id` `AAAA-MM-DD-extra`, assunto `Robozinho dos Momozis até Passar - DD/MM/AAAA - Extra`, cabeçalho "Edição extra", Munger com índice + 1, sem o ALERTA de fim de semana; a janela parte do `window_end` da última execução registrada (a diária de hoje, se houver). Daí em diante a ROTINA é a mesma (passos 2–8, o mesmo `finalizar.sh`). `RE-EXECUÇÃO` e `--refazer` valem igual, com o id `-extra`.

### R8. Re-execução com o rascunho apagado (`--refazer`)

A `RE-EXECUÇÃO` manda conferir o rascunho e a enviada de hoje. Os dois vazios (o dono apagou o rascunho sem envio) → `python3 work/inicio.py --refazer` reabre a janela original e ignora o registro de hoje na deduplicação; siga a ROTINA a partir do passo 1. O passo 7 substitui o registro de hoje; os `ledger_updates` são reaplicados e os contadores, não.

### R9. `PUSH: FALHOU`

O `finalizar.sh` já tentou 5 vezes e, se a `main` andou no remoto (`[rejected]`, non-fast-forward ou fetch first; a recusa de hook do servidor, `[remote rejected]`, não conta: é tentada de novo como falha comum), reaplicou o helper uma vez sobre a `origin/main` (sem rebase textual dos JSON). A linha `ESTADO:` diz o que fazer com a cópia do estado do dia (`/tmp/robozinho-estado-backup-<exec>.tar.gz`, refeita depois de cada rodada OK do helper):
- `ESTADO: … (commit local <sha>) — para reaplicar: tar -xzf … e commitar os arquivos work/ na main`: a cópia é a da última rodada OK (sobre a `main` nova, se houve reaplicação). É a recuperação do dono.
- `ESTADO: … (commit local <sha>, da 1a rodada, sobre a main anterior a mudanca concorrente) — NAO aplique o tar sobre a main atual (apagaria a mudanca concorrente): rode bash work/finalizar.sh de novo com os mesmos argumentos (entrada em …)`: a reaplicação não chegou ao fim. Repita o `finalizar.sh`, uma vez, numa mensagem própria; nunca o tar.

Diga isso na notificação: a cópia vive só nesta sessão, e sem o push a próxima execução não conhece a edição de hoje (o `inicio.py` acusará `dia útil sem execução registrada` e o passo 2 seguirá a §R10).

### R10. Dia útil sem execução registrada

O `inicio.py` acusa dia de edição (seg–sex, feriado incluído: `(feriado: a edição sai em feriado)`) entre a última execução registrada e hoje. A edição daquele dia pode ter saído sem registro (queda entre o `create_draft` e o push, ou `PUSH: FALHOU`): o histórico não a conhece, então os scripts marcam os itens dela como novos (sem `JA PUBLICADAS`), o montador não os descarta como `REPUBLICADA` e a janela começa no fim da última execução **registrada**.
1. No passo 2, junto da anti-duplicata, `search_threads` com o assunto daquele dia (o de hoje com a data trocada) + `in:sent`.
2. Nada achado → a edição não saiu: siga normalmente (a janela já cobre aquele dia).
3. Achada → diga em `verification_notes` (assunto, id e a data/hora do envio, que vem no resultado da busca). Tudo o que tem data **e** hora até esse envio já saiu nela: não publique, nem como herdado — inclusive `ref` de script e edição de informativo anunciada antes. Item só com data: o de dia anterior ao da edição achada já saiu; o do mesmo dia entra só se a fonte mostra hora posterior ao envio. Não abra a enviada (`get_thread` traria ~60 mil caracteres para saber o que a regra da hora já diz). Concursos saem do registro, como sempre: o que ela trouxe de novo e o registro não tem, o coletor traz de novo, e vale o caminho normal.
4. Limite: os itens e os `ledger_updates` dela não entram no histórico (o write-ahead que resolveria isso — README, próximos passos — não foi feito).

### R11. Linhas do `finalizar.sh` fora do normal

- **`REMONTAGEM: <T>/execucao.json é mais novo que a última montagem …`**: houve Edit no `/tmp/execucao.json` depois do último Bash do montador (ex.: a pendência `errata_…` achada depois do rascunho). O `finalizar.sh` rodou o montador de novo sozinho (corpo em `finalizar-email.html`, só para comparar; o rascunho e o `/tmp/email.html` não mudam, nada é enviado) e grava o histórico dessa remontagem. Seguem `REMONTAGEM: MONTAGEM: OK[ COM AVISOS]` (os avisos não se aplicam mais: o rascunho já existe), `REMONTAGEM: itens iguais aos da montagem anterior (N)` e `REMONTAGEM: corpo igual ao|diferente do <arquivo> (…)`. Itens iguais → nada a fazer (corpo diferente com itens iguais é o esperado depois de mexer só em `ledger_updates`).
- **`ALERTA: o execucao.json editado depois da montagem mudou os itens (A -> B; + chave…; - chave…)`**: o histórico registrou itens que o rascunho não tem (`+`) ou deixou de registrar os que ele tem (`-`); amanhã a deduplicação erra nos dois sentidos. Os `items` têm de ser os do rascunho (é o que o leitor recebe): desfaça o Edit deles, rode `python3 work/montar_email.py` e repita o `finalizar.sh` com os mesmos argumentos, numa mensagem — o registro de hoje é substituído (`Ledger: contadores ja aplicados …`: os contadores não se repetem). Item do rascunho que estava errado não se corrige nos `items`: é errata (pendência `errata_AAAA_MM_DD` em `ledger_updates.pendencias`, ROTINA passo 4–5). Vai na 2ª notificação, com o que foi feito. Prevenção: depois do `create_draft`, edite só `ledger_updates`.
- **`PERSISTENCIA ABORTADA: …`** (exit 2, nada commitado):
  - `… a remontagem deu ERRO (acima) — corrija o <T>/execucao.json, rode python3 work/montar_email.py e repita o finalizar.sh`: corrija o que as linhas `ERRO:` acima apontam (o Edit de depois da montagem), e, numa mensagem, Bash do montador + o mesmo `finalizar.sh`;
  - `… o helper nao terminou com STATUS: OK`: o relatório acima traz o `ERRO`; corrija no `/tmp/execucao.json` e repita do mesmo jeito;
  - `… nao encontrado`: a entrada sumiu; rode o montador e repita;
  - o desfecho (ou, se não deu, o que falta) vai na 2ª notificação: sem a gravação, a próxima execução não conhece a de hoje (§R10).
- **`PUSH: recusado (main andou no remoto) — reaplicando o helper sobre origin/main`**: alguém mudou a `main` no dia; o script reaplica sozinho. `AVISO: reset --keep recusado (alteracao local fora do estado) …`: informativo.
- **`AVISO: diferenca local depois da reaplicacao em <arquivos> — nao e da execucao de hoje: NAO commite …`** (depois do `PUSH: OK`): a árvore local ficou com o reverso da mudança concorrente. Não commite, não envie e não "limpe" nada, mesmo que o hook de parada acuse alteração não commitada: a execução de hoje já está na `main`. Diga na notificação.
- **`PUSH: FALHOU`** e **`ESTADO:`**: §R9.

### R12. Concursos: selo vencido, prorrogação e páginas da banca

- **Selo escrito × selo por data.** O helper e o montador aplicam a mesma regra (`selos.selo_escrito`): `selo` no `ledger_updates.concursos.<id>` **igual** ao do registro é cópia e não conta (vale o selo por data, no e-mail e no registro); **diferente** do registro (ou concurso novo) é decisão e prevalece nos dois. Se ele contradiz a data, sai `AVISO ACIONÁVEL: ledger_updates.concursos.<id>.selo: '<X>' escrito hoje contradiz o selo por data '<Y>' (…)`: não foi decisão → escreva `<Y>` ou tire o `selo` do update; a data mudou (prorrogação) → corrija os `prazos` e escreva o selo que a nova data dá.
- **Fim das inscrições vencido.** `INSCRIÇÕES ENCERRADAS` só vem sozinho com a banca oficial lida no dia (e o prazo posterior à última retificação); nesse caso o passo 1 imprime `PRAZO VENCIDO (sem ação): … — encerramento confirmado pela banca oficial lida hoje (…): selo INSCRIÇÕES ENCERRADAS automático` no lugar do `ALERTA: prazo vencido`: nada a buscar nem a escrever. Sem isso, `ENCERRA HOJE`, `ENCERRA EM BREVE` e `INSCRIÇÕES ABERTAS` caem para `PENDÊNCIA DE VERIFICAÇÃO` (`ALERTA: selo por data — <id> … → PENDÊNCIA DE VERIFICAÇÃO: … prorrogação não confirmada — …` no passo 1 e o mesmo texto como `AVISO ACIONÁVEL` no montador), e daí em diante nada muda sozinho: `PENDÊNCIA DE VERIFICAÇÃO` está fora da família de datas, e prazo novo sem selo escrito deixa o selo onde está. Confirme na fonte oficial:
  - encerradas → `"selo": "INSCRIÇÕES ENCERRADAS"` (volta à família; não exige fonte oficial);
  - prorrogadas → `prazos` com a data nova (`confirmado: true`, fonte oficial) **e** o selo que a nova data dá (`ENCERRA HOJE` / `ENCERRA EM BREVE` / `INSCRIÇÕES ABERTAS`, a regra do passo 3 da ROTINA);
  - sem confirmação → não escreva nada: `PENDÊNCIA DE VERIFICAÇÃO` é o honesto; aceite o aviso e use o arquivo de `CAMINHO`.
- **`prazos[].tipo`** (opcional; resolve o ambíguo, o script classifica o resto pelo `evento`; na dúvida, omita): `inscricoes_inicio`, `inscricoes_fim`, `prova` (só a data da prova) e `outro` (inscrição definitiva, resultado, gabarito, recurso, convocação, locais de prova). O `tipo` prevalece sobre o `evento`: `outro` no fim das inscrições desliga o selo por data, o rebaixamento e o DIVERGE desse prazo (`prova` o trata como a data da prova). Por isso, quando o `evento` diz fim (ou início) das inscrições e o `tipo` diz outra coisa, sai uma linha só por prazo (do montador; a do helper é a mesma): `AVISO ACIONÁVEL: ledger_updates.concursos.<id>.prazos[<n>].tipo: '<tipo>' num prazo cujo evento é o fim das inscrições («<evento>») — com esse tipo o selo por data ignora o prazo (com 'inscricoes_fim', o selo por data daria '<selo>': <porquê>); se é o fim das inscrições, escreva tipo 'inscricoes_fim' ou omita o tipo; se não é, aceite o aviso`. É mesmo o fim (início) das inscrições → `"tipo": "inscricoes_fim"` (`"inscricoes_inicio"`) ou sem `tipo`, e rode o montador de novo; não é (isenção, outra etapa que o texto confunde) → aceite o aviso e use o arquivo de `CAMINHO`.
- **Selo por data suspenso (`DIVERGE DO REGISTRO` não corrigido).** A regra é uma só no helper, no montador e no `inicio.py` (`bancas.selo_do_dia`): enquanto o trecho de inscrições do edital (ou da retificação) que o script leu **hoje** na banca contestar o fim das inscrições do registro, já com o `ledger_updates.concursos` de hoje, o registro fica sem o carimbo de verificação da banca (sai `(herdada; verificado em …)`) e o selo da família de datas fica como está, sem recálculo. Sai `AVISO ACIONÁVEL: DIVERGE DO REGISTRO em <id>: edital "…" × registro "…" — …` e, com as duas datas, `selo por data suspenso em <id>: o registro diz fim das inscrições em <DD/MM> e o edital lido hoje, <DD/MM> — o selo <SELO> fica como está (sem recálculo nem carimbo da banca) até prazos/linha baterem com o edital: corrija-os em ledger_updates.concursos.<id> ou escreva o selo` (sem fim das inscrições no registro: "o registro não traz o fim das inscrições e o edital lido hoje, DD/MM"). Essa linha é `ALERTA: selo por data suspenso em <id>: …` no passo 1 (junto do `DIVERGE DO REGISTRO: <id> …` da BANCA FGV e no lugar do `SELO POR DATA` desse id), `AVISO ACIONÁVEL: selo por data suspenso em <id>: …` no montador e `ALERTA: selo por data suspenso em <id>: …` na gravação (2ª notificação). Selo fora da família (`EM ANDAMENTO`, `PENDÊNCIA DE VERIFICAÇÃO`…) não tem a linha; o DIVERGE sai igual.
  - registro velho (o comum) → `prazos` com a data do edital (`confirmado: true`, fonte oficial) **e** `linha`, pelo trecho do edital (ou do LEIA-SE da retificação), e o montador de novo: o carimbo e o selo por data voltam na mesma montagem. Só a `linha` não basta: o fim das inscrições do registro sai dos `prazos` (a `linha` só conta sem prazo);
  - a data do registro vem de ato oficial mais novo que o edital lido hoje → cite o ato na `fonte`, escreva o selo que essa data dá e aceite o aviso (arquivo de `CAMINHO`). Selo diferente do atual é decisão e prevalece (a suspensão acaba); igual ao atual é cópia e não conta: o aviso continua e você o aceita (o selo já é esse).
- **Prazo escrito hoje contra o edital lido hoje.** O `prazos`/`linha` de hoje mudou o fim das inscrições que o registro dizia para uma data que o edital lido hoje não traz. No lugar do DIVERGE desse id, o montador mostra (vem do `--validar` do helper) `AVISO ACIONÁVEL: prazo escrito hoje difere do edital lido hoje: …`, e a gravação, a mesma linha como `ALERTA:` (2ª notificação): `prazo escrito hoje difere do edital lido hoje: <id> edital "<trecho do edital>" × update "<prazo DD/MM/AAAA evento, ou linha: trecho>" — confira a fonte da data escrita: …`. Até resolver, a regra de cima vale: sem carimbo e selo por data suspenso. Confira de onde veio a data:
  - o edital está certo (data de memória, de fonte secundária, de outro cargo) → corrija `prazos` **e** `linha` pelo trecho do edital;
  - ato oficial mais novo que o edital lido hoje (retificação nova que a leitura das 7h não trazia) → cite-o na `fonte`, escreva o selo que a nova data dá (sem ele, fica o selo da data antiga) e aceite o aviso.
- **ERRO na validação dos concursos** (do helper, mostrado pelo montador; nada gravado até corrigir): `INSCRIÇÕES ABERTAS`, `EDITAL PUBLICADO`, `ENCERRA*` ou prazo `confirmado: true` sem `fonte` oficial; `url_oficial`/`dominio_oficial` não oficiais; `banca_slug` fora do formato (`[a-z0-9/-]`, minúsculo) ou repetido em dois registros; "hoje/amanhã/ontem" na `linha`; `remover` sem `desfecho`; concurso novo sem `bloco`, `linha`, `selo`, `verificado_em` ou `fonte` http. Escreva certo da primeira vez: cada ERRO custa uma rodada do montador.
- **Domínio oficial.** `url_oficial` e `dominio_oficial` só de órgão (`.jus.br`, `.gov.br`, `.leg.br`, `.mp.br`, `.def.br`) ou de banca da lista `selos.BANCAS_OFICIAIS`; o resto é ERRO. O `dominio_oficial` não sustenta mais a fonte de selo ou prazo confirmado: vale só a `fonte`.
- **Página da FGV de outro concurso do mesmo órgão.** `SEM REGISTRO (<id>, da mesma sigla, é de outro cargo) → avalie como NOVO`: não é o registro `<id>`. `registro incerto: <id>` seguido de `AVISO: página não cobre <id> (<motivo>): …`: a página não carimba, não dá selo por data nem DIVERGE; trate o registro pelo caminho normal (coletor) e só leve os arquivos dela à `linha` depois de confirmar o cargo.
- **`PROVA EM BREVE` sem prova nos próximos 14 dias** (a prova passou sem confirmação oficial de que foi aplicada, ou foi para longe): o selo por data cai para `PENDÊNCIA DE VERIFICAÇÃO` (`ALERTA: selo por data — <id> PROVA EM BREVE → PENDÊNCIA DE VERIFICAÇÃO: … (adiamento ou prorrogação não confirmada) — …` no passo 1, o mesmo texto como `AVISO ACIONÁVEL` no montador). Confirme na fonte oficial: aplicada → `"selo": "PROVA REALIZADA"`; adiada → `prazos` com a data nova (`confirmado: true`, fonte oficial) e o selo que ela dá; sem confirmação, nada (aceite o aviso e use o arquivo de `CAMINHO`). Sem prazo de prova no registro, o selo fica.
- **BANCA FGV: vínculo da página com o registro** (`work/bancas.py`, 21/11/2026). A página só cobre (carimbo, selo por data, DIVERGE) o registro vinculado: pelo `banca_slug` (o slug da FGV, minúsculo: `tjap26`, `dperj2026`, `exames/enam/6exame`; único entre os registros; `""` desfaz) ou, sem ele, pela `fonte`/`url_oficial` igual à página ou a um arquivo dela.
  - `registro <id> [vínculo pela fonte: grave banca_slug="<slug>"]` → grave `ledger_updates.concursos.<id>.banca_slug` (o vínculo pela fonte é só a rede de segurança da transição);
  - `CANDIDATO <id> ← <slug> | … → confirme o ciclo (ordinal/ano) e grave ledger_updates.concursos.<id>.banca_slug="<slug>"`: mesma organização e cargo, sem vínculo. Confira pelo título e pelos arquivos que é o mesmo concurso (ordinal, ano, edital) e grave; outro ciclo → avalie como NOVO; `(cargo não identificado…)` → confirme qual registro antes;
  - `CANDIDATO a registro NOVO <id> ← exames/<org>/<n>exame … → exame nacional sem registro: crie …`: crie o registro como a linha diz (bloco, prazos do cronograma, `fonte` = a página, `banca_slug`);
  - `NOVA EDIÇÃO? <slug> … — <id> está vinculado a <slug>`: página de ciclo maior (`tjscjuiz27`, `7exame`) que a vinculada. Se é o ciclo seguinte do mesmo concurso acompanhado → `linha`, `prazos` e `banca_slug` novos no registro; se é outro concurso, avalie como NOVO;
  - registro em `PENDÊNCIA DE VERIFICAÇÃO` (só secundária) que a página da banca passa a confirmar → `linha` e `prazos` pelo edital e o selo que a data dá (ao entrar na família de datas) ou, com as inscrições já encerradas e o concurso em fase posterior, `EM ANDAMENTO`;
  - `- MOVIMENTO sem registro: <slug> | <título> | <arquivos novos> | <URL>[ [nota]]`: concurso jurídico em andamento na FGV, sem registro, aberto há mais de 60 dias, com arquivo novo nos últimos 7 dias (`[não é <id>: XXXIX × XL]` = outro ciclo do registro). Avalie como NOVO **no mesmo dia**: o helper marca esses arquivos como vistos e a linha some amanhã. É fonte oficial; carreira final entra de todo o país, apoio só no escopo; concurso encerrado (resultado final, homologação) não entra;
  - `sem linha (só contagem, sem registro): …` (sem arquivo novo, apoio fora do escopo, fora de carreira): nada a fazer.
- **Escopo regional** (decisão do dono, 20/11/2026; `work/escopo.py`): carreiras finais em todo o país; quadro de apoio só com lotação em SP, RJ, MG, ES, PR, SC ou RS, ou órgão nacional com vagas nelas (MPU, DPU…). Registro de apoio fora disso vem na linha `FORA DO ESCOPO` do passo 1 (sem busca, foco nem leitura da página oficial) → `remover` com o desfecho que a linha dá (no dia, o montador o mostra no bloco: "Saiu do acompanhamento").
- **`PAGINA OFICIAL`** (`work/paginas_oficiais.py`: toda `url_oficial` no escopo, todo dia): `MUDOU` = item novo na página (até 5, do mais recente); `LIDA (1ª vez)` = primeira leitura (os 5 mais recentes); `RELIDA (formato novo: confira com o registro)` = estado antigo relido, sem MUDOU falso; `sem item novo` = igual; `não lida (domínio fora da rede hoje)` = não baixada. Ato novo com data → `linha`/`prazos`, com a página na `fonte` (fonte oficial); item que o registro já tem não é movimento.
- **Pendências e prazos que não ganham busca** (prompt do coletor): `REVERIFICAR` ganha busca; `COBERTA PELO PRAZO de <id>` (o prazo do registro já tem busca hoje) e `SÓ VIGIAR MOVIMENTO NOVO` (longo prazo; página oficial fora da rede; ou só secundária com o oficial fora da rede, salvo na 1ª execução da semana) não ganham — silêncio delas não é falha. Prazo só em secundária com o oficial fora da rede só tem busca ao cruzar D-7, D-1, D0 e D+1; depois, `PRAZO VENCIDO (só secundária; desfecho já buscado pelo coletor, sem busca hoje)` → atualize o registro só com fato novo. `ALERTA: candidato a remoção (<id>, prazos só em secundária)`: todas as datas (só de secundária) vencidas há mais de 30 dias e nenhuma futura.

### R13. `create_draft` com erro ou timeout (passo 6)

O `create_draft` pode ter criado o rascunho mesmo com erro ou timeout, e o Apps Script pode já tê-lo enviado. Antes de qualquer nova tentativa, numa mensagem, `list_drafts` com `subject:"<ASSUNTO>"` e `search_threads` com `subject:"<ASSUNTO>" in:sent`:
- achou em qualquer uma → **não recrie**: esse `id` vai no `--draft-id` do passo 7;
- nada nas duas → 1 nova tentativa, igual à primeira (o mesmo conteúdo do Read);
- 2ª falha → **não** rode o `finalizar.sh` e notifique "rascunho não criado: <erro>".
