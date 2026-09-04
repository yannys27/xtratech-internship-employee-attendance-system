import csv
import io
import re
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
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024

EMPLOYEE_UPLOAD_FOLDER = Path(app.root_path) / "uploads" / "employees"
EMPLOYEE_UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)


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


def parse_time(value):
    """Return a time object for HH:MM / HH:MM:SS or None for an empty value."""
    if value in (None, ""):
        return None

    text = str(value).strip()
    for pattern in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(text, pattern).time()
        except ValueError:
            continue
    return False


def validate_username_password_role(username, password, role):
    if not username:
        return "Username is required."
    if len(username) < 3 or len(username) > 50:
        return "Username must contain between 3 and 50 characters."
    if not password:
        return "Password is required."
    if len(password) < 8:
        return "Password must contain at least 8 characters."
    if role not in ALLOWED_ROLES:
        return "Please select a valid user role."
    return None


def validate_employee_input(data):
    """Validate the complete Phase 7 employee profile."""
    employee_number = str(data.get("employee_number", "")).strip()
    national_id_passport = str(data.get("national_id_passport", "")).strip()
    first_name = str(data.get("first_name", "")).strip()
    last_name = str(data.get("last_name", "")).strip()
    date_of_birth = str(data.get("date_of_birth", "")).strip()
    gender = str(data.get("gender", "")).strip()
    residential_address = str(data.get("residential_address", "")).strip()
    phone = str(data.get("phone", "")).strip()
    email = str(data.get("email", "")).strip()
    job_position = str(data.get("job_position", "")).strip()
    department_id = data.get("department_id")
    hire_date = str(data.get("hire_date", "")).strip()
    employment_status = str(data.get("employment_status", "")).strip().title()

    required = {
        "Employee number": employee_number,
        "National ID / Passport number": national_id_passport,
        "First name": first_name,
        "Last name": last_name,
        "Date of birth": date_of_birth,
        "Gender": gender,
        "Residential address": residential_address,
        "Telephone number": phone,
        "Email address": email,
        "Job position": job_position,
        "Hire date": hire_date,
        "Employment status": employment_status,
    }
    for label, value in required.items():
        if not value:
            return None, f"{label} is required."

    if not EMPLOYEE_NUMBER_RE.fullmatch(employee_number):
        return None, "Employee number must contain 2 to 30 letters, numbers, dots, dashes, underscores or slashes."
    if len(national_id_passport) > 50:
        return None, "National ID / Passport number must not exceed 50 characters."
    if len(first_name) > 50 or len(last_name) > 50:
        return None, "First name and last name must not exceed 50 characters."
    if not valid_date(date_of_birth):
        return None, "Date of birth must be a valid date."
    if datetime.strptime(date_of_birth, "%Y-%m-%d").date() >= date.today():
        return None, "Date of birth must be in the past."
    if gender not in ALLOWED_GENDERS:
        return None, "Please select a valid gender."
    if len(residential_address) < 5 or len(residential_address) > 255:
        return None, "Residential address must contain between 5 and 255 characters."
    if not valid_phone(phone):
        return None, "Please enter a valid telephone number using 7 to 15 digits."
    if not valid_email(email):
        return None, "Please enter a valid email address, for example name@example.com."
    if len(job_position) > 100:
        return None, "Job position must not exceed 100 characters."

    try:
        department_id = int(department_id)
        if department_id <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return None, "A valid department is required."

    if not valid_date(hire_date):
        return None, "Hire date must be a valid date."
    if employment_status not in ALLOWED_EMPLOYMENT_STATUSES:
        return None, "Employment status must be Active or Inactive."

    return {
        "employee_number": employee_number,
        "national_id_passport": national_id_passport,
        "first_name": first_name,
        "last_name": last_name,
        "date_of_birth": date_of_birth,
        "gender": gender,
        "residential_address": residential_address,
        "phone": phone,
        "email": email,
        "job_position": job_position,
        "department_id": department_id,
        "hire_date": hire_date,
        "employment_status": employment_status,
    }, None


def validate_employee_photo(file_storage):
    if not file_storage or not file_storage.filename:
        return None

    safe_name = secure_filename(file_storage.filename)
    if "." not in safe_name:
        return "Employee photograph must be a JPG, JPEG, PNG or WEBP image."

    extension = safe_name.rsplit(".", 1)[1].lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        return "Employee photograph must be a JPG, JPEG, PNG or WEBP image."
    if file_storage.mimetype not in ALLOWED_IMAGE_MIMETYPES:
        return "The uploaded file is not a supported image type."

    position = file_storage.stream.tell()
    file_storage.stream.seek(0, 2)
    size = file_storage.stream.tell()
    file_storage.stream.seek(position)
    if size > MAX_EMPLOYEE_PHOTO_BYTES:
        return "Employee photograph must not exceed 5 MB."
    return None


def save_employee_photo(file_storage):
    if not file_storage or not file_storage.filename:
        return None
    extension = secure_filename(file_storage.filename).rsplit(".", 1)[1].lower()
    filename = f"{uuid4().hex}.{extension}"
    file_storage.save(EMPLOYEE_UPLOAD_FOLDER / filename)
    return filename


def remove_employee_photo(filename):
    if not filename:
        return
    safe_name = Path(str(filename)).name
    target = EMPLOYEE_UPLOAD_FOLDER / safe_name
    try:
        if target.is_file():
            target.unlink()
    except OSError:
        pass


def fetch_employee_by_id(employee_id):
    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT employees.*, departments.department_name
            FROM employees
            LEFT JOIN departments ON employees.department_id = departments.department_id
            WHERE employees.employee_id = %s
            """,
            (employee_id,),
        )
        return cursor.fetchone()
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


def minutes_between(start_time, end_time):
    start_minutes = start_time.hour * 60 + start_time.minute
    end_minutes = end_time.hour * 60 + end_time.minute
    return end_minutes - start_minutes


def calculate_attendance_values(attendance_date, check_in, check_out):
    """Calculate Phase 7 Week 2 attendance values automatically."""
    record_date = datetime.strptime(attendance_date, "%Y-%m-%d").date()
    weekend_attendance = record_date.weekday() >= 5

    if check_out and not check_in:
        raise ValueError("A check-out time cannot be recorded without a check-in time.")
    if check_in and check_out and check_out < check_in:
        raise ValueError("Check-out time cannot be earlier than check-in time.")

    if not check_in:
        return {
            "status": "Absent",
            "total_working_hours": None,
            "late_arrival_minutes": 0,
            "early_departure_minutes": 0,
            "weekend_attendance": weekend_attendance,
        }

    late_arrival_minutes = 0
    early_departure_minutes = 0

    # Weekend attendance is tracked separately; weekend employees are not marked late/early.
    if not weekend_attendance:
        late_arrival_minutes = max(0, minutes_between(SCHEDULED_START_TIME, check_in))
        if check_out:
            early_departure_minutes = max(0, minutes_between(check_out, SCHEDULED_END_TIME))

    total_working_hours = None
    if check_out:
        worked_minutes = minutes_between(check_in, check_out)
        total_working_hours = round(worked_minutes / 60, 2)

    status = "Late" if late_arrival_minutes > 0 else "Present"

    return {
        "status": status,
        "total_working_hours": total_working_hours,
        "late_arrival_minutes": late_arrival_minutes,
        "early_departure_minutes": early_departure_minutes,
        "weekend_attendance": weekend_attendance,
    }


def validate_attendance_input(data):
    """Validate raw attendance input and calculate status/hours automatically."""
    employee_id = data.get("employee_id")
    attendance_date = str(data.get("date", "")).strip()
    check_in_raw = data.get("check_in_time")
    check_out_raw = data.get("check_out_time")

    try:
        employee_id = int(employee_id)
        if employee_id <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return None, "A valid employee is required."

    if not attendance_date:
        return None, "Attendance date is required."
    if not valid_date(attendance_date):
        return None, "Attendance date must use YYYY-MM-DD format."

    check_in = parse_time(check_in_raw)
    check_out = parse_time(check_out_raw)

    if check_in is False:
        return None, "Check-in time must use HH:MM format."
    if check_out is False:
        return None, "Check-out time must use HH:MM format."

    try:
        calculated = calculate_attendance_values(attendance_date, check_in, check_out)
    except ValueError as error:
        return None, str(error)

    return {
        "employee_id": employee_id,
        "date": attendance_date,
        "check_in_time": check_in.strftime("%H:%M:%S") if check_in else None,
        "check_out_time": check_out.strftime("%H:%M:%S") if check_out else None,
        "scheduled_start_time": SCHEDULED_START_TIME.strftime("%H:%M:%S"),
        "scheduled_end_time": SCHEDULED_END_TIME.strftime("%H:%M:%S"),
        **calculated,
    }, None


# ---------------------------------------------------------
# PHASE 7 WEEK 3: LEAVE VALIDATION HELPERS
# ---------------------------------------------------------


def validate_leave_request_input(data):
    employee_id = str(data.get("employee_id", "")).strip()
    leave_type = str(data.get("leave_type", "")).strip()
    start_date = str(data.get("start_date", "")).strip()
    end_date = str(data.get("end_date", "")).strip()
    reason = str(data.get("reason", "")).strip()

    if not employee_id.isdigit() or int(employee_id) <= 0:
        return None, "A valid employee is required."
    if leave_type not in ALLOWED_LEAVE_TYPES:
        return None, "Please select a valid leave type."
    if not valid_date(start_date):
        return None, "Start date must be a valid date."
    if not valid_date(end_date):
        return None, "End date must be a valid date."

    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    if end < start:
        return None, "End date cannot be earlier than start date."

    if not reason:
        return None, "Reason is required."
    if len(reason) > 500:
        return None, "Reason must not exceed 500 characters."

    return {
        "employee_id": int(employee_id),
        "leave_type": leave_type,
        "start_date": start_date,
        "end_date": end_date,
        "reason": reason,
    }, None


# ---------------------------------------------------------
# AUDIT LOG HELPERS - TASK 7
# ---------------------------------------------------------


def _infer_audit_module(action):
    """Infer the application module from the audit action text."""
    value = str(action or "").strip().lower()

    if "leave" in value:
        return "Leave Management"
    if "attendance report" in value or "report" in value:
        return "Reports"
    if "attendance" in value or "checked in" in value or "checked out" in value:
        return "Attendance"
    if "employee" in value:
        return "Employee Management"
    if "login" in value or "logout" in value:
        return "Authentication"
    if "user" in value or "password" in value:
        return "User Management"
    return "System"


def _infer_affected_record(action, details):
    """Extract the main affected record from the existing audit details."""
    text = str(details or "")

    patterns = [
        (r"Leave ID:\s*([^;]+)", "Leave Request"),
        (r"Attendance ID:\s*([^;]+)", "Attendance"),
        (r"Employee ID:\s*([^;]+)", "Employee"),
        (r"User ID:\s*([^;]+)", "User"),
    ]

    for pattern, label in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return f"{label} #{match.group(1).strip()}"[:150]

    action_value = str(action or "").lower()
    if "report" in action_value:
        return "Attendance Report"
    if "login" in action_value or "logout" in action_value:
        return "User session"

    return "N/A"


def audit_log(
    action,
    details=None,
    username=None,
    role=None,
    module=None,
    affected_record=None,
):
    """
    Record an important application activity.

    Week 4 records:
    user, role, action, date/time, IP address, affected record and module.
    Audit failures never prevent the requested application action from completing.
    """
    audit_username = str(username or session.get("username") or "System")[:50]

    session_role = role or session.get("role")
    normalized_role = normalize_role(session_role)
    audit_role = str(normalized_role or session_role or "System")[:50]

    audit_action = str(action or "Unknown action")[:100]
    audit_details = str(details) if details else None
    audit_module = str(module or _infer_audit_module(audit_action))[:50]
    audit_affected_record = str(
        affected_record or _infer_affected_record(audit_action, audit_details)
    )[:150]

    try:
        audit_ip_address = str(request.remote_addr or "Unknown")[:45]
    except RuntimeError:
        # Allows the helper to remain safe if it is ever called outside a request.
        audit_ip_address = "System"

    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO audit_log (
                username,
                role,
                action,
                details,
                ip_address,
                affected_record,
                module
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                audit_username,
                audit_role,
                audit_action,
                audit_details,
                audit_ip_address,
                audit_affected_record,
                audit_module,
            ),
        )
        connection.commit()
    except Error:
        # Logging must never break the action the user requested.
        pass
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


# ---------------------------------------------------------
# AUTH / ROLE HELPERS
# ---------------------------------------------------------


def refresh_session_user():
    user_id = session.get("user_id")
    if not user_id:
        return False

    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT user_id, username, role, is_active
            FROM users
            WHERE user_id = %s
            """,
            (user_id,),
        )
        user = cursor.fetchone()

        if not user or not user["is_active"]:
            session.clear()
            return False

        role = normalize_role(user["role"])
        if not role:
            session.clear()
            return False

        session["username"] = user["username"]
        session["role"] = role
        return True
    except Error:
        return False
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


