# robozinho-cloud

Repositório de suporte para rodar a newsletter "Robozinho dos Momozis até Passar" como rotina de nuvem (cloud agent agendado), em vez de tarefa agendada local.

## Estrutura

- `ROTINA.md` — prompt completo que a rotina de nuvem executa (cole o conteúdo deste arquivo no campo de prompt do routine, ou aponte o agente para lê-lo e segui-lo).
- `robozinho-dos-momozis-prompt.md` — prompt mestre (identidade visual, selos, seções, regras editoriais). Imutável.
- `work/template-newsletter-referencia.html` — template HTML da newsletter. Imutável.
- `work/munger-quotes.json` — base de citações do Munger.
- `work/robozinho-aprendizado.json` — ledger de aprendizado (fontes, armadilhas, pendências). Atualizado a cada execução.
- `work/robozinho-estado.json` — resumo de estado gerado automaticamente. Atualizado a cada execução.
- `work/resumo-legislativo-historico.json` — histórico das últimas execuções. Atualizado a cada execução.
- `work/resumo-legislativo-historico-arquivo-*.json` — arquivos mensais arquivados pelo helper (surgem com o tempo).
- `work/Update-Historico.py` — porte em Python do helper `Update-Historico.ps1` (Windows), para rodar no ambiente Linux da rotina de nuvem. Mesma lógica: merge, reconciliação, arquivamento (máx. 10), detecção de mojibake, emissão do estado.

## Por que este repositório existe

Uma rotina de nuvem (cloud agent agendado) roda isolada: cada disparo clona o repositório do zero e não enxerga o disco do computador local. Para a rotina "lembrar" o que já foi publicado, o próprio agente precisa commitar e dar `git push` nos arquivos de `work/` ao final de cada execução (passo 10 de `ROTINA.md`) — isso é a única forma de persistência entre execuções nesse modelo.

## O que fica de fora

- `EnviarRobozinho.gs` (Apps Script que localiza o rascunho pelo assunto e envia) continua vivendo no Google Apps Script da conta Gmail, associado à planilha/projeto onde já está implantado. Ele não muda com esta migração — a rotina de nuvem só passa a *criar o rascunho*; quem envia continua sendo o Apps Script, com o mesmo gatilho de horário.
- Arquivos de histórico mensal antigos e HTMLs de edições passadas não foram trazidos (não são lidos pela rotina).

## Pré-requisitos para a rotina de nuvem funcionar

1. Um conector MCP do Gmail conectado em https://claude.ai/customize/connectors, para a mesma conta usada pelo Apps Script de envio.
2. Este repositório publicado no GitHub (privado, recomendado) e acessível pelo ambiente de nuvem.
3. O routine configurado (via skill `schedule`) apontando para este repositório, com o conector Gmail anexado e `ROTINA.md` como prompt.
