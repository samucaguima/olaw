# APIs do DJEN e do DataJud: contrato verificado

Verificação de 10/10/2026, feita sobre chamadas reais e respostas armazenadas no projeto Supabase `samuel-guimaraes-advogado` (região sa-east-1, São Paulo), onde a captura do DJEN já opera em produção. Nenhum teor de comunicação foi copiado para este documento; constam apenas rotas, parâmetros, nomes de campos e estatísticas de funcionamento.

## 1. DJEN (API de comunicações processuais do CNJ)

### 1.1 Restrição de origem

**[FATO-DOC]** A API bloqueia requisições de IPs fora do Brasil (registro operacional da rotina "Varredura DJEN nacional"; confirmado pelo sucesso das chamadas a partir de São Paulo e pela recusa a partir do ambiente de nuvem desta sessão). **Consequência de projeto:** todo coletor do DJEN roda em infraestrutura hospedada no Brasil (hoje, o banco Supabase em sa-east-1).

### 1.2 Requisição

`GET https://comunicaapi.pje.jus.br/api/v1/comunicacao`

| Parâmetro | Uso verificado |
|---|---|
| `numeroOab` | Número da OAB, sem UF (ex.: `107046`) |
| `ufOab` | UF da inscrição (ex.: `RS`) |
| `siglaTribunal` | Opcional. Omitido, a consulta é nacional (todos os tribunais que publicam no DJEN) |
| `dataDisponibilizacaoInicio`, `dataDisponibilizacaoFim` | `AAAA-MM-DD` |
| `itensPorPagina` | Usado com `100` |
| `pagina` | A partir de `1` |

Cabeçalhos usados: `Accept: application/json` e `User-Agent: Mozilla/5.0`. Sem autenticação.

### 1.3 Resposta

Envelope: `status`, `message`, `count` (total de itens da consulta, não da página) e `items` (lista).

Campos de cada item (todos presentes nas 42 comunicações armazenadas):

| Campo | Tipo | Observação |
|---|---|---|
| `id` | número | Identificador da comunicação; chave de deduplicação |
| `hash` | texto | Usado na rota de certidão |
| `numeroComunicacao` | número | |
| `data_disponibilizacao`, `datadisponibilizacao` | texto | Duas grafias para a mesma data; o coletor usa `data_disponibilizacao` |
| `siglaTribunal` | texto | |
| `numero_processo` | texto | NPU sem máscara |
| `numeroprocessocommascara` | texto | NPU com máscara |
| `codigoClasse`, `nomeClasse` | texto | |
| `idOrgao`, `nomeOrgao` | número, texto | Órgão julgador |
| `tipoComunicacao`, `tipoDocumento` | texto | |
| `meio`, `meiocompleto` | texto | |
| `texto` | texto | Teor em HTML |
| `link` | texto ou nulo | Nulo em 2 dos 42 itens |
| `ativo`, `status` | booleano, texto | |
| `data_cancelamento`, `motivo_cancelamento` | nulo | Previstos para comunicações canceladas |
| `destinatarios` | lista | Itens com `nome`, `polo`, `comunicacao_id` |
| `destinatarioadvogados` | lista | Itens com `id`, `advogado` (objeto), `advogado_id`, `comunicacao_id`, `created_at`, `updated_at` |

### 1.4 Comportamento observado

- Chamadas de 10/10/2026, às 09:30 e às 16:00 UTC: HTTP 200 nas três páginas.
- 09/10/2026, 16:00 UTC: HTTP 503 nas três páginas, com mensagem de sistema em manutenção.
- 09/10/2026, 09:30 UTC: uma página sem resposta em 30 segundos (timeout).
- **Consequência de projeto:** o coletor repete a consulta em horário posterior quando houver 503 ou timeout, e o painel trata a ausência de resposta como falha de coleta, nunca como ausência de publicações (plano, Seção 3, princípio 6).

## 2. DataJud (API pública do CNJ)

Teste real em 10/10/2026, a partir do banco em São Paulo (requisições HTTP do próprio Postgres), com um processo da carteira por tribunal. A chave pública é a publicada pelo CNJ e já usada pela rotina do titular; ela não é versionada neste repositório.

### 2.1 Requisição

`POST https://api-publica.datajud.cnj.jus.br/api_publica_<alias>/_search`

Cabeçalhos: `Authorization: APIKey <chave pública>` e `Content-Type: application/json`. Corpo: `{"query":{"match":{"numeroProcesso":"<NPU sem máscara>"}}}`.

### 2.2 Resultado por tribunal

