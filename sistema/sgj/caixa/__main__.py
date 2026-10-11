"""Inicia a interface de teste em http://127.0.0.1:8000 (exige SGJ_AMBIENTE=teste e SGJ_DB_DSN)."""

import uvicorn

from .web import criar_app

if __name__ == "__main__":
    uvicorn.run(criar_app(), host="127.0.0.1", port=8000)
