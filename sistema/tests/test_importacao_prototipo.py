"""Importação da carteira do protótipo e ligação com a captura do DJEN.

As tabelas do protótipo (`public`) e da captura (`djen`) são recriadas aqui
com a mesma estrutura das de produção e preenchidas com dados fictícios que
reproduzem as situações encontradas na carteira real: grafias variadas de
tribunal e de área, nomes repetidos com maiúsculas diferentes, processos sem
nome de cliente, processo no STJ com a numeração de origem e publicação
registrada pelas duas capturas.
"""

import json
import os

import pytest

psycopg = pytest.importorskip("psycopg")

pytestmark = pytest.mark.skipif(not os.environ.get("SGJ_TEST_PG_DSN"), reason="SGJ_TEST_PG_DSN não definido")

PROTOTIPO = """
CREATE TABLE public.processos (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    numero_cnj text UNIQUE,
    nome text, telefone text, apelido text, area text,
    fase text DEFAULT 'judicial', status text DEFAULT 'ativo',
    tribunal text, parte_contraria text, tipo_acao text, drive_folder_trabalho_path text,
    criado_em timestamptz DEFAULT now(), atualizado_em timestamptz DEFAULT now(), encerrado_em timestamptz
);
CREATE TABLE public.processos_movimentacoes (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    processo_id uuid REFERENCES public.processos(id),
    numero_cnj text, hash_dedup text UNIQUE, tipo text, texto text, data_disponibilizacao date,
    fonte_captura text DEFAULT 'djen', sigiloso boolean DEFAULT false, capturado_em timestamptz DEFAULT now(),
    triagem_ia text, triagem_ia_em timestamptz, triagem_ia_obs text, minuta_path text
);
CREATE SCHEMA djen;
CREATE TABLE djen.comunicacao (
    id bigint PRIMARY KEY, data_disponibilizacao date, tribunal text, processo text, classe text,
    tipo_comunicacao text, tipo_documento text, orgao text, cabecalho text, texto_html text, link text,
    raw jsonb, capturada_em timestamptz DEFAULT now(), revisada boolean DEFAULT false
);
"""

# numero_cnj, nome, área, situação, tribunal, tipo de ação, parte contrária, pasta local
PROCESSOS = [
    ("5000001-11.2025.8.21.0001", "JOÃO EXEMPLO", "civel_bancario", "revisar", "TJRS",
     "Procedimento Comum Cível (réu)", "Banco Exemplo S.A.", "C:\\Clientes\\Exemplo"),
    ("5000002-22.2025.8.21.0002", "João  Exemplo", "cível", "revisar", "tjrs", None, None, None),
    ("5000003-33.2024.8.21.0010", "Maria Exemplo (parceria Colega)", "revisar", "ativo", "TJRS/STJ",
     "Apelação Cível", None, None),
    ("5000004-44.2025.8.24.0023", None, None, "ativo", "tjsc", "SIGILOSO - nao aberto", None, None),
    ("5000005-55.2025.8.24.0023", "", "federal", "ativo", "TJSC", None, None, None),
    ("0000006-66.2025.5.04.0001", "Pedro Exemplo", "trabalhista", "ativo", "TRT4", None, None, None),
    ("5000007-77.2025.4.04.7200", "Ana Exemplo", "previdenciario", "ativo", "TRF4/JEF-SC", None, None, None),
    ("5000008-88.2025.8.13.0024", "Fora Exemplo", "civel", "ativo", "TJMG", None, None, None),
    ("123", "Inválido Exemplo", "civel", "ativo", "TJRS", None, None, None),
]

HTML_PROTOTIPO = (
    "<html><head><meta charset='utf-8'><style>p { margin: 0 }</style></head><body>"
    "<p>Intima&ccedil;&atilde;o da decis&atilde;o de admissibilidade.</p></body></html>"
)

