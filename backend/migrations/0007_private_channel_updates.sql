CREATE TRIGGER private_channels_audit_update AFTER UPDATE ON private_channels BEGIN
    INSERT INTO chat_audit_log(action, message_id, created_at) VALUES ('channel_update', NEW.rowid, NEW.updated_at);
END;
PRAGMA user_version = 7;
