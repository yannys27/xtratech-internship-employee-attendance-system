from flask import Flask, request, jsonify
from db import get_connection

app = Flask(__name__)

@app.route("/")
def home():
    return "Backend is running"

@app.route("/employees", methods=["GET"])
def get_employees():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM employees")
    employees = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(employees)

@app.route("/employees", methods=["POST"])
def add_employee():
    data = request.json
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO employees (first_name, last_name, email, phone, department_id)
        VALUES (%s, %s, %s, %s, %s)
    """, (
        data["first_name"],
        data["last_name"],
        data["email"],
        data["phone"],
        data["department_id"]
    ))

    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"message": "Employee added successfully"})

@app.route("/employees/<int:id>", methods=["PUT"])
def update_employee(id):
    data = request.json
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE employees
        SET first_name=%s, last_name=%s, email=%s, phone=%s, department_id=%s
        WHERE employee_id=%s
    """, (
        data["first_name"],
        data["last_name"],
        data["email"],
        data["phone"],
        data["department_id"],
        id
    ))

    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"message": "Employee updated successfully"})

@app.route("/employees/<int:id>", methods=["DELETE"])
def delete_employee(id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM employees WHERE employee_id=%s", (id,))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"message": "Employee deleted successfully"})

@app.route("/attendance", methods=["GET"])
def get_attendance():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM attendance")
    attendance = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(attendance)

@app.route("/attendance", methods=["POST"])
def add_attendance():
    data = request.json
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO attendance (employee_id, date, check_in_time, check_out_time, status)
        VALUES (%s, %s, %s, %s, %s)
    """, (
        data["employee_id"],
        data["date"],
        data["check_in_time"],
        data["check_out_time"],
        data["status"]
    ))

    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"message": "Attendance added successfully"})

@app.route("/attendance/<int:id>", methods=["PUT"])
def update_attendance(id):
    data = request.json
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE attendance
        SET employee_id=%s, date=%s, check_in_time=%s, check_out_time=%s, status=%s
        WHERE attendance_id=%s
    """, (
        data["employee_id"],
        data["date"],
        data["check_in_time"],
        data["check_out_time"],
        data["status"],
        id
    ))

    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"message": "Attendance updated successfully"})

@app.route("/attendance/<int:id>", methods=["DELETE"])
def delete_attendance(id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM attendance WHERE attendance_id=%s", (id,))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"message": "Attendance deleted successfully"})

if __name__ == "__main__":
    app.run(debug=True)