# Opções de hospedagem em nuvem com servidor no Brasil (São Paulo)

**Data da consulta:** 11/10/2026

**Objeto:** hospedagem de sistema de gestão jurídica de advogado individual, composto por uma API em Python (FastAPI) com processo de tarefas em segundo plano e por um painel web (Next.js). O banco de dados permanece no Supabase (região sa-east-1, São Paulo) e não integra este levantamento.

**Requisitos considerados:** endereço público com HTTPS para recebimento de webhooks (Asaas e Chatwoot); servidor fisicamente no Brasil, preferencialmente em São Paulo; configuração mínima de 1 a 2 vCPU, 2 a 4 GB de memória e 40 a 80 GB de disco; uso leve (um ou dois usuários, cerca de 100 processos).

---

## 1. Método e limitações

1. Nenhuma página pôde ser aberta diretamente. A ferramenta de leitura de páginas (WebFetch) retornou erro de resolução de nome em todos os endereços testados, e o acesso pelo terminal foi recusado pela política de rede do ambiente (testes em render.com e docs.aws.amazon.com). Não houve tentativa de contornar o bloqueio.
2. Todos os dados foram extraídos de trechos exibidos em resultados de busca. Por essa razão, todo dado deste documento leva o rótulo **[CONFERIR]**, inclusive quando o trecho provém de página oficial do fornecedor. A seção 7 identifica cada fonte como oficial ou não oficial.
3. Quando a fonte informa apenas o preço por hora, o valor mensal foi obtido pela multiplicação por 730 horas e vem identificado como "cálculo". Não se trata de preço publicado.
4. Os valores constam na moeda da fonte (US$ ou R$), sem conversão e sem tributos, salvo indicação expressa.
5. Quando a fonte não esclarece se o preço inclui disco, tráfego ou IP público, consta "fonte não informa". Quando o preço não foi encontrado, consta "não localizado".
6. Os preços promocionais das hospedagens dependem do prazo de contratação e mudam com frequência. Os valores de renovação foram registrados sempre que disponíveis.

---

## 2. Tabela comparativa (item a)

| # | Fornecedor | Serviço | Região no Brasil | Menor configuração adequada | Preço mensal | Inclui / não inclui | Fontes | Rótulo |
|---|---|---|---|---|---|---|---|---|
| 1 | AWS | Lightsail | Sim: São Paulo (sa-east-1), disponível desde 12/06/2026 | Pacote Small 2 GB: 2 vCPU, 2 GB, 60 GB SSD | US$ 12,00/mês (preço-base do pacote; valor específico para São Paulo não localizado) | Inclui SSD e IPv4 público; franquia-base de 3 TB, que a FAQ indica ser reduzida à metade em São Paulo; excedente de saída a US$ 0,15/GB; IP estático sem custo enquanto anexado | F1 a F5 | [CONFERIR] |
| 2 | AWS | EC2 | Sim: sa-east-1 (São Paulo) | t3a.small: 2 vCPU, 2 GiB, mais volume EBS gp3 de 40 GB | US$ 0,0302/h; cálculo: US$ 22,05/mês (somente a instância) | Não inclui disco (gp3 a US$ 0,152 ou US$ 0,11 por GB-mês, fontes divergentes), IPv4 público (US$ 0,005/h) nem tráfego (franquia de 100 GB/mês; depois US$ 0,15/GB) | F6 a F13 | [CONFERIR] |
| 3 | Google Cloud | Compute Engine | Sim: southamerica-east1 (Osasco, SP) | e2-small: 2 vCPU de núcleo compartilhado, 2 GB, mais disco pd-balanced de 40 GB | US$ 19,41/mês (US$ 0,0266/h) | Não inclui disco (pd-balanced a US$ 0,15/GB-mês), IP externo (US$ 0,005/h) nem tráfego de saída (tarifa não confirmada); a VM gratuita e2-micro só vale em regiões dos EUA | F14 a F17, F24 | [CONFERIR] |
| 4 | Google Cloud | Cloud Run | Sim: southamerica-east1 (faixa de preço "Tier 2") | Serviço de contêiner com cobrança por instância (CPU sempre alocada) ou "worker pool" para a tarefa contínua | Não localizado (cobrança por vCPU-segundo e GiB-segundo, com franquia gratuita mensal) | Inclui URL HTTPS própria (run.app); domínio próprio por mapeamento ainda em prévia; tráfego não confirmado | F18 a F23 | [CONFERIR] |
| 5 | Microsoft Azure | Virtual Machines | Sim: Brazil South (Estado de São Paulo) | B1ms: 1 vCPU, 2 GiB, mais disco gerenciado | US$ 24,53/mês (US$ 0,0336/h) | Não inclui disco gerenciado (preço para Brazil South não localizado), IP público (US$ 0,005/h, fonte não oficial) nem tráfego (100 GB/mês gratuitos; depois US$ 0,181/GB) | F25 a F31 | [CONFERIR] |
| 6 | Oracle Cloud | Compute, camada Always Free | Sim: São Paulo (sa-saopaulo-1) e Vinhedo, SP (sa-vinhedo-1) | VM.Standard.A1.Flex (processador Arm) dentro do limite gratuito: até 2 OCPU e 12 GB desde 15/06/2026 | US$ 0,00 dentro dos limites gratuitos; acima deles, US$ 0,013106 por OCPU-hora e US$ 0,0019659 por GB-hora | Inclui até 200 GB de block volume e 10 TB/mês de saída (dados não confirmados após a mudança de 2026); recursos gratuitos apenas na região principal escolhida no cadastro; relato de falta de capacidade de A1 em São Paulo | F32 a F44 | [CONFERIR] |
| 7 | Magalu Cloud | Virtual Machines | Sim: br-se1 (Grande São Paulo) e br-ne1 (Fortaleza) | BV2-4-40: 2 vCPU, 4 GB, 40 GB NVMe | R$ 102,99/mês (R$ 0,1411/h) | Inclui disco de 40 GB; IP público cobrado à parte (preço não localizado); tráfego de saída cobrado (preço não localizado) | F45 a F50 | [CONFERIR] |
| 8 | Locaweb | VPS Linux | Sim: data center próprio na cidade de São Paulo (fontes não oficiais e antigas) | VPS 2 GB: 2 vCPU, 2 GB, 60 GB SSD | R$ 23,90/mês em contrato de 24 meses (preço cheio R$ 45,90); renovação a R$ 36,90/mês | Fonte não informa IP público nem tráfego | F51 a F54 | [CONFERIR] |
| 9 | Hostinger | VPS (KVM) | Sim: data center de VPS em São Paulo (anunciado em 14/12/2022) | KVM 1: 1 vCPU, 4 GB, 50 GB NVMe | US$ 6,49/mês em contrato de 24 meses, renovação a US$ 11,99/mês (página oficial em inglês); em R$, fontes não oficiais indicam R$ 25,19 a R$ 27,99/mês em promoção, com renovação a R$ 47,99/mês | Inclui 4 TB de banda, backup semanal e acesso root; IPv4 dedicado (fonte não oficial) | F55 a F60 | [CONFERIR] |
| 10 | Vercel | Funções e hospedagem do Next.js (plano Pro) | Sim: gru1 (São Paulo, executada na região AWS sa-east-1) | Plano Pro (o plano Hobby é restrito a uso pessoal não comercial) | US$ 20,00/mês por assento, com US$ 20 de crédito de uso | Inclui HTTPS automático e 1 TB de transferência em gru1 (excedente a US$ 0,22/GB); não mantém processo contínuo em segundo plano | F61 a F67 | [CONFERIR] |
| 11 | Fly.io | Machines | Sim: gru (São Paulo) | shared-cpu-1x com 2 GB, mais volume se houver necessidade de disco persistente | Não localizado para gru (referência: US$ 10,70/mês em Ashburn, valor anterior a 01/10/2026; fator de São Paulo de 1,6154; memória reajustada em 01/10/2026) | Volume a US$ 0,15/GB-mês; IPv4 dedicado a US$ 2,00/mês (IPv4 compartilhado sem custo, fonte não oficial); saída para a América do Sul a US$ 0,04/GB; HTTPS no endereço fly.dev | F68 a F74 | [CONFERIR] |

