-- Phase 7 - Week 5: Employee Documents
-- Select the target database before running this migration.
-- No database name is hardcoded.
-- Existing employee, attendance, leave, user and audit data is preserved.

CREATE TABLE IF NOT EXISTS employee_documents (
    document_id INT AUTO_INCREMENT PRIMARY KEY,
    employee_id INT NOT NULL,
    document_type VARCHAR(50) NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    stored_filename VARCHAR(255) NOT NULL,
    mime_type VARCHAR(100) NULL,
    file_size BIGINT NOT NULL,
    uploaded_by VARCHAR(50) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_employee_documents_employee
        FOREIGN KEY (employee_id)
        REFERENCES employees(employee_id)
        ON DELETE CASCADE,

    CONSTRAINT uq_employee_documents_stored_filename
        UNIQUE (stored_filename),

    INDEX idx_employee_documents_employee (employee_id),
    INDEX idx_employee_documents_type (document_type),
    INDEX idx_employee_documents_created_at (created_at)
);

SELECT
    document_id,
    employee_id,
    document_type,
    original_filename,
    file_size,
    uploaded_by,
    created_at
FROM employee_documents
ORDER BY created_at DESC, document_id DESC;
