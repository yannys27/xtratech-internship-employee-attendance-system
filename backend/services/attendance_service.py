# Phase 7 - Week 8 Code Refactoring
# Generated from the complete corrected Week 7 backend (commit 609db26 baseline).
# Existing behavior is preserved; code is separated by responsibility.

from datetime import datetime
from config import Config
from utilities.validators import parse_time, valid_date

SCHEDULED_START_TIME = datetime.strptime(Config.ATTENDANCE_START_TIME, "%H:%M").time()
SCHEDULED_END_TIME = datetime.strptime(Config.ATTENDANCE_END_TIME, "%H:%M").time()

def minutes_between(start_time, end_time):
    start_minutes = start_time.hour * 60 + start_time.minute
    end_minutes = end_time.hour * 60 + end_time.minute
    return end_minutes - start_minutes
def calculate_attendance_values(attendance_date, check_in, check_out):
    """Calculate Phase 7 Week 2 attendance values automatically."""
    record_date = datetime.strptime(attendance_date, "%Y-%m-%d").date()
    weekend_attendance = record_date.weekday() >= 5

    if check_out and not check_in:
        raise ValueError("A check-out time cannot be recorded without a check-in time.")
    if check_in and check_out and check_out < check_in:
        raise ValueError("Check-out time cannot be earlier than check-in time.")

    if not check_in:
        return {
            "status": "Absent",
            "total_working_hours": None,
            "late_arrival_minutes": 0,
            "early_departure_minutes": 0,
            "weekend_attendance": weekend_attendance,
        }

    late_arrival_minutes = 0
    early_departure_minutes = 0

    # Weekend attendance is tracked separately; weekend employees are not marked late/early.
    if not weekend_attendance:
        late_arrival_minutes = max(0, minutes_between(SCHEDULED_START_TIME, check_in))
        if check_out:
            early_departure_minutes = max(0, minutes_between(check_out, SCHEDULED_END_TIME))

    total_working_hours = None
    if check_out:
        worked_minutes = minutes_between(check_in, check_out)
        total_working_hours = round(worked_minutes / 60, 2)

    status = "Late" if late_arrival_minutes > 0 else "Present"

    return {
        "status": status,
        "total_working_hours": total_working_hours,
        "late_arrival_minutes": late_arrival_minutes,
        "early_departure_minutes": early_departure_minutes,
        "weekend_attendance": weekend_attendance,
    }
def validate_attendance_input(data):
    """Validate raw attendance input and calculate status/hours automatically."""
    employee_id = data.get("employee_id")
    attendance_date = str(data.get("date", "")).strip()
    check_in_raw = data.get("check_in_time")
    check_out_raw = data.get("check_out_time")

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

    check_in = parse_time(check_in_raw)
    check_out = parse_time(check_out_raw)

    if check_in is False:
        return None, "Check-in time must use HH:MM format."
    if check_out is False:
        return None, "Check-out time must use HH:MM format."

    try:
        calculated = calculate_attendance_values(attendance_date, check_in, check_out)
    except ValueError as error:
        return None, str(error)

    return {
        "employee_id": employee_id,
        "date": attendance_date,
        "check_in_time": check_in.strftime("%H:%M:%S") if check_in else None,
        "check_out_time": check_out.strftime("%H:%M:%S") if check_out else None,
        "scheduled_start_time": SCHEDULED_START_TIME.strftime("%H:%M:%S"),
        "scheduled_end_time": SCHEDULED_END_TIME.strftime("%H:%M:%S"),
        **calculated,
    }, None
