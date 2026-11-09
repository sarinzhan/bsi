-- platform-api schema v1: access module (users, role changes).
-- Each module owns its tables; other modules use them only through the module's provided ports.

-- Append-only tables: history is never edited or deleted.
CREATE FUNCTION forbid_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION '% is append-only: rows are never changed or deleted', TG_TABLE_NAME;
END $$;

-- ---- access module ----

CREATE TABLE users (
  id         text PRIMARY KEY CHECK (id ~ '^[a-z][a-z0-9._-]{1,40}$'),
  name       text NOT NULL,
  roles      text[] NOT NULL CHECK (cardinality(roles) >= 1 AND roles <@ ARRAY['developer', 'devops', 'admin']),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE role_changes (
  id      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id text NOT NULL REFERENCES users (id),
  added   text[] NOT NULL,
  removed text[] NOT NULL,
  by      text NOT NULL,
  reason  text NOT NULL,
  at      timestamptz NOT NULL
);
CREATE INDEX role_changes_user ON role_changes (user_id, id);
CREATE TRIGGER role_changes_append_only BEFORE UPDATE OR DELETE ON role_changes
  FOR EACH ROW EXECUTE FUNCTION forbid_change();
CREATE TRIGGER role_changes_no_truncate BEFORE TRUNCATE ON role_changes
  FOR EACH STATEMENT EXECUTE FUNCTION forbid_change();
