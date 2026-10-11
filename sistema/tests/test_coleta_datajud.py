"""Coleta do DataJud no banco, com pg_net e Vault simulados.

Em produção, `net.http_post` (extensão pg_net) envia a requisição e a
resposta aparece depois em `net._http_response`; o Vault guarda a chave.
Aqui as duas peças são substituídas por tabelas e uma função equivalentes.
"""

import json
import os
from datetime import datetime, timezone

import pytest

psycopg = pytest.importorskip("psycopg")

pytestmark = pytest.mark.skipif(not os.environ.get("SGJ_TEST_PG_DSN"), reason="SGJ_TEST_PG_DSN não definido")

SIMULACAO = """
CREATE SCHEMA net;
CREATE TABLE net.pedidos_teste (id bigserial PRIMARY KEY, url text, body jsonb, headers jsonb, timeout_milliseconds integer);
CREATE FUNCTION net.http_post(url text, body jsonb DEFAULT '{}', params jsonb DEFAULT '{}',
                              headers jsonb DEFAULT '{}', timeout_milliseconds integer DEFAULT 5000)
RETURNS bigint LANGUAGE sql AS $$
    INSERT INTO net.pedidos_teste (url, body, headers, timeout_milliseconds)
    VALUES (url, body, headers, timeout_milliseconds) RETURNING id
$$;
CREATE TABLE net._http_response (id bigint, status_code integer, content_type text, headers jsonb, content text,
                                 timed_out boolean, error_msg text, created timestamptz DEFAULT now());
CREATE SCHEMA vault;
CREATE TABLE vault.decrypted_secrets (name text, decrypted_secret text);
"""


def resposta(hits):
    return json.dumps({"took": 5, "timed_out": False, "hits": {"total": {"value": len(hits)}, "hits": hits}})


def registro(grau, movimentos, sigilo=0):
    return {"_id": f"x_{grau}", "_source": {"grau": grau, "nivelSigilo": sigilo, "movimentos": movimentos}}


@pytest.fixture(scope="module")
def carteira(banco):
    banco.execute(SIMULACAO)
    ids = {}
    cliente = banco.execute("INSERT INTO sgj.clientes (codigo, nome) VALUES ('C0001', 'Cliente') RETURNING id").fetchone()[0]

    def processo(chave, npu, tribunal, situacao="ativo"):
        caso = banco.execute(
            "INSERT INTO sgj.casos (codigo, cliente_id, titulo, situacao) VALUES (%s, %s, 'Caso', %s) RETURNING id",
            (f"K{len(ids) + 1:04d}", cliente, situacao)).fetchone()[0]
        ids[chave] = banco.execute(
            "INSERT INTO sgj.processos (caso_id, npu, tribunal) VALUES (%s, %s, %s) RETURNING id",
            (caso, npu, tribunal)).fetchone()[0]

    processo("tjrs", "50000011120258210001", "TJRS")
    processo("trf4", "50000077720254047200", "TRF4")
    processo("desconhecido", "50000088820258130024", "TJMG")
    processo("encerrado", "50000099920258210001", "TJRS", situacao="encerrado")
    return ids


def disparar(banco, limite=10):
    return banco.execute("SELECT sgj.datajud_disparar(%s)", (limite,)).fetchone()[0]


def coletar(banco):
    return banco.execute("SELECT sgj.datajud_coletar()").fetchone()[0]


def pedidos(banco):
    return banco.execute(
        "SELECT q.request_id, q.processo_id, q.alias, p.url, p.body, p.headers FROM sgj.datajud_requisicao q "
        "JOIN net.pedidos_teste p ON p.id = q.request_id ORDER BY q.request_id"
    ).fetchall()


def responder(banco, request_id, status, conteudo=None, erro=None):
    banco.execute("INSERT INTO net._http_response (id, status_code, content, error_msg) VALUES (%s, %s, %s, %s)",
                  (request_id, status, conteudo, erro))


def test_sem_chave_no_vault_nao_dispara(banco, carteira):
    with pytest.raises(psycopg.errors.RaiseException, match="Chave do DataJud ausente"):
        disparar(banco)


def test_dispara_so_processos_ativos_de_tribunal_conhecido(banco, carteira):
    banco.execute("INSERT INTO vault.decrypted_secrets VALUES ('datajud_api_key', 'chave-de-teste')")
    assert disparar(banco) == 2
    feitos = pedidos(banco)
    assert {(f[1], f[2]) for f in feitos} == {(carteira["tjrs"], "tjrs"), (carteira["trf4"], "trf4")}
    _, _, _, url, corpo, cabecalhos = next(f for f in feitos if f[2] == "tjrs")
    assert url == "https://api-publica.datajud.cnj.jus.br/api_publica_tjrs/_search"
    assert corpo == {"query": {"match": {"numeroProcesso": "50000011120258210001"}}}
    assert cabecalhos["Authorization"] == "APIKey chave-de-teste"
    assert disparar(banco) == 0  # pendentes não são repetidos


