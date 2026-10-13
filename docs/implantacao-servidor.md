# Instalação do aplicativo no servidor

Roteiro para colocar no ar o painel "Meu dia", a Caixa de Publicações e a tela de coletas, num servidor no Brasil, com acesso restrito aos dispositivos do titular. Arquivos em [`sistema/implantacao/`](../sistema/implantacao/).

**Situação em 11/10/2026:** pacote preparado e validado:
- instalação do aplicativo pelo mesmo comando usado na imagem;
- funcionamento com o papel restrito do banco e com a conferência de login;
- aprovação de prazo com registro na auditoria;
- ensaio da quarta etapa numa cópia da estrutura de produção.

A imagem do contêiner não foi construída nesta sessão, porque o ambiente de desenvolvimento não alcança o registro de imagens do Docker; a primeira construção acontece no próprio servidor.

## 1. Como fica

| Peça | Escolha | Motivo |
|---|---|---|
| Servidor | AWS Lightsail, região São Paulo, Ubuntu 24.04, 4 GB | Recomendação do [levantamento de hospedagem](hospedagem-opcoes.md), Seção 8; mesma região do banco |
| Aplicativo | Contêiner Docker, com a porta publicada só no próprio servidor (`127.0.0.1:8000`) | Nada do aplicativo fica exposto à internet |
| Acesso | Rede privada Tailscale, com HTTPS (`tailscale serve`) | Só os dispositivos do titular, conectados à rede privada, alcançam o aplicativo |
| Quem entra | O aplicativo confere o login informado pelo Tailscale (cabeçalho `Tailscale-User-Login`) contra a lista `SGJ_USUARIOS` | Recusa qualquer outro login, mesmo dentro da rede privada |
| Gravações | O aplicativo só aceita gravação (aprovar, arquivar, conferir, cadastrar) que o navegador ateste ter partido das telas do próprio sistema (cabeçalho `Sec-Fetch-Site`, ou `Origin` igual ao endereço) | O Tailscale informa o login em toda requisição que sai do computador do titular, inclusive a que outra página aberta no navegador tente mandar ao sistema; sem essa conferência, a página poderia, por exemplo, arquivar publicações (revisão de segurança de 13/10/2026) |
| Banco | Supabase, com o papel próprio `sgj_app` (migração 0006) | Orientação do Supabase de criar um usuário por serviço, em vez de usar a senha do `postgres` ([documentação](https://supabase.com/docs/guides/database/postgres/roles)) |
| Firewall | Só SSH aceito de fora | Superfície mínima |
| Cópia de segurança | Diária, do esquema `sgj`, cifrada (AES-256), com 30 dias no servidor | Plano, Seção 16 |

O papel `sgj_app` lê o esquema `sgj`. Grava só nas tabelas que o aplicativo altera (clientes, casos, processos, publicações, prazos, tarefas e calendário). Não exclui registros, não altera a auditoria e não acessa os esquemas `djen`, `public`, `iris` e `cron`; a tela de coletas os consulta por duas funções de leitura.

## 2. Antes de começar

1. Quarta etapa aplicada no Supabase: script `aplicar_etapa4_supabase.sql`, que contém as migrações 0005 (coleta do DJEN por processo) e 0006 (papel do aplicativo). Registro em [`implantacao-supabase.md`](implantacao-supabase.md), Seção 8.
2. Conta na AWS, para o Lightsail, e conta no Tailscale (plano pessoal). **[CONFERIR]** preço e condições nas páginas oficiais: https://aws.amazon.com/lightsail/pricing/ e https://tailscale.com/pricing.
3. Um gerenciador de senhas, para guardar a senha do papel `sgj_app` e a senha das cópias de segurança.

## 3. Passo a passo

### 3.1 Criar o servidor

No console do Lightsail:
1. Create instance.
2. Região: São Paulo.
3. Linux/Unix, OS Only, Ubuntu 24.04 LTS.
4. Plano de 4 GB. Nome: `sgj`.

Depois de criado, na aba Networking, remova a regra HTTP (porta 80) e mantenha só SSH (porta 22).

### 3.2 Senha do papel do aplicativo

Gere uma senha só com letras e números, para não exigir codificação na conexão. No terminal do servidor (passo 3.3) ou em qualquer computador com OpenSSL:

```bash
openssl rand -hex 24
```

No SQL Editor do Supabase, habilite o login do papel com essa senha:

```sql
ALTER ROLE sgj_app WITH LOGIN PASSWORD 'cole-aqui-a-senha-gerada';
```

Guarde a senha no gerenciador de senhas.

### 3.3 Instalar

Abra o terminal do servidor pelo botão "Connect using SSH" do Lightsail e execute:

```bash
sudo apt-get update && sudo apt-get install -y git
sudo git clone --branch ccr-f37a444e-64vhr1 https://github.com/samucaguima/olaw.git /opt/sgj
sudo bash /opt/sgj/sistema/implantacao/instalar.sh
```

A primeira execução:
- instala Docker, Tailscale e o firewall;
- cria o arquivo de configuração e a senha das cópias de segurança;
- para, pedindo o preenchimento da configuração.

Quando o trabalho desta etapa for incorporado ao ramo principal do repositório, o `--branch` passa a ser `main`.

### 3.4 Configurar

```bash
sudo nano /opt/sgj/sistema/implantacao/.env
```

- `SGJ_DB_DSN`: no painel do Supabase, botão Connect, opção Session pooler, copie a cadeia de conexão. Nela, troque o usuário `postgres.<ref>` por `sgj_app.<ref>` e a senha pela do passo 3.2.
- `SGJ_USUARIOS`: o seu login no Tailscale (aparece no console do Tailscale, em Users), em letras minúsculas.

Execute de novo `sudo bash /opt/sgj/sistema/implantacao/instalar.sh`. Desta vez, o aplicativo é construído e iniciado.

### 3.5 Rede privada

No servidor:

```bash
sudo tailscale up
sudo tailscale serve --bg 8000
sudo tailscale serve status
```

1. O primeiro comando mostra um endereço para entrar na sua conta do Tailscale.
2. O segundo publica o aplicativo só na rede privada, com HTTPS.
3. O terceiro mostra o endereço de acesso (`https://sgj.<sua-rede>.ts.net`).

Instale o aplicativo do Tailscale no celular e no computador, entre com a mesma conta e abra esse endereço.

**[CONFERIR]** Comandos e comportamento do `tailscale serve`, inclusive o envio do cabeçalho de identidade aos serviços locais: https://tailscale.com/kb/1312/serve. Instalação no Ubuntu: https://tailscale.com/kb/1031/install-linux. Nunca use o `tailscale funnel`, que publicaria o aplicativo na internet.

### 3.6 Conferir

- O painel abre, e o topo mostra "rede privada · seu login".
- A tela Coletas mostra as quatro rotinas e os agendamentos.
- No servidor, `curl -s http://127.0.0.1:8000/saude` responde `{"banco":"ok"}`.
- Teste da cópia de segurança: `sudo /opt/sgj/sistema/implantacao/copia_seguranca.sh` informa o arquivo gravado.

## 4. Operação

| Ação | Comando no servidor |
|---|---|
| Atualizar para a versão mais recente | `sudo bash /opt/sgj/sistema/implantacao/atualizar.sh` |
| Ver os registros do aplicativo | `cd /opt/sgj/sistema/implantacao && sudo docker compose logs --tail 100` |
| Reiniciar o aplicativo | `cd /opt/sgj/sistema/implantacao && sudo docker compose restart` |
| Ver as cópias de segurança | `sudo ls -lh /var/backups/sgj` (registro em `/var/log/sgj-copia.log`) |
| Trocar a senha do papel | `ALTER ROLE sgj_app WITH PASSWORD '...'` no SQL Editor; atualizar o `.env`; `sudo docker compose up -d` |

Para conferir uma cópia de segurança, restaure sempre num banco separado, nunca no de produção:

```bash
sudo gpg --batch --pinentry-mode loopback --passphrase-file /etc/sgj/copia.senha \
  --decrypt /var/backups/sgj/<arquivo>.sql.gz.gpg | gunzip > /tmp/conferencia.sql
```

## 5. Segurança e riscos

- **[RISCO]** Até o login próprio do sistema (Fase 1), entra quem estiver na rede privada com um login autorizado. Por isso:
  - proteja a conta usada no Tailscale com segundo fator;
  - remova do console do Tailscale qualquer dispositivo perdido.
- **[RISCO]** As cópias de segurança ficam no próprio servidor: a perda do servidor leva junto as cópias. A cópia externa, no Drive, entra com o Google Workspace. **[CONFERIR]** a retenção de cópias do próprio Supabase no plano contratado.
- **[RISCO]** Sem a senha de `/etc/sgj/copia.senha`, as cópias não podem ser abertas. Guarde-a fora do servidor.
- Quem tem acesso SSH ao servidor alcança o aplicativo diretamente. Mantenha o acesso SSH restrito à chave do Lightsail.
- As ações no sistema ficam registradas em nome do titular; a identificação por usuário entra com o login próprio.

## 6. Como desfazer

```bash
sudo tailscale serve reset
cd /opt/sgj/sistema/implantacao && sudo docker compose down
```

No Supabase, desabilite o login do papel: `ALTER ROLE sgj_app WITH NOLOGIN;`. A instância pode então ser excluída no console do Lightsail.
