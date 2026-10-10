"""Testes do motor de prazos com calendário sintético.

Tribunal "TJX" e todas as ocorrências são fictícios; os testes verificam a
mecânica do cálculo, não feriados reais. Semana de referência: segunda-feira,
03/08/2026.
"""

from datetime import date

import pytest

from sgj.prazos import (
    NACIONAL,
    Calendario,
    CalculoRecusado,
    CalendarioInconsistente,
    Contagem,
    Ocorrencia,
    TipoOcorrencia,
    calcular_prazo,
)

FONTE = "https://exemplo.invalid/ato-de-teste"


def cal(*ocorrencias, cobertura=(("TJX", None, 2026),)):
    return Calendario(ocorrencias, cobertura)


def oc(dia, tipo=TipoOcorrencia.FERIADO, tribunal="TJX", comarca=None, descricao="Teste"):
    return Ocorrencia(date.fromisoformat(dia), tipo, tribunal, descricao, FONTE, comarca)


def prazo(calendario, disponibilizacao="2026-08-03", dias=5, **kw):
    kw.setdefault("tribunal", "TJX")
    return calcular_prazo(calendario, disponibilizacao=date.fromisoformat(disponibilizacao), dias=dias, **kw)


def test_caso_basico_sem_ocorrencias():
    r = prazo(cal())
    assert r.publicacao == date(2026, 8, 4)
    assert r.inicio == date(2026, 8, 5)
    assert r.vencimento_sem_prorrogacao == date(2026, 8, 11)
    assert r.vencimento == date(2026, 8, 11)
    assert r.data_controle == date(2026, 8, 11)
    assert r.prazo_interno == date(2026, 8, 7)
    assert r.calendario_conferido
    assert r.alertas == ()


def test_disponibilizacao_na_sexta_publica_na_segunda():
    r = prazo(cal(), disponibilizacao="2026-08-07")
    assert r.publicacao == date(2026, 8, 10)
    assert r.inicio == date(2026, 8, 11)
    assert r.vencimento == date(2026, 8, 17)


def test_feriado_no_dia_da_publicacao_desloca_publicacao():
    r = prazo(cal(oc("2026-08-04")))
    assert r.publicacao == date(2026, 8, 5)
    assert r.inicio == date(2026, 8, 6)
    assert r.vencimento == date(2026, 8, 12)


def test_feriado_no_meio_do_prazo_nao_conta_e_aparece_na_memoria():
    r = prazo(cal(oc("2026-08-06", descricao="Feriado fictício")))
    assert r.vencimento == date(2026, 8, 12)
    assert any("06/08/2026" in linha and "Feriado fictício" in linha for linha in r.memoria)


def test_suspensao_permite_publicacao_mas_nao_conta_prazo():
    c = cal()
    c.adicionar_periodo(date(2026, 8, 4), date(2026, 8, 6), TipoOcorrencia.SUSPENSAO, "TJX", "Suspensão", FONTE)
    r = prazo(c)
    assert r.publicacao == date(2026, 8, 4)
    assert r.inicio == date(2026, 8, 7)
    assert r.vencimento == date(2026, 8, 13)


def test_indisponibilidade_no_vencimento_prorroga_apenas_a_data_informativa():
    r = prazo(cal(oc("2026-08-11", TipoOcorrencia.INDISPONIBILIDADE)))
    assert r.vencimento_sem_prorrogacao == date(2026, 8, 11)
    assert r.vencimento == date(2026, 8, 12)
    assert r.data_controle == date(2026, 8, 11)
    assert any(a.startswith("Vencimento (11/08/2026)") for a in r.alertas)


def test_expediente_alterado_no_dia_do_comeco_prorroga_o_comeco():
    r = prazo(cal(oc("2026-08-04", TipoOcorrencia.EXPEDIENTE_ALTERADO)))
    assert r.vencimento_sem_prorrogacao == date(2026, 8, 11)
    assert r.vencimento == date(2026, 8, 12)
    assert any(a.startswith("Dia do começo (04/08/2026)") for a in r.alertas)


def test_prazo_em_dobro():
    r = prazo(cal(), multiplicador=2)
    assert r.vencimento == date(2026, 8, 18)
    assert any("em dobro, total de 10" in linha for linha in r.memoria)


def test_margem_interna_maior_que_o_prazo_e_limitada_ao_inicio():
    r = prazo(cal(), dias=1)
    assert r.vencimento == date(2026, 8, 5)
    assert r.prazo_interno == date(2026, 8, 5)
    assert any("Margem interna" in a for a in r.alertas)


def test_calendario_sem_cobertura_marca_calculo_como_nao_confiavel():
    r = prazo(cal(cobertura=()))
    assert not r.calendario_conferido
    assert r.alertas[0].startswith("CALENDÁRIO NÃO CONFERIDO para TJX em 2026")


