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
