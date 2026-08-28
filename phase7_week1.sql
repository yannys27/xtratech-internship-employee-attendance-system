

ALTER TABLE employees
    ADD COLUMN employee_number VARCHAR(30) NULL AFTER employee_id,
    ADD COLUMN national_id_passport VARCHAR(50) NULL AFTER employee_number,
    ADD COLUMN date_of_birth DATE NULL AFTER last_name,
    ADD COLUMN gender VARCHAR(30) NULL AFTER date_of_birth,
    ADD COLUMN residential_address VARCHAR(255) NULL AFTER gender,
    MODIFY COLUMN phone VARCHAR(30) NULL,
    ADD COLUMN job_position VARCHAR(100) NULL AFTER phone,
    ADD COLUMN hire_date DATE NULL AFTER department_id,
    ADD COLUMN employment_status VARCHAR(20) NOT NULL DEFAULT 'Active' AFTER hire_date,
    ADD COLUMN photo_filename VARCHAR(255) NULL AFTER employment_status;

SET SQL_SAFE_UPDATES = 0;

UPDATE employees
SET employee_number = CONCAT('EMP', LPAD(employee_id, 5, '0'))
WHERE employee_number IS NULL
   OR TRIM(employee_number) = '';

SET SQL_SAFE_UPDATES = 1;

ALTER TABLE employees
    ADD CONSTRAINT uq_employees_employee_number
        UNIQUE (employee_number),
    ADD CONSTRAINT uq_employees_national_id_passport
        UNIQUE (national_id_passport);