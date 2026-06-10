import mysql.connector

def get_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="K@rel2701",
        database="employee_attendance_system"
    )