CREATE TRIGGER private_members_audit_update AFTER UPDATE ON private_members BEGIN
    INSERT INTO chat_audit_log(action, message_id, created_at) VALUES ('member_update', NEW.id, NEW.updated_at);
END;
PRAGMA user_version = 5;
