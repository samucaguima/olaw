-- Coleta do DataJud a partir do banco em São Paulo (plano, Seções 5.4 e 23.3).
-- Pressupõe 0002. Movimentação do DataJud nunca abre prazo: alimenta
-- sgj.movimentacoes (capa e histórico). As requisições usam a extensão pg_net,
-- no mesmo padrão da captura do DJEN; a chave pública do CNJ fica no Vault do
-- Supabase, com o nome datajud_api_key, fora do repositório.

BEGIN;

CREATE TABLE sgj.datajud_requisicao (
    request_id        bigint PRIMARY KEY,
    processo_id       bigint NOT NULL REFERENCES sgj.processos(id) ON DELETE CASCADE,
    alias             text NOT NULL,
    disparada_em      timestamptz NOT NULL DEFAULT now(),
    processada_em     timestamptz,
    status_http       integer,
    registros         integer,
    movimentos_novos  integer,
    erro              text
);
CREATE INDEX datajud_requisicao_processo ON sgj.datajud_requisicao (processo_id, disparada_em);
COMMENT ON TABLE sgj.datajud_requisicao IS 'Requisições à API pública do DataJud e o resultado de cada uma.';

-- Alias da API (api_publica_<alias>). Conferidos em chamada real em 10/10/2026:
-- tjrs, tjsc, tjpr, tjsp, trf4 e trt4. Os demais seguem o mesmo padrão de nome;
-- alias recusado pela API fica registrado como erro da requisição.
CREATE FUNCTION sgj.datajud_alias(p_tribunal text) RETURNS text
LANGUAGE sql IMMUTABLE SET search_path = '' AS $$
    SELECT CASE WHEN p_tribunal IN ('TJDFT', 'TJGO', 'TJMT', 'TJMS', 'TJPR', 'TJRJ', 'TJRS', 'TJSC', 'TJSP',
                                    'TRF1', 'TRF4', 'TRT4', 'TRT12', 'STJ')
                THEN lower(p_tribunal) END
$$;

-- Data do movimento: ISO 8601 ou AAAAMMDDHHMMSS; formato desconhecido retorna nulo.
CREATE FUNCTION sgj.datajud_data(p_valor text) RETURNS timestamptz
LANGUAGE plpgsql STABLE SET search_path = '' AS $$
BEGIN
    IF p_valor ~ '^\d{14}$' THEN
        RETURN to_timestamp(p_valor, 'YYYYMMDDHH24MISS');
    END IF;
    RETURN p_valor::timestamptz;
EXCEPTION WHEN OTHERS THEN
    RETURN NULL;
END;
$$;

-- Dispara a consulta de até p_limite processos de casos não encerrados, começando
-- pelos consultados há mais tempo. A resposta chega de forma assíncrona.
CREATE FUNCTION sgj.datajud_disparar(p_limite integer DEFAULT 30) RETURNS integer
LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE
    v_chave  text;
    r        record;
    v_rid    bigint;
    v_total  integer := 0;
BEGIN
    SELECT decrypted_secret INTO v_chave FROM vault.decrypted_secrets WHERE name = 'datajud_api_key' LIMIT 1;
    IF v_chave IS NULL THEN
        RAISE EXCEPTION 'Chave do DataJud ausente no Vault (nome datajud_api_key).';
    END IF;
    FOR r IN
        SELECT p.id, p.npu, sgj.datajud_alias(p.tribunal) AS alias
        FROM sgj.processos p
        JOIN sgj.casos c ON c.id = p.caso_id
        WHERE c.situacao <> 'encerrado'
          AND sgj.datajud_alias(p.tribunal) IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM sgj.datajud_requisicao q
                          WHERE q.processo_id = p.id AND q.processada_em IS NULL)
        ORDER BY (SELECT max(q.disparada_em) FROM sgj.datajud_requisicao q WHERE q.processo_id = p.id) NULLS FIRST, p.id
        LIMIT p_limite
    LOOP
        v_rid := net.http_post(
            url := 'https://api-publica.datajud.cnj.jus.br/api_publica_' || r.alias || '/_search',
            body := jsonb_build_object('query', jsonb_build_object('match', jsonb_build_object('numeroProcesso', r.npu))),
            headers := jsonb_build_object('Authorization', 'APIKey ' || v_chave, 'Content-Type', 'application/json'),
            timeout_milliseconds := 90000);
        INSERT INTO sgj.datajud_requisicao (request_id, processo_id, alias) VALUES (v_rid, r.id, r.alias);
        v_total := v_total + 1;
    END LOOP;
    RETURN v_total;
END;
$$;

-- Processa as respostas recebidas: grava os movimentos de todos os registros
-- (um por grau ou instância), marca a sincronização e, se o DataJud indicar
-- sigilo, marca o processo como em segredo de justiça (efeito conservador:
-- a IA fica desabilitada para ele).
CREATE FUNCTION sgj.datajud_coletar() RETURNS jsonb
LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE
    v_coleta      bigint;
    r             record;
    v_json        jsonb;
    v_registros   integer;
    v_novos       integer;
    v_sigilo      boolean;
    v_processadas integer := 0;
    v_falhas      integer := 0;
    v_total_novos integer := 0;
    v_expiradas   integer := 0;
