# Robozinho dos Momozis até Passar — Prompt da Newsletter Jurídica

> **Versão 14 — 21/11/2026:** decisões do dono — alvo principal é a eficiência na finalidade e na busca (não perder concurso bom nem atualização de jurisprudência e de leis), com o gasto médio mantido; orquestrador no Fable; quadro de apoio só Sul e Sudeste com MG (SP, RJ, MG, ES, PR, SC, RS) ou nacional, carreiras finais em todo o país (`work/escopo.py`); ementa das leis inteira; pendência interna não vai ao leitor; o Apps Script não muda (HTML completo no corpo do rascunho); push só na `main`; sem aviso de falha fora da sessão. Código: banca FGV com a listagem inteira e vínculo por `banca_slug`; página oficial de todo concurso lida todo dia; LEGIN (decretos e demais atos do DOU) no `coleta_web.py`, com ConJur e Migalhas paginados e índice por relevância para prova; Jurisprudência em Teses do STJ; mudança de dado por migração (`work/migracoes/`); gravação todas-ou-nenhuma, trava de sanidade e custo em US$; uma notificação só, depois da gravação.
>
> **Versão 13 — 16/11/2026:** este documento fica só com a doutrina editorial; o procedimento está na `ROTINA.md` (6 turnos) e nos ramos raros da `docs/referencia-operacional.md` (§R). O que era julgamento mecânico passou a script: selo de concurso por data e carimbo da banca (`work/selos.py`, `work/bancas.py`), feriados (`work/feriados.py`), informativos completos com o resumo oficial de cada julgado (STF) e a tese de cada tema (RG em Pauta) — o resumo do Informativo não é a tese fixada, descarte do repetido certo nas seções de apoio, `impacto` ("Para a prova") na legislação, Munger com lição sem aspas, edição Extra (`work/inicio.py --extra`). O e-mail vai do montador ao rascunho por arquivo, com sentinela no fim do corpo e conferência de tamanho depois do `create_draft`.
>
> **Versão 12 — 11/11/2026:** o orquestrador deixou de compor HTML. Ele escreve o julgamento em `/tmp/execucao.json` e o `work/montar_email.py` monta o e-mail inteiro (template v4), citando por `ref` o que os scripts coletaram; a banca oficial FGV passou a ser lida por script (`work/bancas.py`). Ênfase editorial do dono: **concursos, legislação e informativos** completos; mídia e fofoquinha enxutas.
>
> **Versão 11.1 — 04/11/2026:** este documento passou a ser lido **sob demanda** — as regras que decidem algo todo dia estão condensadas em `ROTINA.md` ("Regras editoriais") e o ledger chega resumido pelo `work/inicio.py`. Concursos (§10) ganharam rodízio de reverificação e descoberta diária de concursos novos; a seção passou a ser gerada por script (hoje, pelo `work/montar_email.py`, a partir do registro do ledger).
>
> **Versão 11 — 15/10/2026 (núcleo diário).** Só o que **decide algo em tempo de execução**: selos, classificação de status e regras editoriais. O detalhe operacional que raramente decide (rotas web do DOU, protocolo de busca no Gmail, fontes mínimas, contingência por fonte, campos do histórico, delegação) foi movido **sem alteração de regra** para `docs/referencia-operacional.md`, com a mesma numeração — consulte quando a situação pedir. O passo a passo está em `ROTINA.md`; o estado das fontes e dos concursos, no ledger. **Versão 10.1 — 24/09/2026** e anteriores: histórico em `resumo-legislativo-historico.json`.

**Tarefa recorrente:** dias úteis (segunda a sexta), 7h (`America/Sao_Paulo`), newsletter em português **"Robozinho dos Momozis até Passar"**, salva como **RASCUNHO** no Gmail para **pereirafranciscofilho@gmail.com** e **luizaxbarreto@gmail.com**, sem pedir confirmação. **A rotina nunca envia** — o Apps Script `EnviarRobozinho.gs` (fora deste repositório) envia pelo assunto exato, às vezes minutos depois da criação e já enviou bem fora da janela nominal (14h15 em 10/07; 20h23 em 06/07): **criar sempre, a qualquer hora**, nunca presumir que rascunho atrasado fica sem envio.

