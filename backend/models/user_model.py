# Phase 7 - Week 8 Code Refactoring
# Generated from the complete corrected Week 7 backend (commit 609db26 baseline).
# Existing behavior is preserved; code is separated by responsibility.


def count_active_administrators(cursor):
    cursor.execute(
        """
        SELECT COUNT(*) AS total
        FROM users
        WHERE is_active = 1
          AND LOWER(REPLACE(role, '_', ' ')) IN ('admin', 'administrator')
        """
    )
    return cursor.fetchone()["total"]
