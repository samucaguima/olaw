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

**Situação em 11/10/2026:** preparada e testada (63 testes em PostgreSQL local, com tabelas de protótipo e de captura que reproduzem a estrutura de produção). A aplicação em produção aguarda a aprovação do titular na ferramenta de acesso ao Supabase, que exige confirmação para alterar o banco. Nada foi alterado em produção nesta etapa.

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

### 6.3 Resultado esperado

Calculado em 11/10/2026 por consultas somente de leitura sobre os dados de produção:

| Item | Esperado |
|---|---|
| Processos importados | 97 (nenhum ignorado) |
| Clientes | 57 por nome, mais o cliente provisório, que recebe 32 processos |
| Tarefas de conferência | 97 (96 com o item da situação "revisar") |
| Áreas | bancário 55, cível 27, trabalhista 5, previdenciário 1, criminal 1, a definir 8 |
| Sistema confirmado pelo DJEN | 15 processos (eproc 10, PJe 2, STJ 3); 82 a confirmar |
| Comarca identificada pelo DJEN | 7 processos |
| Polo passivo pela anotação | 5 processos |
| Segredo de justiça pela anotação | 1 processo |
| Publicações | 285: 249 do protótipo e 36 novas da captura; 6 comunicações presentes nas duas capturas recebem os dados oficiais sem duplicar |

### 6.4 Execução e conferência

```sql
-- 1. Migração (aplicada pelo histórico de migrações do projeto)
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
