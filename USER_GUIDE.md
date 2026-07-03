# User Guide

## Employee and Attendance Management System

This guide explains how to use the Employee and Attendance Management System.

---

# Starting the Application

1. Open the project folder.
2. Open the terminal.
3. Navigate to the backend folder.

```bash
cd backend
```

4. Start the application.

```bash
py app.py
```

5. Open your browser.

```
http://127.0.0.1:5000
```

---

# User Registration

To create a new user, send a POST request to:

```
POST /register
```

Example JSON:

```json
{
    "username":"admin",
    "password":"Admin123!",
    "role":"admin"
}
```

---

# User Login

Send a POST request to:

```
POST /login
```

Example:

```json
{
    "username":"admin",
    "password":"Admin123!"
}
```

If successful, the system creates a user session.

---

# Employee Management

The system allows users to:

- View employees
- Add employees
- Update employee information
- Delete employees

Available endpoints:

GET

```
/employees
```

POST

```
/employees
```

PUT

```
/employees/{id}
```

DELETE

```
/employees/{id}
```

---

# Attendance Management

Users can:

- View attendance
- Record attendance
- Update attendance
- Delete attendance

Endpoints:

GET

```
/attendance
```

POST

```
/attendance
```

PUT

```
/attendance/{id}
```

DELETE

```
/attendance/{id}
```

---

# Reporting

Available reports:

Employee Listing

```
GET /reports/employees
```

Attendance Report

```
GET /reports/attendance
```

Attendance by Status

```
GET /reports/attendance/status/{status}
```

Employee Search

```
GET /search/employees?q=value
```

Attendance Search

```
GET /search/attendance
```

---

# Security Features

The application includes:

- Password hashing
- Session-based authentication
- Protected routes
- Input validation
- SQL Injection protection using parameterized queries

---

# Troubleshooting

If the application does not start:

1. Make sure MySQL Server is running.
2. Verify the database credentials in `db.py`.
3. Install the required packages:

```bash
py -m pip install flask mysql-connector-python werkzeug
```

4. Restart the application:

```bash
py app.py
```

---

# GitHub Repository

https://github.com/yannys27/xtratech-internship-employee-attendance-system