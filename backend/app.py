import csv
import io
import re
from datetime import datetime
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
    session,
    url_for,
)
from mysql.connector import Error, IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from config import Config
from db import get_connection


app = Flask(__name__)
Config.validate()
app.config.from_object(Config)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"


# ---------------------------------------------------------
# CONSTANTS / VALIDATION HELPERS
# ---------------------------------------------------------

ADMIN_ROLE = "Administrator"
HR_ROLE = "HR Officer"
ALLOWED_ROLES = {ADMIN_ROLE, HR_ROLE}
ALLOWED_STATUSES = {"Present", "Absent", "Late"}

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
    first_name = str(data.get("first_name", "")).strip()
    last_name = str(data.get("last_name", "")).strip()
    email = str(data.get("email", "")).strip()
    phone = str(data.get("phone", "")).strip()
    department_id = data.get("department_id")

    if not first_name:
        return None, "First name is required."
    if not last_name:
        return None, "Last name is required."
    if len(first_name) > 50 or len(last_name) > 50:
        return None, "First name and last name must not exceed 50 characters."
    if not email:
        return None, "Email address is required."
    if not valid_email(email):
        return None, "Please enter a valid email address, for example name@example.com."
    if not valid_phone(phone):
        return None, "Please enter a valid phone number using 7 to 15 digits."

    try:
        department_id = int(department_id)
        if department_id <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return None, "A valid department is required."

    return {
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "phone": phone or None,
        "department_id": department_id,
    }, None


def validate_attendance_input(data):
    employee_id = data.get("employee_id")
    attendance_date = str(data.get("date", "")).strip()
    check_in_raw = data.get("check_in_time")
    check_out_raw = data.get("check_out_time")
    status = str(data.get("status", "")).strip().title()

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
    if status not in ALLOWED_STATUSES:
        return None, "Status must be Present, Absent or Late."

    check_in = parse_time(check_in_raw)
    check_out = parse_time(check_out_raw)

    if check_in is False:
        return None, "Check-in time must use HH:MM format."
    if check_out is False:
        return None, "Check-out time must use HH:MM format."
    if check_in and check_out and check_out < check_in:
        return None, "Check-out time cannot be earlier than check-in time."

    return {
        "employee_id": employee_id,
        "date": attendance_date,
        "check_in_time": str(check_in_raw).strip() if check_in_raw not in (None, "") else None,
        "check_out_time": str(check_out_raw).strip() if check_out_raw not in (None, "") else None,
        "status": status,
    }, None


# ---------------------------------------------------------
# AUDIT LOG HELPERS - TASK 7
# ---------------------------------------------------------


