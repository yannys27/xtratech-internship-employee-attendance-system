# Technical Documentation

## Project Title
Employee and Attendance Management System

## Project Objective
The objective of this project is to develop a web-based system for managing employees and attendance records.

## Technologies Used
- Python
- Flask
- MySQL
- MySQL Workbench
- SQL
- Git
- GitHub
- Visual Studio Code

## System Modules
The system includes the following modules:

1. Employee Management
2. Attendance Management
3. Authentication and Security
4. Reporting Features

## Database Tables

### users
Stores system user login information.

Fields:
- user_id
- username
- password
- role

### departments
Stores department information.

Fields:
- department_id
- department_name

### employees
Stores employee information.

Fields:
- employee_id
- first_name
- last_name
- email
- phone
- department_id

### attendance
Stores attendance records.

Fields:
- attendance_id
- employee_id
- date
- check_in_time
- check_out_time
- status

## API Endpoints

### Authentication

| Method | Endpoint | Description |
|---|---|---|
| POST | /register | Register a new user |
| POST | /login | Login user |
| POST | /logout | Logout user |

### Employee Management

| Method | Endpoint | Description |
|---|---|---|
| GET | /employees | Get all employees |
| POST | /employees | Add a new employee |
| PUT | /employees/{id} | Update employee details |
| DELETE | /employees/{id} | Delete employee |

### Attendance Management

| Method | Endpoint | Description |
|---|---|---|
| GET | /attendance | Get all attendance records |
| POST | /attendance | Add attendance record |
| PUT | /attendance/{id} | Update attendance record |
| DELETE | /attendance/{id} | Delete attendance record |

### Reporting

| Method | Endpoint | Description |
|---|---|---|
| GET | /reports/employees | View employee listing report |
| GET | /reports/attendance | View attendance report |
| GET | /reports/attendance/status/{status} | Filter attendance by status |
| GET | /search/employees?q=value | Search employees |
| GET | /search/attendance | Search attendance records |

## Security Features
- Password hashing using Werkzeug.
- Session management using Flask sessions.
- Protected routes using login validation.
- Parameterized SQL queries to reduce SQL injection risk.
- Basic input validation.

## Installation Guide

1. Install required packages:

```bash
py -m pip install flask mysql-connector-python werkzeug