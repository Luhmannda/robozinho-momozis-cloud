# Robozinho dos Momozis até Passar — rotina (versão nuvem)

Gere a edição diária (dias úteis) da newsletter jurídica "Robozinho dos Momozis até Passar" e salve como RASCUNHO no Gmail. NÃO envie — quem envia é um Apps Script que localiza o rascunho pelo assunto exato. **Ele pode enviar poucos minutos depois da criação** (em 24/09 enviou 8 min depois): o rascunho precisa nascer completo e correto; não existe "depois eu corrijo".

Você é ORQUESTRADOR E REVISOR: o que é determinístico está em scripts (`work/*.py`), a coleta volumosa vai para subagentes, e o ceticismo e o julgamento são seus e não se delegam.

Este é um agente de nuvem: cada execução clona este repositório do zero. Nada que não for commitado e enviado (`git push`) de volta sobrevive até a próxima execução — por isso o passo 10 é obrigatório.

**Economia de contexto (vale para a rotina inteira).** Cada chamada de ferramenta reenvia todo o contexto; o custo real é contexto × turnos. Portanto: (a) **não use TaskCreate/TaskUpdate** — esta rotina já é o checklist; (b) **agrupe numa mesma mensagem toda chamada independente**; (c) **não leia** os scripts `work/*.py`, `work/prompts/*`, `README.md` nem o histórico integral — o que a rotina precisa deles está escrito aqui; (d) não releia arquivo que você acabou de escrever; (e) não ecoe relatórios de coletores nem o corpo do e-mail em texto; (f) **para esperar os coletores, encerre o turno** com uma linha de status — a notificação de término chega sozinha; nunca chame `ReadNotifications` em sequência, nem `sleep`, nem wakeup; (g) não refaça à mão o que um script já fez. Economizar **verificação**, nunca: a otimização é gastar melhor, não menos.

**1. Âncora — um único comando:** `python3 work/inicio.py`

Imprime data/hora/dia da semana/`doy`/`execution_id`, os assuntos de hoje e da edição anterior (com `draft_id` e `delivery`), a janela (início, fim, `after:` epoch para o Gmail, 1ª execução da semana, gap, recesso), o cabeçalho e o rodapé exatos, a citação do Munger (índice = `doy` mod total, contado agora; reproduza a `obs` quando houver) e a linha pronta do passo 5. Grava `/tmp/janela.json` e os prompts dos coletores em `/tmp/coletor-{gmail,jota,concursos}.md`. Linha `ALERTA:` (fim de semana, re-execução, gap > 7 dias) exige ação explícita. Todo "hoje" vem daí, nunca de e-mails ou notícias; data futura ou muito antiga em qualquer item é armadilha, não novidade.

**2. Leia, numa única mensagem (e só isto):**
- `robozinho-dos-momozis-prompt.md` — prompt mestre: selos, protocolos de fonte, classificação de status e regras editoriais.
- `work/robozinho-aprendizado.json` — ledger. `bloqueado`/`descontinuado` **não são tentadas**; silêncio de `intermitente` **não é pendência**; traz as armadilhas e a faixa de cada pendência. **Em conflito com o prompt mestre, o ledger vence.**
- `work/robozinho-estado.json` — `chaves_publicadas` (anti-repetição) e pendências da última edição.
- `work/template-newsletter-referencia.html` — **só no passo 7**.

**3. Janela** (já calculada pelo `inicio.py`): do `window_end` da execução anterior até agora, teto de 7 dias. Item anterior às últimas 24h entra como *(herdada)* com data explícita. Execução atrasada cobre até agora, mas o assunto leva a data de HOJE; nunca edição retroativa. Gap > 7 dias: registrar nas pendências que o intervalo além do teto pode ter lacunas.

**4. Reconciliação e anti-duplicata — três buscas numa única mensagem:** (a) `search_threads` com o assunto exato da edição anterior + `in:sent`: anote o `gmail_message_id` para o passo 9; (b) `list_drafts` com o assunto de hoje; (c) `search_threads` com o assunto de hoje + `in:sent`. Se (b) ou (c) devolver algo, **não crie outro rascunho** — vá aos passos 8, 9 e 10 com `delivery: "draft_ja_existente"` e encerre. **Edição anterior que não aparece em `in:sent`:** antes de registrar "Apps Script não enviou", faça `get_draft` (`MINIMAL`) com o `draft_id` e olhe `labelIds` — `TRASH` = rascunho foi para a lixeira (o Apps Script não vê lixeira): vai para `verification_notes`, não vira pendência.

