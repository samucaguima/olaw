"""Caixa de Publicações: cálculo, aprovação e arquivamento, com dados fictícios."""

import json
import os
from datetime import date

import pytest

psycopg = pytest.importorskip("psycopg")

pytestmark = pytest.mark.skipif(not os.environ.get("SGJ_TEST_PG_DSN"), reason="SGJ_TEST_PG_DSN não definido")

from sgj.caixa import servico  # noqa: E402
from sgj.caixa.servico import OperacaoRecusada  # noqa: E402

FONTE = "https://exemplo.invalid/ato"


def inserir(banco, sql, params=()):
    return banco.execute(sql + " RETURNING id", params).fetchone()[0]


@pytest.fixture(scope="module")
def dados(banco):
    ids = {}
    ids["titular"] = inserir(banco, "INSERT INTO sgj.usuarios (nome, email, perfil) VALUES ('Titular', 't@exemplo.invalid', 'titular')")
    cliente = inserir(banco, "INSERT INTO sgj.clientes (codigo, nome) VALUES ('C0001', 'Cliente Exemplo')")
    caso = inserir(banco, "INSERT INTO sgj.casos (codigo, cliente_id, titulo, area) VALUES ('K0001', %s, 'Revisional', 'bancario')", (cliente,))
    ids["p1"] = inserir(banco, "INSERT INTO sgj.processos (caso_id, npu, tribunal, comarca, grau) "
                               "VALUES (%s, '50000011120258210001', 'TJRS', 'Torres', 1)", (caso,))
    ids["p2"] = inserir(banco, "INSERT INTO sgj.processos (caso_id, npu, tribunal) VALUES (%s, '50000022220258210002', 'TJRS')", (caso,))

    def legal(tipo, dias, contagem="uteis", termo="publicacao", obs=None):
        return inserir(banco, "INSERT INTO sgj.prazos_legais (tipo_ato, dias, contagem, dispositivo, link_oficial, conferido_em, "
                              "conferido_por, termo, observacoes) VALUES (%s, %s, %s, 'dispositivo de teste', %s, '2026-10-10', %s, %s, %s)",
                       (tipo, dias, contagem, FONTE, ids["titular"], termo, obs))

    ids["manifestacao"] = legal("manifestacao_sem_prazo_fixado", 5)
    ids["recurso"] = legal("recurso_ou_resposta", 15)
    ids["contestacao"] = legal("contestacao", 15, termo="manual", obs="Termo inicial pelos incisos do art. 335")
    ids["pagamento"] = legal("pagamento_cumprimento_sentenca", 15, obs="[CONFERIR] natureza do prazo de pagamento")
    ids["corridos"] = legal("prazo_em_dias_corridos", 10, contagem="corridos")

    banco.execute("INSERT INTO sgj.calendario (tribunal, data, tipo, descricao, fonte_link) "
                  "VALUES ('*', '2026-09-07', 'feriado', 'Independência', %s)", (FONTE,))
    banco.execute("INSERT INTO sgj.calendario_cobertura (tribunal, comarca, ano, conferido_por, conferido_em) "
                  "VALUES ('TJRS', 'Torres', 2026, %s, '2026-10-10')", (ids["titular"],))

    def publicacao(chave, processo, tribunal, data, texto="Fica intimada a parte."):
        npu = {None: "50099999920258210001"}.get(processo, None)
        ids[chave] = inserir(
            banco,
            "INSERT INTO sgj.publicacoes (processo_id, npu, hash, data_disponibilizacao, tribunal, tipo_comunicacao, texto) "
            "VALUES (%s, coalesce(%s, (SELECT npu FROM sgj.processos WHERE id = %s)), %s, %s, %s, 'Intimação', %s)",
            (processo, npu, processo, f"hash-{chave}", data, tribunal, texto),
        )

    publicacao("a", ids["p1"], "TJRS", "2026-08-03")
    publicacao("b", ids["p2"], "TJRS", "2026-08-03")
    publicacao("c", ids["p1"], "STJ", "2026-09-01")
    publicacao("d", ids["p1"], None, "2026-08-03")
    publicacao("e", None, "TJRS", "2026-08-03")
    publicacao("f", ids["p1"], "TJRS", "2026-08-10")
    publicacao("g", ids["p1"], "TJRS", "2026-09-04")
    publicacao("h", ids["p1"], "TJRS", "2026-09-04", "<script>alert(1)</script> intimação")
    publicacao("i", ids["p1"], "TJRS", "2026-08-12")
    return ids


def test_calculo_com_calendario_conferido(banco, dados):
    s = servico.simular_prazo(banco, dados["a"], prazo_legal_id=dados["manifestacao"])
    r = s.resultado
    assert (r.publicacao, r.inicio, r.vencimento_sem_prorrogacao, r.prazo_interno) == (
        date(2026, 8, 4), date(2026, 8, 5), date(2026, 8, 11), date(2026, 8, 7))
    assert (s.tribunal, s.comarca, s.confiavel, s.alertas) == ("TJRS", "Torres", True, ())


