#!/usr/bin/env sh
# Roles: web (API via gunicorn) | scheduler (expiry scans + reminders) | any other command.
set -e
cd /app/backend
if [ "$1" = "web" ]; then
  python manage.py migrate --noinput
  python manage.py collectstatic --noinput >/dev/null
  if [ "${SEED_DEMO:-false}" = "true" ]; then
    if python -c "import django,os;os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings');django.setup();from accounts.models import User;import sys;sys.exit(0 if User.objects.exists() else 1)"; then
      echo "Database already populated - skipping demo seed"
    else
      python manage.py seed_demo
    fi
  fi
  exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers ${WEB_CONCURRENCY:-3} --timeout 120 --access-logfile -
elif [ "$1" = "scheduler" ]; then
  # wait for the web container to finish migrations
  until python manage.py migrate --check >/dev/null 2>&1; do echo "waiting for migrations..."; sleep 3; done
  exec python manage.py run_scheduler
else
  exec "$@"
fi
