-- Importação da carteira do protótipo e ligação com a captura do DJEN
-- (plano, Seção 23.4). Pressupõe 0001_inicial.sql.
-- Decisão do titular em 11/10/2026: o CPF ou CNPJ dos clientes será
-- informado depois; até lá, o campo fica vazio.

BEGIN;

-- 1. Clientes

ALTER TABLE sgj.clientes ALTER COLUMN cpf_cnpj DROP NOT NULL;
ALTER TABLE sgj.clientes ALTER COLUMN tipo DROP NOT NULL;
ALTER TABLE sgj.clientes ADD CONSTRAINT clientes_tipo_conforme_documento
    CHECK (cpf_cnpj IS NULL OR tipo IS NOT DISTINCT FROM CASE length(cpf_cnpj) WHEN 11 THEN 'PF' ELSE 'PJ' END);
ALTER TABLE sgj.clientes ADD COLUMN provisorio boolean NOT NULL DEFAULT false;
COMMENT ON COLUMN sgj.clientes.tipo IS 'Obrigatório, e conforme o documento, quando o CPF ou CNPJ for informado.';
COMMENT ON COLUMN sgj.clientes.provisorio IS 'Registro técnico que reúne os casos de cliente ainda não identificado.';

-- 2. Processos: o sistema só é registrado com a fonte da confirmação
--    (plano, Seção 23.6, decisão 1).

ALTER TABLE sgj.processos ALTER COLUMN sistema DROP NOT NULL;
ALTER TABLE sgj.processos ADD COLUMN sistema_fonte text CHECK (sistema_fonte IN ('djen', 'robo', 'titular'));
ALTER TABLE sgj.processos ADD CONSTRAINT processos_sistema_com_fonte
    CHECK ((sistema IS NULL) = (sistema_fonte IS NULL));
COMMENT ON COLUMN sgj.processos.tribunal IS 'Tribunal de origem, identificado pelo segmento J.TR da numeração única.';
COMMENT ON COLUMN sgj.processos.sistema IS
    'Nulo até a confirmação. Reverificar periodicamente: TJSP e TJPR mantêm acervo em sistema antigo.';
COMMENT ON COLUMN sgj.processos.sistema_fonte IS
    'djen: endereço do documento na comunicação mais recente; robo: conferido no sistema do tribunal; titular: informado pelo titular.';

-- 3. Publicações: dados da comunicação no DJEN

ALTER TABLE sgj.publicacoes
    ADD COLUMN djen_id bigint UNIQUE,
    ADD COLUMN tribunal text,
    ADD COLUMN orgao text,
    ADD COLUMN classe text,
    ADD COLUMN tipo_documento text,
    ADD COLUMN link text;
CREATE INDEX publicacoes_npu_data ON sgj.publicacoes (npu, data_disponibilizacao);
COMMENT ON COLUMN sgj.publicacoes.hash IS
    'Hash da comunicação no DJEN. Publicação do protótipo ainda sem correspondência no DJEN: identificador do protótipo, com o prefixo "prototipo:".';
COMMENT ON COLUMN sgj.publicacoes.tribunal IS
    'Tribunal que publicou (siglaTribunal do DJEN), cujo calendário rege a contagem; pode diferir do tribunal de origem do processo.';

-- 4. Tarefas de conferência do cadastro importado

ALTER TABLE sgj.tarefas DROP CONSTRAINT tarefas_origem_check;
ALTER TABLE sgj.tarefas ADD CONSTRAINT tarefas_origem_check
    CHECK (origem IN ('publicacao', 'movimentacao', 'financeiro', 'atendimento', 'manual', 'importacao'));

-- 5. Registro da importação: rastreabilidade, repetição sem duplicidade e reversão

CREATE TABLE sgj.importacao_legado (
    origem        text NOT NULL,
    origem_id     text NOT NULL,
    destino       text NOT NULL,
    destino_id    bigint NOT NULL,
    observacoes   jsonb NOT NULL DEFAULT '{}'::jsonb,
    importado_em  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (origem, origem_id, destino)
);
COMMENT ON TABLE sgj.importacao_legado IS
    'Correspondência entre registros do protótipo (esquema public) e do sistema, com os valores de origem não aproveitados.';

-- 6. Funções auxiliares

CREATE FUNCTION sgj.tribunal_da_npu(p_npu text) RETURNS text
LANGUAGE sql IMMUTABLE SET search_path = '' AS $$
    SELECT CASE WHEN length(d) = 20 THEN
        CASE substr(d, 14, 3)
            WHEN '807' THEN 'TJDFT' WHEN '809' THEN 'TJGO' WHEN '811' THEN 'TJMT' WHEN '812' THEN 'TJMS'
            WHEN '816' THEN 'TJPR' WHEN '819' THEN 'TJRJ' WHEN '821' THEN 'TJRS' WHEN '824' THEN 'TJSC'
            WHEN '826' THEN 'TJSP' WHEN '401' THEN 'TRF1' WHEN '404' THEN 'TRF4'
            WHEN '504' THEN 'TRT4' WHEN '512' THEN 'TRT12'
        END
    END
    FROM (SELECT regexp_replace(coalesce(p_npu, ''), '\D', '', 'g') AS d) s