**Conteúdo:** novidades legislativas; leis e atos do DOU; Planalto; STF; STJ; informativos; concursos jurídicos; clipping jurídico; radar de bastidores; versículo do dia; reflexão curta de Charlie Munger.

## 0. Pré-requisitos

- **Em conflito entre este documento e o ledger, o ledger vence** — ele é a memória empírica; este é a doutrina (Seção 16).
- Ao validar data por leitura web, perguntar de forma **neutra** ("qual data aparece na página?") — nunca sugerir a data esperada, para não induzir a confirmação.
- **Autonomia total:** nunca pausar para pedir confirmação; diante de falha, fallback e seguir. **Sucesso = rascunho criado (ou duplicata legítima detectada) + histórico atualizado.**
- PDF/OCR, DOU/INLABS e o que não faz parte da rotina: referência §0.

## 1. Habilidades e recursos

**"Suporte usado na execução"** (rodapé) é escrito pelo `work/montar_email.py` para o leitor, em linguagem simples: o que foi usado e as fontes que falharam (`Fontes que falharam nesta execução: …`, só as com status `falha`), sem códigos http nem nomes de script. O detalhe técnico — rotas tentadas, códigos, scripts, recurso que falhou ou não foi necessário — fica em `errors` e `verification_notes` do histórico. Texto acentuado que vai ao e-mail confere-se por arquivo ou JSON, nunca por console "cru" — o console mente na acentuação nos dois sentidos.

## 2. Identidade visual

- **TEMPLATE v4 (11/11/2026, sobre a v3 aprovada em 24/09/2026):** o layout vive no `work/montar_email.py`, que gera o HTML inteiro — o orquestrador não escreve HTML nem inventa layout. Mesma paleta, largura fluida de 600px, estilos inline, preheader, selos, carimbo de geração e rodapé variável da v3; na v4 os selos não quebram de linha, Concursos passou a uma coluna (órgão — cargo em negrito + selo, detalhes abaixo, novidades em fundo creme) e o quadro de prazos lista à parte os que só constam de fonte secundária. `work/template-newsletter-referencia.html` é uma amostra gerada, para conferência visual. URLs diretas, nunca wrappers (`google.com/url`, `t.rdsv2.net`, tracking). O Gmail corta a **exibição** perto de 102 KB ("Mensagem cortada", sem perder conteúdo): o montador avisa a partir de 80 KB, com o tamanho por seção, e nunca deixa de gerar o rascunho por tamanho; a alavanca é Concursos (linha compacta dos sem mudança, remoção dos encerrados). No fim do corpo vai uma sentinela invisível (`fim-<execution_id>`) para conferir que a cópia está inteira. O HTML vai completo no corpo do rascunho: o Apps Script de envio não muda (decisão do dono).
- **Mini índice — formas curtas canônicas** (os títulos das seções usam os nomes completos; não é exigida identidade literal): Planalto/Legislação · STF Notícias · STF Jurisprudência · STJ Notícias · STJ Jurisprudência · Informativos · Concursos – Carreira · Concursos – Apoio · Se saiu na mídia não é fofoca! · FOFOQUINHA JURÍDICA · Porque sem Deus, nada é possível · Conhecimento nunca é demais · Pendências.
- **Selos padronizados — lista fechada (11/07/2026), não usar selo fora dela:** `NOVO` · `URGENTE` · `INSCRIÇÕES ABERTAS` · `INSCRIÇÕES ENCERRADAS` · `ENCERRA EM BREVE` · `ENCERRA HOJE` · `EDITAL PUBLICADO` · `EM ANDAMENTO` · `EM PLANEJAMENTO` · `PROVA EM BREVE` · `PROVA REALIZADA` · `CONFIRMADO` · `CONFIRMADO POR FONTE OFICIAL` · `CONFIRMADO POR FONTE OFICIAL ALTERNATIVA` · `FORTE INDÍCIO` · `RUMOR` · `SEM CONFIRMAÇÃO OFICIAL` · `PENDÊNCIA` · `PENDÊNCIA DE VERIFICAÇÃO` · `MÍDIA ESPECIALIZADA` · `OPINIÃO/ANÁLISE` · `VERSÍCULO DO DIA` · `SABEDORIA DO DIA`.

## 3. Janela de cobertura

