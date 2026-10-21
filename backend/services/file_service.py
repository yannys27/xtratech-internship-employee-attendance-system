# Phase 7 - Week 8 Code Refactoring
# Generated from the complete corrected Week 7 backend (commit 609db26 baseline).
# Existing behavior is preserved; code is separated by responsibility.

import io
import zipfile
from pathlib import Path
from uuid import uuid4
from werkzeug.utils import secure_filename

ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
ALLOWED_IMAGE_MIMETYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_EMPLOYEE_PHOTO_BYTES = 5 * 1024 * 1024

ALLOWED_DOCUMENT_TYPES = {
    "Employment Contract",
    "Curriculum Vitae (CV)",
    "Passport / National ID",
    "Certificates",
    "Employee Photograph",
}
DOCUMENT_TYPE_EXTENSIONS = {
    "Employment Contract": {"pdf", "doc", "docx"},
    "Curriculum Vitae (CV)": {"pdf", "doc", "docx"},
    "Passport / National ID": {"pdf", "jpg", "jpeg", "png", "webp"},
    "Certificates": {"pdf", "doc", "docx", "jpg", "jpeg", "png", "webp"},
    "Employee Photograph": {"jpg", "jpeg", "png", "webp"},
}
MAX_EMPLOYEE_DOCUMENT_BYTES = 10 * 1024 * 1024

BACKEND_ROOT = Path(__file__).resolve().parents[1]
EMPLOYEE_UPLOAD_FOLDER = BACKEND_ROOT / "uploads" / "employees"
DOCUMENT_UPLOAD_FOLDER = BACKEND_ROOT / "uploads" / "documents"

def ensure_upload_directories():
    EMPLOYEE_UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
    DOCUMENT_UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

def _read_uploaded_file_bytes(file_storage, max_bytes):
    """Read an upload safely and restore the stream position afterwards."""
    position = file_storage.stream.tell()
    try:
        file_storage.stream.seek(0)
        return file_storage.stream.read(max_bytes + 1)
    finally:
        file_storage.stream.seek(position)
def detect_employee_document_mime(file_storage, extension):
    """
    Detect the real file type from file content, not from the browser MIME type.

    Supported signatures:
    - PDF
    - JPEG
    - PNG
    - WEBP
    - DOCX (ZIP package containing Word document parts)
    - legacy DOC (OLE compound file containing WordDocument stream marker)
    """
    data = _read_uploaded_file_bytes(file_storage, MAX_EMPLOYEE_DOCUMENT_BYTES)

    if len(data) > MAX_EMPLOYEE_DOCUMENT_BYTES:
        return None

    if extension == "pdf":
        if data.startswith(b"%PDF-"):
            return "application/pdf"
        return None

    if extension in {"jpg", "jpeg"}:
        if len(data) >= 3 and data[:3] == b"\xff\xd8\xff":
            return "image/jpeg"
        return None

    if extension == "png":
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        return None

    if extension == "webp":
        if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return "image/webp"
        return None

    if extension == "docx":
        try:
            with zipfile.ZipFile(io.BytesIO(data), "r") as archive:
                names = set(archive.namelist())
                if (
                    "[Content_Types].xml" in names
                    and "word/document.xml" in names
                ):
                    return (
                        "application/vnd.openxmlformats-officedocument."
                        "wordprocessingml.document"
                    )
        except (zipfile.BadZipFile, OSError, ValueError):
            pass
        return None

    if extension == "doc":
        ole_signature = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
        word_document_marker = "WordDocument".encode("utf-16le")
        table_0_marker = "0Table".encode("utf-16le")
        table_1_marker = "1Table".encode("utf-16le")

        if (
            data.startswith(ole_signature)
            and word_document_marker in data
            and (table_0_marker in data or table_1_marker in data)
        ):
            return "application/msword"
        return None

    return None
def validate_employee_document(file_storage, document_type):
    """
    Validate an uploaded Week 5 employee document.

    Returns (error_message, detected_mime_type).  The MIME type is determined
    from the actual file content and never trusted from the client request.
    """
    if document_type not in ALLOWED_DOCUMENT_TYPES:
        return "Please select a valid document type.", None

    if not file_storage or not file_storage.filename:
        return "Please select a document to upload.", None

    original_name = secure_filename(file_storage.filename)
    if not original_name or "." not in original_name:
        return "The selected file must have a valid file extension.", None

    extension = original_name.rsplit(".", 1)[1].lower()
    allowed_extensions = DOCUMENT_TYPE_EXTENSIONS.get(document_type, set())

    if extension not in allowed_extensions:
        allowed_display = ", ".join(sorted(ext.upper() for ext in allowed_extensions))
        return (
            f"{document_type} must use one of these file types: {allowed_display}.",
            None,
        )

    position = file_storage.stream.tell()
    file_storage.stream.seek(0, 2)
    size = file_storage.stream.tell()
    file_storage.stream.seek(position)

    if size <= 0:
        return "The selected document is empty.", None

    if size > MAX_EMPLOYEE_DOCUMENT_BYTES:
        return "Employee documents must not exceed 10 MB.", None

    detected_mime = detect_employee_document_mime(file_storage, extension)

    if not detected_mime:
        return (
            f"The uploaded file content does not match the .{extension.upper()} "
            "file type. Please upload a genuine file rather than a renamed file.",
            None,
        )

    return None, detected_mime
def validate_employee_photo(file_storage):
    if not file_storage or not file_storage.filename:
        return None

    safe_name = secure_filename(file_storage.filename)
    if "." not in safe_name:
        return "Employee photograph must be a JPG, JPEG, PNG or WEBP image."

    extension = safe_name.rsplit(".", 1)[1].lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        return "Employee photograph must be a JPG, JPEG, PNG or WEBP image."

    # Validate the actual image signature instead of trusting the client MIME type.
    actual_mime = detect_employee_document_mime(file_storage, extension)
    if actual_mime not in ALLOWED_IMAGE_MIMETYPES:
        return "The uploaded file content does not match the selected image type."

    position = file_storage.stream.tell()
    file_storage.stream.seek(0, 2)
    size = file_storage.stream.tell()
    file_storage.stream.seek(position)
    if size > MAX_EMPLOYEE_PHOTO_BYTES:
        return "Employee photograph must not exceed 5 MB."
    return None
def save_employee_photo(file_storage):
    if not file_storage or not file_storage.filename:
        return None
    extension = secure_filename(file_storage.filename).rsplit(".", 1)[1].lower()
    filename = f"{uuid4().hex}.{extension}"
    file_storage.save(EMPLOYEE_UPLOAD_FOLDER / filename)
    return filename
def remove_employee_photo(filename):
    if not filename:
        return
    safe_name = Path(str(filename)).name
    target = EMPLOYEE_UPLOAD_FOLDER / safe_name
    try:
        if target.is_file():
            target.unlink()
    except OSError:
        pass
def save_employee_document(file_storage):
    """Store a document with a random server-side filename."""
    original_name = secure_filename(file_storage.filename)
    extension = original_name.rsplit(".", 1)[1].lower()
    stored_filename = f"{uuid4().hex}.{extension}"
    file_storage.save(DOCUMENT_UPLOAD_FOLDER / stored_filename)
    return stored_filename, original_name
def remove_employee_document_file(stored_filename):
    """Remove a stored employee document without allowing path traversal."""
    if not stored_filename:
        return

    safe_name = Path(str(stored_filename)).name
    target = DOCUMENT_UPLOAD_FOLDER / safe_name

    try:
        if target.is_file():
            target.unlink()
    except OSError:
        pass
