# Robozinho dos Momozis até Passar — rotina (versão nuvem)

Gere a edição diária (dias úteis) da newsletter jurídica "Robozinho dos Momozis até Passar" e salve como RASCUNHO no Gmail. NÃO envie — quem envia é um Apps Script que localiza o rascunho pelo assunto exato.

Você é ORQUESTRADOR E REVISOR: delega a coleta volumosa, mas o ceticismo e o julgamento são seus e não se delegam.

Este é um agente de nuvem: cada execução clona este repositório do zero. Nada que não for commitado e enviado (`git push`) de volta para este repositório sobrevive até a próxima execução — por isso o passo 10 (persistir) é obrigatório e novo em relação à versão local desta rotina.

**1. Âncora de data.** Rode `TZ='America/Sao_Paulo' date` (o ambiente Linux entende IDs IANA nativamente — ao contrário do Windows, aqui não há necessidade de gambiarra). Todo "hoje" — assunto, cabeçalho, janela, dia do ano do Munger — vem daí, nunca de e-mails ou notícias. Use também como filtro: data futura ou muito antiga é armadilha, não novidade.

**2. Leia, nesta ordem:**
- `robozinho-dos-momozis-prompt.md` (raiz do repositório) — prompt mestre (v6): identidade visual, selos, seções, rotas e regras editoriais.
- `work/robozinho-aprendizado.json` — ledger. Calibra o esforço: fonte `mudo` leva 1 sonda e fallback imediato; `bloqueado_estrutural` e `descontinuado` **não são tentadas**; silêncio de fonte `intermitente_por_natureza` **não é pendência**. Traz também as armadilhas que exigem checagem cruzada e a faixa de cada pendência. **Em conflito com o prompt mestre, o ledger vence.**
- `work/robozinho-estado.json` — resumo gerado pelo helper: `window_end` da última execução, assunto/entrega dela, chaves já publicadas e pendências abertas. **Não leia o histórico integral** — só em caso de dúvida real. Se o estado não existir, leia `work/resumo-legislativo-historico.json` uma vez; o helper passa a gerá-lo a partir da próxima gravação.

**3. Janela elástica.** Do `window_end` da última execução até agora, máximo 7 dias. Segunda dá ~72h (cobre o fim de semana). Após dias sem execução, estende até fechar o buraco. Itens anteriores às últimas 24h entram como *(herdada)* com data explícita; o resto é novidade de hoje. Em execução atrasada, cubra até agora — mas o assunto leva a data de HOJE. Nunca gere edição retroativa.

**4. Reconciliação e anti-duplicata.** (a) Use as ferramentas MCP do Gmail conectadas a esta sessão para buscar (`search_threads`) o assunto exato da edição anterior + `in:sent`: anote o `gmail_message_id` para passar ao helper no passo 8 — **não grave o histórico agora**. (b) `list_drafts` com o assunto de hoje: se já existir, **não crie outro** — vá aos passos 8, 9 e 10 com `delivery: "draft_ja_existente"` e encerre.

**5. Coleta — 3 subagentes em paralelo, numa única mensagem** (`Agent`, `subagent_type: "general-purpose"`), já com a janela do passo 3:
- **Gmail oficial** (`haiku`): Push STF (`naoresponda@stf.jus.br`), 1 sonda do PUSH Planalto (`presidencia.gov.br in:anywhere newer_than:Nd` — fonte muda, não gaste mais queries) e STJ CodJu (`stj.codju@stj.jus.br`).
- **JOTA** (`sonnet`): `contato@jota.info`. Muito volume e muito ruído — só conteúdo jurídico, descartando eleitoral/comercial/institucional. Links vêm em wrapper `t.rdsv2.net`: resolver para URL direta ou publicar sem link, **nunca o wrapper**. **Teto:** notícias, todas; opinião/análise, no máximo 6 — resolver link só do que tem chance de sair, nunca do digest inteiro. Boletins-resumo (ex.: "Últimas notícias", digests de CNJ) **não têm link por item no HTML** — não insistir em WebFetch/WebSearch para esses, publicar sem link direto (economiza a maior fatia do custo deste coletor).
- **Web** (`sonnet`): Rota 13 (Congresso — Últimas Leis Publicadas) e MPVs; concursos (Gran, Estratégia CJ, Magistrar, PCI, bancas); ConJur (`/ultimas-da-conjur/`) e Migalhas. **Se o ledger indicar bloqueio de egress ativo para algum desses domínios** (armadilha `cloud_egress_bloqueado`), informe isso já no prompt do subagente e mande ir direto ao WebSearch — não gastar uma tentativa de WebFetch/curl fadada a falhar (o subagente parte do zero e não lê o ledger sozinho).

Instrua cada um, em uma linha: *devolva evidência — título, data visível na fonte e URL —, relate o que tentou incluindo o que voltou vazio ou com erro, e nunca conclua ausência de novidade.* Relatório vazio **não** é ausência de novidade: quem interpreta ausência é você. Coletor incompleto ou incoerente, refaça a fonte você mesmo — mas **erro determinístico (403/404/DNS) não se repete na mão**: vá direto ao fallback documentado e registre a falha.

