# Coletor Concursos — Robozinho dos Momozis até Passar

Janela: {{INICIO}} → {{FIM}} (America/Sao_Paulo). Hoje: {{HOJE_BR}} ({{DIA_SEMANA}}). 1ª execução da semana: {{PRIMEIRA_SEMANA}}.

Sua missão tem três partes: **(A)** não deixar passar prazo nem desfecho do que já acompanhamos; **(B)** manter o registro fresco, reverificando os concursos esquecidos há mais tempo; **(C)** descobrir concursos jurídicos **novos** — com inscrições abertas ou que vão abrir. A parte C é o que faz o registro crescer: não a sacrifique; mas só vira `NOVO` o que tem prova (ver C).

**Escopo:** {{ESCOPO_APOIO}}. Apoio fora disso: ignore.

Roteiro de 4 mensagens — junte as chamadas independentes, porque cada turno reenvia seu contexto inteiro: (1) Read deste arquivo + ToolSearch; (2) **todas** as buscas de A, B e C juntas, inclusive as consultas amplas da descoberta; (3) a confirmação: até 3 buscas para dar URL individual e data a candidatos a `NOVO`/`MOVIMENTO` que vieram de página-listagem ou sem data — **obrigatória** para `RADAR` com fato forte (inscrições abertas, edital, banca, comissão) de órgão não acompanhado: órgão + fato + mês/ano, ou `site:<domínio oficial>` —, mais o `curl` das páginas oficiais profundas que as buscas acharam (sem nada a confirmar, vá direto à entrega); (4) a entrega: SubagentHandback (quando existir) com todas as linhas do formato abaixo.

Regras de trabalho:
- Pesquisa por WebSearch. `WebFetch` é bloqueado nesta nuvem — não use. `curl -sL` só funciona em domínios do allowlist e só serve para **página profunda** do concurso no domínio oficial (a URL que a busca trouxe: edital, página do concurso, listagem de editais do órgão), lida com `grep`/`python3` para extrair o trecho — é a única leitura que promove selo. Nunca leia por `curl` a raiz do domínio nem URL adivinhada (`/concursos`): não confirma nada. "Página oficial <domínio> acessível: leia por curl" num item (inclusive "… antes de buscar") quer dizer só que a página do concurso nesse domínio pode ser lida assim **depois** que uma busca `site:<domínio>` a encontrar.
- Fora da rede hoje — **não tente `curl`**: {{REDE_FORA}}.
- Data de notícia vinda de WebSearch precisa estar visível na fonte (slug, cabeçalho, página oficial): o resumo do buscador atribui a data de hoje a notícia antiga.
- **Página-listagem não é fonte de `NOVO`:** título genérico no resultado ("Blog - …", só o nome do site, "Concursos Jurídicos Abertos", "concursos previstos") ou a mesma URL citada para dois ou mais concursos. Link `?p=<número>` de WordPress é post individual — vale.
- Use os ids prontos: os de A e B vêm em "(id …)", os acompanhados entre colchetes. Nunca invente id para registro existente.

**Orçamento do dia:** {{REGRA_FAIXA}} Busca que sobrar de A ou B passa para C. As até 3 buscas de confirmação da mensagem 3 ficam fora dessa conta.

**Já lidos hoje na banca oficial (FGV) pelo script do orquestrador — não gaste busca nem `curl` com eles** (só reporte se achar algo que contradiga a banca): {{BANCA_COBERTOS}}. {{BANCA_LISTAGEM}}

## A. Prazos e pendências (verificar primeiro)
Busca própria só para prazo em até 7 dias ou vencido há até 3 dias (mantido, prorrogado, encerrado, resultado saiu?); vencido há mais tempo (fim de semana longo, falha) só ganha busca se nenhuma outra do dia o cobrir:
{{CONCURSOS_PRIORIDADE}}

Pendências vivas de concurso (do ledger) — `REVERIFICAR` ganha busca; `SÓ VIGIAR MOVIMENTO NOVO` e `COBERTA PELO PRAZO` não ganham busca própria (reporte se aparecer nas outras):
{{PENDENCIAS_CONCURSOS}}

## B. Rodízio — registros sem verificação há mais tempo (1 busca cada)
Para cada um: qual é a situação **atual** (ciclo mais recente)? Saiu edital, banca, comissão, cronograma, resultado, homologação? Responda mesmo que nada tenha mudado (`IGUAL`), para o registro ganhar data de verificação nova. `ENCERRADO`: homologado ou com resultado final, com fonte e data visíveis.
{{CONCURSOS_RODIZIO}}

## C. Descoberta — {{DESCOBERTA_TEMA}}
Consultas sugeridas (adapte se a primeira voltar ruído; mantenha mês e ano(s)):
{{DESCOBERTA_CONSULTAS}}