Ver ROTINA passo 1 (elástica: `window_end` anterior → 7h de hoje, teto de 7 dias; segundas ~72h; *(herdada)* para o que é anterior às últimas 24h; nunca edição retroativa). Sempre informar no e-mail data, horário, janela coberta e limitações. **Feriado** (nacional, ponto facultativo ou da Justiça Federal — Lei 5.010/66, art. 62) não suspende a edição: o `work/feriados.py` os calcula, o montador os cita na linha da janela, e silêncio de Planalto, Câmara, STF e STJ nesses dias é normal. *(Histórico: a edição das 18h foi descontinuada; nunca houve edição de fim de semana.)*

## 4. Histórico e não duplicidade

- **Gravação: sempre pelo helper** (ROTINA), passando o **caminho do arquivo**, nunca JSON inline. Não se lê o histórico nem o estado em execução normal: a repetição chega marcada (`[REPETIDA?~chave]` no `coleta_web.py`; `JA_PUBLICADA` no resolver do JOTA; `REPUBLICADA`/`POSSIVEL_REPETIDA` na validação feita pelo montador, passos 4–5 da ROTINA) e, para a mesma história com outro título, a lista `JA SAIU` (Mídia e Fofoquinha das 2 últimas edições, no fim do `coleta_web.py` e do resolver do JOTA): o mesmo fato só volta como desdobramento dito no título; com desfecho oficial, vira uma frase do item oficial. Atos e informativos se comparam pela identidade (tipo + número), nunca pela semelhança do título. Nas seções de apoio (Mídia, Opinião, Fofoquinha), o repetido certo — chave já publicada, ou repetida da mesma fonte — sai sozinho e é listado; o resto é aviso para o julgamento. Nunca se conclui "não existe edição do dia X" a partir de leitura truncada.
- **Chave única estável** `fonte|tipo|numero|ano|data`, minúsculas (ex.: `dou|decreto|11999|2026|2026-06-29`). Item que muda de estado (prova marcada → prova realizada; rumor → desfecho) recebe chave nova com o desfecho; nunca reutiliza a chave anterior.
- Campos por execução e por item, arquivamento: referência §4.

## 5. Fontes oficiais mínimas

Legislação federal e DOU; STF; STJ; CNJ, CNMP, TSE e TST quando houver relevância jurídica; CJF, TRFs, TJs, TREs, TRTs, MPs, Defensorias, AGU, DPU, PGFN, Procuradorias e bancas oficiais quando o assunto envolver concurso, edital, remuneração, ato institucional ou jurisprudência setorial. Lista detalhada: referência §5.

## 6. Protocolo obrigatório — DOU, Planalto e leis/atos federais

**Ordem: Gmail primeiro (sonda do PUSH, `from:presidencia.gov.br in:anywhere`, feita pelo coletor Gmail), depois web (Rotas 13, 9 e 15, lidas pelo `coleta_web.py`).** Sem resenha, **não interromper nem esperar intervenção humana**; nunca depender de colagem manual de EML. Se nada confirmar: seção com o quadro de pendências e o aviso `PUSH Planalto não recuperado nesta execução`. Se a sonda voltar a trazer resenha: reclassificar a fonte `saudavel` no ledger e restaurar o protocolo completo (referência §6).

**Status:** Gmail PUSH → `CONFIRMADO POR FONTE OFICIAL`. Rotas 7–11 e 13–15 → `CONFIRMADO POR FONTE OFICIAL ALTERNATIVA`. Só notícia/snippet → `PENDÊNCIA DE VERIFICAÇÃO` ou `SEM CONFIRMAÇÃO OFICIAL`.

**Para cada ato:** tipo, número, data, órgão, ementa, seção do DOU, edição, link oficial, rota de confirmação, impacto ("Para a prova": o que o ato altera; o montador o deduz da ementa quando ela altera código ou lei conhecida) e status. A seção Planalto/Legislação nunca é cortada e a ementa sai inteira. Atos de rotina (crédito orçamentário, LOA, LDO, PPA e lei de matéria PLN, cargos, capital de estatais, acordos de turismo ou serviços aéreos) saem completos, agrupados no fim da seção — nunca omitidos; cooperação jurídica, matéria penal e extradição nunca são rotina. Decretos e demais atos do DOU que chegam antes da resenha vêm da Legislação Informatizada da Câmara (Rotas 9 e 15, lidas pelo `coleta_web.py`: `CONFIRMADO POR FONTE OFICIAL ALTERNATIVA`); o mesmo ato na resenha PUSH é um item só, com o selo do PUSH. Links `planalto.gov.br/ccivil_03/...` podem ser **publicados** como referência mesmo sem fetch.

