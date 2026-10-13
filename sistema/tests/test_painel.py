"""Painel "Meu dia" e saúde das coletas.

A captura por OAB (esquema djen) é recriada com a estrutura de produção, sem o
pg_cron. Datas relativas ao dia de hoje em São Paulo, como no painel.
"""

import json
import os
from datetime import datetime, timedelta, timezone

import pytest

psycopg = pytest.importorskip("psycopg")

pytestmark = pytest.mark.skipif(not os.environ.get("SGJ_TEST_PG_DSN"), reason="SGJ_TEST_PG_DSN não definido")

# Cabeçalho com que o navegador atesta que a gravação partiu das telas do próprio sistema (web.py).
MESMA_ORIGEM = {"Sec-Fetch-Site": "same-origin"}

SIMULACAO = """
CREATE SCHEMA djen;
CREATE TABLE djen.comunicacao (
    id bigint PRIMARY KEY, data_disponibilizacao date, tribunal text, processo text, classe text,
    tipo_comunicacao text, tipo_documento text, orgao text, cabecalho text, texto_html text, link text,
    raw jsonb, capturada_em timestamptz DEFAULT now(), revisada boolean DEFAULT false
);
CREATE TABLE djen.requisicao (
    request_id bigint PRIMARY KEY, tribunal text, pagina integer, url text, disparada_em timestamptz DEFAULT now(),
    processada_em timestamptz, status_http integer, erro text
);
"""


