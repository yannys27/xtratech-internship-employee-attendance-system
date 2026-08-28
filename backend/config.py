import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()


class Config:
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", "3306"))
    DB_USER = os.getenv("DB_USER")
    DB_PASSWORD = os.getenv("DB_PASSWORD")
    DB_NAME = os.getenv("DB_NAME")
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY")

    # Configurable attendance schedule
    ATTENDANCE_START_TIME = os.getenv(
        "ATTENDANCE_START_TIME",
        "08:00"
    )

    ATTENDANCE_END_TIME = os.getenv(
        "ATTENDANCE_END_TIME",
        "17:00"
    )

    @classmethod
    def validate(cls):

        required_values = {
            "DB_USER": cls.DB_USER,
            "DB_PASSWORD": cls.DB_PASSWORD,
            "DB_NAME": cls.DB_NAME,
            "FLASK_SECRET_KEY": cls.SECRET_KEY,
        }

        missing = [
            name
            for name, value in required_values.items()
            if not value
        ]

        if missing:
            raise RuntimeError(
                "Missing environment variables: "
                + ", ".join(missing)
            )

        try:
            start = datetime.strptime(
                cls.ATTENDANCE_START_TIME,
                "%H:%M"
            ).time()

            end = datetime.strptime(
                cls.ATTENDANCE_END_TIME,
                "%H:%M"
            ).time()

        except ValueError as exc:
            raise RuntimeError(
                "ATTENDANCE_START_TIME and "
                "ATTENDANCE_END_TIME must use HH:MM format."
            ) from exc

        if end <= start:
            raise RuntimeError(
                "ATTENDANCE_END_TIME must be later "
                "than ATTENDANCE_START_TIME."
            )