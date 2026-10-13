# Sistema de gestão jurídica

Implementação do [plano de implementação](../docs/plano-sistema-gestao-juridica.md). Projeto independente do OLAW, que permanece na raiz do repositório sem alteração.

## Situação

| Fase do plano | Entregue neste diretório | Pendente |
|---|---|---|
| 0. Preparação | Sondagem das APIs do DJEN e do DataJud (`sgj/sondagem_apis.py`); [lista de conferência e planilhas-modelo](../docs/fase0/) | Liberação de rede, leitura das fontes, teste real das APIs, planilhas preenchidas, decisões do titular |
| 1. Núcleo e cadastro | Esquema do banco (`sgj/db/migrations/0001_inicial.sql`), com as regras do plano em restrições; importação da carteira do protótipo (`0002_importacao_prototipo.sql`); migrações 0001 a 0004 aplicadas em produção em 11/10/2026 ([registro](../docs/implantacao-supabase.md)); papel do aplicativo no banco (`0006`); painel "Meu dia" em ambiente de teste; pacote de instalação no servidor (`implantacao/`) | Aplicação das migrações 0005 e 0006, instalação no servidor, login próprio (Google com segundo fator), integração com o Drive |
| 2. Publicações, prazos e tarefas | Motor de prazos (`sgj/prazos/`); ligação com a captura do DJEN (`sgj.sincronizar_djen`); termo inicial na tabela de prazos legais (`0003`); coleta do DataJud (`0004`); coleta do DJEN por número de processo (`0005`); Caixa de Publicações e saúde das coletas em ambiente de teste (`sgj/caixa/`) | Triagem pela IA, notificações, calendários dos tribunais |

## Motor de prazos

Calcula, a partir da data de disponibilização no DJEN: publicação, início da contagem, vencimento e prazo interno, em dias úteis, com calendário por tribunal e comarca.

Regras de projeto:

- **O calendário é dado, não código.** Nenhum feriado é presumido. Toda ocorrência exige fonte (link do ato). Tipos: `feriado` (sem expediente), `suspensao` (há expediente, prazo não corre), `indisponibilidade` e `expediente_alterado` (prorrogam o começo ou o vencimento).
- **Falha segura.** Cálculo que atravesse ano sem cobertura conferida para o tribunal e a comarca sai marcado como não confiável, com alerta.
- **Data de controle conservadora.** O vencimento sem prorrogação por indisponibilidade é a data de controle; a data prorrogada aparece como informação.
- **Sem presunção de regra.** Contagem em dias corridos é recusada até que o titular defina a regra.
- **Memória de cálculo.** Cada resultado traz a sequência de datas, os dias excluídos com o motivo e a fonte, e os fundamentos aplicados. Os fundamentos legais estão em constantes no início de `motor.py`, conferidos em 10/10/2026 no texto integral das páginas oficiais, com os links em `FONTES`.

```python
from datetime import date
from pathlib import Path

from sgj.prazos import Calendario, calcular_prazo

calendario = Calendario.de_csv(Path("dados/calendario_forense.csv"), Path("dados/calendario_cobertura.csv"))
r = calcular_prazo(calendario, disponibilizacao=date(2026, 8, 3), dias=15, tribunal="TJRS", comarca="Porto Alegre")
r.data_controle, r.prazo_interno, r.alertas, r.memoria
```

## Painel "Meu dia" e saúde das coletas

Tela inicial (plano, Seção 14.1), somente leitura:
- prazos confirmados em ordem de vencimento, com semáforo (vencido, hoje, até 2 dias, até 7 dias), prazo interno e aviso de calendário não conferido;
- publicações a triar e processos com publicação fora da carteira;
- tarefas de prazo por situação e andamento da conferência do cadastro importado;
- carteira por tribunal, com as pendências de cadastro e a cobertura do calendário do ano.

A tela de coletas mostra a situação da captura por OAB, da sincronização, da consulta por processo e do DataJud, com os agendamentos em horário de Brasília. Falta de resposta aparece como falha de coleta, nunca como ausência de publicações.

## Conferência do cadastro e cadastro de processo

A tela de conferência (`/conferencia`) percorre as tarefas de conferência dos processos importados, com publicação mais recente primeiro. Grava sistema, grau, comarca, polo, segredo de justiça, área, cliente (manter, trocar ou cadastrar) e pasta do Drive. Regras:
- item só é concluído se o dado correspondente estiver preenchido (sistema informado, caso fora do cliente provisório, grau e comarca do 1º grau, polo, área, pasta);
- o segredo de justiça exige confirmação expressa, tanto para concluir o item quanto para mudar a informação (sobretudo para retirá-lo), porque dele depende a habilitação da IA;
- se algum item marcado não puder ser concluído, nada é gravado;
- toda alteração vai para a trilha de auditoria, com os valores anterior e novo.

Os processos com publicação fora da carteira podem ser cadastrados pelo painel. O número passa pela conferência do dígito verificador, as publicações já capturadas se ligam ao processo, e uma conferência é aberta com os dados que ficaram faltando.

## Caixa de Publicações (ambiente de teste)

Fluxo da Seção 6.2 do plano sem a IA, que entra quando houver a conta da OpenAI: o advogado abre a publicação, escolhe o ato na tabela de prazos legais (ou informa os dias, com marca `[CONFERIR]`), vê o cálculo do motor com a memória e os alertas e aprova; a aprovação grava o prazo como confirmado, cria a tarefa e registra a auditoria. "Sem providência" arquiva a publicação com o motivo.

