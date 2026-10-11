"""Interface de teste da Caixa de Publicações (telas e API JSON).

Sem autenticação: só inicia com SGJ_AMBIENTE=teste e, pelo `python -m sgj.caixa`,
só atende no próprio computador (127.0.0.1). O painel definitivo, com login,
vem na Fase 1 (plano, Seções 14 e 16). As ações são registradas em nome do
titular cadastrado em sgj.usuarios.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from ..db.conexao import conectar
from . import servico

POR_PAGINA = 50
MODELOS = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def _data(valor) -> str:
    return valor.strftime("%d/%m/%Y") if isinstance(valor, date) else ""


def _npu(valor: str | None) -> str:
    d = "".join(c for c in (valor or "") if c.isdigit())
    if len(d) != 20:
        return valor or ""
    return f"{d[:7]}-{d[7:9]}.{d[9:13]}.{d[13]}.{d[14:16]}.{d[16:]}"


MODELOS.env.filters["data"] = _data
MODELOS.env.filters["npu"] = _npu
MODELOS.env.filters["ato"] = servico.rotulo_ato
MODELOS.env.globals["rotulo_situacao"] = {
    "capturada": "a triar", "triada": "triada", "aprovada": "aprovada", "arquivada": "sem providência",
}


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


def criar_app(dsn: str | None = None) -> FastAPI:
    if os.environ.get("SGJ_AMBIENTE") != "teste":
        raise RuntimeError(
            "Interface de teste sem autenticação: defina SGJ_AMBIENTE=teste e use somente no próprio computador."
        )

    app = FastAPI(title="Caixa de Publicações (teste)", docs_url="/api/docs", redoc_url=None)

    def conexao():
        with conectar(dsn) as c:
            yield c

    def recusa(erro: servico.OperacaoRecusada) -> HTTPException:
        return HTTPException(status_code=422, detail=str(erro))

    # Telas

    @app.get("/", include_in_schema=False)
    def inicio():
        return RedirectResponse("/caixa", status_code=303)

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

    # API JSON, para o painel definitivo

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
