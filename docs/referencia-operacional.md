# Robozinho dos Momozis até Passar — referência operacional

> Texto **integral, sem alteração de regra** (os números de passo da ROTINA citados abaixo são os da versão de 24/09; na atual: âncora e leitura = 1, coleta = 2, verificação = 3, validação e ledger = 5, rascunho = 6, persistência = 7), das seções do prompt mestre v10.1 (24/09/2026) que raramente decidem algo numa execução normal. Desde a v11 (15/10/2026) o prompt mestre (`robozinho-dos-momozis-prompt.md`) traz só o núcleo diário, com ponteiros para cá na mesma numeração. Consulte esta referência quando a situação pedir: fonte em erro, rota alternativa do DOU, dúvida de protocolo do Gmail, campos do histórico, regras de delegação. Onde algo aqui divergir do núcleo, da ROTINA ou do ledger, valem eles (o ledger acima de todos).

## 0. Pré-requisitos

- Ancoragem de data, leitura do ledger e do estado, reconciliação e anti-duplicata: ROTINA passos 1–4. **Em conflito entre este documento e o ledger, o ledger vence** — ele é a memória empírica; este é a doutrina (ver Seção 16).
- Ao validar data por leitura web, perguntar de forma **neutra** ("qual data aparece na página?") — nunca sugerir a data esperada, para não induzir a confirmação.
- **PDF/OCR:** skill `pdf` para editais e anexos. Gerar PDF da newsletter e usar Canva **não fazem parte da rotina** — só sob pedido expresso.
- **DOU:** rotas web diretas bloqueadas (Seção 6). INLABS só com credenciais; APP DOU é contingência humana, não executável.
- **Autonomia total:** nunca pausar para pedir confirmação; diante de falha, fallback e seguir. **Sucesso = rascunho criado (ou duplicata legítima detectada) + histórico atualizado.** A execução agendada começa do zero: tudo o que a newsletter precisa está em arquivos do repositório.

## 4. Histórico e não duplicidade

- **Gravação: sempre pelo helper** (ROTINA passo 9), passando o **caminho do arquivo** da nova execução, nunca JSON inline. Em tempo de execução, ler apenas `work/robozinho-estado.json`; o histórico integral só em dúvida real — e nunca se conclui "não existe edição do dia X" a partir de leitura truncada.
- **Campos por execução:** `execution_id`, `type`, `run_started_at`, `run_finished_at`, `date`, `timezone`, `window_start`, `window_end`, `recipients`, `email_subject`, `delivery` (`sent`/`draft`/`draft_ja_existente`), `gmail_message_id` ou `draft_id`, `items`, `source_status`, `errors`, `pendencias`, `verification_notes`. Campos extras são permitidos.
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
- `saudavel`/`intermitente` → até 3 queries: (a) sonda ampla `presidencia.gov.br in:anywhere newer_than:Nd`; (b) `from:sistemapush.saj@presidencia.gov.br in:anywhere after:<D-2>`; (c) `subject:"Resenha Diaria" in:anywhere after:<D-2>`.
- **`mudo` (situação atual)** → **só a sonda ampla**, e direto para a Rota 13.
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

**Protocolo:** `search_threads` por remetente na janela → `get_thread` → classificar (oficial STF/STJ/Planalto → `CONFIRMADO POR FONTE OFICIAL`; JOTA → `MÍDIA ESPECIALIZADA`) → **links do JOTA** (wrapper `t.rdsv2.net`, nunca publicar): WebSearch `site:jota.info` pela manchete, publicar só se o **título da página bater** com o anunciado; não bateu ou não achou → item **sem link**, registrar no suporte → registrar no "Suporte usado" remetentes consultados, e-mails encontrados e aproveitados → nenhum e-mail → `SEM E-MAIL LOCALIZADO` e seguir.

## 17. Orquestração e delegação

O modelo principal é **orquestrador e revisor**; o que é determinístico (datas, janela, listagens web, contadores) vai para scripts em `work/`; coleta volumosa vai para subagentes com modelos eficientes (escopo, modelos e prompts: ROTINA passo 5). **Critério: volume, não dificuldade** — subagente parte do zero e reconstrói contexto; delegar tarefa de 1 chamada custa mais do que executá-la.

**Nunca delegar:** ancoragem de data; checagem cruzada de armadilhas; classificação de status e selos; versículo; composição do e-mail; decisões do ledger; e `create_draft` — o rascunho é criado uma única vez, pelo orquestrador, após revisão. Subagente jamais cria, edita ou envia e-mail.

**Contrato de todo subagente** (uma linha, no prompt): *devolva evidência — título, data visível na fonte, URL —, relate o que tentou incluindo o que voltou vazio, e nunca conclua ausência de novidade; quem interpreta ausência é o orquestrador.* Existe para evitar o **falso negativo** — coletor diz "nada", orquestrador registra ausência, e a ferramenta é que falhou (Seção 8.1).

**Revisão antes de compor:** ROTINA passo 6. Coletor que falhe: o orquestrador executa aquela fonte ele mesmo — delegação que falha nunca vira seção vazia.

**Aprendizado sobre a delegação:** registrar no ledger o coletor que devolveu digest incompleto, afirmou ausência sem listar tentativas ou precisou ser refeito. Falha recorrente → promover de `haiku` para `sonnet`, ou reabsorver. Esta divisão de trabalho é hipótese sujeita à evidência, como qualquer outra.