def page_login_required(function):
    @wraps(function)
    def decorated_function(*args, **kwargs):
        if not refresh_session_user():
            return redirect(url_for("login_page"))
        return function(*args, **kwargs)
    return decorated_function


def api_login_required(function):
    @wraps(function)
    def decorated_function(*args, **kwargs):
        if not refresh_session_user():
            return jsonify({"error": "Login required"}), 401
        return function(*args, **kwargs)
    return decorated_function


def page_admin_required(function):
    @wraps(function)
    def decorated_function(*args, **kwargs):
        if not refresh_session_user():
            return redirect(url_for("login_page"))
        if session.get("role") != ADMIN_ROLE:
            flash("Administrator access is required.", "error")
            return redirect(url_for("dashboard"))
        return function(*args, **kwargs)
    return decorated_function


def api_admin_required(function):
    @wraps(function)
    def decorated_function(*args, **kwargs):
        if not refresh_session_user():
            return jsonify({"error": "Login required"}), 401
        if session.get("role") != ADMIN_ROLE:
            return jsonify({"error": "Administrator access required"}), 403
        return function(*args, **kwargs)
    return decorated_function


def page_leave_approver_required(function):
    """Allow only HR Officers and Administrators to review leave requests."""
    @wraps(function)
    def decorated_function(*args, **kwargs):
        if not refresh_session_user():
            return redirect(url_for("login_page"))
        if session.get("role") not in {ADMIN_ROLE, HR_ROLE}:
            flash("HR Officer or Administrator access is required.", "error")
            return redirect(url_for("dashboard"))
        return function(*args, **kwargs)
    return decorated_function


def api_leave_approver_required(function):
    """API equivalent of the leave approval role check."""
    @wraps(function)
    def decorated_function(*args, **kwargs):
        if not refresh_session_user():
            return jsonify({"error": "Login required"}), 401
        if session.get("role") not in {ADMIN_ROLE, HR_ROLE}:
            return jsonify({"error": "HR Officer or Administrator access required"}), 403
        return function(*args, **kwargs)
    return decorated_function


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


# ---------------------------------------------------------
# REPORT FILTER HELPERS - TASK 4
# ---------------------------------------------------------


def get_report_filters(args):
    filters = {
        "employee_name": str(args.get("employee_name", "")).strip(),
        "department_id": str(args.get("department_id", "")).strip(),
        "date_from": str(args.get("date_from", "")).strip(),
        "date_to": str(args.get("date_to", "")).strip(),
        "status": str(args.get("status", "")).strip().title(),
    }

    if len(filters["employee_name"]) > 100:
        return None, "Employee name search must not exceed 100 characters."

    if filters["department_id"]:
        try:
            department_id = int(filters["department_id"])
            if department_id <= 0:
                raise ValueError
            filters["department_id"] = department_id
        except ValueError:
            return None, "Please select a valid department."

    if filters["date_from"] and not valid_date(filters["date_from"]):
        return None, "Start date must use YYYY-MM-DD format."
    if filters["date_to"] and not valid_date(filters["date_to"]):
        return None, "End date must use YYYY-MM-DD format."
    if filters["date_from"] and filters["date_to"]:
        if filters["date_from"] > filters["date_to"]:
            return None, "Start date cannot be after end date."

    if filters["status"] and filters["status"] not in ALLOWED_STATUSES:
        return None, "Please select a valid attendance status."

    return filters, None


def fetch_attendance_report(filters):
    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        query = """
            SELECT
                attendance.attendance_id,
                attendance.employee_id,
                employees.first_name,
                employees.last_name,
                departments.department_name,
                attendance.date,
                attendance.check_in_time,
                attendance.check_out_time,
                attendance.scheduled_start_time,
                attendance.scheduled_end_time,
                attendance.total_working_hours,
                attendance.late_arrival_minutes,
                attendance.early_departure_minutes,
                attendance.weekend_attendance,
                attendance.status
            FROM attendance
            JOIN employees
                ON attendance.employee_id = employees.employee_id
            LEFT JOIN departments
                ON employees.department_id = departments.department_id
            WHERE 1 = 1
        """
        values = []

        if filters.get("employee_name"):
            query += " AND CONCAT(employees.first_name, ' ', employees.last_name) LIKE %s"
            values.append(f"%{filters['employee_name']}%")
        if filters.get("department_id"):
            query += " AND employees.department_id = %s"
            values.append(filters["department_id"])
        if filters.get("date_from"):
            query += " AND attendance.date >= %s"
            values.append(filters["date_from"])
        if filters.get("date_to"):
            query += " AND attendance.date <= %s"
            values.append(filters["date_to"])
        if filters.get("status"):
            query += " AND attendance.status = %s"
            values.append(filters["status"])

        query += " ORDER BY attendance.date DESC, attendance.attendance_id DESC"
        cursor.execute(query, tuple(values))
        return cursor.fetchall()
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


def fetch_departments():
    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT department_id, department_name FROM departments ORDER BY department_name ASC"
        )
        return cursor.fetchall()
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


def report_query_string(filters):
    values = {}
    for key, value in filters.items():
        if value not in (None, ""):
            values[key] = value
    return urlencode(values)


def display_value(value):
    if value in (None, ""):
        return "-"
    return str(value)


# ---------------------------------------------------------
# WEBSITE ROUTES
# ---------------------------------------------------------

@app.route("/")
def home():
    if "user_id" not in session:
        return redirect(url_for("login_page"))
    return redirect(url_for("dashboard"))


@app.route("/login-page")
def login_page():
    if "user_id" in session and refresh_session_user():
        return redirect(url_for("dashboard"))
    return render_template("login.html")