@pytest.fixture(scope="module")
def cenario(banco):
    from sgj.caixa import painel

    banco.execute(SIMULACAO)
    hoje = painel.hoje_sp()
    titular = banco.execute(
        "INSERT INTO sgj.usuarios (nome, email, perfil) VALUES ('Titular', 'titular@exemplo.invalid', 'titular') "
        "RETURNING id").fetchone()[0]
    cliente = banco.execute("INSERT INTO sgj.clientes (codigo, nome) VALUES ('C0001', 'Cliente Exemplo') RETURNING id").fetchone()[0]
    provisorio = banco.execute(
        "INSERT INTO sgj.clientes (codigo, nome, provisorio) VALUES ('C0000', 'Cliente a identificar', true) RETURNING id"
    ).fetchone()[0]

    def processo(codigo, cliente_id, npu, tribunal, **campos):
        caso = banco.execute("INSERT INTO sgj.casos (codigo, cliente_id, titulo) VALUES (%s, %s, 'Caso') RETURNING id",
                             (codigo, cliente_id)).fetchone()[0]
        colunas = ["caso_id", "npu", "tribunal", *campos]
        return banco.execute(
            f"INSERT INTO sgj.processos ({', '.join(colunas)}) VALUES ({', '.join(['%s'] * len(colunas))}) RETURNING id",
            (caso, npu, tribunal, *campos.values())).fetchone()[0]

    tjrs = processo("K0001", cliente, "50000011120258210001", "TJRS", sistema="eproc", sistema_fonte="djen",
                    grau=1, comarca="Porto Alegre")
    tjsc = processo("K0002", cliente, "50000022220258240023", "TJSC")
    trf4 = processo("K0003", provisorio, "50000033320254047200", "TRF4", segredo_justica=True)
    banco.execute("INSERT INTO sgj.calendario_cobertura (tribunal, ano, conferido_por, conferido_em) "
                  "VALUES ('TJRS', %s, %s, %s)", (hoje.year, titular, hoje))

    def publicacao(npu, data, processo_id=None, tribunal=None, tipo="Intimação"):
        return banco.execute(
            "INSERT INTO sgj.publicacoes (processo_id, npu, hash, data_disponibilizacao, tipo_comunicacao, texto, tribunal) "
            "VALUES (%s, %s, %s, %s, %s, 'Texto.', %s) RETURNING id",
            (processo_id, npu, f"h{npu}{data}{tipo}", data, tipo, tribunal)).fetchone()[0]

    # Prazos confirmados: vencido, hoje, em 2 dias, em 5 dias e em 20 dias.
    for deslocamento, situacao in ((-1, "a_fazer"), (0, "em_elaboracao"), (2, "a_fazer"), (5, "conferencia_1"),
                                   (20, "a_fazer")):
        fatal = hoje + timedelta(days=deslocamento)
        pub = publicacao("50000011120258210001", fatal - timedelta(days=10), tjrs, "TJRS", f"Intimação {deslocamento}")
        prazo = banco.execute(
            "INSERT INTO sgj.prazos (processo_id, publicacao_id, dias, data_publicacao, data_inicio, data_fatal, "
            "data_fatal_com_prorrogacao, data_interna, calendario_conferido, memoria_calculo, situacao, aprovado_por, "
            "aprovado_em) VALUES (%s, %s, 15, %s, %s, %s, %s, %s, %s, '{}', 'confirmado', %s, now()) RETURNING id",
            (tjrs, pub, fatal - timedelta(days=9), fatal - timedelta(days=8), fatal, fatal, fatal - timedelta(days=2),
             deslocamento != 5, titular)).fetchone()[0]
        banco.execute(
            "INSERT INTO sgj.tarefas (processo_id, prazo_id, origem, tipo, titulo, situacao, vencimento_interno) "
            "VALUES (%s, %s, 'publicacao', 'prazo_processual', %s, %s, %s)",
            (tjrs, prazo, f"Prazo {deslocamento}", situacao, fatal - timedelta(days=2)))

    # Conferência do cadastro importado: uma concluída e uma pendente.
    itens = [{"item": "Confirmar o sistema do processo", "concluido": False},
             {"item": "Vincular a pasta do processo no Drive (há pasta local registrada no protótipo)", "concluido": False},
             {"item": "Conferir o polo do cliente", "concluido": True}]
    banco.execute("INSERT INTO sgj.tarefas (processo_id, origem, tipo, titulo, checklist) "
                  "VALUES (%s, 'importacao', 'interna', 'Conferir', %s)", (tjsc, json.dumps(itens)))
    banco.execute("INSERT INTO sgj.tarefas (processo_id, origem, tipo, titulo, checklist, situacao) "
                  "VALUES (%s, 'importacao', 'interna', 'Conferir', %s, 'concluida')", (trf4, json.dumps(itens)))

    # Publicações de processos fora da carteira.
    publicacao("50099991120258210001", hoje - timedelta(days=3), tipo="Sentença")
    publicacao("50099991120258210001", hoje - timedelta(days=30), tipo="Despacho")
    publicacao("50088882220254047200", hoje - timedelta(days=10), tribunal="TRF4", tipo="Ato ordinatório")

    # Coletas: captura por OAB com a última rodada válida, sincronização concluída.
    banco.execute("INSERT INTO djen.requisicao (request_id, pagina, disparada_em, processada_em, status_http) "
                  "SELECT g, g, now() - interval '2 hours', now() - interval '110 minutes', 200 FROM generate_series(1, 3) g")
    banco.execute("INSERT INTO sgj.coletas (fonte, inicio, fim, situacao, itens) "
                  "VALUES ('djen', now() - interval '1 hour', now() - interval '1 hour', 'concluida', 4)")
    return {"hoje": hoje, "tjrs": tjrs, "tjsc": tjsc, "trf4": trf4}


def fonte(banco, chave):
    from sgj.caixa import painel

    return next(f for f in painel.saude_coletas(banco) if f.chave == chave)


def test_prazos_em_ordem_e_semaforo(banco, cenario):
    from sgj.caixa import painel

    dia = painel.meu_dia(banco)
    assert dia["contagem_prazos"] == {"vencido": 1, "hoje": 1, "dois_dias": 1, "semana": 1, "depois": 1}
    assert [p["titulo"] for p in dia["prazos"]] == ["Prazo -1", "Prazo 0", "Prazo 2", "Prazo 5", "Prazo 20"]
    hoje = next(p for p in dia["prazos"] if p["titulo"] == "Prazo 0")
    assert hoje["interno_vencido"] and hoje["situacao_tarefa"] == "Em elaboração"
    assert not next(p for p in dia["prazos"] if p["titulo"] == "Prazo 5")["calendario_conferido"]


