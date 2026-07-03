# Employee and Attendance Management System

## Overview

This project was developed as part of my internship at Xtratech.

The system is a web-based Employee and Attendance Management System built using Python, Flask, and MySQL. It allows administrators to manage employees, attendance records, user authentication, and reporting features.

---

# Technologies Used

- Python 3
- Flask
- MySQL
- MySQL Workbench
- SQL
- Git
- GitHub
- Visual Studio Code

---

# Project Structure

```
employee-attendance-system
│
├── backend
│   ├── app.py
│   └── db.py
│
├── database.sql
├── TECHNICAL_DOCUMENTATION.md
├── USER_GUIDE.md
├── README.md
└── .gitignore
```

---

# Features

## Employee Management

- Add employees
- View employees
- Update employees
- Delete employees

---

## Attendance Management

- Add attendance
- View attendance
- Update attendance
- Delete attendance

---

## Authentication

- User registration
- User login
- User logout
- Password hashing
- Session management

---

## Reporting

- Employee listing
- Attendance reports
- Employee search
- Attendance filtering

---

# Database

Database name:

```
employee_attendance_system
```

Tables:

- users
- departments
- employees
- attendance

---

# Installation

Clone the repository:

```bash
git clone https://github.com/yannys27/xtratech-internship-employee-attendance-system.git
```

Open the project:

```bash
cd xtratech-internship-employee-attendance-system
```

Install the required packages:

```bash
py -m pip install flask mysql-connector-python werkzeug
```

Start the application:

```bash
cd backend
py app.py
```

Open your browser:

```
http://127.0.0.1:5000
```

---

# API Endpoints

### Authentication

POST /register

POST /login

POST /logout

---

### Employees

GET /employees

POST /employees

PUT /employees/<id>

DELETE /employees/<id>

---

### Attendance

GET /attendance

POST /attendance

PUT /attendance/<id>

DELETE /attendance/<id>

---

### Reports

GET /reports/employees

GET /reports/attendance

GET /reports/attendance/status/<status>

GET /search/employees

GET /search/attendance

---

# Security

- Password hashing
- Protected routes
- Session authentication
- SQL Injection protection using parameterized queries
- Input validation

---

# Author

Karel Dos Santos

Internship Project – Xtratech

2026