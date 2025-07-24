import os
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.db import connection
from django.contrib.auth import get_user_model

class Command(BaseCommand):
    help = 'Run initial setup: migrate and create superuser'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.NOTICE("Running migrations..."))
        call_command('migrate', interactive=False)

        # Ensure the auth_user table exists before proceeding
        if not self.table_exists('auth_user'):
            self.stdout.write(self.style.ERROR("auth_user table does not exist. Migration likely failed."))
            return

        User = get_user_model()

        username = os.getenv('DJANGO_SUPERUSER_USERNAME')
        email = os.getenv('DJANGO_SUPERUSER_EMAIL')
        password = os.getenv('DJANGO_SUPERUSER_PASSWORD')

        if not all([username, email, password]):
            self.stdout.write(self.style.WARNING('Missing superuser environment variables. Skipping creation.'))
            return

        if not User.objects.filter(username=username).exists():
            User.objects.create_superuser(username, email, password)
            self.stdout.write(self.style.SUCCESS(f'Superuser "{username}" created.'))
        else:
            self.stdout.write(self.style.WARNING(f'Superuser "{username}" already exists.'))

    def table_exists(self, table_name):
        """Helper to check if a DB table exists before querying it."""
        with connection.cursor() as cursor:
            tables = connection.introspection.table_names()
            return table_name in tables
