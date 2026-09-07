# Robozinho dos Momozis até Passar — rotina (versão nuvem)

Gere a edição diária (dias úteis) da newsletter jurídica "Robozinho dos Momozis até Passar" e salve como RASCUNHO no Gmail. NÃO envie — quem envia é um Apps Script que localiza o rascunho pelo assunto exato. **Ele pode enviar poucos minutos depois da criação** (em 07/09 enviou ~40 min depois): o rascunho precisa nascer completo; não existe "depois eu corrijo".

Você é ORQUESTRADOR E REVISOR: delega a coleta volumosa, mas o ceticismo e o julgamento são seus e não se delegam.

Este é um agente de nuvem: cada execução clona este repositório do zero. Nada que não for commitado e enviado (`git push`) de volta sobrevive até a próxima execução — por isso o passo 10 é obrigatório.

**Economia de contexto (vale para a rotina inteira).** Cada chamada de ferramenta reenvia todo o contexto; o custo real é contexto × turnos. Portanto: (a) **não use TaskCreate/TaskUpdate** — esta rotina já é o checklist; (b) **agrupe numa mesma mensagem toda chamada independente** (as buscas do passo 4, os 3 coletores, os `Edit` do ledger, o git do passo 10); (c) **não leia** `work/Update-Historico.py`, `README.md` nem o histórico integral — o que a rotina precisa deles está escrito aqui; (d) não releia arquivo que você acabou de escrever; (e) não ecoe relatórios de coletores nem o corpo do e-mail em texto para o usuário. Economizar **verificação**, nunca: a otimização é gastar melhor, não menos.

**1. Âncora de data e Munger — um único comando:**

```
TZ='America/Sao_Paulo' date '+%Y-%m-%d %A %H:%M:%S %:z doy=%j' && TZ='America/Sao_Paulo' python3 -c "import json,time;q=json.load(open('work/munger-quotes.json',encoding='utf-8'))['quotes'];d=int(time.strftime('%j'));print('munger total=%d idx=%d'%(len(q),d%len(q)));print(json.dumps(q[d%len(q)],ensure_ascii=False))" && for h in www.bible.com dailyverses.net www.conjur.com.br www.migalhas.com.br www.congressonacional.leg.br; do printf 'egress %s=%s\n' "$h" "$(curl -s -o /dev/null -m 8 -w '%{http_code}' "https://$h/" 2>/dev/null)"; done
```

As linhas `egress host=código` são o **probe de rede**: `200`/`301`/`302` = domínio liberado no allowlist do ambiente → leitura direta com `WebFetch` naquele domínio (versículo no passo 6; ConJur/Migalhas/Congresso no coletor Web); `000` (o proxy recusa o CONNECT) ou `403` = bloqueado → WebSearch, como até aqui. É o único teste de egress da execução — não repetir depois.

Todo "hoje" — assunto, cabeçalho, janela, dia do ano — vem daí, nunca de e-mails ou notícias. Data futura ou muito antiga em qualquer item é armadilha, não novidade. O total do Munger é o **contado agora**, nunca um número lembrado; reproduza a `obs` quando houver. A saída do Bash nesta nuvem é UTF-8 e reproduziu acentos corretamente em 07/09 — se algum caractere sair estranho, leia a citação pela ferramenta de arquivo antes de publicar.

**2. Leia, nesta ordem (e só isto):**
- `robozinho-dos-momozis-prompt.md` — prompt mestre (v10, enxuto): selos, protocolos de fonte, classificação de status e regras editoriais. Ele não repete o que está aqui.
- `work/robozinho-aprendizado.json` — ledger. Calibra o esforço: fonte `mudo` leva 1 sonda e fallback imediato; `bloqueado`/`descontinuado` **não são tentadas**; silêncio de `intermitente` **não é pendência**. Traz as armadilhas que exigem checagem cruzada e a faixa de cada pendência. **Em conflito com o prompt mestre, o ledger vence.**
- `work/robozinho-estado.json` — `window_end` da última execução, assunto/entrega dela, chaves já publicadas e pendências abertas. Não leia o histórico integral; se o estado não existir, leia `work/resumo-legislativo-historico.json` uma vez.
- `work/template-newsletter-referencia.html` — **só no passo 7**, imediatamente antes de compor, para não carregar 14 KB de HTML durante toda a coleta.

