# Phase 7 - Week 8 Code Refactoring
# Generated from the complete corrected Week 7 backend (commit 609db26 baseline).
# Existing behavior is preserved; code is separated by responsibility.

from flask import Flask
from config import Config
from routes import register_all_routes
from services.file_service import ensure_upload_directories
from utilities.errors import register_error_handlers


def create_app():
    Config.validate()

    app = Flask(__name__)
    app.config.from_object(Config)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024

    ensure_upload_directories()
    register_error_handlers(app)
    register_all_routes(app)

    return app
