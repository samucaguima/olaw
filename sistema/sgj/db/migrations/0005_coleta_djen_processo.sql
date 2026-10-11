-- Coleta do DJEN por número de processo (plano, Seção 5.1, e Seção 19, risco 1).
-- Pressupõe 0002. Complementa a captura por OAB do esquema djen, que permanece
-- inalterado: consulta a mesma API, a partir do banco em São Paulo, para cada
-- processo de caso não encerrado, e guarda em sgj.djen_comunicacao só as
-- comunicações que a captura por OAB ainda não tinha. A sincronização passa a
-- ler as duas fontes, sem duplicar.
--
-- [CONFERIR] O parâmetro numeroProcesso consta da API apenas por fontes de
-- terceiros (plano, Seção 5.1). Salvaguardas:
-- 1. Sondagem: enquanto a conferência cruzada mais recente não for válida, cada
--    rodada consulta um único processo, num dia em que a captura por OAB já
--    registrou comunicação dele; a resposta precisa trazer essa comunicação.
-- 2. Resposta com comunicação de outro processo é descartada por inteiro.
-- 3. Essa resposta, ou recusa por bloqueio (403) ou excesso (429), suspende a
--    coleta por 24 horas.
-- 4. Consulta que não traz comunicação já capturada por OAB no mesmo período
--    fica marcada como divergente e devolve a coleta à sondagem.

BEGIN;

CREATE TABLE sgj.djen_requisicao (
    request_id       bigint PRIMARY KEY,
    processo_id      bigint NOT NULL REFERENCES sgj.processos(id) ON DELETE CASCADE,
    npu              text NOT NULL,
    data_inicio      date NOT NULL,
    data_fim         date NOT NULL,
    sondagem         boolean NOT NULL DEFAULT false,
    url              text NOT NULL,
    disparada_em     timestamptz NOT NULL DEFAULT now(),
    processada_em    timestamptz,
    status_http      integer,
    resultado        text CHECK (resultado IN ('valida', 'divergente', 'parametro_ignorado', 'falha', 'sem_resposta')),
    total_informado  integer,
    recebidas        integer,
    conferidas       integer,
    novas            integer,
    erro             text
);
CREATE INDEX djen_requisicao_processo ON sgj.djen_requisicao (processo_id, disparada_em);
COMMENT ON TABLE sgj.djen_requisicao IS 'Consultas ao DJEN por número de processo e o resultado de cada uma.';
COMMENT ON COLUMN sgj.djen_requisicao.resultado IS
    'valida: só comunicações do processo consultado, inclusive as já capturadas por OAB no período; '
    'divergente: faltou comunicação já capturada por OAB no período; '
    'parametro_ignorado: veio comunicação de outro processo (nada gravado; coleta suspensa por 24 horas); '
    'falha: erro HTTP ou resposta ilegível; sem_resposta: nenhuma resposta no prazo de retenção do pg_net.';
COMMENT ON COLUMN sgj.djen_requisicao.conferidas IS
    'Comunicações do processo que a captura por OAB já tinha no período consultado (base da conferência cruzada).';