@app.route("/dashboard")
@page_login_required
def dashboard():
    stats = {
        "total_employees": 0,
        "present_today": 0,
        "absent_today": 0,
        "weekly_attendance": 0,
    }
    recent_activities = []
    dashboard_error = None

    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute("SELECT COUNT(*) AS total FROM employees")
        stats["total_employees"] = cursor.fetchone()["total"]

        cursor.execute(
            "SELECT COUNT(DISTINCT employee_id) AS total FROM attendance WHERE date = CURDATE() AND status IN ('Present', 'Late')"
        )
        stats["present_today"] = cursor.fetchone()["total"]

        cursor.execute(
            "SELECT COUNT(DISTINCT employee_id) AS total FROM attendance WHERE date = CURDATE() AND status = 'Absent'"
        )
        stats["absent_today"] = cursor.fetchone()["total"]

        cursor.execute(
            "SELECT COUNT(*) AS total FROM attendance WHERE YEARWEEK(date, 1) = YEARWEEK(CURDATE(), 1)"
        )
        stats["weekly_attendance"] = cursor.fetchone()["total"]

        cursor.execute(
            """
            SELECT
                attendance.attendance_id,
                employees.first_name,
                employees.last_name,
                attendance.date,
                attendance.check_in_time,
                attendance.check_out_time,
                attendance.scheduled_start_time,
                attendance.scheduled_end_time,
                attendance.total_working_hours,
                attendance.late_arrival_minutes,
                attendance.early_departure_minutes,
                attendance.weekend_attendance,
                attendance.status
            FROM attendance
            JOIN employees ON attendance.employee_id = employees.employee_id
            ORDER BY attendance.date DESC,
                     COALESCE(attendance.check_in_time, '00:00:00') DESC,
                     attendance.attendance_id DESC
            LIMIT 8
            """
        )
        recent_activities = cursor.fetchall()
    except Error as error:
        dashboard_error = f"Unable to load dashboard statistics: {error}"
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

    return render_template(
        "index.html",
        username=session.get("username"),
        role=session.get("role"),
        stats=stats,
        recent_activities=recent_activities,
        error=dashboard_error,
    )


@app.route("/employees-page")
@page_login_required
def employees_page():
    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                employees.employee_id,
                employees.employee_number,
                employees.first_name,
                employees.last_name,
                employees.email,
                employees.phone,
                employees.job_position,
                employees.employment_status,
                employees.photo_filename,
                departments.department_name
            FROM employees
            LEFT JOIN departments ON employees.department_id = departments.department_id
            ORDER BY employees.employee_id ASC
            """
        )
        employees = cursor.fetchall()
        cursor.execute("SELECT department_id, department_name FROM departments ORDER BY department_name")
        departments = cursor.fetchall()
        return render_template(
            "employees.html",
            employees=employees,
            departments=departments,
            username=session.get("username"),
            role=session.get("role"),
            genders=sorted(ALLOWED_GENDERS),
            employment_statuses=["Active", "Inactive"],
        )
    except Error as error:
        return render_template(
            "employees.html",
            employees=[],
            departments=[],
            error=f"Unable to load employees: {error}",
            username=session.get("username"),
            role=session.get("role"),
            genders=sorted(ALLOWED_GENDERS),
            employment_statuses=["Active", "Inactive"],
        ), 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


@app.route("/employee-photo/<path:filename>")
@page_login_required
def employee_photo(filename):
    return send_from_directory(EMPLOYEE_UPLOAD_FOLDER, Path(filename).name)


@app.route("/employees/create", methods=["POST"])
@page_login_required
def create_employee_page():
    employee, validation_error = validate_employee_input(request.form)
    if validation_error:
        flash(validation_error, "error")
        return redirect(url_for("employees_page"))

    photo = request.files.get("photo")
    if photo and photo.filename and session.get("role") != ADMIN_ROLE:
        flash("Only Administrators can upload employee photographs.", "error")
        return redirect(url_for("employees_page"))
    photo_error = validate_employee_photo(photo)
    if photo_error:
        flash(photo_error, "error")
        return redirect(url_for("employees_page"))

    photo_filename = None
    connection = None
    cursor = None
    try:
        if photo and photo.filename:
            photo_filename = save_employee_photo(photo)

        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO employees (
                employee_number, national_id_passport, first_name, last_name,
                date_of_birth, gender, residential_address, phone, email,
                job_position, department_id, hire_date, employment_status, photo_filename
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                employee["employee_number"], employee["national_id_passport"],
                employee["first_name"], employee["last_name"], employee["date_of_birth"],
                employee["gender"], employee["residential_address"], employee["phone"],
                employee["email"], employee["job_position"], employee["department_id"],
                employee["hire_date"], employee["employment_status"], photo_filename,
            ),
        )
        employee_id = cursor.lastrowid
        connection.commit()
        audit_log(
            "Employee created",
            f"Employee ID: {employee_id}; employee number: {employee['employee_number']}; name: {employee['first_name']} {employee['last_name']}",
        )
        flash("Employee profile created successfully.", "success")
        return redirect(url_for("employee_profile_page", employee_id=employee_id))
    except IntegrityError as error:
        if photo_filename:
            remove_employee_photo(photo_filename)
        if getattr(error, "errno", None) == 1062:
            flash("Employee number, National ID / Passport number or email is already in use.", "error")
        else:
            flash("The selected department does not exist.", "error")
    except Error as error:
        if photo_filename:
            remove_employee_photo(photo_filename)
        flash(f"Unable to create employee profile: {error}", "error")
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()
    return redirect(url_for("employees_page"))


@app.route("/employees/<int:employee_id>/profile")
@page_login_required
def employee_profile_page(employee_id):
    try:
        employee = fetch_employee_by_id(employee_id)
        if not employee:
            flash("Employee not found.", "error")
            return redirect(url_for("employees_page"))
        departments = fetch_departments()
        return render_template(
            "employee_profile.html",
            employee=employee,
            departments=departments,
            username=session.get("username"),
            role=session.get("role"),
            genders=sorted(ALLOWED_GENDERS),
            employment_statuses=["Active", "Inactive"],
        )
    except Error as error:
        flash(f"Unable to load employee profile: {error}", "error")
        return redirect(url_for("employees_page"))


@app.route("/employees/<int:employee_id>/edit-profile", methods=["POST"])
@page_login_required
def edit_employee_profile(employee_id):
    employee, validation_error = validate_employee_input(request.form)
    if validation_error:
        flash(validation_error, "error")
        return redirect(url_for("employee_profile_page", employee_id=employee_id))

    photo = request.files.get("photo")
    remove_photo = request.form.get("remove_photo") == "1"
    if (photo and photo.filename or remove_photo) and session.get("role") != ADMIN_ROLE:
        flash("Only Administrators can change employee photographs.", "error")
        return redirect(url_for("employee_profile_page", employee_id=employee_id))
    photo_error = validate_employee_photo(photo)
    if photo_error:
        flash(photo_error, "error")
        return redirect(url_for("employee_profile_page", employee_id=employee_id))

    connection = None
    cursor = None
    new_photo_filename = None
    old_photo_filename = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT photo_filename FROM employees WHERE employee_id = %s", (employee_id,))
        existing = cursor.fetchone()
        if not existing:
            flash("Employee not found.", "error")
            return redirect(url_for("employees_page"))

        old_photo_filename = existing.get("photo_filename")
        final_photo_filename = old_photo_filename
        if photo and photo.filename:
            new_photo_filename = save_employee_photo(photo)
            final_photo_filename = new_photo_filename
        elif remove_photo:
            final_photo_filename = None

        cursor.execute(
            """
            UPDATE employees SET
                employee_number = %s,
                national_id_passport = %s,
                first_name = %s,
                last_name = %s,
                date_of_birth = %s,
                gender = %s,
                residential_address = %s,
                phone = %s,
                email = %s,
                job_position = %s,
                department_id = %s,
                hire_date = %s,
                employment_status = %s,
                photo_filename = %s
            WHERE employee_id = %s
            """,
            (
                employee["employee_number"], employee["national_id_passport"],
                employee["first_name"], employee["last_name"], employee["date_of_birth"],
                employee["gender"], employee["residential_address"], employee["phone"],
                employee["email"], employee["job_position"], employee["department_id"],
                employee["hire_date"], employee["employment_status"], final_photo_filename,
                employee_id,
            ),
        )
        connection.commit()

        if old_photo_filename and old_photo_filename != final_photo_filename:
            remove_employee_photo(old_photo_filename)

        audit_log(
            "Employee updated",
            f"Employee ID: {employee_id}; employee number: {employee['employee_number']}; name: {employee['first_name']} {employee['last_name']}; status: {employee['employment_status']}",
        )
        flash("Employee profile updated successfully.", "success")
    except IntegrityError as error:
        if new_photo_filename:
            remove_employee_photo(new_photo_filename)
        if getattr(error, "errno", None) == 1062:
            flash("Employee number, National ID / Passport number or email is already in use.", "error")
        else:
            flash("The selected department does not exist.", "error")
    except Error as error:
        if new_photo_filename:
            remove_employee_photo(new_photo_filename)
        flash(f"Unable to update employee profile: {error}", "error")
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()
    return redirect(url_for("employee_profile_page", employee_id=employee_id))


@app.route("/attendance-page")
@page_login_required
def attendance_page():
    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                attendance.attendance_id,
                attendance.employee_id,
                employees.first_name,
                employees.last_name,
                attendance.date,
                attendance.check_in_time,
                attendance.check_out_time,
                attendance.scheduled_start_time,
                attendance.scheduled_end_time,
                attendance.total_working_hours,
                attendance.late_arrival_minutes,
                attendance.early_departure_minutes,
                attendance.weekend_attendance,
                attendance.status
            FROM attendance
            JOIN employees ON attendance.employee_id = employees.employee_id
            ORDER BY attendance.date DESC, attendance.attendance_id DESC
            """
        )
        attendance_records = cursor.fetchall()

        cursor.execute(
            """
            SELECT employee_id, employee_number, first_name, last_name
            FROM employees
            WHERE employment_status = 'Active'
            ORDER BY first_name, last_name
            """
        )
        employees = cursor.fetchall()

        return render_template(
            "attendance.html",
            attendance=attendance_records,
            employees=employees,
            username=session.get("username"),
            role=session.get("role"),
            today=date.today().isoformat(),
            scheduled_start=SCHEDULED_START_TIME.strftime("%H:%M"),
            scheduled_end=SCHEDULED_END_TIME.strftime("%H:%M"),
        )
    except Error as error:
        return render_template(
            "attendance.html",
            attendance=[],
            employees=[],
            error=f"Unable to load attendance records: {error}",
            username=session.get("username"),
            role=session.get("role"),
            today=date.today().isoformat(),
            scheduled_start=SCHEDULED_START_TIME.strftime("%H:%M"),
            scheduled_end=SCHEDULED_END_TIME.strftime("%H:%M"),
        ), 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