---

## 3. Notas por fornecedor

### 3.1 AWS Lightsail [CONFERIR]

* Versões antigas da documentação de regiões do Lightsail não listam São Paulo. O anúncio oficial de 12/06/2026 inclui São Paulo, Hong Kong e Espanha, com o mesmo modelo de preços do serviço [F1].
* Alternativa com 2 vCPU e 4 GB: pacote Medium 4 GB, US$ 24,00/mês, 80 GB SSD, franquia-base de 4 TB, IPv4 público incluído [F2].
* Segundo a FAQ, os pacotes em São Paulo incluem metade da franquia de transferência das demais regiões (cálculo: 1,5 TB no Small 2 GB), e o excedente custa US$ 0,15/GB [F3]. Outro trecho da mesma FAQ não exibiu a linha de São Paulo, o que reforça a necessidade de conferência.
* Relato não oficial menciona a contratação do plano de US$ 5/mês na região sa-east-1 [F5], o que sugere preço igual ao preço-base, sem confirmação oficial.

### 3.2 AWS EC2 [CONFERIR]

* Preços sob demanda em sa-east-1, obtidos de agregador não oficial, sem identificação do sistema operacional no trecho: t3a.small a US$ 0,0302/h [F6]; t3.small a US$ 0,0336/h [F8]; t3a.medium (2 vCPU, 4 GiB) a US$ 0,0605/h, cálculo de US$ 44,17/mês [F7]; t3.medium a US$ 0,0672/h, cálculo de US$ 49,06/mês [F8].
* Preço sob demanda da família t4g (processador Arm) em sa-east-1: não localizado.
* Volume gp3 em sa-east-1: as fontes não oficiais divergem (US$ 0,152/GB-mês [F9]; US$ 0,11/GB-mês [F10]).
* IPv4 público: US$ 0,005 por IP por hora, desde 01/02/2024, em todas as regiões [F11]. Saída para a internet a partir de São Paulo: US$ 0,15/GB após o volume gratuito [F12]; fonte não oficial indica franquia de 100 GB/mês [F13].

### 3.3 Google Cloud Compute Engine [CONFERIR]

* Valores do agregador gcloud-compute.com para southamerica-east1: e2-small a US$ 0,0266/h (US$ 19,41/mês); e2-medium (2 vCPU de núcleo compartilhado, 4 GB) a US$ 0,0532/h (US$ 38,83/mês); disco pd-balanced a US$ 0,15/GB-mês [F14].
* Outro agregador apresenta valor muito superior para e2-small na mesma região (US$ 0,079/h), aparentemente inconsistente [F15].
* IP externo em uso: US$ 0,005/h; IP reservado sem uso: US$ 0,01/h [F16].
* A camada gratuita (uma VM e2-micro) vale apenas em us-west1, us-central1 e us-east1, não em São Paulo [F17].

