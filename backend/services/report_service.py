# Phase 7 - Week 8 Code Refactoring
# Generated from the complete corrected Week 7 backend (commit 609db26 baseline).
# Existing behavior is preserved; code is separated by responsibility.

from urllib.parse import urlencode
from db import get_connection
from utilities.validators import ALLOWED_STATUSES, valid_date

def get_report_filters(args):
    filters = {
        "employee_name": str(args.get("employee_name", "")).strip(),
        "department_id": str(args.get("department_id", "")).strip(),
        "date_from": str(args.get("date_from", "")).strip(),
        "date_to": str(args.get("date_to", "")).strip(),
        "status": str(args.get("status", "")).strip().title(),
    }

    if len(filters["employee_name"]) > 100:
        return None, "Employee name search must not exceed 100 characters."

    if filters["department_id"]:
        try:
            department_id = int(filters["department_id"])
            if department_id <= 0:
                raise ValueError
            filters["department_id"] = department_id
        except ValueError:
            return None, "Please select a valid department."

    if filters["date_from"] and not valid_date(filters["date_from"]):
        return None, "Start date must use YYYY-MM-DD format."
    if filters["date_to"] and not valid_date(filters["date_to"]):
        return None, "End date must use YYYY-MM-DD format."
    if filters["date_from"] and filters["date_to"]:
        if filters["date_from"] > filters["date_to"]:
            return None, "Start date cannot be after end date."

    if filters["status"] and filters["status"] not in ALLOWED_STATUSES:
        return None, "Please select a valid attendance status."

    return filters, None
def fetch_attendance_report(filters):
    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        query = """
            SELECT
                attendance.attendance_id,
                attendance.employee_id,
                employees.first_name,
                employees.last_name,
                departments.department_name,
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
            JOIN employees
                ON attendance.employee_id = employees.employee_id
            LEFT JOIN departments
                ON employees.department_id = departments.department_id
            WHERE 1 = 1
        """
        values = []

        if filters.get("employee_name"):
            query += " AND CONCAT(employees.first_name, ' ', employees.last_name) LIKE %s"
            values.append(f"%{filters['employee_name']}%")
        if filters.get("department_id"):
            query += " AND employees.department_id = %s"
            values.append(filters["department_id"])
        if filters.get("date_from"):
            query += " AND attendance.date >= %s"
            values.append(filters["date_from"])
        if filters.get("date_to"):
            query += " AND attendance.date <= %s"
            values.append(filters["date_to"])
        if filters.get("status"):
            query += " AND attendance.status = %s"
            values.append(filters["status"])

        query += " ORDER BY attendance.date DESC, attendance.attendance_id DESC"
        cursor.execute(query, tuple(values))
        return cursor.fetchall()
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()
def report_query_string(filters):
    values = {}
    for key, value in filters.items():
        if value not in (None, ""):
            values[key] = value
    return urlencode(values)
def display_value(value):
    if value in (None, ""):
        return "-"
    return str(value)