| Alias | Status | Registros | Sistema informado | Última atualização do registro | Último movimento | Observação |
|---|---|---|---|---|---|---|
| `tjrs` | 200 | 2 (G1 e G2) | Projudi | 09/09/2026 | 28/08/2026 | Processo do eproc informado como "Projudi" |
| `tjsc` | 200 | total 1, lista vazia | não informado | não informado | não informado | O índice acusa o processo, mas não entrega o conteúdo |
| `tjpr` | 200 | 1 | Eproc | 08/07/2026 | 30/06/2026 | |
| `tjsp` | 200 na 2ª tentativa | 1 (G1) | Projudi | 10/08/2026 | 01/07/2026 | 1ª tentativa sem resposta em 30 s; respondeu com limite de 90 s. Processo do e-SAJ ou eproc informado como "Projudi" |
| `trf4` | 200 | 2 (JE e TR) | Projudi | 11/03/2026 | 11/11/2025 | Processo do eproc informado como "Projudi" |
| `trt4` | 200 | 2 | PJe | 09/08/2026 | 11/11/2025 | |

### 2.3 Estrutura da resposta

Envelope Elasticsearch: `took`, `timed_out`, `_shards`, `hits` (`total.value`, `hits[]`). Cada item de `hits[]` traz `_id`, `_index`, `_score` e `_source`, com os campos: `@timestamp`, `assuntos`, `classe`, `dataAjuizamento`, `dataHoraUltimaAtualizacao`, `formato`, `grau`, `id`, `movimentos`, `nivelSigilo`, `numeroProcesso`, `orgaoJulgador`, `sistema`, `tribunal`. Cada movimento: `codigo`, `nome`, `dataHora`, `orgaoJulgador`, `complementosTabelados`.

### 2.4 Consequências de projeto

1. **Um processo, vários registros.** O DataJud devolve um registro por grau ou instância (G1, G2, JE, TR). O coletor agrega todos e ordena os movimentos por `dataHora`.
2. **Defasagem real e grande.** O último movimento disponível tinha de 6 semanas a 11 meses de atraso em 10/10/2026. Confirma a regra do plano: o DataJud nunca abre prazo; serve para capa, classe, assuntos, órgão julgador e histórico.
3. **Campo `sistema` não confiável.** Processos que tramitam no eproc (TJRS e TRF4) aparecem como "Projudi". O sistema de cada processo é definido pelo cadastro e pelo robô, nunca pelo DataJud.
4. **Resposta vazia não é ausência.** `total.value` maior que zero com `hits` vazio (TJSC) e timeout (TJSP) são tratados como "sem dados utilizáveis", com nova tentativa, e não como processo inexistente.
5. **Origem.** O DataJud respondeu a partir do Brasil; a partir do ambiente de nuvem desta sessão, a rede foi recusada pela política do ambiente (não por bloqueio do CNJ). As rotinas do titular já o consultam a partir de sessões na nuvem.

## 3. Normas de contagem conferidas no texto integral

Páginas oficiais obtidas na íntegra em 10/10/2026, a partir do Brasil, e lidas nos dispositivos abaixo. Rótulo: **[FONTE]**.

| Norma | Dispositivo | Conteúdo conferido | Página oficial |
|---|---|---|---|
| Res. CNJ 569/2024 (situação: vigente) | Art. 1º, que dá nova redação ao art. 11, § 3º, da Res. CNJ 455/2022 | Quando a lei não exigir vista ou intimação pessoal, os prazos processuais contam da publicação no DJEN, na forma do art. 224, §§ 1º e 2º, do CPC; a intimação concomitante por outros meios tem valor meramente informacional | https://atos.cnj.jus.br/atos/detalhar/5691 |
| Res. CNJ 569/2024 | Art. 2º (art. 18 da Res. 455/2022) | O Domicílio Judicial Eletrônico é usado exclusivamente para citação eletrônica e comunicações que exijam vista, ciência ou intimação pessoal | idem |
| Lei 11.419/2006 | Art. 4º, §§ 3º e 4º | Publicação no primeiro dia útil seguinte à disponibilização; prazos a partir do primeiro dia útil seguinte à publicação | https://www.planalto.gov.br/ccivil_03/_ato2004-2006/2006/lei/l11419.htm |
| Lei 11.419/2006 | Art. 5º, §§ 1º a 3º | Intimação em portal próprio: considerada feita na consulta, ou automaticamente após 10 dias corridos do envio | idem |
| CPC | Art. 219 | Contagem em dias úteis, somente para prazos processuais | https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/l13105.htm |
| CPC | Art. 220 | Suspensão do curso do prazo processual de 20 de dezembro a 20 de janeiro, inclusive | idem |
| CPC | Art. 224, caput e §§ 1º a 3º | Exclusão do dia do começo; prorrogação do começo e do vencimento por expediente alterado ou indisponibilidade; publicação no primeiro dia útil seguinte à disponibilização; contagem a partir do primeiro dia útil seguinte à publicação | idem |
| CPC | Art. 231, VII | Dia do começo: data de publicação, quando a intimação se der pelo Diário da Justiça | idem |
| CPC | Art. 229, § 2º | Prazo em dobro de litisconsortes com procuradores distintos não se aplica a autos eletrônicos | idem |
| CPC | Art. 1.003, § 6º | O recorrente comprova a ocorrência de feriado local no ato de interposição | idem |

