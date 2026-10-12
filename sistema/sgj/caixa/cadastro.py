"""Conferência do cadastro importado e cadastro de processo (plano, Seção 23.4; Fase 1).

A conferência grava os dados que o titular confirma (sistema, grau, comarca,
polo, segredo de justiça, área, cliente, pasta no Drive) e só dá como
concluído o item que os dados sustentam: o sistema só fica conferido se
informado, o cliente só se o caso saiu do cliente provisório, e assim por
diante. O segredo de justiça exige confirmação expressa, porque dele depende
a habilitação da IA (plano, Seção 23.6, decisão 10). Toda alteração fica na
trilha de auditoria, numa só transação.
"""

from __future__ import annotations

import re

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .servico import OperacaoRecusada, _auditar

SISTEMAS = {"eproc": "eproc", "esaj": "e-SAJ", "projudi": "Projudi", "pje": "PJe", "cpe_stj": "CPE do STJ"}
AREAS = {"bancario": "Bancário", "civel": "Cível", "trabalhista": "Trabalhista", "previdenciario": "Previdenciário",
         "criminal": "Criminal"}
POLOS = {"ativo": "Ativo", "passivo": "Passivo", "terceiro": "Terceiro"}
GRAUS = {1: "1º grau", 2: "2º grau", 3: "Tribunal superior"}
TITULO_CONFERENCIA = "Conferir o cadastro"

# Enunciados dos itens de conferência (migração 0002 e cadastro de processo) e o dado que cada um exige.
TIPOS_DE_ITEM = (
    ("Revisar o cadastro", "revisar"),
    ("Identificar o cliente", "cliente"),
    ("Conferir o nome do cliente", "nome_cliente"),
    ("Definir a área", "area"),
    ("Confirmar o sistema", "sistema"),
    ("Conferir o grau e a comarca", "local"),
    ("Conferir o polo", "polo"),
    ("Confirmar se o processo tramita em segredo", "segredo"),
    ("Vincular a pasta", "pasta"),
)


def tipo_do_item(texto: str) -> str:
    return next((tipo for prefixo, tipo in TIPOS_DE_ITEM if texto.startswith(prefixo)), "outro")


def motivo_pendente(tipo: str, dados: dict, segredo_confirmado: bool = False) -> str | None:
    """Por que o item ainda não pode ser dado como conferido; None se pode."""
    if tipo == "cliente" and dados["cliente_provisorio"]:
        return "o caso ainda está no cliente provisório"
    if tipo == "area" and not dados["area"]:
        return "área não definida"
    if tipo == "sistema" and not dados["sistema"]:
        return "sistema não informado"
    if tipo == "local":
        if dados["grau"] is None:
            return "grau não informado"
        if dados["grau"] == 1 and not dados["comarca"]:
            return "comarca não informada"
    if tipo == "polo" and not dados["polo"]:
        return "polo não informado"
    if tipo == "pasta" and not dados["drive_pasta_id"]:
        return "pasta do Drive não informada"
    if tipo == "segredo" and not segredo_confirmado:
        return "marque a confirmação do segredo de justiça"
    return None


def digito_verificador(npu: str) -> str:
    """Dígito verificador da numeração única (módulo 97, Resolução CNJ 65/2008)."""
    return f"{98 - int(npu[:7] + npu[9:20] + '00') % 97:02d}"


def npu_valido(npu: str) -> bool:
    return bool(re.fullmatch(r"\d{20}", npu)) and digito_verificador(npu) == npu[7:9]


def identificador_pasta(valor: str | None) -> str | None:
    """Identificador da pasta do Drive, a partir do link ou do próprio identificador."""
    valor = (valor or "").strip()
    if not valor:
        return None
    achado = re.search(r"/folders/([A-Za-z0-9_-]+)", valor) or re.fullmatch(r"([A-Za-z0-9_-]{10,})", valor)
    if not achado:
        raise OperacaoRecusada("Pasta do Drive: informe o link da pasta ou o identificador dela.")
    return achado[1]


def _documento(valor: str | None) -> tuple[str | None, str | None]:
    digitos = re.sub(r"\D", "", valor or "")
    if not digitos:
        return None, None
    if len(digitos) not in (11, 14):
        raise OperacaoRecusada("CPF ou CNPJ: informe 11 ou 14 dígitos.")
    return digitos, "PF" if len(digitos) == 11 else "PJ"