**Nas pendências, registrar:** se o PUSH retornou e-mail no período e quais rotas foram tentadas (as desabilitadas como `NÃO TENTADA — bloqueio estrutural`). Queries do PUSH e tabela das rotas 1–15: referência §6.

## 7. Fontes complementares

**Regra de ouro:** fonte secundária nunca substitui fonte oficial. Dizer o Direito é apoio secundário (sempre conferir a decisão original); ConJur, Migalhas e JOTA são mídia especializada; cursinhos e portais de concurso servem a concursos e bastidores. Lista completa: referência §7.

## 8. Protocolo geral de contingência

1. Nunca tratar erro técnico, 403, 502, captcha, JavaScript, manutenção, timeout, DNS, bloqueio de ferramenta, página dinâmica, URL não aberta, resultado vazio, snippet isolado ou homepage defasada como ausência de novidade.
2. Fonte principal falhou → `PENDÊNCIA DE VERIFICAÇÃO`, a falha objetiva, as rotas tentadas, o impacto na confiabilidade e a ação para a próxima execução.
3. **Recesso forense (2 a 31/jul; 20/dez a 31/jan):** fluxo reduzido de STF/STJ, prazos suspensos e informativos sem edição nova são **normais** — registrar como "fluxo reduzido de recesso", **não** como pendência ou falha. Continuar consultando (monocráticas, plantão e atos administrativos continuam saindo).

Rotas alternativas por fonte (STF, STJ, ConJur/Migalhas/JOTA) antes de declarar falha final: referência §8.

## 8-A. Gmail — canal primário e de contingência

Papéis: **primário** (PUSH Planalto), **contingência** (STF Push, STJ CodJu — em paralelo com as rotas web), **legislativo** (boletim da Agência Câmara, `boletins@camara.gov.br` — Rota 11 por e-mail: lei nova, MPV, veto e votação em Plenário → `CONFIRMADO POR FONTE OFICIAL ALTERNATIVA`; não substitui o DOU), **editorial** (JOTA, sempre `MÍDIA ESPECIALIZADA`). Oficial STF/STJ/Planalto → `CONFIRMADO POR FONTE OFICIAL`. O CodJu manda dois produtos: o Informativo STJ (número e data do **assunto** do e-mail) e a Jurisprudência em Teses, que vai na seção STJ Jurisprudência ("Jurisprudência em Teses nº N — <tema>"). Os e-mails de informativo trazem só o link: o conteúdo (destaques) vem do documento oficial, baixado e extraído por `work/informativos.py`; sem acesso, publicar número, data e link e dizer que o conteúdo não foi acessível — nunca resumir de memória.

> **JOTA** envia boletins tipicamente entre 10h e 20h: numa execução às 7h não haverá JOTA do dia D (usar D-1); execução atrasada pode encontrar D — usar normalmente. Ausência de JOTA-D não é falha. Fim de semana sem JOTA é normal.

Links do JOTA vêm no wrapper `t.rdsv2.net` — **nunca publicar**: só a URL resolvida pelo `work/resolver_jota.py` cujo título bate com o anunciado (link de descadastro ou preferências nunca é seguido); senão, item sem link (rótulo automático). Remetentes e protocolo de busca: referência §8-A e `work/prompts/`.

## 9. Conteúdo e ordem do e-mail

A ordem e os componentes são os do template (cabeçalho com dia da semana → índice → resumo executivo em 3–5 cards → janela → Planalto com a frase fixa *"isso aqui só existe porque eles não param de inventar moda..."* → STF Notícias → STF Jurisprudência → STJ Notícias → STJ Jurisprudência → Informativos → Concursos Carreira → Concursos Apoio → Mídia (com bloco Opinião/Análise) → FOFOQUINHA → Versículo → Munger → fontes oficiais → fontes secundárias e função de cada uma → observações/lacunas/pendências com quadro de falhas técnicas e rotas alternativas → rodapé → suporte usado com carimbo).

