"""Testes das restrições do esquema contra um PostgreSQL real.

Executados apenas quando SGJ_TEST_PG_DSN aponta para um servidor; o banco
temporário, com todas as migrações, vem da fixture `banco` (conftest.py).
"""

import os

import pytest

psycopg = pytest.importorskip("psycopg")

pytestmark = pytest.mark.skipif(not os.environ.get("SGJ_TEST_PG_DSN"), reason="SGJ_TEST_PG_DSN não definido")


@pytest.fixture(scope="module")
def base(banco):
    """Cadastro mínimo: titular, cliente, caso, processo e publicação."""
    ids = {}
    ids["usuario"] = banco.execute(
        "INSERT INTO usuarios (nome, email, perfil) VALUES ('Titular', 'titular@exemplo.invalid', 'titular') RETURNING id"
    ).fetchone()[0]
    ids["cliente"] = banco.execute(
        "INSERT INTO clientes (codigo, tipo, nome, cpf_cnpj) VALUES ('C0001', 'PF', 'Cliente Teste', '00000000000') RETURNING id"
    ).fetchone()[0]
    ids["caso"] = banco.execute(
        "INSERT INTO casos (codigo, cliente_id, titulo) VALUES ('K0001', %s, 'Caso teste') RETURNING id",
        (ids["cliente"],),
    ).fetchone()[0]
    ids["processo"] = banco.execute(
        "INSERT INTO processos (caso_id, npu, tribunal, sistema, sistema_fonte) "
        "VALUES (%s, '00000000000000000000', 'TJX', 'eproc', 'titular') RETURNING id",
        (ids["caso"],),
    ).fetchone()[0]
    ids["publicacao"] = banco.execute(
        "INSERT INTO publicacoes (processo_id, npu, hash, data_disponibilizacao, texto) "
        "VALUES (%s, '00000000000000000000', 'h1', '2026-08-03', 'Texto') RETURNING id",
        (ids["processo"],),
    ).fetchone()[0]
    return ids


def rejeita(banco, sql, params=()):
    with pytest.raises(psycopg.errors.Error):
        with banco.transaction():
            banco.execute(sql, params)


def aceita(banco, sql, params=()):
    with banco.transaction():
        return banco.execute(sql, params)


PRAZO = (
    "INSERT INTO prazos (processo_id, publicacao_id, dias, data_publicacao, data_inicio, data_fatal, "
    "data_fatal_com_prorrogacao, data_interna, calendario_conferido, memoria_calculo, situacao, aprovado_por, aprovado_em) "
    "VALUES (%s, %s, 5, '2026-08-04', '2026-08-05', '2026-08-11', '2026-08-11', '2026-08-07', true, '[]', %s, %s, %s) RETURNING id"
)


def test_prazo_confirmado_exige_aprovacao(banco, base):
    rejeita(banco, PRAZO, (base["processo"], base["publicacao"], "confirmado", None, None))
    aceita(banco, PRAZO, (base["processo"], base["publicacao"], "confirmado", base["usuario"], "2026-08-04"))


def test_prazo_com_datas_incoerentes_e_rejeitado(banco, base):
    rejeita(
        banco,
        PRAZO.replace("'2026-08-07', true", "'2026-08-12', true"),
        (base["processo"], base["publicacao"], "sugerido", None, None),
    )


def test_tarefa_com_prazo_processual_exige_prazo(banco, base):
    rejeita(
        banco,
        "INSERT INTO tarefas (processo_id, origem, tipo, titulo) VALUES (%s, 'publicacao', 'prazo_processual', 'Sem prazo')",
        (base["processo"],),
    )
    aceita(
        banco,
        "INSERT INTO tarefas (processo_id, origem, tipo, titulo) VALUES (%s, 'movimentacao', 'interna', 'Conferir movimentação')",
        (base["processo"],),
    )


def test_movimentacao_nao_recebe_prazo_legal(banco, base):
    usuario = base["usuario"]
    prazo_legal = aceita(
        banco,
        "INSERT INTO prazos_legais (tipo_ato, dias, contagem, dispositivo, link_oficial, conferido_em, conferido_por) "
        "VALUES ('ato de teste', 5, 'uteis', 'dispositivo de teste', 'https://exemplo.invalid', '2026-10-09', %s) RETURNING id",
        (usuario,),
    ).fetchone()[0]
    movimentacao = aceita(
        banco,
        "INSERT INTO movimentacoes (processo_id, origem, data_hora, descricao) VALUES (%s, 'datajud', now(), 'Teste') RETURNING id",
        (base["processo"],),
    ).fetchone()[0]
    rejeita(
        banco,
        "INSERT INTO sugestoes_ia (movimentacao_id, prazo_legal_id, modelo_ia, versao_prompt) VALUES (%s, %s, 'm', 'v1')",
        (movimentacao, prazo_legal),
    )


