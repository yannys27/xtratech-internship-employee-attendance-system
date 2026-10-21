# Phase 7 - Week 8 Code Refactoring
# Generated from the complete corrected Week 7 backend (commit 609db26 baseline).
# Existing behavior is preserved; code is separated by responsibility.

from application_factory import create_app

app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
