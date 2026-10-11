"""Inicia a interface (exige SGJ_AMBIENTE e SGJ_DB_DSN; ver sgj/caixa/web.py).

No ambiente de teste, atende só em http://127.0.0.1:8000. No servidor, o
contêiner define SGJ_HOST=0.0.0.0, e a publicação da porta fica restrita ao
próprio servidor (implantacao/compose.yaml).
"""

import os

import uvicorn

from .web import criar_app

if __name__ == "__main__":
    host = os.environ.get("SGJ_HOST", "127.0.0.1")
    if os.environ.get("SGJ_AMBIENTE") == "teste" and host not in ("127.0.0.1", "localhost"):
        raise SystemExit("No ambiente de teste, a interface só atende no próprio computador (SGJ_HOST=127.0.0.1).")
    uvicorn.run(criar_app(), host=host, port=int(os.environ.get("SGJ_PORTA", "8000")),
                proxy_headers=False, server_header=False)