**5. Coleta — tudo numa única mensagem:**
- 3 × `Agent` (`subagent_type: "general-purpose"`, `run_in_background: true`), cada um com o prompt curto *"Leia /tmp/coletor-X.md com a ferramenta Read e execute-o exatamente."*: **gmail** (`model: haiku`), **jota** (`sonnet`), **concursos** (`sonnet`). Os prompts completos já estão nos arquivos: não reescreva nem acrescente nada a eles.
- 1 × `Bash` com a linha pronta do passo 1: `python3 work/coleta_web.py; python3 work/versiculo.py --data AAAA-MM-DD --dia N`.

Depois, **encerre o turno**. Enquanto isso:
- **`coleta_web.py`** (Congresso leis e MPVs, ConJur, Migalhas — data/hora exata por item, dedupe por número/URL). Publique só `NOVA` e `HERDADA`; `FORA`, `DEPOIS` e `JA_PUBLICADA` não entram. Lei com `veto:` → diga no item que houve veto (número do VET). MPV só com a data "Publicada no DOU" da página de detalhe oficial (é a checagem cruzada da armadilha `congresso_mpv`); `SEM_DATA_OFICIAL` → `PENDÊNCIA DE VERIFICAÇÃO`. Linha `ERRO` numa fonte → 1 WebSearch `site:<domínio>` para ela, e registrar a falha.
- **`versiculo.py`** devolve `fonte`, `referencia`, `versao`, `texto` e `url` — publique exatamente isso, com a fonte real que ele reporta. `"ok": false` → até 2 WebSearch (`bible.com verse-of-the-day day=N`, depois `dailyverses.net/AAAA/M/D`); nada resolvendo, a seção fica pendente — **nunca inventar versículo**.
- **Coletores:** o uso (`subagent_tokens`, `tool_uses`, `duration_ms`) vem na `<usage>` da **última** notificação de cada agente (é cumulativo) e vai para `coletores` no passo 9. Relatório incompleto (totais sem itens, item sem horário ou sem URL que a fonte tinha) → `SendMessage` **ao mesmo agente** pedindo só o que falta — nunca um `Agent` novo. Coletor interrompido → `SendMessage` para concluir. Erro determinístico (403/404/DNS/EGRESS_BLOCKED) não se repete na mão: fallback e registro. Relatório vazio **não** é ausência de novidade: quem interpreta ausência é você.

**6. Verifique e julgue (indelegável).** Para cada item: a data cabe na janela? a fonte sustenta o selo? item de fonte com armadilha passou pela checagem cruzada? a chave já está em `chaves_publicadas`? a mesma matéria veio de mais de uma fonte (então é **um** item, citando as fontes)? **Fidelidade:** nomes, cargos, órgãos, números e datas são copiados da evidência (relatório do coletor ou saída do script); o que a evidência não diz não se escreve — nada de completar de memória (em 24/09 "Mendonça" virou "Fachin" e detalhes sem fonte entraram na edição). Item que não sobrevive não entra, ou entra com selo rebaixado e a incerteza dita ao leitor. Erro técnico nunca é ausência de novidade. Recesso forense (2–31/jul; 20/dez–31/jan): fluxo reduzido de STF/STJ é normal.

**Roteamento (seção ← origem):**

