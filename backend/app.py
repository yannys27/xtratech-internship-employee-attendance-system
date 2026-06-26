from flask import Flask, request, jsonify, session
from db import get_connection
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.secret_key = "change_this_secret_key"


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "Login required"}), 401
        return f(*args, **kwargs)

    return decorated_function


@app.route("/")
def home():
    return "Employee and Attendance Management System Backend is running"


# AUTHENTICATION ROUTES

@app.route("/register", methods=["POST"])
def register():
    data = request.json

    username = data.get("username")
    password = data.get("password")
    role = data.get("role", "admin")

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    hashed_password = generate_password_hash(password)

    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            "INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
            (username, hashed_password, role)
        )
        conn.commit()
        return jsonify({"message": "User registered successfully"})
    except:
        return jsonify({"error": "Username already exists"}), 400
    finally:
        cursor.close()
        conn.close()


@app.route("/login", methods=["POST"])
def login():
    data = request.json

    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM users WHERE username=%s", (username,))
    user = cursor.fetchone()

    cursor.close()
    conn.close()

    if user and check_password_hash(user["password"], password):
        session["user_id"] = user["user_id"]
        session["username"] = user["username"]
        session["role"] = user["role"]

        return jsonify({"message": "Login successful"})

    return jsonify({"error": "Invalid username or password"}), 401


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"message": "Logout successful"})


# EMPLOYEE CRUD ROUTES

@app.route("/employees", methods=["GET"])
@login_required
def get_employees():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM employees")
    employees = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify(employees)


@app.route("/employees", methods=["POST"])
@login_required
def add_employee():
    data = request.json

    first_name = data.get("first_name")
    last_name = data.get("last_name")
    email = data.get("email")
    phone = data.get("phone")
    department_id = data.get("department_id")

    if not first_name or not last_name or not email or not department_id:
        return jsonify({"error": "Missing required employee fields"}), 400

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO employees (first_name, last_name, email, phone, department_id)
        VALUES (%s, %s, %s, %s, %s)
    """, (first_name, last_name, email, phone, department_id))

    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({"message": "Employee added successfully"})


@app.route("/employees/<int:id>", methods=["PUT"])
@login_required
def update_employee(id):
    data = request.json

    first_name = data.get("first_name")
    last_name = data.get("last_name")
    email = data.get("email")
    phone = data.get("phone")
    department_id = data.get("department_id")

    if not first_name or not last_name or not email or not department_id:
        return jsonify({"error": "Missing required employee fields"}), 400

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE employees
        SET first_name=%s, last_name=%s, email=%s, phone=%s, department_id=%s
        WHERE employee_id=%s
    """, (first_name, last_name, email, phone, department_id, id))

    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({"message": "Employee updated successfully"})


@app.route("/employees/<int:id>", methods=["DELETE"])
@login_required
def delete_employee(id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM employees WHERE employee_id=%s", (id,))

    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({"message": "Employee deleted successfully"})


# ATTENDANCE CRUD ROUTES

@app.route("/attendance", methods=["GET"])
@login_required
def get_attendance():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM attendance")
    attendance = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify(attendance)


@app.route("/attendance", methods=["POST"])
@login_required
def add_attendance():
    data = request.json

    employee_id = data.get("employee_id")
    date = data.get("date")
    check_in_time = data.get("check_in_time")
    check_out_time = data.get("check_out_time")
    status = data.get("status")

    if not employee_id or not date or not status:
        return jsonify({"error": "Missing required attendance fields"}), 400

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO attendance (employee_id, date, check_in_time, check_out_time, status)
        VALUES (%s, %s, %s, %s, %s)
    """, (employee_id, date, check_in_time, check_out_time, status))

    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({"message": "Attendance added successfully"})


@app.route("/attendance/<int:id>", methods=["PUT"])
@login_required
def update_attendance(id):
    data = request.json

    employee_id = data.get("employee_id")
    date = data.get("date")
    check_in_time = data.get("check_in_time")
    check_out_time = data.get("check_out_time")
    status = data.get("status")

    if not employee_id or not date or not status:
        return jsonify({"error": "Missing required attendance fields"}), 400

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE attendance
        SET employee_id=%s, date=%s, check_in_time=%s, check_out_time=%s, status=%s
        WHERE attendance_id=%s
    """, (employee_id, date, check_in_time, check_out_time, status, id))

    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({"message": "Attendance updated successfully"})


@app.route("/attendance/<int:id>", methods=["DELETE"])
@login_required
def delete_attendance(id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM attendance WHERE attendance_id=%s", (id,))

    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({"message": "Attendance deleted successfully"})


# PHASE 4 - REPORTING ROUTES

@app.route("/reports/employees", methods=["GET"])
@login_required
def employee_listing_report():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT employees.employee_id,
               employees.first_name,
               employees.last_name,
               employees.email,
               employees.phone,
               departments.department_name
        FROM employees
        LEFT JOIN departments ON employees.department_id = departments.department_id
        ORDER BY employees.employee_id ASC
    """)

    employees = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify(employees)


@app.route("/reports/attendance", methods=["GET"])
@login_required
def attendance_report():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT attendance.attendance_id,
               employees.first_name,
               employees.last_name,
               attendance.date,
               attendance.check_in_time,
               attendance.check_out_time,
               attendance.status
        FROM attendance
        JOIN employees ON attendance.employee_id = employees.employee_id
        ORDER BY attendance.date DESC
    """)

    records = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify(records)


@app.route("/reports/attendance/status/<status>", methods=["GET"])
@login_required
def attendance_by_status(status):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT attendance.attendance_id,
               employees.first_name,
               employees.last_name,
               attendance.date,
               attendance.check_in_time,
               attendance.check_out_time,
               attendance.status
        FROM attendance
        JOIN employees ON attendance.employee_id = employees.employee_id
        WHERE attendance.status = %s
        ORDER BY attendance.date DESC
    """, (status,))

    records = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify(records)


@app.route("/search/employees", methods=["GET"])
@login_required
def search_employees():
    keyword = request.args.get("q", "")

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT employees.employee_id,
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
    """, (
        f"%{keyword}%",
        f"%{keyword}%",
        f"%{keyword}%",
        f"%{keyword}%"
    ))

    employees = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify(employees)


@app.route("/search/attendance", methods=["GET"])
@login_required
def search_attendance():
    status = request.args.get("status", "")
    date = request.args.get("date", "")

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    query = """
        SELECT attendance.attendance_id,
               employees.first_name,
               employees.last_name,
               attendance.date,
               attendance.check_in_time,
               attendance.check_out_time,
               attendance.status
        FROM attendance
        JOIN employees ON attendance.employee_id = employees.employee_id
        WHERE 1=1
    """

    values = []

    if status:
        query += " AND attendance.status = %s"
        values.append(status)

    if date:
        query += " AND attendance.date = %s"
        values.append(date)

    query += " ORDER BY attendance.date DESC"

    cursor.execute(query, values)
    records = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify(records)


if __name__ == "__main__":
    app.run(debug=True)