# numero_cnj, processo do protótipo (índice em PROCESSOS ou None), data, texto, hash do protótipo
MOVIMENTACOES = [
    ("5000003-33.2024.8.21.0010", 2, "2026-06-08", HTML_PROTOTIPO, "djen_m1"),
    ("5000001-11.2025.8.21.0001", 0, "2026-05-20", "Fica intimada a parte.", "djen_m2"),
    ("5000004-44.2025.8.24.0023", 3, "2026-07-01", "Intimação em processo sigiloso.", "djen_m3"),
    ("5009999-99.2025.8.21.0001", None, "2026-07-02", "Intimação de processo fora da carteira.", "djen_m4"),
]

# id, processo, tribunal, data, texto, endereço, órgão, classe
COMUNICACOES = [
    (101, "5000003-33.2024.8.21.0010", "STJ", "2026-06-08",
     "<div>Intimação da decisão de <b>admissibilidade</b>.</div>", "https://processo.stj.jus.br/processo/1",
     "SECRETARIA JUDICIÁRIA", "RECURSO ESPECIAL"),
    (102, "5000001-11.2025.8.21.0001", "TJRS", "2026-09-25", "<p>Fica intimada a parte.</p>",
     "https://eproc1g.tjrs.jus.br/eproc/externo.php?x=1", "2ª Vara Cível da Comarca de Torres", "PROCEDIMENTO COMUM CíVEL"),
    (103, "5000003-33.2024.8.21.0010", "TJRS", "2026-03-01", "<p>Acórdão publicado.</p>",
     "https://eproc2g.tjrs.jus.br/eproc/externo.php?x=2", "14ª Câmara Cível", "APELAçãO CíVEL"),
    (104, "5008888-88.2025.8.21.0001", "TJRS", "2026-10-01", "<p>Intimação de processo novo.</p>",
     "https://eproc1g.tjrs.jus.br/eproc/externo.php?x=3", "1ª Vara Cível da Comarca de Osório", "USUCAPIãO"),
    (105, "0000006-66.2025.5.04.0001", "TRT4", "2026-09-28", "<p>Intimação trabalhista.</p>",
     "https://pje.trt4.jus.br/consultaprocessual/x", "VARA DO TRABALHO DE CAMAQUÃ", "AçãO TRABALHISTA - RITO ORDINáRIO"),
    (106, "5000007-77.2025.4.04.7200", "TRF4", "2026-09-30", "<p>Intimação federal.</p>",
     "https://eproc.jfsc.jus.br/eproc/x", "8ª Vara Federal de Florianópolis", "PROCEDIMENTO DO JUIZADO ESPECIAL CíVEL"),
    (107, "5000002-22.2025.8.21.0002", "TJRS", "2026-10-08", "<p>Intimação sem endereço.</p>", "",
     "6ª Vara Cível da Comarca de Caxias do Sul", "PROCEDIMENTO COMUM CíVEL"),
]


def contagens_de_origem(banco):
    return banco.execute(
        "SELECT (SELECT count(*) FROM public.processos), (SELECT count(*) FROM public.processos_movimentacoes), "
        "(SELECT count(*) FROM djen.comunicacao), (SELECT count(*) FROM djen.comunicacao WHERE revisada)"
    ).fetchone()


@pytest.fixture(scope="module")
def carteira(banco):
    banco.execute(PROTOTIPO)
    banco.execute(
        "INSERT INTO sgj.usuarios (nome, email, perfil) VALUES ('Titular', 'titular@exemplo.invalid', 'titular')"
    )
    legados = []
    for ordem, (npu, nome, area, situacao, tribunal, tipo_acao, contraria, pasta) in enumerate(PROCESSOS):
        legados.append(banco.execute(
            "INSERT INTO public.processos (numero_cnj, nome, area, status, tribunal, tipo_acao, parte_contraria, "
            "drive_folder_trabalho_path, criado_em) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, '2026-06-14 10:00'::timestamptz + %s * interval '1 minute') "
            "RETURNING id",
            (npu, nome, area, situacao, tribunal, tipo_acao, contraria, pasta, ordem),
        ).fetchone()[0])
    for npu, indice, data, texto, hash_ in MOVIMENTACOES:
        banco.execute(
            "INSERT INTO public.processos_movimentacoes (processo_id, numero_cnj, hash_dedup, tipo, texto, "
            "data_disponibilizacao, triagem_ia) VALUES (%s, %s, %s, 'Intimação', %s, %s, 'so_ciencia')",
            (None if indice is None else legados[indice], npu, hash_, texto, data),
        )
    for id_, npu, tribunal, data, texto, link, orgao, classe in COMUNICACOES:
        banco.execute(
            "INSERT INTO djen.comunicacao (id, data_disponibilizacao, tribunal, processo, classe, tipo_comunicacao, "
            "orgao, texto_html, link, raw) VALUES (%s, %s, %s, %s, %s, 'Intimação', %s, %s, %s, %s)",
            (id_, data, tribunal, npu, classe, orgao, texto, link, json.dumps({"hash": f"H{id_}", "id": id_})),
        )
    origem_antes = contagens_de_origem(banco)
    importacao = banco.execute("SELECT sgj.importar_carteira_prototipo()").fetchone()[0]
    sincronizacao = banco.execute("SELECT sgj.sincronizar_djen()").fetchone()[0]
    return {"importacao": importacao, "sincronizacao": sincronizacao, "origem_antes": origem_antes}


