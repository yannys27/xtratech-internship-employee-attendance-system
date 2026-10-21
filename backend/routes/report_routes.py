# Phase 7 - Week 8 Code Refactoring
# Generated from the complete corrected Week 7 backend (commit 609db26 baseline).
# Existing behavior is preserved; code is separated by responsibility.

from controllers.report_controller import (
    reports_page,
    export_attendance_report,
    employee_listing_report,
    attendance_report,
    attendance_by_status,
    search_employees,
    search_attendance
)


def register_routes(app):
    app.add_url_rule('/reports-page', endpoint='reports_page', view_func=reports_page)
    app.add_url_rule('/reports/attendance/export/<file_format>', endpoint='export_attendance_report', view_func=export_attendance_report)
    app.add_url_rule('/reports/employees', endpoint='employee_listing_report', view_func=employee_listing_report, methods=['GET'])
    app.add_url_rule('/reports/attendance', endpoint='attendance_report', view_func=attendance_report, methods=['GET'])
    app.add_url_rule('/reports/attendance/status/<status>', endpoint='attendance_by_status', view_func=attendance_by_status, methods=['GET'])
    app.add_url_rule('/search/employees', endpoint='search_employees', view_func=search_employees, methods=['GET'])
    app.add_url_rule('/search/attendance', endpoint='search_attendance', view_func=search_attendance, methods=['GET'])