### 3.4 Google Cloud Run [CONFERIR]

* Disponível em São Paulo [F18]; a região southamerica-east1 integra a faixa de preço "Tier 2" [F19].
* Na cobrança por instância, há franquia gratuita mensal de 240.000 vCPU-segundos e 450.000 GiB-segundos, calculada com base nos preços de us-central1 [F20]. As tarifas por segundo da faixa Tier 2 apresentadas por fontes não oficiais divergem entre si; por isso, não se registrou preço mensal.
* Cada serviço recebe URL HTTPS estável [F21]. O mapeamento de domínio próprio está em prévia e não é recomendado para produção [F22].
* Para processamento contínuo em segundo plano, a documentação descreve os "worker pools" [F23].

### 3.5 Microsoft Azure [CONFERIR]

* Valores do agregador azurespeed.com para Brazil South (730 horas): B1ms a US$ 24,53/mês; B2als_v2 (2 vCPU, 4 GB) a US$ 44,17/mês; B2s (2 vCPU, 4 GB) a US$ 49,06/mês. O trecho não identifica o sistema operacional [F25]. Outra fonte confirma US$ 0,0336/h para B1ms em Brazil South [F26].
* Saída para a internet a partir da América do Sul: 100 GB/mês gratuitos; depois US$ 0,181/GB nos 10 TB seguintes [F27].
* IP público estático Standard: US$ 0,005/h, segundo fonte não oficial [F28]. A página oficial de preços de IP não exibiu os valores no trecho.
* Discos gerenciados são cobrados por faixa de tamanho; preço para Brazil South não localizado [F29].
* A região Brazil South é pareada com South Central US, fora do Brasil; o pareamento é relevante para serviços com replicação geográfica [F30]. Brazil South situa-se no Estado de São Paulo e possui três zonas de disponibilidade [F31].

### 3.6 Oracle Cloud [CONFERIR]

* Regiões: sa-saopaulo-1 (São Paulo) e sa-vinhedo-1 (Vinhedo, SP) [F32, F33].
* Camada Always Free: o limite de A1 foi reduzido de 4 OCPU e 24 GB para 2 OCPU e 12 GB a partir de 15/06/2026, sem anúncio público, segundo fontes não oficiais [F35, F36]. Os trechos da documentação oficial exibem ora o limite antigo, ora o novo (1.500 OCPU-hora e 9.000 GB-hora por mês) [F34]. Há dúvidas de usuários sobre a aplicação dos novos limites a contas pagas [F37].
* Os recursos gratuitos só podem ser criados na região principal (home region), escolhida no cadastro e inalterável [F34, F39]. Para servidor em São Paulo, a região deve ser escolhida no momento do cadastro.
* Há relato, no fórum da Oracle, de indisponibilidade de capacidade A1 em sa-saopaulo-1 [F38].
* As duas VMs AMD gratuitas (VM.Standard.E2.1.Micro) têm 1 GB de memória, abaixo do mínimo exigido, segundo fonte não oficial [F44].
* Fora da camada gratuita: A1.Flex a US$ 0,013106 por OCPU-hora e US$ 0,0019659 por GB-hora, segundo trecho de página de preços da Oracle [F42]; material anterior informava US$ 0,01 e US$ 0,0015 [F43]. Block volume a US$ 0,0255/GB-mês, mais unidades de desempenho (US$ 0,017/GB-mês na opção Balanced) [F41]. Saída de dados: 10 TB/mês gratuitos [F40].

### 3.7 Magalu Cloud [CONFERIR]

* Tabela oficial (indexada há cerca de 277 dias, segundo a busca): BV1-2-10 (1 vCPU, 2 GB, 10 GB) a R$ 44,99/mês; BV2-4-40 (2 vCPU, 4 GB, 40 GB NVMe) a R$ 102,99/mês; BV2-4-100 a R$ 152,99/mês [F45]. A mesma página exibe uma segunda tabela com valores bem maiores (por exemplo, R$ 412,97/mês para BV2-4-40), sem identificação clara do que a diferencia [F45].
* O BV1-2-10 é mais barato, mas tem disco de 10 GB, abaixo do mínimo; o preço de disco adicional (block storage) não foi localizado.
* O IP público é serviço adicional, cobrado à parte [F46]; o tráfego de saída é cobrado [F47]. Valores não localizados.
* Data centers na Grande São Paulo e em Fortaleza [F48]; regiões BR-SE1 e BR-NE1 [F49, F50].

### 3.8 Locaweb [CONFERIR]

* Os valores da página oficial são mensais equivalentes em contrato de 24 meses: VPS 2 GB (2 vCPU, 60 GB SSD) a R$ 23,90 (de R$ 45,90), renovação a R$ 36,90; VPS 4 GB (2 vCPU, 70 GB SSD) a R$ 53,90 (de R$ 89,90) [F51], renovação a R$ 72,90 [F52].
* O plano de entrada (R$ 15,90/mês, 1 GB de memória) não atende ao mínimo de memória [F51].
* Localização: data center próprio na cidade de São Paulo, segundo fontes não oficiais e antigas [F53, F54]. A página oficial consultada não informa a localização exata do VPS.

### 3.9 Hostinger [CONFERIR]

