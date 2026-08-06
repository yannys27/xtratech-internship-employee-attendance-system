Employee and Attendance Management System

Overview

This project was developed as part of my internship at Xtratech. It is a web-based Employee and Attendance Management System built with Python, Flask and MySQL.

Technologies Used

Python 3

Flask

MySQL / MySQL Workbench

Werkzeug password hashing

OpenPyXL for Excel report export

ReportLab for PDF report export

HTML/CSS

Git and GitHub

Visual Studio Code

Main Features

Employee Management

View, create, update and delete employees through protected endpoints.

Email, phone and required-field validation.

Attendance Management

View, create, update and delete attendance records.

Validation for employee, date, time and status fields.

Authentication and User Management

Session-based login and logout.

Password hashing.

Administrator and HR Officer roles.

Administrators can create, edit, activate/deactivate and delete users.

Administrator-only routes are protected on the server.

Dashboard

Total employees.

Employees present today.

Employees absent today.

Attendance records for the current week.

Recent attendance activities.

Search and Filtering

Attendance reports can be filtered by:

Employee name.

Department.

Start and end date.

Attendance status.

Report Export

Filtered attendance reports can be exported as:

PDF.

Excel (.xlsx).

CSV.

Audit Log

The system records important activities such as:

User login and logout.

User creation, modification, password change, activation/deactivation and deletion.

Employee creation, update and deletion.

Attendance record creation, update and deletion.

Report exports.

Each audit entry stores the username, action, date/time and additional relevant information.

Database

Database name:

employee_attendance_system

Tables:

users

departments

employees

attendance

audit_log

Phase 6 Existing Database Update

For an existing database, do not run database.sql again. Run the Phase 6 update script once:

SOURCE phase6_tasks4_7.sql;

Or open phase6_tasks4_7.sql in MySQL Workbench and execute it.

Installation

Install the required Python packages from the project root:

py -m pip install -r requirements.txt

Start the application:

cd backend
py app.py

Open:

http://127.0.0.1:5000

Main Web Pages

/dashboard - Dashboard

/employees-page - Employee Management

/attendance-page - Attendance Management

/reports-page - Filterable reports and exports

/users-page - Administrator-only User Management

/audit-log - Administrator-only Audit Log

API Endpoints

Authentication

POST /register

POST /login

GET|POST /logout

Employees

GET /employees

POST /employees

PUT /employees/<id>

DELETE /employees/<id>

Attendance

GET /attendance

POST /attendance

PUT /attendance/<id>

DELETE /attendance/<id>

Reports

GET /reports/employees

GET /reports/attendance

GET /reports/attendance/status/<status>

GET /reports/attendance/export/pdf

GET /reports/attendance/export/xlsx

GET /reports/attendance/export/csv

GET /search/employees

GET /search/attendance

Security and Validation

Passwords are stored as hashes.

Protected routes require a valid session.

Administrator permissions are checked in the backend.

SQL queries use parameters.

Email, phone, required fields, roles, dates, times and attendance statuses are validated.

User-friendly validation messages are returned for invalid input.

Author

Karel Dos SantosInternship Project - Xtratech2026