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

Ver Seção 2 abaixo, preenchida após o teste.
