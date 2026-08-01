from functools import wraps

from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
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
# ROLE / AUTH HELPERS
# ---------------------------------------------------------

ADMIN_ROLE = "Administrator"
HR_ROLE = "HR Officer"
ALLOWED_ROLES = {ADMIN_ROLE, HR_ROLE}


def normalize_role(role):
    """Keeps old database role names compatible with Phase 6."""
    value = str(role or "").strip().lower().replace("_", " ")

    if value in {"admin", "administrator"}:
        return ADMIN_ROLE

    if value in {"employee", "hr", "hr officer"}:
        return HR_ROLE

    return None


def refresh_session_user():
    """
    Confirms that the logged-in user still exists and is active.
    It also refreshes username/role so permission changes apply immediately.
    """
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
            """
            SELECT COUNT(DISTINCT employee_id) AS total
            FROM attendance
            WHERE date = CURDATE() AND status = 'Present'
            """
        )
        stats["present_today"] = cursor.fetchone()["total"]

        cursor.execute(
            """
            SELECT COUNT(DISTINCT employee_id) AS total
            FROM attendance
            WHERE date = CURDATE() AND status = 'Absent'
            """
        )
        stats["absent_today"] = cursor.fetchone()["total"]

        cursor.execute(
            """
            SELECT COUNT(*) AS total
            FROM attendance
            WHERE YEARWEEK(date, 1) = YEARWEEK(CURDATE(), 1)
            """
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
            JOIN employees
                ON attendance.employee_id = employees.employee_id
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
            LEFT JOIN departments
                ON employees.department_id = departments.department_id
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
            JOIN employees
                ON attendance.employee_id = employees.employee_id
            ORDER BY attendance.date DESC
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


@app.route("/reports-page")
@page_login_required
def reports_page():
    return render_template(
        "reports.html",
        username=session.get("username"),
        role=session.get("role"),
    )


# ---------------------------------------------------------
# TASK 1 + TASK 2: USER MANAGEMENT / ROLES
# ---------------------------------------------------------

@app.route("/users-page")
@page_admin_required
def users_page():
    connection = None
    cursor = None

    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT user_id, username, role, is_active
            FROM users
            ORDER BY user_id ASC
            """
        )
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

    if len(username) < 3 or len(username) > 50:
        flash("Username must contain between 3 and 50 characters.", "error")
        return redirect(url_for("users_page"))

    if len(password) < 8:
        flash("Password must contain at least 8 characters.", "error")
        return redirect(url_for("users_page"))

    if role not in ALLOWED_ROLES:
        flash("Invalid role.", "error")
        return redirect(url_for("users_page"))

    connection = None
    cursor = None

    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO users (username, password, role, is_active)
            VALUES (%s, %s, %s, 1)
            """,
            (username, generate_password_hash(password), role),
        )
        connection.commit()
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
        flash("Invalid role.", "error")
        return redirect(url_for("users_page"))

    if user_id == session.get("user_id") and new_role != ADMIN_ROLE:
        flash("You cannot remove your own Administrator role.", "error")
        return redirect(url_for("users_page"))

    connection = None
    cursor = None

    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT user_id, role, is_active FROM users WHERE user_id = %s",
            (user_id,),
        )
        existing_user = cursor.fetchone()

        if not existing_user:
            flash("User not found.", "error")
            return redirect(url_for("users_page"))

        old_role = normalize_role(existing_user["role"])

        if (
            old_role == ADMIN_ROLE
            and new_role != ADMIN_ROLE
            and existing_user["is_active"]
            and count_active_administrators(cursor) <= 1
        ):
            flash("The system must keep at least one active Administrator.", "error")
            return redirect(url_for("users_page"))

        cursor.execute(
            """
            UPDATE users
            SET username = %s, role = %s
            WHERE user_id = %s
            """,
            (username, new_role, user_id),
        )
        connection.commit()
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

    if len(new_password) < 8:
        flash("New password must contain at least 8 characters.", "error")
        return redirect(url_for("users_page"))

    connection = None
    cursor = None

    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute(
            """
            UPDATE users
            SET password = %s
            WHERE user_id = %s
            """,
            (generate_password_hash(new_password), user_id),
        )
        connection.commit()

        if cursor.rowcount == 0:
            flash("User not found.", "error")
        else:
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
        cursor.execute(
            "SELECT user_id, role, is_active FROM users WHERE user_id = %s",
            (user_id,),
        )
        user = cursor.fetchone()

        if not user:
            flash("User not found.", "error")
            return redirect(url_for("users_page"))

        role = normalize_role(user["role"])

        if (
            role == ADMIN_ROLE
            and user["is_active"]
            and count_active_administrators(cursor) <= 1
        ):
            flash("The last active Administrator cannot be deactivated.", "error")
            return redirect(url_for("users_page"))

        new_status = 0 if user["is_active"] else 1
        cursor.execute(
            "UPDATE users SET is_active = %s WHERE user_id = %s",
            (new_status, user_id),
        )
        connection.commit()
        flash(
            "User activated successfully." if new_status else "User deactivated successfully.",
            "success",
        )

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
        cursor.execute(
            "SELECT user_id, role, is_active FROM users WHERE user_id = %s",
            (user_id,),
        )
        user = cursor.fetchone()

        if not user:
            flash("User not found.", "error")
            return redirect(url_for("users_page"))

        role = normalize_role(user["role"])

        if (
            role == ADMIN_ROLE
            and user["is_active"]
            and count_active_administrators(cursor) <= 1
        ):
            flash("The last active Administrator cannot be deleted.", "error")
            return redirect(url_for("users_page"))

        cursor.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
        connection.commit()
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
# AUTHENTICATION ROUTES
# ---------------------------------------------------------

