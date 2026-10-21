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
def users_page():
    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT user_id, username, role, is_active FROM users ORDER BY user_id ASC")
        users = cursor.fetchall()
        for user in users:
            user["role"] = normalize_role(user["role"]) or user["role"]

        return render_template(
            "users.html",
            users=users,
            username=session.get("username"),
            current_user_id=session.get("user_id"),
            roles=[ADMIN_ROLE, HR_ROLE],
        )
    except Error as error:
        return render_template(
            "users.html",
            users=[],
            username=session.get("username"),
            current_user_id=session.get("user_id"),
            roles=[ADMIN_ROLE, HR_ROLE],
            error=f"Unable to load users: {error}",
        ), 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

@page_admin_required
def create_user():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    role = normalize_role(request.form.get("role"))

    validation_error = validate_username_password_role(username, password, role)
    if validation_error:
        flash(validation_error, "error")
        return redirect(url_for("users_page"))

    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO users (username, password, role, is_active) VALUES (%s, %s, %s, 1)",
            (username, generate_password_hash(password), role),
        )
        user_id = cursor.lastrowid
        connection.commit()
        audit_log("User created", f"User ID: {user_id}; username: {username}; role: {role}")
        flash("User created successfully.", "success")
    except IntegrityError:
        flash("That username already exists.", "error")
    except Error as error:
        flash(f"Unable to create user: {error}", "error")
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()
    return redirect(url_for("users_page"))

@page_admin_required
def edit_user(user_id):
    username = request.form.get("username", "").strip()
    new_role = normalize_role(request.form.get("role"))

    if len(username) < 3 or len(username) > 50:
        flash("Username must contain between 3 and 50 characters.", "error")
        return redirect(url_for("users_page"))
    if new_role not in ALLOWED_ROLES:
        flash("Please select a valid user role.", "error")
        return redirect(url_for("users_page"))
    if user_id == session.get("user_id") and new_role != ADMIN_ROLE:
        flash("You cannot remove your own Administrator role.", "error")
        return redirect(url_for("users_page"))

    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT user_id, username, role, is_active FROM users WHERE user_id = %s", (user_id,))
        existing_user = cursor.fetchone()
        if not existing_user:
            flash("User not found.", "error")
            return redirect(url_for("users_page"))

        old_role = normalize_role(existing_user["role"])
        if old_role == ADMIN_ROLE and new_role != ADMIN_ROLE and existing_user["is_active"] and count_active_administrators(cursor) <= 1:
            flash("The system must keep at least one active Administrator.", "error")
            return redirect(url_for("users_page"))

        cursor.execute("UPDATE users SET username = %s, role = %s WHERE user_id = %s", (username, new_role, user_id))
        connection.commit()
        audit_log(
            "User modified",
            f"User ID: {user_id}; username: {existing_user['username']} -> {username}; role: {old_role} -> {new_role}",
        )
        flash("User updated successfully.", "success")
    except IntegrityError:
        flash("That username is already being used.", "error")
    except Error as error:
        flash(f"Unable to update user: {error}", "error")
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()
    return redirect(url_for("users_page"))

@page_admin_required
def change_user_password(user_id):
    new_password = request.form.get("password", "")
    if not new_password:
        flash("New password is required.", "error")
        return redirect(url_for("users_page"))
    if len(new_password) < 8:
        flash("New password must contain at least 8 characters.", "error")
        return redirect(url_for("users_page"))

    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute("UPDATE users SET password = %s WHERE user_id = %s", (generate_password_hash(new_password), user_id))
        connection.commit()
        if cursor.rowcount == 0:
            flash("User not found.", "error")
        else:
            audit_log("User password changed", f"User ID: {user_id}")
            flash("Password changed successfully.", "success")
    except Error as error:
        flash(f"Unable to change password: {error}", "error")
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()
    return redirect(url_for("users_page"))

@page_admin_required
def toggle_user_active(user_id):
    if user_id == session.get("user_id"):
        flash("You cannot deactivate your own account.", "error")
        return redirect(url_for("users_page"))

    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT user_id, username, role, is_active FROM users WHERE user_id = %s", (user_id,))
        user = cursor.fetchone()
        if not user:
            flash("User not found.", "error")
            return redirect(url_for("users_page"))

        role = normalize_role(user["role"])
        if role == ADMIN_ROLE and user["is_active"] and count_active_administrators(cursor) <= 1:
            flash("The last active Administrator cannot be deactivated.", "error")
            return redirect(url_for("users_page"))

        new_status = 0 if user["is_active"] else 1
        cursor.execute("UPDATE users SET is_active = %s WHERE user_id = %s", (new_status, user_id))
        connection.commit()
        audit_log(
            "User modified",
            f"User ID: {user_id}; username: {user['username']}; account status: {'Active' if new_status else 'Inactive'}",
        )
        flash(
            "User activated successfully." if new_status else "User deactivated successfully.",
            "success" if new_status else "warning",
        )
    except Error as error:
        flash(f"Unable to change account status: {error}", "error")
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()
    return redirect(url_for("users_page"))

@page_admin_required
def delete_user(user_id):
    if user_id == session.get("user_id"):
        flash("You cannot delete your own account.", "error")
        return redirect(url_for("users_page"))

    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT user_id, username, role, is_active FROM users WHERE user_id = %s", (user_id,))
        user = cursor.fetchone()
        if not user:
            flash("User not found.", "error")
            return redirect(url_for("users_page"))

        role = normalize_role(user["role"])
        if role == ADMIN_ROLE and user["is_active"] and count_active_administrators(cursor) <= 1:
            flash("The last active Administrator cannot be deleted.", "error")
            return redirect(url_for("users_page"))

        cursor.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
        connection.commit()
        audit_log("User deleted", f"User ID: {user_id}; username: {user['username']}; role: {role}")
        flash("User deleted successfully.", "success")
    except Error as error:
        flash(f"Unable to delete user: {error}", "error")
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()
    return redirect(url_for("users_page"))

