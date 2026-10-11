"""Caixa de Publicações: da publicação no DJEN ao prazo aprovado e à tarefa (plano, Seção 6.2).

Enquanto a triagem pela IA não estiver ativa, o advogado escolhe o ato na
tabela de prazos legais, ou informa o número de dias, com marca [CONFERIR];
o motor de prazos calcula as datas; a aprovação grava o prazo como
confirmado, cria a tarefa e registra a auditoria. Nenhum prazo é confirmado
sem aprovação, e o cálculo é refeito no servidor no momento da aprovação.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ..prazos import CalculoRecusado, CalendarioInconsistente, Contagem, ResultadoPrazo, calcular_prazo
from ..prazos.banco import carregar_calendario

PENDENTES = ("capturada", "triada")
SITUACOES = ("capturada", "triada", "aprovada", "arquivada")


class OperacaoRecusada(ValueError):
    """Pedido que a Caixa não executa, com o motivo para o advogado."""


@dataclass(frozen=True)
class Simulacao:
    publicacao: dict
    prazo_legal: dict | None
    dias: int
    em_dobro: bool
    tribunal: str
    comarca: str | None
    resultado: ResultadoPrazo
    alertas: tuple[str, ...]
    confiavel: bool
    observacoes: tuple[str, ...] = field(default=())

    def memoria_calculo(self) -> dict:
        legal = self.prazo_legal
        return {
            "tribunal": self.tribunal,
            "comarca": self.comarca,
            "prazo_legal": None if legal is None else {
                "id": legal["id"], "tipo_ato": legal["tipo_ato"], "dias": legal["dias"],
                "dispositivo": legal["dispositivo"], "link_oficial": legal["link_oficial"],
                "observacoes": legal.get("observacoes"),
            },
            "dias": self.dias,
            "dias_definidos_manualmente": legal is None,
            "em_dobro": self.em_dobro,
            "memoria": list(self.resultado.memoria),
            "alertas": list(self.alertas),
            "calendario_conferido": self.confiavel,
            "calculado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }


_CONSULTA_PUBLICACAO = """
SELECT pu.id, pu.npu, pu.data_disponibilizacao, pu.tribunal, pu.tipo_comunicacao, pu.tipo_documento,
       pu.orgao, pu.classe, pu.link, pu.texto, pu.situacao_triagem, pu.djen_id, pu.capturada_em,
       pu.processo_id, pr.tribunal AS processo_tribunal, pr.comarca, pr.grau, pr.sistema,
       pr.segredo_justica, ca.codigo AS caso_codigo, ca.titulo AS caso_titulo,
       cl.codigo AS cliente_codigo, cl.nome AS cliente_nome, cl.provisorio AS cliente_provisorio