@app.route("/register", methods=["POST"])
@api_admin_required
def register():
    """JSON registration endpoint kept for compatibility; Administrator only."""
    data = request.get_json(silent=True) or request.form

    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    role = normalize_role(data.get("role"))

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    if len(username) < 3 or len(username) > 50:
        return jsonify({"error": "Username must contain between 3 and 50 characters"}), 400

    if len(password) < 8:
        return jsonify({"error": "Password must contain at least 8 characters"}), 400

    if role not in ALLOWED_ROLES:
        return jsonify({"error": "Invalid user role"}), 400

    connection = None
    cursor = None

    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO users (username, password, role, is_active)
            VALUES (%s, %s, %s, 1)
            """,
            (username, generate_password_hash(password), role),
        )
        connection.commit()
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
        if request.is_json:
            return jsonify({"error": "Username and password are required"}), 400
        return render_template("login.html", error="Username and password are required"), 400

    connection = None
    cursor = None

    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT user_id, username, password, role, is_active
            FROM users
            WHERE username = %s
            """,
            (username,),
        )
        user = cursor.fetchone()

        if user and check_password_hash(user["password"], password):
            if not user["is_active"]:
                message = "This account is deactivated. Contact an Administrator."
                if request.is_json:
                    return jsonify({"error": message}), 403
                return render_template("login.html", error=message), 403

            role = normalize_role(user["role"])

            if not role:
                message = "This account does not have a valid system role."
                if request.is_json:
                    return jsonify({"error": message}), 403
                return render_template("login.html", error=message), 403

            session.clear()
            session["user_id"] = user["user_id"]
            session["username"] = user["username"]
            session["role"] = role

            if request.is_json:
                return jsonify(
                    {
                        "message": "Login successful",
                        "username": user["username"],
                        "role": role,
                    }
                )

            return redirect(url_for("dashboard"))

        if request.is_json:
            return jsonify({"error": "Invalid username or password"}), 401
        return render_template("login.html", error="Invalid username or password"), 401

    except Error:
        if request.is_json:
            return jsonify({"error": "Unable to complete login"}), 500
        return render_template("login.html", error="Unable to connect to the database"), 500

    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


