# Implantação no Supabase de produção

Projeto `samuel-guimaraes-advogado` (região sa-east-1, São Paulo, PostgreSQL 17). Registro da implantação de 11/10/2026, autorizada pelo titular.

## 1. O que foi feito

| Ordem | Ação | Resultado conferido |
|---|---|---|
| 1 | Verificação prévia | Nenhum esquema `sgj` ou de cópia existente; pgvector disponível (0.8.0) e não instalado; esquema `extensions` existente |
| 2 | Cópia de segurança no esquema `bkp_20261011` | 22 tabelas de `public`, `iris` e `djen` copiadas, com contagens idênticas às originais; segurança por linha ativada e nenhum privilégio para `anon` e `authenticated` |
| 3 | Migração `sgj_0001_inicial` (arquivo [`sistema/sgj/db/migrations/0001_inicial.sql`](../sistema/sgj/db/migrations/0001_inicial.sql), sem as linhas de transação) | 30 tabelas no esquema `sgj`, todas com segurança por linha; pgvector 0.8.0 no esquema `extensions`; `anon` e `authenticated` sem acesso ao esquema; migração registrada no histórico do projeto |
| 4 | Conferência das tabelas existentes | As 22 tabelas de `public`, `iris` e `djen` intactas, com as mesmas contagens (ex.: 97 processos, 28 tarefas, 42 comunicações do DJEN) |
| 5 | Carga de referência | 2 usuários (titular e usuário técnico de verificação automatizada, perfil leitura); 10 prazos legais; 135 dias de calendário (feriados nacionais 2026 e 2027, suspensão do art. 220 do CPC e calendário 2026 do TJPR), todos com fonte oficial |
| 6 | Segunda etapa (Seção 6), executada pelo titular no SQL Editor às 08h49 UTC | Resultado idêntico ao esperado em todos os itens da Seção 6.3; as 22 tabelas de `public`, `iris` e `djen` com as mesmas contagens da cópia de segurança |
| 7 | Terceira etapa (Seção 7), executada pelo titular no SQL Editor às 08h53 UTC | 3 prazos legais de termo manual; agendamentos, chave do DataJud e acesso conferidos (Seção 7.4) |

Os prazos legais e o calendário ficaram registrados como conferidos pelo usuário técnico "Claude (verificação automatizada em fonte oficial)", para distinguir essa verificação da conferência pessoal do titular. Nenhuma cobertura de calendário foi marcada.

## 2. Acesso

O esquema `sgj` não é exposto pela API pública do Supabase. Sem políticas de segurança por linha, apenas o proprietário das tabelas e papéis com permissão de ignorar essas regras (como a chave de serviço, usada no servidor) leem ou gravam. O acesso pelo dashboard será aberto na Fase 1, com políticas explícitas por perfil de usuário.

## 3. Como desfazer

- Remover o novo sistema, sem efeito sobre `public`, `iris` e `djen`: `DROP SCHEMA sgj CASCADE;`
- A extensão pgvector pode permanecer; para removê-la, `DROP EXTENSION vector;`, desde que nenhum outro objeto dependa dela.

## 4. Cópia de segurança

- Cada tabela foi copiada como `bkp_20261011.<esquema>__<tabela>`, com os dados e sem índices, restrições ou gatilhos.
- Restauração de uma tabela (somente em caso de perda, e após conferência): `INSERT INTO <esquema>.<tabela> SELECT * FROM bkp_20261011.<esquema>__<tabela>;`, depois de esvaziar a tabela de destino e verificar dependências.
- **[RISCO]** A cópia duplica dados pessoais de clientes dentro do mesmo projeto. Recomenda-se removê-la após 30 dias de operação sem incidentes: `DROP SCHEMA bkp_20261011 CASCADE;`

## 5. Apontamentos do verificador de segurança do Supabase

Após a implantação, o verificador apontou:

| Apontamento | Origem | Situação |
|---|---|---|
| Tabelas com segurança por linha e sem políticas (nível informativo) | `sgj` e `bkp_20261011`: proposital (acesso bloqueado pela API). `public`, `iris` e `djen`: configuração anterior | Sem ação |
| Funções com `search_path` mutável (nível de alerta) | Anteriores à implantação: `public.buscar_autos`, `public.limpar_texto_djen`, `public.cnj_decodificar`, `iris.norm_fone`, `iris.norm_nome` | Correção recomendada em etapa própria, com teste de cada função ([orientação do Supabase](https://supabase.com/docs/guides/database/database-linter?lint=0011_function_search_path_mutable)) |
| Extensão `pg_net` no esquema `public` (nível de alerta) | Anterior à implantação; usada pela captura do DJEN | Mover exige ajustar as funções `djen.disparar` e `djen.coletar`; manter até a revisão da captura ([orientação do Supabase](https://supabase.com/docs/guides/database/database-linter?lint=0014_extension_in_public)) |

A função criada pela implantação (`sgj.auditoria_imutavel`) tem `search_path` fixo e não aparece entre os apontamentos.

## 6. Segunda etapa: importação da carteira e ligação com o DJEN

**Situação:** aplicada em produção em 11/10/2026, às 08h49 UTC, pelo titular, no SQL Editor do Supabase, com o script único `aplicar_etapa2_supabase.sql` (migração, importação, ligação e conferência numa só transação), entregue fora do repositório. Antes, a etapa foi preparada e testada (63 testes em PostgreSQL local, com tabelas de protótipo e de captura que reproduzem a estrutura de produção), e a ferramenta de acesso ao Supabase cancelou os pedidos de alteração do banco. Executada pelo SQL Editor, a migração não consta do histórico de migrações do projeto, que registra apenas `sgj_0001_inicial`; o registro fica neste documento. Conferência em produção na Seção 6.3.

Decisão do titular em 11/10/2026: o CPF ou CNPJ dos clientes será informado depois.

### 6.1 O que a migração `sgj_0002_importacao_prototipo` faz

Arquivo: [`sistema/sgj/db/migrations/0002_importacao_prototipo.sql`](../sistema/sgj/db/migrations/0002_importacao_prototipo.sql).

- Torna opcionais o CPF ou CNPJ e o tipo de pessoa do cliente; quando o documento for informado, o tipo deve corresponder a ele (11 dígitos, PF; 14, PJ).
- Cria a marca de cliente provisório, que reúne os casos de processos sem nome de cliente.
- Torna opcional o sistema do processo e exige a fonte da confirmação (`djen`, `robo` ou `titular`) sempre que ele for preenchido (Seção 23.6 do plano, decisão 1).
- Acrescenta às publicações o identificador da comunicação no DJEN, o tribunal que publicou (cujo calendário rege a contagem), o órgão, a classe, o tipo de documento e o link.
- Cria a tabela `sgj.importacao_legado`, que liga cada registro do protótipo ao registro novo e guarda os valores de origem não aproveitados (grafia original do tribunal e da área, situação, pasta local, avaliação da IA antiga).
- Cria as funções `sgj.importar_carteira_prototipo()` e `sgj.sincronizar_djen()`, repetíveis e sem efeito sobre as tabelas de origem.
- Agenda `sgj.sincronizar_djen()` às 09h55 e às 16h55 UTC (job `sgj-sincronizar-djen`), depois das coletas do esquema `djen`. Os quatro agendamentos existentes e as funções do esquema `djen` não são alterados.

### 6.2 Regras da importação

| Dado | Regra | Base |
|---|---|---|
| Tribunal | Segmento J.TR da numeração única | **[FATO-DOC]** Coincidência em 97 de 97 processos com o tribunal informado no protótipo e com a sigla das comunicações do DJEN; código fora da tabela conferida interrompe a importação do processo, com aviso |
| Cliente | Um por nome, sem distinção de maiúsculas, acentos e espaços | Nome com anotação ou com mais de uma pessoa entra como está e gera item de conferência |
| Processo sem nome de cliente | Cliente provisório "Cliente a identificar" (C0000) | Item "Identificar o cliente" na tarefa de conferência |
| Caso | Um por processo, com o tipo de ação e a parte contrária do protótipo no título | Agrupamento de processos do mesmo caso fica para o titular |
| Área | `civel_bancario` e `bancario`: bancário; `civel` e `cível`: cível; trabalhista, previdenciário e criminal mantidos; demais grafias ("revisar", "a definir", "federal", vazio): a definir | Item de conferência com a grafia original |
| Sistema e grau | Endereço do documento e órgão da comunicação mais recente no DJEN (eproc, PJe, STJ) | **[FATO-DOC]** Comunicação oficial do próprio processo; sem comunicação com endereço, o sistema fica a confirmar |
| Comarca, órgão e classe | Comunicação mais recente do tribunal de origem no DJEN ("Comarca de ...") | **[FATO-DOC]** Idem |
| Polo | Passivo quando o tipo de ação traz a anotação "(réu)", "(ré)", "(réus)", "(re)" ou "(executado)" | Anotação do titular no protótipo |
| Segredo de justiça | Sim quando o tipo de ação traz "sigiloso"; nos demais, não, até a conferência | Item de conferência em todos os demais |
| Situação "revisar" | Tarefa interna de conferência, com lista só das pendências do processo | Seção 23.4 do plano |
| Publicações do protótipo | Importadas com o identificador do protótipo; ao chegar a mesma comunicação pela captura (mesmo processo, mesma data e mesmo texto), recebem os dados oficiais do DJEN, sem duplicar | Mesmo texto em data diferente é outra publicação |
| Situação da triagem | Todas as publicações entram como capturadas; a avaliação da IA antiga fica no registro de origem | A revisão é do advogado |

### 6.3 Resultado esperado e conferência em produção

O esperado foi calculado em 11/10/2026, antes da execução, por consultas somente de leitura sobre os dados de produção; a conferência, também somente de leitura, foi feita logo depois da execução.

| Item | Esperado | Conferido |
|---|---|---|
| Processos importados | 97 (nenhum ignorado) | 97 |
| Clientes | 57 por nome, mais o cliente provisório, que recebe 32 processos | 58, com o provisório e seus 32 processos; nenhum com CPF ou CNPJ |
| Tarefas de conferência | 97 (96 com o item da situação "revisar") | 97 (96) |
| Áreas | bancário 55, cível 27, trabalhista 5, previdenciário 1, criminal 1, a definir 8 | Idêntico |
| Sistema confirmado pelo DJEN | 15 processos (eproc 10, PJe 2, STJ 3); 82 a confirmar | Idêntico |
| Comarca identificada pelo DJEN | 7 processos | 7 |
| Polo passivo pela anotação | 5 processos | 5 |
| Segredo de justiça pela anotação | 1 processo | 1 |
| Publicações | 285: 249 do protótipo e 36 novas da captura; 6 comunicações presentes nas duas capturas recebem os dados oficiais sem duplicar | 285: 243 só do protótipo e 42 com os dados do DJEN, das quais 6 presentes nas duas capturas |
| Sincronização com o DJEN | Concluída | Concluída (coleta 1, 42 comunicações) |

As 22 tabelas de `public`, `iris` e `djen` mantêm as mesmas contagens da cópia de segurança `bkp_20261011`.

### 6.4 Execução e conferência

```sql
-- 1. Migração 0002 (no SQL Editor, na mesma transação da importação)
-- 2. Importação e ligação
SELECT sgj.importar_carteira_prototipo();
SELECT sgj.sincronizar_djen();
-- 3. Conferência
SELECT (SELECT count(*) FROM sgj.processos) AS processos, (SELECT count(*) FROM sgj.clientes) AS clientes,
       (SELECT count(*) FROM sgj.tarefas WHERE origem = 'importacao') AS tarefas,
       (SELECT count(*) FROM sgj.publicacoes) AS publicacoes,
       (SELECT count(*) FROM sgj.publicacoes WHERE djen_id IS NOT NULL) AS com_dados_do_djen;
```

As tabelas de `public`, `iris` e `djen` devem manter as contagens anteriores, e a coluna `revisada` de `djen.comunicacao` não é tocada.

### 6.5 Como desfazer a segunda etapa

Enquanto não houver lançamento manual no esquema `sgj`:

```sql
SELECT cron.unschedule('sgj-sincronizar-djen');
DELETE FROM sgj.tarefas WHERE origem = 'importacao';
DELETE FROM sgj.publicacoes;
DELETE FROM sgj.coletas WHERE fonte = 'djen';
DELETE FROM sgj.processos;
DELETE FROM sgj.casos;
DELETE FROM sgj.clientes;
DELETE FROM sgj.importacao_legado;
```

### 6.6 Pontos de atenção

- **[RISCO]** O segredo de justiça fica marcado como "não" nos 96 processos sem anotação, até a conferência. Como a IA deve ficar desabilitada para processos sigilosos (Seção 23.6, decisão 10), a triagem da Fase 2 só deve operar em processo com esse item conferido.
- **[RISCO]** O sistema registrado pelo DJEN reflete a comunicação mais recente: processo que voltou do STJ à origem continua marcado como STJ até nova comunicação ou conferência.
- Os 32 processos do cliente provisório vieram da captura automática do protótipo, sem nome de cliente; a identificação depende do titular.
- Nenhum CPF ou CNPJ foi importado, porque o protótipo não os registra.
- **[RISCO]** Sete processos têm publicações registradas e não constam da carteira do protótipo: cinco com comunicações do DJEN entre 16/06 e 06/10/2026 (entre elas, duas sentenças, de 25/09 e de 01/10, um despacho ou decisão, de 06/10, e um ato ordinatório, de 05/10) e dois apenas com intimações do protótipo, de agosto. As 10 publicações ficaram sem processo vinculado; cadastrado o processo, a sincronização seguinte faz a ligação. Cabe ao titular verificar se atua nesses processos e se há prazo em curso.

## 7. Terceira etapa: termo dos prazos legais e coleta do DataJud

**Situação:** aplicada em produção em 11/10/2026, às 08h53 UTC, pelo titular, no SQL Editor, depois da segunda etapa, com o script `aplicar_etapa3_supabase.sql`, entregue fora do repositório porque contém a chave pública do DataJud. Antes, foi preparada e testada (89 testes no total, com pg_net e Vault simulados). Como a segunda, não consta do histórico de migrações do projeto. Conferência em produção na Seção 7.4.

### 7.1 Migração `sgj_0003_termo_prazos_legais`

Arquivo: [`sistema/sgj/db/migrations/0003_termo_prazos_legais.sql`](../sistema/sgj/db/migrations/0003_termo_prazos_legais.sql).

A carga de referência de 11/10/2026 não trouxe as observações da tabela de prazos legais conferida em 10/10/2026. Sem elas, a contestação (CPC, art. 335), os embargos à execução (CPC, art. 915) e a impugnação ao cumprimento de sentença (CPC, art. 525) poderiam ser calculados a partir da publicação no DJEN, o que a própria tabela afasta. A migração cria a coluna `termo` (`publicacao` ou `manual`), marca esses três atos como de controle manual e recupera as observações, inclusive o `[CONFERIR]` do pagamento do art. 523. A Caixa de Publicações recusa o cálculo automático dos atos de termo manual.

### 7.2 Migração `sgj_0004_coleta_datajud`

Arquivo: [`sistema/sgj/db/migrations/0004_coleta_datajud.sql`](../sistema/sgj/db/migrations/0004_coleta_datajud.sql).

| Item | Regra |
|---|---|
| Consulta | `sgj.datajud_disparar(30)`, às 10h20 UTC: até 30 processos de casos não encerrados por dia, começando pelos consultados há mais tempo; a carteira inteira a cada quatro dias, compatível com a defasagem do DataJud |
| Coleta | `sgj.datajud_coletar()`, às 10h30 e às 10h50 UTC: grava os movimentos de todos os registros (um por grau ou instância), sem duplicar |
| Efeito | Movimentação do DataJud nunca abre prazo (plano, Seção 5.4); serve à capa e ao histórico |
| Sigilo | Registro com nível de sigilo maior que zero marca o processo como em segredo de justiça, o que desabilita a IA para ele (efeito só conservador) |
| Falhas | Erro HTTP, resposta vazia e falta de resposta em 6 horas (retenção do pg_net) ficam registrados em `sgj.datajud_requisicao`; o resumo de cada rodada fica em `sgj.coletas` |
| Chave | Vault do Supabase, nome `datajud_api_key`; fora do repositório |
| Aliases | `tjrs`, `tjsc`, `tjpr`, `tjsp`, `trf4` e `trt4` conferidos em chamada real em 10/10/2026; os demais seguem o mesmo padrão de nome e, se recusados, ficam registrados como erro |

### 7.3 Como desfazer a terceira etapa

```sql
SELECT cron.unschedule('sgj-datajud-disparar');
SELECT cron.unschedule('sgj-datajud-coletar');
DELETE FROM sgj.movimentacoes WHERE origem = 'datajud';
DELETE FROM sgj.coletas WHERE fonte = 'datajud';
DROP TABLE sgj.datajud_requisicao;
DELETE FROM vault.secrets WHERE name = 'datajud_api_key';
```

A coluna `termo` pode permanecer: o valor padrão (`publicacao`) reproduz o comportamento anterior.

## 8. Quarta etapa: coleta do DJEN por processo e papel do aplicativo

**Situação em 11/10/2026:** preparada e testada (115 testes) e ensaiada numa cópia da estrutura de produção. Execução pelo titular no SQL Editor, com o script único `aplicar_etapa4_supabase.sql` (migrações 0005 e 0006 numa só transação), entregue fora do repositório. Não altera o esquema `djen` nem os agendamentos existentes.

### 8.1 Migração `sgj_0005_coleta_djen_processo`

Arquivo: [`sistema/sgj/db/migrations/0005_coleta_djen_processo.sql`](../sistema/sgj/db/migrations/0005_coleta_djen_processo.sql). Atende ao risco 1 da Seção 19 do plano (coleta por OAB e por processo).

| Item | Regra |
|---|---|
| Consulta | Mesma API da captura por OAB, a partir do banco em São Paulo, por número de processo de caso não encerrado; publicações dos últimos 7 dias; cada processo uma vez por dia |
| Agenda | A cada 5 minutos, das 11h às 12h55 UTC (8h às 9h55 em Brasília), 10 processos por rodada (job `sgj-djen-processo`), fora dos horários da captura por OAB e do DataJud |
| Gravação | Em `sgj.djen_comunicacao`, só as comunicações que a captura por OAB ainda não tinha; a sincronização passa a ler as duas fontes, sem duplicar |
| Salvaguardas | **[CONFERIR]** o parâmetro `numeroProcesso` consta da API apenas por fontes de terceiros. Por isso: sondagem (um processo por rodada, num dia em que a captura por OAB já registrou comunicação dele, até a resposta trazê-la); resposta com comunicação de outro processo descartada por inteiro; suspensão por 24 horas nesse caso e diante de bloqueio (403) ou excesso de requisições (429); consulta que não traz comunicação já capturada por OAB fica divergente e devolve a coleta à sondagem |
| Utilidade | Comunicação encontrada só pela consulta por processo indica intimação sem a OAB do titular; o total aparece na tela de coletas |

### 8.2 Migração `sgj_0006_acesso_aplicativo`

Arquivo: [`sistema/sgj/db/migrations/0006_acesso_aplicativo.sql`](../sistema/sgj/db/migrations/0006_acesso_aplicativo.sql). Prepara o acesso do aplicativo no servidor ([`implantacao-servidor.md`](implantacao-servidor.md)), conforme a orientação do Supabase de criar um usuário próprio para cada serviço (https://supabase.com/docs/guides/database/postgres/roles, consultada em 11/10/2026).

- Papel `sgj_app`, criado sem login; a senha é definida na instalação do servidor, fora do repositório.
- Lê o esquema `sgj`. Grava só em clientes, casos, processos, publicações, prazos, tarefas e calendário; na auditoria, só inclui. Não exclui registros.
- Política explícita para o papel em cada tabela do esquema `sgj`, que tem segurança por linha ativa.
- Duas funções com o privilégio do proprietário, `sgj.situacao_captura_djen()` e `sgj.agendamentos()`, para a tela de coletas ler a captura do DJEN e os agendamentos sem que o papel receba acesso aos esquemas `djen` e `cron`.

### 8.3 Resultado esperado

| Item | Esperado |
|---|---|
| Agendamentos do sistema | 4 (`sgj-sincronizar-djen`, `sgj-datajud-disparar`, `sgj-datajud-coletar`, `sgj-djen-processo`) |
| Papel do aplicativo | Criado e sem login |
| Políticas | 34, uma por tabela do esquema `sgj` |
| Captura por OAB lida pela função | Número de páginas da última rodada |
| Comunicações na fonte da sincronização | 42 (as da captura por OAB) |

### 8.4 Como desfazer a quarta etapa

```sql
SELECT cron.unschedule('sgj-djen-processo');
-- Reexecutar o CREATE FUNCTION sgj.sincronizar_djen() da migração 0002 como CREATE OR REPLACE.
DROP FUNCTION sgj.djen_processo_rodada(integer, integer), sgj.djen_processo_coletar(),
              sgj.djen_processo_disparar(integer, integer), sgj.djen_processo_pedir(bigint, text, date, date, boolean),
              sgj.djen_fonte(), sgj.situacao_captura_djen(), sgj.agendamentos();
DROP TABLE sgj.djen_comunicacao, sgj.djen_requisicao;
DO $$ DECLARE t text; BEGIN
    FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'sgj' LOOP
        EXECUTE format('DROP POLICY IF EXISTS aplicativo ON sgj.%I', t);
    END LOOP;
END $$;
REVOKE ALL ON ALL TABLES IN SCHEMA sgj FROM sgj_app;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA sgj FROM sgj_app;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA sgj FROM sgj_app;
REVOKE USAGE ON SCHEMA sgj FROM sgj_app;
DROP ROLE sgj_app;
```

As publicações que a consulta por processo trouxe para `sgj.publicacoes` permanecem: são comunicações oficiais do DJEN.

### 7.4 Conferência em produção

Consultas somente de leitura, em 11/10/2026, depois das duas etapas:

| Item | Conferido |
|---|---|
| Termo dos prazos legais | 3 atos de controle manual (contestação, embargos à execução, impugnação ao cumprimento de sentença); observações recuperadas em 9 dos 10 prazos (os embargos de declaração não têm observação na tabela conferida) |
| Agendamentos | `sgj-sincronizar-djen` (09h55 e 16h55 UTC), `sgj-datajud-disparar` (10h20 UTC) e `sgj-datajud-coletar` (10h30 e 10h50 UTC), ativos e executados pelo papel `postgres`; os quatro agendamentos do esquema `djen` mantêm horários e comandos |
| Chave do DataJud | No Vault, com o nome `datajud_api_key`, legível pelo papel dos agendamentos (verificado sem exibir o valor) |
| Respostas do pg_net | Legíveis pelo papel dos agendamentos |
| Processos a consultar | 97, nenhum de caso encerrado: a carteira inteira em quatro rodadas |
| Acesso | Todas as tabelas do esquema `sgj` com segurança por linha; nenhuma das tabelas nem das 11 funções do esquema acessível a `anon` ou `authenticated` |
| Primeira rodada automática | 11/10/2026, conferida às 11h09 UTC: sincronização com o DJEN às 09h55 UTC concluída, sem comunicação nova; consulta ao DataJud às 10h20 UTC com 30 processos, todos com resposta HTTP 200, 28 com registros (3.138 movimentações gravadas, 28 processos sincronizados) e 2 do TJRS sem registros utilizáveis, que voltam à fila; coletas das 10h30 e das 10h50 UTC concluídas. Consultas por tribunal: TJRS 13 (11 com registros), TJPR 6, TJSC 4, TRT4 2 e TJDFT, TJMS, TJMT, TJRJ e TJSP 1 cada. Nenhum processo marcado como sigiloso pelo DataJud; o único sigiloso segue sendo o da anotação do protótipo, ainda não consultado |
