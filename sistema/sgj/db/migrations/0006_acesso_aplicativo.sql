-- Acesso do aplicativo no servidor (plano, Seções 16 e 17). Pressupõe 0005.
-- Cria o papel sgj_app, sem login até a instalação do servidor: lê o esquema
-- sgj, grava só nas tabelas que o aplicativo altera, nunca exclui registros e
-- não altera a auditoria. A tela de coletas lê a captura do DJEN e os
-- agendamentos por funções com o privilégio do proprietário, sem que o papel
-- receba acesso aos esquemas djen e cron.
-- A senha é definida na instalação, fora do repositório, conforme a orientação
-- do Supabase de criar um usuário próprio para cada serviço
-- (https://supabase.com/docs/guides/database/postgres/roles).
-- Migração futura que criar tabela no esquema sgj deve conceder o acesso e a
-- política correspondentes ao papel sgj_app.

BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sgj_app') THEN
        CREATE ROLE sgj_app NOLOGIN;
    END IF;
END $$;
COMMENT ON ROLE sgj_app IS 'Aplicativo do sistema no servidor; login habilitado na instalação, com senha fora do repositório.';

GRANT USAGE ON SCHEMA sgj TO sgj_app;
GRANT SELECT ON ALL TABLES IN SCHEMA sgj TO sgj_app;
GRANT INSERT, UPDATE ON sgj.clientes, sgj.casos, sgj.processos, sgj.publicacoes, sgj.prazos, sgj.tarefas,
                        sgj.calendario, sgj.calendario_cobertura TO sgj_app;
GRANT INSERT ON sgj.auditoria TO sgj_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA sgj TO sgj_app;

-- Com segurança por linha ativa em todas as tabelas, o papel do aplicativo
-- precisa de política explícita; o controle por usuário fica no aplicativo.
DO $$
DECLARE t text;
BEGIN
    FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'sgj' LOOP
        EXECUTE format('CREATE POLICY aplicativo ON sgj.%I FOR ALL TO sgj_app USING (true) WITH CHECK (true)', t);
    END LOOP;
END $$;

-- Situação da captura por OAB (esquema djen): última rodada, último sucesso e
-- comunicações dos últimos 7 dias; nulo se a captura não existir.
CREATE FUNCTION sgj.situacao_captura_djen() RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_ultimo  timestamptz;
    v         jsonb;
BEGIN
    IF to_regclass('djen.requisicao') IS NULL THEN
        RETURN NULL;
    END IF;
    SELECT max(disparada_em) INTO v_ultimo FROM djen.requisicao;
    SELECT jsonb_build_object(
               'ultimo_disparo', v_ultimo,
               'ultimo_sucesso', (SELECT max(q.disparada_em) FROM djen.requisicao q WHERE q.status_http = 200),
               'paginas', count(*),
               'ok', count(*) FILTER (WHERE r.status_http = 200),
               'pendentes', count(*) FILTER (WHERE r.processada_em IS NULL),
               'erro', (array_agg(coalesce(r.erro, 'HTTP ' || r.status_http) ORDER BY r.disparada_em)
                        FILTER (WHERE r.processada_em IS NOT NULL AND r.status_http IS DISTINCT FROM 200))[1])
    INTO v
    FROM djen.requisicao r
    WHERE r.disparada_em >= v_ultimo - interval '10 minutes';
    IF to_regclass('djen.comunicacao') IS NOT NULL THEN
        v := v || jsonb_build_object(
            'capturadas_7_dias', (SELECT count(*) FROM djen.comunicacao c WHERE c.capturada_em > now() - interval '7 days'),
            'so_por_processo', (SELECT count(*) FROM sgj.djen_comunicacao s
                                WHERE NOT EXISTS (SELECT 1 FROM djen.comunicacao c WHERE c.id = s.id)));
    END IF;
    RETURN v;
END;
$$;

-- Agendamentos do sistema e da captura do DJEN, com a última execução de cada um.
CREATE FUNCTION sgj.agendamentos()
RETURNS TABLE (rotina text, agenda text, ativa boolean, situacao text, inicio timestamptz, mensagem text)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
BEGIN
    IF to_regclass('cron.job') IS NULL THEN
        RETURN;
    END IF;
    RETURN QUERY
    SELECT j.jobname::text, j.schedule::text, j.active, d.status::text, d.start_time, d.return_message::text
    FROM cron.job j
    LEFT JOIN LATERAL (SELECT r.status, r.start_time, r.return_message FROM cron.job_run_details r
                       WHERE r.jobid = j.jobid ORDER BY r.start_time DESC LIMIT 1) d ON true
    WHERE j.jobname LIKE 'sgj-%' OR j.jobname LIKE 'djen-%'
    ORDER BY j.jobname;
END;
$$;

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

GRANT EXECUTE ON FUNCTION sgj.situacao_captura_djen(), sgj.agendamentos(), sgj.tribunal_da_npu(text) TO sgj_app;

COMMIT;
