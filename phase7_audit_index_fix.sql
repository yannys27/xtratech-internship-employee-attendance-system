-- Audit Log Index Compatibility Fix
-- Select the target database before running.
-- Safe for existing deployments.
-- No existing audit data is deleted or modified.

DROP PROCEDURE IF EXISTS ensure_audit_log_indexes;

DELIMITER //

CREATE PROCEDURE ensure_audit_log_indexes()
BEGIN

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.statistics
        WHERE table_schema = DATABASE()
          AND table_name = 'audit_log'
          AND index_name = 'idx_audit_username'
    ) THEN

        CREATE INDEX idx_audit_username
        ON audit_log (username);

    END IF;


    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.statistics
        WHERE table_schema = DATABASE()
          AND table_name = 'audit_log'
          AND index_name = 'idx_audit_created_at'
    ) THEN

        CREATE INDEX idx_audit_created_at
        ON audit_log (created_at);

    END IF;

END //

DELIMITER ;

CALL ensure_audit_log_indexes();

DROP PROCEDURE ensure_audit_log_indexes;