@app.route("/attendance-page/create", methods=["POST"])
@page_login_required
def create_attendance_page():
    attendance, validation_error = validate_attendance_input(request.form)
    if validation_error:
        flash(validation_error, "error")
        return redirect(url_for("attendance_page"))

    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO attendance (
                employee_id, date, check_in_time, check_out_time, status,
                scheduled_start_time, scheduled_end_time, total_working_hours,
                late_arrival_minutes, early_departure_minutes, weekend_attendance
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                attendance["employee_id"], attendance["date"],
                attendance["check_in_time"], attendance["check_out_time"],
                attendance["status"], attendance["scheduled_start_time"],
                attendance["scheduled_end_time"], attendance["total_working_hours"],
                attendance["late_arrival_minutes"], attendance["early_departure_minutes"],
                attendance["weekend_attendance"],
            ),
        )
        attendance_id = cursor.lastrowid
        connection.commit()
        audit_log(
            "Attendance record created",
            f"Attendance ID: {attendance_id}; employee ID: {attendance['employee_id']}; "
            f"date: {attendance['date']}; status: {attendance['status']}; "
            f"hours: {attendance['total_working_hours']}",
        )
        flash("Attendance saved and calculated automatically.", "success")
    except IntegrityError:
        flash("The selected employee does not exist.", "error")
    except Error as error:
        flash(f"Unable to save attendance record: {error}", "error")
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()
    return redirect(url_for("attendance_page"))


@app.route("/attendance-page/check-in", methods=["POST"])
@page_login_required
def attendance_check_in_now():
    employee_id = request.form.get("employee_id")
    now = datetime.now()
    payload = {
        "employee_id": employee_id,
        "date": now.date().isoformat(),
        "check_in_time": now.strftime("%H:%M:%S"),
        "check_out_time": None,
    }
    attendance, validation_error = validate_attendance_input(payload)
    if validation_error:
        flash(validation_error, "error")
        return redirect(url_for("attendance_page"))

    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT attendance_id, check_in_time, check_out_time FROM attendance WHERE employee_id = %s AND date = %s ORDER BY attendance_id DESC LIMIT 1",
            (attendance["employee_id"], attendance["date"]),
        )
        existing = cursor.fetchone()
        if existing and existing["check_in_time"]:
            flash("This employee is already checked in today.", "error")
            return redirect(url_for("attendance_page"))

        if existing:
            cursor.execute(
                """
                UPDATE attendance
                SET check_in_time=%s, status=%s, scheduled_start_time=%s, scheduled_end_time=%s,
                    total_working_hours=%s, late_arrival_minutes=%s, early_departure_minutes=%s, weekend_attendance=%s
                WHERE attendance_id=%s
                """,
                (
                    attendance["check_in_time"], attendance["status"], attendance["scheduled_start_time"],
                    attendance["scheduled_end_time"], attendance["total_working_hours"],
                    attendance["late_arrival_minutes"], attendance["early_departure_minutes"],
                    attendance["weekend_attendance"], existing["attendance_id"],
                ),
            )
            attendance_id = existing["attendance_id"]
        else:
            cursor.execute(
                """
                INSERT INTO attendance (
                    employee_id, date, check_in_time, check_out_time, status,
                    scheduled_start_time, scheduled_end_time, total_working_hours,
                    late_arrival_minutes, early_departure_minutes, weekend_attendance
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    attendance["employee_id"], attendance["date"], attendance["check_in_time"],
                    attendance["check_out_time"], attendance["status"], attendance["scheduled_start_time"],
                    attendance["scheduled_end_time"], attendance["total_working_hours"],
                    attendance["late_arrival_minutes"], attendance["early_departure_minutes"],
                    attendance["weekend_attendance"],
                ),
            )
            attendance_id = cursor.lastrowid
        connection.commit()
        audit_log("Employee checked in", f"Attendance ID: {attendance_id}; employee ID: {attendance['employee_id']}; time: {attendance['check_in_time']}; status: {attendance['status']}")
        flash(f"Check-in recorded at {now.strftime('%H:%M:%S')}. Status: {attendance['status']}.", "success")
    except Error as error:
        flash(f"Unable to record check-in: {error}", "error")
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()
    return redirect(url_for("attendance_page"))


@app.route("/attendance-page/check-out", methods=["POST"])
@page_login_required
def attendance_check_out_now():
    employee_id = request.form.get("employee_id")
    now = datetime.now()
    connection = None
    cursor = None
    try:
        employee_id = int(employee_id)
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT * FROM attendance
            WHERE employee_id = %s AND date = %s
            ORDER BY attendance_id DESC LIMIT 1
            """,
            (employee_id, now.date().isoformat()),
        )
        existing = cursor.fetchone()
        if not existing or not existing.get("check_in_time"):
            flash("This employee must check in before checking out.", "error")
            return redirect(url_for("attendance_page"))
        if existing.get("check_out_time"):
            flash("This employee is already checked out today.", "error")
            return redirect(url_for("attendance_page"))

        payload = {
            "employee_id": employee_id,
            "date": now.date().isoformat(),
            "check_in_time": str(existing["check_in_time"]),
            "check_out_time": now.strftime("%H:%M:%S"),
        }
        attendance, validation_error = validate_attendance_input(payload)
        if validation_error:
            flash(validation_error, "error")
            return redirect(url_for("attendance_page"))

        cursor.execute(
            """
            UPDATE attendance
            SET check_out_time=%s, status=%s, scheduled_start_time=%s, scheduled_end_time=%s,
                total_working_hours=%s, late_arrival_minutes=%s, early_departure_minutes=%s, weekend_attendance=%s
            WHERE attendance_id=%s
            """,
            (
                attendance["check_out_time"], attendance["status"], attendance["scheduled_start_time"],
                attendance["scheduled_end_time"], attendance["total_working_hours"],
                attendance["late_arrival_minutes"], attendance["early_departure_minutes"],
                attendance["weekend_attendance"], existing["attendance_id"],
            ),
        )
        connection.commit()
        audit_log(
            "Employee checked out",
            f"Attendance ID: {existing['attendance_id']}; employee ID: {employee_id}; time: {attendance['check_out_time']}; "
            f"hours: {attendance['total_working_hours']}; early departure: {attendance['early_departure_minutes']} min",
        )
        flash(f"Check-out recorded at {now.strftime('%H:%M:%S')}. Total working hours: {attendance['total_working_hours']}.", "success")
    except (TypeError, ValueError):
        flash("Please select a valid employee.", "error")
    except Error as error:
        flash(f"Unable to record check-out: {error}", "error")
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()
    return redirect(url_for("attendance_page"))


@app.route("/attendance-page/<int:attendance_id>/delete", methods=["POST"])
@page_login_required
def delete_attendance_page(attendance_id):
    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM attendance WHERE attendance_id = %s", (attendance_id,))
        attendance = cursor.fetchone()
        if not attendance:
            flash("Attendance record not found.", "error")
            return redirect(url_for("attendance_page"))
        cursor.execute("DELETE FROM attendance WHERE attendance_id = %s", (attendance_id,))
        connection.commit()
        audit_log("Attendance record deleted", f"Attendance ID: {attendance_id}; employee ID: {attendance['employee_id']}; date: {attendance['date']}")
        flash("Attendance record deleted successfully.", "success")
    except Error as error:
        flash(f"Unable to delete attendance record: {error}", "error")
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()
    return redirect(url_for("attendance_page"))


# ---------------------------------------------------------
# TASK 4: REPORT SEARCH / FILTERING
# TASK 5: REPORT EXPORT
# ---------------------------------------------------------

@app.route("/reports-page")
@page_login_required
def reports_page():
    filters, validation_error = get_report_filters(request.args)
    departments = []
    records = []
    error = validation_error

    try:
        departments = fetch_departments()
        if not error:
            records = fetch_attendance_report(filters)
    except Error as db_error:
        error = f"Unable to load report data: {db_error}"

    safe_filters = filters or {
        "employee_name": request.args.get("employee_name", ""),
        "department_id": request.args.get("department_id", ""),
        "date_from": request.args.get("date_from", ""),
        "date_to": request.args.get("date_to", ""),
        "status": request.args.get("status", ""),
    }

    return render_template(
        "reports.html",
        username=session.get("username"),
        role=session.get("role"),
        departments=departments,
        records=records,
        filters=safe_filters,
        export_query=report_query_string(filters) if filters and not error else "",
        error=error,
    )


