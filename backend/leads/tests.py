from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from datetime import datetime, timedelta, timezone as datetime_timezone
from unittest.mock import patch

from accounts.models import User
from .models import CallLog, FollowUp, Lead, LeadAudit, LeadQualification, SystemConfig


class LeadAccessTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(email="manager@example.com", password="password-12345", role=User.Role.ADMIN)
        self.first_so = User.objects.create_user(email="first@example.com", password="password-12345", role=User.Role.CRE)
        self.second_so = User.objects.create_user(email="second@example.com", password="password-12345", role=User.Role.CRE)
        self.ps_so = User.objects.create_user(email="ps@example.com", password="password-12345", role=User.Role.SALES_OFFICER)
        self.receptionist = User.objects.create_user(email="frontdesk@example.com", password="password-12345", role=User.Role.RECEPTIONIST)
        self.ps_so.location = "Kochi"
        self.ps_so.save(update_fields=["location"])
        self.first_lead = Lead.objects.create(name="Aarav", phone="7305198421", assigned_so=self.first_so)
        self.second_lead = Lead.objects.create(name="Mehak", phone="9797210468", assigned_so=self.second_so)
        self.client = APIClient()

    def test_sales_officer_only_sees_assigned_leads(self):
        self.client.force_authenticate(self.first_so)
        response = self.client.get("/api/leads/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], self.first_lead.id)

    def test_lead_list_and_dashboard_query_budgets(self):
        self.client.force_authenticate(self.first_so)

        with self.assertNumQueries(2):
            leads = self.client.get("/api/leads/")
        with self.assertNumQueries(2):
            dashboard = self.client.get("/api/leads/my-dashboard/?section=fresh")

        self.assertEqual(leads.status_code, 200)
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn("Server-Timing", dashboard)

    def test_admin_auto_assigns_unowned_leads(self):
        unowned = Lead.objects.create(name="Danish", phone="7006682391")
        self.client.force_authenticate(self.admin)
        response = self.client.post("/api/leads/auto-assign/", {"lead_ids": [unowned.id]}, format="json")
        self.assertEqual(response.status_code, 200)
        unowned.refresh_from_db()
        self.assertEqual(unowned.assigned_so.role, User.Role.CRE)

    def test_admin_bulk_assigns_matching_filters(self):
        meta = Lead.objects.create(name="Meta lead", phone="7006682394", source=Lead.Source.META)
        google = Lead.objects.create(name="Google lead", phone="7006682395", source=Lead.Source.OTHER, source_label="Google")
        self.client.force_authenticate(self.admin)
        response = self.client.post("/api/leads/bulk-assign/", {"sales_officer_id": self.first_so.id, "filters": {"source": Lead.Source.META}}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["assigned"], 1)
        meta.refresh_from_db()
        google.refresh_from_db()
        self.assertEqual(meta.assigned_so, self.first_so)
        self.assertIsNone(google.assigned_so)

        response = self.client.post("/api/leads/bulk-assign/", {"sales_officer_id": self.second_so.id, "filters": {"source_label": "Google"}}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["assigned"], 1)
        google.refresh_from_db()
        self.assertEqual(google.assigned_so, self.second_so)

    def test_admin_distributes_filtered_bucket_across_selected_cres(self):
        meta_leads = [Lead.objects.create(name=f"Meta {index}", phone=f"70066824{index:02d}", source=Lead.Source.META) for index in range(5)]
        google = Lead.objects.create(name="Google bucket", phone="7006682500", source=Lead.Source.OTHER, source_label="Google")
        assigned_meta = Lead.objects.create(name="Assigned Meta", phone="7006682501", source=Lead.Source.META, assigned_so=self.first_so)
        self.client.force_authenticate(self.admin)

        response = self.client.post("/api/leads/bulk-distribute/", {"sales_officer_ids": [self.first_so.id, self.second_so.id], "filters": {"source": Lead.Source.META}}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["assigned"], 5)
        self.assertEqual(response.data["distribution"][0]["assigned"], 3)
        self.assertEqual(response.data["distribution"][1]["assigned"], 2)
        self.assertEqual(Lead.objects.filter(id__in=[lead.id for lead in meta_leads], assigned_so=self.first_so).count(), 3)
        self.assertEqual(Lead.objects.filter(id__in=[lead.id for lead in meta_leads], assigned_so=self.second_so).count(), 2)
        google.refresh_from_db()
        assigned_meta.refresh_from_db()
        self.assertIsNone(google.assigned_so)
        self.assertEqual(assigned_meta.assigned_so, self.first_so)
        self.assertEqual(LeadAudit.objects.filter(lead__in=meta_leads, event="bucket_assigned_cre").count(), 5)

    def test_admin_distribute_requires_active_cre_selection(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post("/api/leads/bulk-distribute/", {"sales_officer_ids": [], "filters": {}}, format="json")
        self.assertEqual(response.status_code, 400)

        response = self.client.post("/api/leads/bulk-distribute/", {"sales_officer_ids": [self.ps_so.id], "filters": {}}, format="json")
        self.assertEqual(response.status_code, 400)

        self.second_so.is_active = False
        self.second_so.save(update_fields=["is_active"])
        response = self.client.post("/api/leads/bulk-distribute/", {"sales_officer_ids": [self.second_so.id], "filters": {}}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_admin_can_add_an_unassigned_lead(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post("/api/leads/", {"name": "Manual lead", "phone": "7006682392", "source": Lead.Source.WEBSITE, "model_interest": "R8 Lite", "city": "Srinagar"}, format="json")
        self.assertEqual(response.status_code, 201)
        lead = Lead.objects.get(pk=response.data["id"])
        self.assertIsNone(lead.assigned_so)
        self.assertEqual(lead.status, Lead.Status.FRESH)

    def test_admin_models_limit_new_lead_models(self):
        SystemConfig.objects.create(id=1, lists={"models": ["r7"]})
        self.client.force_authenticate(self.admin)
        response = self.client.post("/api/leads/", {"name": "Invalid model", "phone": "7006682310", "source": Lead.Source.WEBSITE, "model_interest": "R8 Pro"}, format="json")
        self.assertEqual(response.status_code, 400)
        response = self.client.post("/api/leads/", {"name": "Valid model", "phone": "7006682311", "source": Lead.Source.WEBSITE, "model_interest": "r7"}, format="json")
        self.assertEqual(response.status_code, 201)

    def test_admin_color_variants_limit_qualification_variants(self):
        SystemConfig.objects.create(id=1, lists={"colorVariants": ["Red"]})
        self.client.force_authenticate(self.first_so)
        response = self.client.patch(f"/api/leads/{self.first_lead.id}/so-update/", {"call_outcome": "QUALIFIED", "status": Lead.Status.QUALIFIED, "city": "Kochi", "ps_officer_id": self.ps_so.id, "qualification": {"variant": "Blue"}}, format="json")
        self.assertEqual(response.status_code, 400)
        response = self.client.patch(f"/api/leads/{self.first_lead.id}/so-update/", {"call_outcome": "QUALIFIED", "status": Lead.Status.QUALIFIED, "city": "Kochi", "ps_officer_id": self.ps_so.id, "qualification": {"variant": "Red"}}, format="json")
        self.assertEqual(response.status_code, 200)

    def test_admin_cannot_add_a_lead_with_future_enquiry_date(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post("/api/leads/", {"name": "Future lead", "phone": "7006682393", "source": Lead.Source.WEBSITE, "enquiry_date": (timezone.localdate() + timedelta(days=1)).isoformat()}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_admin_can_add_a_lead_for_current_ist_date(self):
        self.client.force_authenticate(self.admin)
        fixed_now = datetime(2026, 8, 28, 4, 7, tzinfo=datetime_timezone.utc)
        with patch("django.utils.timezone.now", return_value=fixed_now):
            response = self.client.post("/api/leads/", {"name": "IST Today", "phone": "7006682396", "source": Lead.Source.WEBSITE, "enquiry_date": "2026-08-28"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)

    def test_admin_cannot_assign_a_lead_twice(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(f"/api/leads/{self.first_lead.id}/assign/", {"sales_officer_id": self.second_so.id}, format="json")
        self.assertEqual(response.status_code, 409)
        self.first_lead.refresh_from_db()
        self.assertEqual(self.first_lead.assigned_so, self.first_so)

    def test_sales_officer_cannot_move_a_lead_backward(self):
        self.first_lead.status = Lead.Status.QUALIFIED
        self.first_lead.save()
        self.client.force_authenticate(self.first_so)
        response = self.client.post(f"/api/leads/{self.first_lead.id}/log-call/", {"status": Lead.Status.RNR}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_sales_officer_cannot_skip_ahead_to_won(self):
        self.client.force_authenticate(self.first_so)
        response = self.client.post(f"/api/leads/{self.first_lead.id}/log-call/", {"status": Lead.Status.WON}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_follow_up_requires_a_future_callback_or_walkin(self):
        self.client.force_authenticate(self.first_so)
        future = timezone.now() + timedelta(days=1)
        response = self.client.post(f"/api/leads/{self.first_lead.id}/log-call/", {"status": Lead.Status.CALLBACK, "follow_up_at": future.isoformat()}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(FollowUp.objects.filter(lead=self.first_lead, scheduled_for=future).exists())

        self.first_lead.refresh_from_db()
        response = self.client.post(f"/api/leads/{self.first_lead.id}/log-call/", {"status": Lead.Status.QUALIFIED}, format="json")
        self.assertEqual(response.status_code, 200)
        response = self.client.post(f"/api/leads/{self.first_lead.id}/log-call/", {"status": Lead.Status.LOST, "follow_up_at": future.isoformat()}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(FollowUp.objects.filter(lead=self.first_lead, resolved_at__isnull=True).exists())

    def test_repeated_call_log_creates_one_log_and_follow_up(self):
        self.client.force_authenticate(self.first_so)
        future = timezone.now() + timedelta(days=1)
        payload = {"status": Lead.Status.CALLBACK, "follow_up_at": future.isoformat()}

        self.assertEqual(self.client.post(f"/api/leads/{self.first_lead.id}/log-call/", payload, format="json").status_code, 200)
        self.assertEqual(self.client.post(f"/api/leads/{self.first_lead.id}/log-call/", payload, format="json").status_code, 400)
        self.assertEqual(CallLog.objects.filter(lead=self.first_lead).count(), 1)
        self.assertEqual(FollowUp.objects.filter(lead=self.first_lead, resolved_at__isnull=True).count(), 1)

    def test_sales_dashboard_returns_personal_status_summary(self):
        self.first_lead.status = Lead.Status.QUALIFIED
        self.first_lead.category = Lead.Category.HOT
        self.first_lead.save(update_fields=["status", "category"])
        self.client.force_authenticate(self.first_so)
        response = self.client.get("/api/leads/my-dashboard/?section=qualified")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["summary"]["qualified"], 1)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(set(response.data["results"][0]), {"id", "status", "name", "phone", "source", "flagged_to_manager"})
        self.assertEqual(response.data["results"][0]["status"], Lead.Status.QUALIFIED)

    def test_cre_all_dashboard_includes_handed_off_own_leads(self):
        self.first_lead.status = Lead.Status.QUALIFIED
        self.first_lead.assigned_ps = self.ps_so
        self.first_lead.save(update_fields=["status", "assigned_ps"])
        self.client.force_authenticate(self.first_so)

        response = self.client.get("/api/leads/my-dashboard/?section=all")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["summary"]["total"], 1)
        self.assertEqual(response.data["summary"]["qualified"], 1)
        self.assertEqual([lead["id"] for lead in response.data["results"]], [self.first_lead.id])

    def test_cre_can_update_handed_off_lead_after_ps_call(self):
        self.first_lead.status = Lead.Status.PENDING
        self.first_lead.assigned_ps = self.ps_so
        self.first_lead.save(update_fields=["status", "assigned_ps"])
        CallLog.objects.create(lead=self.first_lead, so=self.ps_so, status=Lead.Status.PENDING, outcome="Need Test Drive", remarks="PS scheduled a test drive.")
        self.client.force_authenticate(self.first_so)
        future = timezone.now() + timedelta(days=1)

        response = self.client.patch(f"/api/leads/{self.first_lead.id}/so-update/", {"call_outcome": "PENDING", "status": Lead.Status.PENDING, "remarks": "CRE helped the customer.", "follow_up_at": future.isoformat()}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([call["outcome"] for call in response.data["call_history"]], ["PENDING", "Need Test Drive"])
        self.assertTrue(FollowUp.objects.filter(lead=self.first_lead, so=self.first_so, scheduled_for=future, resolved_at__isnull=True).exists())

    def test_fresh_dashboard_subfilters_return_matching_rows(self):
        called = Lead.objects.create(name="Called", phone="7305198422", assigned_so=self.first_so, status=Lead.Status.RNR)
        scheduled = Lead.objects.create(name="Scheduled", phone="7305198423", assigned_so=self.first_so, status=Lead.Status.PENDING)
        qualified = Lead.objects.create(name="Qualified", phone="7305198424", assigned_so=self.first_so, status=Lead.Status.QUALIFIED)
        FollowUp.objects.create(lead=scheduled, so=self.first_so, scheduled_for=timezone.now() + timedelta(days=1))
        self.client.force_authenticate(self.first_so)

        response = self.client.get("/api/leads/my-dashboard/?section=fresh&subfilter=untouched")
        self.assertEqual([lead["id"] for lead in response.data["results"]], [self.first_lead.id])

        response = self.client.get("/api/leads/my-dashboard/?section=fresh&subfilter=called")
        self.assertEqual([lead["id"] for lead in response.data["results"]], [called.id])
        self.assertNotIn(qualified.id, [lead["id"] for lead in response.data["results"]])

        response = self.client.get("/api/leads/my-dashboard/?section=fresh&subfilter=scheduled")
        self.assertEqual([lead["id"] for lead in response.data["results"]], [scheduled.id])

    def test_sales_officer_can_save_qualification_from_qualified_outcome(self):
        self.client.force_authenticate(self.first_so)
        response = self.client.patch(f"/api/leads/{self.first_lead.id}/so-update/", {"category": Lead.Category.HOT, "call_outcome": "QUALIFIED", "city": "Kochi", "ps_officer_id": self.ps_so.id, "remarks": "Customer is qualified.", "qualification": {"variant": "R8 Pro", "buying_timeline": "1-2 months", "finance_type": "Bank finance", "trade_in": True, "test_drive": "Requested"}}, format="json")
        self.assertEqual(response.status_code, 200)
        self.first_lead.refresh_from_db()
        self.assertEqual(self.first_lead.status, Lead.Status.QUALIFIED)
        self.assertEqual(self.first_lead.assigned_ps, self.ps_so)
        self.assertEqual(self.first_lead.category, Lead.Category.HOT)
        self.assertEqual(CallLog.objects.get(lead=self.first_lead).outcome, "QUALIFIED")
        self.assertFalse(FollowUp.objects.filter(lead=self.first_lead, resolved_at__isnull=True).exists())
        self.assertEqual(LeadQualification.objects.get(lead=self.first_lead).variant, "R8 Pro")

        duplicate = self.client.patch(f"/api/leads/{self.first_lead.id}/so-update/", {"call_outcome": "QUALIFIED", "status": Lead.Status.QUALIFIED, "city": "Kochi", "ps_officer_id": self.ps_so.id, "qualification": {"variant": "R8 Pro"}}, format="json")
        self.assertEqual(duplicate.status_code, 400)
        self.assertEqual(CallLog.objects.filter(lead=self.first_lead).count(), 1)

    def test_cre_sees_ps_options_for_customer_location(self):
        other_ps = User.objects.create_user(email="north@example.com", password="password-12345", role=User.Role.SALES_OFFICER, location="Kannur")
        self.client.force_authenticate(self.first_so)

        response = self.client.get("/api/auth/sales-officers/?location=Kochi")

        self.assertEqual(response.status_code, 200)
        ids = [officer["id"] for officer in response.data["results"]]
        self.assertIn(self.ps_so.id, ids)
        self.assertNotIn(other_ps.id, ids)

    def test_system_config_returns_only_admin_branches(self):
        User.objects.create_user(email="north@example.com", password="password-12345", role=User.Role.SALES_OFFICER, location="Kannur")
        SystemConfig.objects.create(id=1, lists={"branches": ["Kochi"]})
        self.client.force_authenticate(self.first_so)

        response = self.client.get("/api/system-config/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["lists"]["branches"], ["Kochi"])

    def test_cre_must_choose_matching_ps_for_qualified_lead(self):
        other_ps = User.objects.create_user(email="north@example.com", password="password-12345", role=User.Role.SALES_OFFICER, location="Kannur")
        self.client.force_authenticate(self.first_so)

        missing = self.client.patch(f"/api/leads/{self.first_lead.id}/so-update/", {"call_outcome": "QUALIFIED", "city": "Kochi"}, format="json")
        mismatch = self.client.patch(f"/api/leads/{self.first_lead.id}/so-update/", {"call_outcome": "QUALIFIED", "city": "Kochi", "ps_officer_id": other_ps.id}, format="json")

        self.assertEqual(missing.status_code, 400)
        self.assertEqual(mismatch.status_code, 400)

    def test_call_outcome_only_allows_matching_lead_statuses(self):
        self.client.force_authenticate(self.first_so)
        response = self.client.patch(f"/api/leads/{self.first_lead.id}/so-update/", {"call_outcome": "CONNECTED", "status": Lead.Status.RNR}, format="json")
        self.assertEqual(response.status_code, 400)

        future = timezone.now() + timedelta(days=1)
        response = self.client.patch(f"/api/leads/{self.first_lead.id}/so-update/", {"call_outcome": "PENDING", "status": Lead.Status.QUALIFIED, "follow_up_at": future.isoformat()}, format="json")
        self.assertEqual(response.status_code, 400)

        response = self.client.patch(f"/api/leads/{self.first_lead.id}/so-update/", {"call_outcome": "PENDING", "status": Lead.Status.PENDING, "follow_up_at": future.isoformat()}, format="json")
        self.assertEqual(response.status_code, 200)
        self.first_lead.refresh_from_db()
        self.assertEqual(self.first_lead.status, Lead.Status.PENDING)

    def test_pending_call_outcome_moves_lead_to_pending(self):
        self.client.force_authenticate(self.first_so)
        future = timezone.now() + timedelta(days=1)
        response = self.client.patch(f"/api/leads/{self.first_lead.id}/so-update/", {"call_outcome": "PENDING", "follow_up_at": future.isoformat()}, format="json")
        self.assertEqual(response.status_code, 200)
        self.first_lead.refresh_from_db()
        self.assertEqual(self.first_lead.status, Lead.Status.PENDING)
        self.assertTrue(FollowUp.objects.filter(lead=self.first_lead, resolved_at__isnull=True).exists())

    def test_cre_pending_reasons_route_to_todays_followups_or_pending_sections(self):
        rnr = Lead.objects.create(name="RNR Lead", phone="7305198424", assigned_so=self.first_so)
        switched_off = Lead.objects.create(name="Switch Lead", phone="7305198425", assigned_so=self.first_so)
        generic = Lead.objects.create(name="Generic Pending", phone="7305198426", assigned_so=self.first_so)
        tomorrow_callback = Lead.objects.create(name="Tomorrow Callback", phone="7305198428", assigned_so=self.first_so)
        overdue_callback = Lead.objects.create(name="Overdue Callback", phone="7305198429", assigned_so=self.first_so, status=Lead.Status.PENDING)
        fixed_now = timezone.localtime(timezone.now()).replace(hour=10, minute=0, second=0, microsecond=0)
        same_day_eod = fixed_now.replace(hour=23, minute=59)
        tomorrow = fixed_now + timedelta(days=1)
        yesterday = fixed_now - timedelta(days=1)
        FollowUp.objects.create(lead=overdue_callback, so=self.first_so, scheduled_for=yesterday)
        CallLog.objects.create(lead=overdue_callback, so=self.first_so, status=Lead.Status.PENDING, outcome="Call Me Back")
        self.client.force_authenticate(self.first_so)

        with patch("django.utils.timezone.now", return_value=fixed_now):
            callback = self.client.patch(f"/api/leads/{self.first_lead.id}/so-update/", {"call_outcome": "Call Me Back", "status": Lead.Status.PENDING, "remarks": "Pending reason: Call me back", "follow_up_at": same_day_eod.isoformat()}, format="json")
            rnr_response = self.client.patch(f"/api/leads/{rnr.id}/so-update/", {"call_outcome": "RNR", "status": Lead.Status.PENDING, "remarks": "Pending reason: RNR", "follow_up_at": same_day_eod.isoformat()}, format="json")
            switched_response = self.client.patch(f"/api/leads/{switched_off.id}/so-update/", {"call_outcome": "Switch Off", "status": Lead.Status.PENDING, "remarks": "Pending reason: Switched Off", "follow_up_at": same_day_eod.isoformat()}, format="json")
            generic_response = self.client.patch(f"/api/leads/{generic.id}/so-update/", {"call_outcome": "PENDING", "status": Lead.Status.PENDING, "remarks": "Pending reason: Busy", "follow_up_at": same_day_eod.isoformat()}, format="json")
            tomorrow_response = self.client.patch(f"/api/leads/{tomorrow_callback.id}/so-update/", {"call_outcome": "Call Me Back", "status": Lead.Status.PENDING, "remarks": "Pending reason: Call me back tomorrow", "follow_up_at": tomorrow.isoformat()}, format="json")

        self.assertEqual(callback.status_code, 200)
        self.assertEqual(rnr_response.status_code, 200)
        self.assertEqual(switched_response.status_code, 200)
        self.assertEqual(generic_response.status_code, 200)
        self.assertEqual(tomorrow_response.status_code, 200)
        self.first_lead.refresh_from_db()
        rnr.refresh_from_db()
        switched_off.refresh_from_db()
        generic.refresh_from_db()
        tomorrow_callback.refresh_from_db()
        self.assertEqual(self.first_lead.status, Lead.Status.PENDING)
        self.assertEqual(rnr.status, Lead.Status.PENDING)
        self.assertEqual(switched_off.status, Lead.Status.PENDING)
        self.assertEqual(generic.status, Lead.Status.PENDING)
        self.assertEqual(tomorrow_callback.status, Lead.Status.PENDING)

        follow_ups = self.client.get("/api/leads/my-dashboard/?section=followups")
        pending = self.client.get("/api/leads/my-dashboard/?section=pending")

        self.assertEqual(follow_ups.data["summary"]["followups"], 2)
        self.assertEqual(follow_ups.data["summary"]["pending"], 4)
        self.assertEqual({lead["id"] for lead in follow_ups.data["results"]}, {self.first_lead.id, overdue_callback.id})
        self.assertEqual({lead["id"] for lead in pending.data["results"]}, {rnr.id, switched_off.id, generic.id, tomorrow_callback.id})

    def test_ps_followups_include_due_open_items_only(self):
        yesterday = Lead.objects.create(name="Yesterday PS", phone="7305198430", assigned_ps=self.ps_so, status=Lead.Status.PENDING)
        today = Lead.objects.create(name="Today PS", phone="7305198431", assigned_ps=self.ps_so, status=Lead.Status.PENDING)
        tomorrow = Lead.objects.create(name="Tomorrow PS", phone="7305198432", assigned_ps=self.ps_so, status=Lead.Status.PENDING)
        resolved = Lead.objects.create(name="Resolved PS", phone="7305198433", assigned_ps=self.ps_so, status=Lead.Status.PENDING)
        now = timezone.now()
        FollowUp.objects.create(lead=yesterday, so=self.ps_so, scheduled_for=now - timedelta(days=1))
        FollowUp.objects.create(lead=today, so=self.ps_so, scheduled_for=now)
        FollowUp.objects.create(lead=tomorrow, so=self.ps_so, scheduled_for=now + timedelta(days=1))
        FollowUp.objects.create(lead=resolved, so=self.ps_so, scheduled_for=now, resolved_at=now)
        self.client.force_authenticate(self.ps_so)

        response = self.client.get("/api/leads/my-dashboard/?section=followups")
        missed = self.client.get("/api/leads/my-dashboard/?section=missed")

        self.assertEqual(response.data["summary"]["followups"], 2)
        self.assertEqual(response.data["summary"]["missed"], 1)
        self.assertEqual({lead["id"] for lead in response.data["results"]}, {yesterday.id, today.id})
        self.assertEqual({lead["id"] for lead in missed.data["results"]}, {yesterday.id})

    def test_ps_dashboard_filters_all_fresh_booked_retailed_and_lost(self):
        fresh = Lead.objects.create(name="Fresh PS", phone="7305198434", assigned_ps=self.ps_so, status=Lead.Status.QUALIFIED)
        called = Lead.objects.create(name="Called PS", phone="7305198438", assigned_ps=self.ps_so, status=Lead.Status.QUALIFIED)
        booked = Lead.objects.create(name="Booked PS", phone="7305198435", assigned_ps=self.ps_so, status=Lead.Status.WALKIN)
        retailed = Lead.objects.create(name="Retailed PS", phone="7305198436", assigned_ps=self.ps_so, status=Lead.Status.WON)
        lost = Lead.objects.create(name="Lost PS", phone="7305198437", assigned_ps=self.ps_so, status=Lead.Status.LOST)
        CallLog.objects.create(lead=called, so=self.ps_so, status=Lead.Status.QUALIFIED)
        self.client.force_authenticate(self.ps_so)

        sections = {
            "all": {fresh.id, called.id, booked.id, retailed.id, lost.id},
            "fresh": {fresh.id},
            "walkin": {booked.id},
            "won": {retailed.id},
            "lost": {lost.id},
        }
        for section, expected_ids in sections.items():
            response = self.client.get(f"/api/leads/my-dashboard/?section={section}")
            self.assertEqual({lead["id"] for lead in response.data["results"]}, expected_ids)

    def test_so_update_accepts_same_day_future_follow_up_and_rejects_past(self):
        past_lead = Lead.objects.create(name="Past Follow Up", phone="7305198427", assigned_so=self.first_so)
        fixed_now = timezone.localtime(timezone.now()).replace(hour=10, minute=0, second=0, microsecond=0)
        same_day_eod = fixed_now.replace(hour=23, minute=59)
        same_day_past = fixed_now.replace(hour=9, minute=0)
        self.client.force_authenticate(self.first_so)

        with patch("django.utils.timezone.now", return_value=fixed_now):
            accepted = self.client.patch(f"/api/leads/{self.first_lead.id}/so-update/", {"call_outcome": "Call Me Back", "status": Lead.Status.PENDING, "follow_up_at": same_day_eod.isoformat()}, format="json")
            rejected = self.client.patch(f"/api/leads/{past_lead.id}/so-update/", {"call_outcome": "RNR", "status": Lead.Status.PENDING, "follow_up_at": same_day_past.isoformat()}, format="json")

        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(rejected.status_code, 400)

    def test_assigned_ps_can_schedule_next_day_follow_up(self):
        self.first_lead.status = Lead.Status.QUALIFIED
        self.first_lead.assigned_ps = self.ps_so
        self.first_lead.save(update_fields=["status", "assigned_ps"])
        self.client.force_authenticate(self.ps_so)
        future = timezone.now() + timedelta(days=1)

        invalid_callback = self.client.patch(f"/api/leads/{self.first_lead.id}/so-update/", {
            "call_status": "Not Connected",
            "call_outcome": "Call Me Back",
            "status": Lead.Status.CALLBACK,
            "remarks": "Customer cannot ask for a callback on an unconnected call.",
            "follow_up_at": future.isoformat(),
        }, format="json")

        response = self.client.patch(f"/api/leads/{self.first_lead.id}/so-update/", {
            "call_status": "Connected",
            "call_outcome": "Need Test Drive",
            "status": Lead.Status.PENDING,
            "sales_outcome": Lead.SalesOutcome.PENDING,
            "remarks": "Customer asked for a test drive tomorrow.",
            "follow_up_at": future.isoformat(),
        }, format="json")

        self.assertEqual(invalid_callback.status_code, 400)
        self.assertEqual(response.status_code, 200)
        self.first_lead.refresh_from_db()
        self.assertEqual(self.first_lead.status, Lead.Status.PENDING)
        self.assertTrue(FollowUp.objects.filter(lead=self.first_lead, so=self.ps_so, scheduled_for=future, resolved_at__isnull=True).exists())
        self.assertEqual(CallLog.objects.get(lead=self.first_lead).outcome, "Need Test Drive")

    def test_full_admin_to_cre_to_ps_lead_journey_with_five_followups(self):
        self.client.force_authenticate(self.admin)
        create = self.client.post("/api/leads/", {
            "name": "Nisha Random",
            "phone": "8123456789",
            "email": "nisha.random@example.com",
            "source": Lead.Source.WEBSITE,
            "campaign": "Random August Test",
            "model_interest": "River Indie",
            "city": "Kochi",
            "category": Lead.Category.WARM,
        }, format="json")
        self.assertEqual(create.status_code, 201)
        lead_id = create.data["id"]

        assign = self.client.post(f"/api/leads/{lead_id}/assign/", {"sales_officer_id": self.first_so.id}, format="json")
        self.assertEqual(assign.status_code, 200)

        self.client.force_authenticate(self.first_so)
        qualify = self.client.patch(f"/api/leads/{lead_id}/so-update/", {
            "call_outcome": "QUALIFIED",
            "status": Lead.Status.QUALIFIED,
            "category": Lead.Category.HOT,
            "city": "Kochi",
            "branch": "Kochi",
            "ps_officer_id": self.ps_so.id,
            "remarks": "Random CRE remark: customer wants a proper PS call.",
            "qualification": {
                "variant": "Matte Blue",
                "buying_timeline": "1-2 months",
                "finance_type": "Outright",
                "trade_in": False,
                "test_drive": "Showroom visit",
                "notes": "Random qualification note from CRE.",
            },
        }, format="json")
        self.assertEqual(qualify.status_code, 200)

        self.client.force_authenticate(self.ps_so)
        follow_up_at = timezone.now() + timedelta(days=1)
        ps_calls = [
            ("Not Connected", "RNR", Lead.Status.RNR, "Random PS remark 1: no response on first attempt."),
            ("Not Connected", "Switch Off", Lead.Status.SWITCHED_OFF, "Random PS remark 2: phone switched off."),
            ("Not Connected", "Call Forwarding", Lead.Status.PENDING, "Random PS remark 3: call forwarding active."),
            ("Not Connected", "Line Busy", Lead.Status.PENDING, "Random PS remark 4: line busy, retry tomorrow."),
            ("Connected", "Need Test Drive", Lead.Status.PENDING, "Random PS remark 5: customer asked for test drive."),
        ]
        for call_status, outcome, status_value, remark in ps_calls:
            response = self.client.patch(f"/api/leads/{lead_id}/so-update/", {
                "call_status": call_status,
                "call_outcome": outcome,
                "status": status_value,
                "sales_outcome": Lead.SalesOutcome.PENDING,
                "remarks": remark,
                "follow_up_at": follow_up_at.isoformat(),
            }, format="json")
            self.assertEqual(response.status_code, 200, response.data)

        close = self.client.patch(f"/api/leads/{lead_id}/so-update/", {
            "call_status": "Connected",
            "call_outcome": "Retail Done",
            "status": Lead.Status.WON,
            "sales_outcome": Lead.SalesOutcome.RETAILED,
            "remarks": "Random PS closing remark: customer retailed after five follow-ups.",
        }, format="json")
        self.assertEqual(close.status_code, 200, close.data)

        lead = Lead.objects.get(pk=lead_id)
        self.assertEqual(lead.assigned_so, self.first_so)
        self.assertEqual(lead.assigned_ps, self.ps_so)
        self.assertEqual(lead.status, Lead.Status.WON)
        self.assertEqual(lead.sales_outcome, Lead.SalesOutcome.RETAILED)
        self.assertEqual(CallLog.objects.filter(lead=lead).count(), 7)
        self.assertEqual(FollowUp.objects.filter(lead=lead).count(), 5)
        self.assertFalse(FollowUp.objects.filter(lead=lead, resolved_at__isnull=True).exists())
        self.assertEqual(LeadQualification.objects.get(lead=lead).variant, "Matte Blue")

    def test_receptionist_walkin_to_ps_retail_journey(self):
        self.client.force_authenticate(self.receptionist)
        create = self.client.post("/api/leads/", {
            "name": "Reception Random",
            "phone": "8234567890",
            "email": "reception.random@example.com",
            "profession": "Business",
            "source": Lead.Source.WALKIN,
            "model_interest": "River Indie",
            "ps_officer_id": self.ps_so.id,
            "qualification_input": {
                "variant": "Sunset Red",
                "buying_timeline": "Immediate",
                "finance_type": "",
                "test_drive": "",
                "notes": "Random receptionist walk-in note.",
            },
        }, format="json")
        self.assertEqual(create.status_code, 201, create.data)
        lead_id = create.data["id"]
        lead = Lead.objects.get(pk=lead_id)
        self.assertEqual(lead.status, Lead.Status.QUALIFIED)
        self.assertIsNone(lead.assigned_so)
        self.assertEqual(lead.assigned_ps, self.ps_so)
        self.assertEqual(LeadQualification.objects.get(lead=lead).variant, "Sunset Red")

        analytics = self.client.get("/api/analytics/receptionist/")
        self.assertEqual(analytics.status_code, 200)
        self.assertEqual(analytics.data["summary"], {"total": 1, "walkin": 1, "digital": 0})
        self.assertEqual(analytics.data["so_breakdown"], [{"name": self.ps_so.email, "count": 1}])

        self.client.force_authenticate(self.ps_so)
        follow_up_at = timezone.now() + timedelta(days=1)
        for call_status, outcome, status_value, remark in [
            ("Not Connected", "RNR", Lead.Status.RNR, "Reception random PS remark 1: RNR."),
            ("Not Connected", "Call Forwarding", Lead.Status.PENDING, "Reception random PS remark 2: call forwarding."),
            ("Not Connected", "Line Busy", Lead.Status.PENDING, "Reception random PS remark 3: line busy."),
            ("Connected", "Need More Details", Lead.Status.PENDING, "Reception random PS remark 4: needs pricing detail."),
            ("Connected", "Booking Done", Lead.Status.WALKIN, "Reception random PS remark 5: booking follow-up done."),
        ]:
            response = self.client.patch(f"/api/leads/{lead_id}/so-update/", {
                "call_status": call_status,
                "call_outcome": outcome,
                "status": status_value,
                "sales_outcome": Lead.SalesOutcome.PENDING,
                "remarks": remark,
                "follow_up_at": follow_up_at.isoformat(),
            }, format="json")
            self.assertEqual(response.status_code, 200, response.data)

        close = self.client.patch(f"/api/leads/{lead_id}/so-update/", {
            "call_status": "Connected",
            "call_outcome": "Retail Done",
            "status": Lead.Status.WON,
            "sales_outcome": Lead.SalesOutcome.RETAILED,
            "remarks": "Reception random PS closing remark: retailed.",
        }, format="json")
        self.assertEqual(close.status_code, 200, close.data)

        lead.refresh_from_db()
        self.assertEqual(lead.status, Lead.Status.WON)
        self.assertEqual(lead.sales_outcome, Lead.SalesOutcome.RETAILED)
        self.assertEqual(CallLog.objects.filter(lead=lead).count(), 6)
        self.assertEqual(FollowUp.objects.filter(lead=lead).count(), 5)
        self.assertFalse(FollowUp.objects.filter(lead=lead, resolved_at__isnull=True).exists())

    def test_direct_qualified_and_lost_outcomes_set_matching_statuses(self):
        self.client.force_authenticate(self.first_so)
        response = self.client.patch(f"/api/leads/{self.first_lead.id}/so-update/", {"call_outcome": "QUALIFIED", "status": Lead.Status.QUALIFIED, "city": "Kochi", "ps_officer_id": self.ps_so.id, "qualification": {"variant": "R8 Pro"}}, format="json")
        self.assertEqual(response.status_code, 200)
        self.first_lead.refresh_from_db()
        self.assertEqual(self.first_lead.status, Lead.Status.QUALIFIED)

        self.client.force_authenticate(self.ps_so)
        response = self.client.patch(f"/api/leads/{self.first_lead.id}/so-update/", {"call_outcome": "LOST", "status": Lead.Status.LOST}, format="json")
        self.assertEqual(response.status_code, 200)
        self.first_lead.refresh_from_db()
        self.assertEqual(self.first_lead.status, Lead.Status.LOST)

    def test_ps_can_manually_mark_not_connected_as_no_response_lost(self):
        self.first_lead.status = Lead.Status.QUALIFIED
        self.first_lead.assigned_ps = self.ps_so
        self.first_lead.save(update_fields=["status", "assigned_ps"])
        self.client.force_authenticate(self.ps_so)

        response = self.client.patch(f"/api/leads/{self.first_lead.id}/so-update/", {"call_status": "Not Connected", "call_outcome": "No Response", "status": Lead.Status.LOST, "sales_outcome": Lead.SalesOutcome.LOST, "remarks": "No response, marking lost."}, format="json")

        self.assertEqual(response.status_code, 200, response.data)
        self.first_lead.refresh_from_db()
        self.assertEqual(self.first_lead.status, Lead.Status.LOST)
        self.assertEqual(self.first_lead.sales_outcome, Lead.SalesOutcome.LOST)
        self.assertEqual(self.first_lead.call_logs.latest("id").outcome, "No Response")
        self.assertFalse(FollowUp.objects.filter(lead=self.first_lead, resolved_at__isnull=True).exists())

    def test_call_outcome_rejects_incompatible_follow_up(self):
        self.client.force_authenticate(self.first_so)
        future = timezone.now() + timedelta(days=1)
        response = self.client.patch(f"/api/leads/{self.first_lead.id}/so-update/", {"call_outcome": "QUALIFIED", "follow_up_at": future.isoformat()}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_follow_up_status_requires_a_date_and_other_statuses_cannot_keep_one(self):
        self.client.force_authenticate(self.first_so)
        response = self.client.patch(f"/api/leads/{self.first_lead.id}/so-update/", {"status": Lead.Status.CALLBACK}, format="json")
        self.assertEqual(response.status_code, 400)

        future = timezone.now() + timedelta(days=1)
        response = self.client.patch(f"/api/leads/{self.first_lead.id}/so-update/", {"status": Lead.Status.QUALIFIED, "follow_up_at": future.isoformat()}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_sales_officer_can_edit_customer_details(self):
        self.client.force_authenticate(self.first_so)
        response = self.client.patch(f"/api/leads/{self.first_lead.id}/so-update/", {"name": "Aarav Updated", "phone": "7305198422", "email": "aarav@example.com", "source": Lead.Source.WEBSITE, "campaign": "Summer Drive", "model_interest": "R8 Pro", "city": "Kochi", "branch": "Central", "enquiry_date": timezone.localdate().isoformat()}, format="json")
        self.assertEqual(response.status_code, 200)
        self.first_lead.refresh_from_db()
        self.assertEqual(self.first_lead.name, "Aarav Updated")
        self.assertEqual(self.first_lead.phone, "7305198422")
        self.assertEqual(self.first_lead.source, Lead.Source.WEBSITE)
        self.assertEqual(self.first_lead.branch, "Central")
        self.client.force_authenticate(self.admin)
        admin_view = self.client.get(f"/api/leads/?assigned_so={self.first_so.id}")
        self.assertEqual(admin_view.status_code, 200)
        self.assertEqual(admin_view.data["results"][0]["name"], "Aarav Updated")
        self.assertEqual(admin_view.data["results"][0]["branch"], "Central")
        self.client.force_authenticate(self.first_so)
        response = self.client.patch(f"/api/leads/{self.first_lead.id}/so-update/", {"enquiry_date": (timezone.localdate() + timedelta(days=1)).isoformat()}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_admin_can_update_any_lead_outcome(self):
        self.client.force_authenticate(self.admin)
        response = self.client.patch(f"/api/leads/{self.first_lead.id}/so-update/", {"status": Lead.Status.WON, "sales_outcome": Lead.SalesOutcome.RETAILED, "remarks": "Sale confirmed."}, format="json")
        self.assertEqual(response.status_code, 200)
        self.first_lead.refresh_from_db()
        self.assertEqual(self.first_lead.status, Lead.Status.WON)
        self.assertEqual(self.first_lead.sales_outcome, Lead.SalesOutcome.RETAILED)

    def test_admin_analytics_counts_calls_made_today(self):
        CallLog.objects.create(lead=self.first_lead, so=self.first_so, status=Lead.Status.RNR)
        yesterday = CallLog.objects.create(lead=self.second_lead, so=self.second_so, status=Lead.Status.RNR)
        CallLog.objects.filter(pk=yesterday.pk).update(created_at=timezone.now() - timedelta(days=1))

        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/analytics/admin/")

        self.assertEqual(response.status_code, 200)
        first_officer = next(item for item in response.data["cre"] if item["id"] == self.first_so.id)
        second_officer = next(item for item in response.data["cre"] if item["id"] == self.second_so.id)
        self.assertEqual(first_officer["calls_today"], 1)
        self.assertEqual(second_officer["calls_today"], 0)

    def test_follow_up_submission_moves_fresh_lead_to_follow_ups(self):
        self.client.force_authenticate(self.first_so)
        fixed_now = timezone.localtime(timezone.now()).replace(hour=10, minute=0, second=0, microsecond=0)
        same_day_eod = fixed_now.replace(hour=23, minute=59)
        with patch("django.utils.timezone.now", return_value=fixed_now):
            response = self.client.patch(f"/api/leads/{self.first_lead.id}/so-update/", {"call_outcome": "Call Me Back", "status": Lead.Status.PENDING, "follow_up_at": same_day_eod.isoformat()}, format="json")
        self.assertEqual(response.status_code, 200)
        self.first_lead.refresh_from_db()
        self.assertEqual(self.first_lead.status, Lead.Status.PENDING)
        fresh = self.client.get("/api/leads/my-dashboard/?section=fresh")
        follow_ups = self.client.get("/api/leads/my-dashboard/?section=followups")
        self.assertNotIn(self.first_lead.id, [lead["id"] for lead in fresh.data["results"]])
        self.assertIn(self.first_lead.id, [lead["id"] for lead in follow_ups.data["results"]])

    def test_sales_officer_cannot_update_another_officers_lead(self):
        self.client.force_authenticate(self.first_so)
        response = self.client.patch(f"/api/leads/{self.second_lead.id}/so-update/", {"category": Lead.Category.COLD}, format="json")
        self.assertEqual(response.status_code, 404)

    def test_admin_assigns_qualified_lead_to_ps_so(self):
        self.first_lead.status = Lead.Status.QUALIFIED
        self.first_lead.save(update_fields=["status"])
        self.client.force_authenticate(self.admin)

        response = self.client.post(f"/api/leads/{self.first_lead.id}/assign-ps/", {"sales_officer_id": self.ps_so.id}, format="json")

        self.assertEqual(response.status_code, 200)
        self.first_lead.refresh_from_db()
        self.assertEqual(self.first_lead.assigned_ps, self.ps_so)

    def test_cre_keeps_update_access_after_ps_handoff(self):
        self.first_lead.status = Lead.Status.QUALIFIED
        self.first_lead.assigned_ps = self.ps_so
        self.first_lead.save(update_fields=["status", "assigned_ps"])
        self.client.force_authenticate(self.first_so)

        detail = self.client.get(f"/api/leads/{self.first_lead.id}/")
        dashboard = self.client.get("/api/leads/my-dashboard/?section=qualified")
        update = self.client.patch(f"/api/leads/{self.first_lead.id}/so-update/", {"category": Lead.Category.COLD}, format="json")
        log_call = self.client.post(f"/api/leads/{self.first_lead.id}/log-call/", {"status": Lead.Status.WALKIN, "follow_up_at": (timezone.now() + timedelta(days=1)).isoformat()}, format="json")

        self.assertEqual(detail.status_code, 200)
        self.assertIn(self.first_lead.id, [lead["id"] for lead in dashboard.data["results"]])
        self.assertEqual(update.status_code, 200)
        self.assertEqual(log_call.status_code, 200)

    def test_ps_so_sees_assigned_qualified_lead_with_cre_qualification(self):
        LeadQualification.objects.create(lead=self.first_lead, variant="R8 Pro", buying_timeline="Immediate", finance_type="Inhouse", notes="Ready")
        self.first_lead.status = Lead.Status.QUALIFIED
        self.first_lead.assigned_ps = self.ps_so
        self.first_lead.save(update_fields=["status", "assigned_ps"])
        self.client.force_authenticate(self.ps_so)

        response = self.client.get("/api/leads/")
        detail = self.client.get(f"/api/leads/{self.first_lead.id}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([lead["id"] for lead in response.data["results"]], [self.first_lead.id])
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["qualification"]["variant"], "R8 Pro")

    def test_ps_so_can_retail_but_not_edit_cre_qualification(self):
        self.first_lead.status = Lead.Status.QUALIFIED
        self.first_lead.assigned_ps = self.ps_so
        self.first_lead.save(update_fields=["status", "assigned_ps"])
        self.client.force_authenticate(self.ps_so)

        response = self.client.patch(f"/api/leads/{self.first_lead.id}/so-update/", {"status": Lead.Status.WON, "sales_outcome": Lead.SalesOutcome.RETAILED, "remarks": "Sale done."}, format="json")
        self.assertEqual(response.status_code, 200)
        self.first_lead.refresh_from_db()
        self.assertEqual(self.first_lead.status, Lead.Status.WON)

        response = self.client.patch(f"/api/leads/{self.first_lead.id}/so-update/", {"qualification": {"variant": "R9 Plus"}}, format="json")
        self.assertEqual(response.status_code, 403)
