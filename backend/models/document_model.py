# Phase 7 - Week 8 Code Refactoring
# Generated from the complete corrected Week 7 backend (commit 609db26 baseline).
# Existing behavior is preserved; code is separated by responsibility.

from db import get_connection

def fetch_employee_document(document_id):
    connection = None
    cursor = None

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
            WHERE employee_documents.document_id = %s
            """,
            (document_id,),
        )
        return cursor.fetchone()
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()
