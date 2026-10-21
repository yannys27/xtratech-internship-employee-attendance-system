# Phase 7 - Week 8 Code Refactoring
# Generated from the complete corrected Week 7 backend (commit 609db26 baseline).
# Existing behavior is preserved; code is separated by responsibility.

from flask import flash, redirect, request, url_for

def request_entity_too_large(_error):
    """Show a user-friendly message when an upload exceeds the request-size limit."""
    flash("The selected file is too large. Please upload a smaller file.", "error")
    return redirect(request.referrer or url_for("dashboard"))

def register_error_handlers(app):
    app.register_error_handler(413, request_entity_too_large)
