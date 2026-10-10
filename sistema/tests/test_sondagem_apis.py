"""Testes da sondagem de APIs sem acesso à rede."""

import pytest

from sgj.sondagem_apis import descrever_estrutura, main, parametros_djen


def test_estrutura_nao_expoe_valores():
    resposta = {"count": 2, "items": [{"texto": "conteúdo sigiloso", "numero": 123}, {"texto": "outro"}]}
    estrutura = descrever_estrutura(resposta)
    assert estrutura == {"count": "int", "items": {"itens": 2, "primeiro": {"texto": "str", "numero": "int"}}}
    assert "sigiloso" not in str(estrutura)


def test_estrutura_limita_profundidade_e_trata_lista_vazia():
    assert descrever_estrutura({"a": {"b": {"c": 1}}}, profundidade=1) == {"a": {"b": "..."}}
    assert descrever_estrutura([]) == "lista vazia"


def test_parametros_djen_podem_ser_ajustados_ou_removidos():
    p = parametros_djen("107046", "RS", "2026-10-09", ["itensPorPagina=10", "pagina=", "siglaTribunal=TJRS"])
    assert p["itensPorPagina"] == "10"
    assert "pagina" not in p
    assert p["siglaTribunal"] == "TJRS"
    assert p["dataDisponibilizacaoInicio"] == p["dataDisponibilizacaoFim"] == "2026-10-09"


def test_npu_invalido_e_recusado_antes_de_qualquer_chamada():
    with pytest.raises(SystemExit):
        main(["datajud", "--tribunal", "tjrs", "--npu", "5001234-56.2025"])
