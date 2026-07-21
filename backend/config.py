import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", "3306"))
    DB_USER = os.getenv("DB_USER")
    DB_PASSWORD = os.getenv("DB_PASSWORD")
    DB_NAME = os.getenv("DB_NAME")
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY")

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