# Phase 7 - Week 8 Code Refactoring
# Generated from the complete corrected Week 7 backend (commit 609db26 baseline).
# Existing behavior is preserved; code is separated by responsibility.

from controllers.user_controller import (
    users_page,
    create_user,
    edit_user,
    change_user_password,
    toggle_user_active,
    delete_user
)


def register_routes(app):
    app.add_url_rule('/users-page', endpoint='users_page', view_func=users_page)
    app.add_url_rule('/users/create', endpoint='create_user', view_func=create_user, methods=['POST'])
    app.add_url_rule('/users/<int:user_id>/edit', endpoint='edit_user', view_func=edit_user, methods=['POST'])
    app.add_url_rule('/users/<int:user_id>/password', endpoint='change_user_password', view_func=change_user_password, methods=['POST'])
    app.add_url_rule('/users/<int:user_id>/toggle', endpoint='toggle_user_active', view_func=toggle_user_active, methods=['POST'])
    app.add_url_rule('/users/<int:user_id>/delete', endpoint='delete_user', view_func=delete_user, methods=['POST'])
