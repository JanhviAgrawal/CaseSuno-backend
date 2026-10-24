
from unittest.mock import patch

from django.test import SimpleTestCase

from .services.storage import (
    MAX_FILE_SIZE,
    InvalidDocument,
    validate_document,
)


class ValidateDocumentTests(SimpleTestCase):
    def test_accepts_pdf_with_valid_signature(self):
        extension, content_type = validate_document(
            "evidence.pdf",
            b"%PDF-1.7 test content",
        )

        self.assertEqual(extension, ".pdf")
        self.assertEqual(content_type, "application/pdf")

    def test_accepts_jpeg_with_valid_signature(self):
        extension, content_type = validate_document(
            "photo.jpg",
            b"\xff\xd8\xff test content",
        )

        self.assertEqual(extension, ".jpg")
        self.assertEqual(content_type, "image/jpeg")

    def test_accepts_png_with_valid_signature(self):
        extension, content_type = validate_document(
            "photo.png",
            b"\x89PNG\r\n\x1a\n test content",
        )

        self.assertEqual(extension, ".png")
        self.assertEqual(content_type, "image/png")

    def test_rejects_unsupported_extension(self):
        with self.assertRaises(InvalidDocument):
            validate_document("evidence.exe", b"test")

    def test_rejects_empty_file(self):
        with self.assertRaises(InvalidDocument):
            validate_document("evidence.pdf", b"")

    def test_rejects_file_over_10_mb(self):
        with self.assertRaises(InvalidDocument):
            validate_document(
                "evidence.pdf",
                b"%PDF-" + b"x" * MAX_FILE_SIZE,
            )

    def test_rejects_mismatched_file_content(self):
        with self.assertRaises(InvalidDocument):
            validate_document("evidence.pdf", b"not a PDF")

    def test_rejects_corrupt_docx(self):
        with self.assertRaises(InvalidDocument):
            validate_document("evidence.docx", b"not a ZIP archive")
