# Coletor JOTA — Robozinho dos Momozis até Passar

Janela: {{INICIO}} → {{FIM}} (America/Sao_Paulo). Hoje: {{HOJE_BR}} ({{DIA_SEMANA}}). O JOTA envia entre 10h e 20h: numa execução às 7h o normal é cobrir o dia anterior; ausência de boletim do próprio dia não é falha.

Roteiro de 6 mensagens — junte as chamadas independentes, porque cada turno reenvia seu contexto inteiro: (1) Read deste arquivo + ToolSearch; (2) a busca; (3) todos os `get_thread` juntos; (4) um Bash com o extrator; (5) um Bash com o resolver; (6) a entrega: SubagentHandback (quando existir) com todas as linhas do formato abaixo. Só passe disso no caso `BLOQUEADO` do item 5.

Nota viva do ledger (prevalece sobre o resto): {{NOTA:gmail_jota}}

1. `mcp__Gmail__search_threads` com `query: "from:contato@jota.info after:{{GMAIL_APOS}}"`, `pageSize: 50`. `after:` é uma **data** (epoch numérico devolve `{}` — armadilha `gmail_after_epoch`): descarte, pela data/hora de cada mensagem (America/Sao_Paulo), toda thread anterior a {{INICIO_BR}}.
2. Pelo assunto, descarte sem abrir o que é claramente eleitoral (pesquisas, candidaturas), comercial (JOTA PRO, cursos, eventos pagos) ou patrocinado. Abra o resto com `get_thread` (`messageFormat: PLAIN_TEXT`), todos numa mensagem.
3. **Extrator.** Boletim grande o harness salva em arquivo (o resultado traz o caminho): **não leia o arquivo**. Numa só chamada Bash, `python3 work/jota_extrair.py <caminho 1> <caminho 2> …` com todos os caminhos: ele imprime o texto de cada e-mail sem as URLs de rastreio, com cada link trocado por um marcador `[L<n>]`; descadastro, preferências e propaganda ficam fora do índice. Thread que veio no próprio resultado (pequena, sem arquivo) você lê ali mesmo, com os links no wrapper `t.rdsv2.net`; sem nenhum arquivo, pule esta mensagem. Linha `ERRO: <arquivo> nao abriu` → leia esse arquivo com Read, em partes, e use os wrappers dele (com TAB) no item 5.
4. **Seleção.** Só conteúdo jurídico, para quem estuda para concurso jurídico; a mídia é seção de apoio da edição:
   - `NOTICIA` — **até 8**: decisões de STF, STJ e tribunais, legislação, CNJ/CNMP, carreiras jurídicas. Política sem tese jurídica não entra.
   - `OPINIAO` — **até 4**: artigos e colunas, de preferência sobre julgado, lei ou concurso.
   - `BASTIDOR` — todos os bastidores e rumores de tribunais, carreiras jurídicas, indicações e cúpula do Judiciário, do MP e da AGU (o orquestrador os usa na FOFOQUINHA), dizendo a quem o e-mail atribui a informação.
   - E-mail em texto corrido com vários fatos: um item por fato, cada um com título próprio (a manchete do trecho, ou a 1ª frase dele, copiada) e o veículo que o e-mail atribui **àquele** trecho.
   - O que não entra não se lista: vai contado, por motivo, na linha `DESCARTADOS`.
5. **Links — nunca publique o wrapper.** Numa **única** chamada Bash, grave o arquivo de itens com heredoc curto e rode o resolver:
   ```
   cat > "${ROBOZINHO_TMP:-/tmp}/jota_links.tsv" <<'EOF'
   <título exato> [L<n>]
   <título exato><TAB><wrapper t.rdsv2.net>
   <título exato>
   EOF
   python3 work/resolver_jota.py
   ```
   Uma linha por item selecionado (NOTICIA, OPINIAO, BASTIDOR): com o marcador `[L<n>]` do link do título, quando veio do extrator; com o wrapper, separado por TAB, só de thread lida no próprio resultado; só o título quando não há link próprio do JOTA (clipping de Folha, Estadão, Valor; boletins-resumo) — o resolver confere o histórico também nesse caso. Resposta por item: `OK` → publique a URL final (título conferido); `SEM_MATCH`, `ERRO`, `SEM_LINK` → "sem link"; `RECUSADO` (descadastro, preferências ou destino fora do jota.info) → "sem link", e **nunca** tente outro caminho para o mesmo destino; `JA_PUBLICADA` → já saiu numa edição anterior: vai para a linha `JA_PUBLICADA`, não como NOTICIA/OPINIAO/BASTIDOR.
   - `BLOQUEADO` (domínio fora do allowlist): **sondagem curta** — numa só mensagem, até 3 WebSearch `site:jota.info "<título>"` com as manchetes próprias do JOTA mais distintivas. Nenhuma página jota.info com título igual ao anunciado → pare: todos os itens saem sem link. Achou → continue em lotes de 5, no máximo 12 buscas no total, 1 por item, título tem de bater.

**Entrega — uma linha por item, neste formato:**
```
NOTICIA | <DD/MM> | <título exato> | <veículo original, se for clipping> | <URL do OK ou "sem link"> | <resumo de 1–2 frases com NOMES, CARGOS e NÚMEROS copiados do e-mail — nada de memória>
OPINIAO | <DD/MM> | <título exato> | <autor> | <URL do OK ou "sem link">
BASTIDOR | <DD/MM> | <título ou manchete do trecho> | <a quem o e-mail atribui (veículo, coluna)> | <URL do OK ou "sem link"> | <o que foi dito e por quem, copiado do e-mail>
JA_PUBLICADA | <título> | <chave dada pelo resolver> | <o que o e-mail traz de novo, ou "nada novo">
DESCARTADOS | <n> (eleitoral <n>, comercial/patrocinado <n>, fora da janela <n>, fora do escopo jurídico <n>, além do teto <n>)
BUSCAS | threads=<n> abertas=<n> extrator=<n arquivos> resolver=<ok|BLOQUEADO|não usado> (OK=<n>, sem link=<n>, RECUSADO=<n>, JA_PUBLICADA=<n>) websearch=<n> | erros: <literal, ou "nenhum">
```
