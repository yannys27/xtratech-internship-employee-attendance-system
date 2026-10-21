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

@page_admin_required
def audit_log_page():
    filters = {
        "q": request.args.get("q", "").strip(),
        "username": request.args.get("username", "").strip(),
        "role": request.args.get("role", "").strip(),
        "module": request.args.get("module", "").strip(),
        "action": request.args.get("action", "").strip(),
        "date_from": request.args.get("date_from", "").strip(),
        "date_to": request.args.get("date_to", "").strip(),
    }

    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        query = """
            SELECT
                audit_id,
                username,
                role,
                action,
                details,
                ip_address,
                affected_record,
                module,
                created_at
            FROM audit_log
            WHERE 1 = 1
        """
        params = []

        if filters["q"]:
            search_value = f"%{filters['q']}%"
            query += """
                AND (
                    username LIKE %s
                    OR role LIKE %s
                    OR action LIKE %s
                    OR COALESCE(details, '') LIKE %s
                    OR COALESCE(ip_address, '') LIKE %s
                    OR COALESCE(affected_record, '') LIKE %s
                    OR COALESCE(module, '') LIKE %s
                )
            """
            params.extend([search_value] * 7)

        if filters["username"]:
            query += " AND username = %s"
            params.append(filters["username"])

        if filters["role"]:
            query += " AND role = %s"
            params.append(filters["role"])

        if filters["module"]:
            query += " AND module = %s"
            params.append(filters["module"])

        if filters["action"]:
            query += " AND action = %s"
            params.append(filters["action"])

        if filters["date_from"]:
            if not valid_date(filters["date_from"]):
                flash("From date must be a valid date.", "error")
                filters["date_from"] = ""
            else:
                query += " AND DATE(created_at) >= %s"
                params.append(filters["date_from"])

        if filters["date_to"]:
            if not valid_date(filters["date_to"]):
                flash("To date must be a valid date.", "error")
                filters["date_to"] = ""
            else:
                query += " AND DATE(created_at) <= %s"
                params.append(filters["date_to"])

        if filters["date_from"] and filters["date_to"]:
            start_date = datetime.strptime(filters["date_from"], "%Y-%m-%d").date()
            end_date = datetime.strptime(filters["date_to"], "%Y-%m-%d").date()
            if end_date < start_date:
                flash("To date cannot be earlier than From date.", "error")
                return redirect(url_for("audit_log_page"))

        query += " ORDER BY created_at DESC, audit_id DESC LIMIT 500"
        cursor.execute(query, tuple(params))
        logs = cursor.fetchall()

        cursor.execute(
            "SELECT DISTINCT username FROM audit_log "
            "WHERE username IS NOT NULL AND username <> '' ORDER BY username"
        )
        usernames = [row["username"] for row in cursor.fetchall()]

        cursor.execute(
            "SELECT DISTINCT role FROM audit_log "
            "WHERE role IS NOT NULL AND role <> '' ORDER BY role"
        )
        roles = [row["role"] for row in cursor.fetchall()]

        cursor.execute(
            "SELECT DISTINCT module FROM audit_log "
            "WHERE module IS NOT NULL AND module <> '' ORDER BY module"
        )
        modules = [row["module"] for row in cursor.fetchall()]

        cursor.execute(
            "SELECT DISTINCT action FROM audit_log "
            "WHERE action IS NOT NULL AND action <> '' ORDER BY action"
        )
        actions = [row["action"] for row in cursor.fetchall()]

        return render_template(
            "audit_log.html",
            logs=logs,
            filters=filters,
            usernames=usernames,
            roles=roles,
            modules=modules,
            actions=actions,
            username=session.get("username"),
            role=session.get("role"),
        )
    except Error as error:
        return render_template(
            "audit_log.html",
            logs=[],
            filters=filters,
            usernames=[],
            roles=[],
            modules=[],
            actions=[],
            username=session.get("username"),
            role=session.get("role"),
            error=f"Unable to load audit log: {error}",
        ), 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

