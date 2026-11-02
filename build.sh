#!/usr/bin/env bash
# exit on error
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate
python manage.py createcachetable

# Create the first SYSTEM_ADMIN when SYSTEM_ADMIN_EMAIL and
# SYSTEM_ADMIN_PASSWORD are set. Safe on every deploy: it does nothing once
# an active SYSTEM_ADMIN exists. A failure is logged but does not stop the
# deploy. Remove SYSTEM_ADMIN_PASSWORD from the environment after first login.
if [ -n "$SYSTEM_ADMIN_EMAIL" ]; then
  python manage.py create_system_admin --noinput || echo "create_system_admin failed - check SYSTEM_ADMIN_EMAIL and SYSTEM_ADMIN_PASSWORD"
fi
