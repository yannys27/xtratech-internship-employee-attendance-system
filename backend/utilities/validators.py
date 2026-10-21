# Phase 7 - Week 8 Code Refactoring
# Generated from the complete corrected Week 7 backend (commit 609db26 baseline).
# Existing behavior is preserved; code is separated by responsibility.

import re
from datetime import date, datetime

ADMIN_ROLE = "Administrator"
HR_ROLE = "HR Officer"
ALLOWED_ROLES = {ADMIN_ROLE, HR_ROLE}
ALLOWED_STATUSES = {"Present", "Absent", "Late"}
ALLOWED_GENDERS = {"Male", "Female", "Other", "Prefer not to say"}
ALLOWED_EMPLOYMENT_STATUSES = {"Active", "Inactive"}
ALLOWED_LEAVE_TYPES = {"Annual Leave", "Sick Leave", "Maternity Leave", "Other Leave"}
ALLOWED_LEAVE_STATUSES = {"Pending", "Approved", "Rejected"}

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