def processo(banco, npu):
    linha = banco.execute(
        "SELECT p.tribunal, p.sistema, p.sistema_fonte, p.grau, p.comarca, p.orgao_julgador, p.classe, p.polo, "
        "p.segredo_justica, c.codigo, c.titulo, c.area, cl.nome, cl.provisorio "
        "FROM sgj.processos p JOIN sgj.casos c ON c.id = p.caso_id JOIN sgj.clientes cl ON cl.id = c.cliente_id "
        "WHERE p.npu = regexp_replace(%s, '\\D', '', 'g')",
        (npu,),
    ).fetchone()
    campos = ("tribunal", "sistema", "sistema_fonte", "grau", "comarca", "orgao", "classe", "polo", "segredo",
              "caso", "titulo", "area", "cliente", "provisorio")
    return dict(zip(campos, linha))


def checklist(banco, npu):
    itens = banco.execute(
        "SELECT t.checklist FROM sgj.tarefas t JOIN sgj.processos p ON p.id = t.processo_id "
        "WHERE p.npu = regexp_replace(%s, '\\D', '', 'g') AND t.origem = 'importacao'",
        (npu,),
    ).fetchone()[0]
    return [item["item"] for item in itens]


def test_resumo_da_importacao(carteira):
    resumo = carteira["importacao"]
    assert resumo["processos"] == 7
    assert resumo["casos"] == 7
    assert resumo["clientes_novos"] == 4
    assert resumo["tarefas_de_conferencia"] == 7
    assert resumo["processos_com_sistema_pelo_djen"] == 4
    assert resumo["publicacoes_novas"] == 4
    assert resumo["publicacoes_ja_registradas"] == 0
    assert {i["motivo"] for i in resumo["processos_ignorados"]} == {
        "tribunal não reconhecido pelo segmento J.TR", "numeração inválida"}


def test_tribunal_vem_da_numeracao_e_area_e_normalizada(banco, carteira):
    assert processo(banco, PROCESSOS[1][0])["tribunal"] == "TJRS"
    assert processo(banco, PROCESSOS[2][0])["tribunal"] == "TJRS"
    assert processo(banco, PROCESSOS[6][0])["tribunal"] == "TRF4"
    assert [processo(banco, p[0])["area"] for p in PROCESSOS[:7]] == [
        "bancario", "civel", None, None, None, "trabalhista", "previdenciario"]


def test_nomes_iguais_viram_um_cliente_e_sem_nome_vai_ao_provisorio(banco, carteira):
    p1, p2 = processo(banco, PROCESSOS[0][0]), processo(banco, PROCESSOS[1][0])
    assert p1["cliente"] == p2["cliente"] == "João Exemplo"
    p4, p5 = processo(banco, PROCESSOS[3][0]), processo(banco, PROCESSOS[4][0])
    assert p4["provisorio"] and p5["provisorio"] and p4["cliente"] == "Cliente a identificar"
    codigos = banco.execute("SELECT array_agg(codigo ORDER BY codigo) FROM sgj.clientes").fetchone()[0]
    assert codigos == ["C0000", "C0001", "C0002", "C0003", "C0004"]
    assert banco.execute("SELECT count(*) FROM sgj.clientes WHERE cpf_cnpj IS NOT NULL OR tipo IS NOT NULL").fetchone()[0] == 0