BEGIN
    INSERT INTO sgj.coletas (fonte) VALUES ('datajud') RETURNING id INTO v_coleta;
    FOR r IN
        SELECT q.request_id, q.processo_id, h.status_code, h.content, h.error_msg
        FROM sgj.datajud_requisicao q
        JOIN net._http_response h ON h.id = q.request_id
        WHERE q.processada_em IS NULL
    LOOP
        BEGIN
            v_registros := NULL;
            v_novos := 0;
            IF r.status_code = 200 THEN
                v_json := r.content::jsonb;
                v_registros := jsonb_array_length(coalesce(v_json #> '{hits,hits}', '[]'::jsonb));
                INSERT INTO sgj.movimentacoes (processo_id, origem, data_hora, codigo, descricao, coleta_id)
                SELECT DISTINCT r.processo_id, 'datajud', mv.data_hora, mv.codigo, mv.descricao, v_coleta
                FROM (
                    SELECT sgj.datajud_data(m->>'dataHora') AS data_hora,
                           coalesce(m->>'codigo', '') AS codigo,
                           coalesce(nullif(btrim(concat_ws(' ', m->>'nome',
                               (SELECT '(' || string_agg(concat_ws(': ', c->>'nome', c->>'descricao'), '; ') || ')'
                                FROM jsonb_array_elements(coalesce(m->'complementosTabelados', '[]'::jsonb)) c))), ''),
                               '(movimento sem nome)') AS descricao
                    FROM jsonb_array_elements(coalesce(v_json #> '{hits,hits}', '[]'::jsonb)) h,
                         jsonb_array_elements(coalesce(h #> '{_source,movimentos}', '[]'::jsonb)) m
                ) mv
                WHERE mv.data_hora IS NOT NULL
                ON CONFLICT DO NOTHING;
                GET DIAGNOSTICS v_novos = ROW_COUNT;

                SELECT coalesce(bool_or((h #>> '{_source,nivelSigilo}') ~ '^[1-9]'), false) INTO v_sigilo
                FROM jsonb_array_elements(coalesce(v_json #> '{hits,hits}', '[]'::jsonb)) h;
                IF v_sigilo THEN
                    UPDATE sgj.processos SET segredo_justica = true WHERE id = r.processo_id;
                END IF;
                IF v_registros > 0 THEN
                    UPDATE sgj.processos SET ultima_sincronizacao = now() WHERE id = r.processo_id;
                END IF;
            ELSE
                v_falhas := v_falhas + 1;
            END IF;
            UPDATE sgj.datajud_requisicao
            SET processada_em = now(), status_http = r.status_code, registros = v_registros, movimentos_novos = v_novos,
                erro = CASE WHEN r.status_code IS DISTINCT FROM 200 THEN coalesce(r.error_msg, left(r.content, 300))
                            WHEN v_registros = 0 THEN 'sem registros utilizáveis' END
            WHERE request_id = r.request_id;
            v_processadas := v_processadas + 1;
            v_total_novos := v_total_novos + v_novos;
        EXCEPTION WHEN OTHERS THEN
            UPDATE sgj.datajud_requisicao SET processada_em = now(), status_http = r.status_code, erro = SQLERRM
            WHERE request_id = r.request_id;
            v_falhas := v_falhas + 1;
        END;
    END LOOP;

    -- O pg_net guarda as respostas por tempo limitado; requisição sem resposta
    -- depois de 6 horas é encerrada e volta à fila na próxima rodada.
    UPDATE sgj.datajud_requisicao SET processada_em = now(), erro = 'sem resposta no prazo de retenção do pg_net'
    WHERE processada_em IS NULL AND disparada_em < now() - interval '6 hours';
    GET DIAGNOSTICS v_expiradas = ROW_COUNT;

    UPDATE sgj.coletas
    SET fim = now(), itens = v_total_novos,
        situacao = CASE WHEN v_falhas > 0 AND v_processadas = 0 THEN 'falhou' ELSE 'concluida' END,
        erro = CASE WHEN v_falhas + v_expiradas > 0
                    THEN format('%s requisições com falha, %s sem resposta', v_falhas, v_expiradas) END
    WHERE id = v_coleta;
    RETURN jsonb_build_object('coleta', v_coleta, 'processadas', v_processadas, 'falhas', v_falhas,
                              'sem_resposta', v_expiradas, 'movimentos_novos', v_total_novos);
END;
$$;

-- Agendamento: uma rodada por dia, depois das capturas do DJEN; 30 processos por
-- rodada (a carteira inteira a cada quatro dias, compatível com a defasagem do
-- DataJud). Só onde houver pg_cron.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN
        PERFORM cron.schedule('sgj-datajud-disparar', '20 10 * * *', 'SELECT sgj.datajud_disparar(30)');
        PERFORM cron.schedule('sgj-datajud-coletar', '30,50 10 * * *', 'SELECT sgj.datajud_coletar()');
    END IF;
END $$;

ALTER TABLE sgj.datajud_requisicao ENABLE ROW LEVEL SECURITY;
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
