# robozinho-cloud

Repositório de suporte para rodar a newsletter "Robozinho dos Momozis até Passar" como rotina de nuvem (cloud agent agendado), em vez de tarefa agendada local.

## Fluxo de uma execução (desde 16/11/2026)

Seis turnos do orquestrador; cada um é uma mensagem com todas as suas chamadas (`ROTINA.md`):

1. **Âncora** — `work/inicio.py` (data, janela, feriados, assuntos, banca FGV, selos por data, alertas, ledger resumido, prompts dos coletores) já **dispara em segundo plano** `coleta_web.py`, `informativos.py` e `versiculo.py`; o orquestrador lê os três `/tmp/coletor-*.md` e carrega as ferramentas do Gmail e o WebSearch.
2. **Conferência e coleta** — 3 buscas de anti-duplicata no Gmail + os 3 coletores (`.claude/agents/`) + `work/aguardar_coleta.py`, que espera os scripts (ou os roda, se o disparo não estiver lá) e imprime a linha `SOURCE_STATUS`.
3. **Julgamento** (sem chamadas), escrito com a montagem e a leitura numa mensagem: Write de `/tmp/execucao.json` + `work/montar_email.py` (grava `/tmp/email.html` e imprime só `ASSUNTO`, `PARA`, avisos, `BYTES` e `SHA256`) + Read do e-mail.
4. **Rascunho** — `create_draft` com o conteúdo do Read, do começo à sentinela `fim-<execution_id>`.
5. **Conferência, persistência e aviso** — `list_drafts`/`search_threads` com `larger:` (0,9 × BYTES) para conferir o tamanho, `work/finalizar.sh` (helper + commit + push na `main`) e PushNotification.
6. Uma linha final (ou a 2ª notificação, se algo falhou).

Ramos de exceção (duplicata, coletor que falha, edição Extra, `--refazer`, rascunho menor que o esperado, `PUSH: FALHOU`): `docs/referencia-operacional.md` §R.

## Estrutura

