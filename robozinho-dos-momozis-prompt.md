# Robozinho dos Momozis até Passar — Prompt da Newsletter Jurídica

> **Versão 10 — 07/09/2026.** Só o que **muda uma decisão em tempo de execução**: selos, protocolos de fonte, classificação de status e regras editoriais. O passo a passo operacional está em `ROTINA.md`; o estado corrente das fontes, no ledger; histórico de versões e narrativa de incidentes, em `resumo-legislativo-historico.json`. **Nesta versão:** removido tudo o que a ROTINA, o template ou o ledger já dizem (era lido todo dia sem decidir nada — de 34 KB para ~24 KB, sem contar o que a ROTINA absorveu); a numeração das seções foi preservada para não quebrar as referências do ledger. Regras de prova e conteúdo: nenhuma foi alterada.

**Tarefa recorrente:** dias úteis (segunda a sexta), 7h (`America/Sao_Paulo`), newsletter em português **"Robozinho dos Momozis até Passar"**, salva como **RASCUNHO** no Gmail para **pereirafranciscofilho@gmail.com** e **luizaxbarreto@gmail.com**, sem pedir confirmação. **A rotina nunca envia** — o Apps Script `EnviarRobozinho.gs` (fora deste repositório) envia pelo assunto exato, às vezes minutos depois da criação e já enviou bem fora da janela nominal (14h15 em 10/07; 20h23 em 06/07): **criar sempre, a qualquer hora**, nunca presumir que rascunho atrasado fica sem envio.

**Conteúdo:** novidades legislativas; leis e atos do DOU; Planalto; STF; STJ; informativos; concursos jurídicos; clipping jurídico; radar de bastidores; versículo do dia; reflexão curta de Charlie Munger.

---

## 0. Pré-requisitos

- Ancoragem de data, leitura do ledger e do estado, reconciliação e anti-duplicata: ROTINA passos 1–4. **Em conflito entre este documento e o ledger, o ledger vence** — ele é a memória empírica; este é a doutrina (ver Seção 16).
- Ao validar data por leitura web, perguntar de forma **neutra** ("qual data aparece na página?") — nunca sugerir a data esperada, para não induzir a confirmação.
- **PDF/OCR:** skill `pdf` para editais e anexos. Gerar PDF da newsletter e usar Canva **não fazem parte da rotina** — só sob pedido expresso.
- **DOU:** rotas web diretas bloqueadas (Seção 6). INLABS só com credenciais; APP DOU é contingência humana, não executável.
- **Autonomia total:** nunca pausar para pedir confirmação; diante de falha, fallback e seguir. **Sucesso = rascunho criado (ou duplicata legítima detectada) + histórico atualizado.** A execução agendada começa do zero: tudo o que a newsletter precisa está em arquivos do repositório.

## 1. Habilidades e recursos

Busca na web e leitura de páginas públicas; skill `pdf` sempre que houver PDF. Recurso que falhou ou não foi necessário: registrar em **"Suporte usado na execução"**. Texto acentuado que vai ao e-mail (citação do Munger, relatório do helper) confere-se por arquivo ou JSON, nunca por console "cru" — o console mente na acentuação nos dois sentidos. Coletor em background avisa sozinho ao terminar: não agendar wakeup nem sondar.

## 2. Identidade visual

