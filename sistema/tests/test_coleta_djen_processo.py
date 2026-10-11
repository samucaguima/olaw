"""Coleta do DJEN por número de processo, com pg_net simulado.

A captura por OAB (esquema djen) é recriada com a estrutura de produção. As
respostas da API são escritas diretamente em `net._http_response`, como o
pg_net faria, para exercitar a sondagem, a conferência cruzada, o circuito de
suspensão e a sincronização com as duas fontes.
"""

import json
import os
from datetime import timedelta

import pytest

psycopg = pytest.importorskip("psycopg")

pytestmark = pytest.mark.skipif(not os.environ.get("SGJ_TEST_PG_DSN"), reason="SGJ_TEST_PG_DSN não definido")

SIMULACAO = """
CREATE SCHEMA net;
CREATE TABLE net.pedidos_teste (id bigserial PRIMARY KEY, url text, headers jsonb, timeout_milliseconds integer);
CREATE FUNCTION net.http_get(url text, params jsonb DEFAULT '{}', headers jsonb DEFAULT '{}',
                             timeout_milliseconds integer DEFAULT 5000)
RETURNS bigint LANGUAGE sql AS $$
    INSERT INTO net.pedidos_teste (url, headers, timeout_milliseconds) VALUES (url, headers, timeout_milliseconds)
    RETURNING id
$$;
CREATE TABLE net._http_response (id bigint, status_code integer, content_type text, headers jsonb, content text,
                                 timed_out boolean, error_msg text, created timestamptz DEFAULT now());
CREATE SCHEMA djen;
CREATE TABLE djen.comunicacao (
    id bigint PRIMARY KEY, data_disponibilizacao date, tribunal text, processo text, classe text,
    tipo_comunicacao text, tipo_documento text, orgao text, cabecalho text, texto_html text, link text,
    raw jsonb, capturada_em timestamptz DEFAULT now(), revisada boolean DEFAULT false
);
"""

NPU_A = "50000011120258210001"
NPU_B = "50000022220258240023"
NPU_C = "50000033320254047200"
NPU_D = "50000044420258210001"


def mascara(npu):
    return f"{npu[:7]}-{npu[7:9]}.{npu[9:13]}.{npu[13]}.{npu[14:16]}.{npu[16:]}"


def item(id_, npu, data, texto="Fica intimada a parte."):
    return {"id": id_, "hash": f"H{id_}", "numero_processo": npu, "numeroprocessocommascara": mascara(npu),
            "data_disponibilizacao": data.isoformat(), "siglaTribunal": "TJRS", "nomeOrgao": "1ª Vara Cível",
            "nomeClasse": "PROCEDIMENTO COMUM CÍVEL", "tipoComunicacao": "Intimação", "tipoDocumento": "Despacho",
            "texto": f"<p>{texto}</p>", "link": f"https://eproc1g.tjrs.jus.br/{id_}"}


def envelope(itens, total=None):
    return json.dumps({"status": "success", "message": "", "count": len(itens) if total is None else total,
                       "items": itens})


@pytest.fixture(scope="module")
def carteira(banco):
    banco.execute(SIMULACAO)
    hoje = banco.execute("SELECT (now() AT TIME ZONE 'America/Sao_Paulo')::date").fetchone()[0]
    cliente = banco.execute("INSERT INTO sgj.clientes (codigo, nome) VALUES ('C0001', 'Cliente') RETURNING id").fetchone()[0]
    ids = {}
    for ordem, (chave, npu, tribunal, situacao) in enumerate([
        ("A", NPU_A, "TJRS", "ativo"), ("B", NPU_B, "TJSC", "ativo"),
        ("C", NPU_C, "TRF4", "ativo"), ("D", NPU_D, "TJRS", "encerrado"),
    ], start=1):
        caso = banco.execute(
            "INSERT INTO sgj.casos (codigo, cliente_id, titulo, situacao) VALUES (%s, %s, 'Caso', %s) RETURNING id",
            (f"K{ordem:04d}", cliente, situacao)).fetchone()[0]
        ids[chave] = banco.execute(
            "INSERT INTO sgj.processos (caso_id, npu, tribunal) VALUES (%s, %s, %s) RETURNING id",
            (caso, npu, tribunal)).fetchone()[0]
    conhecida = item(1001, NPU_A, hoje - timedelta(days=2))
    banco.execute(
        "INSERT INTO djen.comunicacao (id, data_disponibilizacao, tribunal, processo, tipo_comunicacao, texto_html, "
        "link, raw) VALUES (1001, %s, 'TJRS', %s, 'Intimação', %s, %s, %s)",
        (conhecida["data_disponibilizacao"], mascara(NPU_A), conhecida["texto"], conhecida["link"], json.dumps(conhecida)))
    return {"ids": ids, "hoje": hoje, "conhecida": conhecida}


