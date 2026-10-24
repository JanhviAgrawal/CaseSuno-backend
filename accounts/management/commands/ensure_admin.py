"""
Create or update a CASE SUNO admin who can sign in to casesuno.in/admin
(and to the Django admin at /admin/ on the API).

Usage:
    python manage.py ensure_admin --email you@casesuno.in --password "..." --name "Your Name"

Or with environment variables (used automatically on Render deploys):
    ADMIN_EMAIL, ADMIN_PASSWORD, ADMIN_NAME
"""

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import AdminUser


class Command(BaseCommand):
    help = "Create or update the CASE SUNO admin login (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("--email", default=os.environ.get("ADMIN_EMAIL", ""))
        parser.add_argument("--password", default=os.environ.get("ADMIN_PASSWORD", ""))
        parser.add_argument("--name", default=os.environ.get("ADMIN_NAME", "CASE SUNO Admin"))
        parser.add_argument(
            "--if-configured",
            action="store_true",
            help="Exit quietly when no email/password is configured (for deploy scripts).",
        )

    @transaction.atomic
    def handle(self, *args, **opts):
        email = (opts["email"] or "").strip().lower()
        password = opts["password"] or ""
        name = (opts["name"] or "CASE SUNO Admin").strip()

        if not email or not password:
            if opts["if_configured"]:
                self.stdout.write("ensure_admin: ADMIN_EMAIL / ADMIN_PASSWORD not set — skipped.")
                return
            raise CommandError("Provide --email and --password (or ADMIN_EMAIL / ADMIN_PASSWORD).")
        if len(password) < 8:
            raise CommandError("Admin password must be at least 8 characters.")

        User = get_user_model()
        user = User.objects.filter(username__iexact=email).first() or User.objects.filter(email__iexact=email).first()
        created_user = user is None
        if user is None:
            user = User(username=email, email=email)
        user.email = email
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.set_password(password)
        user.save()

        admin = AdminUser.objects.filter(email__iexact=email).first()
        created_admin = admin is None
        if admin is None:
            admin = AdminUser(email=email)
        admin.user = user
        admin.name = name
        admin.role = AdminUser.Role.SUPER_ADMIN
        admin.is_active = True
        admin.save()

        self.stdout.write(
            self.style.SUCCESS(
                f"Admin {'created' if created_admin or created_user else 'updated'}: {email}"
            )
        )
