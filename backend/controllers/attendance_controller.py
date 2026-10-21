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
def attendance_page():
    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                attendance.attendance_id,
                attendance.employee_id,
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
            ORDER BY attendance.date DESC, attendance.attendance_id DESC
            """
        )
        attendance_records = cursor.fetchall()

        cursor.execute(
            """
            SELECT employee_id, employee_number, first_name, last_name
            FROM employees
            WHERE employment_status = 'Active'
            ORDER BY first_name, last_name
            """
        )
        employees = cursor.fetchall()

        return render_template(
            "attendance.html",
            attendance=attendance_records,
            employees=employees,
            username=session.get("username"),
            role=session.get("role"),
            today=date.today().isoformat(),
            scheduled_start=SCHEDULED_START_TIME.strftime("%H:%M"),
            scheduled_end=SCHEDULED_END_TIME.strftime("%H:%M"),
        )
    except Error as error:
        return render_template(
            "attendance.html",
            attendance=[],
            employees=[],
            error=f"Unable to load attendance records: {error}",
            username=session.get("username"),
            role=session.get("role"),
            today=date.today().isoformat(),
            scheduled_start=SCHEDULED_START_TIME.strftime("%H:%M"),
            scheduled_end=SCHEDULED_END_TIME.strftime("%H:%M"),
        ), 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

@page_login_required
def create_attendance_page():
    attendance, validation_error = validate_attendance_input(request.form)
    if validation_error:
        flash(validation_error, "error")
        return redirect(url_for("attendance_page"))

    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO attendance (
                employee_id, date, check_in_time, check_out_time, status,
                scheduled_start_time, scheduled_end_time, total_working_hours,
                late_arrival_minutes, early_departure_minutes, weekend_attendance
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                attendance["employee_id"], attendance["date"],
                attendance["check_in_time"], attendance["check_out_time"],
                attendance["status"], attendance["scheduled_start_time"],
                attendance["scheduled_end_time"], attendance["total_working_hours"],
                attendance["late_arrival_minutes"], attendance["early_departure_minutes"],
                attendance["weekend_attendance"],
            ),
        )
        attendance_id = cursor.lastrowid
        connection.commit()
        audit_log(
            "Attendance record created",
            f"Attendance ID: {attendance_id}; employee ID: {attendance['employee_id']}; "
            f"date: {attendance['date']}; status: {attendance['status']}; "
            f"hours: {attendance['total_working_hours']}",
        )
        flash("Attendance saved and calculated automatically.", "success")
    except IntegrityError:
        flash("The selected employee does not exist.", "error")
    except Error as error:
        flash(f"Unable to save attendance record: {error}", "error")
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()
    return redirect(url_for("attendance_page"))

@page_login_required
def attendance_check_in_now():
    employee_id = request.form.get("employee_id")
    now = datetime.now()
    payload = {
        "employee_id": employee_id,
        "date": now.date().isoformat(),
        "check_in_time": now.strftime("%H:%M:%S"),
        "check_out_time": None,
    }
    attendance, validation_error = validate_attendance_input(payload)
    if validation_error:
        flash(validation_error, "error")
        return redirect(url_for("attendance_page"))

    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT attendance_id, check_in_time, check_out_time FROM attendance WHERE employee_id = %s AND date = %s ORDER BY attendance_id DESC LIMIT 1",
            (attendance["employee_id"], attendance["date"]),
        )
        existing = cursor.fetchone()
        if existing and existing["check_in_time"]:
            flash("This employee is already checked in today.", "error")
            return redirect(url_for("attendance_page"))

        if existing:
            cursor.execute(
                """
                UPDATE attendance
                SET check_in_time=%s, status=%s, scheduled_start_time=%s, scheduled_end_time=%s,
                    total_working_hours=%s, late_arrival_minutes=%s, early_departure_minutes=%s, weekend_attendance=%s
                WHERE attendance_id=%s
                """,
                (
                    attendance["check_in_time"], attendance["status"], attendance["scheduled_start_time"],
                    attendance["scheduled_end_time"], attendance["total_working_hours"],
                    attendance["late_arrival_minutes"], attendance["early_departure_minutes"],
                    attendance["weekend_attendance"], existing["attendance_id"],
                ),
            )
            attendance_id = existing["attendance_id"]
        else:
            cursor.execute(
                """
                INSERT INTO attendance (
                    employee_id, date, check_in_time, check_out_time, status,
                    scheduled_start_time, scheduled_end_time, total_working_hours,
                    late_arrival_minutes, early_departure_minutes, weekend_attendance
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    attendance["employee_id"], attendance["date"], attendance["check_in_time"],
                    attendance["check_out_time"], attendance["status"], attendance["scheduled_start_time"],
                    attendance["scheduled_end_time"], attendance["total_working_hours"],
                    attendance["late_arrival_minutes"], attendance["early_departure_minutes"],
                    attendance["weekend_attendance"],
                ),
            )
            attendance_id = cursor.lastrowid
        connection.commit()
        audit_log("Employee checked in", f"Attendance ID: {attendance_id}; employee ID: {attendance['employee_id']}; time: {attendance['check_in_time']}; status: {attendance['status']}")
        flash(f"Check-in recorded at {now.strftime('%H:%M:%S')}. Status: {attendance['status']}.", "success")
    except Error as error:
        flash(f"Unable to record check-in: {error}", "error")
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()
    return redirect(url_for("attendance_page"))