> **Tamanho:** o centro (concursos, legislação, informativos) não tem teto além do bom senso — informativo sai com todos os destaques; a legislação nunca é cortada. O apoio é enxuto: Mídia com cerca de 6 itens (julgado com tese e carreiras primeiro), Opinião/Análise com 3 a 4 ligados ao que importa na edição; o excedente da mídia vira "ver mais" com link.
> **Rascunho mínimo viável:** sempre rascunhar. Seção que falha vira o respectivo quadro de pendências — nunca deixar de gerar o rascunho.

## 10. Concursos jurídicos

**Carreira jurídica — blocos individuais, nesta ordem:** 1. Magistratura Estadual (Juiz de Direito) · 2. Magistratura Federal (Juiz Federal) · 3. Promotor de Justiça (Estadual) · 4. MPF/MPU — Procurador da República *(rótulo histórico "Procurador de Justiça (Federal)"; cobre MPF e carreiras do MPU)* · 5. PFN · 6. AGU — Advogado da União · 7. Procurador do Estado (PGE) · 8. Procurador do Município (PGM) · 9. Defensor Público Estadual (DPE) · 10. Defensor Público Federal (DPU).

**Quadro de apoio:** analista e técnico de MP, Defensoria e TJ, e cargos equivalentes — só com lotação no Sul e no Sudeste, incluindo Minas Gerais (SP, RJ, MG, ES, PR, SC, RS), ou de órgão nacional com vagas nelas (decisão do dono, 20/11/2026; `work/escopo.py`). Carreiras finais: todo o país.

**Formato (gerado pelo `work/montar_email.py` a partir do registro do ledger):** cada bloco tem barra de título e uma linha por concurso, em uma coluna — **órgão — cargo** em negrito com o selo ao lado; abaixo, vagas, remuneração, prazos e banca; *(herdada; verificado em DD/MM)* em itálico; linha nova ou atualizada hoje em fundo creme; zebra. **Não** montar tabelão multicoluna. **Dentro do bloco:** inscrições abertas/encerrando → edital publicado → banca definida → comissão formada → previsão relevante; remunerações oficiais confirmadas primeiro, em ordem decrescente. Bloco sem movimento: linha compacta com selo `EM ANDAMENTO`/`EM PLANEJAMENTO`/`PENDÊNCIA` — nunca selo fora da lista da Seção 2. **Linha compacta (desde 16/11/2026):** a 1ª edição da semana sai completa; de terça a sexta, registro sem mudança (linha, selo ou prazos) desde antes da edição anterior e sem prazo em destaque — a mesma regra do quadro "Prazos no radar" (confirmado em até 30 dias, ou inscrição ou prova a confirmar em até 14) — sai numa linha por bloco, com o selo, a data da última mudança e a inscrição ou prova a confirmar de 15 a 30 dias; `EM PLANEJAMENTO`/`PENDÊNCIA` parado há mais de 15 dias úteis sai compacto todo dia. Registro novo, alterado hoje ou com selo de prazo em curso nunca compacta. Remoção nunca é automática: o `inicio.py` aponta o candidato (todos os prazos confirmados — ou, sem prazo confirmado, todas as datas de secundária — vencidos há mais de 30 dias, sem etapa futura) e o orquestrador decide, com desfecho, que o montador mostra no bloco no dia ("Saiu do acompanhamento"). Linha reescrita sem fato novo para o leitor sai com `movimento: false` (sem "Atualizado hoje").

