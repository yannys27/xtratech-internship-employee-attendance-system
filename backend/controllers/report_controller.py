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
def reports_page():
    filters, validation_error = get_report_filters(request.args)
    departments = []
    records = []
    error = validation_error

    try:
        departments = fetch_departments()
        if not error:
            records = fetch_attendance_report(filters)
    except Error as db_error:
        error = f"Unable to load report data: {db_error}"

    safe_filters = filters or {
        "employee_name": request.args.get("employee_name", ""),
        "department_id": request.args.get("department_id", ""),
        "date_from": request.args.get("date_from", ""),
        "date_to": request.args.get("date_to", ""),
        "status": request.args.get("status", ""),
    }

    return render_template(
        "reports.html",
        username=session.get("username"),
        role=session.get("role"),
        departments=departments,
        records=records,
        filters=safe_filters,
        export_query=report_query_string(filters) if filters and not error else "",
        error=error,
    )

@page_login_required
def export_attendance_report(file_format):
    file_format = file_format.lower()
    if file_format not in {"csv", "xlsx", "pdf"}:
        flash("Unsupported export format.", "error")
        return redirect(url_for("reports_page"))

    filters, validation_error = get_report_filters(request.args)
    if validation_error:
        flash(validation_error, "error")
        return redirect(url_for("reports_page", **request.args))

    try:
        records = fetch_attendance_report(filters)
    except Error:
        flash("Unable to generate the report export.", "error")
        return redirect(url_for("reports_page", **request.args))

    filename_base = f"attendance_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    if file_format == "csv":
        text_stream = io.StringIO()
        writer = csv.writer(text_stream)
        writer.writerow(["Employee", "Department", "Date", "Check In", "Check Out", "Status"])
        for row in records:
            writer.writerow([
                f"{row['first_name']} {row['last_name']}",
                display_value(row.get("department_name")),
                display_value(row.get("date")),
                display_value(row.get("check_in_time")),
                display_value(row.get("check_out_time")),
                display_value(row.get("status")),
            ])

        csv_bytes = io.BytesIO(("\ufeff" + text_stream.getvalue()).encode("utf-8"))
        csv_bytes.seek(0)
        audit_log("Attendance report exported", f"Format: CSV; rows: {len(records)}; filters: {filters}")
        return send_file(
            csv_bytes,
            as_attachment=True,
            download_name=f"{filename_base}.csv",
            mimetype="text/csv; charset=utf-8",
        )

    if file_format == "xlsx":
        from openpyxl import Workbook
        from openpyxl.styles import Font

        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = "Attendance Report"
        headers = ["Employee", "Department", "Date", "Check In", "Check Out", "Status"]
        worksheet.append(headers)
        for cell in worksheet[1]:
            cell.font = Font(bold=True)

        for row in records:
            worksheet.append([
                f"{row['first_name']} {row['last_name']}",
                display_value(row.get("department_name")),
                display_value(row.get("date")),
                display_value(row.get("check_in_time")),
                display_value(row.get("check_out_time")),
                display_value(row.get("status")),
            ])

        widths = [28, 22, 14, 14, 14, 14]
        for index, width in enumerate(widths, start=1):
            worksheet.column_dimensions[chr(64 + index)].width = width

        output = io.BytesIO()
        workbook.save(output)
        output.seek(0)
        audit_log("Attendance report exported", f"Format: XLSX; rows: {len(records)}; filters: {filters}")
        return send_file(
            output,
            as_attachment=True,
            download_name=f"{filename_base}.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    # PDF
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    output = io.BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=landscape(A4),
        rightMargin=10 * mm,
        leftMargin=10 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
    )
    styles = getSampleStyleSheet()
    story = [Paragraph("Attendance Report", styles["Title"]), Spacer(1, 5 * mm)]

    active_filter_parts = []
    if filters.get("employee_name"):
        active_filter_parts.append(f"Employee: {filters['employee_name']}")
    if filters.get("department_id"):
        active_filter_parts.append(f"Department ID: {filters['department_id']}")
    if filters.get("date_from"):
        active_filter_parts.append(f"From: {filters['date_from']}")
    if filters.get("date_to"):
        active_filter_parts.append(f"To: {filters['date_to']}")
    if filters.get("status"):
        active_filter_parts.append(f"Status: {filters['status']}")
    if active_filter_parts:
        story.append(Paragraph("Filters: " + " | ".join(active_filter_parts), styles["Normal"]))
        story.append(Spacer(1, 4 * mm))

    table_data = [["Employee", "Department", "Date", "Check In", "Check Out", "Status"]]
    for row in records:
        table_data.append([
            f"{row['first_name']} {row['last_name']}",
            display_value(row.get("department_name")),
            display_value(row.get("date")),
            display_value(row.get("check_in_time")),
            display_value(row.get("check_out_time")),
            display_value(row.get("status")),
        ])

    table = Table(table_data, repeatRows=1, colWidths=[52 * mm, 42 * mm, 28 * mm, 28 * mm, 28 * mm, 28 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E9ECEF")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(table)
    document.build(story)
    output.seek(0)
    audit_log("Attendance report exported", f"Format: PDF; rows: {len(records)}; filters: {filters}")
    return send_file(
        output,
        as_attachment=True,
        download_name=f"{filename_base}.pdf",
        mimetype="application/pdf",
    )

@api_login_required
def employee_listing_report():
    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                employees.employee_id,
                employees.first_name,
                employees.last_name,
                employees.email,
                employees.phone,
                departments.department_name
            FROM employees
            LEFT JOIN departments ON employees.department_id = departments.department_id
            ORDER BY employees.employee_id ASC
            """
        )
        return jsonify(cursor.fetchall())
    except Error:
        return jsonify({"error": "Unable to generate employee report"}), 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

@api_login_required
def attendance_report():
    filters, validation_error = get_report_filters(request.args)
    if validation_error:
        return jsonify({"error": validation_error}), 400
    try:
        return jsonify(fetch_attendance_report(filters))
    except Error:
        return jsonify({"error": "Unable to generate attendance report"}), 500

@api_login_required
def attendance_by_status(status):
    normalized_status = status.strip().title()
    if normalized_status not in ALLOWED_STATUSES:
        return jsonify({"error": "Invalid attendance status"}), 400
    try:
        return jsonify(fetch_attendance_report({
            "employee_name": "",
            "department_id": "",
            "date_from": "",
            "date_to": "",
            "status": normalized_status,
        }))
    except Error:
        return jsonify({"error": "Unable to filter attendance records"}), 500

@api_login_required
def search_employees():
    keyword = request.args.get("q", "").strip()
    if len(keyword) > 100:
        return jsonify({"error": "Search text must not exceed 100 characters."}), 400
    search_value = f"%{keyword}%"

    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                employees.employee_id,
                employees.employee_number,
                employees.national_id_passport,
                employees.first_name,
                employees.last_name,
                employees.email,
                employees.phone,
                employees.job_position,
                employees.employment_status,
                departments.department_name,
                employees.photo_filename
            FROM employees
            LEFT JOIN departments ON employees.department_id = departments.department_id
            WHERE employees.employee_number LIKE %s
               OR employees.national_id_passport LIKE %s
               OR employees.first_name LIKE %s
               OR employees.last_name LIKE %s
               OR employees.email LIKE %s
               OR employees.job_position LIKE %s
               OR departments.department_name LIKE %s
            ORDER BY employees.employee_id ASC
            """,
            (search_value, search_value, search_value, search_value, search_value, search_value, search_value),
        )
        return jsonify(cursor.fetchall())
    except Error:
        return jsonify({"error": "Unable to search employees"}), 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

@api_login_required
def search_attendance():
    # Supports the new Phase 6 filters and the old ?date=YYYY-MM-DD parameter.
    args = request.args.to_dict()
    if args.get("date") and not args.get("date_from") and not args.get("date_to"):
        args["date_from"] = args["date"]
        args["date_to"] = args["date"]

    filters, validation_error = get_report_filters(args)
    if validation_error:
        return jsonify({"error": validation_error}), 400
    try:
        return jsonify(fetch_attendance_report(filters))
    except Error:
        return jsonify({"error": "Unable to search attendance records"}), 500

