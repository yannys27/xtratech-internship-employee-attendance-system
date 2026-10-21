# Phase 7 - Week 8 Code Refactoring
# Generated from the complete corrected Week 7 backend (commit 609db26 baseline).
# Existing behavior is preserved; code is separated by responsibility.

from controllers.document_controller import (
    employee_documents_page,
    upload_employee_document,
    view_employee_document,
    download_employee_document,
    delete_employee_document
)


def register_routes(app):
    app.add_url_rule('/employee-documents', endpoint='employee_documents_page', view_func=employee_documents_page)
    app.add_url_rule('/employee-documents/upload', endpoint='upload_employee_document', view_func=upload_employee_document, methods=['POST'])
    app.add_url_rule('/employee-documents/<int:document_id>/view', endpoint='view_employee_document', view_func=view_employee_document)
    app.add_url_rule('/employee-documents/<int:document_id>/download', endpoint='download_employee_document', view_func=download_employee_document)
    app.add_url_rule('/employee-documents/<int:document_id>/delete', endpoint='delete_employee_document', view_func=delete_employee_document, methods=['POST'])
