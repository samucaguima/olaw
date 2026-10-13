"""Conferência do cadastro importado e cadastro de processo a partir de publicação fora da carteira."""

import json
import os

import pytest

psycopg = pytest.importorskip("psycopg")

pytestmark = pytest.mark.skipif(not os.environ.get("SGJ_TEST_PG_DSN"), reason="SGJ_TEST_PG_DSN não definido")

# Cabeçalho com que o navegador atesta que a gravação partiu das telas do próprio sistema (web.py).
MESMA_ORIGEM = {"Sec-Fetch-Site": "same-origin"}

ITENS = [
    'Revisar o cadastro: o processo estava com a situação "revisar" no protótipo',
    "Identificar o cliente e vincular o caso a ele",
    "Confirmar o sistema do processo",
    "Conferir o grau e a comarca",
    "Conferir o polo do cliente",
    "Confirmar se o processo tramita em segredo de justiça (a IA fica desabilitada para processos sigilosos)",
    "Vincular a pasta do processo no Drive",
]


def npu(numero: str, resto: str) -> str:
    """Numeração com o dígito verificador correto (numero: 7 dígitos; resto: ano, segmento, tribunal e origem)."""
    from sgj.caixa.cadastro import digito_verificador

    provisoria = numero + "00" + resto
    return numero + digito_verificador(provisoria) + resto


NPU_IMPORTADO = npu("5000001", "20258210001")
NPU_FORA = npu("5009999", "20258210003")


@pytest.fixture(scope="module")
def cenario(banco):
    banco.execute("INSERT INTO sgj.usuarios (nome, email, perfil) VALUES ('Titular', 'titular@exemplo.invalid', 'titular')")
    provisorio = banco.execute(
        "INSERT INTO sgj.clientes (codigo, nome, provisorio) VALUES ('C0000', 'Cliente a identificar', true) RETURNING id"
    ).fetchone()[0]
    banco.execute("INSERT INTO sgj.clientes (codigo, nome, cpf_cnpj, tipo) VALUES ('C0001', 'Maria Exemplo', '12345678901', 'PF')")
    caso = banco.execute("INSERT INTO sgj.casos (codigo, cliente_id, titulo) VALUES ('K0001', %s, 'Revisional') RETURNING id",
                         (provisorio,)).fetchone()[0]
    processo = banco.execute("INSERT INTO sgj.processos (caso_id, npu, tribunal) VALUES (%s, %s, 'TJRS') RETURNING id",
                             (caso, NPU_IMPORTADO)).fetchone()[0]
    tarefa = banco.execute(
        "INSERT INTO sgj.tarefas (processo_id, origem, tipo, titulo, checklist) "
        "VALUES (%s, 'importacao', 'interna', 'Conferir o cadastro importado do protótipo', %s) RETURNING id",
        (processo, json.dumps([{"item": t, "concluido": False} for t in ITENS]))).fetchone()[0]
    for dia, tipo in (("2026-10-05", "Sentença"), ("2026-09-20", "Despacho")):
        banco.execute("INSERT INTO sgj.publicacoes (npu, hash, data_disponibilizacao, tribunal, tipo_comunicacao, texto) "
                      "VALUES (%s, %s, %s, 'TJRS', %s, 'Texto.')", (NPU_FORA, f"h{dia}", dia, tipo))
    titular = banco.execute("SELECT id FROM sgj.usuarios").fetchone()[0]
    return {"tarefa": tarefa, "processo": processo, "caso": caso, "titular": titular}


def formulario(**mudancas):
    base = {"caso_titulo": "Revisional", "segredo": "nao", "cliente_acao": "manter"}
    return {**base, **mudancas}


def salvar(banco, cenario, concluir=(), **campos):
    from sgj.caixa import cadastro

    return cadastro.salvar_conferencia(banco, cenario["tarefa"], cenario["titular"], formulario(**campos), list(concluir))


def processo(banco, cenario):
    return banco.execute(
        "SELECT sistema, sistema_fonte, grau, comarca, polo, segredo_justica, drive_pasta_id FROM sgj.processos WHERE id = %s",
        (cenario["processo"],)).fetchone()