def test_minuta_com_pendencia_nao_pode_ser_aprovada(banco, base):
    tarefa = aceita(
        banco,
        "INSERT INTO tarefas (processo_id, origem, tipo, titulo) VALUES (%s, 'manual', 'interna', 'Minuta') RETURNING id",
        (base["processo"],),
    ).fetchone()[0]
    rejeita(
        banco,
        "INSERT INTO minutas (tarefa_id, docx_drive_id, pendencias_conferir, aprovado_por, aprovado_em) VALUES (%s, 'd1', 1, %s, now())",
        (tarefa, base["usuario"]),
    )


def test_envio_individual_exige_autorizacao(banco, base):
    rejeita(
        banco,
        "INSERT INTO envios (canal, destinatario, conteudo, relatorio_pie, enviado_em) VALUES ('email', 'x@exemplo.invalid', 'c', '{}', now())",
    )


def test_cobranca_emitida_exige_aprovacao(banco, base):
    contrato = aceita(
        banco,
        "INSERT INTO contratos_honorarios (caso_id, modalidade) VALUES (%s, 'fixo') RETURNING id",
        (base["caso"],),
    ).fetchone()[0]
    rejeita(
        banco,
        "INSERT INTO cobrancas (contrato_id, vencimento, valor, situacao) VALUES (%s, '2026-09-01', 100, 'emitida')",
        (contrato,),
    )


def test_calendario_exige_fonte(banco, base):
    rejeita(
        banco,
        "INSERT INTO calendario (tribunal, data, tipo, descricao, fonte_link) VALUES ('TJX', '2026-08-04', 'feriado', 'Teste', ' ')",
    )


def test_auditoria_e_imutavel(banco, base):
    registro = aceita(
        banco,
        "INSERT INTO auditoria (usuario_id, acao, entidade) VALUES (%s, 'teste', 'prazos') RETURNING id",
        (base["usuario"],),
    ).fetchone()[0]
    rejeita(banco, "UPDATE auditoria SET acao = 'alterada' WHERE id = %s", (registro,))
    rejeita(banco, "DELETE FROM auditoria WHERE id = %s", (registro,))


def test_cliente_sem_documento_e_aceito_e_tipo_segue_o_documento(banco, base):
    aceita(banco, "INSERT INTO clientes (codigo, nome) VALUES ('C0101', 'Sem documento')")
    rejeita(banco, "INSERT INTO clientes (codigo, nome, cpf_cnpj) VALUES ('C0102', 'Sem tipo', '00000000001')")
    rejeita(banco, "INSERT INTO clientes (codigo, tipo, nome, cpf_cnpj) VALUES ('C0103', 'PJ', 'Tipo trocado', '00000000002')")
    aceita(banco, "INSERT INTO clientes (codigo, tipo, nome, cpf_cnpj) VALUES ('C0104', 'PJ', 'Empresa', '00000000000100')")


def test_sistema_do_processo_exige_fonte(banco, base):
    processo = "INSERT INTO processos (caso_id, npu, tribunal, sistema, sistema_fonte) VALUES (%s, %s, 'TJX', %s, %s)"
    rejeita(banco, processo, (base["caso"], "00000000000000000001", "eproc", None))
    rejeita(banco, processo, (base["caso"], "00000000000000000002", None, "djen"))
    aceita(banco, processo, (base["caso"], "00000000000000000003", None, None))


def test_todos_os_objetos_ficam_no_esquema_sgj_com_rls(banco, base):
    fora = banco.execute(
        "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'"
    ).fetchone()[0]
    assert fora == 0
    sem_rls = banco.execute(
        "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'sgj' AND c.relkind = 'r' AND NOT c.relrowsecurity"
    ).fetchone()[0]
    assert sem_rls == 0
    total = banco.execute("SELECT count(*) FROM pg_tables WHERE schemaname = 'sgj'").fetchone()[0]
    assert total == 31


def test_papel_sem_privilegio_nao_le_o_esquema(banco, base):
    banco.execute("DROP ROLE IF EXISTS leitor_teste")
    banco.execute("CREATE ROLE leitor_teste")
    try:
        rejeita(banco, "SET LOCAL ROLE leitor_teste; SELECT * FROM sgj.usuarios")
        executaveis = banco.execute(
            "SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'sgj' AND has_function_privilege('leitor_teste', p.oid, 'EXECUTE')"
        ).fetchone()[0]
        assert executaveis == 0
    finally:
        banco.execute("DROP ROLE IF EXISTS leitor_teste")