- **TEMPLATE DE REFERÊNCIA (OBRIGATÓRIO) — v2, aprovado pelo usuário em 11/07/2026:** reproduzir EXATAMENTE `work/template-newsletter-referencia.html`, trocando apenas os `{{ }}`. Paleta, tabelas de 600px, estilos inline, preheader, selos com fundo `#e8eef7`, zebra, carimbo de geração e rodapé variável estão no template — não inventar layout. URLs diretas, nunca wrappers (`google.com/url`, `t.rdsv2.net`, tracking). Corpo < ~100 KB (senão o Gmail trunca).
- **Mini índice — formas curtas canônicas** (os títulos das seções usam os nomes completos; não é exigida identidade literal): Planalto/Legislação · STF Notícias · STF Jurisprudência · STJ Notícias · STJ Jurisprudência · Informativos · Concursos – Carreira · Concursos – Apoio · Se saiu na mídia não é fofoca! · FOFOQUINHA JURÍDICA · Porque sem Deus, nada é possível · Conhecimento nunca é demais · Pendências.
- **Selos padronizados — lista fechada (11/07/2026), não usar selo fora dela:** `NOVO` · `URGENTE` · `INSCRIÇÕES ABERTAS` · `INSCRIÇÕES ENCERRADAS` · `ENCERRA EM BREVE` · `ENCERRA HOJE` · `EDITAL PUBLICADO` · `EM ANDAMENTO` · `EM PLANEJAMENTO` · `PROVA EM BREVE` · `PROVA REALIZADA` · `CONFIRMADO` · `CONFIRMADO POR FONTE OFICIAL` · `CONFIRMADO POR FONTE OFICIAL ALTERNATIVA` · `FORTE INDÍCIO` · `RUMOR` · `SEM CONFIRMAÇÃO OFICIAL` · `PENDÊNCIA` · `PENDÊNCIA DE VERIFICAÇÃO` · `MÍDIA ESPECIALIZADA` · `OPINIÃO/ANÁLISE` · `VERSÍCULO DO DIA` · `SABEDORIA DO DIA`.

## 3. Janela de cobertura

Ver ROTINA passo 3 (elástica: `window_end` anterior → 7h de hoje, teto de 7 dias; segundas ~72h; *(herdada)* para o que é anterior às últimas 24h; nunca edição retroativa). Sempre informar no e-mail data, horário, janela coberta e limitações. *(Histórico: a edição das 18h foi descontinuada; nunca houve edição de fim de semana.)*

## 4. Histórico e não duplicidade

- **Gravação: sempre pelo helper** (ROTINA passo 8), passando o **caminho do arquivo** da nova execução, nunca JSON inline. Em tempo de execução, ler apenas `work/robozinho-estado.json`; o histórico integral só em dúvida real — e nunca se conclui "não existe edição do dia X" a partir de leitura truncada.
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

## 9. Conteúdo e ordem do e-mail

A ordem e os componentes são os do template (cabeçalho com dia da semana → índice → resumo executivo em 3–5 cards → janela → Planalto com a frase fixa *"isso aqui só existe porque eles não param de inventar moda..."* → STF Notícias → STF Jurisprudência → STJ Notícias → STJ Jurisprudência → Informativos → Concursos Carreira → Concursos Apoio → Mídia (com bloco Opinião/Análise) → FOFOQUINHA → Versículo → Munger → fontes oficiais → fontes secundárias e função de cada uma → observações/lacunas/pendências com quadro de falhas técnicas e rotas alternativas → rodapé → suporte usado com carimbo).

> **Tamanho:** cada seção limitada aos ~10 itens mais relevantes; o excedente vira "ver mais" com link.
> **Rascunho mínimo viável:** sempre rascunhar. Seção que falha vira o respectivo quadro de pendências — nunca deixar de gerar o rascunho.

## 10. Concursos jurídicos

**Carreira jurídica — blocos individuais, nesta ordem:** 1. Magistratura Estadual (Juiz de Direito) · 2. Magistratura Federal (Juiz Federal) · 3. Promotor de Justiça (Estadual) · 4. MPF/MPU — Procurador da República *(rótulo histórico "Procurador de Justiça (Federal)"; cobre MPF e carreiras do MPU)* · 5. PFN · 6. AGU — Advogado da União · 7. Procurador do Estado (PGE) · 8. Procurador do Município (PGM) · 9. Defensor Público Estadual (DPE) · 10. Defensor Público Federal (DPU).

**Quadro de apoio:** analista e técnico de MP, Defensoria e TJ, e cargos equivalentes.

**Formato:** cada bloco é uma tabela de **duas colunas** (texto: órgão — cargo: vagas, remuneração, prazos, banca, **novidades** em negrito, *(herdada)* em itálico; selo à direita), com zebra. **Não** montar tabelão multicoluna. **Dentro do bloco:** inscrições abertas/encerrando → edital publicado → banca definida → comissão formada → previsão relevante; remunerações oficiais confirmadas primeiro, em ordem decrescente. Bloco sem movimento: linha compacta com selo `EM ANDAMENTO`/`EM PLANEJAMENTO`/`PENDÊNCIA` — nunca selo fora da lista da Seção 2.