def _opcao(valor: str | None, permitidos, rotulo: str):
    valor = (valor or "").strip()
    if not valor:
        return None
    if valor not in permitidos:
        raise OperacaoRecusada(f"{rotulo}: valor não reconhecido.")
    return valor


def _grau(valor: str | None) -> int | None:
    valor = (valor or "").strip()
    if not valor:
        return None
    if not valor.isdigit() or int(valor) not in GRAUS:
        raise OperacaoRecusada("Grau: valor não reconhecido.")
    return int(valor)


_CONSULTA = """
SELECT t.id AS tarefa_id, t.titulo AS tarefa_titulo, t.situacao AS tarefa_situacao, t.checklist, t.origem,
       pr.id AS processo_id, pr.npu, pr.tribunal, pr.comarca, pr.sistema, pr.sistema_fonte, pr.grau,
       pr.orgao_julgador, pr.classe, pr.polo, pr.segredo_justica, pr.drive_pasta_id,
       ca.id AS caso_id, ca.codigo AS caso_codigo, ca.titulo AS caso_titulo, ca.area,
       cl.id AS cliente_id, cl.codigo AS cliente_codigo, cl.nome AS cliente_nome, cl.cpf_cnpj, cl.tipo AS cliente_tipo,
       cl.provisorio AS cliente_provisorio,
       (SELECT count(*) FROM sgj.publicacoes p WHERE p.processo_id = pr.id) AS publicacoes,
       (SELECT max(p.data_disponibilizacao) FROM sgj.publicacoes p WHERE p.processo_id = pr.id) AS ultima_publicacao
FROM sgj.tarefas t
JOIN sgj.processos pr ON pr.id = t.processo_id
JOIN sgj.casos ca ON ca.id = pr.caso_id
JOIN sgj.clientes cl ON cl.id = ca.cliente_id
WHERE t.tipo = 'interna' AND t.titulo LIKE %s
"""


def _itens(checklist: list, dados: dict) -> list[dict]:
    itens = []
    for indice, item in enumerate(checklist):
        tipo = tipo_do_item(item.get("item", ""))
        itens.append({"indice": indice, "texto": item.get("item", ""), "tipo": tipo,
                      "concluido": bool(item.get("concluido")),
                      "pendencia": None if item.get("concluido") else motivo_pendente(tipo, dados, True)})
    return itens


def listar_conferencias(conexao, *, situacao: str = "pendentes") -> list[dict]:
    """Conferências de cadastro, com publicação mais recente primeiro."""
    abertas = situacao != "concluidas"
    with conexao.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            _CONSULTA + " AND (t.situacao IN ('concluida', 'cancelada')) <> %s "
            "ORDER BY ultima_publicacao DESC NULLS LAST, pr.npu",
            (TITULO_CONFERENCIA + "%", abertas),
        )
        linhas = cursor.fetchall()
    for linha in linhas:
        itens = _itens(linha["checklist"], linha)
        linha["pendentes"] = [i for i in itens if not i["concluido"]]
    return linhas


def obter_conferencia(conexao, tarefa_id: int) -> dict | None:
    with conexao.cursor(row_factory=dict_row) as cursor:
        cursor.execute(_CONSULTA + " AND t.id = %s", (TITULO_CONFERENCIA + "%", tarefa_id))
        dados = cursor.fetchone()
        if dados is None:
            return None
        cursor.execute(
            "SELECT observacoes FROM sgj.importacao_legado "
            "WHERE origem = 'public.processos' AND destino = 'sgj.processos' AND destino_id = %s",
            (dados["processo_id"],),
        )
        legado = cursor.fetchone()
    dados["legado"] = legado["observacoes"] if legado else {}
    dados["itens"] = _itens(dados["checklist"], dados)
    return dados


def clientes_para_escolha(conexao) -> list[dict]:
    with conexao.cursor(row_factory=dict_row) as cursor:
        cursor.execute("SELECT id, codigo, nome FROM sgj.clientes WHERE NOT provisorio ORDER BY nome, codigo")
        return cursor.fetchall()