**Cobertura (desde 04/11/2026):** o coletor de concursos trabalha em três frentes por dia — (A) prazos e pendências; (B) **rodízio** dos 3 registros sem verificação há mais tempo (≥ 7 dias úteis), para nenhum ficar esquecido; (C) **descoberta** de concursos novos, abertos ou que vão abrir, uma carreira por dia útil e varredura geral às segundas. **Só vira `NOVO`** (e entra no registro, passos 4–5 da ROTINA) o que tem URL individual, data visível e fato duro datado no ano (inscrições abertas, edital publicado, banca definida; comissão ou autorização só com o número do ato); o resto é `RADAR`, sem registro. **Banca oficial (desde 11/11/2026):** a página da FGV de cada concurso (situação, arquivos datados — inclusive retificações —, trechos do edital) é lida por `work/bancas.py` no passo 1 — é fonte oficial, promove selo, confirma prazo e acusa `DIVERGE DO REGISTRO`; o coletor não gasta busca com o que ela cobre, e `verificado_em`/`fonte` dos lidos nela são carimbados sozinhos. Desde 21/11 a listagem inteira dos concursos em andamento é lida, e a página só cobre o registro vinculado a ela pelo `banca_slug` (sem ele, pela `fonte`): o orquestrador grava o vínculo dos `CANDIDATO` conferido o ciclo e avalia no mesmo dia, como `NOVO`, o concurso em andamento sem registro (`MOVIMENTO sem registro`). **Selo por data:** dentro da família `INSCRIÇÕES ABERTAS` → `ENCERRA EM BREVE` (até 7 dias) → `ENCERRA HOJE` → `INSCRIÇÕES ENCERRADAS` e `PROVA EM BREVE` (até 14 dias), o selo é recalculado por `work/selos.py` a partir dos prazos **confirmados**; selo escrito no dia **diferente** do registro é decisão e prevalece sobre o cálculo (copiar o selo do registro não conta), por isso, ao **entrar** na família, se escreve o que a data dá (`ENCERRA HOJE`, `ENCERRA EM BREVE` ou `PROVA EM BREVE` antes de `INSCRIÇÕES ABERTAS`), e o AVISO "contradiz o selo por data" aponta o erro; `INSCRIÇÕES ENCERRADAS` automático só com a banca lida no dia e sem retificação no dia do prazo ou depois — fora disso, o selo vencido cai para `PENDÊNCIA DE VERIFICAÇÃO` ("prorrogação não confirmada") e lá fica até o orquestrador confirmar na fonte oficial: encerradas → `INSCRIÇÕES ENCERRADAS`; prorrogadas → prazos novos confirmados e o selo que a nova data dá. `PROVA EM BREVE` com a prova já passada (e nenhuma nos próximos 14 dias) também cai para `PENDÊNCIA DE VERIFICAÇÃO`, até o orquestrador escrever `PROVA REALIZADA` ou a data nova; prova adiada ou distante segue o selo por data. Página oficial profunda (`url_oficial`) de todo concurso no escopo é lida todo dia por `work/paginas_oficiais.py` (`MUDOU`: ato novo).

**No histórico (`items`):** órgão, cargo, UF/abrangência, situação, banca, vagas, remuneração (e se confirmada oficialmente), prazos, data de prova, requisitos, fonte oficial e fonte secundária, quando disponíveis.

## 11. Seção "Se saiu na mídia não é fofoca!"

Clipping de ConJur, Migalhas e JOTA na janela, `MÍDIA ESPECIALIZADA` — cerca de 6 itens, prioridade para julgado com tese (STF, STJ, TJ, TRF) e carreiras; política sem tese jurídica não entra. Julgado do STJ noticiado só pela mídia vai em **STJ Notícias**, com `MÍDIA ESPECIALIZADA` e uma linha fixa do montador no topo da seção, sem nota por item (a rotina não lê a lista de notícias do portal do STJ; STJ Jurisprudência continua só oficial). Matéria que reproduz nota oficial (`[ASSESSORIA X]` no índice do `coleta_web.py`) é fato oficial noticiado — "segundo o ConJur, com informações da assessoria do X" —, nunca rumor nem "sem confirmação oficial". Item de mídia sobre tema que está num informativo oficial da edição cita o tema; a nota de confirmação não muda (o resultado segue só na mídia). Decisão, ato, concurso, julgamento, projeto ou movimento institucional: tentar confirmar em fonte oficial — confirmou → `CONFIRMADO POR FONTE OFICIAL` (ou `ALTERNATIVA`); não → "sem confirmação oficial localizada nesta execução". Por item: veículo, título, data/hora, tema, resumo de 2 a 4 linhas, impacto prático, link direto (resolvido, nunca wrapper), fonte oficial conferida e status. **Artigos/opiniões → `OPINIÃO/ANÁLISE`**, no bloco próprio dentro desta seção (template): 3 a 4, ligados a julgado, lei ou concurso da edição, com título, autor quando houver, data e link se resolvido (senão sem link).

## 12. Seção "FOFOQUINHA JURÍDICA"

