CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE users (
    user_id text PRIMARY KEY,
    email text NOT NULL UNIQUE CHECK (email = lower(email)),
    name text NOT NULL,
    password_hash text NOT NULL,
    role text NOT NULL CHECK (role IN ('student', 'teacher', 'superadmin')),
    profile jsonb NOT NULL DEFAULT '{}'
);
CREATE TABLE classrooms (
    classroom_id text PRIMARY KEY,
    name text NOT NULL,
    subject text,
    description text,
    join_code text NOT NULL UNIQUE,
    created_by text NOT NULL REFERENCES users(user_id),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE classroom_members (
    classroom_id text NOT NULL REFERENCES classrooms ON DELETE CASCADE,
    user_id text NOT NULL REFERENCES users ON DELETE CASCADE,
    PRIMARY KEY (classroom_id, user_id)
);
CREATE INDEX members_by_user ON classroom_members(user_id, classroom_id);
CREATE TABLE files (
    file_id text PRIMARY KEY,
    classroom_id text NOT NULL REFERENCES classrooms ON DELETE CASCADE,
    original_name text NOT NULL,
    storage_path text NOT NULL,
    file_type text NOT NULL,
    sha256_hash text NOT NULL,
    uploaded_by text NOT NULL REFERENCES users,
    uploaded_at timestamptz NOT NULL DEFAULT now(),
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','processing','ready','failed','deleted')),
    active_revision integer,
    UNIQUE (classroom_id, sha256_hash),
    UNIQUE (file_id, classroom_id)
);
CREATE TABLE file_revisions (
    file_id text NOT NULL REFERENCES files ON DELETE CASCADE,
    revision integer NOT NULL CHECK (revision > 0),
    embedding_namespace text NOT NULL,
    chunking_version text NOT NULL,
    status text NOT NULL CHECK (status IN ('pending','ready','failed')),
    PRIMARY KEY (file_id, revision)
);
ALTER TABLE files ADD CONSTRAINT active_revision_exists
    FOREIGN KEY (file_id, active_revision) REFERENCES file_revisions(file_id, revision)
    DEFERRABLE INITIALLY DEFERRED;
CREATE TABLE chunks (
    chunk_id text PRIMARY KEY,
    file_id text NOT NULL,
    classroom_id text NOT NULL,
    revision integer NOT NULL,
    chunk_index integer NOT NULL CHECK (chunk_index >= 0),
    title text NOT NULL DEFAULT '',
    text text NOT NULL,
    content_hash text NOT NULL,
    page_number integer CHECK (page_number > 0),
    extraction_method text,
    embedding vector(1536),
    lexical tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('english', coalesce(title,'')), 'A') ||
        setweight(to_tsvector('english', text), 'B')
    ) STORED,
    FOREIGN KEY (file_id, classroom_id) REFERENCES files(file_id, classroom_id) ON DELETE CASCADE,
    FOREIGN KEY (file_id, revision) REFERENCES file_revisions ON DELETE CASCADE,
    UNIQUE (file_id, revision, chunk_index)
);
CREATE INDEX chunks_by_scope ON chunks(classroom_id, file_id, revision);
CREATE INDEX chunks_lexical ON chunks USING gin(lexical);
CREATE TABLE chat_sessions (
    session_id text PRIMARY KEY,
    user_id text NOT NULL REFERENCES users ON DELETE CASCADE,
    classroom_id text REFERENCES classrooms ON DELETE CASCADE,
    file_id text REFERENCES files ON DELETE CASCADE,
    title text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE chat_messages (
    message_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id text NOT NULL REFERENCES chat_sessions ON DELETE CASCADE,
    role text NOT NULL CHECK (role IN ('user','assistant')),
    content text NOT NULL,
    sources jsonb NOT NULL DEFAULT '[]',
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX messages_by_session ON chat_messages(session_id, message_id);
CREATE TABLE announcements (
    announcement_id text PRIMARY KEY,
    classroom_id text NOT NULL REFERENCES classrooms ON DELETE CASCADE,
    author_id text NOT NULL REFERENCES users,
    content text NOT NULL,
    file_id text REFERENCES files ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE calendar_events (
    event_id text PRIMARY KEY,
    classroom_id text REFERENCES classrooms ON DELETE CASCADE,
    created_by text NOT NULL REFERENCES users,
    title text NOT NULL,
    description text,
    date date NOT NULL,
    type text NOT NULL CHECK (type IN ('event','exam','deadline')),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE notifications (
    notification_id text PRIMARY KEY,
    user_id text NOT NULL REFERENCES users ON DELETE CASCADE,
    classroom_id text REFERENCES classrooms ON DELETE CASCADE,
    type text NOT NULL,
    title text NOT NULL,
    message text NOT NULL,
    link text,
    is_read boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX notifications_by_user ON notifications(user_id, is_read, created_at DESC);