def test_processos_fora_da_carteira(banco, cenario):
    from sgj.caixa import painel

    fora = painel.meu_dia(banco)["fora_da_carteira"]
    assert [(f["npu"], f["publicacoes"], f["ultimo_tipo"], f["tribunais"]) for f in fora] == [
        ("50099991120258210001", 2, "Sentença", "TJRS"),
        ("50088882220254047200", 1, "Ato ordinatório", "TRF4"),
    ]
    assert fora[0]["ultima"] == cenario["hoje"] - timedelta(days=3)


def test_tarefas_e_conferencia_do_cadastro(banco, cenario):
    from sgj.caixa import painel

    tarefas = painel.meu_dia(banco)["tarefas"]
    assert dict(tarefas["colunas"])["A fazer"] == 3 and tarefas["abertas"] == 5
    conferencia = tarefas["conferencia"]
    assert (conferencia["total"], conferencia["concluidas"]) == (2, 1)
    assert [(i["item"], i["n"]) for i in conferencia["pendencias"]] == [
        ("Confirmar o sistema do processo", 1), ("Vincular a pasta do processo no Drive", 1)]


def test_carteira_por_tribunal_com_cobertura_do_calendario(banco, cenario):
    from sgj.caixa import painel

    carteira = painel.meu_dia(banco)["carteira"]
    linhas = {t["tribunal"]: t for t in carteira["tribunais"]}
    assert linhas["TJRS"]["calendario_conferido"] and not linhas["TJSC"]["calendario_conferido"]
    assert carteira["totais"] == {"processos": 3, "sistema_a_confirmar": 2, "cliente_a_identificar": 1,
                                  "local_a_conferir": 2, "segredo": 1, "sem_calendario": 2}


def test_captura_por_oab_ok_incompleta_e_em_falha(banco, cenario):
    assert fonte(banco, "djen_oab").situacao == "ok"
    banco.execute("INSERT INTO djen.requisicao (request_id, pagina, disparada_em, processada_em, status_http, erro) "
                  "VALUES (10, 1, now() - interval '40 minutes', now() - interval '35 minutes', 503, 'Em manutenção'), "
                  "(11, 2, now() - interval '40 minutes', now() - interval '35 minutes', 200, NULL)")
    incompleta = fonte(banco, "djen_oab")
    assert incompleta.situacao == "atencao" and "Em manutenção" in incompleta.resumo
    banco.execute("UPDATE djen.requisicao SET disparada_em = disparada_em - interval '2 days'")
    falha = fonte(banco, "djen_oab")
    assert falha.situacao == "falha" and "Consultar o DJEN manualmente" in falha.resumo


def test_sincronizacao_datajud_e_consulta_por_processo(banco, cenario):
    assert fonte(banco, "sincronizacao").situacao == "ok"
    assert fonte(banco, "datajud").situacao == "aguardando"
    assert fonte(banco, "djen_processo").situacao == "aguardando"
    banco.execute(
        "INSERT INTO sgj.djen_requisicao (request_id, processo_id, npu, data_inicio, data_fim, url, processada_em, "
        "status_http, resultado, erro) VALUES (1, %s, '50000011120258210001', current_date, current_date, 'u', now(), "
        "200, 'parametro_ignorado', 'comunicações de outro processo')", (cenario["tjrs"],))
    suspensa = fonte(banco, "djen_processo")
    assert suspensa.situacao == "falha" and suspensa.resumo.startswith("Suspensa até")
    banco.execute("INSERT INTO sgj.coletas (fonte, situacao, erro) VALUES ('djen', 'falhou', 'relação inexistente')")
    assert fonte(banco, "sincronizacao").situacao == "falha"


@pytest.mark.parametrize(("expressao", "descricao"), [
    ("30 9 * * *", "diariamente às 06h30"),
    ("55 9,16 * * *", "diariamente às 06h55, 13h55"),
    ("*/5 11-12 * * *", "a cada 5 minutos, das 08h às 09h55"),
    ("0 3 * * 1", "0 3 * * 1"),
])
def test_agenda_em_horario_de_brasilia(expressao, descricao):
    from sgj.caixa import painel

    assert painel.descrever_agenda(expressao) == descricao


