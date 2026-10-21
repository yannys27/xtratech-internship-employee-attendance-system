# Phase 7 - Week 8 Code Refactoring
# Generated from the complete corrected Week 7 backend (commit 609db26 baseline).
# Existing behavior is preserved; code is separated by responsibility.

from controllers.auth_controller import (
    home,
    login_page,
    register,
    login,
    logout
)


def register_routes(app):
    app.add_url_rule('/', endpoint='home', view_func=home)
    app.add_url_rule('/login-page', endpoint='login_page', view_func=login_page)
    app.add_url_rule('/register', endpoint='register', view_func=register, methods=['POST'])
    app.add_url_rule('/login', endpoint='login', view_func=login, methods=['POST'])
    app.add_url_rule('/logout', endpoint='logout', view_func=logout, methods=['GET', 'POST'])
