-- Audit Log migration
-- No database name is hardcoded.
-- Select the target database before executing this script.
-- Safe to run more than once.

CREATE TABLE IF NOT EXISTS audit_log (
    audit_id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL,
    action VARCHAR(100) NOT NULL,
    details TEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_audit_username (username),
    INDEX idx_audit_created_at (created_at)
);