-- Esquema inicial do sistema de gestão jurídica (plano, Seção 15).
-- PostgreSQL 16 com a extensão pgvector.

BEGIN;

CREATE EXTENSION IF NOT EXISTS vector;

-- Usuários e regras de trabalho

CREATE TABLE usuarios (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nome        text NOT NULL,
    email       text NOT NULL UNIQUE,
    perfil      text NOT NULL CHECK (perfil IN ('titular', 'colaborador', 'leitura')),
    ativo       boolean NOT NULL DEFAULT true,
    criado_em   timestamptz NOT NULL DEFAULT now()
);

-- Clientes, casos e contratos

CREATE TABLE clientes (
    id                   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    codigo               text NOT NULL UNIQUE CHECK (codigo ~ '^C[0-9]{4,}$'),
    tipo                 text NOT NULL CHECK (tipo IN ('PF', 'PJ')),
    nome                 text NOT NULL,
    cpf_cnpj             text NOT NULL UNIQUE CHECK (cpf_cnpj ~ '^([0-9]{11}|[0-9]{14})$'),
    contatos             jsonb NOT NULL DEFAULT '{}'::jsonb,
    drive_pasta_id       text,
    asaas_customer_id    text UNIQUE,
    chatwoot_contact_id  text UNIQUE,
    criado_em            timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE casos (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    codigo          text NOT NULL UNIQUE CHECK (codigo ~ '^K[0-9]{4,}$'),
    cliente_id      bigint NOT NULL REFERENCES clientes(id),
    titulo          text NOT NULL,
    area            text,
    situacao        text NOT NULL DEFAULT 'ativo' CHECK (situacao IN ('ativo', 'suspenso', 'encerrado')),
    drive_pasta_id  text,
    criado_em       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE contratos_honorarios (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    caso_id             bigint NOT NULL REFERENCES casos(id),
    modalidade          text NOT NULL CHECK (modalidade IN ('fixo', 'parcelado', 'mensal', 'exito', 'misto')),
    valores             jsonb NOT NULL DEFAULT '{}'::jsonb,
    percentual_exito    numeric(5, 2) CHECK (percentual_exito BETWEEN 0 AND 100),
    parcelas            integer CHECK (parcelas > 0),
    documento_drive_id  text,
    criado_em           timestamptz NOT NULL DEFAULT now()
);

-- Processos

CREATE TABLE processos (
    id                   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    caso_id              bigint NOT NULL REFERENCES casos(id),
    npu                  text NOT NULL UNIQUE CHECK (npu ~ '^[0-9]{20}$'),
    tribunal             text NOT NULL,
    comarca              text,
    sistema              text NOT NULL CHECK (sistema IN ('eproc', 'esaj', 'projudi', 'pje', 'cpe_stj')),
    grau                 smallint CHECK (grau IN (1, 2, 3)),
    orgao_julgador       text,
    classe               text,
    polo                 text CHECK (polo IN ('ativo', 'passivo', 'terceiro')),
    segredo_justica      boolean NOT NULL DEFAULT false,
    drive_pasta_id       text,
    ultima_sincronizacao timestamptz,
    criado_em            timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN processos.npu IS 'Numeração única sem máscara (20 dígitos).';
COMMENT ON COLUMN processos.sistema IS 'Reverificar periodicamente: TJSP e TJPR mantêm acervo em sistema antigo.';

CREATE TABLE partes (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    processo_id  bigint NOT NULL REFERENCES processos(id) ON DELETE CASCADE,
    nome         text NOT NULL,
    polo         text NOT NULL CHECK (polo IN ('ativo', 'passivo', 'terceiro')),
    advogados    jsonb NOT NULL DEFAULT '[]'::jsonb
);

-- Coletas, publicações e movimentações

CREATE TABLE coletas (
    id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    fonte     text NOT NULL,
    inicio    timestamptz NOT NULL DEFAULT now(),
    fim       timestamptz,
    situacao  text NOT NULL DEFAULT 'em_execucao' CHECK (situacao IN ('em_execucao', 'concluida', 'falhou')),
    itens     integer NOT NULL DEFAULT 0,
    erro      text
);
COMMENT ON COLUMN coletas.fonte IS 'djen, datajud ou robo:<sistema>:<tribunal>.';

CREATE TABLE publicacoes (
    id                     bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    processo_id            bigint REFERENCES processos(id),
    npu                    text NOT NULL,
    origem                 text NOT NULL DEFAULT 'djen' CHECK (origem = 'djen'),
    hash                   text NOT NULL UNIQUE,
    data_disponibilizacao  date NOT NULL,
    data_publicacao        date,
    tipo_comunicacao       text,
    texto                  text NOT NULL,
    certidao_drive_id      text,
    situacao_triagem       text NOT NULL DEFAULT 'capturada'
                           CHECK (situacao_triagem IN ('capturada', 'triada', 'aprovada', 'arquivada')),
    coleta_id              bigint REFERENCES coletas(id),
    capturada_em           timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN publicacoes.processo_id IS 'Nulo enquanto o processo não estiver cadastrado (fila de processos não identificados).';

CREATE TABLE movimentacoes (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    processo_id  bigint NOT NULL REFERENCES processos(id),
    origem       text NOT NULL CHECK (origem IN ('datajud', 'robo')),
    data_hora    timestamptz NOT NULL,
    codigo       text,
    descricao    text NOT NULL,
    coleta_id    bigint REFERENCES coletas(id),
    UNIQUE (processo_id, origem, data_hora, codigo, descricao)
);

-- Documentos e índice semântico

CREATE TABLE documentos (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    processo_id      bigint REFERENCES processos(id),
    caso_id          bigint REFERENCES casos(id),
    origem           text NOT NULL CHECK (origem IN ('robo', 'dashboard', 'drive', 'iris', 'gerador')),
    evento           text,
    tipo             text,
    drive_file_id    text NOT NULL UNIQUE,
    sha256           text NOT NULL,
    paginas          integer,
    texto_extraido   text,
    indexado         boolean NOT NULL DEFAULT false,
    criado_em        timestamptz NOT NULL DEFAULT now(),
    CHECK (processo_id IS NOT NULL OR caso_id IS NOT NULL)
);

CREATE TABLE documentos_trechos (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    documento_id  bigint NOT NULL REFERENCES documentos(id) ON DELETE CASCADE,
    ordem         integer NOT NULL,
    texto         text NOT NULL,
    embedding     vector,
    UNIQUE (documento_id, ordem)
);
COMMENT ON COLUMN documentos_trechos.embedding IS
    'Gerado por modelo local (plano, Seção 13.3). Fixar a dimensão e criar o índice após a escolha do modelo.';

-- Prazos legais, calendário e prazos

CREATE TABLE prazos_legais (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tipo_ato       text NOT NULL UNIQUE,
    dias           integer NOT NULL CHECK (dias > 0),
    contagem       text NOT NULL CHECK (contagem IN ('uteis', 'corridos')),
    dispositivo    text NOT NULL,
    link_oficial   text NOT NULL,
    conferido_em   date NOT NULL,
    conferido_por  bigint NOT NULL REFERENCES usuarios(id)
);

CREATE TABLE calendario (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tribunal     text NOT NULL,
    comarca      text,
    data         date NOT NULL,
    tipo         text NOT NULL CHECK (tipo IN ('feriado', 'suspensao', 'indisponibilidade', 'expediente_alterado')),
    descricao    text NOT NULL,
    fonte_link   text NOT NULL CHECK (length(trim(fonte_link)) > 0),
    incluido_em  timestamptz NOT NULL DEFAULT now(),
    incluido_por bigint REFERENCES usuarios(id),
    CHECK (tribunal <> '*' OR comarca IS NULL)
);
CREATE INDEX calendario_busca ON calendario (tribunal, data);

CREATE TABLE calendario_cobertura (
    tribunal       text NOT NULL,
    comarca        text NOT NULL DEFAULT '',
    ano            integer NOT NULL,
    conferido_por  bigint NOT NULL REFERENCES usuarios(id),
    conferido_em   date NOT NULL,
    PRIMARY KEY (tribunal, comarca, ano)
);
COMMENT ON COLUMN calendario_cobertura.comarca IS 'Vazio para o tribunal sem feriados municipais (ex.: 2º grau).';

CREATE TABLE sugestoes_ia (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    publicacao_id     bigint REFERENCES publicacoes(id),
    movimentacao_id   bigint REFERENCES movimentacoes(id),
    tipo_ato          text,
    resumo            text,
    providencia       text,
    prazo_legal_id    bigint REFERENCES prazos_legais(id),
    modelo_sugerido   text,
    confianca         numeric(3, 2) CHECK (confianca BETWEEN 0 AND 1),
    modelo_ia         text NOT NULL,
    versao_prompt     text NOT NULL,
    criada_em         timestamptz NOT NULL DEFAULT now(),
    CHECK ((publicacao_id IS NULL) <> (movimentacao_id IS NULL)),
    CHECK (movimentacao_id IS NULL OR prazo_legal_id IS NULL)
);
COMMENT ON TABLE sugestoes_ia IS 'Movimentação sem publicação não recebe prazo legal (plano, Seções 5.4 e 6.2).';

CREATE TABLE prazos (
    id                          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    processo_id                 bigint NOT NULL REFERENCES processos(id),
    publicacao_id               bigint NOT NULL REFERENCES publicacoes(id),
    prazo_legal_id              bigint REFERENCES prazos_legais(id),
    dias                        integer NOT NULL CHECK (dias > 0),
    multiplicador               smallint NOT NULL DEFAULT 1 CHECK (multiplicador IN (1, 2)),
    data_publicacao             date NOT NULL,
    data_inicio                 date NOT NULL,
    data_fatal                  date NOT NULL,
    data_fatal_com_prorrogacao  date NOT NULL,
    data_interna                date NOT NULL,
    calendario_conferido        boolean NOT NULL,
    memoria_calculo             jsonb NOT NULL,
    situacao                    text NOT NULL DEFAULT 'sugerido'
                                CHECK (situacao IN ('sugerido', 'confirmado', 'cumprido', 'cancelado')),
    aprovado_por                bigint REFERENCES usuarios(id),
    aprovado_em                 timestamptz,
    CHECK (data_inicio > data_publicacao),
    CHECK (data_fatal >= data_inicio),
    CHECK (data_fatal_com_prorrogacao >= data_fatal),
    CHECK (data_interna <= data_fatal),
    CHECK (situacao = 'sugerido' OR (aprovado_por IS NOT NULL AND aprovado_em IS NOT NULL))
);
COMMENT ON COLUMN prazos.data_fatal IS 'Data de controle, sem prorrogação por indisponibilidade (motor de prazos).';

-- Tarefas, minutas e protocolos

CREATE TABLE regras_distribuicao (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tipo_ato     text,
    tribunal     text,
    cliente_id   bigint REFERENCES clientes(id),
    responsavel  bigint NOT NULL REFERENCES usuarios(id),
    revisor      bigint NOT NULL REFERENCES usuarios(id)
);

CREATE TABLE tarefas (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    processo_id         bigint REFERENCES processos(id),
    cliente_id          bigint REFERENCES clientes(id),
    prazo_id            bigint REFERENCES prazos(id),
    origem              text NOT NULL CHECK (origem IN ('publicacao', 'movimentacao', 'financeiro', 'atendimento', 'manual')),
    tipo                text NOT NULL CHECK (tipo IN ('prazo_processual', 'interna')),
    titulo              text NOT NULL,
    responsavel         bigint REFERENCES usuarios(id),
    revisor             bigint REFERENCES usuarios(id),
    situacao            text NOT NULL DEFAULT 'a_fazer'
                        CHECK (situacao IN ('a_fazer', 'em_elaboracao', 'conferencia_1', 'pronta_protocolo',
                                            'conferencia_2', 'protocolada', 'concluida', 'cancelada')),
    checklist           jsonb NOT NULL DEFAULT '[]'::jsonb,
    vencimento_interno  date,
    criada_em           timestamptz NOT NULL DEFAULT now(),
    CHECK (processo_id IS NOT NULL OR cliente_id IS NOT NULL),
    CHECK ((tipo = 'prazo_processual') = (prazo_id IS NOT NULL))
);
CREATE INDEX tarefas_painel ON tarefas (situacao, vencimento_interno);

CREATE TABLE modelos_peticao (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tipo           text NOT NULL,
    rito           text,
    versao         integer NOT NULL DEFAULT 1,
    docx_drive_id  text NOT NULL,
    revisado_em    date NOT NULL,
    UNIQUE (tipo, rito, versao)
);

CREATE TABLE referencias_conferidas (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tipo             text NOT NULL CHECK (tipo IN ('sumula', 'tema', 'precedente', 'lei', 'doutrina')),
    identificacao    text NOT NULL UNIQUE,
    ementa_trecho    text NOT NULL,
    link_oficial     text NOT NULL,
    conferido_em     date NOT NULL,
    conferido_por    bigint NOT NULL REFERENCES usuarios(id)
);

CREATE TABLE minutas (
    id                   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tarefa_id            bigint NOT NULL REFERENCES tarefas(id),
    modelo_id            bigint REFERENCES modelos_peticao(id),
    versao               integer NOT NULL DEFAULT 1,
    docx_drive_id        text NOT NULL,
    pdf_drive_id         text,
    pendencias_conferir  integer NOT NULL DEFAULT 0 CHECK (pendencias_conferir >= 0),
    aprovado_por         bigint REFERENCES usuarios(id),
    aprovado_em          timestamptz,
    UNIQUE (tarefa_id, versao),
    CONSTRAINT minuta_aprovada_sem_pendencias CHECK (aprovado_em IS NULL OR pendencias_conferir = 0)
);
COMMENT ON CONSTRAINT minuta_aprovada_sem_pendencias ON minutas IS 'Minuta com [CONFERIR] pendente não pode ser aprovada (plano, Seção 9.3).';

CREATE TABLE protocolos (
    id                    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    minuta_id             bigint NOT NULL REFERENCES minutas(id),
    tribunal              text NOT NULL,
    nivel                 smallint NOT NULL CHECK (nivel IN (1, 2, 3)),
    situacao              text NOT NULL DEFAULT 'preparado' CHECK (situacao IN ('preparado', 'conferido', 'protocolado')),
    captura_tela_id       text,
    comprovante_drive_id  text,
    protocolado_em        timestamptz,
    CHECK (situacao <> 'protocolado' OR protocolado_em IS NOT NULL)
);
COMMENT ON TABLE protocolos IS 'O protocolo é sempre ato manual do advogado; o sistema só prepara (plano, Seção 8.5).';

CREATE TABLE audiencias (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    processo_id      bigint NOT NULL REFERENCES processos(id),
    data_hora        timestamptz NOT NULL,
    tipo             text NOT NULL,
    local_ou_link    text,
    google_event_id  text UNIQUE
);

CREATE TABLE sessoes_tribunal (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sistema       text NOT NULL,
    tribunal      text NOT NULL,
    situacao      text NOT NULL CHECK (situacao IN ('valida', 'expirada')),
    ultimo_login  timestamptz,
    expira_em     timestamptz,
    UNIQUE (sistema, tribunal)
);
COMMENT ON TABLE sessoes_tribunal IS 'Sem senhas nem segredos de segundo fator (plano, Seção 17.1).';

-- Financeiro

CREATE TABLE cobrancas (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    contrato_id       bigint NOT NULL REFERENCES contratos_honorarios(id),
    asaas_payment_id  text UNIQUE,
    vencimento        date NOT NULL,
    valor             numeric(12, 2) NOT NULL CHECK (valor > 0),
    situacao          text NOT NULL DEFAULT 'preparada'
                      CHECK (situacao IN ('preparada', 'emitida', 'confirmada', 'recebida', 'vencida', 'cancelada')),
    boleto_drive_id   text,
    aprovada_por      bigint REFERENCES usuarios(id),
    CHECK (situacao IN ('preparada', 'cancelada') OR aprovada_por IS NOT NULL)
);

CREATE TABLE eventos_webhook (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    origem       text NOT NULL CHECK (origem IN ('asaas', 'chatwoot', 'google')),
    id_externo   text NOT NULL,
    tipo         text NOT NULL,
    payload      jsonb NOT NULL,
    recebido_em  timestamptz NOT NULL DEFAULT now(),
    processado   boolean NOT NULL DEFAULT false,
    UNIQUE (origem, id_externo)
);
COMMENT ON TABLE eventos_webhook IS 'Deduplicação para processamento idempotente (plano, Seção 11.2).';

-- Atendimento e envios

CREATE TABLE resumos_cliente (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    processo_id   bigint NOT NULL REFERENCES processos(id),
    texto         text NOT NULL,
    aprovado_por  bigint REFERENCES usuarios(id),
    aprovado_em   timestamptz,
    enviado_em    timestamptz,
    CHECK (enviado_em IS NULL OR aprovado_em IS NOT NULL)
);

CREATE TABLE modelos_mensagem (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    canal         text NOT NULL CHECK (canal IN ('whatsapp', 'email')),
    finalidade    text NOT NULL,
    texto         text NOT NULL,
    aprovado_por  bigint REFERENCES usuarios(id),
    aprovado_em   timestamptz,
    revogado_em   timestamptz
);
COMMENT ON TABLE modelos_mensagem IS 'Mensagens padronizadas, categoria (b) da Seção 17.3 do plano.';

CREATE TABLE envios (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    canal           text NOT NULL CHECK (canal IN ('email', 'whatsapp')),
    destinatario    text NOT NULL,
    conteudo        text NOT NULL,
    anexos          jsonb NOT NULL DEFAULT '[]'::jsonb,
    relatorio_pie   jsonb NOT NULL,
    autorizado_por  bigint REFERENCES usuarios(id),
    autorizado_em   timestamptz,
    enviado_em      timestamptz,
    CHECK (enviado_em IS NULL OR (autorizado_por IS NOT NULL AND autorizado_em IS NOT NULL))
);
COMMENT ON TABLE envios IS 'Envios individuais, categoria (a) da Seção 17.3: nenhum sai sem autorização registrada.';

-- Auditoria

CREATE TABLE auditoria (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    usuario_id   bigint REFERENCES usuarios(id),
    acao         text NOT NULL,
    entidade     text NOT NULL,
    entidade_id  bigint,
    antes        jsonb,
    depois       jsonb,
    data_hora    timestamptz NOT NULL DEFAULT now()
);

CREATE FUNCTION auditoria_imutavel() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'A trilha de auditoria é imutável (plano, Seção 17.2).';
END;
$$;

CREATE TRIGGER auditoria_sem_alteracao
    BEFORE UPDATE OR DELETE ON auditoria
    FOR EACH ROW EXECUTE FUNCTION auditoria_imutavel();

COMMIT;