@app.route("/reports/attendance/export/<file_format>")
@page_login_required
def export_attendance_report(file_format):
    file_format = file_format.lower()
    if file_format not in {"csv", "xlsx", "pdf"}:
        flash("Unsupported export format.", "error")
        return redirect(url_for("reports_page"))

    filters, validation_error = get_report_filters(request.args)
    if validation_error:
        flash(validation_error, "error")
        return redirect(url_for("reports_page", **request.args))

    try:
        records = fetch_attendance_report(filters)
    except Error:
        flash("Unable to generate the report export.", "error")
        return redirect(url_for("reports_page", **request.args))

    filename_base = f"attendance_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    if file_format == "csv":
        text_stream = io.StringIO()
        writer = csv.writer(text_stream)
        writer.writerow(["Employee", "Department", "Date", "Check In", "Check Out", "Status"])
        for row in records:
            writer.writerow([
                f"{row['first_name']} {row['last_name']}",
                display_value(row.get("department_name")),
                display_value(row.get("date")),
                display_value(row.get("check_in_time")),
                display_value(row.get("check_out_time")),
                display_value(row.get("status")),
            ])

        csv_bytes = io.BytesIO(("\ufeff" + text_stream.getvalue()).encode("utf-8"))
        csv_bytes.seek(0)
        audit_log("Attendance report exported", f"Format: CSV; rows: {len(records)}; filters: {filters}")
        return send_file(
            csv_bytes,
            as_attachment=True,
            download_name=f"{filename_base}.csv",
            mimetype="text/csv; charset=utf-8",
        )

    if file_format == "xlsx":
        from openpyxl import Workbook
        from openpyxl.styles import Font

        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = "Attendance Report"
        headers = ["Employee", "Department", "Date", "Check In", "Check Out", "Status"]
        worksheet.append(headers)
        for cell in worksheet[1]:
            cell.font = Font(bold=True)

        for row in records:
            worksheet.append([
                f"{row['first_name']} {row['last_name']}",
                display_value(row.get("department_name")),
                display_value(row.get("date")),
                display_value(row.get("check_in_time")),
                display_value(row.get("check_out_time")),
                display_value(row.get("status")),
            ])

        widths = [28, 22, 14, 14, 14, 14]
        for index, width in enumerate(widths, start=1):
            worksheet.column_dimensions[chr(64 + index)].width = width

        output = io.BytesIO()
        workbook.save(output)
        output.seek(0)
        audit_log("Attendance report exported", f"Format: XLSX; rows: {len(records)}; filters: {filters}")
        return send_file(
            output,
            as_attachment=True,
            download_name=f"{filename_base}.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    # PDF
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    output = io.BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=landscape(A4),
        rightMargin=10 * mm,
        leftMargin=10 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
    )
    styles = getSampleStyleSheet()
    story = [Paragraph("Attendance Report", styles["Title"]), Spacer(1, 5 * mm)]

    active_filter_parts = []
    if filters.get("employee_name"):
        active_filter_parts.append(f"Employee: {filters['employee_name']}")
    if filters.get("department_id"):
        active_filter_parts.append(f"Department ID: {filters['department_id']}")
    if filters.get("date_from"):
        active_filter_parts.append(f"From: {filters['date_from']}")
    if filters.get("date_to"):
        active_filter_parts.append(f"To: {filters['date_to']}")
    if filters.get("status"):
        active_filter_parts.append(f"Status: {filters['status']}")
    if active_filter_parts:
        story.append(Paragraph("Filters: " + " | ".join(active_filter_parts), styles["Normal"]))
        story.append(Spacer(1, 4 * mm))

    table_data = [["Employee", "Department", "Date", "Check In", "Check Out", "Status"]]
    for row in records:
        table_data.append([
            f"{row['first_name']} {row['last_name']}",
            display_value(row.get("department_name")),
            display_value(row.get("date")),
            display_value(row.get("check_in_time")),
            display_value(row.get("check_out_time")),
            display_value(row.get("status")),
        ])

    table = Table(table_data, repeatRows=1, colWidths=[52 * mm, 42 * mm, 28 * mm, 28 * mm, 28 * mm, 28 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E9ECEF")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(table)
    document.build(story)
    output.seek(0)
    audit_log("Attendance report exported", f"Format: PDF; rows: {len(records)}; filters: {filters}")
    return send_file(
        output,
        as_attachment=True,
        download_name=f"{filename_base}.pdf",
        mimetype="application/pdf",
    )


# ---------------------------------------------------------
# PHASE 7 WEEK 3: LEAVE MANAGEMENT MODULE
# ---------------------------------------------------------

@app.route("/leave-management")
@page_login_required
def leave_management_page():
    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT employee_id, employee_number, first_name, last_name
            FROM employees
            WHERE employment_status = 'Active'
            ORDER BY first_name, last_name
            """
        )
        employees = cursor.fetchall()

        cursor.execute(
            """
            SELECT
                leave_requests.leave_id,
                leave_requests.employee_id,
                employees.employee_number,
                employees.first_name,
                employees.last_name,
                leave_requests.leave_type,
                leave_requests.start_date,
                leave_requests.end_date,
                DATEDIFF(leave_requests.end_date, leave_requests.start_date) + 1 AS total_days,
                leave_requests.reason,
                leave_requests.status,
                leave_requests.requested_by,
                leave_requests.reviewed_by,
                leave_requests.reviewed_at,
                leave_requests.created_at,
                leave_requests.updated_at
            FROM leave_requests
            JOIN employees ON leave_requests.employee_id = employees.employee_id
            ORDER BY leave_requests.created_at DESC, leave_requests.leave_id DESC
            """
        )
        leave_requests = cursor.fetchall()

        return render_template(
            "leave_management.html",
            employees=employees,
            leave_requests=leave_requests,
            leave_types=sorted(ALLOWED_LEAVE_TYPES),
            username=session.get("username"),
            role=session.get("role"),
        )
    except Error as error:
        return render_template(
            "leave_management.html",
            employees=[],
            leave_requests=[],
            leave_types=sorted(ALLOWED_LEAVE_TYPES),
            username=session.get("username"),
            role=session.get("role"),
            error=f"Unable to load leave management: {error}",
        ), 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


@app.route("/leave-management/create", methods=["POST"])
@page_login_required
def create_leave_request_page():
    leave_request, validation_error = validate_leave_request_input(request.form)
    if validation_error:
        flash(validation_error, "error")
        return redirect(url_for("leave_management_page"))

    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            "SELECT employee_id, first_name, last_name FROM employees WHERE employee_id = %s",
            (leave_request["employee_id"],),
        )
        employee = cursor.fetchone()
        if not employee:
            flash("The selected employee does not exist.", "error")
            return redirect(url_for("leave_management_page"))

        cursor.execute(
            """
            INSERT INTO leave_requests (
                employee_id, leave_type, start_date, end_date, reason,
                status, requested_by
            ) VALUES (%s, %s, %s, %s, %s, 'Pending', %s)
            """,
            (
                leave_request["employee_id"],
                leave_request["leave_type"],
                leave_request["start_date"],
                leave_request["end_date"],
                leave_request["reason"],
                session.get("username"),
            ),
        )
        leave_id = cursor.lastrowid
        connection.commit()

        audit_log(
            "Leave request created",
            f"Leave ID: {leave_id}; employee ID: {leave_request['employee_id']}; "
            f"type: {leave_request['leave_type']}; {leave_request['start_date']} to {leave_request['end_date']}",
        )
        flash("Leave request created successfully and is pending review.", "success")
    except IntegrityError:
        flash("Unable to create leave request because the selected employee does not exist.", "error")
    except Error as error:
        flash(f"Unable to create leave request: {error}", "error")
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

    return redirect(url_for("leave_management_page"))


@app.route("/leave-management/<int:leave_id>/<decision>", methods=["POST"])
@page_leave_approver_required
def review_leave_request_page(leave_id, decision):
    decision_map = {"approve": "Approved", "reject": "Rejected"}
    new_status = decision_map.get(str(decision).lower())
    if not new_status:
        flash("Invalid leave review action.", "error")
        return redirect(url_for("leave_management_page"))

    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT leave_requests.leave_id, leave_requests.status, leave_requests.employee_id,
                   leave_requests.leave_type, leave_requests.start_date, leave_requests.end_date,
                   employees.first_name, employees.last_name
            FROM leave_requests
            JOIN employees ON leave_requests.employee_id = employees.employee_id
            WHERE leave_requests.leave_id = %s
            """,
            (leave_id,),
        )
        leave_request = cursor.fetchone()

        if not leave_request:
            flash("Leave request not found.", "error")
            return redirect(url_for("leave_management_page"))
        if leave_request["status"] != "Pending":
            flash("Only pending leave requests can be approved or rejected.", "error")
            return redirect(url_for("leave_management_page"))

        cursor.execute(
            """
            UPDATE leave_requests
            SET status = %s,
                reviewed_by = %s,
                reviewed_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE leave_id = %s
            """,
            (new_status, session.get("username"), leave_id),
        )
        connection.commit()

        audit_log(
            f"Leave request {new_status.lower()}",
            f"Leave ID: {leave_id}; employee ID: {leave_request['employee_id']}; "
            f"employee: {leave_request['first_name']} {leave_request['last_name']}; "
            f"type: {leave_request['leave_type']}; {leave_request['start_date']} to {leave_request['end_date']}",
        )
        flash(f"Leave request {new_status.lower()} successfully.", "success")
    except Error as error:
        flash(f"Unable to review leave request: {error}", "error")
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

    return redirect(url_for("leave_management_page"))


# ---------------------------------------------------------
# TASK 1 + TASK 2: USER MANAGEMENT / ROLES
# TASK 7: USER ACTION AUDITING
# ---------------------------------------------------------

@app.route("/users-page")
@page_admin_required
def users_page():
    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT user_id, username, role, is_active FROM users ORDER BY user_id ASC")
        users = cursor.fetchall()
        for user in users:
            user["role"] = normalize_role(user["role"]) or user["role"]

        return render_template(
            "users.html",
            users=users,
            username=session.get("username"),
            current_user_id=session.get("user_id"),
            roles=[ADMIN_ROLE, HR_ROLE],
        )
    except Error as error:
        return render_template(
            "users.html",
            users=[],
            username=session.get("username"),
            current_user_id=session.get("user_id"),
            roles=[ADMIN_ROLE, HR_ROLE],
            error=f"Unable to load users: {error}",
        ), 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


@app.route("/users/create", methods=["POST"])
@page_admin_required
def create_user():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    role = normalize_role(request.form.get("role"))

    validation_error = validate_username_password_role(username, password, role)
    if validation_error:
        flash(validation_error, "error")
        return redirect(url_for("users_page"))

    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO users (username, password, role, is_active) VALUES (%s, %s, %s, 1)",
            (username, generate_password_hash(password), role),
        )
        user_id = cursor.lastrowid
        connection.commit()
        audit_log("User created", f"User ID: {user_id}; username: {username}; role: {role}")
        flash("User created successfully.", "success")
    except IntegrityError:
        flash("That username already exists.", "error")
    except Error as error:
        flash(f"Unable to create user: {error}", "error")
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()
    return redirect(url_for("users_page"))