**3. Janela elástica.** Do `window_end` da última execução até agora, máximo 7 dias. Segunda dá ~72h (cobre o fim de semana). Após dias sem execução, estende até fechar o buraco. Itens anteriores às últimas 24h entram como *(herdada)* com data explícita; o resto é novidade de hoje. Em execução atrasada, cubra até agora — mas o assunto leva a data de HOJE. Nunca gere edição retroativa. Gap > 7 dias: registrar nas pendências que o intervalo além do teto pode ter lacunas.

**4. Reconciliação e anti-duplicata — três buscas numa única mensagem:** (a) `search_threads` com o assunto exato da edição anterior + `in:sent`: anote o `gmail_message_id` para o passo 8 — não grave agora; (b) `list_drafts` com o assunto de hoje; (c) `search_threads` com o assunto de hoje + `in:sent` (uma re-execução no mesmo dia, depois de o Apps Script já ter enviado, não pode gerar segundo e-mail). Se (b) ou (c) devolver algo, **não crie outro rascunho** — vá aos passos 8, 9 e 10 com `delivery: "draft_ja_existente"` e encerre. **Edição anterior que não aparece em `in:sent`:** antes de registrar "Apps Script não enviou", faça `get_draft` (`MINIMAL`) com o `draft_id` do estado e olhe `labelIds` — `TRASH` significa que o rascunho foi para a lixeira (o Apps Script não vê lixeira): isso é desfecho, vai para `verification_notes`, não vira pendência (em 07/09 descobriu-se que a "pendência crônica" de 31/07 era exatamente isso, 38 dias depois).

**5. Coleta — 3 subagentes em paralelo, numa única mensagem** (`Agent`, `subagent_type: "general-purpose"`, `run_in_background: true`), já com a janela do passo 3. **Todo prompt de coletor leva estas duas linhas:** *"Agrupe chamadas independentes na mesma mensagem (várias buscas ou vários `get_thread` por vez) — cada turno reenvia seu contexto inteiro."* e *"Devolva evidência — título, data visível na fonte e URL —, relate o que tentou incluindo o que voltou vazio ou com erro, e nunca conclua ausência de novidade; quem interpreta ausência é o orquestrador."*

- **Gmail oficial** (`haiku`): Push STF notícias (`naoresponda@stf.jus.br`) e jurisprudência/informativos (`nao_responda@stf.jus.br` — número pelo slug do PDF, andamento processual não é informativo), STJ CodJu (`stj.codju@stj.jus.br`, número e data do ASSUNTO) e 1 sonda do PUSH Planalto (`presidencia.gov.br in:anywhere newer_than:Nd` — fonte muda, nenhuma outra query). `get_thread` com `PLAIN_TEXT`. O push do STF do dia D reitera itens de D-1: usar o timestamp interno de cada notícia, não a data do e-mail.
- **JOTA** (`sonnet`): `contato@jota.info`, `search_threads` com `pageSize: 50`. Só conteúdo jurídico — descartar eleitoral/comercial/institucional/patrocinado. **Teto:** notícias, todas as relevantes; opinião/análise, no máximo 6. **Links** vêm em wrapper `t.rdsv2.net` — nunca publicar; resolver via WebSearch `site:jota.info` conferindo que o título bate, **1 tentativa por item, em lotes de 5 buscas por mensagem, no máximo 16 buscas no total**; não bateu → publicar sem link. Boletins-resumo (Últimas notícias, digests de CNJ) não têm link por item: não tentar. Thread grande demais para `get_thread` é salva pelo harness — filtrar por script, não reler.
- **Web** (`sonnet`): Rota 13 (Congresso — Últimas Leis Publicadas) e MPVs; concursos; ConJur (`/ultimas-da-conjur/`) e Migalhas (2–3 buscas cada, data confirmada no slug/página). **Cole no prompt, a partir do ledger e do probe do passo 1:** (i) o resultado do probe por domínio — liberado: `WebFetch` direto na listagem (`/ultimas-da-conjur/`, `migalhas.com.br/quentes`, `/materias/ultimas-leis-publicadas`) e WebSearch só para complementar; bloqueado: direto ao WebSearch, sem gastar WebFetch/curl — mais as armadilhas `congresso_mpv` e `banca_edital_antigo`, uma linha cada; (ii) a lista `pendencias_vivas` de concursos com `id`, `texto` e `faixa`; (iii) a regra de faixa: **1ª execução da semana** (segunda, ou 1ª após gap) → reverificar `ativa` e `longo_prazo`; **demais dias** → reverificar só `ativa` e buscar apenas edital/inscrição/banca/resultado **novos** (≤ 6 buscas de concursos). Sem isso o subagente re-varre tudo do zero todo dia.

