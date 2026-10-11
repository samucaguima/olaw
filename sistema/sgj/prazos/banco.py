"""Carga do calendário forense a partir do banco (tabelas sgj.calendario e sgj.calendario_cobertura)."""

from __future__ import annotations

from typing import Iterable

from psycopg.rows import dict_row

from .calendario import NACIONAL, Calendario, Ocorrencia, TipoOcorrencia


def carregar_calendario(conexao, tribunais: Iterable[str]) -> Calendario:
    """Ocorrências nacionais e dos tribunais indicados, com a cobertura conferida de cada um."""
    tribunais = sorted({t for t in tribunais if t})
    calendario = Calendario()
    with conexao.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            "SELECT tribunal, comarca, data, tipo, descricao, fonte_link FROM sgj.calendario "
            "WHERE tribunal = %s OR tribunal = ANY(%s) ORDER BY data, id",
            (NACIONAL, tribunais),
        )
        for linha in cursor:
            calendario.adicionar(
                Ocorrencia(
                    data=linha["data"],
                    tipo=TipoOcorrencia(linha["tipo"]),
                    tribunal=linha["tribunal"],
                    descricao=linha["descricao"],
                    fonte=linha["fonte_link"],
                    comarca=linha["comarca"] or None,
                )
            )
        cursor.execute(
            "SELECT tribunal, comarca, ano FROM sgj.calendario_cobertura WHERE tribunal = ANY(%s)",
            (tribunais,),
        )
        for linha in cursor:
            calendario.marcar_conferido(linha["tribunal"], linha["comarca"] or None, linha["ano"])
    return calendario