$$;
COMMENT ON FUNCTION sgj.tribunal_da_npu(text) IS
    'Tribunal pelo segmento J.TR da numeração única. Tabela restrita aos códigos conferidos na carteira real em 11/10/2026 '
    '(coincidência integral com o tribunal informado no protótipo e com a sigla das comunicações do DJEN); código fora dela retorna nulo.';

CREATE FUNCTION sgj.chave_nome(p_nome text) RETURNS text
LANGUAGE sql IMMUTABLE SET search_path = '' AS $$
    SELECT nullif(translate(lower(btrim(regexp_replace(coalesce(p_nome, ''), '\s+', ' ', 'g'))),
                            'áàâãäéèêëíìîïóòôõöúùûüçñ', 'aaaaaeeeeiiiiooooouuuucn'), '')
$$;
COMMENT ON FUNCTION sgj.chave_nome(text) IS 'Chave de comparação de nomes, indiferente a maiúsculas, acentos e espaços.';

CREATE FUNCTION sgj.chave_texto(p_texto text) RETURNS text
LANGUAGE sql IMMUTABLE SET search_path = '' AS $$
    SELECT md5(regexp_replace(lower(coalesce(p_texto, '')), '[^a-z0-9]', '', 'g'))
$$;
COMMENT ON FUNCTION sgj.chave_texto(text) IS
    'Chave de comparação de textos, indiferente a formatação, pontuação e letras acentuadas.';

