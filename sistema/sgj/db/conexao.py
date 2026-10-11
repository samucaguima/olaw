"""Conexão com o banco: Supabase em produção ou servidor PostgreSQL local de teste."""

from __future__ import annotations

import os

import psycopg
from psycopg.rows import dict_row


def conectar(dsn: str | None = None) -> psycopg.Connection:
    """Abre conexão em modo autocommit, com linhas como dicionários; operações de escrita usam
    `conexao.transaction()`. O DSN vem do argumento ou de SGJ_DB_DSN."""
    dsn = dsn or os.environ.get("SGJ_DB_DSN")
    if not dsn:
        raise RuntimeError("Defina SGJ_DB_DSN com a conexão do banco.")
    return psycopg.connect(dsn, row_factory=dict_row, autocommit=True)