@page_login_required
def attendance_check_out_now():
    employee_id = request.form.get("employee_id")
    now = datetime.now()
    connection = None
    cursor = None
    try:
        employee_id = int(employee_id)
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT * FROM attendance
            WHERE employee_id = %s AND date = %s
            ORDER BY attendance_id DESC LIMIT 1
            """,
            (employee_id, now.date().isoformat()),
        )
        existing = cursor.fetchone()
        if not existing or not existing.get("check_in_time"):
            flash("This employee must check in before checking out.", "error")
            return redirect(url_for("attendance_page"))
        if existing.get("check_out_time"):
            flash("This employee is already checked out today.", "error")
            return redirect(url_for("attendance_page"))

        payload = {
            "employee_id": employee_id,
            "date": now.date().isoformat(),
            "check_in_time": str(existing["check_in_time"]),
            "check_out_time": now.strftime("%H:%M:%S"),
        }
        attendance, validation_error = validate_attendance_input(payload)
        if validation_error:
            flash(validation_error, "error")
            return redirect(url_for("attendance_page"))

        cursor.execute(
            """
            UPDATE attendance
            SET check_out_time=%s, status=%s, scheduled_start_time=%s, scheduled_end_time=%s,
                total_working_hours=%s, late_arrival_minutes=%s, early_departure_minutes=%s, weekend_attendance=%s
            WHERE attendance_id=%s
            """,
            (
                attendance["check_out_time"], attendance["status"], attendance["scheduled_start_time"],
                attendance["scheduled_end_time"], attendance["total_working_hours"],
                attendance["late_arrival_minutes"], attendance["early_departure_minutes"],
                attendance["weekend_attendance"], existing["attendance_id"],
            ),
        )
        connection.commit()
        audit_log(
            "Employee checked out",
            f"Attendance ID: {existing['attendance_id']}; employee ID: {employee_id}; time: {attendance['check_out_time']}; "
            f"hours: {attendance['total_working_hours']}; early departure: {attendance['early_departure_minutes']} min",
        )
        flash(f"Check-out recorded at {now.strftime('%H:%M:%S')}. Total working hours: {attendance['total_working_hours']}.", "success")
    except (TypeError, ValueError):
        flash("Please select a valid employee.", "error")
    except Error as error:
        flash(f"Unable to record check-out: {error}", "error")
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()
    return redirect(url_for("attendance_page"))

@page_login_required
def delete_attendance_page(attendance_id):
    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM attendance WHERE attendance_id = %s", (attendance_id,))
        attendance = cursor.fetchone()
        if not attendance:
            flash("Attendance record not found.", "error")
            return redirect(url_for("attendance_page"))
        cursor.execute("DELETE FROM attendance WHERE attendance_id = %s", (attendance_id,))
        connection.commit()
        audit_log("Attendance record deleted", f"Attendance ID: {attendance_id}; employee ID: {attendance['employee_id']}; date: {attendance['date']}")
        flash("Attendance record deleted successfully.", "success")
    except Error as error:
        flash(f"Unable to delete attendance record: {error}", "error")
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()
    return redirect(url_for("attendance_page"))

@api_login_required
def get_attendance():
    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                attendance.attendance_id,
                attendance.employee_id,
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
            ORDER BY attendance.date DESC, attendance.attendance_id DESC
            """
        )
        return jsonify(cursor.fetchall())
    except Error:
        return jsonify({"error": "Unable to retrieve attendance records"}), 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

