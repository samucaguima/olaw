"""Telas e API JSON do sistema: painel "Meu dia", Caixa de Publicações e saúde das coletas.

Ainda sem login próprio (o login Google com segundo fator vem na Fase 1; plano,
Seção 16). Por isso só inicia em dois ambientes:
- SGJ_AMBIENTE=teste: no próprio computador (127.0.0.1);
- SGJ_AMBIENTE=rede_privada: no servidor, acessível só pela rede privada
  Tailscale, que informa o login de quem acessa no cabeçalho
  Tailscale-User-Login; só os logins de SGJ_USUARIOS entram.
As ações são registradas em nome do titular cadastrado em sgj.usuarios.

O Tailscale informa o login em toda requisição que sai do computador do
titular, inclusive a que outra página aberta no navegador mande ao sistema.
Por isso, gravação (POST) só é aceita quando o navegador atesta que partiu das
telas do próprio sistema (Sec-Fetch-Site, ou Origin igual ao endereço); e, no
ambiente de teste, só se atende pelo endereço 127.0.0.1 ou localhost, o que
impede outra página de ler o sistema trocando o endereço do próprio domínio
(DNS rebinding).
"""

from __future__ import annotations

import os
import re
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from ..db.conexao import conectar
from . import cadastro, painel, servico

POR_PAGINA = 50
AMBIENTES = {"teste": "ambiente de teste", "rede_privada": "rede privada"}
CABECALHO_IDENTIDADE = "Tailscale-User-Login"
SEM_IDENTIDADE = {"/saude"}
METODOS_DE_LEITURA = {"GET", "HEAD", "OPTIONS"}
HOSTS_DE_TESTE = {"127.0.0.1", "localhost"}
MODELOS = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


DIAS_DA_SEMANA = ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo")


def _data(valor) -> str:
    return valor.strftime("%d/%m/%Y") if isinstance(valor, date) else ""


def _data_longa(valor: date) -> str:
    return f"{DIAS_DA_SEMANA[valor.weekday()]}, {valor.strftime('%d/%m/%Y')}"


def _hora(valor: datetime | None) -> str:
    return valor.astimezone(painel.FUSO).strftime("%d/%m/%Y às %Hh%M") if valor else ""


def _npu(valor: str | None) -> str:
    d = "".join(c for c in (valor or "") if c.isdigit())
    if len(d) != 20:
        return valor or ""
    return f"{d[:7]}-{d[7:9]}.{d[9:13]}.{d[13]}.{d[14:16]}.{d[16:]}"


MODELOS.env.filters["data"] = _data
MODELOS.env.filters["data_longa"] = _data_longa
MODELOS.env.filters["hora"] = _hora
MODELOS.env.filters["npu"] = _npu
MODELOS.env.filters["ato"] = servico.rotulo_ato
MODELOS.env.globals["rotulo_situacao"] = {
    "capturada": "a triar", "triada": "triada", "aprovada": "aprovada", "arquivada": "sem providência",
}
MODELOS.env.globals["rotulo_coleta"] = {
    "ok": "funcionando", "atencao": "atenção", "falha": "falha", "aguardando": "aguardando", "inativa": "não instalada",
}
MODELOS.env.globals["classe_coleta"] = {"ok": "ok", "atencao": "atencao", "falha": "alerta", "aguardando": "", "inativa": ""}
MODELOS.env.globals["rotulo_semaforo"] = dict(painel.SEMAFORO)
MODELOS.env.globals["classe_semaforo"] = {
    "vencido": "alerta", "hoje": "alerta", "dois_dias": "atencao", "semana": "", "depois": "",
}
MODELOS.env.globals["ambiente"] = "ambiente de teste"
OPCOES_CADASTRO = {"sistemas": cadastro.SISTEMAS, "graus": cadastro.GRAUS, "polos": cadastro.POLOS, "areas": cadastro.AREAS}


class PedidoPrazo(BaseModel):
    prazo_legal_id: int | None = None
    dias: int | None = None
    em_dobro: bool = False
    providencia: str | None = None


