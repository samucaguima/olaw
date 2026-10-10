"""Calendário forense por tribunal e comarca.

O calendário é dado, não código: o sistema não presume nenhum feriado,
suspensão ou indisponibilidade. Toda ocorrência exige fonte (link do ato
do tribunal ou da norma) e só vale para o tribunal e a comarca indicados.

A cobertura registra quais anos foram conferidos pelo titular para cada
tribunal e comarca. O motor de prazos sinaliza como não confiável o
cálculo que atravessa período sem cobertura (falha segura).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum
from pathlib import Path
from typing import Callable, Iterable

NACIONAL = "*"


class TipoOcorrencia(str, Enum):
    FERIADO = "feriado"
    """Dia sem expediente forense: não é dia útil nem conta prazo."""

    SUSPENSAO = "suspensao"
    """Prazos suspensos: há expediente, mas o dia não conta prazo."""

    INDISPONIBILIDADE = "indisponibilidade"
    """Indisponibilidade do sistema: o dia conta, mas prorroga começo ou vencimento."""

    EXPEDIENTE_ALTERADO = "expediente_alterado"
    """Expediente encerrado antes ou iniciado depois: mesmo efeito da indisponibilidade."""


_SEM_EXPEDIENTE = {TipoOcorrencia.FERIADO}
_SEM_CONTAGEM = {TipoOcorrencia.FERIADO, TipoOcorrencia.SUSPENSAO}
_PRORROGAM = {TipoOcorrencia.INDISPONIBILIDADE, TipoOcorrencia.EXPEDIENTE_ALTERADO}

_DIAS_SEMANA = ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
                "sexta-feira", "sábado", "domingo")

LIMITE_BUSCA_DIAS = 400


class CalendarioInconsistente(ValueError):
    """Ocorrência inválida ou calendário que não permite encontrar dia útil."""


@dataclass(frozen=True)
class Ocorrencia:
    data: date
    tipo: TipoOcorrencia
    tribunal: str
    descricao: str
    fonte: str
    comarca: str | None = None

    def __post_init__(self) -> None:
        if not self.tribunal.strip():
            raise CalendarioInconsistente("Ocorrência sem tribunal (use '*' para nacional).")
        if not self.descricao.strip():
            raise CalendarioInconsistente(f"Ocorrência de {self.data} sem descrição.")
        if not self.fonte.strip():
            raise CalendarioInconsistente(
                f"Ocorrência de {self.data} ({self.descricao}) sem fonte; "
                "toda entrada do calendário exige o link do ato correspondente."
            )
        if self.tribunal == NACIONAL and self.comarca:
            raise CalendarioInconsistente("Ocorrência nacional não pode indicar comarca.")

    def aplica_se(self, tribunal: str, comarca: str | None) -> bool:
        if self.tribunal not in (NACIONAL, tribunal):
            return False
        return self.comarca is None or self.comarca == comarca


def nome_dia(d: date) -> str:
    return _DIAS_SEMANA[d.weekday()]


def formatar(d: date) -> str:
    return d.strftime("%d/%m/%Y")


class Calendario:
    def __init__(
        self,
        ocorrencias: Iterable[Ocorrencia] = (),
        cobertura: Iterable[tuple[str, str | None, int]] = (),
    ) -> None:
        self._por_data: dict[date, list[Ocorrencia]] = {}
        self._cobertura: set[tuple[str, str | None, int]] = set()
        for ocorrencia in ocorrencias:
            self.adicionar(ocorrencia)
        for tribunal, comarca, ano in cobertura:
            self.marcar_conferido(tribunal, comarca, ano)

    # Montagem

    def adicionar(self, ocorrencia: Ocorrencia) -> None:
        self._por_data.setdefault(ocorrencia.data, []).append(ocorrencia)

    def adicionar_periodo(
        self,
        inicio: date,
        fim: date,
        tipo: TipoOcorrencia,
        tribunal: str,
        descricao: str,
        fonte: str,
        comarca: str | None = None,
    ) -> None:
        if fim < inicio:
            raise CalendarioInconsistente(f"Período invertido: {inicio} a {fim}.")
        d = inicio
        while d <= fim:
            self.adicionar(Ocorrencia(d, tipo, tribunal, descricao, fonte, comarca))
            d += timedelta(days=1)

    def marcar_conferido(self, tribunal: str, comarca: str | None, ano: int) -> None:
        self._cobertura.add((tribunal, comarca or None, ano))

    # Consulta

    def conferido(self, tribunal: str, comarca: str | None, ano: int) -> bool:
        return (tribunal, comarca or None, ano) in self._cobertura

    def ocorrencias(self, d: date, tribunal: str, comarca: str | None) -> list[Ocorrencia]:
        return [o for o in self._por_data.get(d, []) if o.aplica_se(tribunal, comarca)]

    def tem_expediente(self, d: date, tribunal: str, comarca: str | None) -> bool:
        if d.weekday() >= 5:
            return False
        return not any(o.tipo in _SEM_EXPEDIENTE for o in self.ocorrencias(d, tribunal, comarca))

    def conta_prazo(self, d: date, tribunal: str, comarca: str | None) -> bool:
        if d.weekday() >= 5:
            return False
        return not any(o.tipo in _SEM_CONTAGEM for o in self.ocorrencias(d, tribunal, comarca))

    def prorrogacoes(self, d: date, tribunal: str, comarca: str | None) -> list[Ocorrencia]:
        return [o for o in self.ocorrencias(d, tribunal, comarca) if o.tipo in _PRORROGAM]

    def motivo_sem_contagem(self, d: date, tribunal: str, comarca: str | None) -> str | None:
        if d.weekday() >= 5:
            return nome_dia(d)
        impeditivas = [o for o in self.ocorrencias(d, tribunal, comarca) if o.tipo in _SEM_CONTAGEM]
        if not impeditivas:
            return None
        return "; ".join(f"{o.tipo.value}: {o.descricao} (fonte: {o.fonte})" for o in impeditivas)

    def proximo(self, d: date, criterio: Callable[[date], bool]) -> date:
        """Primeiro dia estritamente posterior a `d` que atende ao critério."""
        candidato = d
        for _ in range(LIMITE_BUSCA_DIAS):
            candidato += timedelta(days=1)
            if criterio(candidato):
                return candidato
        raise CalendarioInconsistente(
            f"Nenhum dia válido em {LIMITE_BUSCA_DIAS} dias após {formatar(d)}; revise o calendário."
        )

    def anterior(self, d: date, criterio: Callable[[date], bool]) -> date:
        """Último dia estritamente anterior a `d` que atende ao critério."""
        candidato = d
        for _ in range(LIMITE_BUSCA_DIAS):
            candidato -= timedelta(days=1)
            if criterio(candidato):
                return candidato
        raise CalendarioInconsistente(
            f"Nenhum dia válido em {LIMITE_BUSCA_DIAS} dias antes de {formatar(d)}; revise o calendário."
        )

    # Carga a partir de planilhas (modelos em docs/fase0/modelos)

    @classmethod
    def de_csv(cls, ocorrencias_csv: Path, cobertura_csv: Path | None = None) -> "Calendario":
        calendario = cls()
        with open(ocorrencias_csv, encoding="utf-8", newline="") as arquivo:
            for linha, registro in enumerate(csv.DictReader(arquivo), start=2):
                try:
                    inicio = date.fromisoformat(registro["data_inicio"])
                    fim = date.fromisoformat(registro.get("data_fim") or registro["data_inicio"])
                    tipo = TipoOcorrencia(registro["tipo"].strip())
                    calendario.adicionar_periodo(
                        inicio,
                        fim,
                        tipo,
                        registro["tribunal"].strip(),
                        registro.get("descricao") or "",
                        registro.get("fonte") or "",
                        (registro.get("comarca") or "").strip() or None,
                    )
                except (KeyError, ValueError) as erro:
                    raise CalendarioInconsistente(f"{ocorrencias_csv}, linha {linha}: {erro}") from erro
        if cobertura_csv is not None:
            with open(cobertura_csv, encoding="utf-8", newline="") as arquivo:
                for registro in csv.DictReader(arquivo):
                    calendario.marcar_conferido(
                        registro["tribunal"].strip(),
                        (registro.get("comarca") or "").strip() or None,
                        int(registro["ano"]),
                    )
        return calendario
