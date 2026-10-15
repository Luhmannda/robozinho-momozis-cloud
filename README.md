# robozinho-cloud

Repositório de suporte para rodar a newsletter "Robozinho dos Momozis até Passar" como rotina de nuvem (cloud agent agendado), em vez de tarefa agendada local.

## Estrutura

- `ROTINA.md` — prompt completo que a rotina de nuvem executa (cole o conteúdo deste arquivo no campo de prompt do routine, ou aponte o agente para lê-lo e segui-lo).
- `robozinho-dos-momozis-prompt.md` — prompt mestre, núcleo lido todo dia (identidade visual, selos, status, regras editoriais).
- `docs/referencia-operacional.md` — texto integral das seções operacionais do prompt mestre (rotas do DOU, protocolo do Gmail, contingência por fonte, delegação), consultado só quando a situação pede.
- `.claude/agents/coletor-*.md` — coletores Gmail, JOTA e Concursos como subagentes próprios, só com as ferramentas de que precisam (base de contexto ~8× menor que a do `general-purpose`) e o modelo no frontmatter.
- `work/template-newsletter-referencia.html` — template HTML da newsletter. Imutável.
- `work/munger-quotes.json` — base de citações do Munger.
- `work/robozinho-aprendizado.json` — ledger de aprendizado (fontes, armadilhas, pendências e o registro estruturado de concursos). Contadores aplicados pelo helper; julgamento só pelo campo `ledger_updates` da execução.
- `work/robozinho-estado.json` — resumo de estado gerado automaticamente. Atualizado a cada execução.
- `work/resumo-legislativo-historico.json` — histórico das últimas execuções. Atualizado a cada execução.
- `work/resumo-legislativo-historico-arquivo-*.json` — arquivos mensais arquivados pelo helper (surgem com o tempo).
- `work/Update-Historico.py` — porte em Python do helper `Update-Historico.ps1` (Windows), para rodar no ambiente Linux da rotina de nuvem. Merge, reconciliação, arquivamento (máx. 10), detecção de mojibake, emissão do estado e das métricas; valida categoria/selo/chave/URL de cada item antes de gravar e, com `--ledger`, aplica os contadores mecânicos e os `ledger_updates`. `--validar` confere tudo (inclusive matéria repetida entre fontes) antes do rascunho, sem gravar; `--medir-uso` registra modelo e tokens reais do orquestrador e dos coletores; o cabeçalho da execução vem do `/tmp/janela.json`.
- `work/inicio.py` — passo 1: âncora de data, janela, assuntos, rodapé, Munger, prazos de concursos (radar e fila de verificação), teste de rede das páginas oficiais e os prompts prontos dos coletores (`/tmp/coletor-*.md`).
- `work/finalizar.sh` — passo 7: helper + commit + push para `main` numa chamada, só com `STATUS: OK` (na branch local `main`, para o hook de parada não gerar branch órfã).
- `work/medir_uso.py` — mede, sem custo de tokens, o uso real da sessão a partir das transcrições locais.
- `work/repeticao.py` — detecção de matéria repetida entre fontes por semelhança de título (usada pelo `coleta_web.py` e pela validação).
- `work/prompts/coletor-*.md` — modelos fixos dos prompts dos coletores Gmail, JOTA e Concursos (preenchidos pelo `inicio.py`).
- `work/coleta_web.py` — coleta determinística de Congresso (leis e MPVs), ConJur e Migalhas, com hora exata por matéria, dedupe contra o histórico, marca `[REPETIDA?~chave]` e filtro de sorteios/eventos (`PROMO`).
- `work/informativos.py` — conteúdo dos informativos (STF, Repercussão Geral em Pauta e STJ) direto do documento oficial: acha a edição nova pelo número, baixa e extrai os destaques, sem tokens.
- `work/versiculo.py` — versículo do dia (YouVersion → DailyVerses.net), com conferência da data.
- `work/resolver_jota.py` — resolve os links-wrapper do JOTA por curl; só funciona com `www.jota.info` e `t.rdsv2.net` no allowlist do ambiente (senão avisa `BLOQUEADO` e o coletor faz uma sondagem curta por WebSearch).

## Por que este repositório existe

Uma rotina de nuvem (cloud agent agendado) roda isolada: cada disparo clona o repositório do zero e não enxerga o disco do computador local. Para a rotina "lembrar" o que já foi publicado, o próprio agente precisa commitar e dar `git push` nos arquivos de `work/` ao final de cada execução (passo 7 de `ROTINA.md`, `work/finalizar.sh`) — isso é a única forma de persistência entre execuções nesse modelo.

## O que fica de fora

- `EnviarRobozinho.gs` (Apps Script que localiza o rascunho pelo assunto e envia) continua vivendo no Google Apps Script da conta Gmail, associado à planilha/projeto onde já está implantado. Ele não muda com esta migração — a rotina de nuvem só passa a *criar o rascunho*; quem envia continua sendo o Apps Script, com o mesmo gatilho de horário.
- Arquivos de histórico mensal antigos e HTMLs de edições passadas não foram trazidos (não são lidos pela rotina).

## Pré-requisitos para a rotina de nuvem funcionar

1. Um conector MCP do Gmail conectado em https://claude.ai/customize/connectors, para a mesma conta usada pelo Apps Script de envio.
2. Este repositório publicado no GitHub (privado, recomendado) e acessível pelo ambiente de nuvem.
3. O routine configurado (via skill `schedule`) apontando para este repositório, com o conector Gmail anexado e `ROTINA.md` como prompt.