class PedidoArquivamento(BaseModel):
    motivo: str | None = None


def _simulacao_json(s: servico.Simulacao) -> dict:
    r = s.resultado
    return {
        "tribunal": s.tribunal, "comarca": s.comarca, "dias": s.dias, "em_dobro": s.em_dobro,
        "disponibilizacao": r.disponibilizacao.isoformat(), "publicacao": r.publicacao.isoformat(),
        "inicio": r.inicio.isoformat(), "vencimento_controle": r.vencimento_sem_prorrogacao.isoformat(),
        "vencimento_com_prorrogacao": r.vencimento.isoformat(), "prazo_interno": r.prazo_interno.isoformat(),
        "confiavel": s.confiavel, "alertas": list(s.alertas), "memoria": list(r.memoria),
    }


def _usuarios_autorizados() -> set[str]:
    autorizados = {u.strip().lower() for u in os.environ.get("SGJ_USUARIOS", "").split(",") if u.strip()}
    if not autorizados:
        raise RuntimeError("Na rede privada, defina SGJ_USUARIOS com os logins autorizados, separados por vírgula.")
    return autorizados


def _nome_do_host(host: str) -> str:
    try:
        return urlsplit("//" + host).hostname or ""
    except ValueError:
        return ""


def _partiu_do_proprio_sistema(request: Request) -> bool:
    """Atestado do navegador de que a requisição saiu de uma tela do próprio sistema."""
    site = request.headers.get("sec-fetch-site")
    if site is not None:
        return site == "same-origin"
    try:
        origem = urlsplit(request.headers.get("origin", "")).netloc.lower()
    except ValueError:
        return False
    return bool(origem) and origem == request.headers.get("host", "").lower()


