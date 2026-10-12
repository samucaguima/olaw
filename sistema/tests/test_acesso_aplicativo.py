"""Papel do aplicativo no servidor (migração 0006): o painel funciona com ele, e nada além do necessário é permitido."""

import os

import pytest

psycopg = pytest.importorskip("psycopg")

pytestmark = pytest.mark.skipif(not os.environ.get("SGJ_TEST_PG_DSN"), reason="SGJ_TEST_PG_DSN não definido")

CAPTURA = """
CREATE SCHEMA djen;
CREATE TABLE djen.comunicacao (id bigint PRIMARY KEY, data_disponibilizacao date, processo text, texto_html text,
                               raw jsonb, capturada_em timestamptz DEFAULT now(), revisada boolean DEFAULT false);
CREATE TABLE djen.requisicao (request_id bigint PRIMARY KEY, disparada_em timestamptz DEFAULT now(),
                              processada_em timestamptz, status_http integer, erro text);
ALTER TABLE djen.comunicacao ENABLE ROW LEVEL SECURITY;
ALTER TABLE djen.requisicao ENABLE ROW LEVEL SECURITY;
INSERT INTO djen.requisicao VALUES (1, now() - interval '1 hour', now() - interval '55 minutes', 200, NULL);
INSERT INTO djen.comunicacao (id, data_disponibilizacao, processo) VALUES (10, current_date, '5000001-11.2025.8.21.0001');
"""


@pytest.fixture(scope="module")
def aplicativo(banco):
    banco.execute(CAPTURA)
    cliente = banco.execute("INSERT INTO sgj.clientes (codigo, nome) VALUES ('C0001', 'Cliente') RETURNING id").fetchone()[0]
    caso = banco.execute("INSERT INTO sgj.casos (codigo, cliente_id, titulo) VALUES ('K0001', %s, 'Caso') RETURNING id",
                         (cliente,)).fetchone()[0]
    processo = banco.execute("INSERT INTO sgj.processos (caso_id, npu, tribunal) VALUES (%s, '50000011120258210001', 'TJRS') "
                             "RETURNING id", (caso,)).fetchone()[0]
    banco.execute("SET ROLE sgj_app")
    try:
        yield {"processo": processo}
    finally:
        banco.execute("RESET ROLE")


def test_painel_e_coletas_funcionam_com_o_papel_do_aplicativo(banco, aplicativo):
    from sgj.caixa import painel

    assert banco.execute("SELECT current_user").fetchone()[0] == "sgj_app"
    dia = painel.meu_dia(banco)
    assert dia["carteira"]["totais"]["processos"] == 1
    captura = next(f for f in dia["coletas"] if f.chave == "djen_oab")
    assert captura.situacao == "ok" and "1 comunicações capturadas" in captura.detalhes[0]
    assert painel.agendamentos(banco) == []


def test_papel_grava_tarefa_mas_nao_exclui_nem_altera_auditoria(banco, aplicativo):
    tarefa = banco.execute(
        "INSERT INTO sgj.tarefas (processo_id, origem, tipo, titulo) VALUES (%s, 'manual', 'interna', 'Teste') RETURNING id",
        (aplicativo["processo"],)).fetchone()[0]
    banco.execute("UPDATE sgj.tarefas SET situacao = 'concluida' WHERE id = %s", (tarefa,))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        banco.execute("DELETE FROM sgj.tarefas WHERE id = %s", (tarefa,))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        banco.execute("UPDATE sgj.auditoria SET acao = 'x'")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        banco.execute("UPDATE sgj.prazos_legais SET dias = 1")


def test_papel_nao_le_os_esquemas_da_captura_e_do_agendador(banco, aplicativo):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        banco.execute("SELECT count(*) FROM djen.requisicao")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        banco.execute("SELECT sgj.sincronizar_djen()")


def test_papel_cadastra_processo_e_grava_conferencia(banco, aplicativo):
    from sgj.caixa import cadastro

    banco.execute("RESET ROLE")
    titular = banco.execute("INSERT INTO sgj.usuarios (nome, email, perfil) VALUES ('Titular', 't@exemplo.invalid', 'titular') "
                            "RETURNING id").fetchone()[0]
    banco.execute("SET ROLE sgj_app")
    numero = "5004444" + "00" + "20258210001"
    numero = numero[:7] + cadastro.digito_verificador(numero) + numero[9:]
    resultado = cadastro.cadastrar_processo(banco, titular, {
        "npu": numero, "segredo": "nao", "caso_titulo": "Caso novo", "cliente_acao": "novo", "cliente_novo_nome": "Cliente Novo"})
    cadastro.salvar_conferencia(banco, resultado["tarefa_id"], titular,
                                {"caso_titulo": "Caso novo", "segredo": "nao", "cliente_acao": "manter", "sistema": "eproc"}, [1])
    assert banco.execute("SELECT sistema FROM sgj.processos WHERE npu = %s", (numero,)).fetchone()[0] == "eproc"