@app.route("/logout", methods=["GET", "POST"])
def logout():
    session.clear()

    if request.method == "POST" and request.is_json:
        return jsonify({"message": "Logout successful"})

    return redirect(url_for("login_page"))


# ---------------------------------------------------------
# EMPLOYEE CRUD API
# Administrator and HR Officer can use these operations.
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
            LEFT JOIN departments
                ON employees.department_id = departments.department_id
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
        return jsonify({"error": "JSON request body is required"}), 400

    first_name = str(data.get("first_name", "")).strip()
    last_name = str(data.get("last_name", "")).strip()
    email = str(data.get("email", "")).strip()
    phone = str(data.get("phone", "")).strip()
    department_id = data.get("department_id")

    if not first_name or not last_name or not email or not department_id:
        return jsonify({"error": "First name, last name, email and department are required"}), 400

    if "@" not in email:
        return jsonify({"error": "A valid email address is required"}), 400

    connection = None
    cursor = None

    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO employees
                (first_name, last_name, email, phone, department_id)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (first_name, last_name, email, phone or None, department_id),
        )
        connection.commit()
        return jsonify(
            {"message": "Employee added successfully", "employee_id": cursor.lastrowid}
        ), 201

    except IntegrityError:
        return jsonify({"error": "An employee with this email already exists"}), 409

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
        return jsonify({"error": "JSON request body is required"}), 400

    first_name = str(data.get("first_name", "")).strip()
    last_name = str(data.get("last_name", "")).strip()
    email = str(data.get("email", "")).strip()
    phone = str(data.get("phone", "")).strip()
    department_id = data.get("department_id")

    if not first_name or not last_name or not email or not department_id:
        return jsonify({"error": "First name, last name, email and department are required"}), 400

    if "@" not in email:
        return jsonify({"error": "A valid email address is required"}), 400

    connection = None
    cursor = None

    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT employee_id FROM employees WHERE employee_id = %s", (employee_id,))

        if not cursor.fetchone():
            return jsonify({"error": "Employee not found"}), 404

        cursor.execute(
            """
            UPDATE employees
            SET first_name = %s,
                last_name = %s,
                email = %s,
                phone = %s,
                department_id = %s
            WHERE employee_id = %s
            """,
            (first_name, last_name, email, phone or None, department_id, employee_id),
        )
        connection.commit()
        return jsonify({"message": "Employee updated successfully"})

    except IntegrityError:
        return jsonify({"error": "Another employee already uses this email"}), 409

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
        cursor = connection.cursor()
        cursor.execute("DELETE FROM employees WHERE employee_id = %s", (employee_id,))
        connection.commit()

        if cursor.rowcount == 0:
            return jsonify({"error": "Employee not found"}), 404

        return jsonify({"message": "Employee deleted successfully"})

    except Error:
        return jsonify({"error": "Unable to delete employee"}), 500

    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


