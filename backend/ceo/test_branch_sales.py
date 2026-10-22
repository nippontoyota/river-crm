import csv
import io
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from leads.models import CallLog, Lead, SystemConfig


class BranchSalesTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.ceo = User.objects.create_user('branch-ceo@example.com', role='CEO')
        self.ps = User.objects.create_user('branch-ps@example.com', role='SO', location='Kochi')
        self.client.force_authenticate(self.ceo)
        SystemConfig.objects.update_or_create(pk=1, defaults={'lists': {'branches': ['Kochi', 'Thrissur', 'Empty']}})
        self.today = timezone.localdate()
        self.leads = []
        for index, status in enumerate(['FRESH', 'BOOKED', 'WON', 'LOST', 'UNQUALIFIED']):
            self.leads.append(Lead.objects.create(name=f'Kochi {status}', phone=f'90000000{index:02}', branch=' Kochi ' if index % 2 else 'KOCHI', source='WEBSITE', enquiry_date=self.today, status=status, assigned_ps=self.ps))
        self.other = Lead.objects.create(name='Other branch', phone='9111111111', branch='Thrissur', status='BOOKED', enquiry_date=self.today)
        self.old = Lead.objects.create(name='Old enquiry', phone='9222222222', branch='Kochi', status='BOOKED', enquiry_date=self.today-timedelta(days=60))
        self.unknown = Lead.objects.create(name='Unknown branch', phone='9333333333', branch='', enquiry_date=self.today)
        self.deleted = Lead.objects.create(name='Deleted', phone='9444444444', branch='Kochi', status='WON', enquiry_date=self.today, deleted_at=timezone.now())
        earlier = CallLog.objects.create(lead=self.leads[2], so=self.ps, status='WON')
        CallLog.objects.filter(pk=earlier.pk).update(created_at=timezone.now()-timedelta(days=3))
        self.call = CallLog.objects.create(lead=self.leads[2], so=self.ps, status='WON')
        CallLog.objects.create(lead=self.old, so=self.ps, status='BOOKED')
        CallLog.objects.create(lead=self.other, so=self.ps, status='BOOKED')
        CallLog.objects.create(lead=self.deleted, so=self.ps, status='WON')

    def get(self, section, **filters):
        response = self.client.get(f'/api/ceo/{section}/', {'range': 'today', **filters})
        self.assertEqual(response.status_code, 200, getattr(response, 'data', None))
        return response

    def test_cohort_counts_match_every_branch_drilldown_in_both_modes(self):
        for mode in ['period', 'cohort']:
            rows = self.get('branch-sales', mode=mode).data['results']
            kochi = next(row for row in rows if row['key'] == 'kochi')
            self.assertEqual([kochi[key] for key in ['total', 'booked', 'retailed', 'lost', 'conversion']], [5, 1, 1, 2, 20.0])
            self.assertEqual(kochi['last_call_lead_id'], self.leads[2].pk)
            self.assertEqual(kochi['last_call'], self.call.created_at)
            for row in rows:
                for metric in ['total', 'booked', 'retailed', 'lost']:
                    result = self.get('leads', mode=mode, branch=row['key'], branch_metric=metric).data
                    self.assertEqual(result['count'], row[metric], (row['key'], metric))
                    self.assertNotIn(self.deleted.pk, [lead['id'] for lead in result['results']])
            empty = next(row for row in rows if row['key'] == 'empty')
            self.assertEqual((empty['total'], empty['conversion'], empty['last_call']), (0, 0, None))
        self.assertEqual(self.get('overview').data['branch_sales'], self.get('branch-sales').data['results'])

    def test_scoping_csv_and_last_call_history(self):
        rows = self.get('branch-sales', branch='kochi', source='WEBSITE', employee=self.ps.pk).data['results']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['total'], 5)
        self.assertEqual(rows[0]['last_call_lead_id'], self.leads[2].pk)
        export = self.get('export/branch-sales', branch='kochi')
        records = list(csv.DictReader(io.StringIO('\n'.join(b''.join(export.streaming_content).decode('utf-8-sig').splitlines()[2:]))))
        self.assertEqual(list(records[0]), ['Branch', 'Total', 'Booked', 'Retailed', 'Lost', 'Conv.', 'Last call'])
        self.assertEqual(records[0]['Lost'], '2')
        export = self.get('export/leads', branch='kochi', branch_metric='lost')
        records = list(csv.DictReader(io.StringIO('\n'.join(b''.join(export.streaming_content).decode('utf-8-sig').splitlines()[2:]))))
        self.assertEqual({int(row['id']) for row in records}, {self.leads[3].pk, self.leads[4].pk})
        self.assertEqual(self.client.get('/api/ceo/leads/', {'branch_metric': 'invalid'}).status_code, 400)
        self.client.force_authenticate(self.ps)
        self.assertEqual(self.client.get('/api/ceo/branch-sales/').status_code, 403)

    def test_old_calls_do_not_appear_as_last_call_in_selected_dates(self):
        CallLog.objects.filter(pk=self.call.pk).update(created_at=timezone.now()-timedelta(days=2))
        row = self.get('branch-sales', branch='kochi').data['results'][0]
        self.assertIsNone(row['last_call'])
        self.assertIsNone(row['last_call_lead_id'])