def criar_app(dsn: str | None = None) -> FastAPI:
    ambiente = os.environ.get("SGJ_AMBIENTE", "")
    if ambiente not in AMBIENTES:
        raise RuntimeError(
            "Interface sem login próprio: defina SGJ_AMBIENTE=teste (somente no próprio computador) ou "
            "SGJ_AMBIENTE=rede_privada (servidor acessível só pela rede privada, com SGJ_USUARIOS)."
        )
    autorizados = _usuarios_autorizados() if ambiente == "rede_privada" else None
    MODELOS.env.globals["ambiente"] = AMBIENTES[ambiente]

    # A documentação da API carrega código de fora (CDN); fica só no ambiente de teste.
    teste = ambiente == "teste"
    app = FastAPI(title="Gestão jurídica", docs_url="/api/docs" if teste else None,
                  openapi_url="/openapi.json" if teste else None, redoc_url=None)

    @app.middleware("http")
    async def origem(request: Request, call_next):
        if teste and _nome_do_host(request.headers.get("host", "")) not in HOSTS_DE_TESTE:
            return PlainTextResponse("No ambiente de teste, acesse pelo endereço http://127.0.0.1:8000.", status_code=400)
        if request.method not in METODOS_DE_LEITURA and not _partiu_do_proprio_sistema(request):
            return PlainTextResponse("Gravação recusada: a requisição não partiu das telas do próprio sistema.",
                                     status_code=403)
        return await call_next(request)

    if autorizados is not None:
        @app.middleware("http")
        async def identidade(request: Request, call_next):
            if request.url.path not in SEM_IDENTIDADE:
                login = request.headers.get(CABECALHO_IDENTIDADE, "").strip().lower()
                if login not in autorizados:
                    return PlainTextResponse("Acesso restrito aos usuários autorizados da rede privada.", status_code=403)
                request.state.login = login
            return await call_next(request)

    @app.get("/saude", include_in_schema=False)
    def saude():
        """Verificação do contêiner: responde sem identidade e sem revelar dados."""
        try:
            with conectar(dsn) as c:
                c.execute("SELECT 1")
        except Exception:
            return JSONResponse({"banco": "indisponível"}, status_code=503)
        return {"banco": "ok"}

    def conexao():
        with conectar(dsn) as c:
            yield c

    def recusa(erro: servico.OperacaoRecusada) -> HTTPException:
        return HTTPException(status_code=422, detail=str(erro))

    # Telas

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def meu_dia(request: Request, c=Depends(conexao)):
        return MODELOS.TemplateResponse(request, "painel.html", painel.meu_dia(c))

    @app.get("/coletas", response_class=HTMLResponse, include_in_schema=False)
    def coletas(request: Request, c=Depends(conexao)):
        return MODELOS.TemplateResponse(request, "coletas.html", {
            "coletas": painel.saude_coletas(c), "agendamentos": painel.agendamentos(c),
        })

    @app.get("/caixa", response_class=HTMLResponse, include_in_schema=False)
    def caixa(request: Request, situacao: str = "pendentes", tribunal: str = "", busca: str = "",
              pagina: int = 1, c=Depends(conexao)):
        pagina = max(pagina, 1)
        itens, total = servico.listar_publicacoes(
            c, situacao=situacao, tribunal=tribunal or None, busca=busca or None,
            limite=POR_PAGINA, deslocamento=(pagina - 1) * POR_PAGINA,
        )
        filtros = {"situacao": situacao, "tribunal": tribunal, "busca": busca}
        return MODELOS.TemplateResponse(request, "caixa.html", {
            "itens": itens, "total": total, "pagina": pagina, "paginas": max(1, -(-total // POR_PAGINA)),
            "filtros": filtros, "resumo": servico.resumo(c),
            "consulta": lambda **extra: urlencode({**filtros, **extra}),
        })

    def _tela_publicacao(request: Request, c, publicacao_id: int, *, simulacao=None, erro=None,
                         pedido: PedidoPrazo | None = None, mensagem=None, status_code=200):
        publicacao = servico.obter_publicacao(c, publicacao_id)
        if publicacao is None:
            raise HTTPException(status_code=404, detail="Publicação não encontrada.")
        return MODELOS.TemplateResponse(request, "publicacao.html", {
            "p": publicacao, "prazos_legais": servico.prazos_legais(c), "simulacao": simulacao, "erro": erro,
            "pedido": pedido or PedidoPrazo(), "mensagem": mensagem,
            "aprovado": servico.prazo_aprovado(c, publicacao_id),
            "pendente": publicacao["situacao_triagem"] in servico.PENDENTES,
        }, status_code=status_code)

    def _pedido_de_formulario(prazo_legal_id: str, dias: str, em_dobro: str, providencia: str) -> PedidoPrazo:
        return PedidoPrazo(
            prazo_legal_id=int(prazo_legal_id) if prazo_legal_id.strip() else None,
            dias=int(dias) if dias.strip() else None,
            em_dobro=bool(em_dobro), providencia=providencia or None,
        )

    @app.get("/caixa/{publicacao_id}", response_class=HTMLResponse, include_in_schema=False)
    def publicacao(request: Request, publicacao_id: int, ok: str = "", c=Depends(conexao)):
        mensagens = {"aprovado": "Prazo aprovado e tarefa criada.", "arquivado": "Publicação arquivada sem providência."}
        return _tela_publicacao(request, c, publicacao_id, mensagem=mensagens.get(ok))

    @app.post("/caixa/{publicacao_id}/calcular", response_class=HTMLResponse, include_in_schema=False)
    def calcular(request: Request, publicacao_id: int, prazo_legal_id: str = Form(""), dias: str = Form(""),
                 em_dobro: str = Form(""), providencia: str = Form(""), c=Depends(conexao)):
        try:
            pedido = _pedido_de_formulario(prazo_legal_id, dias, em_dobro, providencia)
            simulacao = servico.simular_prazo(c, publicacao_id, prazo_legal_id=pedido.prazo_legal_id,
                                              dias=pedido.dias, em_dobro=pedido.em_dobro)
            return _tela_publicacao(request, c, publicacao_id, simulacao=simulacao, pedido=pedido)
        except (servico.OperacaoRecusada, ValueError) as erro:
            return _tela_publicacao(request, c, publicacao_id, erro=str(erro), status_code=422)

    @app.post("/caixa/{publicacao_id}/aprovar", include_in_schema=False)
    def aprovar(request: Request, publicacao_id: int, prazo_legal_id: str = Form(""), dias: str = Form(""),
                em_dobro: str = Form(""), providencia: str = Form(""), c=Depends(conexao)):
        try:
            pedido = _pedido_de_formulario(prazo_legal_id, dias, em_dobro, providencia)
            servico.aprovar_prazo(c, publicacao_id, servico.usuario_titular(c), prazo_legal_id=pedido.prazo_legal_id,
                                  dias=pedido.dias, em_dobro=pedido.em_dobro, providencia=pedido.providencia)
        except (servico.OperacaoRecusada, ValueError) as erro:
            return _tela_publicacao(request, c, publicacao_id, erro=str(erro), status_code=422)
        return RedirectResponse(f"/caixa/{publicacao_id}?ok=aprovado", status_code=303)

    @app.post("/caixa/{publicacao_id}/arquivar", include_in_schema=False)
    def arquivar(request: Request, publicacao_id: int, motivo: str = Form(""), c=Depends(conexao)):
        try:
            servico.arquivar_publicacao(c, publicacao_id, servico.usuario_titular(c), motivo)
        except servico.OperacaoRecusada as erro:
            return _tela_publicacao(request, c, publicacao_id, erro=str(erro), status_code=422)
        return RedirectResponse(f"/caixa/{publicacao_id}?ok=arquivado", status_code=303)

    # Conferência do cadastro e cadastro de processo

    @app.get("/conferencia", response_class=HTMLResponse, include_in_schema=False)
    def conferencias(request: Request, situacao: str = "pendentes", c=Depends(conexao)):
        return MODELOS.TemplateResponse(request, "conferencias.html", {
            "itens": cadastro.listar_conferencias(c, situacao=situacao), "situacao": situacao,
        })

    def _tela_conferencia(request: Request, c, tarefa_id: int, *, erro=None, mensagem=None, status_code=200):
        dados = cadastro.obter_conferencia(c, tarefa_id)
        if dados is None:
            raise HTTPException(status_code=404, detail="Conferência não encontrada.")
        return MODELOS.TemplateResponse(request, "conferencia.html", {
            "c": dados, "erro": erro, "mensagem": mensagem, "clientes": cadastro.clientes_para_escolha(c),
            **OPCOES_CADASTRO,
        }, status_code=status_code)

    @app.get("/conferencia/{tarefa_id}", response_class=HTMLResponse, include_in_schema=False)
    def conferencia(request: Request, tarefa_id: int, ok: str = "", c=Depends(conexao)):
        mensagens = {"salvo": "Dados gravados.", "cadastrado": "Processo cadastrado. Confira os itens restantes."}
        return _tela_conferencia(request, c, tarefa_id, mensagem=mensagens.get(ok))

    @app.post("/conferencia/{tarefa_id}", include_in_schema=False)
    async def gravar_conferencia(request: Request, tarefa_id: int, c=Depends(conexao)):
        formulario = await request.form()
        concluir = [int(v) for v in formulario.getlist("concluir") if str(v).isdigit()]
        try:
            cadastro.salvar_conferencia(c, tarefa_id, servico.usuario_titular(c), dict(formulario), concluir)
        except servico.OperacaoRecusada as erro:
            return _tela_conferencia(request, c, tarefa_id, erro=str(erro), status_code=422)
        return RedirectResponse(f"/conferencia/{tarefa_id}?ok=salvo", status_code=303)

    def _tela_processo_novo(request: Request, c, formulario: dict, *, erro=None, status_code=200):
        npu = re.sub(r"\D", "", formulario.get("npu") or "")
        return MODELOS.TemplateResponse(request, "processo_novo.html", {
            "f": {**formulario, "npu": npu}, "erro": erro, "clientes": cadastro.clientes_para_escolha(c),
            "publicacoes": cadastro.publicacoes_sem_processo(c, npu) if npu else [], **OPCOES_CADASTRO,
        }, status_code=status_code)

    @app.get("/processos/novo", response_class=HTMLResponse, include_in_schema=False)
    def processo_novo(request: Request, npu: str = "", c=Depends(conexao)):
        digitos = re.sub(r"\D", "", npu)
        tribunal = cadastro.tribunal_sugerido(c, digitos) if len(digitos) == 20 else None
        return _tela_processo_novo(request, c, {"npu": digitos, "tribunal": tribunal})

    @app.post("/processos/novo", include_in_schema=False)
    async def cadastrar_processo(request: Request, c=Depends(conexao)):
        formulario = dict(await request.form())
        try:
            resultado = cadastro.cadastrar_processo(c, servico.usuario_titular(c), formulario)
        except servico.OperacaoRecusada as erro:
            return _tela_processo_novo(request, c, formulario, erro=str(erro), status_code=422)
        if resultado["tarefa_id"]:
            return RedirectResponse(f"/conferencia/{resultado['tarefa_id']}?ok=cadastrado", status_code=303)
        return RedirectResponse("/", status_code=303)

    # API JSON, para o painel definitivo

    @app.get("/api/painel")
    def api_painel(c=Depends(conexao)):
        return jsonable_encoder(painel.meu_dia(c))

    @app.get("/api/coletas")
    def api_coletas(c=Depends(conexao)):
        return jsonable_encoder({"coletas": painel.saude_coletas(c), "agendamentos": painel.agendamentos(c)})

    @app.get("/api/publicacoes")
    def api_listar(situacao: str = "pendentes", tribunal: str = "", busca: str = "", pagina: int = 1,
                   c=Depends(conexao)):
        itens, total = servico.listar_publicacoes(
            c, situacao=situacao, tribunal=tribunal or None, busca=busca or None,
            limite=POR_PAGINA, deslocamento=(max(pagina, 1) - 1) * POR_PAGINA,
        )
        return {"total": total, "pagina": max(pagina, 1), "itens": itens}

    @app.get("/api/publicacoes/{publicacao_id}")
    def api_publicacao(publicacao_id: int, c=Depends(conexao)):
        publicacao = servico.obter_publicacao(c, publicacao_id)
        if publicacao is None:
            raise HTTPException(status_code=404, detail="Publicação não encontrada.")
        return {"publicacao": publicacao, "prazo": servico.prazo_aprovado(c, publicacao_id)}

    @app.get("/api/prazos-legais")
    def api_prazos_legais(c=Depends(conexao)):
        return servico.prazos_legais(c)

    @app.post("/api/publicacoes/{publicacao_id}/simulacao")
    def api_simular(publicacao_id: int, pedido: PedidoPrazo, c=Depends(conexao)):
        try:
            return _simulacao_json(servico.simular_prazo(c, publicacao_id, prazo_legal_id=pedido.prazo_legal_id,
                                                         dias=pedido.dias, em_dobro=pedido.em_dobro))
        except servico.OperacaoRecusada as erro:
            raise recusa(erro) from erro

    @app.post("/api/publicacoes/{publicacao_id}/aprovacao", status_code=201)
    def api_aprovar(publicacao_id: int, pedido: PedidoPrazo, c=Depends(conexao)):
        try:
            resultado = servico.aprovar_prazo(c, publicacao_id, servico.usuario_titular(c),
                                              prazo_legal_id=pedido.prazo_legal_id, dias=pedido.dias,
                                              em_dobro=pedido.em_dobro, providencia=pedido.providencia)
        except servico.OperacaoRecusada as erro:
            raise recusa(erro) from erro
        return {"prazo_id": resultado["prazo_id"], "tarefa_id": resultado["tarefa_id"],
                "calculo": _simulacao_json(resultado["simulacao"])}

    @app.post("/api/publicacoes/{publicacao_id}/arquivamento", status_code=201)
    def api_arquivar(publicacao_id: int, pedido: PedidoArquivamento, c=Depends(conexao)):
        try:
            servico.arquivar_publicacao(c, publicacao_id, servico.usuario_titular(c), pedido.motivo)
        except servico.OperacaoRecusada as erro:
            raise recusa(erro) from erro
        return {"situacao": "arquivada"}

    return app
