"""Sales call eligibility and milestone transitions shared by reads and writes."""
from datetime import timedelta

from django.utils import timezone
from rest_framework.exceptions import ValidationError

from accounts.models import User
from .models import Lead


CLOSED_STATUSES = {Lead.Status.WON, Lead.Status.LOST, Lead.Status.UNQUALIFIED}
CONNECTED = {
    "Need Test Drive": "PENDING", "Showroom Visit": "PENDING",
    "Exchange Issue": "PENDING", "Booking Done": "WALKIN", "Retail Done": "WON",
    "Call Me Back": "CALLBACK", "Need time": "PENDING", "Need SO Call": "PENDING",
    "Need More Details": "PENDING", "Discount Issue": "PENDING",
    "Not Interested": "LOST", "Already Booked": "LOST", "Lost to Competition": "LOST",
    "Finance Rejected": "LOST", "Dropped": "LOST", "Lost to co-dealer": "LOST",
}
NOT_CONNECTED = {
    "RNR": "RNR", "Switch Off": "SWITCHED_OFF", "Call Forwarding": "PENDING",
    "Line Busy": "PENDING", "Invalid Number": "PENDING", "No Response": "PENDING",
}
PS_CALL_OUTCOME_STATUS_OPTIONS = {name: {state} for name, state in {**CONNECTED, **NOT_CONNECTED}.items()}
# CE pending reasons use these labels without the sales call workflow.
for name in ("RNR", "Switch Off", "Call Me Back"):
    PS_CALL_OUTCOME_STATUS_OPTIONS[name].add(Lead.Status.PENDING)

CALL_FIELDS = {"status", "sales_outcome", "remarks", "call_status", "call_outcome", "follow_up_at"}


def is_closed(lead):
    return lead.status in CLOSED_STATUSES or lead.sales_outcome in {"RETAILED", "LOST"}


def is_booked(lead):
    return lead.status == Lead.Status.WALKIN or lead.sales_outcome == Lead.SalesOutcome.BOOKED


def outcome_policy(lead, user):
    active = bool(user and user.is_active and not lead.deleted_at)
    sales = active and (user.is_admin or (user.role == User.Role.SALES_OFFICER and lead.assigned_ps_id == user.pk))
    can_update = bool(not is_closed(lead) and (sales or (active and user.role == User.Role.CRE and lead.assigned_so_id == user.pk)))
    groups = {"Connected": [], "Not Connected": []}
    if sales and can_update:
        for call_status, outcomes in (("Connected", CONNECTED), ("Not Connected", NOT_CONNECTED)):
            for label, state in outcomes.items():
                if label == "Need Test Drive" and lead.test_drive_completed_at:
                    continue
                if label == "Booking Done" and is_booked(lead):
                    continue
                sales_outcome = {"WON": "RETAILED", "LOST": "LOST", "WALKIN": "BOOKED"}.get(state, "PENDING")
                if is_booked(lead) and sales_outcome == "PENDING":
                    state, sales_outcome = "WALKIN", "BOOKED"
                groups[call_status].append({
                    "label": label, "status": state, "sales_outcome": sales_outcome,
                    "tone": "lost" if state == "LOST" else "qualified",
                    "requires_follow_up": state not in CLOSED_STATUSES,
                })
    return {
        "can_update": can_update,
        "can_complete_test_drive": bool(sales and not is_closed(lead) and not lead.test_drive_completed_at),
        "outcomes": groups,
    }


def validate_sales_call(lead, user, attrs):
    if not CALL_FIELDS.intersection(attrs):
        return attrs
    policy = outcome_policy(lead, user)
    if not policy["can_update"]:
        raise ValidationError({"detail": "This lead is closed or unavailable for updates."})
    call_status = attrs.get("call_status")
    if call_status not in policy["outcomes"]:
        raise ValidationError({"call_status": "Choose Connected or Not Connected."})
    option = next((item for item in policy["outcomes"][call_status] if item["label"] == attrs.get("call_outcome")), None)
    if not option:
        raise ValidationError({"call_outcome": "This outcome is unavailable for the current lead and call status. Refresh and choose again."})
    if not attrs.get("remarks", "").strip():
        raise ValidationError({"remarks": "Remarks are required."})
    for field in ("status", "sales_outcome"):
        if attrs.get(field) and attrs[field] != option[field]:
            raise ValidationError({field: "This value conflicts with the lead's progress and call outcome."})
        attrs[field] = option[field]
    follow_up = attrs.get("follow_up_at")
    if option["requires_follow_up"]:
        if not follow_up:
            raise ValidationError({"follow_up_at": "Choose a follow-up date for this outcome."})
        if not timezone.now() < follow_up <= timezone.now() + timedelta(days=3):
            raise ValidationError({"follow_up_at": "Choose a future follow-up within the next 3 days."})
    elif follow_up:
        raise ValidationError({"follow_up_at": "Closed outcomes cannot have a follow-up."})
    validate_retail_vehicle(lead, attrs)
    return attrs


def validate_milestone_change(lead, attrs):
    """Protect milestones on the older CE/status-only interfaces as well."""
    if not CALL_FIELDS.intersection(attrs):
        return
    if is_closed(lead):
        raise ValidationError({"detail": "This lead is closed. Use the reopen action before recording another outcome."})
    next_status = attrs.get("status") or lead.status
    if is_booked(lead) and (next_status not in {"WALKIN", "WON", "LOST"} or attrs.get("sales_outcome") == "PENDING"):
        raise ValidationError({"status": "A routine follow-up cannot remove the booking. Use a sales call outcome."})
    expected = {"WALKIN": "BOOKED", "WON": "RETAILED", "LOST": "LOST"}.get(next_status, "PENDING")
    if attrs.get("sales_outcome") and attrs["sales_outcome"] != expected:
        raise ValidationError({"sales_outcome": "Choose a sales outcome matching the lead status."})
    attrs["sales_outcome"] = expected
    validate_retail_vehicle(lead, attrs)


def validate_retail_vehicle(lead, attrs):
    if (attrs.get("sales_outcome") == "RETAILED" or attrs.get("status") == "WON") and lead.sales_outcome != "RETAILED" and not lead.vehicles.exists():
        raise ValidationError({"chassis_number": "Register the scooter chassis in Vehicle & service history before marking this sale Retailed."})