def disparar(banco, limite=10, dias=7):
    return banco.execute("SELECT sgj.djen_processo_disparar(%s, %s)", (limite, dias)).fetchone()[0]


def coletar(banco):
    return banco.execute("SELECT sgj.djen_processo_coletar()").fetchone()[0]


def pendentes(banco):
    return banco.execute(
        "SELECT q.request_id, q.processo_id, q.data_inicio, q.data_fim, q.sondagem, p.url, p.headers "
        "FROM sgj.djen_requisicao q JOIN net.pedidos_teste p ON p.id = q.request_id "
        "WHERE q.processada_em IS NULL ORDER BY q.request_id").fetchall()


def responder(banco, request_id, status, conteudo=None, erro=None):
    banco.execute("INSERT INTO net._http_response (id, status_code, content, error_msg) VALUES (%s, %s, %s, %s)",
                  (request_id, status, conteudo, erro))


def requisicao(banco, request_id):
    linha = banco.execute(
        "SELECT resultado, status_http, recebidas, conferidas, novas, erro FROM sgj.djen_requisicao WHERE request_id = %s",
        (request_id,)).fetchone()
    return dict(zip(("resultado", "status", "recebidas", "conferidas", "novas", "erro"), linha))


def test_sondagem_consulta_um_processo_no_dia_de_comunicacao_conhecida(banco, carteira):
    assert disparar(banco) == 1
    [(rid, processo, inicio, fim, sondagem, url, cabecalhos)] = pendentes(banco)
    dia = carteira["hoje"] - timedelta(days=2)
    assert (processo, inicio, fim, sondagem) == (carteira["ids"]["A"], dia, dia, True)
    assert url == ("https://comunicaapi.pje.jus.br/api/v1/comunicacao?numeroProcesso=" + NPU_A
                   + f"&itensPorPagina=100&pagina=1&dataDisponibilizacaoInicio={dia}&dataDisponibilizacaoFim={dia}")
    assert cabecalhos == {"Accept": "application/json", "User-Agent": "Mozilla/5.0"}
    assert disparar(banco) == 0  # sondagem pendente


def test_sondagem_sem_a_comunicacao_conhecida_fica_divergente(banco, carteira):
    [(rid, *_)] = pendentes(banco)
    responder(banco, rid, 200, envelope([]))
    resultado = coletar(banco)
    assert (resultado["processadas"], resultado["divergentes"], resultado["novas"]) == (1, 1, 0)
    assert requisicao(banco, rid)["resultado"] == "divergente"
    # Continua em sondagem: um processo, agora com a janela normal.
    assert disparar(banco) == 1
    [(_, processo, inicio, fim, sondagem, *_)] = pendentes(banco)
    assert (processo, sondagem) == (carteira["ids"]["A"], False)
    assert (inicio, fim) == (carteira["hoje"] - timedelta(days=7), carteira["hoje"])


def test_conferencia_valida_grava_so_o_que_a_captura_por_oab_nao_tinha(banco, carteira):
    [(rid, *_)] = pendentes(banco)
    nova = item(1002, NPU_A, carteira["hoje"], "Intimação encontrada só pela consulta por processo.")
    responder(banco, rid, 200, envelope([carteira["conhecida"], nova]))
    resultado = coletar(banco)
    assert (resultado["processadas"], resultado["novas"], resultado["falhas"]) == (1, 1, 0)
    assert requisicao(banco, rid) | {"erro": None} == {
        "resultado": "valida", "status": 200, "recebidas": 2, "conferidas": 1, "novas": 1, "erro": None}
    assert [linha[0] for linha in banco.execute("SELECT id FROM sgj.djen_comunicacao").fetchall()] == [1002]
    sinc = resultado["sincronizacao"]
    assert (sinc["situacao"], sinc["inseridas"], sinc["inseridas_pela_consulta_por_processo"]) == ("concluida", 2, 1)
    publicacao = banco.execute(
        "SELECT processo_id, hash, texto FROM sgj.publicacoes WHERE djen_id = 1002").fetchone()
    assert publicacao == (carteira["ids"]["A"], "H1002", "Intimação encontrada só pela consulta por processo.")
    fonte = banco.execute("SELECT fonte, situacao, itens FROM sgj.coletas WHERE id = %s", (resultado["coleta"],)).fetchone()
    assert fonte == ("djen_processo", "concluida", 1)