* Data center de VPS em São Paulo anunciado em 14/12/2022 [F55]; a página de VPS no Brasil informa a possibilidade de migrar VPS existente pelo painel [F56].
* KVM 1: US$ 6,49/mês em contrato de 24 meses, renovação a US$ 11,99/mês; inclui 4 TB de banda, backup semanal gratuito e acesso root [F57].
* Em R$: R$ 25,19/mês em promoção (de R$ 69,99), com renovação a R$ 47,99/mês [F58]; outra página indica "a partir de R$ 27,99/mês" [F59]. São fontes não oficiais, possivelmente com links de afiliado.
* Alternativa com 2 vCPU: KVM 2 (2 vCPU, 8 GB, 100 GB NVMe), a R$ 35,09/mês em promoção, com renovação a R$ 69,99/mês [F58].
* IPv4 dedicado incluído, segundo fonte não oficial [F60].

### 3.10 Vercel [CONFERIR]

* A região gru1 (São Paulo) corresponde à região AWS sa-east-1 [F61].
* Plano Pro: US$ 20/mês, com US$ 20 de crédito de uso e um assento incluído; assentos adicionais a US$ 20/mês [F63]. Em gru1, 1 TB de transferência incluído e excedente a US$ 0,22/GB; tabela aplicável ao plano Pro [F62].
* O plano Hobby é restrito a uso pessoal não comercial; uso comercial exige plano Pro ou Enterprise [F64].
* Não há processo persistente: tarefas em segundo plano executam como funções sujeitas a limite de duração [F65]; funções Python podem durar até 30 minutos no plano Pro [F66]. Assim, a Vercel atenderia ao painel Next.js e a rotas da API, mas o processo contínuo de tarefas dependeria de outro serviço.
* Todo deployment é servido por HTTPS, com certificado automático [F67].

### 3.11 Fly.io [CONFERIR]

* A região gru (São Paulo) consta da lista de regiões [F68]. Segundo resumo de terceiros, o projeto de consolidação de regiões não desativou São Paulo; a lista completa não foi confirmada [F69].
* O preço regional corresponde ao preço de Ashburn multiplicado pelo fator da região [F70]. O valor de shared-cpu-1x com 2 GB em Ashburn aparece como US$ 10,70/mês [F70], mas o preço da memória subiu para US$ 6,00/GB-mês em 01/10/2026 [F72]. O fator de faturamento de São Paulo seria 1,6154, segundo pull request no repositório público da documentação [F71]; a própria Fly.io declarou que instalar servidores em São Paulo custa cerca do dobro [F73]. O preço final em gru não foi localizado.
* Volume a US$ 0,15/GB-mês; IPv4 dedicado a US$ 2,00/mês; saída para a América do Sul a US$ 0,04/GB [F70]. IPv4 compartilhado sem custo e HTTPS no endereço fly.dev, segundo fonte não oficial [F74].

---

## 4. Estimativa composta para serviços cobrados por componente (cálculo)

Os totais abaixo são cálculo próprio a partir dos preços unitários citados nas seções 2 e 3 (mês de 730 horas). Não são preços publicados, não incluem tráfego acima das franquias nem tributos, e herdam o rótulo [CONFERIR] de cada componente.

| Opção | Componentes | Total mensal estimado | Rótulo |
|---|---|---|---|
| Lightsail Small 2 GB (referência) | Pacote único, com SSD e IPv4 incluídos | US$ 12,00 | [CONFERIR] |
| Lightsail Medium 4 GB (referência) | Pacote único, com SSD e IPv4 incluídos | US$ 24,00 | [CONFERIR] |
| EC2 t3a.small, gp3 de 40 GB e 1 IPv4 | US$ 22,05 + US$ 6,08 (ou US$ 4,40) + US$ 3,65 | US$ 31,78 (ou US$ 30,10) | [CONFERIR] |
| EC2 t3a.medium, gp3 de 40 GB e 1 IPv4 | US$ 44,17 + US$ 6,08 (ou US$ 4,40) + US$ 3,65 | US$ 53,90 (ou US$ 52,22) | [CONFERIR] |
| Compute Engine e2-small, pd-balanced de 40 GB e IP externo | US$ 19,41 + US$ 6,00 + US$ 3,65 | US$ 29,06 | [CONFERIR] |
| Compute Engine e2-medium, pd-balanced de 40 GB e IP externo | US$ 38,83 + US$ 6,00 + US$ 3,65 | US$ 48,48 | [CONFERIR] |
| Azure B1ms e IP público | US$ 24,53 + US$ 3,65 | US$ 28,18, mais disco gerenciado (não localizado) | [CONFERIR] |
| Azure B2als_v2 e IP público | US$ 44,17 + US$ 3,65 | US$ 47,82, mais disco gerenciado (não localizado) | [CONFERIR] |

---

## 5. Fornecedores descartados (item b)

| Fornecedor | Motivo do descarte | Fontes | Rótulo |
|---|---|---|---|
| Render | Não possui região no Brasil. Regiões disponíveis: Oregon, Ohio e Virgínia (EUA), Frankfurt e Singapura. | F75 | [CONFERIR] |
| DigitalOcean | Não possui região no Brasil. A lista oficial de datacenters (verificada pelo fornecedor em 10/08/2026) não inclui nenhum no Brasil, e o fórum do fornecedor registra ausência de previsão de datacenter brasileiro (resposta sem data no trecho). | F76, F77 | [CONFERIR] |

**Candidatos mantidos com ressalva funcional** (possuem região no Brasil, mas não atendem sozinhos à arquitetura descrita):

