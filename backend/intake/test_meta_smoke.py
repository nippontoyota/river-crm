import io
import json
import logging
import os
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs

from django.test import override_settings

import meta_test_lead


class MetaSmokeTests(TestCase):
    @override_settings(INTAKE_SECRETS={'main-meta': {'access_token': 'secret-not-logged'}}, META_GRAPH_VERSION='v99.0')
    def test_creates_labelled_meta_test_without_writing_crm_or_logging_token(self):
        self.check_creation('')
        self.check_creation('777')

    def check_creation(self, replace_id):
        self.addCleanup(logging.disable, logging.root.manager.disable)
        form = SimpleNamespace(connection=SimpleNamespace(secret_ref='main-meta'), mappings=MagicMock())
        form.mappings.order_by.return_value.first.return_value = SimpleNamespace(
            rules={'required': ['name', 'phone', 'email', 'city']})
        payloads = [
            {'page': {'id': meta_test_lead.PAGE_ID}, 'questions': [
                {'key': key} for key in ['full_name', 'phone_number', 'email', 'city']]},
            {'data': [{'id': replace_id}] if replace_id else []},
            *([{'success': True}] if replace_id else []), {'id': '1234567890'},
        ]
        requests = []

        def respond(request, **kwargs):
            requests.append(request)
            response = MagicMock()
            response.__enter__.return_value.read.return_value = json.dumps(payloads[len(requests) - 1]).encode()
            return response

        with patch.dict(os.environ, {'REPLACE_META_TEST_ID': replace_id}), \
                patch('intake.models.Submission.objects.filter') as receipts, \
                patch('django.db.connection.vendor', 'postgresql'), patch('django.db.transaction.atomic'), \
                patch('django.db.connection.cursor') as cursor, \
                patch('intake.models.IntakeForm.objects.select_related') as forms, \
                patch('leads.models.Lead.objects.filter') as leads, \
                patch('intake.mapping.SystemConfig.objects.filter') as configs, \
                patch('meta_test_lead.build_opener') as opener, redirect_stdout(io.StringIO()) as output:
            receipts.return_value.exists.return_value = True
            forms.return_value.get.return_value = form
            leads.return_value.exists.return_value = False
            configs.return_value.values_list.return_value.first.return_value = {}
            opener.return_value.open.side_effect = respond
            meta_test_lead.main()
            cursor.return_value.__enter__.return_value.execute.assert_called_once_with('SET TRANSACTION READ ONLY')
            deletes = [request for request in requests if request.get_method() == 'DELETE']
            self.assertEqual(len(deletes), int(bool(replace_id)))
            if replace_id:
                self.assertTrue(deletes[0].full_url.endswith('/777?'))
                receipts.assert_called_once_with(external_id=replace_id, form=form,
                                                 fetched_at__isnull=False, answers_expired=False)
            self.assertEqual(requests[-1].get_method(), 'POST')
            self.assertTrue(requests[-1].full_url.endswith('/test_leads'))
            fields = json.loads(parse_qs(requests[-1].data.decode())['field_data'][0])
            values = {field['name']: field['values'][0] for field in fields}
            self.assertTrue(values['full_name'].startswith(meta_test_lead.PREFIX))
            self.assertEqual(values['phone_number'], '0000000000')
            self.assertNotIn('secret-not-logged', output.getvalue())
            self.assertIn('PASS created Meta test lead_id=1234567890', output.getvalue())
