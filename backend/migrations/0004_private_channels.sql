CREATE TABLE private_channels (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, code_hash BLOB NOT NULL UNIQUE,
    code_encrypted BLOB NOT NULL, owner_hash BLOB NOT NULL,
    created_at REAL NOT NULL, updated_at REAL NOT NULL, deleted_at REAL
);
CREATE TABLE private_members (
    id INTEGER PRIMARY KEY, channel_id TEXT NOT NULL REFERENCES private_channels(id) ON DELETE RESTRICT,
    identity_hash BLOB NOT NULL, nickname TEXT NOT NULL, nickname_key TEXT NOT NULL,
    created_at REAL NOT NULL, updated_at REAL NOT NULL, deleted_at REAL,
    UNIQUE(channel_id, identity_hash), UNIQUE(channel_id, nickname_key)
);
CREATE TABLE private_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT, channel_id TEXT NOT NULL REFERENCES private_channels(id) ON DELETE RESTRICT,
    name TEXT NOT NULL, body TEXT NOT NULL, attachment TEXT,
    created_at REAL NOT NULL, updated_at REAL NOT NULL, deleted_at REAL
);
CREATE INDEX private_messages_channel_time ON private_messages(channel_id, created_at, id);
CREATE TABLE private_attempts (identity_hash BLOB NOT NULL, created_at REAL NOT NULL);
CREATE INDEX private_attempts_identity_time ON private_attempts(identity_hash, created_at);
CREATE TRIGGER private_channels_audit_insert AFTER INSERT ON private_channels BEGIN
    INSERT INTO chat_audit_log(action, message_id, created_at) VALUES ('channel_insert', NEW.rowid, NEW.created_at);
END;
CREATE TRIGGER private_members_audit_insert AFTER INSERT ON private_members BEGIN
    INSERT INTO chat_audit_log(action, message_id, created_at) VALUES ('member_insert', NEW.id, NEW.created_at);
END;
CREATE TRIGGER private_messages_audit_insert AFTER INSERT ON private_messages BEGIN
    INSERT INTO chat_audit_log(action, message_id, created_at) VALUES ('private_insert', NEW.id, NEW.created_at);
END;
CREATE TRIGGER private_messages_audit_delete AFTER DELETE ON private_messages BEGIN
    INSERT INTO chat_audit_log(action, message_id, created_at) VALUES ('private_delete', OLD.id, unixepoch());
END;
PRAGMA user_version = 4;
