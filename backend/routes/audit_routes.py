# Phase 7 - Week 8 Code Refactoring
# Generated from the complete corrected Week 7 backend (commit 609db26 baseline).
# Existing behavior is preserved; code is separated by responsibility.

from controllers.audit_controller import (
    audit_log_page
)


def register_routes(app):
    app.add_url_rule('/audit-log', endpoint='audit_log_page', view_func=audit_log_page)
