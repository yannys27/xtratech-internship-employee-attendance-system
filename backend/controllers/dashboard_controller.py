# Phase 7 - Week 8 Code Refactoring
# Generated from the complete corrected Week 7 backend (commit 609db26 baseline).
# Existing behavior is preserved; code is separated by responsibility.

import csv
import io
from datetime import date, datetime, time
from pathlib import Path

from flask import (
    Response, flash, jsonify, redirect, render_template, request,
    send_file, send_from_directory, session, url_for,
)
from mysql.connector import Error, IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from db import get_connection
from utilities.validators import (
    ADMIN_ROLE, HR_ROLE, ALLOWED_ROLES, ALLOWED_STATUSES, ALLOWED_GENDERS,
    ALLOWED_EMPLOYMENT_STATUSES, ALLOWED_LEAVE_TYPES, ALLOWED_LEAVE_STATUSES,
    normalize_role, validate_username_password_role, validate_employee_input,
    validate_leave_request_input, valid_date, parse_time,
)
from utilities.auth import (
    refresh_session_user, page_login_required, api_login_required,
    page_admin_required, api_admin_required, page_leave_approver_required,
    api_leave_approver_required, page_document_access_required,
)
from services.audit_service import audit_log
from services.attendance_service import (
    SCHEDULED_START_TIME, SCHEDULED_END_TIME, calculate_attendance_values,
    validate_attendance_input,
)
from services.file_service import (
    EMPLOYEE_UPLOAD_FOLDER, DOCUMENT_UPLOAD_FOLDER, ALLOWED_DOCUMENT_TYPES,
    validate_employee_photo, save_employee_photo, remove_employee_photo,
    validate_employee_document, detect_employee_document_mime,
    save_employee_document, remove_employee_document_file,
)
from services.report_service import (
    get_report_filters, fetch_attendance_report, report_query_string, display_value,
)
from models.employee_model import fetch_employee_by_id, fetch_departments
from models.document_model import fetch_employee_document
from models.user_model import count_active_administrators