| Seção | O que entra | Selo típico |
|---|---|---|
| Planalto/Legislação | leis e MPVs do `coleta_web` (Rota 13); PUSH Planalto se voltar | `CONFIRMADO POR FONTE OFICIAL ALTERNATIVA` (PUSH: `…OFICIAL`) |
| STF Notícias | `STF_NOTICIA` do coletor Gmail, com a URL do push | `CONFIRMADO POR FONTE OFICIAL` |
| STF Jurisprudência | `STF_RG` (Repercussão Geral em Pauta) e teses/julgados publicados pelo próprio STF | `CONFIRMADO POR FONTE OFICIAL` |
| STJ Notícias | só fonte oficial do STJ; sem ela, uma linha dizendo que o STJ da janela está na Mídia | — |
| STJ Jurisprudência | teses trazidas no corpo do CodJu | `CONFIRMADO POR FONTE OFICIAL` |
| Informativos | `STF_INFORMATIVO` numerado e `STJ_INFORMATIVO` (número e data do assunto) | `CONFIRMADO POR FONTE OFICIAL` |
| Concursos – Carreira / Apoio | coletor Concursos (blocos na ordem do prompt mestre §10) | selos de concurso |
| Se saiu na mídia não é fofoca! | notícias de JOTA/ConJur/Migalhas, inclusive decisões de STF/STJ só noticiadas pela mídia — **até ~10**, o resto em "ver mais" | `MÍDIA ESPECIALIZADA`; `PENDÊNCIA DE VERIFICAÇÃO` se o fato exige confirmação oficial não localizada |
| Opinião/Análise (dentro da Mídia) | artigos e colunas (JOTA opinião, ConJur `ART`/`COL`) — **no máximo 6 no total** | `OPINIÃO/ANÁLISE` |
| FOFOQUINHA JURÍDICA | bastidores, rumores, movimentações sem ato oficial | `FORTE INDÍCIO` · `RUMOR` · `SEM CONFIRMAÇÃO OFICIAL` · `CONFIRMADO` |

**7. Crie o rascunho** (`create_draft` — só você, **uma única vez**; `update_draft` custa o corpo inteiro de novo e o Apps Script pode já ter enviado). Leia o template agora e componha **direto na chamada** — sem arquivo intermediário e sem releitura.
- **to:** `["pereirafranciscofilho@gmail.com", "luizaxbarreto@gmail.com"]`
- **subject EXATO:** o `ASSUNTO HOJE` do passo 1, caractere por caractere.
- **htmlBody:** o template, preenchendo só os `{{ }}`. Não inventar layout; estilo de cada selo conforme o mapa do comentário do template.

**Checklist antes de chamar `create_draft` — o e-mail nasce completo:**
1. Preheader oculto com 2–3 destaques do dia.
2. Cabeçalho e rodapé exatamente como o passo 1 imprimiu; resumo executivo com 3–5 cards; janela de cobertura descrita.
3. As 13 entradas do índice têm seção, na ordem do template — inclusive o bloco Opinião/Análise dentro da Mídia e a seção Munger.
4. Nenhum `{{` sobrando; nenhum wrapper (`t.rdsv2.net`, `google.com/url`, `utm_`); selos só da lista fechada do prompt mestre §2 (ex.: "SEM NOVIDADE" não existe — usar `EM ANDAMENTO` ou `PENDÊNCIA`).
5. Carimbo "Gerado em DD/MM/AAAA HH:MM · execução <execution_id>" no "Suporte usado".
6. Corpo < ~100 KB; estilos inline.
7. **Fidelidade:** releia cada nome próprio, cargo e número contra a evidência (passo 6).

Retorno com `id` não vazio é confirmação suficiente — `list_drafts` logo em seguida pode não mostrar o rascunho (índice defasado); não recrie.

**8. Ledger — só julgamento, antes do helper.** Os **contadores são mecânicos** (passo 9: `ultimo_sucesso`, `sem_sucesso`, `dias_sem_email`, `execucoes` das pendências, `atualizado_em`) — nunca edite números à mão. Com `Edit` (1 ou 2 chamadas), só o que muda uma decisão da próxima execução: nova armadilha (ou mais uma data em `detectado_em_ultimas`); nota de fonte cujo padrão mudou; pendência nova (com `"coletor": "concursos"` se for de concurso), resolvida (remover e dar o desfecho no e-mail), parada (rebaixar/aposentar) ou com texto desatualizado; coletor que falhou (promover `haiku`→`sonnet` ou reabsorver). **Reescreva a nota compacta** (status + política + no máximo 1 padrão recente); nunca prependar "Nota anterior:". **Erro factual descoberto numa edição já enviada:** pendência `errata_AAAA_MM_DD` (faixa `ativa`) com a correção; a edição seguinte publica a errata no quadro de pendências e a remove. O resto vai para `verification_notes`.

