# Fase 0: lista de conferência

Referência: [plano de implementação](../plano-sistema-gestao-juridica.md), Seção 18. A Fase 0 termina quando todos os itens marcados como **saída** estiverem concluídos.

## Situação em 10/10/2026

- **Concluído:** contrato das APIs do DJEN e do DataJud verificado em chamadas reais a partir do Brasil (itens B.5, B.6 e C); normas de contagem conferidas no texto integral (itens B.1 a B.4); tabela de prazos legais e calendário nacional, art. 220 do CPC e TJPR 2026 conferidos (Seção D, parcial); decisões da Seção F aceitas pelo titular. Registro em [`apis-verificadas.md`](apis-verificadas.md).
- **Pendente:** calendários de 2026 do TJRS, TJSC, TJSP e STJ, feriados municipais e calendários de 2027; itens B.7 a B.15; contas da Seção E. A carteira já existe no Supabase do titular e será importada pelo sistema, sem planilha.
- **Rede:** liberar domínios neste ambiente de nuvem não resolveria o DJEN, que recusa origem fora do Brasil. Os coletores rodam no banco em São Paulo.

## A. Liberação de rede do ambiente

Em 10/10/2026, a política de rede do ambiente de execução recusou a conexão aos domínios abaixo (resposta "403 Forbidden" do proxy, registrada pela sondagem da Seção C). A liberação é feita nas configurações do ambiente: menu do ambiente na barra de título da sessão, Edit, Network access, Allowed domains ([instruções](https://code.claude.com/docs/en/cloud-environments#network-access)).

- `comunicaapi.pje.jus.br`, `comunica.pje.jus.br`, `hcomunicaapi.cnj.jus.br`
- `api-publica.datajud.cnj.jus.br`, `datajud-wiki.cnj.jus.br`
- `www.cnj.jus.br`, `atos.cnj.jus.br`, `formularios.cnj.jus.br`, `docs.pdpj.jus.br`
- `www.planalto.gov.br`
- `www.tjrs.jus.br`, `www.tjsc.jus.br`, `www.tjpr.jus.br`, `www.tjsp.jus.br`, `esaj.tjsp.jus.br`, `www.stj.jus.br`, `centraldeajuda.stj.jus.br`, `portal-eproc.trf4.jus.br`
- `docs.asaas.com`, `developers.chatwoot.com`, `www.chatwoot.com`, `developers.google.com`, `developers.openai.com`, `help.openai.com`, `developers.facebook.com`, `www.oab.org.br`

## B. Leitura integral das fontes [CONFERIR]

Cada item altera uma regra do sistema. Registrar, ao lado, a data da leitura e o resultado.

| # | O que conferir | Fonte | Efeito no sistema | Situação |
|---|---|---|---|---|
| 1 | Redação vigente do art. 11, § 3º, da Res. CNJ 455/2022 (texto compilado): prazo contado da publicação no DJEN | https://atos.cnj.jus.br/files/compilado18070620250603683f39ca8ca16.pdf | DJEN como gatilho único de prazo (plano, Seção 5.2) | ☐ |
| 2 | Comunicado do CNJ sobre a contagem exclusiva pelo DJEN desde 16/05/2025 | https://www.cnj.jus.br/cnj-alerta-tribunais-sobre-novas-regras-de-contagem-de-prazos-processuais/ | Idem | ☐ |
| 3 | Lei 11.419/2006, art. 4º, §§ 3º e 4º, e art. 5º | https://www.planalto.gov.br/ccivil_03/_ato2004-2006/2006/lei/l11419.htm | Constantes de fundamento do motor de prazos (`sgj/prazos/motor.py`) | ☐ |
| 4 | CPC, arts. 219, 224 e 231, VII | https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/l13105.htm | Regras de publicação, início, dias úteis e prorrogação do motor | ☐ |
| 5 | Swagger oficial da API de comunicações do DJEN: rota pública de consulta, parâmetros, campos, limites | https://www.cnj.jus.br/programas-e-acoes/processo-judicial-eletronico-pje/comunicacoes-processuais/orientacoes-aos-tribunais/ | Coletor do DJEN; se não houver rota pública, contingência da Seção 5.1 | ☐ **saída** |
| 6 | DataJud: chave pública vigente, aliases, formato de consulta e termo de uso | https://datajud-wiki.cnj.jus.br/api-publica/acesso/ ; https://formularios.cnj.jus.br/wp-content/uploads/2023/05/Termos-de-uso-api-publica-V1.1.pdf | Coletor do DataJud e limite de requisições | ☐ **saída** |
| 7 | eproc: "Preparar Movimentação" e salvamento de inicial, nos manuais do TJRS, TJSC e TJPR | https://www.tjsp.jus.br/Download/EPROC/ManuaisPublicoExterno/1.4-EPROC-ADVOGADO-EXTERNO-Como-peticionar-intermediarias_23.04.26.pdf (referência do TJSP) | Nível 2 de preparação do protocolo | ☐ |
| 8 | e-SAJ: "Salvar para protocolar depois" e se o cadastro da petição exige login por certificado | https://www.tjsp.jus.br/Download/SPI/Downloads/Apostila-PETIC-ELETRONICO-Novo-Portal-Peticionamento-Intermediario-13-05-2024.pdf | Nível 2 ou Nível 1 no e-SAJ | ☐ |
| 9 | Segundo fator no eproc do TJRS e do TJSC; validade da sessão após retirada do token A3 | https://www.tjrs.jus.br/novo/eproc/duvidas-frequentes/ | Modelo de sessão assistida | ☐ |
| 10 | Limites de arquivo do eproc do TJPR, do Projudi e do e-SAJ | Manuais dos tribunais | Pré-voo dos PDFs (plano, Seção 8.6) | ☐ |
| 11 | Asaas: autenticação, webhooks, limites | https://docs.asaas.com/docs/webhook-para-cobrancas | Fase 5 | ☐ |
| 12 | Chatwoot: Agent Bot, modelos de WhatsApp, campanhas | https://www.chatwoot.com/hc/user-guide/articles/1677497472-how-to-use-agent-bots | Fase 5 | ☐ |
| 13 | Google: escopos `drive` e `gmail.*`, isenção de verificação para aplicativo interno | https://developers.google.com/workspace/guides/configure-oauth-consent | Fase 1 | ☐ **saída** |
| 14 | OpenAI: retenção de dados, Zero Data Retention, residência de dados | https://developers.openai.com/api/docs/guides/your-data | Pedido de ZDR; avaliação de tratamento de dados | ☐ |
| 15 | Provimento CFOAB 205/2021 e eventual atualização | https://www.oab.org.br/leisnormas/legislacao/provimentos/205-2021 | Campanhas por WhatsApp (Fase 5) | ☐ |

## C. Teste real das APIs

Executar após a liberação da rede, a partir do diretório `sistema/`. A saída mostra apenas status HTTP e nomes de campos, nunca valores.

```bash
pip install -e ".[dev]"

# DataJud: chave pública copiada da página oficial (item B.6)
export DATAJUD_API_KEY='...'
python -m sgj.sondagem_apis datajud --tribunal tjrs --npu <NPU de processo da carteira, 20 dígitos>

# DJEN: ajustar nomes de parâmetros com --param conforme o Swagger (item B.5)
python -m sgj.sondagem_apis djen --oab 107046 --uf RS --data <AAAA-MM-DD de dia com publicação conhecida>
```

Registrar o resultado (status e estrutura) no item correspondente. **Saída:** as duas chamadas com status 200 e estrutura documentada, ou contingência do DJEN definida.

## D. Planilhas a preencher

Modelos em [`modelos/`](modelos/). Não incluir dados de clientes em repositório público; as planilhas preenchidas ficam no Drive (`99_Sistema/`).

| Planilha | Conteúdo | Colunas |
|---|---|---|
| `inventario_carteira.csv` | Um processo por linha | código e nome do cliente; tipo de pessoa (PF/PJ); CPF ou CNPJ só com dígitos; código e título do caso; NPU com 20 dígitos; tribunal; comarca; sistema (`eproc`, `esaj`, `projudi`, `pje`, `cpe_stj`); grau; polo; segredo de justiça (sim/não) |
| `tabela_prazos_legais.csv` | Um tipo de ato por linha, conferido pelo titular | tipo de ato; dias; contagem (`uteis` ou `corridos`); dispositivo; link oficial; data e autor da conferência |
| `calendario_forense.csv` | Feriados, suspensões, indisponibilidades e expedientes alterados | `data_inicio` e `data_fim` (AAAA-MM-DD; `data_fim` vazio para um só dia); `tipo` (`feriado`, `suspensao`, `indisponibilidade`, `expediente_alterado`); `tribunal` (sigla, ou `*` para nacional); `comarca` (vazio para todo o tribunal); `descricao`; `fonte` (link obrigatório) |
| `calendario_cobertura.csv` | Anos conferidos por tribunal e comarca | tribunal; comarca (vazio para o tribunal sem feriados municipais); ano; quem conferiu; quando |

O motor de prazos marca como **não confiável** todo cálculo que atravesse ano sem cobertura registrada. **Saída:** inventário completo; calendário de 2026 e 2027 conferido para cada tribunal e comarca da carteira; tabela de prazos legais com os atos mais frequentes.

## E. Contas e acessos

- [ ] Google Workspace com domínio próprio; Drive compartilhado "Gestão Jurídica" (plano, Seção 10)
- [ ] Projeto no Google Cloud com tela de consentimento "Internal"
- [ ] Organização na OpenAI API; pedido de Zero Data Retention
- [ ] Chave de sandbox do Asaas
- [ ] Token de acesso do Chatwoot e identificação da caixa de WhatsApp (Cloud API ou outra)
- [ ] Definição do equipamento da Estação Robô

## F. Decisões do titular

As 13 decisões da [Seção 20 do plano](../plano-sistema-gestao-juridica.md#20-decisões-pendentes-do-titular). **Saída:** decisões 1, 2, 3, 8, 12 e 13 tomadas.
