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
def employees_page():
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
                employees.first_name,
                employees.last_name,
                employees.email,
                employees.phone,
                employees.job_position,
                employees.employment_status,
                employees.photo_filename,
                departments.department_name
            FROM employees
            LEFT JOIN departments ON employees.department_id = departments.department_id
            ORDER BY employees.employee_id ASC
            """
        )
        employees = cursor.fetchall()
        cursor.execute("SELECT department_id, department_name FROM departments ORDER BY department_name")
        departments = cursor.fetchall()
        return render_template(
            "employees.html",
            employees=employees,
            departments=departments,
            username=session.get("username"),
            role=session.get("role"),
            genders=sorted(ALLOWED_GENDERS),
            employment_statuses=["Active", "Inactive"],
        )
    except Error as error:
        return render_template(
            "employees.html",
            employees=[],
            departments=[],
            error=f"Unable to load employees: {error}",
            username=session.get("username"),
            role=session.get("role"),
            genders=sorted(ALLOWED_GENDERS),
            employment_statuses=["Active", "Inactive"],
        ), 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

@page_login_required
def employee_photo(filename):
    return send_from_directory(EMPLOYEE_UPLOAD_FOLDER, Path(filename).name)

@page_login_required
def create_employee_page():
    employee, validation_error = validate_employee_input(request.form)
    if validation_error:
        flash(validation_error, "error")
        return redirect(url_for("employees_page"))

    photo = request.files.get("photo")
    if photo and photo.filename and session.get("role") != ADMIN_ROLE:
        flash("Only Administrators can upload employee photographs.", "error")
        return redirect(url_for("employees_page"))
    photo_error = validate_employee_photo(photo)
    if photo_error:
        flash(photo_error, "error")
        return redirect(url_for("employees_page"))

    photo_filename = None
    connection = None
    cursor = None
    try:
        if photo and photo.filename:
            photo_filename = save_employee_photo(photo)

        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO employees (
                employee_number, national_id_passport, first_name, last_name,
                date_of_birth, gender, residential_address, phone, email,
                job_position, department_id, hire_date, employment_status, photo_filename
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                employee["employee_number"], employee["national_id_passport"],
                employee["first_name"], employee["last_name"], employee["date_of_birth"],
                employee["gender"], employee["residential_address"], employee["phone"],
                employee["email"], employee["job_position"], employee["department_id"],
                employee["hire_date"], employee["employment_status"], photo_filename,
            ),
        )
        employee_id = cursor.lastrowid
        connection.commit()
        audit_log(
            "Employee created",
            f"Employee ID: {employee_id}; employee number: {employee['employee_number']}; name: {employee['first_name']} {employee['last_name']}",
        )
        flash("Employee profile created successfully.", "success")
        return redirect(url_for("employee_profile_page", employee_id=employee_id))
    except IntegrityError as error:
        if photo_filename:
            remove_employee_photo(photo_filename)
        if getattr(error, "errno", None) == 1062:
            flash("Employee number, National ID / Passport number or email is already in use.", "error")
        else:
            flash("The selected department does not exist.", "error")
    except Error as error:
        if photo_filename:
            remove_employee_photo(photo_filename)
        flash(f"Unable to create employee profile: {error}", "error")
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()
    return redirect(url_for("employees_page"))

@page_login_required
def employee_profile_page(employee_id):
    try:
        employee = fetch_employee_by_id(employee_id)
        if not employee:
            flash("Employee not found.", "error")
            return redirect(url_for("employees_page"))
        departments = fetch_departments()
        return render_template(
            "employee_profile.html",
            employee=employee,
            departments=departments,
            username=session.get("username"),
            role=session.get("role"),
            genders=sorted(ALLOWED_GENDERS),
            employment_statuses=["Active", "Inactive"],
        )
    except Error as error:
        flash(f"Unable to load employee profile: {error}", "error")
        return redirect(url_for("employees_page"))

@page_login_required
def edit_employee_profile(employee_id):
    employee, validation_error = validate_employee_input(request.form)
    if validation_error:
        flash(validation_error, "error")
        return redirect(url_for("employee_profile_page", employee_id=employee_id))

    photo = request.files.get("photo")
    remove_photo = request.form.get("remove_photo") == "1"
    if (photo and photo.filename or remove_photo) and session.get("role") != ADMIN_ROLE:
        flash("Only Administrators can change employee photographs.", "error")
        return redirect(url_for("employee_profile_page", employee_id=employee_id))
    photo_error = validate_employee_photo(photo)
    if photo_error:
        flash(photo_error, "error")
        return redirect(url_for("employee_profile_page", employee_id=employee_id))

    connection = None
    cursor = None
    new_photo_filename = None
    old_photo_filename = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT photo_filename FROM employees WHERE employee_id = %s", (employee_id,))
        existing = cursor.fetchone()
        if not existing:
            flash("Employee not found.", "error")
            return redirect(url_for("employees_page"))

        old_photo_filename = existing.get("photo_filename")
        final_photo_filename = old_photo_filename
        if photo and photo.filename:
            new_photo_filename = save_employee_photo(photo)
            final_photo_filename = new_photo_filename
        elif remove_photo:
            final_photo_filename = None

        cursor.execute(
            """
            UPDATE employees SET
                employee_number = %s,
                national_id_passport = %s,
                first_name = %s,
                last_name = %s,
                date_of_birth = %s,
                gender = %s,
                residential_address = %s,
                phone = %s,
                email = %s,
                job_position = %s,
                department_id = %s,
                hire_date = %s,
                employment_status = %s,
                photo_filename = %s
            WHERE employee_id = %s
            """,
            (
                employee["employee_number"], employee["national_id_passport"],
                employee["first_name"], employee["last_name"], employee["date_of_birth"],
                employee["gender"], employee["residential_address"], employee["phone"],
                employee["email"], employee["job_position"], employee["department_id"],
                employee["hire_date"], employee["employment_status"], final_photo_filename,
                employee_id,
            ),
        )
        connection.commit()

        if old_photo_filename and old_photo_filename != final_photo_filename:
            remove_employee_photo(old_photo_filename)

        audit_log(
            "Employee updated",
            f"Employee ID: {employee_id}; employee number: {employee['employee_number']}; name: {employee['first_name']} {employee['last_name']}; status: {employee['employment_status']}",
        )
        flash("Employee profile updated successfully.", "success")
    except IntegrityError as error:
        if new_photo_filename:
            remove_employee_photo(new_photo_filename)
        if getattr(error, "errno", None) == 1062:
            flash("Employee number, National ID / Passport number or email is already in use.", "error")
        else:
            flash("The selected department does not exist.", "error")
    except Error as error:
        if new_photo_filename:
            remove_employee_photo(new_photo_filename)
        flash(f"Unable to update employee profile: {error}", "error")
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()
    return redirect(url_for("employee_profile_page", employee_id=employee_id))

@api_login_required
def get_employees():
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
                employees.date_of_birth,
                employees.gender,
                employees.residential_address,
                employees.email,
                employees.phone,
                employees.job_position,
                employees.department_id,
                departments.department_name,
                employees.hire_date,
                employees.employment_status,
                employees.photo_filename
            FROM employees
            LEFT JOIN departments ON employees.department_id = departments.department_id
            ORDER BY employees.employee_id ASC
            """
        )
        return jsonify(cursor.fetchall())
    except Error:
        return jsonify({"error": "Unable to retrieve employees"}), 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