- `ROTINA.md` — prompt que a rotina de nuvem executa (cole o conteúdo no campo de prompt do routine, ou aponte o agente para lê-lo e segui-lo).
- `robozinho-dos-momozis-prompt.md` — prompt mestre: a doutrina editorial (identidade visual, selos, status, seções, autoaprendizagem). Lido só sob demanda, diante de dúvida editorial que a ROTINA não resolva.
- `docs/referencia-operacional.md` — seções operacionais do prompt mestre que raramente decidem algo (rotas do DOU, protocolo do Gmail, contingência por fonte, delegação) e os ramos de exceção da ROTINA (§R).
- `.claude/agents/coletor-*.md` — coletores Gmail (haiku), JOTA (sonnet) e Concursos (sonnet) como subagentes próprios, só com as ferramentas de que precisam e o contrato de evidência; entregam pelo SubagentHandback, quando existe.
- `work/prompts/coletor-*.md` — modelos dos prompts dos coletores, preenchidos pelo `inicio.py` (janela, notas do ledger, pendências, prazos, rodízio, descoberta, ids dos concursos acompanhados).
- `work/inicio.py` — passo 1: âncora de data, janela (teto de 7 dias), feriados, assuntos, Munger (`tipo` lição/aforismo), prazos e selo por data dos concursos, leitura da banca FGV, páginas oficiais com `url_oficial`, teste de rede, alertas (prazo vencido, candidato a remoção, dia útil sem execução registrada, pendência no limite), o LEDGER enxuto e os prompts prontos; dispara os scripts do passo 2. `--extra` (edição extraordinária), `--refazer` (rascunho apagado sem envio), `--sem-disparo` (ou `ROBOZINHO_DISPARO=0`).
- `work/aguardar_coleta.py` — passo 2: espera os scripts disparados pelo `inicio.py` (teto de 240 s contados do disparo, não da chamada: `--teto`; a espera extra da §R4 calcula o teto pelo tempo decorrido), roda-os ali se não houver disparo (`--rodar` força) e imprime as saídas e a linha `SOURCE_STATUS`.
- `work/coleta_web.py` — Congresso (leis e MPVs), ConJur e Migalhas, com hora exata, dedupe contra o histórico, `[REPETIDA?~chave]` e ids curtos (`lei15527`, `c7`, `m3`) que o orquestrador cita por `ref`; nova tentativa em falha transitória.
- `work/informativos.py` — Informativo STF (com o RESUMO oficial de cada julgado), Repercussão Geral em Pauta (estágio de cada tema: tese, votação, pauta) e Informativo STJ (Repetitivo/RQF/órgão), direto do documento oficial; edições novas, atrasadas, puladas e as revisitas "em atraso", sem sondar edição impossível.
- `work/versiculo.py` — versículo do dia (DailyVerses.net; o YouVersion só é sondado às segundas, e o anti-bot dele não é erro).
- `work/jota_extrair.py` — texto compacto dos boletins do JOTA salvos em arquivo, sem as URLs de rastreio: cada link vira `[L<n>]` num índice; descadastro e propaganda ficam fora.
- `work/resolver_jota.py` — resolve os links do JOTA (por índice ou wrapper) sem seguir redirecionamento às cegas, só no `jota.info`, recusa descadastro/preferências, confere o título e marca `JA_PUBLICADA` o que já saiu; `BLOQUEADO` sem rede.
- `work/montar_email.py` — passos 4/5: lê o julgamento (`/tmp/execucao.json`, que nunca sobrescreve), resolve os `ref`, deriva o mecânico (selo por data, carimbo da banca, linha de apoio, "sem link", `impacto`, grupo do Planalto, concursos compactos), descarta o repetido certo das seções de apoio, valida e grava o corpo em `/tmp/email.html` (ou `/tmp/email-com-avisos.html` com aviso acionável) e a versão resolvida em `/tmp/execucao.resolvido.json`. `--com-html` imprime o corpo, só para depuração.
- `work/bancas.py` — leitura determinística da banca oficial FGV (situação, arquivos datados e retificações, trechos do edital, `DIVERGE DO REGISTRO`), com as URLs já vistas em `work/concursos-estado.json`.
- `work/selos.py` — regras dos concursos: selo por data (só com prazo confirmado), padrão de prova da validação, candidato a remoção, `mudou_em`.
- `work/feriados.py` — feriados nacionais, pontos facultativos e os da Justiça Federal (Lei 5.010/66, art. 62).
- `work/paginas_oficiais.py` — lê a página oficial profunda (`url_oficial`) dos concursos em foco e acusa mudança só nos trechos com palavras-chave.
- `work/repeticao.py` — detecção de matéria repetida: identidade numérica (tipo + número) antes da semelhança de título.
- `work/Update-Historico.py` — helper de gravação (porte em Python do antigo `Update-Historico.ps1` do Windows, que não faz parte deste repositório): merge, reconciliação (só vira `sent` com o message id), arquivamento (máx. 10), validação de itens e de `ledger_updates` (padrão de prova dos concursos), contadores, mecânico dos concursos, medição de uso e estado. `--validar` é chamado pelo montador.
- `work/finalizar.sh` — passo 7: helper (a partir do `execucao.resolvido.json`) + commit + push para `main`, só com `STATUS: OK`; se a `main` andou no remoto, reaplica o helper sobre ela (sem rebase textual dos JSON); em falha definitiva, cópia do estado em `/tmp/robozinho-estado-backup-<exec>.tar.gz`.
- `work/medir_uso.py` — uso real da sessão (orquestrador e coletores), a partir das transcrições locais, com `custo_relativo`.
- `work/template-newsletter-referencia.html` — amostra do e-mail (conferência visual; a rotina não a lê).
- `work/munger-quotes.json` — base de citações e lições do Munger.
- Estado commitado pelo `finalizar.sh`: `work/robozinho-aprendizado.json` (ledger: fontes, armadilhas, pendências e o registro de concursos), `work/robozinho-estado.json` (resumo e métricas), `work/resumo-legislativo-historico.json` (últimas 10 execuções), `work/resumo-legislativo-historico-arquivo-*.json` (arquivos mensais) e `work/concursos-estado.json` (arquivos da banca já vistos e páginas oficiais; criado pelo helper na 1ª execução).
- `work/testes/test_*.py` — testes sem rede e sem pytest (`python3 work/testes/test_<grupo>.py`): `test_informativos.py`, `test_web.py`, `test_est.py`, `test_mon.py` e `test_doc.py` (coerência da documentação com o código). Fixtures em `work/testes/fixtures/`. Temporários em `ROBOZINHO_TMP` (padrão `/tmp`).

## Métricas de custo

- **`custo_relativo`** (por execução, em `orquestrador` e `coletores` no histórico): o custo em unidades do preço do token de **entrada do próprio modelo** — entrada × 1 + cache lido × 0,1 + cache gravado × 1,25 + saída × 5 (`medir_uso.PESOS`). Substitui o antigo `contexto_total`, que media quase só a leitura de cache (cerca de 4% do custo) e escondeu a alta de 13/11. Execução antiga é estimada pelos agregados. O estado guarda `metricas.orquestrador_custo_relativo_ultimas_10` e `metricas.orquestrador_custo_relativo_mediana`.
- **`ALERTA_ECONOMIA`** (no relatório do `finalizar.sh`): custo relativo do orquestrador acima de 1,3 × a mediana das 10 execuções anteriores com medição.
- **`ALERTA: modelo do orquestrador mudou`**: o `custo_relativo` não enxerga troca de modelo (é relativo ao preço de cada um); este alerta, sim. Os dois vão para a notificação do dia.

