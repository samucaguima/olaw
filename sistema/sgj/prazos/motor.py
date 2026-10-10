"""Motor de prazos processuais contados da publicação no DJEN.

Regras aplicadas (plano, Seções 5.2 e 7.1). Fundamentos conferidos em
10/10/2026 no texto integral das páginas oficiais (ver FONTES abaixo e
docs/fase0/apis-verificadas.md, Seção 3):

1. Prazo contado da publicação no DJEN quando a lei não exigir intimação
   pessoal (Res. CNJ 455/2022, art. 11, § 3º, na redação da Res. 569/2024).
2. Publicação: primeiro dia útil seguinte à disponibilização.
3. Começo: o dia da publicação, excluído da contagem; a contagem se inicia
   no primeiro dia útil seguinte.
4. Contagem em dias úteis; feriados e suspensões não contam.
5. Indisponibilidade do sistema ou expediente alterado no dia do começo ou
   do vencimento prorroga esse dia para o primeiro dia útil seguinte.

O motor devolve duas datas de vencimento. `vencimento_sem_prorrogacao`
ignora as prorrogações da regra 5 e é a data de controle recomendada; a
data com prorrogação é informativa e vem acompanhada de alerta.

Quando o prazo atravessa feriado que não é nacional, o motor alerta para a
comprovação do feriado local no ato de interposição de recurso (CPC, art.
1.003, § 6º).

A contagem em dias corridos não está implementada: a regra (termo inicial
e efeito das suspensões) depende de definição do titular, e o motor recusa
o cálculo em vez de presumir.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum

from .calendario import NACIONAL, Calendario, CalendarioInconsistente, Ocorrencia, TipoOcorrencia, formatar

# Conferidos em 10/10/2026 no texto integral das páginas oficiais abaixo.
FONTES = {
    "cpc": "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/l13105.htm",
    "lei_11419": "https://www.planalto.gov.br/ccivil_03/_ato2004-2006/2006/lei/l11419.htm",
    "res_cnj_569": "https://atos.cnj.jus.br/atos/detalhar/5691",
}
FUNDAMENTO_TERMO = "Res. CNJ 455/2022, art. 11, § 3º, na redação da Res. CNJ 569/2024"
FUNDAMENTO_PUBLICACAO = "Lei 11.419/2006, art. 4º, § 3º; CPC, art. 224, § 2º"
FUNDAMENTO_INICIO = "Lei 11.419/2006, art. 4º, § 4º; CPC, art. 224, caput e § 3º"
FUNDAMENTO_DIAS_UTEIS = "CPC, art. 219"
FUNDAMENTO_PRORROGACAO = "CPC, art. 224, § 1º"
FUNDAMENTO_FERIADO_LOCAL = "CPC, art. 1.003, § 6º"


class Contagem(str, Enum):
    UTEIS = "uteis"
    CORRIDOS = "corridos"


class CalculoRecusado(ValueError):
    """Parâmetros que o motor não aceita calcular sem regra definida pelo titular."""


@dataclass(frozen=True)
class ResultadoPrazo:
    tribunal: str
    comarca: str | None
    disponibilizacao: date
    publicacao: date
    inicio: date
    vencimento_sem_prorrogacao: date
    vencimento: date
    prazo_interno: date
    dias: int
    multiplicador: int
    calendario_conferido: bool
    memoria: tuple[str, ...]
    alertas: tuple[str, ...]

    @property
    def data_controle(self) -> date:
        """Data a usar no controle de prazos: a mais conservadora."""
        return self.vencimento_sem_prorrogacao


def calcular_prazo(
    calendario: Calendario,
    *,
    disponibilizacao: date,
    dias: int,
    tribunal: str,
    comarca: str | None = None,
    contagem: Contagem = Contagem.UTEIS,
    multiplicador: int = 1,
    margem_interna: int = 2,
) -> ResultadoPrazo:
    if contagem is not Contagem.UTEIS:
        raise CalculoRecusado(
            "Contagem em dias corridos sem regra definida pelo titular; "
            "o prazo deve ser controlado manualmente."
        )
    if dias < 1:
        raise CalculoRecusado("O prazo deve ter ao menos 1 dia.")
    if multiplicador not in (1, 2):
        raise CalculoRecusado("Multiplicador aceito: 1 (simples) ou 2 (em dobro).")
    if margem_interna < 0:
        raise CalculoRecusado("A margem do prazo interno não pode ser negativa.")

    def tem_expediente(d: date) -> bool:
        return calendario.tem_expediente(d, tribunal, comarca)

    def conta_prazo(d: date) -> bool:
        return calendario.conta_prazo(d, tribunal, comarca)

    total = dias * multiplicador
    memoria: list[str] = []
    alertas: list[str] = []

    memoria.append(f"Termo: publicação no DJEN ({FUNDAMENTO_TERMO}).")
    memoria.append(f"Disponibilização no DJEN: {formatar(disponibilizacao)}.")
    publicacao = calendario.proximo(disponibilizacao, tem_expediente)
    memoria.append(
        f"Publicação: {formatar(publicacao)}, primeiro dia útil seguinte à disponibilização "
        f"({FUNDAMENTO_PUBLICACAO})."
    )

    # Caminho de controle: sem prorrogações por indisponibilidade ou expediente alterado.
    inicio_base = calendario.proximo(publicacao, conta_prazo)
    vencimento_base = _contar_uteis(calendario, inicio_base, total, conta_prazo)

    # Caminho com prorrogações do começo e do vencimento.
    comeco = publicacao
    while calendario.prorrogacoes(comeco, tribunal, comarca):
        motivos = _descrever(calendario.prorrogacoes(comeco, tribunal, comarca))
        novo = calendario.proximo(comeco, tem_expediente)
        alertas.append(
            f"Dia do começo ({formatar(comeco)}) com {motivos}: prorrogação para {formatar(novo)} "
            f"({FUNDAMENTO_PRORROGACAO}). Informativo; controle pela data sem prorrogação."
        )
        comeco = novo
    inicio = calendario.proximo(comeco, conta_prazo)
    vencimento = _contar_uteis(calendario, inicio, total, conta_prazo)
    while calendario.prorrogacoes(vencimento, tribunal, comarca):
        motivos = _descrever(calendario.prorrogacoes(vencimento, tribunal, comarca))
        novo = calendario.proximo(vencimento, conta_prazo)
        alertas.append(
            f"Vencimento ({formatar(vencimento)}) com {motivos}: prorrogação para {formatar(novo)} "
            f"({FUNDAMENTO_PRORROGACAO}). Informativo; controle pela data sem prorrogação."
        )
        vencimento = novo

    memoria.append(
        f"Início da contagem: {formatar(inicio_base)}, primeiro dia útil seguinte à publicação "
        f"({FUNDAMENTO_INICIO})."
    )
    descricao_prazo = f"{dias} dias úteis" + (" em dobro, total de " + str(total) if multiplicador == 2 else "")
    memoria.append(f"Prazo: {descricao_prazo} ({FUNDAMENTO_DIAS_UTEIS}).")
    if multiplicador == 2:
        alertas.append(
            "Prazo em dobro: confirmar a hipótese legal (ex.: CPC, arts. 183 e 186). Litisconsortes com "
            "procuradores distintos não têm prazo em dobro em autos eletrônicos (CPC, art. 229, § 2º)."
        )
    memoria.extend(_dias_excluidos(calendario, inicio_base, vencimento_base, tribunal, comarca))
    memoria.append(f"Vencimento (data de controle): {formatar(vencimento_base)}.")

    locais = _ocorrencias_locais(calendario, disponibilizacao, max(vencimento, vencimento_base), tribunal, comarca)
    if locais:
        alertas.append(
            "Prazo afetado por feriado ou suspensão não nacional ("
            + "; ".join(f"{formatar(o.data)}: {o.descricao}, fonte {o.fonte}" for o in locais)
            + f"). Em recurso, comprovar a ocorrência no ato de interposição ({FUNDAMENTO_FERIADO_LOCAL})."
        )

    prazo_interno = vencimento_base
    for _ in range(margem_interna):
        anterior = calendario.anterior(prazo_interno, conta_prazo)
        if anterior < inicio_base:
            alertas.append(
                f"Margem interna de {margem_interna} dias úteis maior que o prazo; "
                f"prazo interno fixado no início da contagem ({formatar(inicio_base)})."
            )
            prazo_interno = inicio_base
            break
        prazo_interno = anterior
    memoria.append(f"Prazo interno ({margem_interna} dias úteis antes): {formatar(prazo_interno)}.")

    anos = range(disponibilizacao.year, max(vencimento, vencimento_base).year + 1)
    pendentes = [a for a in anos if not calendario.conferido(tribunal, comarca, a)]
    if pendentes:
        local = tribunal + (f"/{comarca}" if comarca else "")
        alertas.insert(
            0,
            f"CALENDÁRIO NÃO CONFERIDO para {local} em {', '.join(map(str, pendentes))}: "
            "feriados e suspensões podem estar ausentes; cálculo não confiável.",
        )

    return ResultadoPrazo(
        tribunal=tribunal,
        comarca=comarca,
        disponibilizacao=disponibilizacao,
        publicacao=publicacao,
        inicio=inicio_base,
        vencimento_sem_prorrogacao=vencimento_base,
        vencimento=vencimento,
        prazo_interno=prazo_interno,
        dias=dias,
        multiplicador=multiplicador,
        calendario_conferido=not pendentes,
        memoria=tuple(memoria),
        alertas=tuple(alertas),
    )


def _contar_uteis(calendario: Calendario, inicio: date, total: int, conta_prazo) -> date:
    if not conta_prazo(inicio):
        raise CalendarioInconsistente(f"Início da contagem em dia que não conta: {formatar(inicio)}.")
    d = inicio
    for _ in range(total - 1):
        d = calendario.proximo(d, conta_prazo)
    return d


def _dias_excluidos(
    calendario: Calendario, inicio: date, fim: date, tribunal: str, comarca: str | None
) -> list[str]:
    linhas: list[str] = []
    fins_de_semana = 0
    d = inicio
    while d < fim:
        d = date.fromordinal(d.toordinal() + 1)
        motivo = calendario.motivo_sem_contagem(d, tribunal, comarca)
        if motivo is None:
            continue
        if d.weekday() >= 5:
            fins_de_semana += 1
        else:
            linhas.append(f"Não conta: {formatar(d)} ({motivo}).")
    if fins_de_semana:
        linhas.insert(0, f"Não contam: {fins_de_semana} dias de fim de semana no período.")
    return linhas


def _ocorrencias_locais(
    calendario: Calendario, inicio: date, fim: date, tribunal: str, comarca: str | None
) -> list[Ocorrencia]:
    """Feriados e suspensões não nacionais que, sozinhos, excluem dia de semana entre `inicio` e `fim`.

    Dia já excluído por ocorrência nacional (feriado em lei federal, suspensão do art. 220 do CPC)
    não depende de prova de feriado local e não é apontado.
    """
    impeditivos = (TipoOcorrencia.FERIADO, TipoOcorrencia.SUSPENSAO)
    locais: list[Ocorrencia] = []
    d = inicio
    while d < fim:
        d = date.fromordinal(d.toordinal() + 1)
        if d.weekday() >= 5:
            continue
        do_dia = [o for o in calendario.ocorrencias(d, tribunal, comarca) if o.tipo in impeditivos]
        if any(o.tribunal == NACIONAL for o in do_dia):
            continue
        locais.extend(do_dia)
    return locais


def _descrever(ocorrencias) -> str:
    return "; ".join(f"{o.tipo.value} ({o.descricao}; fonte: {o.fonte})" for o in ocorrencias)