@api_login_required
def add_employee():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON request body is required."}), 400

    employee, validation_error = validate_employee_input(data)
    if validation_error:
        return jsonify({"error": validation_error}), 400

    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO employees (
                employee_number, national_id_passport, first_name, last_name,
                date_of_birth, gender, residential_address, phone, email,
                job_position, department_id, hire_date, employment_status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                employee["employee_number"], employee["national_id_passport"],
                employee["first_name"], employee["last_name"], employee["date_of_birth"],
                employee["gender"], employee["residential_address"], employee["phone"],
                employee["email"], employee["job_position"], employee["department_id"],
                employee["hire_date"], employee["employment_status"],
            ),
        )
        employee_id = cursor.lastrowid
        connection.commit()
        audit_log(
            "Employee created",
            f"Employee ID: {employee_id}; employee number: {employee['employee_number']}; name: {employee['first_name']} {employee['last_name']}",
        )
        return jsonify({"message": "Employee added successfully", "employee_id": employee_id}), 201
    except IntegrityError as error:
        if getattr(error, "errno", None) == 1062:
            return jsonify({"error": "Employee number, National ID / Passport number or email is already in use."}), 409
        return jsonify({"error": "The selected department does not exist."}), 400
    except Error:
        return jsonify({"error": "Unable to add employee"}), 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

@api_login_required
def update_employee(employee_id):
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON request body is required."}), 400

    employee, validation_error = validate_employee_input(data)
    if validation_error:
        return jsonify({"error": validation_error}), 400

    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT employee_id FROM employees WHERE employee_id = %s", (employee_id,))
        if not cursor.fetchone():
            return jsonify({"error": "Employee not found"}), 404

        cursor.execute(
            """
            UPDATE employees SET
                employee_number = %s, national_id_passport = %s,
                first_name = %s, last_name = %s, date_of_birth = %s,
                gender = %s, residential_address = %s, phone = %s,
                email = %s, job_position = %s, department_id = %s,
                hire_date = %s, employment_status = %s
            WHERE employee_id = %s
            """,
            (
                employee["employee_number"], employee["national_id_passport"],
                employee["first_name"], employee["last_name"], employee["date_of_birth"],
                employee["gender"], employee["residential_address"], employee["phone"],
                employee["email"], employee["job_position"], employee["department_id"],
                employee["hire_date"], employee["employment_status"], employee_id,
            ),
        )
        connection.commit()
        audit_log(
            "Employee updated",
            f"Employee ID: {employee_id}; employee number: {employee['employee_number']}; name: {employee['first_name']} {employee['last_name']}",
        )
        return jsonify({"message": "Employee updated successfully"})
    except IntegrityError as error:
        if getattr(error, "errno", None) == 1062:
            return jsonify({"error": "Employee number, National ID / Passport number or email is already in use."}), 409
        return jsonify({"error": "The selected department does not exist."}), 400
    except Error:
        return jsonify({"error": "Unable to update employee"}), 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

@api_login_required
def delete_employee(employee_id):
    connection = None
    cursor = None
    photo_filename = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT first_name, last_name, email, employee_number, photo_filename FROM employees WHERE employee_id = %s",
            (employee_id,),
        )
        employee = cursor.fetchone()
        if not employee:
            return jsonify({"error": "Employee not found"}), 404
        photo_filename = employee.get("photo_filename")

        cursor.execute("DELETE FROM employees WHERE employee_id = %s", (employee_id,))
        connection.commit()
        if photo_filename:
            remove_employee_photo(photo_filename)
        audit_log(
            "Employee deleted",
            f"Employee ID: {employee_id}; employee number: {employee.get('employee_number')}; name: {employee['first_name']} {employee['last_name']}; email: {employee['email']}",
        )
        return jsonify({"message": "Employee deleted successfully"})
    except IntegrityError:
        return jsonify({"error": "This employee has attendance records and cannot be deleted until those records are removed."}), 409
    except Error:
        return jsonify({"error": "Unable to delete employee"}), 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

