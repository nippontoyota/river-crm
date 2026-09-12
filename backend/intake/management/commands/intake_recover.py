from django.core.management.base import BaseCommand
from intake.tasks import purge_expired_answers, reconcile_forms, sweep_receipts


class Command(BaseCommand):
    help = 'Recover due intake and upload work from database state after an outage.'

    def handle(self, *args, **options):
        purge_expired_answers.run()
        sweep_receipts.run()
        reconcile_forms.run()
        self.stdout.write('Recovery sweep finished; due work was offered to the broker.')
