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
def leave_management_page():
    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT employee_id, employee_number, first_name, last_name
            FROM employees
            WHERE employment_status = 'Active'
            ORDER BY first_name, last_name
            """
        )
        employees = cursor.fetchall()

        cursor.execute(
            """
            SELECT
                leave_requests.leave_id,
                leave_requests.employee_id,
                employees.employee_number,
                employees.first_name,
                employees.last_name,
                leave_requests.leave_type,
                leave_requests.start_date,
                leave_requests.end_date,
                DATEDIFF(leave_requests.end_date, leave_requests.start_date) + 1 AS total_days,
                leave_requests.reason,
                leave_requests.status,
                leave_requests.requested_by,
                leave_requests.reviewed_by,
                leave_requests.reviewed_at,
                leave_requests.created_at,
                leave_requests.updated_at
            FROM leave_requests
            JOIN employees ON leave_requests.employee_id = employees.employee_id
            ORDER BY leave_requests.created_at DESC, leave_requests.leave_id DESC
            """
        )
        leave_requests = cursor.fetchall()

        return render_template(
            "leave_management.html",
            employees=employees,
            leave_requests=leave_requests,
            leave_types=sorted(ALLOWED_LEAVE_TYPES),
            username=session.get("username"),
            role=session.get("role"),
        )
    except Error as error:
        return render_template(
            "leave_management.html",
            employees=[],
            leave_requests=[],
            leave_types=sorted(ALLOWED_LEAVE_TYPES),
            username=session.get("username"),
            role=session.get("role"),
            error=f"Unable to load leave management: {error}",
        ), 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

@page_login_required
def create_leave_request_page():
    leave_request, validation_error = validate_leave_request_input(request.form)
    if validation_error:
        flash(validation_error, "error")
        return redirect(url_for("leave_management_page"))

    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            "SELECT employee_id, first_name, last_name FROM employees WHERE employee_id = %s",
            (leave_request["employee_id"],),
        )
        employee = cursor.fetchone()
        if not employee:
            flash("The selected employee does not exist.", "error")
            return redirect(url_for("leave_management_page"))

        cursor.execute(
            """
            INSERT INTO leave_requests (
                employee_id, leave_type, start_date, end_date, reason,
                status, requested_by
            ) VALUES (%s, %s, %s, %s, %s, 'Pending', %s)
            """,
            (
                leave_request["employee_id"],
                leave_request["leave_type"],
                leave_request["start_date"],
                leave_request["end_date"],
                leave_request["reason"],
                session.get("username"),
            ),
        )
        leave_id = cursor.lastrowid
        connection.commit()

        audit_log(
            "Leave request created",
            f"Leave ID: {leave_id}; employee ID: {leave_request['employee_id']}; "
            f"type: {leave_request['leave_type']}; {leave_request['start_date']} to {leave_request['end_date']}",
        )
        flash("Leave request created successfully and is pending review.", "success")
    except IntegrityError:
        flash("Unable to create leave request because the selected employee does not exist.", "error")
    except Error as error:
        flash(f"Unable to create leave request: {error}", "error")
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

    return redirect(url_for("leave_management_page"))

@page_leave_approver_required
def review_leave_request_page(leave_id, decision):
    decision_map = {"approve": "Approved", "reject": "Rejected"}
    new_status = decision_map.get(str(decision).lower())
    if not new_status:
        flash("Invalid leave review action.", "error")
        return redirect(url_for("leave_management_page"))

    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT leave_requests.leave_id, leave_requests.status, leave_requests.employee_id,
                   leave_requests.leave_type, leave_requests.start_date, leave_requests.end_date,
                   employees.first_name, employees.last_name
            FROM leave_requests
            JOIN employees ON leave_requests.employee_id = employees.employee_id
            WHERE leave_requests.leave_id = %s
            """,
            (leave_id,),
        )
        leave_request = cursor.fetchone()

        if not leave_request:
            flash("Leave request not found.", "error")
            return redirect(url_for("leave_management_page"))
        if leave_request["status"] != "Pending":
            flash("Only pending leave requests can be approved or rejected.", "error")
            return redirect(url_for("leave_management_page"))

        cursor.execute(
            """
            UPDATE leave_requests
            SET status = %s,
                reviewed_by = %s,
                reviewed_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE leave_id = %s
            """,
            (new_status, session.get("username"), leave_id),
        )
        connection.commit()

        audit_log(
            f"Leave request {new_status.lower()}",
            f"Leave ID: {leave_id}; employee ID: {leave_request['employee_id']}; "
            f"employee: {leave_request['first_name']} {leave_request['last_name']}; "
            f"type: {leave_request['leave_type']}; {leave_request['start_date']} to {leave_request['end_date']}",
        )
        flash(
            f"Leave request {new_status.lower()} successfully.",
            "success" if new_status == "Approved" else "warning",
        )
    except Error as error:
        flash(f"Unable to review leave request: {error}", "error")
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

    return redirect(url_for("leave_management_page"))