* **Vercel:** atende ao painel Next.js e a rotas da API, mas não mantém o processo contínuo de tarefas em segundo plano [F65].
* **Google Cloud Run:** a tarefa contínua exige cobrança por instância ou "worker pool", com custo mensal não localizado [F20, F23].

---

## 6. Critérios objetivos para a escolha (item c)

Os critérios abaixo não estão em ordem de prioridade; a ponderação cabe ao titular.

**Critério 1. Custo mensal total em regime, na moeda de cobrança.**
Forma de aferição: somar, para a mesma configuração, instância, disco, IP público e tráfego estimado, adotando o preço de renovação (e não o promocional) e considerando o prazo mínimo exigido para obter o preço anunciado; registrar separadamente as opções cobradas em R$ e em US$.
Pontos levantados: Locaweb e Hostinger anunciam preço condicionado a contrato de 24 meses, com renovação mais alta [F51, F57, F58]; em EC2, Compute Engine e Azure, disco e IP público são cobrados à parte [F9 a F11, F14, F16, F25, F28]; Lightsail inclui disco e IPv4 no pacote [F2].

**Critério 2. Aderência à arquitetura do sistema.**
Forma de aferição: verificar, para cada opção, se (i) mantém em execução contínua o processo de tarefas em segundo plano junto com a API e (ii) oferece endereço HTTPS estável para os webhooks; classificar como "atende", "atende com ajuste" ou "não atende".
Pontos levantados: os servidores virtuais (Lightsail, EC2, Compute Engine, Azure, Oracle, Magalu, Locaweb e Hostinger) executam processos contínuos, mas o HTTPS depende de domínio e certificado configurados pelo titular, sendo possível o uso de certificado gratuito e automatizado do Let's Encrypt [F78]; Cloud Run fornece URL HTTPS própria [F21], mas o processo contínuo exige cobrança por instância ou "worker pool" [F20, F23]; a Vercel não mantém processo persistente [F65]; a Fly.io fornece HTTPS no endereço fly.dev [F74].

**Critério 3. Localização dos dados e proximidade com o banco de dados.**
Forma de aferição: (i) confirmar, no contrato e na configuração, que servidor, discos e cópias de segurança permanecem no Brasil; (ii) medir, em período de teste, a latência entre o servidor e o banco no Supabase (sa-east-1).
Pontos levantados: Lightsail, EC2 e a região gru1 da Vercel operam na mesma região AWS do banco (sa-east-1) [F1, F61]; a região Brazil South do Azure é pareada com South Central US, fora do Brasil, o que importa para recursos com replicação geográfica [F30]; os demais fornecedores informam data centers no Estado de São Paulo [F24, F32, F48, F53, F55].

**Critério 4. Encargo operacional e estabilidade das condições contratuais.**
Forma de aferição: estimar as horas mensais de manutenção a cargo do titular (atualizações do sistema operacional, renovação de certificados, cópias de segurança); verificar prazo mínimo de contratação, perda de desconto em caso de saída antecipada e histórico de alteração unilateral de condições.
Pontos levantados: a camada gratuita da Oracle teve o limite de A1 reduzido à metade em 15/06/2026, sem anúncio público [F35]; há relato de falta de capacidade de A1 em São Paulo [F38]; a Fly.io reajustou o preço da memória em 01/10/2026 [F72]; a Hostinger inclui backup semanal no KVM 1 [F57].

---

## 7. Fontes

Todas as fontes foram consultadas em 11/10/2026, exclusivamente por trecho de resultado de busca. "Oficial" designa página do próprio fornecedor; "não oficial" designa agregadores, blogs, imprensa ou fóruns de usuários.

