#!/usr/bin/env bash
# Instalação do aplicativo num servidor Ubuntu 24.04 (ex.: AWS Lightsail em São Paulo).
# Executar como root a partir do repositório clonado:
#   sudo bash /opt/sgj/sistema/implantacao/instalar.sh
# Pode ser repetido: cada passo verifica o que já foi feito. Roteiro completo em
# docs/implantacao-servidor.md.
set -euo pipefail

AQUI="$(cd "$(dirname "$0")" && pwd)"
[ "$(id -u)" -eq 0 ] || { echo "Execute como root (sudo)."; exit 1; }
. /etc/os-release
[ "${ID:-}" = "ubuntu" ] || { echo "Roteiro preparado para Ubuntu; sistema encontrado: ${ID:-desconhecido}."; exit 1; }

echo "1. Pacotes do sistema (Docker, Compose, GnuPG, firewall)"
apt-get update -q
DEBIAN_FRONTEND=noninteractive apt-get install -y -q docker.io docker-compose-v2 gnupg ufw curl openssl python3
systemctl enable --now docker

echo "2. Tailscale (repositório oficial)"
if ! command -v tailscale >/dev/null; then
    curl -fsSL "https://pkgs.tailscale.com/stable/ubuntu/${VERSION_CODENAME}.noarmor.gpg" \
        -o /usr/share/keyrings/tailscale-archive-keyring.gpg
    curl -fsSL "https://pkgs.tailscale.com/stable/ubuntu/${VERSION_CODENAME}.tailscale-keyring.list" \
        -o /etc/apt/sources.list.d/tailscale.list
    apt-get update -q && apt-get install -y -q tailscale
fi

echo "3. Firewall: só SSH aceito de fora; o aplicativo não fica exposto à internet"
ufw allow OpenSSH >/dev/null
ufw --force enable >/dev/null
ufw status | head -5

echo "4. Configuração do aplicativo"
if [ ! -f "$AQUI/.env" ]; then
    install -m 600 "$AQUI/.env.exemplo" "$AQUI/.env"
fi
chmod 600 "$AQUI/.env"

echo "5. Senha das cópias de segurança"
install -d -m 700 /etc/sgj
if [ ! -f /etc/sgj/copia.senha ]; then
    (umask 077 && openssl rand -base64 32 > /etc/sgj/copia.senha)
    echo "   Senha criada em /etc/sgj/copia.senha. Guarde uma cópia num gerenciador de senhas:"
    echo "   sem ela, as cópias não podem ser abertas."
fi
cat > /etc/cron.d/sgj-copia <<CRON
# Cópia de segurança diária do esquema sgj (06h30 UTC, 03h30 em Brasília)
30 6 * * * root $AQUI/copia_seguranca.sh >> /var/log/sgj-copia.log 2>&1
CRON
chmod 644 /etc/cron.d/sgj-copia

if grep -v '^#' "$AQUI/.env" | grep -q '<'; then
    echo
    echo "Falta preencher $AQUI/.env (conexão do banco e logins autorizados)."
    echo "Depois, execute de novo: sudo bash $0"
    exit 0
fi

echo "6. Aplicativo"
cd "$AQUI"
docker compose up -d --build
sleep 5
docker compose ps

echo
echo "Próximos passos, se ainda não feitos:"
echo "  tailscale up                 (entrar na rede privada com a sua conta)"
echo "  tailscale serve --bg 8000    (publicar o aplicativo só na rede privada, com HTTPS)"
echo "  tailscale serve status       (mostra o endereço https://... para abrir no navegador)"
