-- Aether core persistence schema (Neon / Postgres)

CREATE TABLE IF NOT EXISTS worlds (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS characters (
    id TEXT NOT NULL,
    world_id TEXT NOT NULL REFERENCES worlds (id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (world_id, id)
);

CREATE INDEX IF NOT EXISTS idx_characters_world_id ON characters (world_id);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL REFERENCES worlds (id) ON DELETE CASCADE,
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sessions_world_id ON sessions (world_id);

CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    world_id TEXT,
    session_id TEXT,
    event_type TEXT NOT NULL,
    actor_id TEXT,
    occurred_at TIMESTAMPTZ NOT NULL,
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_events_world_occurred
    ON events (world_id, occurred_at);

CREATE INDEX IF NOT EXISTS idx_events_session_id
    ON events (session_id)
    WHERE session_id IS NOT NULL;