def test_coleta_grava_movimentos_de_todos_os_graus_sem_duplicar(banco, carteira):
    feitos = {f[2]: f[0] for f in pedidos(banco)}
    movimentos_g1 = [
        {"codigo": 26, "nome": "Distribuição", "dataHora": "2025-03-10T14:00:00.000Z"},
        {"codigo": 85, "nome": "Petição", "dataHora": "20250415103000",
         "complementosTabelados": [{"nome": "tipo de petição", "descricao": "Contestação"}]},
        {"codigo": 85, "nome": "Petição", "dataHora": "data inválida"},
    ]
    movimentos_g2 = [{"codigo": 26, "nome": "Distribuição", "dataHora": "2025-03-10T14:00:00.000Z"},
                     {"codigo": 970, "nome": "Audiência", "dataHora": "2025-06-01T09:00:00Z"}]
    responder(banco, feitos["tjrs"], 200, resposta([registro("G1", movimentos_g1), registro("G2", movimentos_g2)]))
    responder(banco, feitos["trf4"], 504, None, "Gateway Timeout")
    resultado = coletar(banco)
    assert (resultado["processadas"], resultado["falhas"], resultado["movimentos_novos"]) == (2, 1, 3)
    descricoes = [linha[0] for linha in banco.execute(
        "SELECT descricao FROM sgj.movimentacoes WHERE processo_id = %s ORDER BY data_hora", (carteira["tjrs"],)).fetchall()]
    assert descricoes == ["Distribuição", "Petição (tipo de petição: Contestação)", "Audiência"]
    sincronia = dict(banco.execute(
        "SELECT id, ultima_sincronizacao IS NOT NULL FROM sgj.processos WHERE id = ANY(%s)",
        ([carteira["tjrs"], carteira["trf4"]],)).fetchall())
    assert sincronia == {carteira["tjrs"]: True, carteira["trf4"]: False}
    erro = banco.execute("SELECT status_http, erro FROM sgj.datajud_requisicao WHERE request_id = %s",
                         (feitos["trf4"],)).fetchone()
    assert erro == (504, "Gateway Timeout")
    coleta = banco.execute("SELECT situacao, itens, erro FROM sgj.coletas WHERE id = %s", (resultado["coleta"],)).fetchone()
    assert coleta == ("concluida", 3, "1 requisições com falha, 0 sem resposta")


def test_nova_consulta_comeca_pelo_processo_consultado_ha_mais_tempo(banco, carteira):
    banco.execute("UPDATE sgj.datajud_requisicao SET disparada_em = disparada_em - interval '1 day' "
                  "WHERE processo_id = %s", (carteira["trf4"],))
    assert disparar(banco, limite=1) == 1
    ultimo = banco.execute("SELECT processo_id FROM sgj.datajud_requisicao ORDER BY request_id DESC LIMIT 1").fetchone()[0]
    assert ultimo == carteira["trf4"]


def test_resposta_repetida_nao_duplica_e_sigilo_marca_o_processo(banco, carteira):
    assert disparar(banco, limite=1) == 1
    ultimo = banco.execute("SELECT request_id, processo_id FROM sgj.datajud_requisicao ORDER BY request_id DESC LIMIT 1").fetchone()
    assert ultimo[1] == carteira["tjrs"]
    trf4 = banco.execute("SELECT request_id FROM sgj.datajud_requisicao WHERE processo_id = %s AND processada_em IS NULL",
                         (carteira["trf4"],)).fetchone()[0]
    responder(banco, ultimo[0], 200, resposta([registro("G2", [
        {"codigo": 970, "nome": "Audiência", "dataHora": "2025-06-01T09:00:00Z"}], sigilo=1)]))
    responder(banco, trf4, 200, resposta([]))
    resultado = coletar(banco)
    assert (resultado["movimentos_novos"], resultado["falhas"]) == (0, 0)
    assert banco.execute("SELECT segredo_justica FROM sgj.processos WHERE id = %s", (carteira["tjrs"],)).fetchone()[0] is True
    vazio = banco.execute("SELECT registros, erro FROM sgj.datajud_requisicao WHERE request_id = %s", (trf4,)).fetchone()
    assert vazio == (0, "sem registros utilizáveis")


def test_requisicao_sem_resposta_expira(banco, carteira):
    assert disparar(banco, limite=1) == 1
    banco.execute("UPDATE sgj.datajud_requisicao SET disparada_em = now() - interval '7 hours' WHERE processada_em IS NULL")
    resultado = coletar(banco)
    assert resultado["sem_resposta"] == 1
    assert banco.execute("SELECT count(*) FROM sgj.datajud_requisicao WHERE processada_em IS NULL").fetchone()[0] == 0


def test_leitura_de_datas(banco, carteira):
    datas = banco.execute(
        "SELECT sgj.datajud_data('2025-11-11T10:20:30.000Z'), sgj.datajud_data('20250115103000'), sgj.datajud_data('abc')"
    ).fetchone()
    assert datas[0] == datetime(2025, 11, 11, 10, 20, 30, tzinfo=timezone.utc)
    assert datas[1].replace(tzinfo=None) == datetime(2025, 1, 15, 10, 30)
    assert datas[2] is None