# ---------------------------------------------------------
# ATTENDANCE CRUD API
# Administrator and HR Officer can use these operations.
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
            JOIN employees
                ON attendance.employee_id = employees.employee_id
            ORDER BY attendance.date DESC
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
        return jsonify({"error": "JSON request body is required"}), 400

    employee_id = data.get("employee_id")
    attendance_date = data.get("date")
    check_in_time = data.get("check_in_time")
    check_out_time = data.get("check_out_time")
    status = str(data.get("status", "")).strip().title()
    allowed_statuses = {"Present", "Absent", "Late"}

    if not employee_id or not attendance_date or not status:
        return jsonify({"error": "Employee, date and status are required"}), 400

    if status not in allowed_statuses:
        return jsonify({"error": "Status must be Present, Absent or Late"}), 400

    connection = None
    cursor = None

    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO attendance
                (employee_id, date, check_in_time, check_out_time, status)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (employee_id, attendance_date, check_in_time, check_out_time, status),
        )
        connection.commit()
        return jsonify(
            {"message": "Attendance added successfully", "attendance_id": cursor.lastrowid}
        ), 201

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
        return jsonify({"error": "JSON request body is required"}), 400

    employee_id = data.get("employee_id")
    attendance_date = data.get("date")
    check_in_time = data.get("check_in_time")
    check_out_time = data.get("check_out_time")
    status = str(data.get("status", "")).strip().title()
    allowed_statuses = {"Present", "Absent", "Late"}

    if not employee_id or not attendance_date or not status:
        return jsonify({"error": "Employee, date and status are required"}), 400

    if status not in allowed_statuses:
        return jsonify({"error": "Status must be Present, Absent or Late"}), 400

    connection = None
    cursor = None

    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT attendance_id FROM attendance WHERE attendance_id = %s", (attendance_id,))

        if not cursor.fetchone():
            return jsonify({"error": "Attendance record not found"}), 404

        cursor.execute(
            """
            UPDATE attendance
            SET employee_id = %s,
                date = %s,
                check_in_time = %s,
                check_out_time = %s,
                status = %s
            WHERE attendance_id = %s
            """,
            (employee_id, attendance_date, check_in_time, check_out_time, status, attendance_id),
        )
        connection.commit()
        return jsonify({"message": "Attendance updated successfully"})

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
        cursor = connection.cursor()
        cursor.execute("DELETE FROM attendance WHERE attendance_id = %s", (attendance_id,))
        connection.commit()

        if cursor.rowcount == 0:
            return jsonify({"error": "Attendance record not found"}), 404

        return jsonify({"message": "Attendance deleted successfully"})

    except Error:
        return jsonify({"error": "Unable to delete attendance record"}), 500

    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


# ---------------------------------------------------------
# REPORTING AND SEARCH API
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
            LEFT JOIN departments
                ON employees.department_id = departments.department_id
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
            JOIN employees
                ON attendance.employee_id = employees.employee_id
            ORDER BY attendance.date DESC
            """
        )
        return jsonify(cursor.fetchall())

    except Error:
        return jsonify({"error": "Unable to generate attendance report"}), 500

    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


@app.route("/reports/attendance/status/<status>", methods=["GET"])
@api_login_required
def attendance_by_status(status):
    normalized_status = status.strip().title()

    if normalized_status not in {"Present", "Absent", "Late"}:
        return jsonify({"error": "Invalid attendance status"}), 400

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
            JOIN employees
                ON attendance.employee_id = employees.employee_id
            WHERE attendance.status = %s
            ORDER BY attendance.date DESC
            """,
            (normalized_status,),
        )
        return jsonify(cursor.fetchall())

    except Error:
        return jsonify({"error": "Unable to filter attendance records"}), 500

    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


@app.route("/search/employees", methods=["GET"])
@api_login_required
def search_employees():
    keyword = request.args.get("q", "").strip()
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
            LEFT JOIN departments
                ON employees.department_id = departments.department_id
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
    status = request.args.get("status", "").strip().title()
    attendance_date = request.args.get("date", "").strip()

    connection = None
    cursor = None

    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        query = """
            SELECT
                attendance.attendance_id,
                employees.first_name,
                employees.last_name,
                attendance.date,
                attendance.check_in_time,
                attendance.check_out_time,
                attendance.status
            FROM attendance
            JOIN employees
                ON attendance.employee_id = employees.employee_id
            WHERE 1 = 1
        """
        values = []

        if status:
            if status not in {"Present", "Absent", "Late"}:
                return jsonify({"error": "Invalid attendance status"}), 400
            query += " AND attendance.status = %s"
            values.append(status)

        if attendance_date:
            query += " AND attendance.date = %s"
            values.append(attendance_date)

        query += " ORDER BY attendance.date DESC"
        cursor.execute(query, tuple(values))
        return jsonify(cursor.fetchall())

    except Error:
        return jsonify({"error": "Unable to search attendance records"}), 500

    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


if __name__ == "__main__":
    app.run(debug=True)