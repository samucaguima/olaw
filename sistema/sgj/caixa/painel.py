"""Painel do advogado ("Meu dia", plano, Seção 14.1) e saúde das coletas.

Somente leitura. Datas e horários no fuso de São Paulo. A ausência de resposta
de uma coleta é tratada como falha de coleta, nunca como ausência de
publicações (plano, Seção 3). Objetos ainda não instalados no banco (por
exemplo, a coleta por processo antes da migração 0005) aparecem como tais, sem
erro.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row

from . import servico

FUSO = ZoneInfo("America/Sao_Paulo")
JANELA = timedelta(hours=26)
SEMAFORO = (
    ("vencido", "Vencidos"),
    ("hoje", "Vencem hoje"),
    ("dois_dias", "Até 2 dias"),
    ("semana", "Até 7 dias"),
    ("depois", "Depois"),
)
ROTULOS_SITUACAO_TAREFA = {
    "a_fazer": "A fazer", "em_elaboracao": "Em elaboração", "conferencia_1": "Conferência 1",
    "pronta_protocolo": "Pronta para protocolo", "conferencia_2": "Conferência 2", "protocolada": "Protocolada",
}


def agora_utc() -> datetime:
    return datetime.now(timezone.utc)


def hoje_sp(agora: datetime | None = None) -> date:
    return (agora or agora_utc()).astimezone(FUSO).date()


def semaforo(data_fatal: date, hoje: date) -> str:
    if data_fatal < hoje:
        return "vencido"
    if data_fatal == hoje:
        return "hoje"
    if data_fatal <= hoje + timedelta(days=2):
        return "dois_dias"
    if data_fatal <= hoje + timedelta(days=7):
        return "semana"
    return "depois"


def _existe(cursor, objeto: str) -> bool:
    cursor.execute("SELECT to_regclass(%s) IS NOT NULL AS existe", (objeto,))
    return cursor.fetchone()["existe"]


# Meu dia

def _prazos(cursor, hoje: date) -> list[dict]:
    cursor.execute(
        "SELECT pz.id, pz.data_fatal, pz.data_fatal_com_prorrogacao, pz.data_interna, pz.calendario_conferido, "
        "pz.publicacao_id, pr.npu, coalesce(pu.tribunal, pr.tribunal) AS tribunal, pr.segredo_justica, "
        "cl.codigo AS cliente_codigo, cl.nome AS cliente_nome, cl.provisorio AS cliente_provisorio, "
        "t.id AS tarefa_id, t.titulo, t.situacao AS tarefa_situacao "
        "FROM sgj.prazos pz "
        "JOIN sgj.processos pr ON pr.id = pz.processo_id "
        "JOIN sgj.casos ca ON ca.id = pr.caso_id "
        "JOIN sgj.clientes cl ON cl.id = ca.cliente_id "
        "JOIN sgj.publicacoes pu ON pu.id = pz.publicacao_id "
        "LEFT JOIN sgj.tarefas t ON t.prazo_id = pz.id "
        "WHERE pz.situacao = 'confirmado' "
        "ORDER BY pz.data_fatal, pz.data_interna, pz.id"
    )
    prazos = cursor.fetchall()
    for p in prazos:
        p["semaforo"] = semaforo(p["data_fatal"], hoje)
        p["interno_vencido"] = p["data_interna"] < hoje <= p["data_fatal"]
        p["situacao_tarefa"] = ROTULOS_SITUACAO_TAREFA.get(p["tarefa_situacao"], p["tarefa_situacao"])
    return prazos


def _tarefas(cursor) -> dict:
    cursor.execute(
        "SELECT situacao, count(*) AS n FROM sgj.tarefas "
        "WHERE tipo = 'prazo_processual' AND situacao NOT IN ('concluida', 'cancelada') GROUP BY situacao"
    )
    por_situacao = {linha["situacao"]: linha["n"] for linha in cursor}
    colunas = [(rotulo, por_situacao.get(chave, 0)) for chave, rotulo in ROTULOS_SITUACAO_TAREFA.items()]
    cursor.execute(
        "SELECT count(*) AS total, count(*) FILTER (WHERE situacao IN ('concluida', 'cancelada')) AS concluidas "
        "FROM sgj.tarefas WHERE origem = 'importacao'"
    )
    conferencia = cursor.fetchone()
    # Itens pendentes das tarefas de conferência, agrupados pelo enunciado (sem o complemento entre parênteses).
    cursor.execute(
        "SELECT regexp_replace(e->>'item', '\\s*\\(.*$', '') AS item, count(*) AS n "
        "FROM sgj.tarefas t, jsonb_array_elements(t.checklist) e "
        "WHERE t.origem = 'importacao' AND t.situacao NOT IN ('concluida', 'cancelada') "
        "AND NOT coalesce((e->>'concluido')::boolean, false) "
        "GROUP BY 1 ORDER BY 2 DESC, 1"
    )
    conferencia["pendencias"] = cursor.fetchall()
    cursor.execute(
        "SELECT count(*) AS n FROM sgj.tarefas WHERE tipo = 'interna' AND origem <> 'importacao' "
        "AND situacao NOT IN ('concluida', 'cancelada')"
    )
    return {"colunas": colunas, "abertas": sum(n for _, n in colunas), "conferencia": conferencia,
            "internas": cursor.fetchone()["n"]}


def _fora_da_carteira(cursor) -> list[dict]:
    cursor.execute(
        "SELECT pu.npu, count(*) AS publicacoes, max(pu.data_disponibilizacao) AS ultima, "
        "(array_agg(coalesce(pu.tipo_documento, pu.tipo_comunicacao) "
        "  ORDER BY pu.data_disponibilizacao DESC, pu.id DESC))[1] AS ultimo_tipo, "
        "(array_agg(pu.id ORDER BY pu.data_disponibilizacao DESC, pu.id DESC))[1] AS ultima_publicacao_id, "
        "string_agg(DISTINCT coalesce(pu.tribunal, sgj.tribunal_da_npu(pu.npu), 'não informado'), ', ') AS tribunais, "
        "count(*) FILTER (WHERE pu.situacao_triagem = ANY(%s)) AS a_triar "
        "FROM sgj.publicacoes pu WHERE pu.processo_id IS NULL "
        "GROUP BY pu.npu ORDER BY max(pu.data_disponibilizacao) DESC, pu.npu",
        (list(servico.PENDENTES),),
    )
    return cursor.fetchall()


def _carteira(cursor, hoje: date) -> dict:
    cursor.execute(
        "SELECT pr.tribunal, count(*) AS processos, "
        "count(*) FILTER (WHERE pr.sistema IS NULL) AS sistema_a_confirmar, "
        "count(*) FILTER (WHERE cl.provisorio) AS cliente_a_identificar, "
        "count(*) FILTER (WHERE pr.grau IS NULL OR (pr.grau = 1 AND pr.comarca IS NULL)) AS local_a_conferir, "
        "count(*) FILTER (WHERE pr.segredo_justica) AS segredo, "
        "EXISTS (SELECT 1 FROM sgj.calendario_cobertura cc WHERE cc.tribunal = pr.tribunal AND cc.ano = %s) "
        "  AS calendario_conferido "
        "FROM sgj.processos pr JOIN sgj.casos ca ON ca.id = pr.caso_id JOIN sgj.clientes cl ON cl.id = ca.cliente_id "
        "WHERE ca.situacao <> 'encerrado' "
        "GROUP BY pr.tribunal ORDER BY count(*) DESC, pr.tribunal",
        (hoje.year,),
    )
    tribunais = cursor.fetchall()
    totais = {chave: sum(t[chave] for t in tribunais)
              for chave in ("processos", "sistema_a_confirmar", "cliente_a_identificar", "local_a_conferir", "segredo")}
    totais["sem_calendario"] = sum(t["processos"] for t in tribunais if not t["calendario_conferido"])
    return {"tribunais": tribunais, "totais": totais, "ano": hoje.year}


def meu_dia(conexao, agora: datetime | None = None) -> dict:
    """Tudo o que a tela inicial mostra, numa consulta por bloco."""
    agora = agora or agora_utc()
    hoje = hoje_sp(agora)
    with conexao.cursor(row_factory=dict_row) as cursor:
        prazos = _prazos(cursor, hoje)
        dados = {
            "hoje": hoje,
            "prazos": prazos,
            "contagem_prazos": {chave: sum(1 for p in prazos if p["semaforo"] == chave) for chave, _ in SEMAFORO},
            "tarefas": _tarefas(cursor),
            "fora_da_carteira": _fora_da_carteira(cursor),
            "carteira": _carteira(cursor, hoje),
        }
    dados["publicacoes"] = servico.resumo(conexao)
    dados["coletas"] = saude_coletas(conexao, agora)
    return dados


# Saúde das coletas

@dataclass
class Fonte:
    chave: str
    nome: str
    situacao: str  # ok, atencao, falha, aguardando, inativa
    resumo: str
    ultima: datetime | None = None
    detalhes: list[str] = field(default_factory=list)


def _hora(valor: datetime | None) -> str:
    return valor.astimezone(FUSO).strftime("%d/%m às %Hh%M") if valor else "nunca"


def _djen_oab(cursor, agora: datetime) -> Fonte:
    nome = "Captura do DJEN por OAB"
    if not _existe(cursor, "djen.requisicao"):
        return Fonte("djen_oab", nome, "inativa", "Captura não encontrada no banco.")
    cursor.execute(
        "WITH ultima AS (SELECT max(disparada_em) AS em FROM djen.requisicao) "
        "SELECT (SELECT em FROM ultima) AS ultimo_disparo, "
        "(SELECT max(disparada_em) FROM djen.requisicao WHERE status_http = 200) AS ultimo_sucesso, "
        "count(*) AS paginas, count(*) FILTER (WHERE status_http = 200) AS ok, "
        "count(*) FILTER (WHERE processada_em IS NULL) AS pendentes, "
        "(array_agg(coalesce(erro, 'HTTP ' || status_http) ORDER BY disparada_em) "
        "  FILTER (WHERE processada_em IS NOT NULL AND status_http IS DISTINCT FROM 200))[1] AS erro "
        "FROM djen.requisicao WHERE disparada_em >= (SELECT em FROM ultima) - interval '10 minutes'"
    )
    r = cursor.fetchone()
    if r["ultimo_disparo"] is None:
        return Fonte("djen_oab", nome, "aguardando", "Nenhuma consulta registrada.")
    detalhes = []
    if _existe(cursor, "djen.comunicacao"):
        cursor.execute("SELECT count(*) AS n FROM djen.comunicacao WHERE capturada_em > now() - interval '7 days'")
        detalhes.append(f"{cursor.fetchone()['n']} comunicações capturadas nos últimos 7 dias.")
    rodada = f"Última consulta em {_hora(r['ultimo_disparo'])}: {r['ok']} de {r['paginas']} páginas com resposta válida."
    if r["ultimo_sucesso"] is None or agora - r["ultimo_sucesso"] > JANELA:
        return Fonte("djen_oab", nome, "falha",
                     f"Sem resposta válida da API desde {_hora(r['ultimo_sucesso'])}. Consultar o DJEN manualmente.",
                     r["ultimo_sucesso"], [rodada] + detalhes)
    falhas = r["paginas"] - r["ok"] - r["pendentes"]
    atrasadas = r["pendentes"] if agora - r["ultimo_disparo"] > timedelta(minutes=30) else 0
    if falhas or atrasadas:
        motivo = f" ({r['erro']})" if r["erro"] else ""
        return Fonte("djen_oab", nome, "atencao",
                     f"Última rodada incompleta: {falhas + atrasadas} de {r['paginas']} páginas sem resposta válida{motivo}. "
                     "A rodada seguinte repete a consulta.",
                     r["ultimo_sucesso"], [rodada] + detalhes)
    return Fonte("djen_oab", nome, "ok", rodada, r["ultimo_sucesso"], detalhes)


def _ultima_coleta(cursor, fonte: str) -> tuple[dict | None, datetime | None]:
    cursor.execute(
        "SELECT inicio, fim, situacao, itens, erro FROM sgj.coletas WHERE fonte = %s ORDER BY id DESC LIMIT 1", (fonte,)
    )
    ultima = cursor.fetchone()
    cursor.execute(
        "SELECT max(inicio) AS em FROM sgj.coletas WHERE fonte = %s AND situacao = 'concluida'", (fonte,)
    )
    return ultima, cursor.fetchone()["em"]


def _sincronizacao(cursor, agora: datetime) -> Fonte:
    nome = "Sincronização com o sistema"
    ultima, sucesso = _ultima_coleta(cursor, "djen")
    if ultima is None:
        return Fonte("sincronizacao", nome, "aguardando", "Nenhuma sincronização registrada.")
    if ultima["situacao"] == "falhou":
        return Fonte("sincronizacao", nome, "falha", f"A última sincronização falhou: {ultima['erro']}", sucesso)
    if sucesso is None or agora - sucesso > JANELA:
        return Fonte("sincronizacao", nome, "falha", f"Sem sincronização concluída desde {_hora(sucesso)}.", sucesso)
    return Fonte("sincronizacao", nome, "ok",
                 f"Última em {_hora(sucesso)}: {ultima['itens']} comunicações novas ou completadas.", sucesso)


def _datajud(cursor, agora: datetime) -> Fonte:
    nome = "Movimentações do DataJud"
    if not _existe(cursor, "sgj.datajud_requisicao"):
        return Fonte("datajud", nome, "inativa", "Coleta não instalada.")
    cursor.execute(
        "SELECT count(*) AS total, max(disparada_em) AS ultima, "
        "count(*) FILTER (WHERE status_http = 200 AND registros > 0) AS com_registros, "
        "count(*) FILTER (WHERE status_http = 200 AND registros = 0) AS sem_registros, "
        "count(*) FILTER (WHERE processada_em IS NOT NULL AND status_http IS DISTINCT FROM 200) AS falhas, "
        "count(*) FILTER (WHERE processada_em IS NULL) AS pendentes, "
        "coalesce(sum(movimentos_novos), 0) AS movimentos "
        "FROM sgj.datajud_requisicao WHERE disparada_em > now() - interval '26 hours'"
    )
    r = cursor.fetchone()
    cursor.execute(
        "SELECT count(*) FILTER (WHERE ultima_sincronizacao IS NOT NULL) AS sincronizados, count(*) AS total "
        "FROM sgj.processos"
    )
    carteira = cursor.fetchone()
    detalhes = [f"{carteira['sincronizados']} de {carteira['total']} processos já sincronizados ao menos uma vez."]
    cursor.execute(
        "SELECT alias, left(erro, 120) AS erro, count(*) AS n FROM sgj.datajud_requisicao "
        "WHERE disparada_em > now() - interval '26 hours' AND erro IS NOT NULL "
        "GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 5"
    )
    detalhes += [f"{e['alias']}: {e['erro']} ({e['n']})" for e in cursor.fetchall()]
    ultima, sucesso = _ultima_coleta(cursor, "datajud")
    if r["total"] == 0:
        cursor.execute("SELECT count(*) AS n FROM sgj.datajud_requisicao")
        if cursor.fetchone()["n"] == 0:
            return Fonte("datajud", nome, "aguardando", "Aguardando a primeira rodada (diária, às 07h20).",
                         None, detalhes)
        return Fonte("datajud", nome, "falha", "Nenhuma consulta nas últimas 26 horas.", sucesso, detalhes)
    if ultima and ultima["situacao"] == "falhou":
        return Fonte("datajud", nome, "falha", f"A última coleta falhou: {ultima['erro']}", sucesso, detalhes)
    texto = (f"Rodada de {_hora(r['ultima'])}: {r['total']} consultas, {r['com_registros']} com registros, "
             f"{r['movimentos']} movimentos novos")
    if r["falhas"] or r["sem_registros"]:
        return Fonte("datajud", nome, "atencao",
                     texto + f"; {r['falhas']} com falha e {r['sem_registros']} sem registros utilizáveis.",
                     sucesso, detalhes)
    if r["pendentes"]:
        texto += f"; {r['pendentes']} aguardando resposta"
    return Fonte("datajud", nome, "ok", texto + ".", sucesso, detalhes)


def _djen_processo(cursor, agora: datetime) -> Fonte:
    nome = "Consulta ao DJEN por processo"
    if not _existe(cursor, "sgj.djen_requisicao"):
        return Fonte("djen_processo", nome, "inativa", "Ainda não instalada (migração 0005).")
    cursor.execute(
        "SELECT max(processada_em) AS em, "
        "(array_agg(coalesce(erro, 'HTTP ' || status_http) ORDER BY processada_em DESC))[1] AS motivo "
        "FROM sgj.djen_requisicao WHERE processada_em > now() - interval '24 hours' "
        "AND (resultado = 'parametro_ignorado' OR status_http IN (403, 429))"
    )
    suspensao = cursor.fetchone()
    cursor.execute(
        "SELECT resultado FROM sgj.djen_requisicao "
        "WHERE (conferidas > 0 AND resultado IN ('valida', 'divergente')) OR resultado = 'parametro_ignorado' "
        "ORDER BY processada_em DESC, request_id DESC LIMIT 1"
    )
    estado = cursor.fetchone()
    cursor.execute(
        "SELECT count(*) AS total, max(disparada_em) AS ultima, "
        "count(*) FILTER (WHERE resultado = 'valida') AS validas, "
        "count(*) FILTER (WHERE resultado = 'divergente') AS divergentes, "
        "count(*) FILTER (WHERE resultado IN ('falha', 'sem_resposta')) AS falhas, "
        "coalesce(sum(novas), 0) AS novas "
        "FROM sgj.djen_requisicao WHERE disparada_em > now() - interval '26 hours' AND NOT sondagem"
    )
    r = cursor.fetchone()
    detalhes = []
    if _existe(cursor, "djen.comunicacao"):
        cursor.execute(
            "SELECT count(*) AS n FROM sgj.djen_comunicacao s "
            "WHERE NOT EXISTS (SELECT 1 FROM djen.comunicacao c WHERE c.id = s.id)"
        )
        detalhes.append(f"{cursor.fetchone()['n']} comunicações encontradas só pela consulta por processo, "
                        "sem a OAB do titular na intimação.")
    if suspensao["em"] is not None:
        return Fonte("djen_processo", nome, "falha",
                     f"Suspensa até {_hora(suspensao['em'] + timedelta(hours=24))}: {suspensao['motivo']}",
                     suspensao["em"], detalhes)
    if estado is None or estado["resultado"] != "valida":
        cursor.execute("SELECT count(*) AS n FROM sgj.djen_requisicao")
        if cursor.fetchone()["n"] == 0:
            return Fonte("djen_processo", nome, "aguardando",
                         "Aguardando a primeira rodada (diária, das 08h às 09h55), que começa em sondagem.",
                         None, detalhes)
        return Fonte("djen_processo", nome, "atencao",
                     "Em sondagem: um processo por rodada até a consulta trazer, sem divergência, uma comunicação "
                     "já capturada por OAB. A captura por OAB segue normalmente.", None, detalhes)
    texto = (f"Rodada de {_hora(r['ultima'])}: {r['total']} processos consultados, {r['novas']} comunicações "
             "que a captura por OAB não tinha")
    if r["total"] == 0:
        return Fonte("djen_processo", nome, "falha", "Nenhuma consulta nas últimas 26 horas.", None, detalhes)
    if r["divergentes"] or r["falhas"]:
        return Fonte("djen_processo", nome, "atencao",
                     texto + f"; {r['falhas']} com falha e {r['divergentes']} divergentes.", r["ultima"], detalhes)
    return Fonte("djen_processo", nome, "ok", texto + ".", r["ultima"], detalhes)


def saude_coletas(conexao, agora: datetime | None = None) -> list[Fonte]:
    agora = agora or agora_utc()
    with conexao.cursor(row_factory=dict_row) as cursor:
        return [_djen_oab(cursor, agora), _sincronizacao(cursor, agora), _djen_processo(cursor, agora),
                _datajud(cursor, agora)]


_CAMPO = re.compile(r"^\d+(,\d+)*$")


def descrever_agenda(expressao: str, referencia: date | None = None) -> str:
    """Agenda do pg_cron (UTC) em horário de Brasília, nos formatos usados pelo sistema."""
    partes = expressao.split()
    if len(partes) != 5 or partes[2:] != ["*", "*", "*"]:
        return expressao
    minuto, hora = partes[:2]
    dia = referencia or date.today()

    def local(h: int, m: int) -> datetime:
        return datetime(dia.year, dia.month, dia.day, h, m, tzinfo=timezone.utc).astimezone(FUSO)

    if _CAMPO.match(minuto) and _CAMPO.match(hora):
        horarios = sorted(local(int(h), int(m)) for h in hora.split(",") for m in minuto.split(","))
        return "diariamente às " + ", ".join(h.strftime("%Hh%M") for h in horarios)
    passo = re.fullmatch(r"\*/(\d+)", minuto)
    faixa = re.fullmatch(r"(\d+)-(\d+)", hora)
    if passo and faixa:
        inicio, fim = local(int(faixa[1]), 0), local(int(faixa[2]), 0)
        return (f"a cada {passo[1]} minutos, das {inicio.strftime('%Hh')} às "
                f"{fim.strftime('%Hh')}{60 - int(passo[1]):02d}")
    return expressao


def agendamentos(conexao) -> list[dict]:
    """Agendamentos do sistema e da captura do DJEN, com a última execução de cada um.

    Lista vazia quando o pg_cron não existe ou o papel da conexão não pode lê-lo."""
    try:
        with conexao.cursor(row_factory=dict_row) as cursor:
            if not _existe(cursor, "cron.job"):
                return []
            cursor.execute(
                "SELECT j.jobname, j.schedule, j.active, d.status, d.start_time, d.return_message "
                "FROM cron.job j LEFT JOIN LATERAL ("
                "  SELECT r.status, r.start_time, r.return_message FROM cron.job_run_details r "
                "  WHERE r.jobid = j.jobid ORDER BY r.start_time DESC LIMIT 1) d ON true "
                "WHERE j.jobname LIKE 'sgj-%' OR j.jobname LIKE 'djen-%' ORDER BY j.jobname"
            )
            linhas = cursor.fetchall()
    except psycopg.Error:
        return []
    for linha in linhas:
        linha["agenda"] = descrever_agenda(linha["schedule"])
        linha["quando"] = _hora(linha["start_time"]) if linha["start_time"] else "ainda não executado"
    return linhas