## Decisão pendente do dono: modelo do orquestrador

O orquestrador rodou em `claude-sonnet-5-5` até 12/11 e em `claude-fable-5-2` desde 13/11 — troca feita na configuração da rotina agendada, fora deste repositório, sem registro; o `.claude/settings.json` continua dizendo `claude-sonnet-5-5`. O Fable custa cerca de 4 vezes mais por token, e o orquestrador é cerca de 85% do custo de uma execução. Recomendação da revisão de 16/11: um replay dos passos 3–5 (julgamento e montagem) em Sonnet 5.5 sobre um dia salvo, comparando o `execucao.json` e o e-mail com os do Fable; decidida a escolha, registrá-la aqui e na ROTINA e alinhar (ou remover) a chave `model` do `.claude/settings.json`. Até lá, nada foi mudado na configuração; o `ALERTA` acima avisa de qualquer nova troca.

## Próximos passos (não implementados)

- **Corpo por anexo de referência** (`sha256:<hex>:/tmp/email.html` no `create_draft`) com o Apps Script conferindo o SHA e fazendo `draft.update`/`send` — tiraria a cópia de ~60 mil caracteres do orquestrador (a maior despesa do dia). Exige mudar o `EnviarRobozinho.gs` (fora do repositório) e um teste prévio com rascunho de assunto diferente: o preenchimento do arquivo pode exigir aprovação numa execução agendada. Só se o anexo falhar: o Apps Script lendo o HTML do repositório (a entrega passaria a depender do push).
- **`MAX_MCP_OUTPUT_TOKENS` para o JOTA** (`.claude/settings.json`): mandaria para arquivo todo boletim do JOTA, que então passaria sempre pelo `jota_extrair.py`. Vale para todas as chamadas MCP da sessão: exige uma execução real conferindo que as threads do Gmail oficial continuam inline.
- **Pendências de concurso dentro do registro** (E5/E7): `movimento_em`, `expira_apos` e `fonte_id`, e as pendências de concurso migradas para o próprio registro numa só migração.
- **Write-ahead contra queda** (F1): registro gravado antes do rascunho (`finalizar.sh --pre`), para que uma queda entre o `create_draft` e o push não faça a execução seguinte repetir a edição. Hoje há só o `ALERTA: dia útil sem execução registrada` e a busca em `in:sent`.
- **`gmail_extrair.py`** (B8) e itens dos coletores por referência (B9): extração determinística das threads do Gmail a partir das transcrições, com ids citáveis por `ref`.
- **Armadilhas desatualizadas no ledger:** a regra de `jota_link_wrapper_mismatch` (WebSearch por item) e a de `gmail_after_epoch` ("dia anterior ao início da janela") ficaram para trás do código; `ledger_updates` não permite reescrever a regra de uma armadilha existente.
- Outros: `precedentes.py` do STJ (consulta ainda não descoberta), "Tese fixada" do Informativo STF, paginação de ConJur/Migalhas às segundas, card "Para a prova" no resumo, corte automático do apoio acima de 90 KB, checagem de domínio por fonte no montador e guarda de integridade dos scripts antes do helper (K3).

## Por que este repositório existe

Uma rotina de nuvem (cloud agent agendado) roda isolada: cada disparo clona o repositório do zero e não enxerga o disco do computador local. Para a rotina "lembrar" o que já foi publicado, o próprio agente precisa commitar e dar `git push` nos arquivos de estado de `work/` ao final de cada execução (passo 7 de `ROTINA.md`, `work/finalizar.sh`) — essa é a única forma de persistência entre execuções nesse modelo.

## O que fica de fora

- `EnviarRobozinho.gs` (Apps Script que localiza o rascunho pelo assunto e envia, em varreduras a cada 15 minutos) continua vivendo no Google Apps Script da conta Gmail, associado à planilha/projeto onde já está implantado. A rotina de nuvem só *cria o rascunho*; quem envia é o Apps Script, com o mesmo gatilho de horário.
- Arquivos de histórico mensal antigos e HTMLs de edições passadas não foram trazidos (não são lidos pela rotina).

## Pré-requisitos para a rotina de nuvem funcionar

1. Um conector MCP do Gmail conectado em https://claude.ai/customize/connectors, para a mesma conta usada pelo Apps Script de envio.
2. Este repositório publicado no GitHub (privado, recomendado) e acessível pelo ambiente de nuvem.
3. O routine configurado (via skill `schedule`) apontando para este repositório, com o conector Gmail anexado e `ROTINA.md` como prompt.