@app.route("/users/<int:user_id>/edit", methods=["POST"])
@page_admin_required
def edit_user(user_id):
    username = request.form.get("username", "").strip()
    new_role = normalize_role(request.form.get("role"))

    if len(username) < 3 or len(username) > 50:
        flash("Username must contain between 3 and 50 characters.", "error")
        return redirect(url_for("users_page"))
    if new_role not in ALLOWED_ROLES:
        flash("Please select a valid user role.", "error")
        return redirect(url_for("users_page"))
    if user_id == session.get("user_id") and new_role != ADMIN_ROLE:
        flash("You cannot remove your own Administrator role.", "error")
        return redirect(url_for("users_page"))

    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT user_id, username, role, is_active FROM users WHERE user_id = %s", (user_id,))
        existing_user = cursor.fetchone()
        if not existing_user:
            flash("User not found.", "error")
            return redirect(url_for("users_page"))

        old_role = normalize_role(existing_user["role"])
        if old_role == ADMIN_ROLE and new_role != ADMIN_ROLE and existing_user["is_active"] and count_active_administrators(cursor) <= 1:
            flash("The system must keep at least one active Administrator.", "error")
            return redirect(url_for("users_page"))

        cursor.execute("UPDATE users SET username = %s, role = %s WHERE user_id = %s", (username, new_role, user_id))
        connection.commit()
        audit_log(
            "User modified",
            f"User ID: {user_id}; username: {existing_user['username']} -> {username}; role: {old_role} -> {new_role}",
        )
        flash("User updated successfully.", "success")
    except IntegrityError:
        flash("That username is already being used.", "error")
    except Error as error:
        flash(f"Unable to update user: {error}", "error")
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()
    return redirect(url_for("users_page"))


@app.route("/users/<int:user_id>/password", methods=["POST"])
@page_admin_required
def change_user_password(user_id):
    new_password = request.form.get("password", "")
    if not new_password:
        flash("New password is required.", "error")
        return redirect(url_for("users_page"))
    if len(new_password) < 8:
        flash("New password must contain at least 8 characters.", "error")
        return redirect(url_for("users_page"))

    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute("UPDATE users SET password = %s WHERE user_id = %s", (generate_password_hash(new_password), user_id))
        connection.commit()
        if cursor.rowcount == 0:
            flash("User not found.", "error")
        else:
            audit_log("User password changed", f"User ID: {user_id}")
            flash("Password changed successfully.", "success")
    except Error as error:
        flash(f"Unable to change password: {error}", "error")
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()
    return redirect(url_for("users_page"))


@app.route("/users/<int:user_id>/toggle", methods=["POST"])
@page_admin_required
def toggle_user_active(user_id):
    if user_id == session.get("user_id"):
        flash("You cannot deactivate your own account.", "error")
        return redirect(url_for("users_page"))

    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT user_id, username, role, is_active FROM users WHERE user_id = %s", (user_id,))
        user = cursor.fetchone()
        if not user:
            flash("User not found.", "error")
            return redirect(url_for("users_page"))

        role = normalize_role(user["role"])
        if role == ADMIN_ROLE and user["is_active"] and count_active_administrators(cursor) <= 1:
            flash("The last active Administrator cannot be deactivated.", "error")
            return redirect(url_for("users_page"))

        new_status = 0 if user["is_active"] else 1
        cursor.execute("UPDATE users SET is_active = %s WHERE user_id = %s", (new_status, user_id))
        connection.commit()
        audit_log(
            "User modified",
            f"User ID: {user_id}; username: {user['username']}; account status: {'Active' if new_status else 'Inactive'}",
        )
        flash("User activated successfully." if new_status else "User deactivated successfully.", "success")
    except Error as error:
        flash(f"Unable to change account status: {error}", "error")
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()
    return redirect(url_for("users_page"))


@app.route("/users/<int:user_id>/delete", methods=["POST"])
@page_admin_required
def delete_user(user_id):
    if user_id == session.get("user_id"):
        flash("You cannot delete your own account.", "error")
        return redirect(url_for("users_page"))

    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT user_id, username, role, is_active FROM users WHERE user_id = %s", (user_id,))
        user = cursor.fetchone()
        if not user:
            flash("User not found.", "error")
            return redirect(url_for("users_page"))

        role = normalize_role(user["role"])
        if role == ADMIN_ROLE and user["is_active"] and count_active_administrators(cursor) <= 1:
            flash("The last active Administrator cannot be deleted.", "error")
            return redirect(url_for("users_page"))

        cursor.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
        connection.commit()
        audit_log("User deleted", f"User ID: {user_id}; username: {user['username']}; role: {role}")
        flash("User deleted successfully.", "success")
    except Error as error:
        flash(f"Unable to delete user: {error}", "error")
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()
    return redirect(url_for("users_page"))


# ---------------------------------------------------------
# TASK 7: AUDIT LOG PAGE
# ---------------------------------------------------------

@app.route("/audit-log")
@page_admin_required
def audit_log_page():
    filters = {
        "q": request.args.get("q", "").strip(),
        "username": request.args.get("username", "").strip(),
        "role": request.args.get("role", "").strip(),
        "module": request.args.get("module", "").strip(),
        "action": request.args.get("action", "").strip(),
        "date_from": request.args.get("date_from", "").strip(),
        "date_to": request.args.get("date_to", "").strip(),
    }

    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        query = """
            SELECT
                audit_id,
                username,
                role,
                action,
                details,
                ip_address,
                affected_record,
                module,
                created_at
            FROM audit_log
            WHERE 1 = 1
        """
        params = []

        if filters["q"]:
            search_value = f"%{filters['q']}%"
            query += """
                AND (
                    username LIKE %s
                    OR role LIKE %s
                    OR action LIKE %s
                    OR COALESCE(details, '') LIKE %s
                    OR COALESCE(ip_address, '') LIKE %s
                    OR COALESCE(affected_record, '') LIKE %s
                    OR COALESCE(module, '') LIKE %s
                )
            """
            params.extend([search_value] * 7)

        if filters["username"]:
            query += " AND username = %s"
            params.append(filters["username"])

        if filters["role"]:
            query += " AND role = %s"
            params.append(filters["role"])

        if filters["module"]:
            query += " AND module = %s"
            params.append(filters["module"])

        if filters["action"]:
            query += " AND action = %s"
            params.append(filters["action"])

        if filters["date_from"]:
            if not valid_date(filters["date_from"]):
                flash("From date must be a valid date.", "error")
                filters["date_from"] = ""
            else:
                query += " AND DATE(created_at) >= %s"
                params.append(filters["date_from"])

        if filters["date_to"]:
            if not valid_date(filters["date_to"]):
                flash("To date must be a valid date.", "error")
                filters["date_to"] = ""
            else:
                query += " AND DATE(created_at) <= %s"
                params.append(filters["date_to"])

        if filters["date_from"] and filters["date_to"]:
            start_date = datetime.strptime(filters["date_from"], "%Y-%m-%d").date()
            end_date = datetime.strptime(filters["date_to"], "%Y-%m-%d").date()
            if end_date < start_date:
                flash("To date cannot be earlier than From date.", "error")
                return redirect(url_for("audit_log_page"))

        query += " ORDER BY created_at DESC, audit_id DESC LIMIT 500"
        cursor.execute(query, tuple(params))
        logs = cursor.fetchall()

        cursor.execute(
            "SELECT DISTINCT username FROM audit_log "
            "WHERE username IS NOT NULL AND username <> '' ORDER BY username"
        )
        usernames = [row["username"] for row in cursor.fetchall()]

        cursor.execute(
            "SELECT DISTINCT role FROM audit_log "
            "WHERE role IS NOT NULL AND role <> '' ORDER BY role"
        )
        roles = [row["role"] for row in cursor.fetchall()]

        cursor.execute(
            "SELECT DISTINCT module FROM audit_log "
            "WHERE module IS NOT NULL AND module <> '' ORDER BY module"
        )
        modules = [row["module"] for row in cursor.fetchall()]

        cursor.execute(
            "SELECT DISTINCT action FROM audit_log "
            "WHERE action IS NOT NULL AND action <> '' ORDER BY action"
        )
        actions = [row["action"] for row in cursor.fetchall()]

        return render_template(
            "audit_log.html",
            logs=logs,
            filters=filters,
            usernames=usernames,
            roles=roles,
            modules=modules,
            actions=actions,
            username=session.get("username"),
            role=session.get("role"),
        )
    except Error as error:
        return render_template(
            "audit_log.html",
            logs=[],
            filters=filters,
            usernames=[],
            roles=[],
            modules=[],
            actions=[],
            username=session.get("username"),
            role=session.get("role"),
            error=f"Unable to load audit log: {error}",
        ), 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


# ---------------------------------------------------------
# AUTHENTICATION ROUTES
# ---------------------------------------------------------

