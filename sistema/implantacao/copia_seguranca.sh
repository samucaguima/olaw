#!/usr/bin/env bash
# Cópia de segurança do esquema sgj: pg_dump, compressão e cifra AES-256 com a
# senha de /etc/sgj/copia.senha; retenção de 30 dias em /var/backups/sgj.
# Executada todo dia pelo agendamento /etc/cron.d/sgj-copia (instalar.sh).
set -euo pipefail

AQUI="$(cd "$(dirname "$0")" && pwd)"
DESTINO=/var/backups/sgj
SENHA=/etc/sgj/copia.senha
ARQUIVO="$DESTINO/sgj-$(date -u +%Y%m%d-%H%M).sql.gz.gpg"
AMBIENTE="$(mktemp)"
trap 'rm -f "$AMBIENTE"' EXIT
chmod 600 "$AMBIENTE"

DSN="$(grep -E '^SGJ_DB_DSN=' "$AQUI/.env" | cut -d= -f2-)"
# A senha vai para o contêiner por arquivo de ambiente, nunca pela linha de comando.
python3 - "$DSN" > "$AMBIENTE" <<'PY'
import sys
from urllib.parse import parse_qsl, unquote, urlsplit
p = urlsplit(sys.argv[1])
q = dict(parse_qsl(p.query))
print(f"PGHOST={p.hostname}\nPGPORT={p.port or 5432}\nPGUSER={unquote(p.username or '')}")
print(f"PGPASSWORD={unquote(p.password or '')}\nPGDATABASE={p.path.lstrip('/') or 'postgres'}")
print(f"PGSSLMODE={q.get('sslmode', 'require')}")
PY

install -d -m 700 "$DESTINO"
if ! docker run --rm --env-file "$AMBIENTE" postgres:17 \
        pg_dump --schema=sgj --no-owner --no-privileges --enable-row-security \
    | gzip -9 \
    | gpg --batch --yes --pinentry-mode loopback --passphrase-file "$SENHA" --symmetric --cipher-algo AES256 -o "$ARQUIVO"
then
    rm -f "$ARQUIVO"
    echo "$(date -u +%FT%TZ) FALHA na cópia de segurança" >&2
    exit 1
fi
chmod 600 "$ARQUIVO"
find "$DESTINO" -name 'sgj-*.sql.gz.gpg' -mtime +30 -delete
echo "$(date -u +%FT%TZ) cópia gravada: $ARQUIVO ($(stat -c %s "$ARQUIVO") bytes)"