FROM sgj.publicacoes pu
LEFT JOIN sgj.processos pr ON pr.id = pu.processo_id
LEFT JOIN sgj.casos ca ON ca.id = pr.caso_id
LEFT JOIN sgj.clientes cl ON cl.id = ca.cliente_id
"""


def _filtros(situacao: str, tribunal: str | None, busca: str | None) -> tuple[str, list]:
    condicoes, parametros = [], []
    if situacao == "pendentes":
        condicoes.append("pu.situacao_triagem = ANY(%s)")
        parametros.append(list(PENDENTES))
    elif situacao in SITUACOES:
        condicoes.append("pu.situacao_triagem = %s")
        parametros.append(situacao)
    if tribunal:
        condicoes.append("coalesce(pu.tribunal, pr.tribunal) = %s")
        parametros.append(tribunal)
    if busca:
        digitos = "".join(c for c in busca if c.isdigit())
        if len(digitos) >= 7:
            condicoes.append("pu.npu LIKE %s")
            parametros.append(f"%{digitos}%")
        else:
            condicoes.append("(cl.nome ILIKE %s OR ca.titulo ILIKE %s)")
            parametros.extend([f"%{busca}%", f"%{busca}%"])
    return (" WHERE " + " AND ".join(condicoes)) if condicoes else "", parametros


def listar_publicacoes(conexao, *, situacao: str = "pendentes", tribunal: str | None = None,
                       busca: str | None = None, limite: int = 50, deslocamento: int = 0) -> tuple[list[dict], int]:
    """Publicações filtradas, mais recentes primeiro, e o total do filtro."""
    onde, parametros = _filtros(situacao, tribunal, busca)
    with conexao.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            "SELECT count(*) AS total FROM sgj.publicacoes pu "
            "LEFT JOIN sgj.processos pr ON pr.id = pu.processo_id "
            "LEFT JOIN sgj.casos ca ON ca.id = pr.caso_id "
            "LEFT JOIN sgj.clientes cl ON cl.id = ca.cliente_id" + onde,
            parametros,
        )
        total = cursor.fetchone()["total"]
        cursor.execute(
            _CONSULTA_PUBLICACAO + onde + " ORDER BY pu.data_disponibilizacao DESC, pu.id DESC LIMIT %s OFFSET %s",
            [*parametros, limite, deslocamento],
        )
        return cursor.fetchall(), total


def resumo(conexao) -> dict:
    """Contagens para o cabeçalho da Caixa."""
    with conexao.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            "SELECT count(*) FILTER (WHERE situacao_triagem = ANY(%s)) AS pendentes, "
            "count(*) FILTER (WHERE situacao_triagem = ANY(%s) AND processo_id IS NULL) AS sem_processo, "
            "count(*) FILTER (WHERE situacao_triagem = ANY(%s) AND data_disponibilizacao >= current_date - 30) AS recentes "
            "FROM sgj.publicacoes",
            (list(PENDENTES), list(PENDENTES), list(PENDENTES)),
        )
        dados = cursor.fetchone()
        cursor.execute(
            "SELECT DISTINCT coalesce(pu.tribunal, pr.tribunal) AS tribunal FROM sgj.publicacoes pu "
            "LEFT JOIN sgj.processos pr ON pr.id = pu.processo_id ORDER BY 1"
        )
        dados["tribunais"] = [linha["tribunal"] for linha in cursor if linha["tribunal"]]
        return dados


def obter_publicacao(conexao, publicacao_id: int, *, bloquear: bool = False) -> dict | None:
    with conexao.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            _CONSULTA_PUBLICACAO + " WHERE pu.id = %s" + (" FOR UPDATE OF pu" if bloquear else ""),
            (publicacao_id,),
        )
        return cursor.fetchone()


def prazo_aprovado(conexao, publicacao_id: int) -> dict | None:
    """Prazo confirmado e tarefa da publicação, se houver."""
    with conexao.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            "SELECT pz.*, t.id AS tarefa_id, t.situacao AS tarefa_situacao, t.titulo AS tarefa_titulo "
            "FROM sgj.prazos pz LEFT JOIN sgj.tarefas t ON t.prazo_id = pz.id "
            "WHERE pz.publicacao_id = %s AND pz.situacao <> 'cancelado' ORDER BY pz.id DESC LIMIT 1",
            (publicacao_id,),
        )
        return cursor.fetchone()


def prazos_legais(conexao) -> list[dict]:
    with conexao.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            "SELECT id, tipo_ato, dias, contagem, dispositivo, link_oficial, termo, observacoes "
            "FROM sgj.prazos_legais ORDER BY tipo_ato"
        )
        return cursor.fetchall()


def usuario_titular(conexao) -> int:
    with conexao.cursor(row_factory=dict_row) as cursor:
        cursor.execute("SELECT id FROM sgj.usuarios WHERE perfil = 'titular' AND ativo ORDER BY id LIMIT 1")
        linha = cursor.fetchone()
    if linha is None:
        raise OperacaoRecusada("Nenhum titular ativo cadastrado.")
    return linha["id"]


ROTULOS_ATOS = {
    "manifestacao_sem_prazo_fixado": "Manifestação sem prazo fixado",
    "recurso_ou_resposta": "Recurso ou resposta a recurso",
    "embargos_de_declaracao": "Embargos de declaração",
    "agravo_decisao_unipessoal_tribunal": "Agravo contra decisão unipessoal em tribunal",
    "manifestacao_fato_impeditivo": "Réplica: fato impeditivo, modificativo ou extintivo",
    "manifestacao_preliminares": "Réplica: preliminares do art. 337",
    "impugnacao_cumprimento_sentenca": "Impugnação ao cumprimento de sentença",
    "pagamento_cumprimento_sentenca": "Pagamento no cumprimento de sentença",
    "contestacao": "Contestação",
    "embargos_a_execucao": "Embargos à execução",
}


def rotulo_ato(tipo_ato: str) -> str:
    if tipo_ato in ROTULOS_ATOS:
        return ROTULOS_ATOS[tipo_ato]
    texto = tipo_ato.replace("_", " ")
    return texto[:1].upper() + texto[1:]


def _local_da_contagem(publicacao: dict) -> tuple[str, str | None, list[str], bool]:
    """Tribunal e comarca cujo calendário rege a contagem, com os alertas da escolha."""
    alertas: list[str] = []
    confiavel = True
    tribunal = publicacao["tribunal"]
    if not tribunal:
        tribunal = publicacao["processo_tribunal"]
        if not tribunal:
            raise OperacaoRecusada("Publicação sem tribunal identificado e sem processo cadastrado: cálculo impossível.")
        alertas.append(
            f"Tribunal que publicou não informado (publicação importada do protótipo): usado o tribunal de origem "
            f"do processo ({tribunal}). Conferir antes de aprovar."
        )
        confiavel = False
    comarca = None
    if tribunal == publicacao["processo_tribunal"]:
        if publicacao["grau"] == 1 and publicacao["comarca"]:
            comarca = publicacao["comarca"]
        elif publicacao["grau"] in (None, 1):
            alertas.append(
                "Grau ou comarca do processo não identificados: feriados municipais não foram considerados, "
                "o que antecipa a data (critério conservador). Conferir."
            )
            confiavel = False
    return tribunal, comarca, alertas, confiavel


def simular_prazo(conexao, publicacao_id: int, *, prazo_legal_id: int | None = None, dias: int | None = None,
                  em_dobro: bool = False, publicacao: dict | None = None) -> Simulacao:
    """Calcula o prazo sem gravar nada."""
    publicacao = publicacao or obter_publicacao(conexao, publicacao_id)
    if publicacao is None:
        raise OperacaoRecusada("Publicação não encontrada.")

    legal = None
    observacoes: list[str] = []
    alertas: list[str] = []
    if prazo_legal_id:
        legal = next((p for p in prazos_legais(conexao) if p["id"] == prazo_legal_id), None)
        if legal is None:
            raise OperacaoRecusada("Prazo legal não encontrado na tabela.")
        if legal["termo"] != "publicacao":
            raise OperacaoRecusada(
                f"{rotulo_ato(legal['tipo_ato'])} ({legal['dispositivo']}): o termo inicial não é a publicação no DJEN"
                + (f" ({legal['observacoes']})" if legal.get("observacoes") else "")
                + ". Controle manual do prazo."
            )
        dias_prazo = legal["dias"]
        if legal.get("observacoes"):
            observacoes.append(legal["observacoes"])
            if "[CONFERIR]" in legal["observacoes"]:
                alertas.append(f"{legal['dispositivo']}: {legal['observacoes']}")
    elif dias:
        dias_prazo = dias
        alertas.append(f"[CONFERIR] Prazo de {dias} dias definido manualmente, fora da tabela de prazos legais.")
    else:
        raise OperacaoRecusada("Escolha o ato na tabela de prazos legais ou informe o número de dias.")

    tribunal, comarca, alertas_local, confiavel = _local_da_contagem(publicacao)
    calendario = carregar_calendario(conexao, [tribunal])
    try:
        resultado = calcular_prazo(
            calendario,
            disponibilizacao=publicacao["data_disponibilizacao"],
            dias=dias_prazo,
            tribunal=tribunal,
            comarca=comarca,
            contagem=Contagem(legal["contagem"]) if legal else Contagem.UTEIS,
            multiplicador=2 if em_dobro else 1,
        )
    except (CalculoRecusado, CalendarioInconsistente) as erro:
        raise OperacaoRecusada(str(erro)) from erro

    todos = (*resultado.alertas, *alertas_local, *alertas)
    return Simulacao(
        publicacao=publicacao,
        prazo_legal=legal,
        dias=dias_prazo,
        em_dobro=em_dobro,
        tribunal=tribunal,
        comarca=comarca,
        resultado=resultado,
        alertas=tuple(todos),
        confiavel=resultado.calendario_conferido and confiavel,
        observacoes=tuple(observacoes),
    )


def _auditar(cursor, usuario_id: int, acao: str, entidade: str, entidade_id: int, antes=None, depois=None) -> None:
    cursor.execute(
        "INSERT INTO sgj.auditoria (usuario_id, acao, entidade, entidade_id, antes, depois) VALUES (%s, %s, %s, %s, %s, %s)",
        (usuario_id, acao, entidade, entidade_id,
         None if antes is None else Jsonb(antes), None if depois is None else Jsonb(depois)),
    )


def aprovar_prazo(conexao, publicacao_id: int, usuario_id: int, *, prazo_legal_id: int | None = None,
                  dias: int | None = None, em_dobro: bool = False, providencia: str | None = None) -> dict:
    """Confirma o prazo calculado agora, cria a tarefa e registra a auditoria, numa só transação."""
    with conexao.transaction():
        publicacao = obter_publicacao(conexao, publicacao_id, bloquear=True)
        if publicacao is None:
            raise OperacaoRecusada("Publicação não encontrada.")
        if publicacao["situacao_triagem"] not in PENDENTES:
            raise OperacaoRecusada(f"Publicação já tratada (situação: {publicacao['situacao_triagem']}).")
        if publicacao["processo_id"] is None:
            raise OperacaoRecusada("Processo não cadastrado: cadastre o processo antes de aprovar o prazo.")
        simulacao = simular_prazo(conexao, publicacao_id, prazo_legal_id=prazo_legal_id, dias=dias,
                                  em_dobro=em_dobro, publicacao=publicacao)
        r = simulacao.resultado
        agora = datetime.now(timezone.utc)
        with conexao.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                "INSERT INTO sgj.prazos (processo_id, publicacao_id, prazo_legal_id, dias, multiplicador, data_publicacao, "
                "data_inicio, data_fatal, data_fatal_com_prorrogacao, data_interna, calendario_conferido, memoria_calculo, "
                "situacao, aprovado_por, aprovado_em) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'confirmado', %s, %s) "
                "RETURNING id",
                (publicacao["processo_id"], publicacao_id, prazo_legal_id or None, simulacao.dias, r.multiplicador,
                 r.publicacao, r.inicio, r.vencimento_sem_prorrogacao, r.vencimento, r.prazo_interno,
                 simulacao.confiavel, Jsonb(simulacao.memoria_calculo()), usuario_id, agora),
            )
            prazo_id = cursor.fetchone()["id"]
            ato = rotulo_ato(simulacao.prazo_legal["tipo_ato"]) if simulacao.prazo_legal else f"Prazo de {simulacao.dias} dias"
            titulo = (providencia or "").strip() or f"{ato} ({simulacao.tribunal})"
            checklist = [{"item": "Conferir o teor integral da publicação no DJEN", "concluido": False}]
            if not simulacao.confiavel:
                checklist.append({"item": "Conferir a contagem do prazo: calendário ou local da contagem não conferido",
                                  "concluido": False})
            cursor.execute(
                "INSERT INTO sgj.tarefas (processo_id, prazo_id, origem, tipo, titulo, responsavel, revisor, checklist, "
                "vencimento_interno) VALUES (%s, %s, 'publicacao', 'prazo_processual', %s, %s, %s, %s, %s) RETURNING id",
                (publicacao["processo_id"], prazo_id, titulo, usuario_id, usuario_id, Jsonb(checklist), r.prazo_interno),
            )
            tarefa_id = cursor.fetchone()["id"]
            cursor.execute("UPDATE sgj.publicacoes SET situacao_triagem = 'aprovada' WHERE id = %s", (publicacao_id,))
            _auditar(cursor, usuario_id, "aprovar_prazo", "prazos", prazo_id, depois={
                "publicacao_id": publicacao_id, "data_fatal": r.vencimento_sem_prorrogacao.isoformat(),
                "data_interna": r.prazo_interno.isoformat(), "calendario_conferido": simulacao.confiavel,
            })
            _auditar(cursor, usuario_id, "criar_tarefa", "tarefas", tarefa_id, depois={"prazo_id": prazo_id, "titulo": titulo})
            _auditar(cursor, usuario_id, "alterar_situacao", "publicacoes", publicacao_id,
                     antes={"situacao_triagem": publicacao["situacao_triagem"]}, depois={"situacao_triagem": "aprovada"})
    return {"prazo_id": prazo_id, "tarefa_id": tarefa_id, "simulacao": simulacao}


def arquivar_publicacao(conexao, publicacao_id: int, usuario_id: int, motivo: str | None = None) -> None:
    """Sem providência: arquiva a publicação, com o motivo na auditoria."""
    with conexao.transaction():
        publicacao = obter_publicacao(conexao, publicacao_id, bloquear=True)
        if publicacao is None:
            raise OperacaoRecusada("Publicação não encontrada.")
        if publicacao["situacao_triagem"] not in PENDENTES:
            raise OperacaoRecusada(f"Publicação já tratada (situação: {publicacao['situacao_triagem']}).")
        with conexao.cursor() as cursor:
            cursor.execute("UPDATE sgj.publicacoes SET situacao_triagem = 'arquivada' WHERE id = %s", (publicacao_id,))
            _auditar(cursor, usuario_id, "arquivar_publicacao", "publicacoes", publicacao_id,
                     antes={"situacao_triagem": publicacao["situacao_triagem"]},
                     depois={"situacao_triagem": "arquivada", "motivo": (motivo or "").strip() or None})