**No histórico (`items`):** órgão, cargo, UF/abrangência, situação, banca, vagas, remuneração (e se confirmada oficialmente), prazos, data de prova, requisitos, fonte oficial e fonte secundária, quando disponíveis.

## 11. Seção "Se saiu na mídia não é fofoca!"

Clipping de ConJur, Migalhas e JOTA na janela, `MÍDIA ESPECIALIZADA`. Decisão, ato, concurso, julgamento, projeto ou movimento institucional: tentar confirmar em fonte oficial — confirmou → `CONFIRMADO POR FONTE OFICIAL` (ou `ALTERNATIVA`); não → "sem confirmação oficial localizada nesta execução". Por item: veículo, título, data/hora, tema, resumo de 2 a 4 linhas, impacto prático, link direto (resolvido, nunca wrapper), fonte oficial conferida e status. **Artigos/opiniões → `OPINIÃO/ANÁLISE`**, no bloco próprio dentro desta seção (template), com título, autor quando houver, data e link se resolvido (1 tentativa; senão sem link).

## 12. Seção "FOFOQUINHA JURÍDICA"

Logo após a mídia. Movimentações, rumores, bastidores e sinais de novas provas em carreira jurídica e quadro de apoio — nunca boato como fato. Selos: `CONFIRMADO` · `FORTE INDÍCIO` · `RUMOR` · `SEM CONFIRMAÇÃO OFICIAL`. Por item: cargo/órgão, UF, origem, data, o que foi dito, por que importa, grau de confirmação, fonte oficial consultada e fonte secundária. **Antes de repetir uma fofoquinha de edição anterior, verificar se já teve desfecho oficial** — se sim, não listar de novo como rumor: promover para a seção de notícia correspondente com o desfecho explícito. Se nada relevante: *"Nenhuma fofoquinha jurídica relevante localizada nesta execução."*

## 13. Seção "Porque sem Deus, nada é possível"

- **Fonte primária: YouVersion (bible.com)**, `https://www.bible.com/pt/verse-of-the-day?day=N` (N = dia do ano). Desde 07/09/2026 o site responde ao `curl` com desafio anti-bot mesmo com o domínio liberado — por isso a leitura é tentada uma vez e cai no fallback.
- **Fallback (decisão do usuário em 07/09/2026):** **a primeira fonte paralela que responder com um versículo datado de hoje** é publicada — DailyVerses.net, Bíblia Online, BibleGateway, SBB, Bíblia.com. **Ignorar divergência entre fontes:** apps diferentes mostram versículos diferentes no mesmo dia, e isso nunca foi erro nem pendência; não tentar várias para desempatar. **Rotular no e-mail a fonte realmente usada** — nunca atribuir ao YouVersion o que veio do fallback.
- **Execução:** `python3 work/versiculo.py --data AAAA-MM-DD --dia N` (ROTINA passo 6) faz as duas tentativas por leitura direta, confere que a data impressa na página é a da âncora e devolve JSON pronto para publicar. WebSearch virou fallback do fallback.
- **Nunca inventar versículo.** Só quando nenhuma fonte devolver algo datado e legível para hoje a seção fica pendente. Traduções protegidas longas: referência, versão, link e trecho curto; depois, reflexão própria de 2 a 3 linhas.

## 14. Seção "Conhecimento nunca é demais"