| ID | Link | Tipo | Dado extraído |
|---|---|---|---|
| F1 | <https://aws.amazon.com/pt/about-aws/whats-new/2026/06/amazon-lightsail-aws-regions/> | Oficial | Anúncio de 12/06/2026: Lightsail disponível em São Paulo, Hong Kong e Espanha, com o mesmo modelo de preços |
| F2 | <https://docs.aws.amazon.com/lightsail/latest/userguide/amazon-lightsail-bundles.html> | Oficial | Pacotes Linux com IPv4 público: Small 2 GB, US$ 12,00/mês, 2 vCPU, 2 GB, 60 GB, 3 TB; Medium 4 GB, US$ 24,00/mês, 2 vCPU, 4 GB, 80 GB, 4 TB |
| F3 | <https://docs.aws.amazon.com/lightsail/latest/userguide/amazon-lightsail-faq-data-transfer-allowance.html> | Oficial | Excedente em São Paulo: US$ 0,15/GB; pacotes em São Paulo com metade da franquia de transferência |
| F4 | <https://docs.aws.amazon.com/lightsail/latest/userguide/understanding-static-ip-addresses-in-amazon-lightsail.html> | Oficial | IP estático sem custo enquanto anexado a instância |
| F5 | <https://luizpicoli.com/articles/deploying-a-dealership-site-on-aws-lightsail/> | Não oficial | Relato de contratação do plano de US$ 5/mês em sa-east-1 |
| F6 | <https://www.doit.com/compute/spot/sa-east-1/t3a.small> | Não oficial | t3a.small sob demanda em sa-east-1: US$ 0,0302/h |
| F7 | <https://www.doit.com/compute/spot/sa-east-1/t3a.medium> | Não oficial | t3a.medium sob demanda em sa-east-1: US$ 0,0605/h |
| F8 | <https://www.doit.com/compute/spot/sa-east-1/t3.small> e <https://www.doit.com/compute/spot/sa-east-1/t3.medium> | Não oficial | t3.small: US$ 0,0336/h; t3.medium: US$ 0,0672/h |
| F9 | <https://aws-pricing.com/sa-east-1.html> | Não oficial | EBS gp3 em sa-east-1: US$ 0,152/GB-mês |
| F10 | <https://cloudoptimo.com/blog/everything-you-need-to-know-about-aws-ebs-pricing-and-cost-saving-tips/> | Não oficial | EBS gp3 em São Paulo: US$ 0,11/GB-mês |
| F11 | <https://aws.amazon.com/blogs/aws/new-aws-public-ipv4-address-charge-public-ip-insights/> | Oficial | IPv4 público: US$ 0,005 por IP por hora desde 01/02/2024, em todas as regiões |
| F12 | <https://aws.amazon.com/pt/blogs/aws-brasil/ensaios-sobre-transferencia-de-dados-na-aws-1> | Oficial | Saída para a internet em sa-east-1: US$ 0,15/GB após o volume gratuito |
| F13 | <https://www.apptio.com/blog/aws-data-transfer-costs> | Não oficial | São Paulo: 100 GB/mês gratuitos; depois US$ 0,15/GB |
| F14 | <https://gcloud-compute.com/southamerica-east1.html> | Não oficial | e2-small: US$ 0,0266/h (US$ 19,41/mês); e2-medium: US$ 0,0532/h (US$ 38,83/mês); pd-balanced: US$ 0,15/GB-mês |
| F15 | <https://www.devzero.io/instances/gcp/e2-small> | Não oficial | Valor divergente para e2-small em southamerica-east1: US$ 0,079/h |
| F16 | <https://www.doit.com/blog/no-more-free-external-ips-on-google-cloud-how-much-will-it-cost-you> | Não oficial | IP externo em uso: US$ 0,005/h; reservado sem uso: US$ 0,01/h |
| F17 | <https://cloud.google.com/free/docs/compute-getting-started> | Oficial | e2-micro gratuita apenas em us-west1, us-central1 e us-east1 |
| F18 | <https://docs.cloud.google.com/run/docs/locations> | Oficial | Cloud Run disponível em São Paulo |
| F19 | <https://docs.cloud.google.com/functions/1stgendocs/locations> | Oficial | southamerica-east1 na faixa de preço Tier 2 |
| F20 | <https://cloud.google.com/run/pricing> | Oficial | Franquia mensal (cobrança por instância): 240.000 vCPU-segundos e 450.000 GiB-segundos, com base em us-central1 |
| F21 | <https://docs.cloud.google.com/run/docs/triggering/https-request> | Oficial | Todo serviço recebe URL HTTPS estável |
| F22 | <https://docs.cloud.google.com/run/docs/mapping-custom-domains> | Oficial | Mapeamento de domínio próprio em prévia, não recomendado para produção |
| F23 | <https://docs.cloud.google.com/run/docs/configuring/workerpools/workerpools-cost-optimization> | Oficial | "Worker pools" para processamento em segundo plano; preços em dois níveis regionais |
| F24 | <https://cloudprice.net/gcp/regions/southamerica-east1> | Não oficial | southamerica-east1 localizada em Osasco, São Paulo |
| F25 | <https://www.azurespeed.com/AzureVmPricing/Regions/brazilsouth> | Não oficial | Brazil South: B1ms US$ 0,0336/h (US$ 24,53/mês); B2als_v2 US$ 0,0605/h (US$ 44,17/mês); B2s US$ 0,0672/h (US$ 49,06/mês) |
| F26 | <https://sparecores.com/server/azure/Standard_B1ms> | Não oficial | B1ms em Brazil South: US$ 0,0336/h |
| F27 | <https://azure.microsoft.com/en-us/pricing/details/bandwidth/> | Oficial | Saída a partir da América do Sul: 100 GB/mês gratuitos; depois US$ 0,181/GB |
| F28 | <https://community.databricks.com/t5/blogs/blogarticleprintpage/blog-id/Product-Platform-Updates/article-id/60> | Não oficial | IPv4 público estático Standard: US$ 0,005/h |
| F29 | <https://azure.microsoft.com/en-gb/pricing/details/managed-disks/> | Oficial | Discos gerenciados cobrados por faixa de tamanho (valor para Brazil South não exibido) |
| F30 | <https://learn.microsoft.com/en-us/azure/reliability/regions-paired> | Oficial | Brazil South pareada com South Central US, fora do Brasil |
| F31 | <https://www.azurespeed.com/Information/AzureRegions/BrazilSouth> | Não oficial | Brazil South no Estado de São Paulo, com três zonas de disponibilidade |
| F32 | <https://docs.oracle.com/en/cloud/saas/enterprise-performance-management-common/tsepm/opc_gen_2_regions.html> | Oficial | Regiões sa-saopaulo-1 (São Paulo) e sa-vinhedo-1 (Vinhedo) |
| F33 | <https://blogs.oracle.com/cloud-infrastructure/oracle-opens-second-cloud-region-in-brazil-delivering-lower-latency-disaster-recovery-and-more-multicloud-support> | Oficial | Vinhedo como segunda região da Oracle no Brasil |
| F34 | <https://docs.oracle.com/en-us/iaas/Content/FreeTier/resourceref.htm> | Oficial | Recursos Always Free (A1.Flex, 200 GB de block volume, região principal); trechos com limite antigo e novo de A1 |
| F35 | <https://www.infoq.com/news/2026/07/oracle-cloud-free-tier-limits/> | Não oficial | Redução do limite gratuito de A1 para 2 OCPU e 12 GB a partir de 15/06/2026, sem anúncio |
| F36 | <https://linuxiac.com/oracle-quietly-cuts-free-tier-ampere-a1-resources-in-half/> | Não oficial | Confirma a redução pela metade dos recursos A1 gratuitos |
| F37 | <https://community.oracle.com/customerconnect/discussion/964620/do-the-new-reduced-ampere-a1-free-tier-limits-apply-to-existing-users> | Não oficial (fórum de usuários no site da Oracle) | Dúvidas sobre a aplicação dos novos limites |
| F38 | <https://community.oracle.com/CustomerConnect/discussions/tagged/arm> | Não oficial (fórum de usuários no site da Oracle) | Tópico sobre falta de capacidade de A1.Flex em sa-saopaulo-1 |
| F39 | <https://blogs.oracle.com/database/freedom-to-build-announcing-oracle-cloud-free-tier-with-new-always-free-services-and-always-free-oracle-autonomous-database> | Oficial | Serviços Always Free apenas na região principal, inalterável após o cadastro |
| F40 | <https://www.oracle.com/cloud/networking/pricing> | Oficial | Saída de dados: 10 TB/mês gratuitos (inclusive América do Sul) |
| F41 | <https://www.oracle.com/cloud/storage/block-volumes/pricing> | Oficial | Block volume: US$ 0,0255/GB-mês, mais US$ 0,017/GB-mês na opção Balanced |
| F42 | <https://www.oracle.com/cloud/compute/pricing> e <https://www.oracle.com/cloud/iaas-paas/> | Oficial | A1.Flex: US$ 0,013106 por OCPU-hora e US$ 0,0019659 por GB-hora (não foi possível identificar qual das duas páginas exibiu o trecho) |
| F43 | <https://developer.arm.com/community/arm-community-blogs/b/servers-and-cloud-computing-blog/posts/oracle-cloud-infrastructure-arm-based-a1> | Não oficial | Preço anterior de A1: US$ 0,01 por núcleo-hora |
| F44 | <https://selfhost.it.com/blog/oci-free-tier-breakdown> | Não oficial | VMs AMD gratuitas (E2.1.Micro) com 1 GB de memória; 10 TB/mês de saída |
| F45 | <https://magalu.cloud/precos/virtual-machines/> | Oficial | BV1-2-10: R$ 44,99/mês; BV2-4-40: R$ 0,1411/h, R$ 102,99/mês; BV2-4-100: R$ 152,99/mês; segunda tabela com valores maiores |
| F46 | <https://help.magalu.cloud/hc/pt-br/articles/7832857814811-As-inst%C3%A2ncias-j%C3%A1-possuem-IP-p%C3%BAblico> | Oficial | IP público é serviço adicional, cobrado separadamente |
| F47 | <https://docs.magalu.cloud/docs/network/additional-explanations/natgw> | Oficial | Tráfego de saída (Data Transfer Egress) é cobrado |
| F48 | <https://www.datacenterdynamics.com/br/not%C3%ADcias/magalu-lanca-servico-de-nuvem-com-foco-na-digitalizacao-das-empresas-brasileiras/> | Não oficial | Data centers na Grande São Paulo e em Fortaleza (CE) |
| F49 | <https://minhaagenda.cursoseventos.nic.br/files/apresentacao/arquivo/2093/Historico%20Magalu%20Cloud%20-%20Nic.br%20(2025).pdf> | Não oficial (apresentação em evento do Nic.br) | Regiões BR-SE1 e BR-NE1 |
| F50 | <https://www.mobiletime.com.br/noticias/13/12/2024/magalu-cloud-expansao/> | Não oficial | Três regiões no Sudeste (São Paulo) e duas no Nordeste (Fortaleza), em 12/2024 |
| F51 | <https://www.locaweb.com.br/servidor-vps/> | Oficial | VPS 2 GB: 2 vCPU, 60 GB SSD, R$ 23,90/mês (de R$ 45,90), renovação R$ 36,90; VPS 4 GB: 2 vCPU, 70 GB SSD, R$ 53,90/mês (de R$ 89,90); plano de entrada R$ 15,90 com 1 GB; valores em contrato de 24 meses |
| F52 | <https://www.locaweb.com.br/n8n/> | Oficial | Renovação do VPS 4 GB: R$ 72,90/mês |
| F53 | <https://tudosobrehospedagemdesites.com.br/locaweb/> | Não oficial | Data center próprio na cidade de São Paulo |
| F54 | <https://www.datacenterdynamics.com/br/not%C3%ADcias/locaweb-se-consolida-em-hospedagem/> | Não oficial | Data center em São Paulo com cerca de 1.900 m² |
| F55 | <https://www.hostinger.com/blog/?p=4211> | Oficial | Novo data center de VPS em São Paulo (publicação de 14/12/2022) |
| F56 | <https://www.hostinger.com/vps/servers/brazil> | Oficial | VPS no Brasil (AMD EPYC, NVMe); migração de VPS existente pelo painel |
| F57 | <https://www.hostinger.com/vps-hosting.md> | Oficial | KVM 1: 1 vCPU, 4 GB, 50 GB NVMe, 4 TB; US$ 6,49/mês em 24 meses; renovação US$ 11,99/mês; backup semanal gratuito; acesso root |
| F58 | <https://horadecodar.com.br/valor-vps/> | Não oficial | KVM 1: R$ 25,19/mês (de R$ 69,99), renovação R$ 47,99/mês; KVM 2 (2 vCPU, 8 GB, 100 GB): R$ 35,09/mês, renovação R$ 69,99/mês |
| F59 | <https://horadecodar.com.br/quanto-custa-vps/> | Não oficial | KVM 1 a partir de R$ 27,99/mês; KVM 2 a partir de R$ 38,99/mês |
| F60 | <https://www.whtop.com/compare/hostinger,time4vps> | Não oficial | KVM 1 com um IP dedicado |
| F61 | <https://vercel.com/docs/regions> | Oficial | gru1 (São Paulo) corresponde à região AWS sa-east-1 |
| F62 | <https://vercel.com/docs/pricing/regional-pricing/gru1> | Oficial | gru1: 1 TB de transferência incluído; excedente a US$ 0,22/GB; aplicável ao plano Pro |
| F63 | <https://vercel.com/docs/plans/pro-plan> | Oficial | Pro: US$ 20/mês com US$ 20 de crédito; um assento incluído; assento adicional a US$ 20/mês |
| F64 | <https://vercel.com/docs/plans/hobby> e <https://vercel.com/docs/limits/fair-use-guidelines> | Oficial | Hobby restrito a uso pessoal não comercial; definição de uso comercial |
| F65 | <https://vercel.com/docs/frameworks/backend/celery> | Oficial | Sem processo persistente; tarefas executam como funções, com limite de duração |
| F66 | <https://vercel.com/changelog/vercel-functions-can-now-run-up-to-30-minutes> | Oficial | Funções Python e Node.js com até 30 minutos nos planos Pro e Enterprise |
| F67 | <https://vercel.com/docs/cdn-security/encryption> | Oficial | Todo deployment é servido por HTTPS, com certificado automático |
| F68 | <https://fly.io/docs/reference/regions/> | Oficial | Região gru (São Paulo) listada |
| F69 | <https://fly.io/blog/the-region-consolidation-project/> | Oficial | Projeto de consolidação de regiões (lista completa não exibida no trecho) |
| F70 | <https://fly.io/docs/about/pricing/> e <https://fly.io/pricing.md> | Oficial | shared-cpu-1x com 2 GB: US$ 10,70/mês em Ashburn; preço regional pelo fator da região; volume US$ 0,15/GB-mês; IPv4 dedicado US$ 2,00/mês; saída para a América do Sul US$ 0,04/GB |
| F71 | <https://github.com/superfly/docs/pull/2505> | Não oficial (pull request no repositório público da documentação) | Fator de faturamento de São Paulo: 1,6154 |
| F72 | <https://layerbase.com/blog/fly-io-memory-price-increase> | Não oficial | Memória reajustada para US$ 6,00/GB-mês em 01/10/2026 |
| F73 | <https://community.fly.io/t/region-specific-machines-pricing/20690> | Não oficial (fórum no site da Fly.io) | Preços por região; custo de instalação em São Paulo cerca do dobro |
| F74 | <https://alchemy.run/fly/networking> | Não oficial | IPv4 compartilhado sem custo; HTTPS em endereço fly.dev |
| F75 | <https://render.com/docs/regions> | Oficial | Regiões: Oregon, Ohio, Virgínia, Frankfurt e Singapura |
| F76 | <https://docs.digitalocean.com/platform/regional-availability/> | Oficial | Lista de datacenters (verificada em 10/08/2026) sem unidade no Brasil |
| F77 | <https://www.digitalocean.com/community/questions/why-digitalocean-doesn-t-have-a-datacenter-in-brazil> | Não oficial (fórum no site da DigitalOcean) | Sem previsão de datacenter no Brasil |
| F78 | <https://letsencrypt.org/about/> | Oficial (Let's Encrypt) | Autoridade certificadora gratuita e automatizada |

