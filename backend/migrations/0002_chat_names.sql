CREATE TABLE IF NOT EXISTS chat_names (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    identity_hash BLOB NOT NULL UNIQUE,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    deleted_at REAL
);
CREATE TRIGGER IF NOT EXISTS chat_names_audit_insert AFTER INSERT ON chat_names
BEGIN
    INSERT INTO chat_audit_log(action, message_id, created_at) VALUES ('name_insert', NEW.id, NEW.created_at);
END;
CREATE TRIGGER IF NOT EXISTS chat_names_updated_at AFTER UPDATE ON chat_names
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE chat_names SET updated_at = unixepoch() WHERE id = NEW.id;
END;
PRAGMA user_version = 2;