Prazos usuais conferidos para a tabela de prazos legais: arts. 183 e 186 (prazo em dobro da Fazenda Pública e da Defensoria), 218, § 3º (5 dias na falta de previsão), 335 (contestação, 15 dias), 350 e 351 (manifestação do autor, 15 dias), 523 (pagamento no cumprimento de sentença, 15 dias), 525 (impugnação, 15 dias), 915 (embargos à execução, 15 dias), 1.003, § 5º (recursos e respostas, 15 dias, salvo embargos de declaração), 1.023 (embargos de declaração, 5 dias) e 1.070 (agravo contra decisão unipessoal em tribunal, 15 dias). Registro em [`dados-publicos/tabela_prazos_legais.csv`](dados-publicos/tabela_prazos_legais.csv).

## 4. Calendário forense

Regra de inclusão: só entra no calendário ([`dados-publicos/calendario_forense.csv`](dados-publicos/calendario_forense.csv)) a data conferida na página oficial. Feriado não confirmado fica de fora, porque um feriado inexistente adiaria o vencimento calculado; a ausência de um feriado real, ao contrário, apenas antecipa a data de controle.

| Conteúdo | Situação | Fonte |
|---|---|---|
| Feriados nacionais de 2026 e 2027: 1º/1, 21/4, 1º/5, 7/9, 2/11, 15/11, 25/12 | **[FONTE]** conferido | Lei 662/1949, art. 1º (redação da Lei 10.607/2002) |
| 12/10 | **[FONTE]** conferido | Lei 6.802/1980, art. 1º |
| 20/11 | **[FONTE]** conferido | Lei 14.759/2023, art. 1º |
| Suspensão dos prazos de 20/12 a 20/1 | **[FONTE]** conferido | CPC, art. 220 |
| TJPR, 2026: feriados e suspensões de expediente | **[FONTE]** conferido na página oficial de notícias do tribunal, que reproduz o Decreto Judiciário 621/2025 | https://www.tjpr.jus.br/noticias/-/asset_publisher/9jZB/content/tjpr-divulga-calend%C3%A1rio-de-feriados-no-ano-de-2026/18319 |
| TJPR, feriados municipais das comarcas e alterações do Decreto Judiciário 88/2026 | **[CONFERIR]** | Tabela anexa ao decreto |
| TJSC, 2026: Resolução GP 1/2026, alterada pelas Resoluções GP 12, 33, 37 e 45/2026 | **[CONFERIR]**: localizada por busca; o portal do TJSC bloqueou a leitura automatizada | https://www.tjsc.jus.br/calendario-institucional |
| TJSP, 2026: Provimento CSM 2.813/2025, alterado pelo 2.845/2026 | **[CONFERIR]**: localizado por busca; a página não respondeu | https://www.tjsp.jus.br/CanaisComunicacao/Feriados/ProcessosFisicos |
| STJ, 2026: Portaria STJ/GDG 1.010/2025; prazos suspensos de 2 a 31/7/2026 (Portaria STJ/GP 455/2026) | **[CONFERIR]**: localizado por busca; o portal do STJ recusou a leitura automatizada | https://www.stj.jus.br/sites/portalp/Paginas/Comunicacao/Noticias/2026/06012026-Portaria-define-feriados-e-pontos-facultativos-do-STJ-em-2026.aspx |
| TJRS, 2026 | **[CONFERIR]**: ato do Órgão Especial de 2026 não localizado; os anos anteriores seguem o mesmo rito (ato anual) | https://www.tjrs.jus.br/novo/noticia/orgao-especial-aprova-calendario-de-feriados-na-justica-estadual-em-2023/ |
| Demais tribunais da carteira (TJMS, TJRJ, TJMT, TJGO, TJDFT, TRF4, TRF1, TRT4, TRT12) | Não pesquisados | |
| Calendários de 2027 dos tribunais | Ainda não publicados em 10/10/2026, salvo verificação em contrário | |

Nenhuma cobertura foi marcada em [`calendario_cobertura.csv`](dados-publicos/calendario_cobertura.csv). Por isso o motor continua sinalizando todo cálculo como "calendário não conferido", e assim deve permanecer até o calendário de cada tribunal e comarca da carteira estar completo.

**[RISCO]** Em 10/10/2026, o portal do TJSC classificou a leitura automatizada como acesso não autorizado e bloqueou temporariamente o endereço de origem (o banco em São Paulo); o portal do STJ recusou a requisição. As consultas a portais de tribunais foram interrompidas. Consequência de projeto: o servidor que captura o DJEN não acessa portais de tribunais; a leitura desses portais fica com a Estação Robô, em sessão autenticada e frequência baixa (plano, Seção 8.3).