def _proximo_codigo(cursor, tabela: str, letra: str) -> str:
    cursor.execute("SELECT pg_advisory_xact_lock(hashtext('sgj.codigos'))")
    cursor.execute(
        f"SELECT coalesce(max(substr(codigo, 2)::integer), 0) + 1 AS n FROM sgj.{tabela} WHERE codigo ~ %s",
        (f"^{letra}[0-9]+$",),
    )
    n = cursor.fetchone()["n"]
    return f"{letra}{n:04d}"


def _criar_cliente(cursor, usuario_id: int, nome: str | None, documento: str | None) -> int:
    nome = re.sub(r"\s+", " ", (nome or "")).strip()
    if not nome:
        raise OperacaoRecusada("Novo cliente: informe o nome.")
    cpf_cnpj, tipo = _documento(documento)
    _documento_livre(cursor, cpf_cnpj, None)
    codigo = _proximo_codigo(cursor, "clientes", "C")
    cursor.execute("INSERT INTO sgj.clientes (codigo, nome, cpf_cnpj, tipo) VALUES (%s, %s, %s, %s) RETURNING id",
                   (codigo, nome, cpf_cnpj, tipo))
    cliente_id = cursor.fetchone()["id"]
    _auditar(cursor, usuario_id, "criar_cliente", "clientes", cliente_id,
             depois={"codigo": codigo, "nome": nome, "tipo": tipo, "documento_informado": cpf_cnpj is not None})
    return cliente_id


def _documento_livre(cursor, cpf_cnpj: str | None, cliente_id: int | None) -> None:
    if cpf_cnpj is None:
        return
    cursor.execute("SELECT codigo FROM sgj.clientes WHERE cpf_cnpj = %s AND id IS DISTINCT FROM %s", (cpf_cnpj, cliente_id))
    outro = cursor.fetchone()
    if outro:
        raise OperacaoRecusada(f"CPF ou CNPJ já cadastrado para o cliente {outro['codigo']}.")


def _cliente_existente(cursor, codigo: str | None) -> int:
    cursor.execute("SELECT id FROM sgj.clientes WHERE codigo = %s AND NOT provisorio", ((codigo or "").strip(),))
    linha = cursor.fetchone()
    if linha is None:
        raise OperacaoRecusada("Cliente escolhido não encontrado.")
    return linha["id"]


def _alterar(cursor, usuario_id: int, tabela: str, registro_id: int, atual: dict, novo: dict) -> None:
    """Atualiza só os campos que mudaram e registra antes e depois."""
    mudancas = {campo: valor for campo, valor in novo.items() if atual.get(campo) != valor}
    if not mudancas:
        return
    atribuicoes = ", ".join(f"{campo} = %s" for campo in mudancas)
    cursor.execute(f"UPDATE sgj.{tabela} SET {atribuicoes} WHERE id = %s", (*mudancas.values(), registro_id))
    _auditar(cursor, usuario_id, "alterar_cadastro", tabela, registro_id,
             antes={campo: atual.get(campo) for campo in mudancas}, depois=mudancas)