CREATE TABLE sgj.djen_comunicacao (
    id                     bigint PRIMARY KEY,
    data_disponibilizacao  date,
    tribunal               text,
    processo               text,
    classe                 text,
    tipo_comunicacao       text,
    tipo_documento         text,
    orgao                  text,
    texto_html             text,
    link                   text,
    raw                    jsonb NOT NULL,
    request_id             bigint REFERENCES sgj.djen_requisicao(request_id) ON DELETE SET NULL,
    capturada_em           timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE sgj.djen_comunicacao IS
    'Comunicações encontradas pela consulta por processo e ausentes da captura por OAB (esquema djen) no momento da coleta; '
    'mesmos campos de djen.comunicacao.';

COMMENT ON COLUMN sgj.coletas.fonte IS 'djen (sincronização), djen_processo (consulta por processo), datajud ou robo:<sistema>:<tribunal>.';

-- Fonte única da sincronização. A mesma comunicação nas duas capturas vale pela
-- captura por OAB.
CREATE FUNCTION sgj.djen_fonte()
RETURNS TABLE (id bigint, data_disponibilizacao date, tribunal text, orgao text, classe text, tipo_comunicacao text,
               tipo_documento text, texto_html text, link text, processo text, raw jsonb, por_processo boolean)
LANGUAGE plpgsql STABLE SET search_path = '' AS $$
BEGIN
    RETURN QUERY
    SELECT c.id, c.data_disponibilizacao, c.tribunal, c.orgao, c.classe, c.tipo_comunicacao, c.tipo_documento,
           c.texto_html, c.link, c.processo, c.raw, false
    FROM djen.comunicacao c
    UNION ALL
    SELECT s.id, s.data_disponibilizacao, s.tribunal, s.orgao, s.classe, s.tipo_comunicacao, s.tipo_documento,
           s.texto_html, s.link, s.processo, s.raw, true
    FROM sgj.djen_comunicacao s
    WHERE NOT EXISTS (SELECT 1 FROM djen.comunicacao c2 WHERE c2.id = s.id);
END;
$$;

-- Sincronização (0002) com as duas fontes; regras inalteradas.
CREATE OR REPLACE FUNCTION sgj.sincronizar_djen() RETURNS jsonb
LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE
    v_coleta        bigint;
    v_completadas   integer := 0;
    v_inseridas     integer := 0;
    v_por_processo  integer := 0;
    v_vinculadas    integer := 0;
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
            FROM sgj.djen_fonte() c
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
        WITH novas AS (
            INSERT INTO sgj.publicacoes (processo_id, npu, hash, data_disponibilizacao, tipo_comunicacao, texto,
                                         coleta_id, djen_id, tribunal, orgao, classe, tipo_documento, link)
            SELECT pr.id, s.npu, s.hash, s.data_disponibilizacao, s.tipo_comunicacao,
                   coalesce(sgj.texto_de_html(s.texto_html), '(comunicação sem texto)'), v_coleta,
                   s.id, s.tribunal, s.orgao, s.classe, s.tipo_documento, s.link
            FROM (SELECT c.id, c.data_disponibilizacao, c.tribunal, c.orgao, c.classe, c.tipo_comunicacao,
                         c.tipo_documento, c.texto_html, nullif(c.link, '') AS link,
                         regexp_replace(coalesce(c.processo, ''), '\D', '', 'g') AS npu,
                         coalesce(nullif(c.raw->>'hash', ''), 'djen:' || c.id) AS hash
                  FROM sgj.djen_fonte() c) s
            LEFT JOIN sgj.processos pr ON pr.npu = s.npu
            WHERE s.npu <> '' AND s.data_disponibilizacao IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM sgj.publicacoes p WHERE p.djen_id = s.id OR p.hash = s.hash)
            ORDER BY s.data_disponibilizacao, s.id
            ON CONFLICT DO NOTHING
            RETURNING djen_id
        )
        SELECT count(*), count(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM djen.comunicacao c WHERE c.id = novas.djen_id))
        INTO v_inseridas, v_por_processo
        FROM novas;

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
                              'inseridas_pela_consulta_por_processo', v_por_processo,
                              'completadas', v_completadas, 'vinculadas', v_vinculadas);
END;
$$;

-- Uma requisição à API por processo, com os mesmos cabeçalhos e limite de tempo
-- da captura por OAB.
CREATE FUNCTION sgj.djen_processo_pedir(p_processo_id bigint, p_npu text, p_inicio date, p_fim date,
                                        p_sondagem boolean) RETURNS bigint
LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE
    v_url  text;
    v_rid  bigint;
BEGIN
    v_url := format('https://comunicaapi.pje.jus.br/api/v1/comunicacao?numeroProcesso=%s&itensPorPagina=100&pagina=1'
                    '&dataDisponibilizacaoInicio=%s&dataDisponibilizacaoFim=%s',
                    p_npu, to_char(p_inicio, 'YYYY-MM-DD'), to_char(p_fim, 'YYYY-MM-DD'));
    v_rid := net.http_get(url := v_url,
                          headers := '{"Accept": "application/json", "User-Agent": "Mozilla/5.0"}'::jsonb,
                          timeout_milliseconds := 30000);
    INSERT INTO sgj.djen_requisicao (request_id, processo_id, npu, data_inicio, data_fim, sondagem, url)
    VALUES (v_rid, p_processo_id, p_npu, p_inicio, p_fim, p_sondagem, v_url);
    RETURN v_rid;