@app.route("/register", methods=["POST"])
@api_admin_required
def register():
    data = request.get_json(silent=True) or request.form
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    role = normalize_role(data.get("role"))

    validation_error = validate_username_password_role(username, password, role)
    if validation_error:
        return jsonify({"error": validation_error}), 400

    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO users (username, password, role, is_active) VALUES (%s, %s, %s, 1)",
            (username, generate_password_hash(password), role),
        )
        user_id = cursor.lastrowid
        connection.commit()
        audit_log("User created", f"User ID: {user_id}; username: {username}; role: {role}")
        return jsonify({"message": "User registered successfully"}), 201
    except IntegrityError:
        return jsonify({"error": "Username already exists"}), 409
    except Error:
        return jsonify({"error": "Unable to register user"}), 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


@app.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or request.form
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))

    if not username or not password:
        message = "Username and password are required."
        if request.is_json:
            return jsonify({"error": message}), 400
        return render_template("login.html", error=message), 400

    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT user_id, username, password, role, is_active FROM users WHERE username = %s",
            (username,),
        )
        user = cursor.fetchone()

        if user and not user["is_active"]:
            message = "This account is inactive. Please contact an administrator."
            if request.is_json:
                return jsonify({"error": message}), 403
            return render_template("login.html", error=message), 403

        if user and check_password_hash(user["password"], password):
            role = normalize_role(user["role"])
            if not role:
                message = "This account has an invalid role."
                if request.is_json:
                    return jsonify({"error": message}), 403
                return render_template("login.html", error=message), 403

            session.clear()
            session["user_id"] = user["user_id"]
            session["username"] = user["username"]
            session["role"] = role
            audit_log("User login", f"User ID: {user['user_id']}", username=user["username"])

            if request.is_json:
                return jsonify({"message": "Login successful", "username": user["username"], "role": role})
            return redirect(url_for("dashboard"))

        message = "Invalid username or password."
        if request.is_json:
            return jsonify({"error": message}), 401
        return render_template("login.html", error=message), 401
    except Error:
        message = "Unable to connect to the database."
        if request.is_json:
            return jsonify({"error": "Unable to complete login"}), 500
        return render_template("login.html", error=message), 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


@app.route("/logout", methods=["GET", "POST"])
def logout():
    username = session.get("username")
    user_id = session.get("user_id")
    if username:
        audit_log("User logout", f"User ID: {user_id}", username=username)
    session.clear()

    if request.method == "POST" and request.is_json:
        return jsonify({"message": "Logout successful"})
    return redirect(url_for("login_page"))


# ---------------------------------------------------------
# EMPLOYEE CRUD API - PHASE 7 WEEK 1 PROFILE ENHANCEMENT
# ---------------------------------------------------------

@app.route("/employees", methods=["GET"])
@api_login_required
def get_employees():
    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                employees.employee_id,
                employees.employee_number,
                employees.national_id_passport,
                employees.first_name,
                employees.last_name,
                employees.date_of_birth,
                employees.gender,
                employees.residential_address,
                employees.email,
                employees.phone,
                employees.job_position,
                employees.department_id,
                departments.department_name,
                employees.hire_date,
                employees.employment_status,
                employees.photo_filename
            FROM employees
            LEFT JOIN departments ON employees.department_id = departments.department_id
            ORDER BY employees.employee_id ASC
            """
        )
        return jsonify(cursor.fetchall())
    except Error:
        return jsonify({"error": "Unable to retrieve employees"}), 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


@app.route("/employees", methods=["POST"])
@api_login_required
def add_employee():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON request body is required."}), 400

    employee, validation_error = validate_employee_input(data)
    if validation_error:
        return jsonify({"error": validation_error}), 400

    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO employees (
                employee_number, national_id_passport, first_name, last_name,
                date_of_birth, gender, residential_address, phone, email,
                job_position, department_id, hire_date, employment_status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                employee["employee_number"], employee["national_id_passport"],
                employee["first_name"], employee["last_name"], employee["date_of_birth"],
                employee["gender"], employee["residential_address"], employee["phone"],
                employee["email"], employee["job_position"], employee["department_id"],
                employee["hire_date"], employee["employment_status"],
            ),
        )
        employee_id = cursor.lastrowid
        connection.commit()
        audit_log(
            "Employee created",
            f"Employee ID: {employee_id}; employee number: {employee['employee_number']}; name: {employee['first_name']} {employee['last_name']}",
        )
        return jsonify({"message": "Employee added successfully", "employee_id": employee_id}), 201
    except IntegrityError as error:
        if getattr(error, "errno", None) == 1062:
            return jsonify({"error": "Employee number, National ID / Passport number or email is already in use."}), 409
        return jsonify({"error": "The selected department does not exist."}), 400
    except Error:
        return jsonify({"error": "Unable to add employee"}), 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


@app.route("/employees/<int:employee_id>", methods=["PUT"])
@api_login_required
def update_employee(employee_id):
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON request body is required."}), 400

    employee, validation_error = validate_employee_input(data)
    if validation_error:
        return jsonify({"error": validation_error}), 400

    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT employee_id FROM employees WHERE employee_id = %s", (employee_id,))
        if not cursor.fetchone():
            return jsonify({"error": "Employee not found"}), 404

        cursor.execute(
            """
            UPDATE employees SET
                employee_number = %s, national_id_passport = %s,
                first_name = %s, last_name = %s, date_of_birth = %s,
                gender = %s, residential_address = %s, phone = %s,
                email = %s, job_position = %s, department_id = %s,
                hire_date = %s, employment_status = %s
            WHERE employee_id = %s
            """,
            (
                employee["employee_number"], employee["national_id_passport"],
                employee["first_name"], employee["last_name"], employee["date_of_birth"],
                employee["gender"], employee["residential_address"], employee["phone"],
                employee["email"], employee["job_position"], employee["department_id"],
                employee["hire_date"], employee["employment_status"], employee_id,
            ),
        )
        connection.commit()
        audit_log(
            "Employee updated",
            f"Employee ID: {employee_id}; employee number: {employee['employee_number']}; name: {employee['first_name']} {employee['last_name']}",
        )
        return jsonify({"message": "Employee updated successfully"})
    except IntegrityError as error:
        if getattr(error, "errno", None) == 1062:
            return jsonify({"error": "Employee number, National ID / Passport number or email is already in use."}), 409
        return jsonify({"error": "The selected department does not exist."}), 400
    except Error:
        return jsonify({"error": "Unable to update employee"}), 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


@app.route("/employees/<int:employee_id>", methods=["DELETE"])
@api_login_required
def delete_employee(employee_id):
    connection = None
    cursor = None
    photo_filename = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT first_name, last_name, email, employee_number, photo_filename FROM employees WHERE employee_id = %s",
            (employee_id,),
        )
        employee = cursor.fetchone()
        if not employee:
            return jsonify({"error": "Employee not found"}), 404
        photo_filename = employee.get("photo_filename")

        cursor.execute("DELETE FROM employees WHERE employee_id = %s", (employee_id,))
        connection.commit()
        if photo_filename:
            remove_employee_photo(photo_filename)
        audit_log(
            "Employee deleted",
            f"Employee ID: {employee_id}; employee number: {employee.get('employee_number')}; name: {employee['first_name']} {employee['last_name']}; email: {employee['email']}",
        )
        return jsonify({"message": "Employee deleted successfully"})
    except IntegrityError:
        return jsonify({"error": "This employee has attendance records and cannot be deleted until those records are removed."}), 409
    except Error:
        return jsonify({"error": "Unable to delete employee"}), 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


# ---------------------------------------------------------
# ATTENDANCE CRUD API - TASK 6 VALIDATION + TASK 7 AUDIT
# ---------------------------------------------------------

@app.route("/attendance", methods=["GET"])
@api_login_required
def get_attendance():
    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                attendance.attendance_id,
                attendance.employee_id,
                employees.first_name,
                employees.last_name,
                attendance.date,
                attendance.check_in_time,
                attendance.check_out_time,
                attendance.scheduled_start_time,
                attendance.scheduled_end_time,
                attendance.total_working_hours,
                attendance.late_arrival_minutes,
                attendance.early_departure_minutes,
                attendance.weekend_attendance,
                attendance.status
            FROM attendance
            JOIN employees ON attendance.employee_id = employees.employee_id
            ORDER BY attendance.date DESC, attendance.attendance_id DESC
            """
        )
        return jsonify(cursor.fetchall())
    except Error:
        return jsonify({"error": "Unable to retrieve attendance records"}), 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


@app.route("/attendance", methods=["POST"])
@api_login_required
def add_attendance():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON request body is required."}), 400

    attendance, validation_error = validate_attendance_input(data)
    if validation_error:
        return jsonify({"error": validation_error}), 400

    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO attendance (
                employee_id, date, check_in_time, check_out_time, status,
                scheduled_start_time, scheduled_end_time, total_working_hours,
                late_arrival_minutes, early_departure_minutes, weekend_attendance
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                attendance["employee_id"], attendance["date"], attendance["check_in_time"],
                attendance["check_out_time"], attendance["status"],
                attendance["scheduled_start_time"], attendance["scheduled_end_time"],
                attendance["total_working_hours"], attendance["late_arrival_minutes"],
                attendance["early_departure_minutes"], attendance["weekend_attendance"],
            ),
        )
        attendance_id = cursor.lastrowid
        connection.commit()
        audit_log(
            "Attendance record created",
            f"Attendance ID: {attendance_id}; employee ID: {attendance['employee_id']}; date: {attendance['date']}; status: {attendance['status']}",
        )
        return jsonify({"message": "Attendance added successfully", "attendance_id": attendance_id}), 201
    except IntegrityError:
        return jsonify({"error": "The selected employee does not exist."}), 400
    except Error:
        return jsonify({"error": "Unable to add attendance record"}), 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


