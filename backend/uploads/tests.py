from django.test import TestCase
from rest_framework.test import APIClient
from unittest.mock import patch

from accounts.models import User
from leads.models import Lead
from .models import UploadBatch, UploadRow
from .serializers import UploadBatchSerializer
from .tasks import parse_upload_batch


class UploadDuplicateTests(TestCase):
    def test_skipping_a_duplicate_unblocks_import(self):
        admin = User.objects.create_user(email="manager@example.com", password="password-12345", role=User.Role.ADMIN)
        lead = Lead.objects.create(name="Existing", phone="7000000000")
        batch = UploadBatch.objects.create(filename="leads.csv", storage_path="imports/test.csv", uploaded_by=admin, status=UploadBatch.Status.READY, total_rows=1, parsed_ok=1, duplicates_found=1)
        row = UploadRow.objects.create(batch=batch, row_number=2, normalized_phone=lead.phone, duplicate_of=lead, resolution=UploadRow.Resolution.PENDING, data={"name": "Duplicate"})
        client = APIClient()
        client.force_authenticate(admin)

        response = client.post(f"/api/uploads/{batch.id}/resolve-duplicates/", {"rows": [{"id": row.id, "resolution": "SKIP"}]}, format="json")

        self.assertEqual(response.status_code, 200)
        row.refresh_from_db()
        batch.refresh_from_db()
        self.assertEqual(row.resolution, UploadRow.Resolution.SKIP)
        self.assertEqual(batch.duplicates_found, 0)

    def test_parser_marks_existing_phones_with_one_bulk_lookup(self):
        admin = User.objects.create_user(email="manager@example.com", password="password-12345", role=User.Role.ADMIN)
        Lead.objects.create(name="Existing", phone="7000000000")
        batch = UploadBatch.objects.create(filename="leads.csv", storage_path="imports/test.csv", uploaded_by=admin)
        content = b"name,phone,source\nExisting again,7000000000,website\nNew lead,7000000001,meta\n"

        with patch("uploads.tasks.download_bytes", return_value=content):
            parse_upload_batch.run(batch.id)

        batch.refresh_from_db()
        rows = list(batch.rows.order_by("row_number"))
        self.assertEqual(batch.status, UploadBatch.Status.READY)
        self.assertEqual(batch.duplicates_found, 0)
        self.assertEqual(batch.skipped, 1)
        self.assertEqual([row.resolution for row in rows], [UploadRow.Resolution.SKIP, UploadRow.Resolution.IMPORT])
        self.assertEqual(rows[0].data["_duplicate_type"], "CRM")
        summary = UploadBatchSerializer(batch).data
        self.assertEqual(summary["removed_duplicates"], 1)
        self.assertEqual(summary["crm_duplicates_found"], 1)
        self.assertEqual(summary["file_duplicates_found"], 0)

    def test_parser_auto_skips_duplicate_phones_inside_upload(self):
        admin = User.objects.create_user(email="manager@example.com", password="password-12345", role=User.Role.ADMIN)
        batch = UploadBatch.objects.create(filename="leads.csv", storage_path="imports/test.csv", uploaded_by=admin)
        content = b"name,phone,source\nFirst lead,7000000000,website\nRepeated lead,7000000000,meta\nNew lead,7000000001,meta\n"

        with patch("uploads.tasks.download_bytes", return_value=content):
            parse_upload_batch.run(batch.id)

        batch.refresh_from_db()
        rows = list(batch.rows.order_by("row_number"))
        self.assertEqual(batch.status, UploadBatch.Status.READY)
        self.assertEqual(batch.parsed_ok, 2)
        self.assertEqual(batch.skipped, 1)
        self.assertEqual([row.resolution for row in rows], [UploadRow.Resolution.IMPORT, UploadRow.Resolution.SKIP, UploadRow.Resolution.IMPORT])
        self.assertEqual(rows[1].data["_duplicate_type"], "FILE")
        self.assertIn("Row 2", rows[1].data["_duplicate_label"])
        summary = UploadBatchSerializer(batch).data
        self.assertEqual(summary["removed_duplicates"], 1)
        self.assertEqual(summary["crm_duplicates_found"], 0)
        self.assertEqual(summary["file_duplicates_found"], 1)
