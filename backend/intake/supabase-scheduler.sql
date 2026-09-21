-- Run as the database owner. Install disabled; enable after verifying the token.
-- Tokens belong in Vault, never in this file or the cron command.
BEGIN;

CREATE EXTENSION IF NOT EXISTS pg_cron;
CREATE EXTENSION IF NOT EXISTS pg_net WITH SCHEMA extensions;
CREATE SCHEMA IF NOT EXISTS crm_scheduler;
REVOKE ALL ON SCHEMA crm_scheduler FROM PUBLIC, anon, authenticated;

CREATE OR REPLACE FUNCTION crm_scheduler.dispatch_background()
RETURNS bigint
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $function$
DECLARE
    dispatch_token text;
BEGIN
    SELECT btrim(decrypted_secret) INTO dispatch_token
    FROM vault.decrypted_secrets
    WHERE name = 'crm_github_dispatch_token';
    IF dispatch_token IS NULL OR btrim(dispatch_token) = '' THEN
        RAISE EXCEPTION 'Missing Vault secret crm_github_dispatch_token';
    END IF;

    RETURN net.http_post(
        url := 'https://api.github.com/repos/nippontoyota/river-crm/actions/workflows/crm-background.yml/dispatches',
        headers := jsonb_build_object(
            'Authorization', 'Bearer ' || dispatch_token,
            'Accept', 'application/vnd.github+json',
            'Content-Type', 'application/json',
            'X-GitHub-Api-Version', '2022-11-28',
            'User-Agent', 'river-crm-scheduler'
        ),
        body := '{"ref":"main","inputs":{"mode":"process"}}'::jsonb,
        timeout_milliseconds := 10000
    );
END;
$function$;
REVOKE ALL ON FUNCTION crm_scheduler.dispatch_background() FROM PUBLIC, anon, authenticated;

DO $install$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM cron.job WHERE jobname = 'crm-background-dispatch') THEN
        PERFORM cron.alter_job(
            cron.schedule('crm-background-dispatch', '*/5 * * * *',
                          'SELECT crm_scheduler.dispatch_background();'),
            active := false
        );
    END IF;
END;
$install$;

COMMIT;
