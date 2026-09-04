-- Phase 7 - Week 4: Complete Audit Log
-- Select the target database before executing this migration.
-- No database name is hardcoded.
-- Existing audit records are preserved.
-- Run this migration ONCE after phase6_audit_log.sql.

ALTER TABLE audit_log
    ADD COLUMN role VARCHAR(50) NULL AFTER username,
    ADD COLUMN ip_address VARCHAR(45) NULL AFTER action,
    ADD COLUMN affected_record VARCHAR(150) NULL AFTER ip_address,
    ADD COLUMN module VARCHAR(50) NULL AFTER affected_record;

-- Existing entries were created before Week 4.
-- Values that were not originally recorded are labelled rather than guessed.

UPDATE audit_log
SET
    role = COALESCE(NULLIF(role, ''), 'Not recorded'),

    ip_address = COALESCE(
        NULLIF(ip_address, ''),
        'Not recorded'
    ),

    affected_record = COALESCE(
        NULLIF(affected_record, ''),
        LEFT(
            COALESCE(details, 'Legacy audit entry'),
            150
        )
    ),

    module = COALESCE(
        NULLIF(module, ''),
        'Legacy'
    )

WHERE
    role IS NULL
    OR role = ''
    OR ip_address IS NULL
    OR ip_address = ''
    OR affected_record IS NULL
    OR affected_record = ''
    OR module IS NULL
    OR module = '';

ALTER TABLE audit_log
    ADD INDEX idx_audit_role (role),
    ADD INDEX idx_audit_module (module),
    ADD INDEX idx_audit_action (action);

SELECT
    audit_id,
    username,
    role,
    action,
    created_at,
    ip_address,
    affected_record,
    module,
    details
FROM audit_log
ORDER BY created_at DESC, audit_id DESC
LIMIT 50;