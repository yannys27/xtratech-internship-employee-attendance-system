# Phase 7 - Week 8 Code Refactoring
# Generated from the complete corrected Week 7 backend (commit 609db26 baseline).
# Existing behavior is preserved; code is separated by responsibility.

from db import get_connection

def fetch_employee_by_id(employee_id):
    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT employees.*, departments.department_name
            FROM employees
            LEFT JOIN departments ON employees.department_id = departments.department_id
            WHERE employees.employee_id = %s
            """,
            (employee_id,),
        )
        return cursor.fetchone()
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

def fetch_departments():
    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT department_id, department_name FROM departments ORDER BY department_name ASC"
        )
        return cursor.fetchall()
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()
