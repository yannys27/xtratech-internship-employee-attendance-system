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

def home():
    if "user_id" not in session:
        return redirect(url_for("login_page"))
    return redirect(url_for("dashboard"))

def login_page():
    if "user_id" in session and refresh_session_user():
        return redirect(url_for("dashboard"))
    return render_template("login.html")

@api_admin_required
def register():
    data = request.get_json(silent=True) or request.form
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    role = normalize_role(data.get("role"))

    validation_error = validate_username_password_role(username, password, role)
    if validation_error:
        return jsonify({"error": validation_error}), 400

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
        return jsonify({"message": "User registered successfully"}), 201
    except IntegrityError:
        return jsonify({"error": "Username already exists"}), 409
    except Error:
        return jsonify({"error": "Unable to register user"}), 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

def login():
    data = request.get_json(silent=True) or request.form
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))

    if not username or not password:
        message = "Username and password are required."
        if request.is_json:
            return jsonify({"error": message}), 400
        return render_template("login.html", error=message), 400

    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT user_id, username, password, role, is_active FROM users WHERE username = %s",
            (username,),
        )
        user = cursor.fetchone()

        if user and not user["is_active"]:
            message = "This account is inactive. Please contact an administrator."
            if request.is_json:
                return jsonify({"error": message}), 403
            return render_template("login.html", error=message), 403

        if user and check_password_hash(user["password"], password):
            role = normalize_role(user["role"])
            if not role:
                message = "This account has an invalid role."
                if request.is_json:
                    return jsonify({"error": message}), 403
                return render_template("login.html", error=message), 403

            session.clear()
            session["user_id"] = user["user_id"]
            session["username"] = user["username"]
            session["role"] = role
            audit_log("User login", f"User ID: {user['user_id']}", username=user["username"])

            if request.is_json:
                return jsonify({"message": "Login successful", "username": user["username"], "role": role})

            flash(f"Welcome back, {user['username']}.", "success")
            return redirect(url_for("dashboard"))

        message = "Invalid username or password."
        if request.is_json:
            return jsonify({"error": message}), 401
        return render_template("login.html", error=message), 401
    except Error:
        message = "Unable to connect to the database."
        if request.is_json:
            return jsonify({"error": "Unable to complete login"}), 500
        return render_template("login.html", error=message), 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

def logout():
    username = session.get("username")
    user_id = session.get("user_id")
    if username:
        audit_log("User logout", f"User ID: {user_id}", username=username)
    session.clear()

    if request.method == "POST" and request.is_json:
        return jsonify({"message": "Logout successful"})

    flash("You have been logged out successfully.", "info")
    return redirect(url_for("login_page"))