def test_caso_por_processo_com_titulo_polo_e_segredo(banco, carteira):
    p1 = processo(banco, PROCESSOS[0][0])
    assert p1["caso"] == "K0001"
    assert p1["titulo"] == "Procedimento Comum Cível (réu) x Banco Exemplo S.A."
    assert p1["polo"] == "passivo"
    assert processo(banco, PROCESSOS[1][0])["titulo"] == "Processo 5000002-22.2025.8.21.0002"
    assert processo(banco, PROCESSOS[3][0])["segredo"] is True
    assert processo(banco, PROCESSOS[0][0])["segredo"] is False


def test_dados_verificaveis_no_djen(banco, carteira):
    p1 = processo(banco, PROCESSOS[0][0])
    assert (p1["sistema"], p1["sistema_fonte"], p1["grau"], p1["comarca"]) == ("eproc", "djen", 1, "Torres")
    assert p1["orgao"] == "2ª Vara Cível da Comarca de Torres"
    assert p1["classe"] == "PROCEDIMENTO COMUM CÍVEL"
    # No STJ, com a numeração de origem: sistema e grau do STJ; órgão e classe da origem.
    p3 = processo(banco, PROCESSOS[2][0])
    assert (p3["tribunal"], p3["sistema"], p3["grau"], p3["comarca"]) == ("TJRS", "cpe_stj", 3, None)
    assert (p3["orgao"], p3["classe"]) == ("14ª Câmara Cível", "APELAÇÃO CÍVEL")
    # Comunicação sem endereço do documento não confirma o sistema.
    p2 = processo(banco, PROCESSOS[1][0])
    assert (p2["sistema"], p2["sistema_fonte"], p2["grau"], p2["comarca"]) == (None, None, 1, "Caxias do Sul")
    p6 = processo(banco, PROCESSOS[5][0])
    assert (p6["sistema"], p6["grau"], p6["comarca"]) == ("pje", 1, None)
    p7 = processo(banco, PROCESSOS[6][0])
    assert (p7["sistema"], p7["grau"]) == ("eproc", 1)
    sem_comunicacao = processo(banco, PROCESSOS[3][0])
    assert (sem_comunicacao["sistema"], sem_comunicacao["grau"]) == (None, None)


def test_tarefa_de_conferencia_lista_so_as_pendencias(banco, carteira):
    assert checklist(banco, PROCESSOS[0][0]) == [
        'Revisar o cadastro: o processo estava com a situação "revisar" no protótipo',
        "Confirmar se o processo tramita em segredo de justiça (a IA fica desabilitada para processos sigilosos)",
        "Vincular a pasta do processo no Drive (há pasta local registrada no protótipo)",
    ]
    p3 = checklist(banco, PROCESSOS[2][0])
    assert "Conferir o nome do cliente: o registro de origem contém anotação ou mais de uma pessoa" in p3
    assert "Definir a área do caso (no protótipo: revisar)" in p3
    assert "Confirmar o sistema do processo" not in p3
    p4 = checklist(banco, PROCESSOS[3][0])
    assert p4[0] == "Identificar o cliente e vincular o caso a ele"
    assert "Confirmar o sistema do processo" in p4
    assert not any("segredo" in item for item in p4)
    situacoes = banco.execute(
        "SELECT DISTINCT tipo, situacao, responsavel IS NOT NULL FROM sgj.tarefas WHERE origem = 'importacao'"
    ).fetchall()
    assert situacoes == [("interna", "a_fazer", True)]


