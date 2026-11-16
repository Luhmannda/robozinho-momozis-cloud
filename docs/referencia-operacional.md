# Robozinho dos Momozis até Passar — referência operacional

> Duas partes. **§0–§17:** as seções do prompt mestre v10.1 (24/09/2026) que raramente decidem algo numa execução normal, na mesma numeração do prompt mestre (`robozinho-dos-momozis-prompt.md`, que desde a v11 traz só a doutrina editorial), atualizadas em 16/11/2026 para o fluxo atual (onde um script passou a fazer o procedimento, o texto aponta o script). **§R:** os ramos de exceção da `ROTINA.md`, que ela aponta só quando o caso ocorre. Passos da ROTINA (16/11/2026): 1 = âncora (`work/inicio.py`); 2 = conferência anti-duplicata e coleta (coletores + `work/aguardar_coleta.py`); 3 = julgamento; 4–5 = Write do `/tmp/execucao.json` + `work/montar_email.py` + Read do e-mail; 6 = `create_draft`; 7–8 = conferência do rascunho, `work/finalizar.sh` e notificação. Onde algo aqui divergir da ROTINA ou do ledger, valem eles (o ledger acima de todos).

## 0. Pré-requisitos

- Ancoragem de data, resumo do ledger, reconciliação e anti-duplicata: ROTINA passos 1–2 (o `inicio.py` lê o estado e o ledger; o orquestrador não os lê em JSON). **Em conflito entre este documento e o ledger, o ledger vence** — ele é a memória empírica; este é a doutrina (ver Seção 16).
- Ao validar data por leitura web, perguntar de forma **neutra** ("qual data aparece na página?") — nunca sugerir a data esperada, para não induzir a confirmação.
- **PDF/OCR:** skill `pdf` para editais e anexos. Gerar PDF da newsletter e usar Canva **não fazem parte da rotina** — só sob pedido expresso.
- **DOU:** rotas web diretas bloqueadas (Seção 6). INLABS só com credenciais; APP DOU é contingência humana, não executável.
- **Autonomia total:** nunca pausar para pedir confirmação; diante de falha, fallback e seguir. **Sucesso = rascunho criado (ou duplicata legítima detectada) + histórico atualizado.** A execução agendada começa do zero: tudo o que a newsletter precisa está em arquivos do repositório.

## 4. Histórico e não duplicidade

- **Gravação: sempre pelo helper** (`work/Update-Historico.py`, chamado pelo `work/finalizar.sh` no passo 7), a partir do **arquivo** da execução — o `/tmp/execucao.resolvido.json` que o `montar_email.py` grava (ou o `/tmp/execucao.json`, se não houver resolvido mais novo), nunca JSON inline. Em tempo de execução não se lê o histórico nem o estado: a repetição chega marcada pelos scripts — e nunca se conclui "não existe edição do dia X" a partir de leitura truncada.
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

- **Tipo inexistente ou sem a ferramenta** → relance com `subagent_type: "general-purpose"` e `model` `haiku` (gmail) ou `sonnet` (jota, concursos), o mesmo prompt da ROTINA e, no fim dele, o contrato que o agente próprio traria: *"Você só lê; nunca cria, edita ou envia e-mail. Devolva evidência (título, data visível, URL), liste item a item, relate o que tentou — inclusive o que voltou vazio ou com erro — e nunca conclua ausência de novidade."*
- **Negado pelo classificador** → não contorne nem execute o coletor à mão: confira com `diff` o `/tmp/coletor-X.md` contra `work/prompts/coletor-X.md` (só a janela e os dados do ledger podem diferir) e relance o **mesmo** `Agent` citando a conferência. Negado de novo → `errors`, quadro de pendências no lugar das seções daquele coletor e aviso na notificação.
- **Relatório incompleto** (totais sem itens, item sem horário ou sem a URL que a fonte tinha) → `SendMessage` (ToolSearch `select:SendMessage`) ao mesmo agente, pedindo só o que falta.
- **Coletor Gmail ou JOTA vazio em dia útil** → refaça só as buscas dele (`search_threads`, já carregado) com o `after:` de data do passo 1 e filtre pelo horário interno.
- Falha recorrente de um coletor → registre no ledger (`fontes` ou pendência); promover `haiku` → `sonnet` no frontmatter é decisão a tomar com evidência de várias execuções.

### R4. Script do passo 2 ainda rodando ou sem saída

`aguardar_coleta.py` espera até 240 s contados do **disparo** do passo 1, não da chamada: como os coletores rodam antes dele, em geral esse teto já passou e ele só confere (5 s) — por isso um `--teto` fixo mais tarde não esperaria nada. A linha `== <script>.py (… — AINDA RODANDO após 240 s: saída parcial abaixo; a fonte fica sem status)` quer dizer que o script não terminou. Espere por ele **numa mensagem própria, antes do Write** do `/tmp/execucao.json` (a dos WebSearch de fallback, se houver: os ids e as linhas `ERRO` dele só servem se você os vir antes de julgar), com **um** Bash de `timeout: 600000`:

```
python3 - <<'FIM'
import json, os, subprocess, sys, time
from datetime import datetime
p = os.path.join(os.environ.get("ROBOZINHO_TMP", "/tmp"), "passo2-disparo.json")
t0 = datetime.fromisoformat(json.load(open(p, encoding="utf-8"))["disparado_em"]).timestamp()
teto = int(time.time() - t0) + 240          # o teto conta do disparo: decorrido + mais 4 min a partir de agora
subprocess.run([sys.executable, "work/aguardar_coleta.py", "--teto", str(teto)])
FIM
```

A saída é a do passo 2 (processo morto sem resultado é rodado de novo ali); a linha `SOURCE_STATUS` dela substitui a anterior.
- **Terminou** → julgue com essa saída e cite os `ref` dele normalmente.
- **Ainda rodando** → as fontes dele vão como `falha` em `source_status` e em `errors` (`coleta_web`: `congresso_ultimas_leis`, `congresso_mpvs`, `conjur`, `migalhas`; `informativos`: `informativos_docs`; `versiculo`: `youversion`, `dailyverses`, e o versículo segue pela §R5), nenhum `ref` dele é citado (o montador recusaria o id sem evidência) e a lacuna vai ao leitor em `email.limitacoes` (ex.: "Informativos do STF e do STJ não lidos nesta execução: a coleta não terminou a tempo; voltam na próxima edição"). Seção do centro da edição vazia sem aviso é falso negativo. Se o script terminar entre o Write e o montador, o montador troca o status (`AVISO: source_status: vale o do script`); a limitação continua verdadeira para esta edição.

`rodado aqui (sem disparo do inicio.py)` não é falha: o disparo estava desligado (`--sem-disparo`, `ROBOZINHO_DISPARO=0`) ou foi perdido, e o script rodou ali.

### R5. Versículo pelo fallback de WebSearch

Só com o texto do dia, a referência e a data **visíveis** na página (nunca de memória, nunca do resumo do buscador sem a página datada). O `versiculo.py` sempre grava `/tmp/versiculo.json` (também com `ok: false`) e você não o leu: o Write pode recusá-lo (a ferramenta recusa sobrescrever arquivo existente não lido). Grave por **Bash**, na mensagem do Write do `/tmp/execucao.json`, **antes** do Bash do montador, rotulando a fonte REAL. O script troca só os campos do versículo; `tentativas` e `source_status` continuam os do `versiculo.py`:

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
1. `list_drafts` com `subject:"<ASSUNTO>"` (sem `larger:`) e `search_threads` com `subject:"<ASSUNTO>" in:sent` (sem `larger:`), numa mensagem.
2. **Rascunho achado** (menor que o esperado): se a próxima varredura do Apps Script (:13, :28, :43, :58) estiver a mais de 3 min, `delete_draft` (ToolSearch `select:mcp__Gmail__delete_draft`) desse id e `create_draft` de novo com o conteúdo do Read do passo 4–5 (já no contexto; sem ele, Read de `/tmp/email.html` com `allow_large`), na mesma mensagem e na ordem delete → create; varredura perto → não mexa (o Apps Script pode enviar no meio da troca). Nos dois casos, notificação urgente ao dono, com o que foi feito e o id novo (o histórico fica com o `draft_id` antigo — inofensivo: a reconciliação do dia seguinte procura pelo assunto em `in:sent`).
3. **Só a enviada achada** (sem `larger:`): saiu menor que o esperado — notificação urgente; o dono decide a errata (pendência `errata_AAAA_MM_DD` na próxima execução).
4. **Nada achado**: o rascunho sumiu sem envio — notificação urgente; a próxima execução detecta pelo anti-duplicata.

### R7. Edição extra (a pedido do dono)

`python3 work/inicio.py --extra` no lugar do passo 1: `execution_id` `AAAA-MM-DD-extra`, assunto `Robozinho dos Momozis até Passar - DD/MM/AAAA - Extra`, cabeçalho "Edição extra", Munger com índice + 1, sem o ALERTA de fim de semana; a janela parte do `window_end` da última execução registrada (a diária de hoje, se houver). Daí em diante a ROTINA é a mesma (passos 2–8, o mesmo `finalizar.sh`). `RE-EXECUÇÃO` e `--refazer` valem igual, com o id `-extra`.

### R8. Re-execução com o rascunho apagado (`--refazer`)

A `RE-EXECUÇÃO` manda conferir o rascunho e a enviada de hoje. Os dois vazios (o dono apagou o rascunho sem envio) → `python3 work/inicio.py --refazer` reabre a janela original e ignora o registro de hoje na deduplicação; siga a ROTINA a partir do passo 1. O passo 7 substitui o registro de hoje; os `ledger_updates` são reaplicados e os contadores, não.

### R9. `PUSH: FALHOU`

O `finalizar.sh` já tentou 5 vezes e, se a `main` andou no remoto, reaplicou o helper uma vez sobre a `origin/main` (sem rebase textual dos JSON). A linha `ESTADO:` aponta a cópia do estado do dia (`/tmp/robozinho-estado-backup-<exec>.tar.gz`) e o commit local. Diga isso na notificação: a cópia vive só nesta sessão, e sem o push a próxima execução não conhece a edição de hoje (o `inicio.py` acusará `dia útil sem execução registrada` e o passo 2 procurará a edição em `in:sent`).