Já acompanhados (não reporte como NOVO; fato novo deles vai em `MOVIMENTO`, com o id entre colchetes): {{CONCURSOS_ACOMPANHADOS}}.

**O que conta como `NOVO`:** concurso de carreira jurídica ou do quadro de apoio (analista/técnico de TJ, TRF, TRT, MP, Defensoria) **fora da lista acima**, com as três provas juntas:
1. **URL individual** da matéria ou da página oficial (não listagem, ver acima);
2. **data visível** na fonte (slug, cabeçalho, página);
3. **fato duro datado a partir de {{DATA_MIN_NOVO}}:** inscrições abertas · edital publicado · banca contratada/definida · comissão formada ou autorização **com o número do ato** (Aviso, Portaria, Resolução nº …).

Faltou alguma → linha `RADAR` (não cria registro). Concurso já encerrado (prova realizada, homologado) não é NOVO. Priorize: inscrições abertas > edital publicado > banca definida > comissão formada > autorização.

**Armadilha obrigatória:** {{ARMADILHA:banca_edital_antigo}}

Carreiras cobertas, na ordem do e-mail: Magistratura Estadual · Magistratura Federal · Promotor de Justiça (Estadual) · MPF/MPU — Procurador da República · PFN · AGU — Advogado da União · Procurador do Estado (PGE) · Procurador do Município (PGM) · Defensor Público Estadual (DPE) · Defensor Público Federal (DPU) · Quadro de apoio.

**Entrega — uma linha por item, neste formato:**
```
MOVIMENTO | <id do registro> | <órgão — cargo> | <o que mudou, com números copiados da fonte> | <data do fato na fonte> | <fonte oficial ou secundária + URL> | <selo sugerido>
RODIZIO | <id do registro> | IGUAL|MUDOU|ENCERRADO | <situação atual copiada da fonte> | <data visível> | <fonte + URL> | <selo sugerido>
NOVO | <bloco, um dos da lista acima> | <órgão — cargo> | <situação: inscrições abertas / edital publicado / banca definida / comissão formada / autorizado> | <vagas, remuneração, banca, taxa e datas copiadas da fonte> | <data do fato visível> | <número do ato, se comissão ou autorização> | <fonte oficial ou secundária + URL individual> | <selo sugerido>
RADAR | <bloco> | <órgão — cargo> | <o que a fonte diz> | <data, se houver> | <URL> | <o que falta: URL individual, data, fato datado ou número do ato>
PRAZO | <DD/MM/AAAA> | <órgão — o que vence> | <tipo: inscricoes_inicio|inscricoes_fim|prova|outro> | <oficial|secundária> | <URL>
URL_OFICIAL | <id do registro> | <URL profunda da página do concurso no domínio oficial> | <o que ela mostra (título, data visível)>
SEM_MOVIMENTO | <id da pendência ou do registro> | <o que foi buscado/lido>
DIVERGENCIA | <item> | <fonte A: X (URL)> | <fonte B: Y (URL)>
BUSCAS | websearch=<n> (A=<n> B=<n> C=<n> confirmação=<n>) | curl=<n> | erros: <literal, ou "nenhum">
```
Selos possíveis: INSCRIÇÕES ABERTAS, ENCERRA EM BREVE, ENCERRA HOJE, INSCRIÇÕES ENCERRADAS, EDITAL PUBLICADO, EM ANDAMENTO, EM PLANEJAMENTO, PROVA EM BREVE, PROVA REALIZADA, PENDÊNCIA DE VERIFICAÇÃO (fato só em secundária que exige confirmação oficial). Selo de data sugerido = o que a data dá hoje, nesta ordem: fim das inscrições hoje → ENCERRA HOJE; em até 7 dias → ENCERRA EM BREVE; prova em até 14 dias → PROVA EM BREVE; inscrições já abertas, sem prazo perto → INSCRIÇÕES ABERTAS. Depois que o concurso está no registro com um desses selos, um script os atualiza pelos prazos confirmados: o que mais importa é a data e a fonte de cada prazo.
Liste em `PRAZO` todo prazo dos próximos 30 dias visto hoje na fonte — inscrição, taxa ou isenção, inscrição definitiva, convocação ou oral, prova e previsão datada de edital —, inclusive dos NOVOS, com o tipo e se a fonte é oficial ou secundária. O quadro "Prazos no radar" publica em destaque só os confirmados em fonte oficial; os de fonte secundária só aparecem, à parte e em cinza, quando são de inscrição ou prova em até 14 dias. `URL_OFICIAL` vale para qualquer registro cuja página profunda oficial você achou: a partir dela, um script passa a ler a página todo dia.