def test_feriado_nacional_adia_publicacao_e_vencimento(banco, dados):
    r = servico.simular_prazo(banco, dados["g"], prazo_legal_id=dados["manifestacao"]).resultado
    assert (r.publicacao, r.inicio, r.vencimento_sem_prorrogacao, r.prazo_interno) == (
        date(2026, 9, 8), date(2026, 9, 9), date(2026, 9, 15), date(2026, 9, 11))


def test_grau_desconhecido_nao_e_confiavel(banco, dados):
    s = servico.simular_prazo(banco, dados["b"], prazo_legal_id=dados["manifestacao"])
    assert not s.confiavel and s.comarca is None
    assert any("Grau ou comarca" in a for a in s.alertas)


def test_publicacao_do_stj_usa_o_calendario_do_stj(banco, dados):
    s = servico.simular_prazo(banco, dados["c"], prazo_legal_id=dados["recurso"])
    assert (s.tribunal, s.comarca, s.confiavel) == ("STJ", None, False)
    assert s.alertas[0].startswith("CALENDÁRIO NÃO CONFERIDO para STJ")


def test_tribunal_nao_informado_usa_a_origem_com_alerta(banco, dados):
    s = servico.simular_prazo(banco, dados["d"], prazo_legal_id=dados["manifestacao"])
    assert s.tribunal == "TJRS" and not s.confiavel
    assert any("Tribunal que publicou não informado" in a for a in s.alertas)


def test_termo_diverso_da_publicacao_e_recusado(banco, dados):
    with pytest.raises(OperacaoRecusada, match="termo inicial não é a publicação"):
        servico.simular_prazo(banco, dados["a"], prazo_legal_id=dados["contestacao"])


def test_dias_corridos_sao_recusados(banco, dados):
    with pytest.raises(OperacaoRecusada, match="dias corridos"):
        servico.simular_prazo(banco, dados["a"], prazo_legal_id=dados["corridos"])


def test_dias_fora_da_tabela_e_observacao_conferir_viram_alerta(banco, dados):
    manual = servico.simular_prazo(banco, dados["a"], dias=10)
    assert "[CONFERIR] Prazo de 10 dias definido manualmente, fora da tabela de prazos legais." in manual.alertas
    pagamento = servico.simular_prazo(banco, dados["a"], prazo_legal_id=dados["pagamento"])
    assert any("[CONFERIR] natureza" in a for a in pagamento.alertas)
    with pytest.raises(OperacaoRecusada, match="Escolha o ato"):
        servico.simular_prazo(banco, dados["a"])


def test_aprovacao_grava_prazo_tarefa_e_auditoria(banco, dados):
    resultado = servico.aprovar_prazo(banco, dados["a"], dados["titular"], prazo_legal_id=dados["recurso"])
    prazo = banco.execute(
        "SELECT situacao, aprovado_por, data_publicacao, data_inicio, data_fatal, data_interna, calendario_conferido, "
        "memoria_calculo->'prazo_legal'->>'tipo_ato' FROM sgj.prazos WHERE id = %s", (resultado["prazo_id"],)).fetchone()
    assert prazo == ("confirmado", dados["titular"], date(2026, 8, 4), date(2026, 8, 5), date(2026, 8, 25),
                     date(2026, 8, 21), True, "recurso_ou_resposta")
    tarefa = banco.execute(
        "SELECT tipo, origem, prazo_id, vencimento_interno, responsavel, titulo FROM sgj.tarefas WHERE id = %s",
        (resultado["tarefa_id"],)).fetchone()
    assert tarefa == ("prazo_processual", "publicacao", resultado["prazo_id"], date(2026, 8, 21), dados["titular"],
                      "Recurso ou resposta a recurso (TJRS)")
    assert banco.execute("SELECT situacao_triagem FROM sgj.publicacoes WHERE id = %s", (dados["a"],)).fetchone()[0] == "aprovada"
    acoes = [linha[0] for linha in banco.execute("SELECT acao FROM sgj.auditoria ORDER BY id").fetchall()]
    assert acoes[-3:] == ["aprovar_prazo", "criar_tarefa", "alterar_situacao"]
    with pytest.raises(OperacaoRecusada, match="já tratada"):
        servico.aprovar_prazo(banco, dados["a"], dados["titular"], prazo_legal_id=dados["recurso"])


def test_aprovacao_nao_confiavel_entra_na_lista_da_tarefa(banco, dados):
    resultado = servico.aprovar_prazo(banco, dados["b"], dados["titular"], prazo_legal_id=dados["manifestacao"],
                                      providencia="Manifestar sobre o laudo")
    titulo, checklist = banco.execute("SELECT titulo, checklist FROM sgj.tarefas WHERE id = %s",
                                      (resultado["tarefa_id"],)).fetchone()
    assert titulo == "Manifestar sobre o laudo"
    assert [i["item"] for i in checklist][-1].startswith("Conferir a contagem do prazo")