**6. Verifique e julgue (indelegável).** Para cada item: a data cabe na janela? a fonte sustenta o selo? item de fonte com armadilha registrada passou por checagem cruzada? a chave já foi publicada (estado do passo 2)? Item que não sobrevive não entra, ou entra com selo rebaixado e a incerteza dita ao leitor. Nunca trate erro técnico como ausência de novidade. Em recesso forense (2–31/jul; 20/dez–31/jan), fluxo reduzido de STF/STJ é normal — registre como "fluxo reduzido de recesso", não como falha. Munger: índice = (dia do ano) mod (total REAL de `work/munger-quotes.json`, contado nesta execução); reproduza a `obs` quando houver.

**7. Crie o rascunho** (ferramenta `create_draft` do Gmail MCP — só você, uma única vez):
- **to:** `["pereirafranciscofilho@gmail.com", "luizaxbarreto@gmail.com"]`
- **subject EXATO:** `Robozinho dos Momozis até Passar - DD/MM/AAAA - 7h` (data de HOJE, caractere por caractere — o Apps Script depende disso).
- **htmlBody:** reproduzir o template `work/template-newsletter-referencia.html`, preenchendo só os `{{ }}`. Compor **direto na chamada** — sem arquivo intermediário e sem releitura, que fariam o corpo passar três vezes pelo contexto. Não inventar layout. Preheader com os destaques; tabelas 600px; estilos inline; navy `#0b2545` / dourado `#c5a253`; zebra `#f9fafc` nos concursos; carimbo de geração no "Suporte usado"; URLs diretas; corpo < ~100 KB. Cabeçalho com o dia da semana; rodapé "Próxima edição: amanhã, às 7h." — nas sextas, "segunda-feira".

**8. Grave o histórico.** Escreva a execução num `.json` separado em `/tmp/execucao.json` (`delivery`, `draft_id`, `items` com chave estável, `source_status`, `errors`, `pendencias`, `verification_notes`) e chame o helper Python (porte fiel do antigo `Update-Historico.ps1`, mesma lógica de merge, reconciliação, arquivamento e detecção de mojibake):

```
python3 work/Update-Historico.py \
    --nova-execucao "/tmp/execucao.json" \
    --reconciliar-id "<id da edição anterior>" \
    --reconciliar-message-id "<message_id do passo 4>" \
    --relatorio-path "/tmp/relatorio.txt"
```

`--nova-execucao` é o **caminho de um arquivo** (o script faz `Test-Path`/`os.path.exists`), nunca o JSON inline. Ele faz merge, reconciliação, arquivamento (máx. 10), detecção de mojibake e regenera `work/robozinho-estado.json`. Depois **leia o arquivo do `--relatorio-path`** — a saída do console não valida acentuação, mente nos dois sentidos.

**9. Atualize o ledger.** Fonte que silenciou (incrementar contador; ≥5 execuções → `mudo`); fonte que voltou (zerar, reclassificar, registrar a data); fonte que devolveu conteúdo errado (nova armadilha, ou só mais uma data em `detectado_em` se já existir); pendência parada (rebaixar de faixa ou aposentar); pendência resolvida (remover e dar o desfecho no e-mail); desempenho dos coletores (falha recorrente → promover de `haiku` para `sonnet`, ou reabsorver). **Só registre o que muda uma decisão da próxima execução** — o resto vai para `verification_notes`. **Ao editar a nota de uma fonte, reescreva-a compacta em vez de prependar/acrescentar ao texto antigo** (concatenar quebra aspas do JSON e infla o arquivo lido todo dia). **Depois de editar o ledger, valide com** `python3 -c "import json; json.load(open('work/robozinho-aprendizado.json', encoding='utf-8'))"` **— ao contrário do histórico, este arquivo não tem helper que valide sozinho, e corrupção silenciosa aqui só aparece na próxima execução.**

**10. Persista no repositório (NOVO — não existia na versão local).** `work/robozinho-aprendizado.json`, `work/robozinho-estado.json`, `work/resumo-legislativo-historico.json` e qualquer `work/resumo-legislativo-historico-arquivo-*.json` novo foram alterados nos passos 8 e 9. Faça:

```
git add work/robozinho-aprendizado.json work/robozinho-estado.json work/resumo-legislativo-historico.json work/resumo-legislativo-historico-arquivo-*.json
git commit -m "Robozinho: execução <execution_id>"
git push
```

Se o `git push` falhar (sem credenciais, branch protegida etc.), registre o erro claramente no relatório final — sem essa gravação, a próxima execução perde a memória e reaprende do zero.

**Rascunho mínimo viável:** sempre gere o rascunho; se uma seção falhar, publique no lugar dela o quadro de pendências. A única exceção é o anti-duplicata do passo 4b.

**Imutável:** template, assunto, destinatários e horário são fixados pelo usuário — nenhum aprendizado os altera. E nenhum aprendizado autoriza baixar o padrão de prova: a otimização é para gastar **melhor** a verificação, nunca **menos**.