---

## 8. Recomendação técnica [INTERPRETAÇÃO]

A decisão é do titular; a recomendação abaixo aplica os critérios da seção 6 aos dados levantados, todos ainda [CONFERIR].

1. **Opção recomendada: AWS Lightsail em São Paulo, pacote de 4 GB** (US$ 24,00/mês pelo preço-base, com disco e IPv4 incluídos [F2]). Fica na mesma região AWS do banco no Supabase (sa-east-1), tem preço fixo por pacote e um único servidor atende à API, ao processo de tarefas e ao painel. O pacote de 2 GB (US$ 12,00/mês) tende a ficar justo quando entrarem a fila de tarefas, a conversão de documentos e o OCR previstos na Seção 16 do plano. Antes de contratar, conferir na página oficial a disponibilidade da região de São Paulo e o preço local.
2. **Alternativa na mesma linha:** EC2 (t3a.medium) ou Google Compute Engine (e2-medium), com disco e IP cobrados à parte, na faixa de US$ 48 a US$ 54/mês pelo cálculo da seção 4. Mais flexíveis, porém mais caros e com mais itens de cobrança.
3. **Se a prioridade for pagar em reais com contrato brasileiro:** VPS da Locaweb ou da Hostinger, com o custo do contrato de 24 meses e do preço de renovação, e com a localização do servidor a confirmar no contrato.
4. **Não recomendados para o servidor principal:** a camada gratuita da Oracle (limites reduzidos sem anúncio e relato de falta de capacidade em São Paulo) e a Vercel isoladamente (não mantém o processo contínuo de tarefas).