-- Texto legível a partir do HTML das comunicações: remove cabeçalho, estilos e
-- marcações, converte quebras de linha e entidades. Texto sem marcação passa
-- apenas pela conversão de entidades e pela limpeza de espaços.
CREATE FUNCTION sgj.texto_de_html(p_html text) RETURNS text
LANGUAGE plpgsql IMMUTABLE SET search_path = '' AS $$
DECLARE
    t text := coalesce(p_html, '');
    entidades constant text[] := ARRAY[
        'nbsp', ' ', 'emsp', ' ', 'ensp', ' ', 'thinsp', ' ',
        'lt', '<', 'gt', '>', 'quot', '"', 'apos', '''',
        'ldquo', '“', 'rdquo', '”', 'lsquo', '‘', 'rsquo', '’', 'laquo', '«', 'raquo', '»',
        'ndash', '–', 'mdash', '—', 'hellip', '…', 'bull', '•', 'middot', '·',
        'sect', '§', 'para', '¶', 'deg', '°', 'ordm', 'º', 'ordf', 'ª', 'acute', '´',
        'copy', '©', 'reg', '®', 'euro', '€',
        'aacute', 'á', 'Aacute', 'Á', 'agrave', 'à', 'Agrave', 'À', 'acirc', 'â', 'Acirc', 'Â',
        'atilde', 'ã', 'Atilde', 'Ã', 'auml', 'ä', 'Auml', 'Ä',
        'eacute', 'é', 'Eacute', 'É', 'egrave', 'è', 'Egrave', 'È', 'ecirc', 'ê', 'Ecirc', 'Ê',
        'euml', 'ë', 'Euml', 'Ë',
        'iacute', 'í', 'Iacute', 'Í', 'igrave', 'ì', 'Igrave', 'Ì', 'icirc', 'î', 'Icirc', 'Î',
        'iuml', 'ï', 'Iuml', 'Ï',
        'oacute', 'ó', 'Oacute', 'Ó', 'ograve', 'ò', 'Ograve', 'Ò', 'ocirc', 'ô', 'Ocirc', 'Ô',
        'otilde', 'õ', 'Otilde', 'Õ', 'ouml', 'ö', 'Ouml', 'Ö',
        'uacute', 'ú', 'Uacute', 'Ú', 'ugrave', 'ù', 'Ugrave', 'Ù', 'ucirc', 'û', 'Ucirc', 'Û',
        'uuml', 'ü', 'Uuml', 'Ü',
        'ccedil', 'ç', 'Ccedil', 'Ç', 'ntilde', 'ñ', 'Ntilde', 'Ñ'
    ];
    i integer;
    m text[];
    cp integer;
BEGIN
    IF t ~ '<[A-Za-z!/]' THEN
        -- No HTML, a quebra de linha do código-fonte é apenas espaço.
        t := regexp_replace(t, '\s+', ' ', 'g');
        t := regexp_replace(t, '<!--.*?-->', '', 'g');
        t := regexp_replace(t, '<head[ >].*?</head\s*>', '', 'gi');
        t := regexp_replace(t, '<style[ >].*?</style\s*>', '', 'gi');
        t := regexp_replace(t, '<script[ >].*?</script\s*>', '', 'gi');
        t := regexp_replace(t, '<br\s*/?>', E'\n', 'gi');
        t := regexp_replace(t, '</(p|div|li|tr|table|h[1-6]|section|article|header|footer|center)\s*>|<hr[^>]*>', E'\n', 'gi');
        t := regexp_replace(t, '</t[dh]\s*>', ' ', 'gi');
        t := regexp_replace(t, '<[^>]*>', '', 'g');
    END IF;
    FOR i IN 1 .. array_length(entidades, 1) / 2 LOOP
        t := replace(t, '&' || entidades[2 * i - 1] || ';', entidades[2 * i]);
    END LOOP;
    LOOP
        m := regexp_match(t, '&#([xX][0-9A-Fa-f]{1,6}|[0-9]{1,7});');
        EXIT WHEN m IS NULL;
        cp := CASE WHEN m[1] ~ '^[xX]' THEN ('x' || lpad(substr(m[1], 2), 8, '0'))::bit(32)::integer
                   ELSE m[1]::integer END;
        t := replace(t, '&#' || m[1] || ';',
                     CASE WHEN cp BETWEEN 1 AND 1114111 AND cp NOT BETWEEN 55296 AND 57343 THEN chr(cp) ELSE '' END);
    END LOOP;
    t := replace(t, '&amp;', '&');
    t := regexp_replace(t, '[ \t\r\f\u00a0]+', ' ', 'g');
    t := regexp_replace(t, ' ?\n ?', E'\n', 'g');
    t := regexp_replace(t, '\n{3,}', E'\n\n', 'g');
    RETURN nullif(btrim(t, E' \n'), '');
END;
$$;

-- 7. Importação da carteira do protótipo (public.processos e
--    public.processos_movimentacoes). Repetível: importa apenas o que ainda não
--    consta de sgj.importacao_legado; não altera nenhuma tabela do protótipo.

CREATE FUNCTION sgj.importar_carteira_prototipo() RETURNS jsonb
LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE
    v_titular            bigint;
    v_provisorio         bigint;
    v_ignorados          jsonb;
    v_clientes           integer := 0;
    v_casos              integer := 0;
    v_processos          integer := 0;
    v_tarefas            integer := 0;
    v_publicacoes        integer := 0;
    v_publicacoes_antes  integer := 0;
BEGIN
    SELECT id INTO v_titular FROM sgj.usuarios WHERE perfil = 'titular' AND ativo ORDER BY id LIMIT 1;
    IF v_titular IS NULL THEN
        RAISE EXCEPTION 'Nenhum titular ativo em sgj.usuarios.';
    END IF;

    DROP TABLE IF EXISTS pg_temp.imp_origem, pg_temp.imp, pg_temp.imp_clientes, pg_temp.imp_djen, pg_temp.imp_pub;

    -- 7.1 Processos do protótipo ainda não importados
    CREATE TEMP TABLE imp_origem ON COMMIT DROP AS
    SELECT p.id::text AS legado_id,
           regexp_replace(coalesce(p.numero_cnj, ''), '\D', '', 'g') AS npu,
           p.numero_cnj AS npu_original,
           sgj.tribunal_da_npu(p.numero_cnj) AS tribunal,
           nullif(btrim(regexp_replace(coalesce(p.nome, ''), '\s+', ' ', 'g')), '') AS nome,
           nullif(btrim(p.tipo_acao), '') AS tipo_acao,
           nullif(btrim(p.parte_contraria), '') AS parte_contraria,
           nullif(btrim(p.apelido), '') AS apelido,
           p.area AS area_original,
           p.tribunal AS tribunal_original,
           p.status AS status_original,
           p.fase AS fase_original,
           p.encerrado_em,
           nullif(btrim(p.drive_folder_trabalho_path), '') AS pasta_local,
           p.criado_em
    FROM public.processos p
    WHERE NOT EXISTS (SELECT 1 FROM sgj.importacao_legado l
                      WHERE l.origem = 'public.processos' AND l.origem_id = p.id::text AND l.destino = 'sgj.processos');

    SELECT coalesce(jsonb_agg(jsonb_build_object('processo', o.npu_original, 'motivo', o.motivo) ORDER BY o.npu_original), '[]'::jsonb)
    INTO v_ignorados
    FROM (SELECT x.npu_original,
                 CASE WHEN length(x.npu) <> 20 THEN 'numeração inválida'
                      WHEN x.tribunal IS NULL THEN 'tribunal não reconhecido pelo segmento J.TR'
                      WHEN EXISTS (SELECT 1 FROM sgj.processos s WHERE s.npu = x.npu) THEN 'processo já cadastrado no sistema'
                      WHEN count(*) OVER (PARTITION BY x.npu) > 1 THEN 'numeração repetida no protótipo'
                 END AS motivo
          FROM pg_temp.imp_origem x) o
    WHERE o.motivo IS NOT NULL;

    CREATE TEMP TABLE imp ON COMMIT DROP AS
    SELECT o.*,
           sgj.chave_nome(o.nome) AS chave_cliente,
           CASE WHEN lower(btrim(o.area_original)) IN ('civel_bancario', 'bancario', 'bancário') THEN 'bancario'
                WHEN lower(btrim(o.area_original)) ~ '^c[ií]vel' THEN 'civel'
                WHEN lower(btrim(o.area_original)) = 'trabalhista' THEN 'trabalhista'
                WHEN lower(btrim(o.area_original)) IN ('previdenciario', 'previdenciário') THEN 'previdenciario'
                WHEN lower(btrim(o.area_original)) = 'criminal' THEN 'criminal'
           END AS area,
           CASE WHEN o.tipo_acao ~* '\((r[ée]u?s?|re|executad[oa]s?)\)' THEN 'passivo' END AS polo,
           coalesce(o.tipo_acao ~* 'sigilos', false) AS segredo,
           CASE WHEN o.fase_original = 'encerrado' OR o.encerrado_em IS NOT NULL THEN 'encerrado' ELSE 'ativo' END AS situacao_caso,
           coalesce(o.tipo_acao, o.apelido,
                    'Processo ' || substr(o.npu, 1, 7) || '-' || substr(o.npu, 8, 2) || '.' || substr(o.npu, 10, 4) || '.'
                    || substr(o.npu, 14, 1) || '.' || substr(o.npu, 15, 2) || '.' || substr(o.npu, 17, 4))
               || coalesce(' x ' || o.parte_contraria, '') AS titulo,
           row_number() OVER (ORDER BY o.criado_em, o.npu) AS ordem,
           NULL::text AS sistema, NULL::smallint AS grau, NULL::text AS comarca, NULL::text AS orgao,
           NULL::text AS classe, NULL::jsonb AS evidencia, NULL::text AS caso_codigo,
           NULL::bigint AS cliente_id, NULL::bigint AS caso_id, NULL::bigint AS processo_id
    FROM pg_temp.imp_origem o
    WHERE length(o.npu) = 20
      AND o.tribunal IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM sgj.processos s WHERE s.npu = o.npu)
      AND (SELECT count(*) FROM pg_temp.imp_origem o2 WHERE o2.npu = o.npu) = 1;

    -- 7.2 Dados verificáveis nas comunicações do DJEN já capturadas
    CREATE TEMP TABLE imp_djen (npu text, id bigint, data date, tribunal text, host text, orgao text, classe text) ON COMMIT DROP;
    IF to_regclass('djen.comunicacao') IS NOT NULL THEN
        INSERT INTO pg_temp.imp_djen
        SELECT regexp_replace(coalesce(c.processo, ''), '\D', '', 'g'), c.id, c.data_disponibilizacao, c.tribunal,
               lower(substring(nullif(c.link, '') FROM '^https?://([^/:?#]+)')), nullif(btrim(c.orgao), ''), nullif(btrim(c.classe), '')
        FROM djen.comunicacao c
        WHERE c.data_disponibilizacao IS NOT NULL
          AND regexp_replace(coalesce(c.processo, ''), '\D', '', 'g') IN (SELECT npu FROM pg_temp.imp);
    END IF;

    -- Sistema: endereço do documento na comunicação mais recente (o STJ publica com a numeração de origem).
    UPDATE pg_temp.imp i SET sistema = ev.sistema, evidencia = ev.evidencia
    FROM (SELECT DISTINCT ON (d.npu) d.npu,
                 CASE WHEN d.tribunal = 'STJ' THEN 'cpe_stj'
                      WHEN d.host LIKE 'eproc%' THEN 'eproc'
                      WHEN d.host LIKE 'pje%' THEN 'pje'
                      WHEN d.host LIKE 'esaj%' THEN 'esaj'
                      WHEN d.host LIKE 'projudi%' THEN 'projudi'
                 END AS sistema,
                 jsonb_build_object('comunicacao_djen', d.id, 'data', d.data, 'tribunal', d.tribunal, 'endereco', d.host) AS evidencia
          FROM pg_temp.imp_djen d
          WHERE d.tribunal = 'STJ' OR d.host IS NOT NULL
          ORDER BY d.npu, d.data DESC, d.id DESC) ev
    WHERE ev.npu = i.npu;

    -- Grau: órgão da comunicação mais recente; na falta, endereço do eproc.
    UPDATE pg_temp.imp i SET grau = ev.grau
    FROM (SELECT DISTINCT ON (d.npu) d.npu,
                 (CASE WHEN d.tribunal = 'STJ' THEN 3
                       WHEN d.orgao ~* 'turma recursal' THEN NULL
                       WHEN d.orgao ~* '(vara|juizado|upj)' THEN 1
                       WHEN d.orgao ~* '(c[aâ]mara|gab\.|gabinete)' THEN 2
                       WHEN d.host LIKE 'eproc1g.%' THEN 1
                       WHEN d.host LIKE 'eproc2g.%' THEN 2
                  END)::smallint AS grau
          FROM pg_temp.imp_djen d
          ORDER BY d.npu, d.data DESC, d.id DESC) ev
    WHERE ev.npu = i.npu;

    -- Comarca: órgão de primeiro grau identificado como "Comarca de".
    UPDATE pg_temp.imp i SET comarca = ev.comarca
    FROM (SELECT DISTINCT ON (d.npu) d.npu, btrim(substring(d.orgao FROM 'Comarca de (.+)$')) AS comarca
          FROM pg_temp.imp_djen d
          WHERE d.orgao ~ 'Comarca de .'
          ORDER BY d.npu, d.data DESC, d.id DESC) ev
    WHERE ev.npu = i.npu;

    -- Órgão e classe: comunicação mais recente do próprio tribunal de origem.
    UPDATE pg_temp.imp i SET orgao = ev.orgao, classe = ev.classe
    FROM (SELECT DISTINCT ON (d.npu, d.tribunal) d.npu, d.tribunal, d.orgao, upper(d.classe) AS classe
          FROM pg_temp.imp_djen d
          ORDER BY d.npu, d.tribunal, d.data DESC, d.id DESC) ev
    WHERE ev.npu = i.npu AND ev.tribunal = i.tribunal;

    -- 7.3 Clientes: um por nome; processos sem nome ficam no cliente provisório.
    IF EXISTS (SELECT 1 FROM pg_temp.imp WHERE chave_cliente IS NULL) THEN
        SELECT id INTO v_provisorio FROM sgj.clientes WHERE provisorio ORDER BY id LIMIT 1;
        IF v_provisorio IS NULL THEN
            INSERT INTO sgj.clientes (codigo, nome, provisorio)
            VALUES ('C0000', 'Cliente a identificar', true)
            RETURNING id INTO v_provisorio;
        END IF;
        UPDATE pg_temp.imp SET cliente_id = v_provisorio WHERE chave_cliente IS NULL;
    END IF;

    CREATE TEMP TABLE imp_clientes ON COMMIT DROP AS
    WITH variantes AS (
        SELECT chave_cliente, nome, count(*) AS n, min(ordem) AS primeira, (nome <> upper(nome)) AS tem_minusculas
        FROM pg_temp.imp WHERE chave_cliente IS NOT NULL
        GROUP BY chave_cliente, nome
    )
    SELECT DISTINCT ON (v.chave_cliente) v.chave_cliente, v.nome,
           (SELECT min(i2.ordem) FROM pg_temp.imp i2 WHERE i2.chave_cliente = v.chave_cliente) AS ordem,
           (SELECT c.id FROM sgj.clientes c WHERE NOT c.provisorio AND sgj.chave_nome(c.nome) = v.chave_cliente
            ORDER BY c.id LIMIT 1) AS cliente_id
    FROM variantes v
    ORDER BY v.chave_cliente, v.n DESC, v.tem_minusculas DESC, v.primeira;

    WITH base AS (
        SELECT coalesce(max(substr(codigo, 2)::integer), 0) AS n FROM sgj.clientes WHERE codigo ~ '^C[0-9]+$'
    ), numerados AS (
        SELECT ic.chave_cliente, ic.nome, base.n + row_number() OVER (ORDER BY ic.ordem) AS n
        FROM pg_temp.imp_clientes ic, base
        WHERE ic.cliente_id IS NULL
    ), novos AS (
        INSERT INTO sgj.clientes (codigo, nome)
        SELECT 'C' || lpad(n::text, greatest(4, length(n::text)), '0'), nome FROM numerados
        RETURNING id, nome
    )
    UPDATE pg_temp.imp_clientes ic SET cliente_id = novos.id
    FROM novos WHERE ic.cliente_id IS NULL AND ic.nome = novos.nome;
    GET DIAGNOSTICS v_clientes = ROW_COUNT;

    UPDATE pg_temp.imp i SET cliente_id = ic.cliente_id
    FROM pg_temp.imp_clientes ic WHERE ic.chave_cliente = i.chave_cliente;

    -- 7.4 Casos: um por processo, na ordem de cadastro no protótipo.
    UPDATE pg_temp.imp i SET caso_codigo = 'K' || lpad(r.n::text, greatest(4, length(r.n::text)), '0')
    FROM (SELECT legado_id,
                 (SELECT coalesce(max(substr(codigo, 2)::integer), 0) FROM sgj.casos WHERE codigo ~ '^K[0-9]+$')
                 + row_number() OVER (ORDER BY ordem) AS n
          FROM pg_temp.imp) r
    WHERE r.legado_id = i.legado_id;

    INSERT INTO sgj.casos (codigo, cliente_id, titulo, area, situacao)
    SELECT caso_codigo, cliente_id, titulo, area, situacao_caso FROM pg_temp.imp ORDER BY ordem;
    GET DIAGNOSTICS v_casos = ROW_COUNT;
    UPDATE pg_temp.imp i SET caso_id = c.id FROM sgj.casos c WHERE c.codigo = i.caso_codigo;

    -- 7.5 Processos
    INSERT INTO sgj.processos (caso_id, npu, tribunal, comarca, sistema, sistema_fonte, grau,
                               orgao_julgador, classe, polo, segredo_justica)
    SELECT caso_id, npu, tribunal, comarca, sistema, CASE WHEN sistema IS NOT NULL THEN 'djen' END, grau,
           orgao, classe, polo, segredo
    FROM pg_temp.imp ORDER BY ordem;
    GET DIAGNOSTICS v_processos = ROW_COUNT;
    UPDATE pg_temp.imp i SET processo_id = p.id FROM sgj.processos p WHERE p.npu = i.npu;

    INSERT INTO sgj.importacao_legado (origem, origem_id, destino, destino_id, observacoes)
    SELECT 'public.processos', legado_id, 'sgj.processos', processo_id,
           jsonb_strip_nulls(jsonb_build_object(
               'tribunal', tribunal_original, 'area', area_original, 'situacao', status_original,
               'nome', nome, 'apelido', apelido, 'tipo_acao', tipo_acao, 'parte_contraria', parte_contraria,
               'pasta_local', pasta_local, 'evidencia_djen', evidencia))
    FROM pg_temp.imp
    UNION ALL
    SELECT 'public.processos', legado_id, 'sgj.casos', caso_id, '{}'::jsonb FROM pg_temp.imp
    UNION ALL
    SELECT 'public.processos', legado_id, 'sgj.clientes', cliente_id, '{}'::jsonb FROM pg_temp.imp;

    -- 7.6 Tarefa interna de conferência por processo (plano, Seção 23.4)
    INSERT INTO sgj.tarefas (processo_id, origem, tipo, titulo, responsavel, checklist)
    SELECT i.processo_id, 'importacao', 'interna', 'Conferir o cadastro importado do protótipo', v_titular,
           (SELECT coalesce(jsonb_agg(jsonb_build_object('item', x.item, 'concluido', false) ORDER BY x.ordem), '[]'::jsonb)
            FROM (VALUES
                (1, CASE WHEN i.status_original = 'revisar'
                         THEN 'Revisar o cadastro: o processo estava com a situação "revisar" no protótipo' END),
                (2, CASE WHEN i.chave_cliente IS NULL THEN 'Identificar o cliente e vincular o caso a ele'
                         WHEN i.nome ~* '\s(x|vs\.?)\s|[()/]|\s-\s|\s(e|&)\s'
                         THEN 'Conferir o nome do cliente: o registro de origem contém anotação ou mais de uma pessoa' END),
                (3, CASE WHEN i.area IS NULL THEN 'Definir a área do caso'
                         || coalesce(' (no protótipo: ' || nullif(btrim(i.area_original), '') || ')', '') END),
                (4, CASE WHEN i.sistema IS NULL THEN 'Confirmar o sistema do processo' END),
                (5, CASE WHEN i.grau IS NULL OR i.comarca IS NULL THEN 'Conferir o grau e a comarca' END),
                (6, CASE WHEN i.polo IS NULL THEN 'Conferir o polo do cliente' END),
                (7, CASE WHEN NOT i.segredo
                         THEN 'Confirmar se o processo tramita em segredo de justiça (a IA fica desabilitada para processos sigilosos)' END),
                (8, 'Vincular a pasta do processo no Drive'
                    || CASE WHEN i.pasta_local IS NOT NULL THEN ' (há pasta local registrada no protótipo)' ELSE '' END)
            ) AS x(ordem, item)
            WHERE x.item IS NOT NULL)
    FROM pg_temp.imp i ORDER BY i.ordem;
    GET DIAGNOSTICS v_tarefas = ROW_COUNT;

    -- 7.7 Publicações capturadas pelo protótipo, sem duplicar as já registradas
    --     (mesmo processo, mesma data de disponibilização e mesmo texto).
    CREATE TEMP TABLE imp_pub ON COMMIT DROP AS
    SELECT m.id::text AS legado_id,
           regexp_replace(coalesce(m.numero_cnj, ''), '\D', '', 'g') AS npu,
           m.data_disponibilizacao,
           nullif(btrim(m.tipo), '') AS tipo,
           coalesce(sgj.texto_de_html(m.texto), '(publicação sem texto no protótipo)') AS texto,
           'prototipo:' || coalesce(nullif(m.hash_dedup, ''), m.id::text) AS hash,
           jsonb_strip_nulls(jsonb_build_object(
               'fonte_captura', m.fonte_captura, 'capturado_em', m.capturado_em, 'sigiloso', m.sigiloso,
               'triagem_ia', m.triagem_ia, 'triagem_ia_em', m.triagem_ia_em, 'triagem_ia_obs', m.triagem_ia_obs,
               'minuta', m.minuta_path)) AS observacoes,
           NULL::bigint AS publicacao_id
    FROM public.processos_movimentacoes m
    WHERE m.data_disponibilizacao IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM sgj.importacao_legado l
                      WHERE l.origem = 'public.processos_movimentacoes' AND l.origem_id = m.id::text);

    UPDATE pg_temp.imp_pub ip SET publicacao_id = (
        SELECT p.id FROM sgj.publicacoes p
        WHERE p.npu = ip.npu AND p.data_disponibilizacao = ip.data_disponibilizacao
          AND sgj.chave_texto(p.texto) = sgj.chave_texto(ip.texto)
        ORDER BY p.id LIMIT 1);
    SELECT count(*) INTO v_publicacoes_antes FROM pg_temp.imp_pub WHERE publicacao_id IS NOT NULL;

    WITH novas AS (
        INSERT INTO sgj.publicacoes (processo_id, npu, hash, data_disponibilizacao, tipo_comunicacao, texto)
        SELECT pr.id, ip.npu, ip.hash, ip.data_disponibilizacao, ip.tipo, ip.texto
        FROM pg_temp.imp_pub ip LEFT JOIN sgj.processos pr ON pr.npu = ip.npu
        WHERE ip.publicacao_id IS NULL
        ON CONFLICT (hash) DO NOTHING
        RETURNING id, hash
    )
    UPDATE pg_temp.imp_pub ip SET publicacao_id = novas.id FROM novas WHERE ip.hash = novas.hash;
    GET DIAGNOSTICS v_publicacoes = ROW_COUNT;

    UPDATE pg_temp.imp_pub ip SET publicacao_id = p.id
    FROM sgj.publicacoes p WHERE ip.publicacao_id IS NULL AND p.hash = ip.hash;

    INSERT INTO sgj.importacao_legado (origem, origem_id, destino, destino_id, observacoes)
    SELECT 'public.processos_movimentacoes', legado_id, 'sgj.publicacoes', publicacao_id, observacoes
    FROM pg_temp.imp_pub WHERE publicacao_id IS NOT NULL;

    RETURN jsonb_build_object(
        'processos', v_processos,
        'casos', v_casos,
        'clientes_novos', v_clientes,
        'cliente_provisorio', v_provisorio,
        'processos_com_sistema_pelo_djen', (SELECT count(*) FROM pg_temp.imp WHERE sistema IS NOT NULL),
        'tarefas_de_conferencia', v_tarefas,
        'publicacoes_novas', v_publicacoes,
        'publicacoes_ja_registradas', v_publicacoes_antes,
        'processos_ignorados', v_ignorados);
END;
$$;

-- 8. Ligação com a captura do DJEN (esquema djen, que permanece inalterado).
--    Repetível: cada comunicação entra uma única vez; falha fica registrada em sgj.coletas.

CREATE FUNCTION sgj.sincronizar_djen() RETURNS jsonb
LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE
    v_coleta       bigint;
    v_completadas  integer := 0;
    v_inseridas    integer := 0;
    v_vinculadas   integer := 0;
BEGIN
    INSERT INTO sgj.coletas (fonte) VALUES ('djen') RETURNING id INTO v_coleta;
    BEGIN
        -- Publicação importada do protótipo que corresponde a comunicação capturada
        -- (mesmo processo, mesma data e mesmo texto) recebe os dados oficiais.
        WITH captura AS (
            SELECT c.id, coalesce(nullif(c.raw->>'hash', ''), 'djen:' || c.id) AS hash,
                   regexp_replace(coalesce(c.processo, ''), '\D', '', 'g') AS npu, c.data_disponibilizacao,
                   c.tribunal, c.orgao, c.classe, c.tipo_documento, nullif(c.link, '') AS link,
                   sgj.chave_texto(sgj.texto_de_html(c.texto_html)) AS chave
            FROM djen.comunicacao c
            WHERE NOT EXISTS (SELECT 1 FROM sgj.publicacoes p WHERE p.djen_id = c.id)
        ), candidatos AS (
            SELECT DISTINCT ON (cap.id) cap.*, p.id AS publicacao_id
            FROM captura cap
            JOIN sgj.publicacoes p
              ON p.djen_id IS NULL AND p.npu = cap.npu AND p.data_disponibilizacao = cap.data_disponibilizacao
             AND sgj.chave_texto(p.texto) = cap.chave
            WHERE NOT EXISTS (SELECT 1 FROM sgj.publicacoes x WHERE x.hash = cap.hash)
            ORDER BY cap.id, p.id
        ), pares AS (
            SELECT DISTINCT ON (publicacao_id) * FROM candidatos ORDER BY publicacao_id, id
        )
        UPDATE sgj.publicacoes p
        SET djen_id = pares.id, hash = pares.hash, tribunal = pares.tribunal, orgao = pares.orgao,
            classe = pares.classe, tipo_documento = pares.tipo_documento, link = pares.link
        FROM pares WHERE p.id = pares.publicacao_id;
        GET DIAGNOSTICS v_completadas = ROW_COUNT;

        -- Comunicações novas
        INSERT INTO sgj.publicacoes (processo_id, npu, hash, data_disponibilizacao, tipo_comunicacao, texto,
                                     coleta_id, djen_id, tribunal, orgao, classe, tipo_documento, link)
        SELECT pr.id, s.npu, s.hash, s.data_disponibilizacao, s.tipo_comunicacao,
               coalesce(sgj.texto_de_html(s.texto_html), '(comunicação sem texto)'), v_coleta,
               s.id, s.tribunal, s.orgao, s.classe, s.tipo_documento, s.link
        FROM (SELECT c.id, c.data_disponibilizacao, c.tribunal, c.orgao, c.classe, c.tipo_comunicacao,
                     c.tipo_documento, c.texto_html, nullif(c.link, '') AS link,
                     regexp_replace(coalesce(c.processo, ''), '\D', '', 'g') AS npu,
                     coalesce(nullif(c.raw->>'hash', ''), 'djen:' || c.id) AS hash
              FROM djen.comunicacao c) s
        LEFT JOIN sgj.processos pr ON pr.npu = s.npu
        WHERE s.npu <> '' AND s.data_disponibilizacao IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM sgj.publicacoes p WHERE p.djen_id = s.id OR p.hash = s.hash)
        ORDER BY s.data_disponibilizacao, s.id
        ON CONFLICT DO NOTHING;
        GET DIAGNOSTICS v_inseridas = ROW_COUNT;

        -- Publicações de processos cadastrados depois da captura
        UPDATE sgj.publicacoes p SET processo_id = pr.id
        FROM sgj.processos pr WHERE p.processo_id IS NULL AND pr.npu = p.npu;
        GET DIAGNOSTICS v_vinculadas = ROW_COUNT;

        UPDATE sgj.coletas SET fim = now(), situacao = 'concluida', itens = v_completadas + v_inseridas
        WHERE id = v_coleta;
    EXCEPTION WHEN OTHERS THEN
        UPDATE sgj.coletas SET fim = now(), situacao = 'falhou', erro = SQLERRM WHERE id = v_coleta;
        RETURN jsonb_build_object('coleta', v_coleta, 'situacao', 'falhou', 'erro', SQLERRM);
    END;
    RETURN jsonb_build_object('coleta', v_coleta, 'situacao', 'concluida', 'inseridas', v_inseridas,
                              'completadas', v_completadas, 'vinculadas', v_vinculadas);
END;
$$;

-- 9. Agendamento: dez minutos após a última coleta de cada turno do esquema djen
--    (09h45 e 16h15 UTC). Só onde houver pg_cron.

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN
        PERFORM cron.schedule('sgj-sincronizar-djen', '55 9,16 * * *', 'SELECT sgj.sincronizar_djen()');
    END IF;
END $$;

-- 10. Proteção de acesso dos novos objetos

ALTER TABLE sgj.importacao_legado ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA sgj FROM PUBLIC;

DO $$
DECLARE r text;
BEGIN
    FOREACH r IN ARRAY ARRAY['anon', 'authenticated'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
            EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA sgj FROM %I', r);
            EXECUTE format('REVOKE ALL ON ALL SEQUENCES IN SCHEMA sgj FROM %I', r);
            EXECUTE format('REVOKE ALL ON ALL FUNCTIONS IN SCHEMA sgj FROM %I', r);
        END IF;
    END LOOP;
END $$;

COMMIT;