@api_login_required
def add_attendance():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON request body is required."}), 400

    attendance, validation_error = validate_attendance_input(data)
    if validation_error:
        return jsonify({"error": validation_error}), 400

    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO attendance (
                employee_id, date, check_in_time, check_out_time, status,
                scheduled_start_time, scheduled_end_time, total_working_hours,
                late_arrival_minutes, early_departure_minutes, weekend_attendance
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                attendance["employee_id"], attendance["date"], attendance["check_in_time"],
                attendance["check_out_time"], attendance["status"],
                attendance["scheduled_start_time"], attendance["scheduled_end_time"],
                attendance["total_working_hours"], attendance["late_arrival_minutes"],
                attendance["early_departure_minutes"], attendance["weekend_attendance"],
            ),
        )
        attendance_id = cursor.lastrowid
        connection.commit()
        audit_log(
            "Attendance record created",
            f"Attendance ID: {attendance_id}; employee ID: {attendance['employee_id']}; date: {attendance['date']}; status: {attendance['status']}",
        )
        return jsonify({"message": "Attendance added successfully", "attendance_id": attendance_id}), 201
    except IntegrityError:
        return jsonify({"error": "The selected employee does not exist."}), 400
    except Error:
        return jsonify({"error": "Unable to add attendance record"}), 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

@api_login_required
def update_attendance(attendance_id):
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON request body is required."}), 400

    attendance, validation_error = validate_attendance_input(data)
    if validation_error:
        return jsonify({"error": validation_error}), 400

    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM attendance WHERE attendance_id = %s", (attendance_id,))
        existing = cursor.fetchone()
        if not existing:
            return jsonify({"error": "Attendance record not found"}), 404

        cursor.execute(
            """
            UPDATE attendance
            SET employee_id = %s, date = %s, check_in_time = %s, check_out_time = %s, status = %s,
                scheduled_start_time = %s, scheduled_end_time = %s, total_working_hours = %s,
                late_arrival_minutes = %s, early_departure_minutes = %s, weekend_attendance = %s
            WHERE attendance_id = %s
            """,
            (
                attendance["employee_id"], attendance["date"], attendance["check_in_time"],
                attendance["check_out_time"], attendance["status"],
                attendance["scheduled_start_time"], attendance["scheduled_end_time"],
                attendance["total_working_hours"], attendance["late_arrival_minutes"],
                attendance["early_departure_minutes"], attendance["weekend_attendance"], attendance_id,
            ),
        )
        connection.commit()
        audit_log(
            "Attendance record updated",
            f"Attendance ID: {attendance_id}; employee ID: {attendance['employee_id']}; date: {attendance['date']}; status: {attendance['status']}",
        )
        return jsonify({"message": "Attendance updated successfully"})
    except IntegrityError:
        return jsonify({"error": "The selected employee does not exist."}), 400
    except Error:
        return jsonify({"error": "Unable to update attendance record"}), 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

@api_login_required
def delete_attendance(attendance_id):
    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM attendance WHERE attendance_id = %s", (attendance_id,))
        attendance = cursor.fetchone()
        if not attendance:
            return jsonify({"error": "Attendance record not found"}), 404

        cursor.execute("DELETE FROM attendance WHERE attendance_id = %s", (attendance_id,))
        connection.commit()
        audit_log(
            "Attendance record deleted",
            f"Attendance ID: {attendance_id}; employee ID: {attendance['employee_id']}; date: {attendance['date']}; status: {attendance['status']}",
        )
        return jsonify({"message": "Attendance deleted successfully"})
    except Error:
        return jsonify({"error": "Unable to delete attendance record"}), 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