def salvar_conferencia(conexao, tarefa_id: int, usuario_id: int, formulario: dict, concluir: list[int]) -> dict:
    """Grava os dados conferidos e conclui os itens indicados, se os dados os sustentarem; tudo ou nada."""
    with conexao.transaction():
        with conexao.cursor(row_factory=dict_row) as cursor:
            cursor.execute("SELECT situacao FROM sgj.tarefas WHERE id = %s FOR UPDATE", (tarefa_id,))
            tarefa = cursor.fetchone()
            atual = obter_conferencia(conexao, tarefa_id)
            if tarefa is None or atual is None:
                raise OperacaoRecusada("Conferência não encontrada.")
            if tarefa["situacao"] in ("concluida", "cancelada"):
                raise OperacaoRecusada("Conferência já concluída.")

            # Cliente
            acao = formulario.get("cliente_acao") or "manter"
            cliente_id = atual["cliente_id"]
            if acao == "novo":
                cliente_id = _criar_cliente(cursor, usuario_id, formulario.get("cliente_novo_nome"),
                                            formulario.get("cliente_novo_documento"))
            elif acao == "existente":
                cliente_id = _cliente_existente(cursor, formulario.get("cliente_existente"))
            elif acao == "manter" and not atual["cliente_provisorio"]:
                nome = re.sub(r"\s+", " ", formulario.get("cliente_nome") or "").strip() or atual["cliente_nome"]
                cpf_cnpj, tipo = _documento(formulario.get("cliente_documento"))
                if cpf_cnpj is None:
                    cpf_cnpj, tipo = atual["cpf_cnpj"], atual["cliente_tipo"]
                _documento_livre(cursor, cpf_cnpj, cliente_id)
                _alterar(cursor, usuario_id, "clientes", cliente_id,
                         {"nome": atual["cliente_nome"], "cpf_cnpj": atual["cpf_cnpj"], "tipo": atual["cliente_tipo"]},
                         {"nome": nome, "cpf_cnpj": cpf_cnpj, "tipo": tipo})
            elif acao != "manter":
                raise OperacaoRecusada("Cliente: opção não reconhecida.")

            # Caso
            titulo = re.sub(r"\s+", " ", formulario.get("caso_titulo") or "").strip()
            if not titulo:
                raise OperacaoRecusada("Informe o título do caso.")
            _alterar(cursor, usuario_id, "casos", atual["caso_id"],
                     {"cliente_id": atual["cliente_id"], "titulo": atual["caso_titulo"], "area": atual["area"]},
                     {"cliente_id": cliente_id, "titulo": titulo, "area": _opcao(formulario.get("area"), AREAS, "Área")})

            # Processo
            sistema = _opcao(formulario.get("sistema"), SISTEMAS, "Sistema")
            novo = {
                "sistema": sistema,
                "sistema_fonte": atual["sistema_fonte"] if sistema == atual["sistema"] else ("titular" if sistema else None),
                "grau": _grau(formulario.get("grau")),
                "comarca": re.sub(r"\s+", " ", formulario.get("comarca") or "").strip() or None,
                "polo": _opcao(formulario.get("polo"), POLOS, "Polo"),
                "drive_pasta_id": identificador_pasta(formulario.get("drive_pasta")) or atual["drive_pasta_id"],
            }
            segredo = formulario.get("segredo")
            if segredo in ("sim", "nao"):
                novo["segredo_justica"] = segredo == "sim"
            campos = ("sistema", "sistema_fonte", "grau", "comarca", "polo", "drive_pasta_id", "segredo_justica")
            _alterar(cursor, usuario_id, "processos", atual["processo_id"], {c: atual[c] for c in campos}, novo)

            # Itens
            depois = obter_conferencia(conexao, tarefa_id)
            confirmado = bool(formulario.get("segredo_confirmado")) and segredo in ("sim", "nao")
            checklist = [dict(item) for item in depois["checklist"]]
            recusas, concluidos = [], []
            for indice in sorted(set(concluir)):
                if not 0 <= indice < len(checklist) or checklist[indice].get("concluido"):
                    continue
                motivo = motivo_pendente(tipo_do_item(checklist[indice]["item"]), depois, confirmado)
                if motivo:
                    recusas.append(f"{checklist[indice]['item']}: {motivo}")
                else:
                    checklist[indice]["concluido"] = True
                    concluidos.append(checklist[indice]["item"])
            if recusas:
                raise OperacaoRecusada("Nada foi gravado. Itens que ainda não podem ser concluídos: " + "; ".join(recusas) + ".")
            terminada = all(item.get("concluido") for item in checklist)
            if concluidos or terminada:
                cursor.execute("UPDATE sgj.tarefas SET checklist = %s, situacao = %s WHERE id = %s",
                               (Jsonb(checklist), "concluida" if terminada else tarefa["situacao"], tarefa_id))
                _auditar(cursor, usuario_id, "conferir_cadastro", "tarefas", tarefa_id,
                         depois={"itens_concluidos": concluidos, "conferencia_concluida": terminada})
    return {"itens_concluidos": len(concluidos), "concluida": terminada}


def publicacoes_sem_processo(conexao, npu: str) -> list[dict]:
    with conexao.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            "SELECT id, data_disponibilizacao, tribunal, coalesce(tipo_documento, tipo_comunicacao) AS tipo, "
            "situacao_triagem FROM sgj.publicacoes WHERE npu = %s AND processo_id IS NULL "
            "ORDER BY data_disponibilizacao DESC, id DESC",
            (npu,),
        )
        return cursor.fetchall()


def tribunal_sugerido(conexao, npu: str) -> str | None:
    with conexao.cursor(row_factory=dict_row) as cursor:
        cursor.execute("SELECT sgj.tribunal_da_npu(%s) AS tribunal", (npu,))
        return cursor.fetchone()["tribunal"]