Logo após a mídia. Movimentações, rumores, bastidores e sinais de novas provas em carreira jurídica e quadro de apoio — nunca boato como fato. Selos: `CONFIRMADO` · `FORTE INDÍCIO` · `RUMOR` · `SEM CONFIRMAÇÃO OFICIAL`. Por item: cargo/órgão, UF, origem, data, o que foi dito, por que importa, grau de confirmação, fonte oficial consultada e fonte secundária. Nota ou anúncio oficial reproduzido pelo JOTA é fato oficial noticiado, não boato. **Antes de repetir uma fofoquinha de edição anterior, verificar se já teve desfecho oficial** — se sim, não listar de novo como rumor: promover para a seção de notícia correspondente com o desfecho explícito. Se nada relevante: *"Nenhuma fofoquinha jurídica relevante localizada nesta execução."*

## 13. Seção "Porque sem Deus, nada é possível"

Fonte e fallback já resolvidos por `work/versiculo.py` (ROTINA passo 2: o YouVersion só é sondado às segundas — o anti-bot dele é esperado e não entra em erros nem no rodapé — e o DailyVerses.net, com a data da página conferida, é a fonte de fato) — publique exatamente o que ele retornar (`fonte`, `referência`, `versão`, `texto`), **rotulando a fonte REAL informada** (nunca atribua ao YouVersion o que veio de outra fonte). Ignorar divergência entre apps no mesmo dia não é erro nem pendência. Traduções protegidas longas: referência, versão, link e trecho curto; sempre acrescentar reflexão própria de 2–3 linhas conectada ao dia.

Saída `VERSICULO ok=false`: fallback por WebSearch (até 2 buscas; ROTINA passo 2 e referência §R5). Nada resolvendo, a seção fica **pendente** — nunca inventar versículo.

## 14. Seção "Conhecimento nunca é demais"

