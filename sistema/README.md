# Sistema de gestão jurídica

Implementação do [plano de implementação](../docs/plano-sistema-gestao-juridica.md). Projeto independente do OLAW, que permanece na raiz do repositório sem alteração.

## Situação

| Fase do plano | Entregue neste diretório | Pendente |
|---|---|---|
| 0. Preparação | Sondagem das APIs do DJEN e do DataJud (`sgj/sondagem_apis.py`); [lista de conferência e planilhas-modelo](../docs/fase0/) | Liberação de rede, leitura das fontes, teste real das APIs, planilhas preenchidas, decisões do titular |
| 1. Núcleo e cadastro | Esquema do banco (`sgj/db/migrations/0001_inicial.sql`), com as regras do plano em restrições | API, autenticação, integração com o Drive, dashboard |
| 2. Publicações, prazos e tarefas | Motor de prazos (`sgj/prazos/`) | Coletores, triagem pela IA, tarefas, notificações |

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

## Banco de dados

Implantado em 11/10/2026 no esquema `sgj` do Supabase de produção (São Paulo), ao lado dos esquemas existentes; ver [`docs/implantacao-supabase.md`](../docs/implantacao-supabase.md).

PostgreSQL 16 com pgvector. Além das tabelas da Seção 15 do plano, a migração codifica regras do plano como restrições, verificadas em teste:

- prazo só passa de "sugerido" com aprovação registrada;
- tarefa com prazo processual exige prazo vinculado; movimentação sem publicação não recebe prazo legal;
- minuta com pendência `[CONFERIR]` não pode ser aprovada;
- envio individual só sai com autorização registrada; cobrança só é emitida com aprovação;
- entrada de calendário exige fonte;
- trilha de auditoria imutável (gatilho impede alteração e exclusão).

## Testes

```bash
cd sistema
pip install -e ".[dev]"
pytest
```

Os testes do banco rodam quando `SGJ_TEST_PG_DSN` aponta para um servidor PostgreSQL (banco administrativo); cada execução cria e remove um banco temporário. Sem pgvector instalado no servidor, o tipo `vector` é substituído por um domínio provisório e o índice semântico fica fora do teste.

```bash
pip install "psycopg[binary]>=3.2"
SGJ_TEST_PG_DSN="host=/caminho/do/socket port=5432 user=postgres dbname=postgres" pytest
```

## Dados reais

Planilhas preenchidas, exportações e qualquer dado de cliente ficam fora do repositório (pasta `dados/`, ignorada pelo git, ou Drive). O repositório é derivado (fork) de projeto público; confirme a visibilidade antes de versionar qualquer arquivo com dado real.
