# Phase 7 - Week 8 Code Refactoring
# Generated from the complete corrected Week 7 backend (commit 609db26 baseline).
# Existing behavior is preserved; code is separated by responsibility.

from controllers.dashboard_controller import (
    dashboard
)


def register_routes(app):
    app.add_url_rule('/dashboard', endpoint='dashboard', view_func=dashboard)