def test_validada_consulta_os_demais_processos_ativos_uma_vez_por_dia(banco, carteira):
    assert disparar(banco) == 2
    feitos = pendentes(banco)
    assert {f[1] for f in feitos} == {carteira["ids"]["B"], carteira["ids"]["C"]}
    assert all(not f[4] for f in feitos)
    assert disparar(banco) == 0  # pendentes e processo já consultado hoje


def test_outro_processo_na_resposta_ou_excesso_suspendem_a_coleta(banco, carteira):
    feitos = {f[1]: f[0] for f in pendentes(banco)}
    responder(banco, feitos[carteira["ids"]["B"]], 429, "Too Many Requests")
    responder(banco, feitos[carteira["ids"]["C"]], 200,
              envelope([item(2001, "99999999920258210001", carteira["hoje"])], total=5000))
    resultado = coletar(banco)
    assert (resultado["processadas"], resultado["falhas"], resultado["novas"]) == (2, 2, 0)
    assert requisicao(banco, feitos[carteira["ids"]["B"]])["resultado"] == "falha"
    ignorada = requisicao(banco, feitos[carteira["ids"]["C"]])
    assert ignorada["resultado"] == "parametro_ignorado" and "nada foi gravado" in ignorada["erro"]
    assert banco.execute("SELECT count(*) FROM sgj.djen_comunicacao WHERE id = 2001").fetchone()[0] == 0
    assert disparar(banco) == 0  # suspensa por 24 horas
    banco.execute("UPDATE sgj.djen_requisicao SET disparada_em = disparada_em - interval '25 hours', "
                  "processada_em = processada_em - interval '25 hours'")
    # Passadas 24 horas, volta à sondagem: de novo o processo com comunicação conhecida.
    assert disparar(banco) == 1
    [(_, processo, inicio, fim, sondagem, *_)] = pendentes(banco)
    dia = carteira["hoje"] - timedelta(days=2)
    assert (processo, inicio, fim, sondagem) == (carteira["ids"]["A"], dia, dia, True)


def test_pagina_incompleta_fica_anotada_e_sondagem_valida_libera_a_coleta(banco, carteira):
    [(rid, *_)] = pendentes(banco)
    responder(banco, rid, 200, envelope([carteira["conhecida"]], total=150))
    coletar(banco)
    situacao = requisicao(banco, rid)
    assert (situacao["resultado"], situacao["conferidas"]) == ("valida", 1)
    assert "primeira página" in situacao["erro"]
    assert disparar(banco) == 3  # A, B e C: nenhum consultado hoje depois de 24 horas


def test_mesma_comunicacao_depois_capturada_por_oab_nao_duplica(banco, carteira):
    antes = banco.execute("SELECT count(*) FROM sgj.publicacoes").fetchone()[0]
    nova = item(1002, NPU_A, carteira["hoje"], "Intimação encontrada só pela consulta por processo.")
    banco.execute(
        "INSERT INTO djen.comunicacao (id, data_disponibilizacao, tribunal, processo, tipo_comunicacao, texto_html, "
        "link, raw) VALUES (1002, %s, 'TJRS', %s, 'Intimação', %s, %s, %s)",
        (nova["data_disponibilizacao"], mascara(NPU_A), nova["texto"], nova["link"], json.dumps(nova)))
    sinc = banco.execute("SELECT sgj.sincronizar_djen()").fetchone()[0]
    assert (sinc["inseridas"], sinc["completadas"]) == (0, 0)
    assert banco.execute("SELECT count(*) FROM sgj.publicacoes").fetchone()[0] == antes
    fonte = banco.execute("SELECT por_processo FROM sgj.djen_fonte() WHERE id = 1002").fetchall()
    assert fonte == [(False,)]


def test_requisicao_sem_resposta_expira(banco, carteira):
    rid = banco.execute("SELECT sgj.djen_processo_pedir(%s, %s, %s, %s, false)",
                        (carteira["ids"]["B"], NPU_B, carteira["hoje"], carteira["hoje"])).fetchone()[0]
    banco.execute("UPDATE sgj.djen_requisicao SET disparada_em = now() - interval '7 hours' WHERE request_id = %s", (rid,))
    resultado = coletar(banco)
    assert resultado["sem_resposta"] == 1
    assert requisicao(banco, rid)["resultado"] == "sem_resposta"


def test_rodada_coleta_e_dispara(banco, carteira):
    banco.execute("DELETE FROM sgj.djen_requisicao WHERE processada_em IS NULL")
    resultado = banco.execute("SELECT sgj.djen_processo_rodada(10, 7)").fetchone()[0]
    assert resultado["processadas"] == 0 and resultado["disparadas"] >= 0
