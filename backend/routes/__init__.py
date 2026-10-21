# Phase 7 - Week 8 route registration

from routes.auth_routes import register_routes as register_auth_routes
from routes.dashboard_routes import register_routes as register_dashboard_routes
from routes.employee_routes import register_routes as register_employee_routes
from routes.document_routes import register_routes as register_document_routes
from routes.attendance_routes import register_routes as register_attendance_routes
from routes.report_routes import register_routes as register_report_routes
from routes.leave_routes import register_routes as register_leave_routes
from routes.user_routes import register_routes as register_user_routes
from routes.audit_routes import register_routes as register_audit_routes


def register_all_routes(app):
    register_auth_routes(app)
    register_dashboard_routes(app)
    register_employee_routes(app)
    register_document_routes(app)
    register_attendance_routes(app)
    register_report_routes(app)
    register_leave_routes(app)
    register_user_routes(app)
    register_audit_routes(app)