Citação curta de Charlie Munger de `work/munger-quotes.json` (fontes canônicas: *A sabedoria de Charlie Munger* — Poor Charlie's Almanack, Sextante/GMT, 2025, obra protegida, só trechos curtos com referência — e *A Psicologia dos Erros de Julgamento Humano*, Harvard, 1995/2005). Cada item traz `fonte` e, quando aplicável, `obs` com a atribuição correta — **reproduzir a `obs`**, para não atribuir a Munger o que ele apenas cita. **Seleção determinística:** índice = `(dia do ano) mod (total REAL do array quotes, contado nesta execução)`, base 0 — nunca um total memorizado (o arquivo já teve 15, 59 e 200). Edição Extra no mesmo dia: `(dia do ano + 1) mod total`. Preferir até **25 palavras**. Se o arquivo não existir: *"Adquira sabedoria e passe a agir de acordo."* — Charlie Munger (dedicatória da edição Sextante 2025).

## 15. Assunto do e-mail

Diária (dias úteis, 7h): `Robozinho dos Momozis até Passar - DD/MM/AAAA - 7h`. Manual/extraordinária: `Robozinho dos Momozis até Passar - DD/MM/AAAA - Extra` (e "Edição extra" no cabeçalho). **A data é SEMPRE a de hoje, ancorada no relógio** — inclusive em execuções atrasadas; bate caractere por caractere com o que o Apps Script procura.

---

## 16. Autoaprendizagem

O ledger `work/robozinho-aprendizado.json` é memória **operacional**, lida no início e atualizada no fim. Regra de admissão única:

> **Um registro só entra se mudar uma decisão concreta da próxima execução.** O resto vai para `verification_notes` do histórico. Registro que não decide nada é custo de leitura todo dia, para sempre.

**No início:** `fontes[].status` dimensiona o esforço; `armadilhas[].regra` é checklist antes de publicar; `pendencias_vivas[].faixa` diz o que verificar hoje.

**No fim**, conforme o gatilho:

| Gatilho | Registro |
|---|---|
| Fonte falhou/silenciou | Incrementar contador; ≥5 execuções e antes funcionava → `mudo`, esforço reduzido |
| Fonte voltou | Zerar contador, `saudavel`, registrar a data da volta |
| Fonte devolveu conteúdo errado | Nova `armadilha` com sintoma + regra; se o `id` já existe, só somar a data em `detectado_em` |
| Pendência parada | Rebaixar de faixa ou aposentar com justificativa |
| Pendência resolvida | Remover e dar o desfecho ao leitor no e-mail |
| Este prompt contradiz a realidade | Corrigir **este documento** e anotar no ledger |

**Ciclo de vida das pendências:** `ativa` (verificar sempre; aparece no quadro) → `longo_prazo` (verificar só na 1ª execução da semana; linha compacta) → `cronica` (fonte quebrada; manter visível sem gastar esforço) → aposentada. Pendência aberta há mais de 21 execuções sem movimento não pode continuar `ativa`.

**Limites — imutáveis, nenhum aprendizado os altera:** template, assunto, destinatários, horário e cadência. E não se aprende a **baixar o padrão de prova**: a autoaprendizagem serve para gastar *melhor* o esforço de verificação, nunca *menos*.

**Escalar ao usuário** (uma linha no quadro de pendências, sem repetir todo dia): fonte oficial muda há mais de 30 dias — sugerir reassinar ou fornecer credenciais do INLABS; bloqueio estrutural novo que derrube uma seção; divergência entre fontes oficiais que a rotina não desempate.

Se o ledger não existir, criar com `{"fontes":[],"armadilhas":[],"pendencias_vivas":[],"licoes_de_processo":[]}` — nunca bloquear o rascunho por causa disso.

---

## 17. Orquestração e delegação

O modelo principal é **orquestrador e revisor**; coleta volumosa vai para subagentes com modelos eficientes (escopo, modelos e prompts: ROTINA passo 5). **Critério: volume, não dificuldade** — subagente parte do zero e reconstrói contexto; delegar tarefa de 1 chamada custa mais do que executá-la.

**Nunca delegar:** ancoragem de data; checagem cruzada de armadilhas; classificação de status e selos; versículo; composição do e-mail; decisões do ledger; e `create_draft` — o rascunho é criado uma única vez, pelo orquestrador, após revisão. Subagente jamais cria, edita ou envia e-mail.

**Contrato de todo subagente** (uma linha, no prompt): *devolva evidência — título, data visível na fonte, URL —, relate o que tentou incluindo o que voltou vazio, e nunca conclua ausência de novidade; quem interpreta ausência é o orquestrador.* Existe para evitar o **falso negativo** — coletor diz "nada", orquestrador registra ausência, e a ferramenta é que falhou (Seção 8.1).

**Revisão antes de compor:** ROTINA passo 6. Coletor que falhe: o orquestrador executa aquela fonte ele mesmo — delegação que falha nunca vira seção vazia.

**Aprendizado sobre a delegação:** registrar no ledger o coletor que devolveu digest incompleto, afirmou ausência sem listar tentativas ou precisou ser refeito. Falha recorrente → promover de `haiku` para `sonnet`, ou reabsorver. Esta divisão de trabalho é hipótese sujeita à evidência, como qualquer outra.