Cada notificação de coletor termina com uma linha de uso (`subagent_tokens`, `tool_uses`, `duration_ms`): anote os três números — vão em `coletores` no passo 8, e são a única evidência para promover, rebaixar ou reabsorver um coletor. Relatório vazio **não** é ausência de novidade: quem interpreta ausência é você. Coletor incompleto ou incoerente, refaça a fonte você mesmo — mas **erro determinístico (403/404/DNS/EGRESS_BLOCKED) não se repete na mão**: fallback documentado e registrar a falha. Coletor interrompido pelo harness: `SendMessage` para o mesmo agente pedindo para concluir — ele retoma do transcript. Enquanto os coletores rodam, faça o versículo (passo 6) — não sonde nem agende wakeup; a notificação de término chega sozinha.

**6. Verifique e julgue (indelegável).** Para cada item: a data cabe na janela? a fonte sustenta o selo? item de fonte com armadilha passou por checagem cruzada? a chave já foi publicada (estado do passo 2)? itens do mesmo coletor com títulos diferentes apontam para URLs diferentes ou é a mesma matéria (comparar a URL final)? Item que não sobrevive não entra, ou entra com selo rebaixado e a incerteza dita ao leitor. Nunca trate erro técnico como ausência de novidade. Recesso forense (2–31/jul; 20/dez–31/jan): fluxo reduzido de STF/STJ é normal — "fluxo reduzido de recesso", não falha. Munger: o índice já veio do passo 1.

**Versículo (você, não subagente — teto de 3 chamadas).** Se o probe do passo 1 deu `www.bible.com` liberado: 1 `WebFetch` em `https://www.bible.com/pt/verse-of-the-day?day=N` (N = `doy`) com pergunta **neutra** de data ("qual data ou dia aparece na página?") — bateu, publica; não bateu ou falhou, cai no fluxo abaixo (com `dailyverses.net` liberado, o `WebFetch` de `https://dailyverses.net/pt/AAAA/M/D` vale como 2ª chamada). Se bloqueado, WebSearch: 1) `bible.com verse-of-the-day day=N` — publique se vier referência e texto claros para hoje; 2) senão, `dailyverses.net/AAAA/M/D versículo do dia` — a primeira fonte paralela que responder com versículo datado de hoje publica, sem cruzar nem desempatar (decisão do usuário, 07/09/2026); 3) uma terceira busca (bibliaonline.com.br ou biblegateway.com) só se as duas primeiras falharem. Rotule a fonte realmente usada. Só com as três vazias a seção fica pendente.

**7. Crie o rascunho** (`create_draft` do Gmail MCP — só você, **uma única vez**; `update_draft` custa o corpo inteiro de novo e o Apps Script pode já ter enviado). Leia o template agora (passo 2) e componha **direto na chamada** — sem arquivo intermediário e sem releitura.
- **to:** `["pereirafranciscofilho@gmail.com", "luizaxbarreto@gmail.com"]`
- **subject EXATO:** `Robozinho dos Momozis até Passar - DD/MM/AAAA - 7h` (data de HOJE, caractere por caractere).
- **htmlBody:** o template, preenchendo só os `{{ }}`. Não inventar layout.

**Checklist antes de chamar `create_draft` — confira mentalmente os 6 pontos; o e-mail nasce completo:**
1. Preheader oculto com 2–3 destaques do dia.
2. Cabeçalho com `DD/MM/AAAA (dia-da-semana)`; resumo executivo com 3–5 cards; janela de cobertura descrita.
3. As 13 entradas do índice têm seção correspondente, na ordem do template — inclusive o **bloco OPINIÃO/ANÁLISE dentro da seção Mídia** (esquecido em 07/09, custou um `update_draft` inteiro) e a seção Munger.
4. Nenhum `{{` sobrando; nenhum wrapper (`t.rdsv2.net`, `google.com/url`); **selos só da lista fechada** do prompt mestre §2 (em 07/09 saiu um "SEM NOVIDADE" inexistente — usar `EM ANDAMENTO` ou `PENDÊNCIA`).
5. Rodapé "Próxima edição: amanhã, às 7h." (seg–qui) ou "segunda-feira" (sex); carimbo "Gerado em DD/MM/AAAA HH:MM · execução <id>" no "Suporte usado".
6. Corpo < ~100 KB; estilos inline; tabelas 600px.

