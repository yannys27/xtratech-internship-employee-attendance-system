# Phase 7 - Week 8 Code Refactoring
# Generated from the complete corrected Week 7 backend (commit 609db26 baseline).
# Existing behavior is preserved; code is separated by responsibility.

import re
from flask import request, session
from mysql.connector import Error
from db import get_connection
from utilities.validators import normalize_role

def _infer_audit_module(action):
    """Infer the application module from the audit action text."""
    value = str(action or "").strip().lower()

    if "document" in value:
        return "Employee Documents"
    if "leave" in value:
        return "Leave Management"
    if "attendance report" in value or "report" in value:
        return "Reports"
    if "attendance" in value or "checked in" in value or "checked out" in value:
        return "Attendance"
    if "employee" in value:
        return "Employee Management"
    if "login" in value or "logout" in value:
        return "Authentication"
    if "user" in value or "password" in value:
        return "User Management"
    return "System"
def _infer_affected_record(action, details):
    """Extract the main affected record from the existing audit details."""
    text = str(details or "")

    patterns = [
        (r"Document ID:\s*([^;]+)", "Employee Document"),
        (r"Leave ID:\s*([^;]+)", "Leave Request"),
        (r"Attendance ID:\s*([^;]+)", "Attendance"),
        (r"Employee ID:\s*([^;]+)", "Employee"),
        (r"User ID:\s*([^;]+)", "User"),
    ]

    for pattern, label in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return f"{label} #{match.group(1).strip()}"[:150]

    action_value = str(action or "").lower()
    if "report" in action_value:
        return "Attendance Report"
    if "login" in action_value or "logout" in action_value:
        return "User session"

    return "N/A"
def audit_log(
    action,
    details=None,
    username=None,
    role=None,
    module=None,
    affected_record=None,
):
    """
    Record an important application activity.

    Week 4 records:
    user, role, action, date/time, IP address, affected record and module.
    Audit failures never prevent the requested application action from completing.
    """
    audit_username = str(username or session.get("username") or "System")[:50]

    session_role = role or session.get("role")
    normalized_role = normalize_role(session_role)
    audit_role = str(normalized_role or session_role or "System")[:50]

    audit_action = str(action or "Unknown action")[:100]
    audit_details = str(details) if details else None
    audit_module = str(module or _infer_audit_module(audit_action))[:50]
    audit_affected_record = str(
        affected_record or _infer_affected_record(audit_action, audit_details)
    )[:150]

    try:
        audit_ip_address = str(request.remote_addr or "Unknown")[:45]
    except RuntimeError:
        # Allows the helper to remain safe if it is ever called outside a request.
        audit_ip_address = "System"

    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO audit_log (
                username,
                role,
                action,
                details,
                ip_address,
                affected_record,
                module
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                audit_username,
                audit_role,
                audit_action,
                audit_details,
                audit_ip_address,
                audit_affected_record,
                audit_module,
            ),
        )
        connection.commit()
    except Error:
        # Logging must never break the action the user requested.
        pass
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()
