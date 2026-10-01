import csv
import io
import re
import zipfile
from datetime import date, datetime, time
from pathlib import Path
from uuid import uuid4
from functools import wraps
from urllib.parse import urlencode

from flask import (
    Flask,
    Response,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    session,
    url_for,
)
from mysql.connector import Error, IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from config import Config
from db import get_connection


app = Flask(__name__)
Config.validate()
app.config.from_object(Config)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024

EMPLOYEE_UPLOAD_FOLDER = Path(app.root_path) / "uploads" / "employees"
EMPLOYEE_UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

DOCUMENT_UPLOAD_FOLDER = Path(app.root_path) / "uploads" / "documents"
DOCUMENT_UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------
# CONSTANTS / VALIDATION HELPERS
# ---------------------------------------------------------

ADMIN_ROLE = "Administrator"
HR_ROLE = "HR Officer"
ALLOWED_ROLES = {ADMIN_ROLE, HR_ROLE}
ALLOWED_STATUSES = {"Present", "Absent", "Late"}
ALLOWED_GENDERS = {"Male", "Female", "Other", "Prefer not to say"}
ALLOWED_EMPLOYMENT_STATUSES = {"Active", "Inactive"}
ALLOWED_LEAVE_TYPES = {"Annual Leave", "Sick Leave", "Maternity Leave", "Other Leave"}
ALLOWED_LEAVE_STATUSES = {"Pending", "Approved", "Rejected"}
ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
ALLOWED_IMAGE_MIMETYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_EMPLOYEE_PHOTO_BYTES = 5 * 1024 * 1024

# Phase 7 - Week 5: Employee Documents
ALLOWED_DOCUMENT_TYPES = {
    "Employment Contract",
    "Curriculum Vitae (CV)",
    "Passport / National ID",
    "Certificates",
    "Employee Photograph",
}
DOCUMENT_TYPE_EXTENSIONS = {
    "Employment Contract": {"pdf", "doc", "docx"},
    "Curriculum Vitae (CV)": {"pdf", "doc", "docx"},
    "Passport / National ID": {"pdf", "jpg", "jpeg", "png", "webp"},
    "Certificates": {"pdf", "doc", "docx", "jpg", "jpeg", "png", "webp"},
    "Employee Photograph": {"jpg", "jpeg", "png", "webp"},
}
MAX_EMPLOYEE_DOCUMENT_BYTES = 10 * 1024 * 1024

# Phase 7 - configurable working schedule
# Defaults come from Config (.env) and can differ by environment.
SCHEDULED_START_TIME = datetime.strptime(
    app.config["ATTENDANCE_START_TIME"], "%H:%M"
).time()
SCHEDULED_END_TIME = datetime.strptime(
    app.config["ATTENDANCE_END_TIME"], "%H:%M"
).time()

EMPLOYEE_NUMBER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{1,29}$")

EMAIL_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$")
PHONE_RE = re.compile(r"^\+?[0-9 ()-]{7,20}$")


def normalize_role(role):
    """Keep old role names compatible with Phase 6."""
    value = str(role or "").strip().lower().replace("_", " ")

    if value in {"admin", "administrator"}:
        return ADMIN_ROLE
    if value in {"employee", "hr", "hr officer"}:
        return HR_ROLE
    return None


def valid_email(value):
    value = str(value or "").strip()
    return bool(value and len(value) <= 100 and EMAIL_RE.fullmatch(value))


def valid_phone(value):
    value = str(value or "").strip()
    if not value:
        return True
    if not PHONE_RE.fullmatch(value):
        return False
    digits = re.sub(r"\D", "", value)
    return 7 <= len(digits) <= 15


def valid_date(value):
    if not value:
        return False
    try:
        datetime.strptime(str(value), "%Y-%m-%d")
        return True
    except ValueError:
        return False
