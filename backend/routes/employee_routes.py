# Phase 7 - Week 8 Code Refactoring
# Generated from the complete corrected Week 7 backend (commit 609db26 baseline).
# Existing behavior is preserved; code is separated by responsibility.

from controllers.employee_controller import (
    employees_page,
    employee_photo,
    create_employee_page,
    employee_profile_page,
    edit_employee_profile,
    get_employees,
    add_employee,
    update_employee,
    delete_employee
)


def register_routes(app):
    app.add_url_rule('/employees-page', endpoint='employees_page', view_func=employees_page)
    app.add_url_rule('/employee-photo/<path:filename>', endpoint='employee_photo', view_func=employee_photo)
    app.add_url_rule('/employees/create', endpoint='create_employee_page', view_func=create_employee_page, methods=['POST'])
    app.add_url_rule('/employees/<int:employee_id>/profile', endpoint='employee_profile_page', view_func=employee_profile_page)
    app.add_url_rule('/employees/<int:employee_id>/edit-profile', endpoint='edit_employee_profile', view_func=edit_employee_profile, methods=['POST'])
    app.add_url_rule('/employees', endpoint='get_employees', view_func=get_employees, methods=['GET'])
    app.add_url_rule('/employees', endpoint='add_employee', view_func=add_employee, methods=['POST'])
    app.add_url_rule('/employees/<int:employee_id>', endpoint='update_employee', view_func=update_employee, methods=['PUT'])
    app.add_url_rule('/employees/<int:employee_id>', endpoint='delete_employee', view_func=delete_employee, methods=['DELETE'])
