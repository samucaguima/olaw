#!/usr/bin/env bash
# Atualiza o aplicativo com a versão mais recente do repositório:
#   sudo bash /opt/sgj/sistema/implantacao/atualizar.sh
set -euo pipefail
AQUI="$(cd "$(dirname "$0")" && pwd)"
git -C "$AQUI/../.." pull --ff-only
cd "$AQUI"
docker compose up -d --build
docker image prune -f >/dev/null
docker compose ps