@page_login_required
def dashboard():
    """Phase 7 Week 7 dashboard analytics."""
    stats = {
        "total_employees": 0,
        "attendance_today": 0,
        "present_today": 0,
        "absent_today": 0,
        "late_today": 0,
        "weekly_attendance": 0,
        "monthly_attendance": 0,
    }

    analytics = {
        "department_labels": [],
        "department_values": [],
        "today_status_labels": ["Present", "Late", "Absent"],
        "today_status_values": [0, 0, 0],
        "weekly_labels": [],
        "weekly_values": [],
        "monthly_labels": [],
        "monthly_values": [],
    }

    recent_activities = []
    dashboard_error = None

    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        # Summary statistics
        cursor.execute("SELECT COUNT(*) AS total FROM employees")
        stats["total_employees"] = int(cursor.fetchone()["total"] or 0)

        cursor.execute(
            "SELECT COUNT(DISTINCT employee_id) AS total FROM attendance WHERE date = CURDATE()"
        )
        stats["attendance_today"] = int(cursor.fetchone()["total"] or 0)

        cursor.execute(
            "SELECT COUNT(DISTINCT employee_id) AS total FROM attendance WHERE date = CURDATE() AND status = 'Present'"
        )
        stats["present_today"] = int(cursor.fetchone()["total"] or 0)

        cursor.execute(
            "SELECT COUNT(DISTINCT employee_id) AS total FROM attendance WHERE date = CURDATE() AND status = 'Absent'"
        )
        stats["absent_today"] = int(cursor.fetchone()["total"] or 0)

        cursor.execute(
            "SELECT COUNT(DISTINCT employee_id) AS total FROM attendance WHERE date = CURDATE() AND status = 'Late'"
        )
        stats["late_today"] = int(cursor.fetchone()["total"] or 0)

        cursor.execute(
            "SELECT COUNT(*) AS total FROM attendance WHERE YEARWEEK(date, 1) = YEARWEEK(CURDATE(), 1)"
        )
        stats["weekly_attendance"] = int(cursor.fetchone()["total"] or 0)

        cursor.execute(
            """
            SELECT COUNT(*) AS total
            FROM attendance
            WHERE YEAR(date) = YEAR(CURDATE())
              AND MONTH(date) = MONTH(CURDATE())
            """
        )
        stats["monthly_attendance"] = int(cursor.fetchone()["total"] or 0)

        # Employees per department
        cursor.execute(
            """
            SELECT
                COALESCE(departments.department_name, 'Unassigned') AS department_name,
                COUNT(employees.employee_id) AS total
            FROM employees
            LEFT JOIN departments
                ON employees.department_id = departments.department_id
            GROUP BY COALESCE(departments.department_name, 'Unassigned')
            ORDER BY department_name
            """
        )
        department_rows = cursor.fetchall()
        analytics["department_labels"] = [
            str(row["department_name"]) for row in department_rows
        ]
        analytics["department_values"] = [
            int(row["total"] or 0) for row in department_rows
        ]

        # Today's status distribution
        cursor.execute(
            """
            SELECT status, COUNT(DISTINCT employee_id) AS total
            FROM attendance
            WHERE date = CURDATE()
              AND status IN ('Present', 'Late', 'Absent')
            GROUP BY status
            """
        )
        today_lookup = {
            str(row["status"]): int(row["total"] or 0)
            for row in cursor.fetchall()
        }
        analytics["today_status_values"] = [
            today_lookup.get("Present", 0),
            today_lookup.get("Late", 0),
            today_lookup.get("Absent", 0),
        ]

        # Current-week attendance trend
        cursor.execute(
            """
            SELECT
                DATE_FORMAT(date, '%a %d') AS label,
                date AS attendance_date,
                COUNT(*) AS total
            FROM attendance
            WHERE YEARWEEK(date, 1) = YEARWEEK(CURDATE(), 1)
            GROUP BY date
            ORDER BY attendance_date
            """
        )
        weekly_rows = cursor.fetchall()
        analytics["weekly_labels"] = [str(row["label"]) for row in weekly_rows]
        analytics["weekly_values"] = [int(row["total"] or 0) for row in weekly_rows]

        # Current-month attendance trend
        cursor.execute(
            """
            SELECT
                DATE_FORMAT(date, '%d %b') AS label,
                date AS attendance_date,
                COUNT(*) AS total
            FROM attendance
            WHERE YEAR(date) = YEAR(CURDATE())
              AND MONTH(date) = MONTH(CURDATE())
            GROUP BY date
            ORDER BY attendance_date
            """
        )
        monthly_rows = cursor.fetchall()
        analytics["monthly_labels"] = [str(row["label"]) for row in monthly_rows]
        analytics["monthly_values"] = [int(row["total"] or 0) for row in monthly_rows]

        # Existing recent-attendance activity list
        cursor.execute(
            """
            SELECT
                attendance.attendance_id,
                employees.first_name,
                employees.last_name,
                attendance.date,
                attendance.check_in_time,
                attendance.check_out_time,
                attendance.scheduled_start_time,
                attendance.scheduled_end_time,
                attendance.total_working_hours,
                attendance.late_arrival_minutes,
                attendance.early_departure_minutes,
                attendance.weekend_attendance,
                attendance.status
            FROM attendance
            JOIN employees ON attendance.employee_id = employees.employee_id
            ORDER BY attendance.date DESC,
                     COALESCE(attendance.check_in_time, '00:00:00') DESC,
                     attendance.attendance_id DESC
            LIMIT 8
            """
        )
        recent_activities = cursor.fetchall()

    except Error as error:
        dashboard_error = f"Unable to load dashboard analytics: {error}"
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

    return render_template(
        "index.html",
        username=session.get("username"),
        role=session.get("role"),
        stats=stats,
        analytics=analytics,
        recent_activities=recent_activities,
        error=dashboard_error,
    )