def itens_concluidos(banco, cenario):
    checklist = banco.execute("SELECT checklist FROM sgj.tarefas WHERE id = %s", (cenario["tarefa"],)).fetchone()[0]
    return [i for i, item in enumerate(checklist) if item["concluido"]]


def test_numero_unico_e_pasta_do_drive():
    from sgj.caixa.cadastro import identificador_pasta, npu_valido, OperacaoRecusada

    assert npu_valido(NPU_FORA) and not npu_valido(NPU_FORA[:7] + "00" + NPU_FORA[9:])
    assert identificador_pasta("https://drive.google.com/drive/folders/1AbC_def-ghiJKL?usp=sharing") == "1AbC_def-ghiJKL"
    assert identificador_pasta("1AbC_def-ghiJKL") == "1AbC_def-ghiJKL"
    with pytest.raises(OperacaoRecusada):
        identificador_pasta("pasta do cliente")


def test_item_sem_o_dado_correspondente_nao_conclui_e_nada_e_gravado(banco, cenario):
    from sgj.caixa.cadastro import OperacaoRecusada

    with pytest.raises(OperacaoRecusada, match="sistema não informado"):
        salvar(banco, cenario, concluir=[2], comarca="Torres", grau="1")
    assert processo(banco, cenario)[2:4] == (None, None)
    assert itens_concluidos(banco, cenario) == []


def test_dados_gravados_concluem_os_itens_que_sustentam(banco, cenario):
    salvar(banco, cenario, concluir=[2, 3, 4], sistema="eproc", grau="1", comarca="Torres", polo="passivo")
    assert processo(banco, cenario)[:5] == ("eproc", "titular", 1, "Torres", "passivo")
    assert itens_concluidos(banco, cenario) == [2, 3, 4]
    acoes = banco.execute("SELECT acao, entidade FROM sgj.auditoria ORDER BY id").fetchall()
    assert ("alterar_cadastro", "processos") in acoes and ("conferir_cadastro", "tarefas") in acoes


def test_segredo_de_justica_exige_confirmacao_expressa(banco, cenario):
    from sgj.caixa.cadastro import OperacaoRecusada

    with pytest.raises(OperacaoRecusada, match="confirmação do segredo"):
        salvar(banco, cenario, concluir=[5], sistema="eproc", grau="1", comarca="Torres", polo="passivo", segredo="sim")
    assert processo(banco, cenario)[5] is False
    salvar(banco, cenario, concluir=[5], sistema="eproc", grau="1", comarca="Torres", polo="passivo", segredo="sim",
           segredo_confirmado="1")
    assert processo(banco, cenario)[5] is True and 5 in itens_concluidos(banco, cenario)
    # Retirar o segredo também exige a confirmação, mesmo sem marcar item.
    with pytest.raises(OperacaoRecusada, match="mudar o segredo"):
        salvar(banco, cenario, sistema="eproc", grau="1", comarca="Torres", polo="passivo", segredo="nao")
    assert processo(banco, cenario)[5] is True


def test_cliente_novo_tira_o_caso_do_provisorio_e_documento_repetido_e_recusado(banco, cenario):
    from sgj.caixa.cadastro import OperacaoRecusada

    campos = {"sistema": "eproc", "grau": "1", "comarca": "Torres", "polo": "passivo", "segredo": "sim"}
    with pytest.raises(OperacaoRecusada, match="já cadastrado para o cliente C0001"):
        salvar(banco, cenario, concluir=[1], cliente_acao="novo", cliente_novo_nome="João Exemplo",
               cliente_novo_documento="123.456.789-01", **campos)
    salvar(banco, cenario, concluir=[1], cliente_acao="novo", cliente_novo_nome="João  Exemplo",
           cliente_novo_documento="98.765.432/0001-10", **campos)
    cliente = banco.execute("SELECT k.codigo, k.nome, k.cpf_cnpj, k.tipo FROM sgj.casos c JOIN sgj.clientes k ON k.id = c.cliente_id "
                            "WHERE c.id = %s", (cenario["caso"],)).fetchone()
    assert cliente == ("C0002", "João Exemplo", "98765432000110", "PJ")
    assert 1 in itens_concluidos(banco, cenario)


