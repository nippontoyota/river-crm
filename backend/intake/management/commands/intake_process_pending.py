from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from intake.processor import process_pending


class Command(BaseCommand):
    help = 'Process pending intake, requested Meta fetches and uploads without a broker (run every five minutes).'

    def add_arguments(self, parser):
        parser.add_argument('--max-seconds', type=int, default=240)

    def handle(self, *args, **options):
        if settings.INTAKE_EXECUTION_MODE != 'database':
            raise CommandError('Set INTAKE_EXECUTION_MODE=database before running this processor.')
        if not 1 <= options['max_seconds'] <= 240:
            raise CommandError('--max-seconds must be between 1 and 240.')
        self.stdout.write(process_pending(options['max_seconds']))
