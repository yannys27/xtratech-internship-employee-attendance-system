USE employee_attendance_system;

-- Phase 7 - Week 2: Attendance Enhancement
-- Run this script ONCE on the existing database.
-- It does not delete existing employee, attendance, user or audit-log data.

ALTER TABLE attendance
    ADD COLUMN scheduled_start_time TIME NOT NULL DEFAULT '08:00:00' AFTER check_out_time,
    ADD COLUMN scheduled_end_time TIME NOT NULL DEFAULT '17:00:00' AFTER scheduled_start_time,
    ADD COLUMN total_working_hours DECIMAL(5,2) NULL AFTER scheduled_end_time,
    ADD COLUMN late_arrival_minutes INT NOT NULL DEFAULT 0 AFTER total_working_hours,
    ADD COLUMN early_departure_minutes INT NOT NULL DEFAULT 0 AFTER late_arrival_minutes,
    ADD COLUMN weekend_attendance BOOLEAN NOT NULL DEFAULT FALSE AFTER early_departure_minutes;

SET SQL_SAFE_UPDATES = 0;

UPDATE attendance
SET
    scheduled_start_time = '08:00:00',
    scheduled_end_time = '17:00:00',

    weekend_attendance = CASE
        WHEN DAYOFWEEK(date) IN (1, 7) THEN TRUE
        ELSE FALSE
    END,

    total_working_hours = CASE
        WHEN check_in_time IS NOT NULL
             AND check_out_time IS NOT NULL
        THEN ROUND(
            TIME_TO_SEC(
                TIMEDIFF(check_out_time, check_in_time)
            ) / 3600,
            2
        )
        ELSE NULL
    END,

    late_arrival_minutes = CASE
        WHEN check_in_time IS NOT NULL
             AND DAYOFWEEK(date) NOT IN (1, 7)
             AND check_in_time > '08:00:00'
        THEN FLOOR(
            TIME_TO_SEC(
                TIMEDIFF(check_in_time, '08:00:00')
            ) / 60
        )
        ELSE 0
    END,

    early_departure_minutes = CASE
        WHEN check_out_time IS NOT NULL
             AND DAYOFWEEK(date) NOT IN (1, 7)
             AND check_out_time < '17:00:00'
        THEN FLOOR(
            TIME_TO_SEC(
                TIMEDIFF('17:00:00', check_out_time)
            ) / 60
        )
        ELSE 0
    END,

    status = CASE
        WHEN check_in_time IS NULL
            THEN 'Absent'

        WHEN DAYOFWEEK(date) NOT IN (1, 7)
             AND check_in_time > '08:00:00'
            THEN 'Late'

        ELSE 'Present'
    END;

SET SQL_SAFE_UPDATES = 1;

SELECT
    attendance_id,
    employee_id,
    date,
    check_in_time,
    check_out_time,
    total_working_hours,
    late_arrival_minutes,
    early_departure_minutes,
    status,
    weekend_attendance
FROM attendance
ORDER BY date DESC, attendance_id DESC;