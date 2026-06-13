import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "zproject.settings")

app = Celery("wrangle")

# Read config from Django settings, looking for CELERY_* keys.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks in all INSTALLED_APPS (looks for tasks.py).
app.autodiscover_tasks()
