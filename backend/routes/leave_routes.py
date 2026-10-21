# Phase 7 - Week 8 Code Refactoring
# Generated from the complete corrected Week 7 backend (commit 609db26 baseline).
# Existing behavior is preserved; code is separated by responsibility.

from controllers.leave_controller import (
    leave_management_page,
    create_leave_request_page,
    review_leave_request_page,
    get_leave_requests,
    add_leave_request,
    update_leave_request_status
)


def register_routes(app):
    app.add_url_rule('/leave-management', endpoint='leave_management_page', view_func=leave_management_page)
    app.add_url_rule('/leave-management/create', endpoint='create_leave_request_page', view_func=create_leave_request_page, methods=['POST'])
    app.add_url_rule('/leave-management/<int:leave_id>/<decision>', endpoint='review_leave_request_page', view_func=review_leave_request_page, methods=['POST'])
    app.add_url_rule('/leave-requests', endpoint='get_leave_requests', view_func=get_leave_requests, methods=['GET'])
    app.add_url_rule('/leave-requests', endpoint='add_leave_request', view_func=add_leave_request, methods=['POST'])
    app.add_url_rule('/leave-requests/<int:leave_id>/status', endpoint='update_leave_request_status', view_func=update_leave_request_status, methods=['PATCH'])