@api_login_required
def get_leave_requests():
    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                leave_requests.leave_id,
                leave_requests.employee_id,
                employees.employee_number,
                employees.first_name,
                employees.last_name,
                leave_requests.leave_type,
                leave_requests.start_date,
                leave_requests.end_date,
                leave_requests.reason,
                leave_requests.status,
                leave_requests.requested_by,
                leave_requests.reviewed_by,
                leave_requests.reviewed_at,
                leave_requests.created_at,
                leave_requests.updated_at
            FROM leave_requests
            JOIN employees ON leave_requests.employee_id = employees.employee_id
            ORDER BY leave_requests.created_at DESC, leave_requests.leave_id DESC
            """
        )
        return jsonify(cursor.fetchall())
    except Error:
        return jsonify({"error": "Unable to retrieve leave requests"}), 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

@api_login_required
def add_leave_request():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON request body is required."}), 400

    leave_request, validation_error = validate_leave_request_input(data)
    if validation_error:
        return jsonify({"error": validation_error}), 400

    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT employee_id FROM employees WHERE employee_id = %s",
            (leave_request["employee_id"],),
        )
        if not cursor.fetchone():
            return jsonify({"error": "The selected employee does not exist."}), 400

        cursor.execute(
            """
            INSERT INTO leave_requests (
                employee_id, leave_type, start_date, end_date, reason,
                status, requested_by
            ) VALUES (%s, %s, %s, %s, %s, 'Pending', %s)
            """,
            (
                leave_request["employee_id"],
                leave_request["leave_type"],
                leave_request["start_date"],
                leave_request["end_date"],
                leave_request["reason"],
                session.get("username"),
            ),
        )
        leave_id = cursor.lastrowid
        connection.commit()
        audit_log(
            "Leave request created",
            f"Leave ID: {leave_id}; employee ID: {leave_request['employee_id']}; "
            f"type: {leave_request['leave_type']}; {leave_request['start_date']} to {leave_request['end_date']}",
        )
        return jsonify({"message": "Leave request created successfully", "leave_id": leave_id, "status": "Pending"}), 201
    except Error:
        return jsonify({"error": "Unable to create leave request"}), 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

@api_leave_approver_required
def update_leave_request_status(leave_id):
    data = request.get_json(silent=True) or {}
    new_status = str(data.get("status", "")).strip().title()
    if new_status not in {"Approved", "Rejected"}:
        return jsonify({"error": "Status must be Approved or Rejected."}), 400

    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT leave_id, employee_id, leave_type, start_date, end_date, status FROM leave_requests WHERE leave_id = %s",
            (leave_id,),
        )
        leave_request = cursor.fetchone()
        if not leave_request:
            return jsonify({"error": "Leave request not found"}), 404
        if leave_request["status"] != "Pending":
            return jsonify({"error": "Only pending leave requests can be approved or rejected."}), 409

        cursor.execute(
            """
            UPDATE leave_requests
            SET status = %s, reviewed_by = %s, reviewed_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE leave_id = %s
            """,
            (new_status, session.get("username"), leave_id),
        )
        connection.commit()
        audit_log(
            f"Leave request {new_status.lower()}",
            f"Leave ID: {leave_id}; employee ID: {leave_request['employee_id']}; "
            f"type: {leave_request['leave_type']}; {leave_request['start_date']} to {leave_request['end_date']}",
        )
        return jsonify({"message": f"Leave request {new_status.lower()} successfully", "status": new_status})
    except Error:
        return jsonify({"error": "Unable to update leave request status"}), 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

