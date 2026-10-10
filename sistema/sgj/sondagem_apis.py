"""Sondagem das APIs do DJEN e do DataJud (Fase 0 do plano).

Confirma, com chamada real, a rota, o status HTTP e os NOMES dos campos
devolvidos, antes da codificação dos coletores. Por sigilo, nunca imprime
valores: apenas a estrutura (chaves e quantidade de itens).

Uso:
    python -m sgj.sondagem_apis datajud --tribunal tjrs --npu 00000000000000000000
        (exige DATAJUD_API_KEY no ambiente, copiada da página oficial
         https://datajud-wiki.cnj.jus.br/api-publica/acesso/)

    python -m sgj.sondagem_apis djen --oab 107046 --uf RS --data 2026-10-09
        (os nomes dos parâmetros do DJEN NÃO foram verificados em fonte
         oficial; ajuste-os com --param nome=valor conforme o Swagger do CNJ)
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

DATAJUD_URL = "https://api-publica.datajud.cnj.jus.br/api_publica_{tribunal}/_search"
DJEN_URL = "https://comunicaapi.pje.jus.br/api/v1/comunicacao"
TIMEOUT = 30


def descrever_estrutura(dado: Any, profundidade: int = 3) -> Any:
    """Reduz um JSON à sua estrutura: chaves, tipos e tamanho de listas, sem valores."""
    if profundidade < 0:
        return "..."
    if isinstance(dado, dict):
        return {chave: descrever_estrutura(valor, profundidade - 1) for chave, valor in dado.items()}
    if isinstance(dado, list):
        if not dado:
            return "lista vazia"
        return {"itens": len(dado), "primeiro": descrever_estrutura(dado[0], profundidade - 1)}
    return type(dado).__name__


def _requisitar(requisicao: urllib.request.Request) -> tuple[int, Any, str | None]:
    """Devolve status HTTP (0 se não houve conexão), JSON e mensagem de falha."""
    contexto = ssl.create_default_context(cafile=os.environ.get("SSL_CERT_FILE"))
    try:
        with urllib.request.urlopen(requisicao, timeout=TIMEOUT, context=contexto) as resposta:
            corpo = resposta.read()
            status = resposta.status
    except urllib.error.HTTPError as erro:
        corpo = erro.read()
        status = erro.code
    except urllib.error.URLError as erro:
        return 0, None, f"falha de conexão: {erro.reason}"
    try:
        return status, json.loads(corpo or b"null"), None
    except json.JSONDecodeError:
        return status, None, f"resposta não JSON ({len(corpo)} bytes)"


def sondar_datajud(tribunal: str, npu: str) -> dict[str, Any]:
    chave = os.environ.get("DATAJUD_API_KEY")
    if not chave:
        raise SystemExit("Defina DATAJUD_API_KEY com a chave pública da página oficial do DataJud.")
    url = DATAJUD_URL.format(tribunal=tribunal.lower())
    corpo = json.dumps({"size": 1, "query": {"match": {"numeroProcesso": npu}}}).encode()
    requisicao = urllib.request.Request(
        url,
        data=corpo,
        method="POST",
        headers={"Authorization": f"APIKey {chave}", "Content-Type": "application/json"},
    )
    status, dado, mensagem = _requisitar(requisicao)
    return {"url": url, "status": status, "mensagem": mensagem, "estrutura": descrever_estrutura(dado, profundidade=6)}


def parametros_djen(oab: str, uf: str, data: str, extras: list[str]) -> dict[str, str]:
    parametros = {
        "numeroOab": oab,
        "ufOab": uf,
        "dataDisponibilizacaoInicio": data,
        "dataDisponibilizacaoFim": data,
        "pagina": "1",
        "itensPorPagina": "5",
    }
    for extra in extras:
        nome, _, valor = extra.partition("=")
        if valor:
            parametros[nome] = valor
        else:
            parametros.pop(nome, None)
    return parametros


def sondar_djen(oab: str, uf: str, data: str, extras: list[str]) -> dict[str, Any]:
    parametros = parametros_djen(oab, uf, data, extras)
    url = f"{DJEN_URL}?{urllib.parse.urlencode(parametros)}"
    status, dado, mensagem = _requisitar(urllib.request.Request(url, headers={"Accept": "application/json"}))
    return {"url": url, "status": status, "mensagem": mensagem, "estrutura": descrever_estrutura(dado, profundidade=4)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="api", required=True)

    p_datajud = sub.add_parser("datajud", help="Consulta um processo na API pública do DataJud")
    p_datajud.add_argument("--tribunal", required=True, help="sigla do alias, ex.: tjrs, tjsc, tjpr, tjsp, stj")
    p_datajud.add_argument("--npu", required=True, help="número do processo, 20 dígitos sem máscara")

    p_djen = sub.add_parser("djen", help="Consulta comunicações do DJEN por OAB e data")
    p_djen.add_argument("--oab", required=True)
    p_djen.add_argument("--uf", required=True)
    p_djen.add_argument("--data", required=True, help="AAAA-MM-DD")
    p_djen.add_argument(
        "--param", action="append", default=[],
        help="ajusta parâmetro: nome=valor para incluir ou substituir; nome= para remover",
    )

    args = parser.parse_args(argv)
    if args.api == "datajud":
        if not (args.npu.isdigit() and len(args.npu) == 20):
            parser.error("--npu deve ter 20 dígitos, sem máscara")
        resultado = sondar_datajud(args.tribunal, args.npu)
    else:
        resultado = sondar_djen(args.oab, args.uf, args.data, args.param)
    json.dump(resultado, sys.stdout, ensure_ascii=False, indent=2)
    print()
    return 0 if 200 <= resultado["status"] < 300 else 1


if __name__ == "__main__":
    raise SystemExit(main())
