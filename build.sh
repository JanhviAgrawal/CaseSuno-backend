#!/usr/bin/env bash
# Render build command:  ./build.sh
set -o errexit

pip install --upgrade pip
pip install -r requirements.txt

python manage.py collectstatic --no-input
python manage.py migrate --no-input
# Creates/updates the admin login from ADMIN_EMAIL / ADMIN_PASSWORD (skipped if not set)
python manage.py ensure_admin --if-configured
