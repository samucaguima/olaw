"""Banco PostgreSQL temporário, com todas as migrações aplicadas em ordem.

Usado quando SGJ_TEST_PG_DSN aponta para um servidor (banco administrativo,
ex.: host=/caminho port=54329 user=postgres dbname=postgres). Cada módulo de
teste recebe um banco próprio, removido ao final. Sem a extensão pgvector no
servidor, o tipo `vector` é substituído por um domínio provisório, e o índice
semântico fica fora do teste.
"""

import os
import uuid
from pathlib import Path

import pytest

MIGRACOES = sorted((Path(__file__).parents[1] / "sgj" / "db" / "migrations").glob("*.sql"))


@pytest.fixture(scope="module")
def banco():
    dsn = os.environ.get("SGJ_TEST_PG_DSN")
    if not dsn:
        pytest.skip("SGJ_TEST_PG_DSN não definido")
    psycopg = pytest.importorskip("psycopg")
    from psycopg.conninfo import make_conninfo

    nome = f"sgj_teste_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{nome}"')
        tem_pgvector = admin.execute(
            "SELECT 1 FROM pg_available_extensions WHERE name = 'vector'"
        ).fetchone()
    try:
        with psycopg.connect(make_conninfo(dsn, dbname=nome), autocommit=True) as conexao:
            for migracao in MIGRACOES:
                sql = migracao.read_text(encoding="utf-8")
                if not tem_pgvector:
                    sql = sql.replace(
                        "CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;",
                        "CREATE DOMAIN extensions.vector AS real[];",
                    )
                conexao.execute(sql)
            conexao.execute("SET search_path TO sgj, public")
            yield conexao
    finally:
        with psycopg.connect(dsn, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{nome}" WITH (FORCE)')