Regras aplicadas:

- o calendário usado é o do tribunal que publicou (a publicação do STJ segue o calendário do STJ, ainda que o processo venha do TJRS);
- a comarca só entra no cálculo quando o processo está no primeiro grau do mesmo tribunal; sem grau ou comarca, os feriados municipais ficam de fora (data mais cedo, critério conservador) e o cálculo sai como não confiável;
- ato cujo prazo não corre da publicação no DJEN (contestação, embargos à execução, impugnação ao cumprimento de sentença) é recusado, com a indicação de controle manual;
- o cálculo é refeito no servidor no momento da aprovação; publicação já tratada não é aprovada de novo, e publicação de processo não cadastrado não recebe prazo.

```bash
pip install -e ".[web]"
SGJ_AMBIENTE=teste SGJ_DB_DSN="host=... dbname=..." python -m sgj.caixa   # http://127.0.0.1:8000
```

Ainda sem login próprio, a interface só inicia em dois ambientes:
- `SGJ_AMBIENTE=teste`: atende só no próprio computador;
- `SGJ_AMBIENTE=rede_privada`: no servidor, aceita só pedidos da rede privada Tailscale cujo login conste de `SGJ_USUARIOS` ([roteiro de instalação](../docs/implantacao-servidor.md)).

Nos dois ambientes, gravação só é aceita quando o navegador atesta que partiu das telas do próprio sistema (`Sec-Fetch-Site: same-origin`, ou `Origin` igual ao endereço); assim, outra página aberta no navegador não consegue aprovar, arquivar nem alterar cadastro. No ambiente de teste, o sistema só atende pelos endereços `127.0.0.1` e `localhost`, o que impede outra página de ler os dados trocando o endereço do próprio domínio (DNS rebinding).

A API JSON (`/api/...`) é a base do painel definitivo; a documentação dela (`/api/docs`) só fica disponível no ambiente de teste, porque carrega código de fora.

## Banco de dados

Implantado em 11/10/2026 no esquema `sgj` do Supabase de produção (São Paulo), ao lado dos esquemas existentes; ver [`docs/implantacao-supabase.md`](../docs/implantacao-supabase.md).

PostgreSQL 16 com pgvector. Além das tabelas da Seção 15 do plano, a migração codifica regras do plano como restrições, verificadas em teste:

- prazo só passa de "sugerido" com aprovação registrada;
- tarefa com prazo processual exige prazo vinculado; movimentação sem publicação não recebe prazo legal;
- minuta com pendência `[CONFERIR]` não pode ser aprovada;
- envio individual só sai com autorização registrada; cobrança só é emitida com aprovação;
- entrada de calendário exige fonte;
- trilha de auditoria imutável (gatilho impede alteração e exclusão);
- sistema do processo só é registrado com a fonte da confirmação (DJEN, robô ou titular);
- tipo de pessoa conforme o CPF ou CNPJ, quando informado.

A migração `0002_importacao_prototipo.sql` traz a importação da carteira do protótipo (`sgj.importar_carteira_prototipo()`) e a ligação com a captura do DJEN já existente no banco (`sgj.sincronizar_djen()`, agendada duas vezes ao dia). Ambas são repetíveis e não alteram as tabelas de origem; regras, resultado esperado e conferência em produção em [`docs/implantacao-supabase.md`](../docs/implantacao-supabase.md), Seção 6.

A migração `0003_termo_prazos_legais.sql` registra, na tabela de prazos legais, o termo inicial de cada ato (publicação no DJEN ou controle manual). A `0004_coleta_datajud.sql` cria a coleta do DataJud no próprio banco, pela extensão pg_net: consulta 30 processos por dia, grava os movimentos em `sgj.movimentacoes` (nunca abre prazo) e marca como sigiloso o processo que o DataJud indicar como tal; a chave pública do CNJ fica no Vault do Supabase. Aplicada em produção em 11/10/2026; conferência na Seção 7 do mesmo documento.

A migração `0005_coleta_djen_processo.sql` consulta o DJEN também por número de processo, sem alterar a captura por OAB, e guarda só o que ela ainda não tinha. Começa em sondagem e confere cada resposta com a captura por OAB, porque o parâmetro de consulta por processo não foi conferido em fonte oficial. A `0006_acesso_aplicativo.sql` cria o papel `sgj_app`, usado pelo aplicativo no servidor, com acesso mínimo ao esquema `sgj`. Regras, resultado esperado e reversão na Seção 8 do mesmo documento.

## Testes

```bash
cd sistema
pip install -e ".[dev]"
pytest
```

Os testes do banco rodam quando `SGJ_TEST_PG_DSN` aponta para um servidor PostgreSQL (banco administrativo); cada módulo de teste cria e remove um banco temporário com todas as migrações. Os testes da importação recriam as tabelas do protótipo e da captura do DJEN com a estrutura de produção e dados fictícios. Sem pgvector instalado no servidor, o tipo `vector` é substituído por um domínio provisório e o índice semântico fica fora do teste.

```bash
pip install "psycopg[binary]>=3.2"
SGJ_TEST_PG_DSN="host=/caminho/do/socket port=5432 user=postgres dbname=postgres" pytest
```

## Dados reais

Planilhas preenchidas, exportações e qualquer dado de cliente ficam fora do repositório (pasta `dados/`, ignorada pelo git, ou Drive). O repositório é derivado (fork) de projeto público; confirme a visibilidade antes de versionar qualquer arquivo com dado real.