END;
$$;

-- Dispara a consulta de até p_limite processos de casos não encerrados, cada um
-- uma vez por dia, com as publicações dos últimos p_dias dias (data de São
-- Paulo), começando pelos consultados há mais tempo. Em sondagem, um processo
-- por rodada; com a coleta suspensa, nenhum.
CREATE FUNCTION sgj.djen_processo_disparar(p_limite integer DEFAULT 10, p_dias integer DEFAULT 7) RETURNS integer
LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE
    v_hoje      date := (now() AT TIME ZONE 'America/Sao_Paulo')::date;
    v_estado    text;
    r           record;
    v_total     integer := 0;
BEGIN
    IF EXISTS (SELECT 1 FROM sgj.djen_requisicao
               WHERE processada_em > now() - interval '24 hours'
                 AND (resultado = 'parametro_ignorado' OR status_http IN (403, 429))) THEN
        RETURN 0;
    END IF;

    SELECT q.resultado INTO v_estado
    FROM sgj.djen_requisicao q
    WHERE (q.conferidas > 0 AND q.resultado IN ('valida', 'divergente')) OR q.resultado = 'parametro_ignorado'
    ORDER BY q.processada_em DESC, q.request_id DESC
    LIMIT 1;

    IF v_estado IS DISTINCT FROM 'valida' THEN
        IF EXISTS (SELECT 1 FROM sgj.djen_requisicao WHERE processada_em IS NULL) THEN
            RETURN 0;
        END IF;
        IF to_regclass('djen.comunicacao') IS NOT NULL THEN
            SELECT p.id, p.npu, max(c.data_disponibilizacao) AS dia INTO r
            FROM sgj.processos p
            JOIN sgj.casos k ON k.id = p.caso_id
            JOIN djen.comunicacao c ON regexp_replace(coalesce(c.processo, ''), '\D', '', 'g') = p.npu
            WHERE k.situacao <> 'encerrado' AND c.data_disponibilizacao IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM sgj.djen_requisicao q
                              WHERE q.processo_id = p.id AND q.sondagem AND q.disparada_em > now() - interval '1 day')
            GROUP BY p.id, p.npu
            ORDER BY max(c.data_disponibilizacao) DESC, p.id
            LIMIT 1;
            IF FOUND THEN
                PERFORM sgj.djen_processo_pedir(r.id, r.npu, r.dia, r.dia, true);
                RETURN 1;
            END IF;
        END IF;
        p_limite := least(p_limite, 1);
    END IF;

    FOR r IN
        SELECT p.id, p.npu
        FROM sgj.processos p
        JOIN sgj.casos k ON k.id = p.caso_id
        WHERE k.situacao <> 'encerrado'
          AND NOT EXISTS (SELECT 1 FROM sgj.djen_requisicao q
                          WHERE q.processo_id = p.id
                            AND (q.processada_em IS NULL
                                 OR (NOT q.sondagem AND q.resultado IN ('valida', 'divergente')
                                     AND (q.disparada_em AT TIME ZONE 'America/Sao_Paulo')::date = v_hoje)))
        ORDER BY (SELECT max(q.disparada_em) FROM sgj.djen_requisicao q WHERE q.processo_id = p.id AND NOT q.sondagem)
                 NULLS FIRST, p.id
        LIMIT greatest(p_limite, 0)
    LOOP
        PERFORM sgj.djen_processo_pedir(r.id, r.npu, v_hoje - p_dias, v_hoje, false);
        v_total := v_total + 1;
    END LOOP;
    RETURN v_total;
END;
$$;