Citação curta de Charlie Munger de `work/munger-quotes.json` (fontes canônicas: *A sabedoria de Charlie Munger* — Poor Charlie's Almanack, Sextante/GMT, 2025, obra protegida, só trechos curtos com referência — e *A Psicologia dos Erros de Julgamento Humano*, Harvard, 1995/2005). Cada item traz `fonte`, `tipo` e, quando aplicável, `obs` com a atribuição correta — **reproduzir a `obs`**, para não atribuir a Munger o que ele apenas cita. **`aforismo`** (citação curta amplamente pública) sai entre aspas, assinado "— Charlie Munger"; **`licao`** (síntese própria das ideias dele, a maioria do banco) sai **sem aspas**, assinada "— lição inspirada em Charlie Munger · <fonte>" — paráfrase nunca se apresenta como citação literal. Mesma caixa e mesma cor nos dois casos. **Seleção determinística** já calculada pelo comando único do passo 1 da ROTINA (índice = dia do ano mod total real do array, contado na hora — nunca memorizado). Edição Extra no mesmo dia: `(dia do ano + 1) mod total` (`work/inicio.py --extra` já calcula). Preferir até **25 palavras**. Se o arquivo não existir: *"Adquira sabedoria e passe a agir de acordo."* — Charlie Munger (dedicatória da edição Sextante 2025).

## 15. Assunto do e-mail

Diária (dias úteis, 7h): `Robozinho dos Momozis até Passar - DD/MM/AAAA - 7h`. Manual/extraordinária: `Robozinho dos Momozis até Passar - DD/MM/AAAA - Extra` (e "Edição extra" no cabeçalho), gerada com `python3 work/inicio.py --extra` (`execution_id` `AAAA-MM-DD-extra`; referência §R7). **A data é SEMPRE a de hoje, ancorada no relógio** — inclusive em execuções atrasadas; bate caractere por caractere com o que o Apps Script procura.

---

## 16. Autoaprendizagem

O ledger `work/robozinho-aprendizado.json` é memória **operacional**, lida no início e atualizada no fim. Regra de admissão única:

> **Um registro só entra se mudar uma decisão concreta da próxima execução.** O resto vai para `verification_notes` do histórico. Registro que não decide nada é custo de leitura todo dia, para sempre.

**No início:** `fontes[].status` dimensiona o esforço; `armadilhas[].regra` é checklist antes de publicar; `pendencias_vivas[].faixa` diz o que verificar hoje.

**No fim**, conforme o gatilho — todo registro de julgamento vai no campo `ledger_updates` da execução (ROTINA passos 4–5), validado e aplicado pelo helper; contadores e o mecânico dos concursos (carimbo da banca, selo por data, `mudou_em`) são do helper:

| Gatilho | Registro |
|---|---|
| Fonte falhou/silenciou | Contador incrementado pelo helper (`--ledger`, a partir de `source_status`); ≥5 execuções e antes funcionava → `mudo`, esforço reduzido |
| Fonte voltou | Zerar contador, `saudavel`, registrar a data da volta |
| Fonte devolveu conteúdo errado | Nova `armadilha` com sintoma + regra; se o `id` já existe, só somar a data em `detectado_em` |
| Pendência parada | Rebaixar de faixa ou aposentar com justificativa |
| Pendência resolvida | Remover com `desfecho`, escrito para o leitor: o montador o mostra no dia ("Saiu do acompanhamento"), se ele via a pendência |
| Este prompt contradiz a realidade | Corrigir **este documento** e anotar no ledger |

**Ciclo de vida das pendências:** `ativa` (verificar sempre; aparece no quadro) → `longo_prazo` (verificar só na 1ª execução da semana; no quadro só quando o texto muda ou na 1ª execução da semana) → `cronica` (fonte quebrada; manter visível sem gastar esforço) → aposentada. Pendência aberta há mais de 21 execuções sem movimento não pode continuar `ativa`. O `texto` é para o leitor, sem jargão operacional (sonda, protocolo, coletor, script… vão em `politica`): pendência interna não vai ao leitor, nem a que repete item, limitação ou observação da edição.

**Mudança de dado fora da rotina** (registro conferido à mão, escopo, correção): nunca Edit no ledger, que a rotina reescreve todo dia; vai como migração `work/migracoes/<id>.json`, aplicada uma vez pelo `inicio.py` com a mesma validação do helper. Regra de armadilha que o código tornou falsa: `REGRAS_ATUALIZADAS` do helper.

**Limites — imutáveis, nenhum aprendizado os altera:** identidade visual (o layout do `work/montar_email.py`), assunto, destinatários, horário e cadência. E não se aprende a **baixar o padrão de prova**: a autoaprendizagem serve para gastar *melhor* o esforço de verificação, nunca *menos*.

**Escalar ao usuário** (uma linha no quadro de pendências, sem repetir todo dia): fonte oficial muda há mais de 30 dias — sugerir reassinar ou fornecer credenciais do INLABS; bloqueio estrutural novo que derrube uma seção; divergência entre fontes oficiais que a rotina não desempate.

Se o ledger não existir, criar com `{"fontes":[],"armadilhas":[],"pendencias_vivas":[],"licoes_de_processo":[]}` — nunca bloquear o rascunho por causa disso.

## 17. Orquestração e delegação

O modelo principal (Fable, decisão do dono) é **orquestrador e revisor**; o determinístico (datas, janela, feriados, listagens web, banca, selos por data, contadores, medição de uso, montagem do e-mail) está em scripts de `work/`; a coleta volumosa vai para os coletores próprios de `.claude/agents/` (ferramentas mínimas; modelo no frontmatter). **Critério: volume, não dificuldade.**

**Nunca delegar:** ancoragem de data; checagem cruzada de armadilhas; classificação de status e selos; a escolha do que entra em cada seção (a montagem do HTML é do `work/montar_email.py`); decisões do ledger; e `create_draft` — o rascunho é criado uma única vez, pelo orquestrador, após revisão. Subagente jamais cria, edita ou envia e-mail.

**Contrato de todo subagente** (no `.claude/agents/coletor-*.md`): *devolva evidência — título, data visível na fonte, URL —, relate o que tentou incluindo o que voltou vazio, e nunca conclua ausência de novidade; quem interpreta ausência é o orquestrador.* Coletor que falhe: relançar (referência §R3), nunca executar o coletor à mão; falhou de novo → a falha vai para `errors` e as seções dele saem com o quadro de pendências e o aviso ao leitor — delegação que falha nunca vira "sem novidade". Falha recorrente de um coletor → promover `haiku`→`sonnet` no frontmatter, ou reabsorver (registrar no ledger). Detalhe: referência §17.