def test_virada_de_ano_exige_cobertura_dos_dois_anos():
    r = prazo(cal(), disponibilizacao="2026-12-28", dias=10)
    assert r.vencimento.year == 2027
    assert not r.calendario_conferido
    assert "2027" in r.alertas[0]


def test_feriado_municipal_vale_apenas_para_a_comarca():
    c = cal(oc("2026-08-04", comarca="Cidade A"), cobertura=())
    assert prazo(c, comarca="Cidade A").publicacao == date(2026, 8, 5)
    assert prazo(c, comarca="Cidade B").publicacao == date(2026, 8, 4)
    assert prazo(c).publicacao == date(2026, 8, 4)


def test_ocorrencia_nacional_vale_para_todos_e_de_outro_tribunal_nao():
    c = cal(oc("2026-08-04", tribunal=NACIONAL), oc("2026-08-06", tribunal="TJY"))
    r = prazo(c)
    assert r.publicacao == date(2026, 8, 5)
    assert r.vencimento == date(2026, 8, 12)


def test_ocorrencia_sem_fonte_e_rejeitada():
    with pytest.raises(CalendarioInconsistente, match="sem fonte"):
        Ocorrencia(date(2026, 8, 4), TipoOcorrencia.FERIADO, "TJX", "Feriado", "  ")


def test_ocorrencia_nacional_com_comarca_e_rejeitada():
    with pytest.raises(CalendarioInconsistente):
        Ocorrencia(date(2026, 8, 4), TipoOcorrencia.FERIADO, NACIONAL, "Feriado", FONTE, "Cidade A")


@pytest.mark.parametrize(
    "parametros",
    [{"contagem": Contagem.CORRIDOS}, {"dias": 0}, {"multiplicador": 3}, {"margem_interna": -1}],
)
def test_parametros_sem_regra_definida_sao_recusados(parametros):
    with pytest.raises(CalculoRecusado):
        prazo(cal(), **parametros)


def test_calendario_sem_dia_util_levanta_erro():
    c = cal()
    c.adicionar_periodo(date(2026, 8, 4), date(2027, 12, 31), TipoOcorrencia.FERIADO, "TJX", "Erro", FONTE)
    with pytest.raises(CalendarioInconsistente, match="revise o calendário"):
        prazo(c)


def test_carga_por_csv(tmp_path):
    ocorrencias = tmp_path / "calendario.csv"
    ocorrencias.write_text(
        "data_inicio,data_fim,tipo,tribunal,comarca,descricao,fonte\n"
        f"2026-08-04,2026-08-06,suspensao,TJX,,Suspensão,{FONTE}\n"
        f"2026-08-11,,feriado,TJX,Cidade A,Feriado municipal,{FONTE}\n",
        encoding="utf-8",
    )
    cobertura = tmp_path / "cobertura.csv"
    cobertura.write_text(
        "tribunal,comarca,ano,conferido_por,conferido_em\nTJX,Cidade A,2026,Titular,2026-10-09\n",
        encoding="utf-8",
    )
    c = Calendario.de_csv(ocorrencias, cobertura)
    r = prazo(c, comarca="Cidade A")
    assert r.inicio == date(2026, 8, 7)
    assert r.vencimento == date(2026, 8, 14)
    assert r.calendario_conferido


def test_csv_com_tipo_invalido_indica_a_linha(tmp_path):
    ocorrencias = tmp_path / "calendario.csv"
    ocorrencias.write_text(
        "data_inicio,data_fim,tipo,tribunal,comarca,descricao,fonte\n"
        f"2026-08-04,,ferias,TJX,,Teste,{FONTE}\n",
        encoding="utf-8",
    )
    with pytest.raises(CalendarioInconsistente, match="linha 2"):
        Calendario.de_csv(ocorrencias)


def test_modelos_da_fase0_sao_lidos_pelo_motor():
    from pathlib import Path

    modelos = Path(__file__).parents[2] / "docs" / "fase0" / "modelos"
    c = Calendario.de_csv(modelos / "calendario_forense.csv", modelos / "calendario_cobertura.csv")
    assert not c.conferido("TJRS", None, 2026)


def test_csv_sem_fonte_indica_a_linha(tmp_path):
    ocorrencias = tmp_path / "calendario.csv"
    ocorrencias.write_text(
        "data_inicio,data_fim,tipo,tribunal,comarca,descricao,fonte\n"
        f"2026-08-04,,feriado,TJX,,Teste,{FONTE}\n"
        "2026-08-05,,feriado,TJX,,Sem fonte,\n",
        encoding="utf-8",
    )
    with pytest.raises(CalendarioInconsistente, match="linha 3.*sem fonte"):
        Calendario.de_csv(ocorrencias)
