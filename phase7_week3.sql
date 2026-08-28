-- Phase 7 - Week 3: Leave Management Module
-- Select the target database before running this migration.
-- No database name is hardcoded.
-- This migration preserves all existing employee, attendance, user and audit-log data.

CREATE TABLE IF NOT EXISTS leave_requests (
    leave_id INT AUTO_INCREMENT PRIMARY KEY,
    employee_id INT NOT NULL,
    leave_type VARCHAR(50) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    reason VARCHAR(500) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'Pending',
    requested_by VARCHAR(50) NULL,
    reviewed_by VARCHAR(50) NULL,
    reviewed_at DATETIME NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT fk_leave_requests_employee
        FOREIGN KEY (employee_id) REFERENCES employees(employee_id),

    INDEX idx_leave_employee (employee_id),
    INDEX idx_leave_status (status),
    INDEX idx_leave_dates (start_date, end_date)
);

SELECT
    leave_id, employee_id, leave_type, start_date, end_date,
    reason, status, requested_by, reviewed_by, reviewed_at, created_at
FROM leave_requests
ORDER BY created_at DESC, leave_id DESC;
