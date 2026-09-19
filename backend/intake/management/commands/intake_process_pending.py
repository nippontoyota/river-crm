from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from intake.processor import process_pending


class Command(BaseCommand):
    help = 'Process durable intake and uploads without a broker; optionally scan Meta and run reminders.'

    def add_arguments(self, parser):
        parser.add_argument('--max-seconds', type=int, default=240)
        parser.add_argument('--automatic-meta', action='store_true', help='Request enabled Meta form scans when 30 minutes overdue.')
        parser.add_argument('--reminders', action='store_true', help='Process follow-up and feedback reminders once under the processor lease.')

    def handle(self, *args, **options):
        if settings.INTAKE_EXECUTION_MODE != 'database':
            raise CommandError('Set INTAKE_EXECUTION_MODE=database before running this processor.')
        if not 1 <= options['max_seconds'] <= 240:
            raise CommandError('--max-seconds must be between 1 and 240.')
        try:
            summary = process_pending(options['max_seconds'], automatic_meta=options['automatic_meta'], reminders=options['reminders'])
        except Exception:
            raise CommandError('processor_failed; check database access and runtime configuration. Details redacted.') from None
        self.stdout.write(summary)