-- Processa as respostas recebidas, confere cada uma com a captura por OAB e
-- guarda as comunicações que só a consulta por processo encontrou; havendo
-- comunicação nova, sincroniza em seguida.
CREATE FUNCTION sgj.djen_processo_coletar() RETURNS jsonb
LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE
    v_coleta       bigint;
    v_tem_djen     boolean := to_regclass('djen.comunicacao') IS NOT NULL;
    r              record;
    v_json         jsonb;
    v_itens        jsonb;
    v_total        integer;
    v_recebidas    integer;
    v_outros       integer;
    v_conhecidas   bigint[];
    v_capturadas   bigint[];
    v_faltantes    integer;
    v_novas        integer;
    v_resultado    text;
    v_erro         text;
    v_processadas  integer := 0;
    v_falhas       integer := 0;
    v_divergentes  integer := 0;
    v_total_novas  integer := 0;
    v_expiradas    integer := 0;
    v_sinc         jsonb;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM sgj.djen_requisicao WHERE processada_em IS NULL) THEN
        RETURN jsonb_build_object('processadas', 0);
    END IF;
    INSERT INTO sgj.coletas (fonte) VALUES ('djen_processo') RETURNING id INTO v_coleta;
    FOR r IN
        SELECT q.request_id, q.npu, q.data_inicio, q.data_fim, h.status_code, h.content, h.error_msg
        FROM sgj.djen_requisicao q
        JOIN net._http_response h ON h.id = q.request_id
        WHERE q.processada_em IS NULL
        ORDER BY q.request_id
    LOOP
        BEGIN
            v_total := NULL;
            v_recebidas := NULL;
            v_conhecidas := '{}';
            v_capturadas := '{}';
            v_novas := 0;
            v_erro := NULL;
            IF r.status_code = 200 THEN
                v_json := r.content::jsonb;
                IF jsonb_typeof(v_json->'items') IS DISTINCT FROM 'array' THEN
                    RAISE EXCEPTION 'resposta sem a lista de comunicações (items)';
                END IF;
                v_itens := v_json->'items';
                v_recebidas := jsonb_array_length(v_itens);
                v_total := CASE WHEN v_json->>'count' ~ '^\d+$' THEN (v_json->>'count')::integer END;
                SELECT count(*) INTO v_outros
                FROM jsonb_array_elements(v_itens) it
                WHERE regexp_replace(coalesce(it->>'numero_processo', it->>'numeroprocessocommascara', ''), '\D', '', 'g')
                      <> r.npu
                   OR coalesce(it->>'id', '') !~ '^\d+$';
                IF v_outros > 0 THEN
                    v_resultado := 'parametro_ignorado';
                    v_erro := format('%s de %s comunicações de outro processo ou sem identificador; nada foi gravado, '
                                     'e a consulta por processo fica suspensa por 24 horas', v_outros, v_recebidas);
                ELSE
                    IF v_tem_djen THEN
                        SELECT coalesce(array_agg(c.id), '{}') INTO v_conhecidas
                        FROM djen.comunicacao c
                        WHERE regexp_replace(coalesce(c.processo, ''), '\D', '', 'g') = r.npu
                          AND c.data_disponibilizacao BETWEEN r.data_inicio AND r.data_fim;
                        SELECT coalesce(array_agg(c.id), '{}') INTO v_capturadas
                        FROM djen.comunicacao c
                        WHERE c.id IN (SELECT (it->>'id')::bigint FROM jsonb_array_elements(v_itens) it);
                    END IF;
                    SELECT count(*) INTO v_faltantes
                    FROM unnest(v_conhecidas) AS k(id)
                    WHERE NOT EXISTS (SELECT 1 FROM jsonb_array_elements(v_itens) it WHERE (it->>'id')::bigint = k.id);

                    INSERT INTO sgj.djen_comunicacao (id, data_disponibilizacao, tribunal, processo, classe,
                                                      tipo_comunicacao, tipo_documento, orgao, texto_html, link, raw,
                                                      request_id)
                    SELECT (it->>'id')::bigint, (it->>'data_disponibilizacao')::date, it->>'siglaTribunal',
                           it->>'numeroprocessocommascara', it->>'nomeClasse', it->>'tipoComunicacao',
                           it->>'tipoDocumento', it->>'nomeOrgao', it->>'texto', it->>'link', it, r.request_id
                    FROM jsonb_array_elements(v_itens) it
                    WHERE NOT ((it->>'id')::bigint = ANY (v_capturadas))
                    ON CONFLICT (id) DO NOTHING;
                    GET DIAGNOSTICS v_novas = ROW_COUNT;

                    IF v_faltantes > 0 THEN
                        v_resultado := 'divergente';
                        v_divergentes := v_divergentes + 1;
                        v_erro := format('%s de %s comunicações já capturadas por OAB no período não vieram na consulta',
                                         v_faltantes, cardinality(v_conhecidas));
                    ELSE
                        v_resultado := 'valida';
                        IF v_total > v_recebidas THEN
                            v_erro := format('%s comunicações no período; gravada só a primeira página (%s)',
                                             v_total, v_recebidas);
                        END IF;
                    END IF;
                END IF;
            ELSE
                v_resultado := 'falha';
                v_erro := coalesce(r.error_msg, left(r.content, 300), 'sem conteúdo');
            END IF;
            IF v_resultado IN ('falha', 'parametro_ignorado') THEN
                v_falhas := v_falhas + 1;
            END IF;
            UPDATE sgj.djen_requisicao
            SET processada_em = now(), status_http = r.status_code, resultado = v_resultado,
                total_informado = v_total, recebidas = v_recebidas, conferidas = cardinality(v_conhecidas),
                novas = v_novas, erro = v_erro
            WHERE request_id = r.request_id;
            v_total_novas := v_total_novas + v_novas;
        EXCEPTION WHEN OTHERS THEN
            UPDATE sgj.djen_requisicao
            SET processada_em = now(), status_http = r.status_code, resultado = 'falha', erro = SQLERRM
            WHERE request_id = r.request_id;
            v_falhas := v_falhas + 1;
        END;
        v_processadas := v_processadas + 1;
    END LOOP;

    -- O pg_net guarda as respostas por tempo limitado.
    UPDATE sgj.djen_requisicao
    SET processada_em = now(), resultado = 'sem_resposta', erro = 'sem resposta no prazo de retenção do pg_net'
    WHERE processada_em IS NULL AND disparada_em < now() - interval '6 hours';
    GET DIAGNOSTICS v_expiradas = ROW_COUNT;

    IF v_total_novas > 0 THEN
        v_sinc := sgj.sincronizar_djen();
    END IF;

    UPDATE sgj.coletas
    SET fim = now(), itens = v_total_novas,
        situacao = CASE WHEN v_processadas > 0 AND v_falhas = v_processadas THEN 'falhou' ELSE 'concluida' END,
        erro = CASE WHEN v_falhas + v_divergentes + v_expiradas > 0
                    THEN format('%s com falha, %s divergentes, %s sem resposta', v_falhas, v_divergentes, v_expiradas) END
    WHERE id = v_coleta;
    RETURN jsonb_build_object('coleta', v_coleta, 'processadas', v_processadas, 'falhas', v_falhas,
                              'divergentes', v_divergentes, 'sem_resposta', v_expiradas, 'novas', v_total_novas,
                              'sincronizacao', v_sinc);
END;
$$;

-- Rodada agendada: processa as respostas pendentes e dispara o lote seguinte.
CREATE FUNCTION sgj.djen_processo_rodada(p_limite integer DEFAULT 10, p_dias integer DEFAULT 7) RETURNS jsonb
LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE
    v_resultado jsonb;
BEGIN
    v_resultado := sgj.djen_processo_coletar();
    RETURN v_resultado || jsonb_build_object('disparadas', sgj.djen_processo_disparar(p_limite, p_dias));
END;
$$;

-- Agendamento: a cada 5 minutos, das 11h às 12h55 UTC (8h às 9h55 em Brasília),
-- fora dos horários da captura por OAB (9h30 e 16h UTC) e do DataJud (10h20 a
-- 10h50 UTC); 10 processos por rodada. Só onde houver pg_cron.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN
        PERFORM cron.schedule('sgj-djen-processo', '*/5 11-12 * * *', 'SELECT sgj.djen_processo_rodada(10, 7)');
    END IF;
END $$;

ALTER TABLE sgj.djen_requisicao ENABLE ROW LEVEL SECURITY;
ALTER TABLE sgj.djen_comunicacao ENABLE ROW LEVEL SECURITY;
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
