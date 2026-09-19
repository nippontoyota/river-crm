from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from intake.tasks import purge_expired_answers, reconcile_forms, sweep_receipts


class Command(BaseCommand):
    help = 'Recover due intake and upload work from database state after an outage.'

    def handle(self, *args, **options):
        if settings.INTAKE_EXECUTION_MODE == 'database':
            call_command('intake_process_pending', stdout=self.stdout)
            return
        purge_expired_answers.run()
        sweep_receipts.run()
        reconcile_forms.run()
        self.stdout.write('Recovery sweep finished; due work was offered to the broker.')
