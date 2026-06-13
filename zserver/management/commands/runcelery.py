import subprocess
import sys

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Start a Celery worker for this project."

    def handle(self, *args, **options):
        cmd = [sys.executable, "-m", "celery", "-A", "zproject", "worker", "--loglevel=info", "--pool=solo"]
        self.stdout.write(f"Starting Celery: {' '.join(cmd)}\n")
        subprocess.run(cmd)
