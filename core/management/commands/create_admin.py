from django.core.management.base import BaseCommand
from django.core.management import call_command

class Command(BaseCommand):
    help = 'Run initial setup: migrate and create superuser'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.NOTICE("Running migrations..."))
        call_command('migrate')

        from django.contrib.auth.models import User
        if not User.objects.filter(username='erika').exists():
            User.objects.create_superuser('erika', 'erika@admin.com', 'erika')
            self.stdout.write(self.style.SUCCESS('Superuser created.'))
        else:
            self.stdout.write(self.style.WARNING('Superuser already exists.'))