def test_ultimos_itens_concluem_a_conferencia(banco, cenario):
    from sgj.caixa import cadastro

    salvar(banco, cenario, concluir=[0, 6], sistema="eproc", grau="1", comarca="Torres", polo="passivo", segredo="sim",
           drive_pasta="https://drive.google.com/drive/folders/1AbC_def-ghiJKL")
    assert banco.execute("SELECT situacao FROM sgj.tarefas WHERE id = %s", (cenario["tarefa"],)).fetchone()[0] == "concluida"
    assert cadastro.listar_conferencias(banco) == []
    assert len(cadastro.listar_conferencias(banco, situacao="concluidas")) == 1
    with pytest.raises(cadastro.OperacaoRecusada, match="já concluída"):
        salvar(banco, cenario)


def test_cadastro_de_processo_fora_da_carteira(banco, cenario):
    from sgj.caixa import cadastro

    base = {"npu": NPU_FORA, "segredo": "nao", "caso_titulo": "Execução x Banco", "cliente_acao": "existente",
            "cliente_existente": "C0001", "polo": "passivo"}
    with pytest.raises(cadastro.OperacaoRecusada, match="dígito verificador"):
        cadastro.cadastrar_processo(banco, cenario["titular"], {**base, "npu": NPU_FORA[:7] + "00" + NPU_FORA[9:]})
    with pytest.raises(cadastro.OperacaoRecusada, match="segredo de justiça"):
        cadastro.cadastrar_processo(banco, cenario["titular"], {**base, "segredo": ""})
    resultado = cadastro.cadastrar_processo(banco, cenario["titular"], base)
    assert (resultado["caso_codigo"], resultado["publicacoes_vinculadas"]) == ("K0002", 2)
    novo = banco.execute("SELECT tribunal, sistema, polo, segredo_justica FROM sgj.processos WHERE npu = %s", (NPU_FORA,)).fetchone()
    assert novo == ("TJRS", None, "passivo", False)
    pendentes = [i["texto"] for i in cadastro.obter_conferencia(banco, resultado["tarefa_id"])["itens"]]
    assert pendentes == ["Definir a área do caso", "Confirmar o sistema do processo", "Conferir o grau e a comarca",
                         "Vincular a pasta do processo no Drive"]
    with pytest.raises(cadastro.OperacaoRecusada, match="já cadastrado"):
        cadastro.cadastrar_processo(banco, cenario["titular"], base)


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


def test_telas_de_conferencia_e_de_cadastro(banco, cenario, cliente_web):
    lista = cliente_web.get("/conferencia?situacao=concluidas")
    assert lista.status_code == 200 and "conferido" in lista.text
    tarefa = banco.execute("SELECT id FROM sgj.tarefas WHERE titulo = 'Conferir o cadastro do processo'").fetchone()[0]
    tela = cliente_web.get(f"/conferencia/{tarefa}")
    assert tela.status_code == 200 and "Itens da conferência" in tela.text
    recusa = cliente_web.post(f"/conferencia/{tarefa}", data={"caso_titulo": "Execução x Banco", "segredo": "nao",
                                                              "cliente_acao": "manter", "concluir": ["1"]})
    assert recusa.status_code == 422 and "Nada foi gravado" in recusa.text
    gravado = cliente_web.post(f"/conferencia/{tarefa}", data={"caso_titulo": "Execução x Banco", "segredo": "nao",
                                                               "cliente_acao": "manter", "sistema": "eproc", "concluir": ["1"]},
                               follow_redirects=False)
    assert gravado.status_code == 303
    novo = npu("5007777", "20258210003")
    formulario = cliente_web.get(f"/processos/novo?npu={novo}")
    assert formulario.status_code == 200 and 'value="TJRS"' in formulario.text
    cadastrado = cliente_web.post("/processos/novo", data={"npu": novo, "segredo": "sim", "caso_titulo": "Novo caso",
                                                           "cliente_acao": "novo", "cliente_novo_nome": "Ana Exemplo"},
                                  follow_redirects=False)
    assert cadastrado.status_code == 303 and cadastrado.headers["location"].endswith("?ok=cadastrado")