def test_publicacao_sem_processo_nao_aprova(banco, dados):
    assert servico.simular_prazo(banco, dados["e"], prazo_legal_id=dados["manifestacao"]).tribunal == "TJRS"
    with pytest.raises(OperacaoRecusada, match="Processo não cadastrado"):
        servico.aprovar_prazo(banco, dados["e"], dados["titular"], prazo_legal_id=dados["manifestacao"])


def test_arquivamento_registra_motivo(banco, dados):
    servico.arquivar_publicacao(banco, dados["f"], dados["titular"], "Mera ciência")
    assert banco.execute("SELECT situacao_triagem FROM sgj.publicacoes WHERE id = %s", (dados["f"],)).fetchone()[0] == "arquivada"
    depois = banco.execute("SELECT depois FROM sgj.auditoria WHERE acao = 'arquivar_publicacao' ORDER BY id DESC LIMIT 1").fetchone()[0]
    assert depois == {"situacao_triagem": "arquivada", "motivo": "Mera ciência"}


def test_lista_e_filtros(banco, dados):
    itens, total = servico.listar_publicacoes(banco, situacao="pendentes")
    assert total == len(itens) and dados["a"] not in [i["id"] for i in itens]
    _, total_stj = servico.listar_publicacoes(banco, situacao="todas", tribunal="STJ")
    assert total_stj == 1
    itens, _ = servico.listar_publicacoes(banco, situacao="todas", busca="5000002-22")
    assert {i["id"] for i in itens} == {dados["b"]}
    assert servico.resumo(banco)["sem_processo"] == 1


# Interface web e API

@pytest.fixture(scope="module")
def cliente_web(banco, dados):
    from fastapi.testclient import TestClient

    from sgj.caixa.web import criar_app

    anterior = os.environ.get("SGJ_AMBIENTE")
    os.environ["SGJ_AMBIENTE"] = "teste"
    try:
        yield TestClient(criar_app(banco.info.dsn))
    finally:
        if anterior is None:
            os.environ.pop("SGJ_AMBIENTE", None)
        else:
            os.environ["SGJ_AMBIENTE"] = anterior


def test_interface_exige_ambiente_de_teste(monkeypatch):
    from sgj.caixa.web import criar_app

    monkeypatch.delenv("SGJ_AMBIENTE", raising=False)
    with pytest.raises(RuntimeError, match="SGJ_AMBIENTE=teste"):
        criar_app("dbname=nenhum")


def test_telas_de_lista_e_de_calculo(cliente_web, dados):
    lista = cliente_web.get("/caixa")
    assert lista.status_code == 200 and "5000001-11.2025.8.21.0001" in lista.text
    calculo = cliente_web.post(f"/caixa/{dados['g']}/calcular", data={"prazo_legal_id": str(dados["manifestacao"])})
    assert calculo.status_code == 200 and "15/09/2026" in calculo.text and "11/09/2026" in calculo.text
    recusa = cliente_web.post(f"/caixa/{dados['g']}/calcular", data={"prazo_legal_id": str(dados["contestacao"])})
    assert recusa.status_code == 422 and "Não executado" in recusa.text


def test_aprovacao_pela_tela(cliente_web, dados):
    resposta = cliente_web.post(f"/caixa/{dados['g']}/aprovar", data={"prazo_legal_id": str(dados["manifestacao"])},
                                follow_redirects=False)
    assert resposta.status_code == 303
    tela = cliente_web.get(resposta.headers["location"])
    assert "Prazo aprovado e tarefa criada." in tela.text and "15/09/2026" in tela.text


def test_texto_da_publicacao_e_escapado(cliente_web, dados):
    tela = cliente_web.get(f"/caixa/{dados['h']}")
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in tela.text and "<script>alert" not in tela.text


def test_api_json(cliente_web, dados):
    simulacao = cliente_web.post(f"/api/publicacoes/{dados['i']}/simulacao",
                                 content=json.dumps({"prazo_legal_id": dados["manifestacao"]}),
                                 headers={"Content-Type": "application/json"})
    assert simulacao.status_code == 200 and simulacao.json()["vencimento_controle"] == "2026-08-20"
    recusa = cliente_web.post(f"/api/publicacoes/{dados['i']}/simulacao", json={"prazo_legal_id": dados["contestacao"]})
    assert recusa.status_code == 422
    aprovacao = cliente_web.post(f"/api/publicacoes/{dados['i']}/aprovacao", json={"prazo_legal_id": dados["manifestacao"]})
    assert aprovacao.status_code == 201 and aprovacao.json()["calculo"]["prazo_interno"] == "2026-08-18"
    assert cliente_web.get("/api/publicacoes", params={"situacao": "aprovada"}).json()["total"] >= 3