def test_semaforo():
    from sgj.caixa import painel

    hoje = datetime(2026, 10, 11, tzinfo=timezone.utc).date()
    assert [painel.semaforo(hoje + timedelta(days=d), hoje) for d in (-3, 0, 1, 2, 3, 7, 8)] == [
        "vencido", "hoje", "dois_dias", "dois_dias", "semana", "semana", "depois"]


@pytest.fixture(scope="module")
def cliente_web(banco, cenario):
    from fastapi.testclient import TestClient

    from sgj.caixa.web import criar_app

    anterior = os.environ.get("SGJ_AMBIENTE")
    os.environ["SGJ_AMBIENTE"] = "teste"
    try:
        yield TestClient(criar_app(banco.info.dsn), base_url="http://127.0.0.1:8000", headers=MESMA_ORIGEM)
    finally:
        if anterior is None:
            os.environ.pop("SGJ_AMBIENTE", None)
        else:
            os.environ["SGJ_AMBIENTE"] = anterior


def test_telas_do_painel_e_das_coletas(cliente_web):
    inicio = cliente_web.get("/")
    assert inicio.status_code == 200
    for trecho in ("Meu dia", "Prazos em ordem de vencimento", "5009999-11.2025.8.21.0001", "Conferência do cadastro",
                   "calendário não conferido", "Captura do DJEN por OAB"):
        assert trecho in inicio.text
    coletas = cliente_web.get("/coletas")
    assert coletas.status_code == 200
    assert "Saúde das coletas" in coletas.text and "Agendamentos indisponíveis" in coletas.text
    api = cliente_web.get("/api/painel").json()
    assert api["contagem_prazos"]["vencido"] == 1 and api["coletas"][0]["chave"] == "djen_oab"
    assert cliente_web.get("/api/coletas").json()["agendamentos"] == []


def test_rede_privada_exige_login_autorizado(banco, cenario, monkeypatch):
    from fastapi.testclient import TestClient

    from sgj.caixa.web import criar_app

    monkeypatch.setenv("SGJ_AMBIENTE", "rede_privada")
    monkeypatch.delenv("SGJ_USUARIOS", raising=False)
    with pytest.raises(RuntimeError, match="SGJ_USUARIOS"):
        criar_app(banco.info.dsn)
    monkeypatch.setenv("SGJ_USUARIOS", "Titular@Exemplo.invalid, outro@exemplo.invalid")
    cliente = TestClient(criar_app(banco.info.dsn))
    assert cliente.get("/").status_code == 403
    assert cliente.get("/api/painel", headers={"Tailscale-User-Login": "intruso@exemplo.invalid"}).status_code == 403
    pagina = cliente.get("/", headers={"Tailscale-User-Login": "titular@exemplo.invalid"})
    assert pagina.status_code == 200
    assert "rede privada · titular@exemplo.invalid" in pagina.text
    assert cliente.get("/saude").json() == {"banco": "ok"}
    # O Tailscale informa o login também quando outra página manda o navegador gravar no sistema.
    titular = {"Tailscale-User-Login": "titular@exemplo.invalid"}
    outro_site = cliente.post("/caixa/1/arquivar", headers={**titular, "Sec-Fetch-Site": "cross-site"})
    assert outro_site.status_code == 403 and "não partiu das telas" in outro_site.text
    assert cliente.post("/caixa/999999/arquivar", headers={**titular, "Sec-Fetch-Site": "same-origin"}).status_code == 404
    assert cliente.get("/api/docs", headers=titular).status_code == 404
    assert cliente.get("/openapi.json", headers=titular).status_code == 404
    monkeypatch.setenv("SGJ_AMBIENTE", "producao")
    with pytest.raises(RuntimeError, match="SGJ_AMBIENTE=rede_privada"):
        criar_app(banco.info.dsn)