def test_publicacao_das_duas_capturas_nao_duplica(banco, carteira):
    sinc = carteira["sincronizacao"]
    assert (sinc["situacao"], sinc["completadas"], sinc["inseridas"], sinc["vinculadas"]) == ("concluida", 1, 6, 0)
    assert banco.execute("SELECT count(*) FROM sgj.publicacoes").fetchone()[0] == 10
    completada = banco.execute(
        "SELECT p.djen_id, p.hash, p.tribunal, p.link, p.texto FROM sgj.publicacoes p "
        "JOIN sgj.importacao_legado l ON l.destino_id = p.id AND l.destino = 'sgj.publicacoes' "
        "JOIN public.processos_movimentacoes m ON m.id::text = l.origem_id WHERE m.hash_dedup = 'djen_m1'"
    ).fetchone()
    assert completada == (101, "H101", "STJ", "https://processo.stj.jus.br/processo/1",
                          "Intimação da decisão de admissibilidade.")
    # Mesmo texto em outra data é outra publicação.
    assert banco.execute(
        "SELECT count(*) FROM sgj.publicacoes WHERE texto = 'Fica intimada a parte.'"
    ).fetchone()[0] == 2
    fora = banco.execute(
        "SELECT count(*) FROM sgj.publicacoes WHERE processo_id IS NULL"
    ).fetchone()[0]
    assert fora == 2


def test_tabelas_de_origem_ficam_intactas(banco, carteira):
    assert contagens_de_origem(banco) == carteira["origem_antes"]


def test_repeticao_nao_duplica_e_vincula_processo_cadastrado_depois(banco, carteira):
    assert banco.execute("SELECT sgj.importar_carteira_prototipo()").fetchone()[0]["processos"] == 0
    sinc = banco.execute("SELECT sgj.sincronizar_djen()").fetchone()[0]
    assert (sinc["inseridas"], sinc["completadas"], sinc["vinculadas"]) == (0, 0, 0)
    banco.execute(
        "INSERT INTO public.processos (numero_cnj, nome, tribunal) VALUES ('5008888-88.2025.8.21.0001', 'Novo Exemplo', 'TJRS')"
    )
    resumo = banco.execute("SELECT sgj.importar_carteira_prototipo()").fetchone()[0]
    assert (resumo["processos"], resumo["clientes_novos"], resumo["publicacoes_novas"]) == (1, 1, 0)
    novo = processo(banco, "5008888-88.2025.8.21.0001")
    assert (novo["caso"], novo["sistema"], novo["comarca"]) == ("K0008", "eproc", "Osório")
    sinc = banco.execute("SELECT sgj.sincronizar_djen()").fetchone()[0]
    assert (sinc["inseridas"], sinc["vinculadas"]) == (0, 1)
    assert banco.execute("SELECT count(*) FROM sgj.publicacoes").fetchone()[0] == 10


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        (HTML_PROTOTIPO, "Intimação da decisão de admissibilidade."),
        ("<p>Linha 1<br>Linha 2</p><p>Linha&nbsp;3 &amp;lt; &#233; &#xE9;</p>", "Linha 1\nLinha 2\nLinha 3 &lt; é é"),
        ("<table><tr><td>A</td><td>B</td></tr></table>", "A B"),
        ("Texto   simples\ncom quebra &ccedil;", "Texto simples\ncom quebra ç"),
        ("Espaço" + chr(0xA0) + " rígido", "Espaço rígido"),
        ("a &ndash; b &mdash; c", "a " + chr(0x2013) + " b " + chr(0x2014) + " c"),
        ("<p> </p>", None),
    ],
)
def test_conversao_de_html(banco, entrada, esperado):
    assert banco.execute("SELECT sgj.texto_de_html(%s)", (entrada,)).fetchone()[0] == esperado


def test_falha_da_sincronizacao_fica_registrada(banco, carteira):
    banco.execute("ALTER TABLE djen.comunicacao RENAME TO comunicacao_ausente")
    try:
        resultado = banco.execute("SELECT sgj.sincronizar_djen()").fetchone()[0]
    finally:
        banco.execute("ALTER TABLE djen.comunicacao_ausente RENAME TO comunicacao")
    assert resultado["situacao"] == "falhou"
    coleta = banco.execute("SELECT situacao, erro IS NOT NULL FROM sgj.coletas WHERE id = %s", (resultado["coleta"],)).fetchone()
    assert coleta == ("falhou", True)
