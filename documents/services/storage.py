
import io
import uuid
import zipfile
from pathlib import Path

try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError
except ImportError:  # pragma: no cover - storage is optional
    boto3 = None

    class BotoCoreError(Exception):
        pass

    class ClientError(Exception):
        pass

try:
    import clamd
except ImportError:  # pragma: no cover - antivirus is optional
    clamd = None

from django.conf import settings


# CASE SUNO roadmap: maximum upload size is 10 MB.
MAX_FILE_SIZE = 10 * 1024 * 1024

ALLOWED_TYPES = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".docx": (
        "application/vnd.openxmlformats-officedocument."
        "wordprocessingml.document"
    ),
}


class InvalidDocument(Exception):
    """The uploaded document is invalid or unsupported."""


class DocumentServiceUnavailable(Exception):
    """Storage or antivirus service is unavailable."""


def validate_document(filename, data):
    """Validate extension, size, and basic file content."""

    extension = Path(filename).suffix.lower()

    if extension not in ALLOWED_TYPES:
        raise InvalidDocument("unsupported_file_type")

    if not data:
        raise InvalidDocument("empty_file")

    if len(data) > MAX_FILE_SIZE:
        raise InvalidDocument("file_too_large")

    if extension == ".pdf":
        valid = data.startswith(b"%PDF-")

    elif extension == ".jpg":
        valid = data.startswith(b"\xff\xd8\xff")

    elif extension == ".png":
        valid = data.startswith(b"\x89PNG\r\n\x1a\n")

    else:
        # DOCX is a ZIP archive containing Word document files.
        valid = False

        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names = set(archive.namelist())
                valid = (
                    "[Content_Types].xml" in names
                    and "word/document.xml" in names
                )
        except (zipfile.BadZipFile, OSError):
            valid = False

    if not valid:
        raise InvalidDocument("file_content_does_not_match_type")

    return extension, ALLOWED_TYPES[extension]


def scan_for_virus(data):
    """Scan file contents before allowing them into private storage."""

    if clamd is None:
        raise DocumentServiceUnavailable("virus_scan_unavailable")

    try:
        scanner = clamd.ClamdNetworkSocket(
            host=settings.CLAMAV_HOST,
            port=settings.CLAMAV_PORT,
            timeout=30,
        )

        result = scanner.scan_stream(data)

        if not result or "stream" not in result:
            raise DocumentServiceUnavailable(
                "virus_scan_unavailable"
            )

        scan_status, scan_message = result["stream"]

        if scan_status == "FOUND":
            raise InvalidDocument("virus_detected")

        if scan_status != "OK":
            raise DocumentServiceUnavailable(
                "virus_scan_failed"
            )

    except (InvalidDocument, DocumentServiceUnavailable):
        raise

    except Exception as exc:
        raise DocumentServiceUnavailable(
            "virus_scan_unavailable"
        ) from exc


def get_s3_client():
    """Build an S3 client from Django settings."""

    if boto3 is None:
        raise DocumentServiceUnavailable("document_storage_not_configured")

    if not all((
        settings.S3_KEY,
        settings.S3_SECRET,
        settings.S3_BUCKET,
    )):
        raise DocumentServiceUnavailable(
            "document_storage_not_configured"
        )

    kwargs = {
        "aws_access_key_id": settings.S3_KEY,
        "aws_secret_access_key": settings.S3_SECRET,
        "region_name": settings.S3_REGION,
    }

    # A custom endpoint is required for many S3-compatible providers.
    if settings.S3_ENDPOINT:
        kwargs["endpoint_url"] = settings.S3_ENDPOINT

    try:
        return boto3.client("s3", **kwargs)
    except Exception as exc:
        raise DocumentServiceUnavailable(
            "document_storage_unavailable"
        ) from exc


def upload_document(matter_id, extension, content_type, data):
    """Upload a validated and scanned file to private object storage."""

    client = get_s3_client()

    # Generate a random object key instead of trusting the uploaded filename.
    file_key = (
        f"matters/{matter_id}/documents/"
        f"{uuid.uuid4().hex}{extension}"
    )

    try:
        client.upload_fileobj(
            io.BytesIO(data),
            settings.S3_BUCKET,
            file_key,
            ExtraArgs={
                "ContentType": content_type,
                "ContentDisposition": "attachment",
            },
        )

    except (BotoCoreError, ClientError, OSError) as exc:
        raise DocumentServiceUnavailable(
            "document_storage_unavailable"
        ) from exc

    return file_key


def delete_document(file_key):
    """Delete an object during database-failure cleanup."""

    client = get_s3_client()

    try:
        client.delete_object(
            Bucket=settings.S3_BUCKET,
            Key=file_key,
        )

    except (BotoCoreError, ClientError, OSError) as exc:
        raise DocumentServiceUnavailable(
            "document_storage_unavailable"
        ) from exc


def create_presigned_download_url(file_key, expires_in=300):
    """Generate a temporary download URL; default expiry is five minutes."""

    client = get_s3_client()

    try:
        return client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": settings.S3_BUCKET,
                "Key": file_key,
            },
            ExpiresIn=expires_in,
        )

    except (BotoCoreError, ClientError, OSError) as exc:
        raise DocumentServiceUnavailable(
            "document_storage_unavailable"
        ) from exc
