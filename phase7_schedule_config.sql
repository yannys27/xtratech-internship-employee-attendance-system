-- Phase 7 - Configurable Attendance Schedule Migration
-- Select the target database before executing this script.
-- Existing attendance records are preserved.
-- This removes the fixed database defaults for working schedule times.

ALTER TABLE attendance
    MODIFY COLUMN scheduled_start_time TIME NOT NULL,
    MODIFY COLUMN scheduled_end_time TIME NOT NULL;