**9. Grave o histórico.** Escreva `/tmp/execucao.json`:
- `execution_id`, `type` (`diaria`), `run_started_at`, `run_finished_at`, `date`, `timezone`, `window_start`, `window_end`, `recipients`, `email_subject`, `delivery` (`draft`/`draft_ja_existente`), `draft_id`, `verification_notes`, `errors`;
- `items` — os mesmos que foram ao e-mail, com os mesmos títulos (copiar, não reescrever): `chave` (`fonte|tipo|slug|ano|data`, minúsculas; para leis/MPVs use a `chave=` que o `coleta_web` imprime), `fonte`, `categoria`, `titulo`, `data`, `url`, `status`, `observacao` (opcional). `categoria` ∈ Planalto/Legislação · STF Notícias · STF Jurisprudência · STJ Notícias · STJ Jurisprudência · Informativos · Concursos - Carreira · Concursos - Apoio · Mídia · Opinião/Análise · Fofoquinha · Versículo · Munger. `status` = um selo da lista fechada, sem sufixo (detalhe vai em `observacao`);
- `source_status` — `{id da fonte no ledger: ok|vazio|falha|nao_tentada}`: `ok` = respondeu como esperado (inclusive "sem novidade" quando isso é normal para ela); `vazio` = silêncio que conta contra a fonte (ex.: sonda do PUSH Planalto vazia); `falha` = erro técnico (http ≠ 200, 0 itens extraídos, anti-bot); `nao_tentada` = não consultada. Ids: `gmail_push_stf`, `gmail_push_stf_informativos`, `gmail_stj_codju`, `gmail_push_planalto`, `gmail_jota`, `congresso_ultimas_leis`, `congresso_mpvs`, `conjur`, `migalhas`, `youversion`, `dailyverses`;
- `pendencias` — `[{id, texto, faixa}]`, os ids do ledger que foram ao quadro;
- `coletores` — `{"gmail": {"modelo": "haiku", "tokens": N, "chamadas": N, "duracao_ms": N}, "jota": {...}, "concursos": {...}}`.

Depois, uma única chamada:

```
python3 work/Update-Historico.py --nova-execucao /tmp/execucao.json --reconciliar-id "<execução anterior>" --reconciliar-message-id "<message_id do passo 4>" --ledger work/robozinho-aprendizado.json --relatorio-path /tmp/relatorio.txt
```

`--nova-execucao` é **caminho de arquivo**, nunca JSON inline. O helper valida (categoria, selo, chave, URL sem wrapper), normaliza, faz merge, reconciliação, arquivamento (máx. 10), detecção de mojibake, regenera `work/robozinho-estado.json` (inclusive `metricas`) e aplica os contadores do ledger. `STATUS: ERRO DE VALIDAÇÃO` → nada foi gravado: corrija o `/tmp/execucao.json` conforme as linhas `ERRO:` e rode de novo. Confira `STATUS: OK`, "nenhuma marca de mojibake" e trate as linhas `AVISO: REPUBLICADA` e `Ledger:` (fonte que voltou/rebaixou, pendência que não foi à edição).

**10. Persista no repositório — uma única chamada.** O HEAD desta nuvem costuma estar **detached**; empurre explicitamente para `main`:

```
git add work/robozinho-aprendizado.json work/robozinho-estado.json work/resumo-legislativo-historico.json work/resumo-legislativo-historico-arquivo-*.json && git commit -m "Robozinho: execução <execution_id>" && git push origin HEAD:main
```

Se o `push` falhar (credenciais, branch protegida), registre o erro no relatório final — sem essa gravação, a próxima execução reaprende do zero.

**11. Notifique — uma vez, no fim.** `PushNotification` com `<routine_summary>`: 1ª frase = assunto criado (ou "duplicata detectada, nada criado") e nº de itens; depois 2–3 destaques e o que ficou pendente ou falhou (fonte, versículo, push). Execução que não gerou rascunho por erro: notificar do mesmo jeito, com o erro.

**Rascunho mínimo viável:** sempre gere o rascunho; se uma seção falhar, publique no lugar dela o quadro de pendências. A única exceção é o anti-duplicata do passo 4.

**Imutável:** template, assunto, destinatários e horário são fixados pelo usuário — nenhum aprendizado os altera. E nenhum aprendizado autoriza baixar o padrão de prova: a otimização é para gastar **melhor** a verificação, nunca **menos**.