def cadastrar_processo(conexao, usuario_id: int, formulario: dict) -> dict:
    """Cadastra cliente (se novo), caso e processo, liga as publicações já capturadas e abre a conferência."""
    npu = re.sub(r"\D", "", formulario.get("npu") or "")
    if not npu_valido(npu):
        raise OperacaoRecusada("Número do processo inválido: são 20 dígitos, com o dígito verificador conferido.")
    tribunal = (formulario.get("tribunal") or "").strip().upper() or tribunal_sugerido(conexao, npu)
    if not tribunal:
        raise OperacaoRecusada("Informe o tribunal do processo.")
    segredo = formulario.get("segredo")
    if segredo not in ("sim", "nao"):
        raise OperacaoRecusada("Informe se o processo tramita em segredo de justiça.")
    titulo = re.sub(r"\s+", " ", formulario.get("caso_titulo") or "").strip()
    if not titulo:
        raise OperacaoRecusada("Informe o título do caso.")
    sistema = _opcao(formulario.get("sistema"), SISTEMAS, "Sistema")
    grau = _grau(formulario.get("grau"))
    comarca = re.sub(r"\s+", " ", formulario.get("comarca") or "").strip() or None
    polo = _opcao(formulario.get("polo"), POLOS, "Polo")
    area = _opcao(formulario.get("area"), AREAS, "Área")

    with conexao.transaction():
        with conexao.cursor(row_factory=dict_row) as cursor:
            cursor.execute("SELECT 1 FROM sgj.processos WHERE npu = %s", (npu,))
            if cursor.fetchone():
                raise OperacaoRecusada("Processo já cadastrado.")
            if formulario.get("cliente_acao") == "novo":
                cliente_id = _criar_cliente(cursor, usuario_id, formulario.get("cliente_novo_nome"),
                                            formulario.get("cliente_novo_documento"))
            else:
                cliente_id = _cliente_existente(cursor, formulario.get("cliente_existente"))
            codigo = _proximo_codigo(cursor, "casos", "K")
            cursor.execute("INSERT INTO sgj.casos (codigo, cliente_id, titulo, area) VALUES (%s, %s, %s, %s) RETURNING id",
                           (codigo, cliente_id, titulo, area))
            caso_id = cursor.fetchone()["id"]
            cursor.execute(
                "INSERT INTO sgj.processos (caso_id, npu, tribunal, comarca, sistema, sistema_fonte, grau, polo, "
                "segredo_justica) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (caso_id, npu, tribunal, comarca, sistema, "titular" if sistema else None, grau, polo, segredo == "sim"),
            )
            processo_id = cursor.fetchone()["id"]
            cursor.execute("UPDATE sgj.publicacoes SET processo_id = %s WHERE npu = %s AND processo_id IS NULL",
                           (processo_id, npu))
            vinculadas = cursor.rowcount
            dados = {"cliente_provisorio": False, "area": area, "sistema": sistema, "grau": grau, "comarca": comarca,
                     "polo": polo, "drive_pasta_id": None}
            itens = [texto for texto, tipo in (
                ("Definir a área do caso", "area"), ("Confirmar o sistema do processo", "sistema"),
                ("Conferir o grau e a comarca", "local"), ("Conferir o polo do cliente", "polo"),
                ("Vincular a pasta do processo no Drive", "pasta"),
            ) if motivo_pendente(tipo, dados)]
            tarefa_id = None
            if itens:
                cursor.execute(
                    "INSERT INTO sgj.tarefas (processo_id, origem, tipo, titulo, responsavel, checklist) "
                    "VALUES (%s, 'manual', 'interna', %s, %s, %s) RETURNING id",
                    (processo_id, TITULO_CONFERENCIA + " do processo", usuario_id,
                     Jsonb([{"item": texto, "concluido": False} for texto in itens])),
                )
                tarefa_id = cursor.fetchone()["id"]
            _auditar(cursor, usuario_id, "cadastrar_processo", "processos", processo_id, depois={
                "npu": npu, "tribunal": tribunal, "caso": codigo, "cliente_id": cliente_id,
                "segredo_justica": segredo == "sim", "publicacoes_vinculadas": vinculadas,
            })
    return {"processo_id": processo_id, "caso_codigo": codigo, "tarefa_id": tarefa_id, "publicacoes_vinculadas": vinculadas}