@app.route("/attendance/<int:attendance_id>", methods=["PUT"])
@api_login_required
def update_attendance(attendance_id):
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON request body is required."}), 400

    attendance, validation_error = validate_attendance_input(data)
    if validation_error:
        return jsonify({"error": validation_error}), 400

    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM attendance WHERE attendance_id = %s", (attendance_id,))
        existing = cursor.fetchone()
        if not existing:
            return jsonify({"error": "Attendance record not found"}), 404

        cursor.execute(
            """
            UPDATE attendance
            SET employee_id = %s, date = %s, check_in_time = %s, check_out_time = %s, status = %s,
                scheduled_start_time = %s, scheduled_end_time = %s, total_working_hours = %s,
                late_arrival_minutes = %s, early_departure_minutes = %s, weekend_attendance = %s
            WHERE attendance_id = %s
            """,
            (
                attendance["employee_id"], attendance["date"], attendance["check_in_time"],
                attendance["check_out_time"], attendance["status"],
                attendance["scheduled_start_time"], attendance["scheduled_end_time"],
                attendance["total_working_hours"], attendance["late_arrival_minutes"],
                attendance["early_departure_minutes"], attendance["weekend_attendance"], attendance_id,
            ),
        )
        connection.commit()
        audit_log(
            "Attendance record updated",
            f"Attendance ID: {attendance_id}; employee ID: {attendance['employee_id']}; date: {attendance['date']}; status: {attendance['status']}",
        )
        return jsonify({"message": "Attendance updated successfully"})
    except IntegrityError:
        return jsonify({"error": "The selected employee does not exist."}), 400
    except Error:
        return jsonify({"error": "Unable to update attendance record"}), 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


@app.route("/attendance/<int:attendance_id>", methods=["DELETE"])
@api_login_required
def delete_attendance(attendance_id):
    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM attendance WHERE attendance_id = %s", (attendance_id,))
        attendance = cursor.fetchone()
        if not attendance:
            return jsonify({"error": "Attendance record not found"}), 404

        cursor.execute("DELETE FROM attendance WHERE attendance_id = %s", (attendance_id,))
        connection.commit()
        audit_log(
            "Attendance record deleted",
            f"Attendance ID: {attendance_id}; employee ID: {attendance['employee_id']}; date: {attendance['date']}; status: {attendance['status']}",
        )
        return jsonify({"message": "Attendance deleted successfully"})
    except Error:
        return jsonify({"error": "Unable to delete attendance record"}), 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


# ---------------------------------------------------------
# PHASE 7 WEEK 3: LEAVE MANAGEMENT API
# ---------------------------------------------------------

@app.route("/leave-requests", methods=["GET"])
@api_login_required
def get_leave_requests():
    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                leave_requests.leave_id,
                leave_requests.employee_id,
                employees.employee_number,
                employees.first_name,
                employees.last_name,
                leave_requests.leave_type,
                leave_requests.start_date,
                leave_requests.end_date,
                leave_requests.reason,
                leave_requests.status,
                leave_requests.requested_by,
                leave_requests.reviewed_by,
                leave_requests.reviewed_at,
                leave_requests.created_at,
                leave_requests.updated_at
            FROM leave_requests
            JOIN employees ON leave_requests.employee_id = employees.employee_id
            ORDER BY leave_requests.created_at DESC, leave_requests.leave_id DESC
            """
        )
        return jsonify(cursor.fetchall())
    except Error:
        return jsonify({"error": "Unable to retrieve leave requests"}), 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


@app.route("/leave-requests", methods=["POST"])
@api_login_required
def add_leave_request():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON request body is required."}), 400

    leave_request, validation_error = validate_leave_request_input(data)
    if validation_error:
        return jsonify({"error": validation_error}), 400

    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT employee_id FROM employees WHERE employee_id = %s",
            (leave_request["employee_id"],),
        )
        if not cursor.fetchone():
            return jsonify({"error": "The selected employee does not exist."}), 400

        cursor.execute(
            """
            INSERT INTO leave_requests (
                employee_id, leave_type, start_date, end_date, reason,
                status, requested_by
            ) VALUES (%s, %s, %s, %s, %s, 'Pending', %s)
            """,
            (
                leave_request["employee_id"],
                leave_request["leave_type"],
                leave_request["start_date"],
                leave_request["end_date"],
                leave_request["reason"],
                session.get("username"),
            ),
        )
        leave_id = cursor.lastrowid
        connection.commit()
        audit_log(
            "Leave request created",
            f"Leave ID: {leave_id}; employee ID: {leave_request['employee_id']}; "
            f"type: {leave_request['leave_type']}; {leave_request['start_date']} to {leave_request['end_date']}",
        )
        return jsonify({"message": "Leave request created successfully", "leave_id": leave_id, "status": "Pending"}), 201
    except Error:
        return jsonify({"error": "Unable to create leave request"}), 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


@app.route("/leave-requests/<int:leave_id>/status", methods=["PATCH"])
@api_leave_approver_required
def update_leave_request_status(leave_id):
    data = request.get_json(silent=True) or {}
    new_status = str(data.get("status", "")).strip().title()
    if new_status not in {"Approved", "Rejected"}:
        return jsonify({"error": "Status must be Approved or Rejected."}), 400

    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT leave_id, employee_id, leave_type, start_date, end_date, status FROM leave_requests WHERE leave_id = %s",
            (leave_id,),
        )
        leave_request = cursor.fetchone()
        if not leave_request:
            return jsonify({"error": "Leave request not found"}), 404
        if leave_request["status"] != "Pending":
            return jsonify({"error": "Only pending leave requests can be approved or rejected."}), 409

        cursor.execute(
            """
            UPDATE leave_requests
            SET status = %s, reviewed_by = %s, reviewed_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE leave_id = %s
            """,
            (new_status, session.get("username"), leave_id),
        )
        connection.commit()
        audit_log(
            f"Leave request {new_status.lower()}",
            f"Leave ID: {leave_id}; employee ID: {leave_request['employee_id']}; "
            f"type: {leave_request['leave_type']}; {leave_request['start_date']} to {leave_request['end_date']}",
        )
        return jsonify({"message": f"Leave request {new_status.lower()} successfully", "status": new_status})
    except Error:
        return jsonify({"error": "Unable to update leave request status"}), 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


# ---------------------------------------------------------
# REPORTING / SEARCH API
# ---------------------------------------------------------

@app.route("/reports/employees", methods=["GET"])
@api_login_required
def employee_listing_report():
    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                employees.employee_id,
                employees.first_name,
                employees.last_name,
                employees.email,
                employees.phone,
                departments.department_name
            FROM employees
            LEFT JOIN departments ON employees.department_id = departments.department_id
            ORDER BY employees.employee_id ASC
            """
        )
        return jsonify(cursor.fetchall())
    except Error:
        return jsonify({"error": "Unable to generate employee report"}), 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


@app.route("/reports/attendance", methods=["GET"])
@api_login_required
def attendance_report():
    filters, validation_error = get_report_filters(request.args)
    if validation_error:
        return jsonify({"error": validation_error}), 400
    try:
        return jsonify(fetch_attendance_report(filters))
    except Error:
        return jsonify({"error": "Unable to generate attendance report"}), 500


@app.route("/reports/attendance/status/<status>", methods=["GET"])
@api_login_required
def attendance_by_status(status):
    normalized_status = status.strip().title()
    if normalized_status not in ALLOWED_STATUSES:
        return jsonify({"error": "Invalid attendance status"}), 400
    try:
        return jsonify(fetch_attendance_report({
            "employee_name": "",
            "department_id": "",
            "date_from": "",
            "date_to": "",
            "status": normalized_status,
        }))
    except Error:
        return jsonify({"error": "Unable to filter attendance records"}), 500


@app.route("/search/employees", methods=["GET"])
@api_login_required
def search_employees():
    keyword = request.args.get("q", "").strip()
    if len(keyword) > 100:
        return jsonify({"error": "Search text must not exceed 100 characters."}), 400
    search_value = f"%{keyword}%"

    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                employees.employee_id,
                employees.employee_number,
                employees.national_id_passport,
                employees.first_name,
                employees.last_name,
                employees.email,
                employees.phone,
                employees.job_position,
                employees.employment_status,
                departments.department_name,
                employees.photo_filename
            FROM employees
            LEFT JOIN departments ON employees.department_id = departments.department_id
            WHERE employees.employee_number LIKE %s
               OR employees.national_id_passport LIKE %s
               OR employees.first_name LIKE %s
               OR employees.last_name LIKE %s
               OR employees.email LIKE %s
               OR employees.job_position LIKE %s
               OR departments.department_name LIKE %s
            ORDER BY employees.employee_id ASC
            """,
            (search_value, search_value, search_value, search_value, search_value, search_value, search_value),
        )
        return jsonify(cursor.fetchall())
    except Error:
        return jsonify({"error": "Unable to search employees"}), 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


@app.route("/search/attendance", methods=["GET"])
@api_login_required
def search_attendance():
    # Supports the new Phase 6 filters and the old ?date=YYYY-MM-DD parameter.
    args = request.args.to_dict()
    if args.get("date") and not args.get("date_from") and not args.get("date_to"):
        args["date_from"] = args["date"]
        args["date_to"] = args["date"]

    filters, validation_error = get_report_filters(args)
    if validation_error:
        return jsonify({"error": validation_error}), 400
    try:
        return jsonify(fetch_attendance_report(filters))
    except Error:
        return jsonify({"error": "Unable to search attendance records"}), 500


if __name__ == "__main__":
    app.run(debug=True)