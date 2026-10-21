# Phase 7 - Week 8 Code Refactoring
# Generated from the complete corrected Week 7 backend (commit 609db26 baseline).
# Existing behavior is preserved; code is separated by responsibility.

from controllers.attendance_controller import (
    attendance_page,
    create_attendance_page,
    attendance_check_in_now,
    attendance_check_out_now,
    delete_attendance_page,
    get_attendance,
    add_attendance,
    update_attendance,
    delete_attendance
)


def register_routes(app):
    app.add_url_rule('/attendance-page', endpoint='attendance_page', view_func=attendance_page)
    app.add_url_rule('/attendance-page/create', endpoint='create_attendance_page', view_func=create_attendance_page, methods=['POST'])
    app.add_url_rule('/attendance-page/check-in', endpoint='attendance_check_in_now', view_func=attendance_check_in_now, methods=['POST'])
    app.add_url_rule('/attendance-page/check-out', endpoint='attendance_check_out_now', view_func=attendance_check_out_now, methods=['POST'])
    app.add_url_rule('/attendance-page/<int:attendance_id>/delete', endpoint='delete_attendance_page', view_func=delete_attendance_page, methods=['POST'])
    app.add_url_rule('/attendance', endpoint='get_attendance', view_func=get_attendance, methods=['GET'])
    app.add_url_rule('/attendance', endpoint='add_attendance', view_func=add_attendance, methods=['POST'])
    app.add_url_rule('/attendance/<int:attendance_id>', endpoint='update_attendance', view_func=update_attendance, methods=['PUT'])
    app.add_url_rule('/attendance/<int:attendance_id>', endpoint='delete_attendance', view_func=delete_attendance, methods=['DELETE'])
