# Phase 7 - Week 8 Code Refactoring
# Generated from the complete corrected Week 7 backend (commit 609db26 baseline).
# Existing behavior is preserved; code is separated by responsibility.

from functools import wraps
from flask import flash, jsonify, redirect, session, url_for
from mysql.connector import Error
from db import get_connection
from utilities.validators import ADMIN_ROLE, HR_ROLE, normalize_role

def refresh_session_user():
    user_id = session.get("user_id")
    if not user_id:
        return False

    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT user_id, username, role, is_active
            FROM users
            WHERE user_id = %s
            """,
            (user_id,),
        )
        user = cursor.fetchone()

        if not user or not user["is_active"]:
            session.clear()
            return False

        role = normalize_role(user["role"])
        if not role:
            session.clear()
            return False

        session["username"] = user["username"]
        session["role"] = role
        return True
    except Error:
        return False
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()
def page_login_required(function):
    @wraps(function)
    def decorated_function(*args, **kwargs):
        if not refresh_session_user():
            return redirect(url_for("login_page"))
        return function(*args, **kwargs)
    return decorated_function
def api_login_required(function):
    @wraps(function)
    def decorated_function(*args, **kwargs):
        if not refresh_session_user():
            return jsonify({"error": "Login required"}), 401
        return function(*args, **kwargs)
    return decorated_function
def page_admin_required(function):
    @wraps(function)
    def decorated_function(*args, **kwargs):
        if not refresh_session_user():
            return redirect(url_for("login_page"))
        if session.get("role") != ADMIN_ROLE:
            flash("Administrator access is required.", "error")
            return redirect(url_for("dashboard"))
        return function(*args, **kwargs)
    return decorated_function
def api_admin_required(function):
    @wraps(function)
    def decorated_function(*args, **kwargs):
        if not refresh_session_user():
            return jsonify({"error": "Login required"}), 401
        if session.get("role") != ADMIN_ROLE:
            return jsonify({"error": "Administrator access required"}), 403
        return function(*args, **kwargs)
    return decorated_function
def page_leave_approver_required(function):
    """Allow only HR Officers and Administrators to review leave requests."""
    @wraps(function)
    def decorated_function(*args, **kwargs):
        if not refresh_session_user():
            return redirect(url_for("login_page"))
        if session.get("role") not in {ADMIN_ROLE, HR_ROLE}:
            flash("HR Officer or Administrator access is required.", "error")
            return redirect(url_for("dashboard"))
        return function(*args, **kwargs)
    return decorated_function
def api_leave_approver_required(function):
    """API equivalent of the leave approval role check."""
    @wraps(function)
    def decorated_function(*args, **kwargs):
        if not refresh_session_user():
            return jsonify({"error": "Login required"}), 401
        if session.get("role") not in {ADMIN_ROLE, HR_ROLE}:
            return jsonify({"error": "HR Officer or Administrator access required"}), 403
        return function(*args, **kwargs)
    return decorated_function
def page_document_access_required(function):
    """Allow only HR Officers and Administrators to access employee documents."""
    @wraps(function)
    def decorated_function(*args, **kwargs):
        if not refresh_session_user():
            return redirect(url_for("login_page"))
        if session.get("role") not in {ADMIN_ROLE, HR_ROLE}:
            flash("HR Officer or Administrator access is required.", "error")
            return redirect(url_for("dashboard"))
        return function(*args, **kwargs)
    return decorated_function
