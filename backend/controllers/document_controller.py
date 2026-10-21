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

@page_document_access_required
def employee_documents_page():
    employee_filter = str(request.args.get("employee_id", "")).strip()
    document_type_filter = str(request.args.get("document_type", "")).strip()

    connection = None
    cursor = None

    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT employee_id, employee_number, first_name, last_name
            FROM employees
            ORDER BY first_name, last_name
            """
        )
        employees = cursor.fetchall()

        query = """
            SELECT
                employee_documents.document_id,
                employee_documents.employee_id,
                employee_documents.document_type,
                employee_documents.original_filename,
                employee_documents.mime_type,
                employee_documents.file_size,
                employee_documents.uploaded_by,
                employee_documents.created_at,
                employees.employee_number,
                employees.first_name,
                employees.last_name
            FROM employee_documents
            JOIN employees
                ON employee_documents.employee_id = employees.employee_id
            WHERE 1 = 1
        """
        params = []

        if employee_filter:
            try:
                employee_id = int(employee_filter)
                if employee_id <= 0:
                    raise ValueError
                query += " AND employee_documents.employee_id = %s"
                params.append(employee_id)
            except ValueError:
                flash("Please select a valid employee.", "error")
                employee_filter = ""

        if document_type_filter:
            if document_type_filter not in ALLOWED_DOCUMENT_TYPES:
                flash("Please select a valid document type.", "error")
                document_type_filter = ""
            else:
                query += " AND employee_documents.document_type = %s"
                params.append(document_type_filter)

        query += """
            ORDER BY
                employee_documents.created_at DESC,
                employee_documents.document_id DESC
        """

        cursor.execute(query, tuple(params))
        documents = cursor.fetchall()

        return render_template(
            "employee_documents.html",
            employees=employees,
            documents=documents,
            document_types=[
                "Employment Contract",
                "Curriculum Vitae (CV)",
                "Passport / National ID",
                "Certificates",
                "Employee Photograph",
            ],
            filters={
                "employee_id": employee_filter,
                "document_type": document_type_filter,
            },
            username=session.get("username"),
            role=session.get("role"),
        )

    except Error as error:
        return render_template(
            "employee_documents.html",
            employees=[],
            documents=[],
            document_types=[
                "Employment Contract",
                "Curriculum Vitae (CV)",
                "Passport / National ID",
                "Certificates",
                "Employee Photograph",
            ],
            filters={
                "employee_id": employee_filter,
                "document_type": document_type_filter,
            },
            username=session.get("username"),
            role=session.get("role"),
            error=f"Unable to load employee documents: {error}",
        ), 500

    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

@page_document_access_required
def upload_employee_document():
    employee_id_raw = str(request.form.get("employee_id", "")).strip()
    document_type = str(request.form.get("document_type", "")).strip()
    file_storage = request.files.get("document")

    try:
        employee_id = int(employee_id_raw)
        if employee_id <= 0:
            raise ValueError
    except ValueError:
        flash("Please select a valid employee.", "error")
        return redirect(url_for("employee_documents_page"))

    validation_error, detected_mime_type = validate_employee_document(
        file_storage, document_type
    )
    if validation_error:
        flash(validation_error, "error")
        return redirect(url_for("employee_documents_page", employee_id=employee_id))

    connection = None
    cursor = None
    stored_filename = None

    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT employee_id, employee_number, first_name, last_name
            FROM employees
            WHERE employee_id = %s
            """,
            (employee_id,),
        )
        employee = cursor.fetchone()

        if not employee:
            flash("The selected employee does not exist.", "error")
            return redirect(url_for("employee_documents_page"))

        stored_filename, original_filename = save_employee_document(file_storage)

        file_size = (DOCUMENT_UPLOAD_FOLDER / stored_filename).stat().st_size
        # Store the server-detected MIME type, never the client-provided value.
        mime_type = str(detected_mime_type or "application/octet-stream")[:100]

        cursor.execute(
            """
            INSERT INTO employee_documents (
                employee_id,
                document_type,
                original_filename,
                stored_filename,
                mime_type,
                file_size,
                uploaded_by
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                employee_id,
                document_type,
                original_filename,
                stored_filename,
                mime_type,
                file_size,
                session.get("username"),
            ),
        )
        document_id = cursor.lastrowid
        connection.commit()

        audit_log(
            "Employee document uploaded",
            f"Document ID: {document_id}; Employee ID: {employee_id}; "
            f"employee: {employee['first_name']} {employee['last_name']}; "
            f"type: {document_type}; file: {original_filename}",
            module="Employee Documents",
            affected_record=f"Employee Document #{document_id}",
        )

        flash("Employee document uploaded successfully.", "success")

    except Error as error:
        if stored_filename:
            remove_employee_document_file(stored_filename)
        flash(f"Unable to upload employee document: {error}", "error")

    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

    return redirect(url_for("employee_documents_page", employee_id=employee_id))

@page_document_access_required
def view_employee_document(document_id):
    try:
        document = fetch_employee_document(document_id)

        if not document:
            flash("Employee document not found.", "error")
            return redirect(url_for("employee_documents_page"))

        stored_filename = Path(str(document["stored_filename"])).name
        target = DOCUMENT_UPLOAD_FOLDER / stored_filename

        if not target.is_file():
            flash("The stored document file could not be found.", "error")
            return redirect(
                url_for("employee_documents_page", employee_id=document["employee_id"])
            )

        audit_log(
            "Employee document viewed",
            f"Document ID: {document_id}; Employee ID: {document['employee_id']}; "
            f"type: {document['document_type']}; file: {document['original_filename']}",
            module="Employee Documents",
            affected_record=f"Employee Document #{document_id}",
        )

        return send_from_directory(
            DOCUMENT_UPLOAD_FOLDER,
            stored_filename,
            as_attachment=False,
            download_name=document["original_filename"],
            mimetype=document["mime_type"] or None,
        )

    except Error as error:
        flash(f"Unable to open employee document: {error}", "error")
        return redirect(url_for("employee_documents_page"))

@page_document_access_required
def download_employee_document(document_id):
    try:
        document = fetch_employee_document(document_id)

        if not document:
            flash("Employee document not found.", "error")
            return redirect(url_for("employee_documents_page"))

        stored_filename = Path(str(document["stored_filename"])).name
        target = DOCUMENT_UPLOAD_FOLDER / stored_filename

        if not target.is_file():
            flash("The stored document file could not be found.", "error")
            return redirect(
                url_for("employee_documents_page", employee_id=document["employee_id"])
            )

        audit_log(
            "Employee document downloaded",
            f"Document ID: {document_id}; Employee ID: {document['employee_id']}; "
            f"type: {document['document_type']}; file: {document['original_filename']}",
            module="Employee Documents",
            affected_record=f"Employee Document #{document_id}",
        )

        return send_from_directory(
            DOCUMENT_UPLOAD_FOLDER,
            stored_filename,
            as_attachment=True,
            download_name=document["original_filename"],
            mimetype=document["mime_type"] or None,
        )

    except Error as error:
        flash(f"Unable to download employee document: {error}", "error")
        return redirect(url_for("employee_documents_page"))

@page_document_access_required
def delete_employee_document(document_id):
    connection = None
    cursor = None
    document = None

    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT
                employee_documents.document_id,
                employee_documents.employee_id,
                employee_documents.document_type,
                employee_documents.original_filename,
                employee_documents.stored_filename,
                employees.first_name,
                employees.last_name
            FROM employee_documents
            JOIN employees
                ON employee_documents.employee_id = employees.employee_id
            WHERE employee_documents.document_id = %s
            """,
            (document_id,),
        )
        document = cursor.fetchone()

        if not document:
            flash("Employee document not found.", "error")
            return redirect(url_for("employee_documents_page"))

        cursor.execute(
            "DELETE FROM employee_documents WHERE document_id = %s",
            (document_id,),
        )
        connection.commit()

        remove_employee_document_file(document["stored_filename"])

        audit_log(
            "Employee document deleted",
            f"Document ID: {document_id}; Employee ID: {document['employee_id']}; "
            f"employee: {document['first_name']} {document['last_name']}; "
            f"type: {document['document_type']}; file: {document['original_filename']}",
            module="Employee Documents",
            affected_record=f"Employee Document #{document_id}",
        )

        flash("Employee document deleted successfully.", "success")

    except Error as error:
        flash(f"Unable to delete employee document: {error}", "error")

    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

    if document:
        return redirect(
            url_for("employee_documents_page", employee_id=document["employee_id"])
        )

    return redirect(url_for("employee_documents_page"))

