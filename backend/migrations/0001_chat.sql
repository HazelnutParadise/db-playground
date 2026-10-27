CREATE TABLE IF NOT EXISTS chat_settings (
    key TEXT PRIMARY KEY,
    value BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    body TEXT NOT NULL CHECK (length(body) BETWEEN 1 AND 1000),
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    deleted_at REAL
);
CREATE INDEX IF NOT EXISTS chat_messages_created_at_idx ON chat_messages(created_at, id);
CREATE TABLE IF NOT EXISTS chat_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    message_id INTEGER NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS chat_audit_created_at_idx ON chat_audit_log(created_at);
CREATE TABLE IF NOT EXISTS chat_request_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    method TEXT NOT NULL,
    path TEXT NOT NULL,
    status INTEGER NOT NULL,
    actor TEXT NOT NULL,
    client_ip TEXT NOT NULL,
    user_agent TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS chat_request_created_at_idx ON chat_request_log(created_at);
CREATE TRIGGER IF NOT EXISTS chat_messages_audit_insert AFTER INSERT ON chat_messages
BEGIN
    INSERT INTO chat_audit_log(action, message_id, created_at) VALUES ('insert', NEW.id, NEW.created_at);
END;
CREATE TRIGGER IF NOT EXISTS chat_messages_audit_update AFTER UPDATE ON chat_messages
BEGIN
    INSERT INTO chat_audit_log(action, message_id, created_at) VALUES ('update', NEW.id, NEW.updated_at);
END;
CREATE TRIGGER IF NOT EXISTS chat_messages_audit_delete AFTER DELETE ON chat_messages
BEGIN
    INSERT INTO chat_audit_log(action, message_id, created_at) VALUES ('delete', OLD.id, unixepoch());
END;
CREATE TRIGGER IF NOT EXISTS chat_messages_updated_at AFTER UPDATE ON chat_messages
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE chat_messages SET updated_at = unixepoch() WHERE id = NEW.id;
END;
PRAGMA user_version = 1;