def audit_log(action, details=None, username=None):
    """
    Record an important activity. Audit failures do not break the main action.
    The Phase 6 SQL update must be run once to create the audit_log table.
    """
    audit_username = str(username or session.get("username") or "System")[:50]
    action = str(action or "Unknown action")[:100]
    details = str(details) if details else None

    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO audit_log (username, action, details)
            VALUES (%s, %s, %s)
            """,
            (audit_username, action, details),
        )
        connection.commit()
    except Error:
        # Logging should never prevent the requested operation from completing.
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
            "SELECT COUNT(DISTINCT employee_id) AS total FROM attendance WHERE date = CURDATE() AND status = 'Present'"
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
        employees = cursor.fetchall()
        return render_template(
            "employees.html",
            employees=employees,
            username=session.get("username"),
            role=session.get("role"),
        )
    except Error as error:
        return render_template(
            "employees.html",
            employees=[],
            error=f"Unable to load employees: {error}",
            username=session.get("username"),
            role=session.get("role"),
        ), 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


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
                employees.first_name,
                employees.last_name,
                attendance.date,
                attendance.check_in_time,
                attendance.check_out_time,
                attendance.status
            FROM attendance
            JOIN employees ON attendance.employee_id = employees.employee_id
            ORDER BY attendance.date DESC, attendance.attendance_id DESC
            """
        )
        attendance_records = cursor.fetchall()
        return render_template(
            "attendance.html",
            attendance=attendance_records,
            username=session.get("username"),
            role=session.get("role"),
        )
    except Error as error:
        return render_template(
            "attendance.html",
            attendance=[],
            error=f"Unable to load attendance records: {error}",
            username=session.get("username"),
            role=session.get("role"),
        ), 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


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
    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT audit_id, username, action, details, created_at
            FROM audit_log
            ORDER BY created_at DESC, audit_id DESC
            LIMIT 200
            """
        )
        logs = cursor.fetchall()
        return render_template(
            "audit_log.html",
            logs=logs,
            username=session.get("username"),
            role=session.get("role"),
        )
    except Error as error:
        return render_template(
            "audit_log.html",
            logs=[],
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
# EMPLOYEE CRUD API - TASK 6 VALIDATION + TASK 7 AUDIT
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
                employees.first_name,
                employees.last_name,
                employees.email,
                employees.phone,
                employees.department_id,
                departments.department_name
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
            INSERT INTO employees (first_name, last_name, email, phone, department_id)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                employee["first_name"], employee["last_name"], employee["email"],
                employee["phone"], employee["department_id"],
            ),
        )
        employee_id = cursor.lastrowid
        connection.commit()
        audit_log(
            "Employee created",
            f"Employee ID: {employee_id}; name: {employee['first_name']} {employee['last_name']}; email: {employee['email']}",
        )
        return jsonify({"message": "Employee added successfully", "employee_id": employee_id}), 201
    except IntegrityError as error:
        if getattr(error, "errno", None) == 1062:
            return jsonify({"error": "An employee with this email already exists."}), 409
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
        cursor.execute("SELECT * FROM employees WHERE employee_id = %s", (employee_id,))
        old_employee = cursor.fetchone()
        if not old_employee:
            return jsonify({"error": "Employee not found"}), 404

        cursor.execute(
            """
            UPDATE employees
            SET first_name = %s, last_name = %s, email = %s, phone = %s, department_id = %s
            WHERE employee_id = %s
            """,
            (
                employee["first_name"], employee["last_name"], employee["email"],
                employee["phone"], employee["department_id"], employee_id,
            ),
        )
        connection.commit()
        audit_log(
            "Employee updated",
            f"Employee ID: {employee_id}; name: {employee['first_name']} {employee['last_name']}; email: {employee['email']}",
        )
        return jsonify({"message": "Employee updated successfully"})
    except IntegrityError as error:
        if getattr(error, "errno", None) == 1062:
            return jsonify({"error": "Another employee already uses this email."}), 409
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
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT first_name, last_name, email FROM employees WHERE employee_id = %s", (employee_id,))
        employee = cursor.fetchone()
        if not employee:
            return jsonify({"error": "Employee not found"}), 404

        cursor.execute("DELETE FROM employees WHERE employee_id = %s", (employee_id,))
        connection.commit()
        audit_log(
            "Employee deleted",
            f"Employee ID: {employee_id}; name: {employee['first_name']} {employee['last_name']}; email: {employee['email']}",
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
            INSERT INTO attendance (employee_id, date, check_in_time, check_out_time, status)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                attendance["employee_id"], attendance["date"], attendance["check_in_time"],
                attendance["check_out_time"], attendance["status"],
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
            SET employee_id = %s, date = %s, check_in_time = %s, check_out_time = %s, status = %s
            WHERE attendance_id = %s
            """,
            (
                attendance["employee_id"], attendance["date"], attendance["check_in_time"],
                attendance["check_out_time"], attendance["status"], attendance_id,
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
                employees.first_name,
                employees.last_name,
                employees.email,
                employees.phone,
                departments.department_name
            FROM employees
            LEFT JOIN departments ON employees.department_id = departments.department_id
            WHERE employees.first_name LIKE %s
               OR employees.last_name LIKE %s
               OR employees.email LIKE %s
               OR departments.department_name LIKE %s
            ORDER BY employees.employee_id ASC
            """,
            (search_value, search_value, search_value, search_value),
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