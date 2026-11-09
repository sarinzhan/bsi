-- server-tools schema v1: servers (servers module), access changes (servers module), audit log (tools module).

-- Append-only tables: history is never edited or deleted.
CREATE FUNCTION forbid_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION '% is append-only: rows are never changed or deleted', TG_TABLE_NAME;
END $$;

-- ---- servers module ----

CREATE TABLE servers (
  name          text PRIMARY KEY CHECK (name ~ '^[a-z0-9][a-z0-9-]{1,62}$'),
  host          text NOT NULL,
  env           text NOT NULL CHECK (env IN ('dev', 'stage', 'prod')),
  systems       text[] NOT NULL DEFAULT '{}',   -- systems allowed to use this server
  allowed_tools text[] NOT NULL DEFAULT '{}',   -- empty = the agent can do nothing here
  ssh_user      text NOT NULL DEFAULT 'deploy',
  ssh_port      integer NOT NULL DEFAULT 22 CHECK (ssh_port BETWEEN 1 AND 65535),
  updated_at    timestamptz NOT NULL DEFAULT now(),
  -- the same rule as the domain, so a hand-written UPDATE cannot break it either
  CONSTRAINT no_ssh_exec_on_prod CHECK (NOT (env = 'prod' AND 'ssh_exec' = ANY (allowed_tools)))
);

CREATE TABLE access_changes (
  id      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  server  text NOT NULL REFERENCES servers (name),
  added   text[] NOT NULL,
  removed text[] NOT NULL,
  by      text NOT NULL,
  reason  text NOT NULL,
  at      timestamptz NOT NULL
);
CREATE INDEX access_changes_server ON access_changes (server, id);
CREATE TRIGGER access_changes_append_only BEFORE UPDATE OR DELETE ON access_changes
  FOR EACH ROW EXECUTE FUNCTION forbid_change();
CREATE TRIGGER access_changes_no_truncate BEFORE TRUNCATE ON access_changes
  FOR EACH STATEMENT EXECUTE FUNCTION forbid_change();

-- ---- tools module ----

CREATE TABLE audit_log (
  id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  at           timestamptz NOT NULL DEFAULT now(),
  run_id       text NOT NULL,
  chat_id      text NOT NULL,
  requested_by text NOT NULL,
  tool         text NOT NULL,
  server       text NOT NULL,     -- no foreign key: the tools module does not own servers
  command      text NOT NULL,     -- masked, exactly as shown on the approval card
  approved_by  text NOT NULL,
  status       text NOT NULL CHECK (status IN ('rejected', 'denied', 'failed', 'done')),
  exit_code    integer
);
CREATE INDEX audit_log_chat ON audit_log (chat_id, id);
CREATE INDEX audit_log_at ON audit_log (at);
CREATE TRIGGER audit_log_append_only BEFORE UPDATE OR DELETE ON audit_log
  FOR EACH ROW EXECUTE FUNCTION forbid_change();
CREATE TRIGGER audit_log_no_truncate BEFORE TRUNCATE ON audit_log
  FOR EACH STATEMENT EXECUTE FUNCTION forbid_change();