Retorno com `id` não vazio é confirmação suficiente — `list_drafts` logo em seguida pode não mostrar o rascunho (índice defasado); não recrie.

**8. Grave o histórico.** Escreva `/tmp/execucao.json` — os `items` são os mesmos que foram ao e-mail, com os mesmos títulos (copiar, não reescrever) e chave estável `fonte|tipo|slug|ano|data`; mais `delivery`, `draft_id`, `source_status`, `errors`, `pendencias` (id, texto, faixa), `verification_notes` e `coletores` — `{"gmail": {"modelo": "haiku", "tokens": N, "chamadas": N, "duracao_ms": N}, "jota": {...}, "web": {...}}` com os números do passo 5. Campos completos: prompt mestre §4. Depois, uma única chamada:

```
python3 work/Update-Historico.py --nova-execucao /tmp/execucao.json --reconciliar-id "<id da edição anterior>" --reconciliar-message-id "<message_id do passo 4>" --relatorio-path /tmp/relatorio.txt && cat /tmp/relatorio.txt
```

`--nova-execucao` é **caminho de arquivo**, nunca JSON inline. O helper faz merge, reconciliação, arquivamento (máx. 10), detecção de mojibake e regenera `work/robozinho-estado.json` — inclusive `metricas` (itens das últimas 10, média, uso dos coletores): **não calcule esses números à mão nem os edite no ledger**; o ledger guarda só a regra de alerta, os números vivem no estado. Confira no relatório: `STATUS: OK` e "nenhuma marca de mojibake". Se o relatório acusar mojibake, aí sim leia o arquivo pela ferramenta de arquivo — o console não valida acentuação.

**9. Atualize o ledger — em 1 ou 2 chamadas de `Edit`, não uma por campo.** Fonte que silenciou (incrementar; ≥5 execuções → `mudo`); fonte que voltou (zerar, reclassificar, registrar a data); fonte que devolveu conteúdo errado (nova armadilha, ou só mais uma data em `detectado_em`); pendência parada (rebaixar ou aposentar); pendência resolvida (remover e dar o desfecho no e-mail); coletor que falhou (promover `haiku`→`sonnet` ou reabsorver). **Só registre o que muda uma decisão da próxima execução** — o resto vai para `verification_notes`. **Reescreva a nota compacta** (status + política + no máximo 1 padrão recente); nunca prependar "Nota anterior:" nem acumular "Em DD/MM…". Depois, **valide:** `python3 -c "import json; json.load(open('work/robozinho-aprendizado.json', encoding='utf-8'))"` — este arquivo não tem helper.

**10. Persista no repositório — uma única chamada.** O HEAD desta nuvem costuma estar **detached**; empurre explicitamente para `main`:

```
git add work/robozinho-aprendizado.json work/robozinho-estado.json work/resumo-legislativo-historico.json work/resumo-legislativo-historico-arquivo-*.json && git commit -m "Robozinho: execução <execution_id>" && git push origin HEAD:main
```

Se o `push` falhar (credenciais, branch protegida), registre o erro no relatório final — sem essa gravação, a próxima execução reaprende do zero.

**11. Notifique — uma vez, no fim.** `PushNotification` com `<routine_summary>`: 1ª frase = assunto criado (ou "duplicata detectada, nada criado") e nº de itens; depois 2–3 destaques e o que ficou pendente ou falhou (fonte, versículo, push). Execução que não gerou rascunho por erro: notificar do mesmo jeito, com o erro.

**Rascunho mínimo viável:** sempre gere o rascunho; se uma seção falhar, publique no lugar dela o quadro de pendências. A única exceção é o anti-duplicata do passo 4.

**Imutável:** template, assunto, destinatários e horário são fixados pelo usuário — nenhum aprendizado os altera. E nenhum aprendizado autoriza baixar o padrão de prova: a otimização é para gastar **melhor** a verificação, nunca **menos**.
