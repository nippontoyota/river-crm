from decimal import Decimal

from django.db import transaction
from django.db.models import Case, DecimalField, F, Q, Sum, Value, When
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from accounts.models import User
from leads.models import Lead
from .models import FinancialEntry, SaleAccount, SalesTarget, TargetRevision
from .tracking import branch_key

TARGET_FIELDS = ("enquiries", "test_drives", "bookings", "retails", "retail_value")
MONEY = DecimalField(max_digits=15, decimal_places=2)


def signed_amount():
    return Case(When(kind="PAYMENT", then=F("amount")), When(kind="REFUND", then=-F("amount")),
                When(kind="REVERSAL", reverses__kind="PAYMENT", then=-F("amount")),
                When(kind="REVERSAL", reverses__kind="REFUND", then=F("amount")), default=Value(Decimal("0")), output_field=MONEY)


def balance(account):
    return account.entries.aggregate(value=Sum(signed_amount()))["value"] or Decimal("0")


def target_data(target):
    return {"id": target.id, "month": target.month.isoformat(), "branch": target.branch, "so": target.so_id,
            **{key: str(getattr(target, key)) if key == "retail_value" else getattr(target, key) for key in TARGET_FIELDS}, "updated_at": target.updated_at.isoformat()}


class TargetInput(serializers.Serializer):
    month = serializers.DateField()
    branch = serializers.CharField(max_length=120)
    so = serializers.PrimaryKeyRelatedField(queryset=User.objects.filter(role="SO", is_active=True, deleted_at__isnull=True), required=False, allow_null=True)
    enquiries = serializers.IntegerField(min_value=0)
    test_drives = serializers.IntegerField(min_value=0)
    bookings = serializers.IntegerField(min_value=0)
    retails = serializers.IntegerField(min_value=0)
    retail_value = serializers.DecimalField(max_digits=15, decimal_places=2, min_value=0)
    version = serializers.DateTimeField(required=False)

    def validate(self, attrs):
        from leads.models import SystemConfig
        attrs["branch"] = branch_key(attrs["branch"])
        known = {branch_key(value) for value in (SystemConfig.objects.filter(pk=1).values_list("lists", flat=True).first() or {}).get("branches", [])}
        known.update(branch_key(value) for value in Lead.objects.values_list("branch", flat=True).distinct())
        if not attrs["branch"] or attrs["branch"] not in known:
            raise ValidationError({"branch": "Choose a configured or recorded branch."})
        if attrs["month"].day != 1:
            raise ValidationError({"month": "Use the first day of the target month."})
        if attrs.get("so") and branch_key(attrs["so"].location) != attrs["branch"]:
            raise ValidationError({"so": "Choose an SO in this branch."})
        return attrs


@transaction.atomic
def save_target(data, actor):
    # The branch target is also the lock for concurrent SO allocations.
    if data.get("so") and not SalesTarget.objects.filter(month=data["month"], branch=data["branch"], so__isnull=True).exists():
        raise ValidationError({"branch": "Set the branch target before allocating SO targets."})
    parent, _ = SalesTarget.objects.get_or_create(month=data["month"], branch=data["branch"], so=None)
    SalesTarget.objects.select_for_update().get(pk=parent.pk)
    target = SalesTarget.objects.filter(month=data["month"], branch=data["branch"], so=data.get("so")).first()
    before = target_data(target) if target else {}
    version = data.pop("version", None)
    if target and version and target.updated_at != version:
        raise ValidationError({"detail": "This target changed. Reload before saving."})
    if target is None:
        target = SalesTarget(month=data["month"], branch=data["branch"], so=data.get("so"))
    for key in TARGET_FIELDS:
        setattr(target, key, data[key])
    target.save()
    TargetRevision.objects.create(target=target, actor=actor, before=before, after=target_data(target))
    return target


class FinanceInput(serializers.Serializer):
    lead = serializers.PrimaryKeyRelatedField(queryset=Lead.objects.all())
    kind = serializers.ChoiceField(choices=FinancialEntry._meta.get_field("kind").choices)
    amount = serializers.DecimalField(max_digits=15, decimal_places=2, min_value=0, required=False, default=0)
    occurred_on = serializers.DateField()
    method = serializers.ChoiceField(choices=FinancialEntry._meta.get_field("method").choices, required=False, default="")
    reference = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    notes = serializers.CharField(max_length=500)
    idempotency_key = serializers.UUIDField()
    reverses = serializers.IntegerField(min_value=1, required=False)
    agreed_amount = serializers.DecimalField(max_digits=15, decimal_places=2, min_value=0, required=False, allow_null=True)
    retail_amount = serializers.DecimalField(max_digits=15, decimal_places=2, min_value=0, required=False, allow_null=True)
    confirmed_on = serializers.DateField(required=False, allow_null=True)

    def validate(self, attrs):
        if attrs["occurred_on"] > timezone.localdate() or (attrs.get("confirmed_on") and attrs["confirmed_on"] > timezone.localdate()):
            raise ValidationError({"occurred_on": "Financial dates cannot be in the future."})
        if attrs["kind"] in {"PAYMENT", "REFUND"} and (not attrs["amount"] or not attrs["method"]):
            raise ValidationError({"amount": "Enter a positive amount and payment method."})
        if attrs["kind"] == "REVERSAL" and not attrs.get("reverses"):
            raise ValidationError({"reverses": "Choose the payment or refund to reverse."})
        if attrs["kind"] == "VALUATION" and not {"agreed_amount", "retail_amount"}.intersection(attrs):
            raise ValidationError({"agreed_amount": "Enter a sale amount to revise."})
        if attrs["kind"] != "VALUATION" and {"agreed_amount", "retail_amount", "confirmed_on"}.intersection(attrs):
            raise ValidationError({"kind": "Use a sale value revision to change agreed or retail amounts."})
        if attrs["kind"] != "REVERSAL" and attrs.get("reverses"):
            raise ValidationError({"reverses": "Only a reversal can reference an earlier entry."})
        return attrs


@transaction.atomic
def save_finance(data, actor):
    lead = Lead.objects.select_for_update().get(pk=data["lead"].pk)
    request_record = {key: str(value.pk if key == "lead" else value) for key, value in data.items()}
    existing = FinancialEntry.objects.filter(idempotency_key=data["idempotency_key"]).first()
    if existing:
        if existing.after.get("request") != request_record:
            raise ValidationError({"idempotency_key": "This submission key was already used for another entry."})
        return existing
    account, _ = SaleAccount.objects.get_or_create(lead=lead)
    before = {key: str(getattr(account, key)) if getattr(account, key) is not None else None for key in ("agreed_amount", "retail_amount", "confirmed_on")}
    kind = data["kind"]
    original = None
    amount = data["amount"]
    net = balance(account)
    if kind == "VALUATION":
        amount = Decimal("0")
        for key in before:
            if key in data:
                setattr(account, key, data[key])
        if account.retail_amount is not None and not account.confirmed_on:
            raise ValidationError({"confirmed_on": "Enter the date of the final confirmed customer amount."})
        if account.retail_amount is None:
            account.confirmed_on = None
        account.save()
    elif kind == "REVERSAL":
        original = FinancialEntry.objects.filter(pk=data["reverses"], account=account, kind__in=["PAYMENT", "REFUND"]).first()
        if not original or FinancialEntry.objects.filter(reverses=original).exists():
            raise ValidationError({"reverses": "Choose an unreversed payment or refund from this lead."})
        if data["occurred_on"] < original.occurred_on:
            raise ValidationError({"occurred_on": "A reversal cannot predate its original entry."})
        amount = original.amount
        net += -amount if original.kind == "PAYMENT" else amount
    elif kind == "REFUND":
        net -= amount
    else:
        net += amount
    if net < 0:
        raise ValidationError({"amount": "This entry would refund more than the customer's net payments."})
    if kind != "VALUATION":
        delta = -amount if kind == "REFUND" or (kind == "REVERSAL" and original.kind == "PAYMENT") else amount
        # Backdated entries must also preserve balances on every intervening day.
        days = list(account.entries.values("occurred_on").annotate(change=Sum(signed_amount())).order_by("occurred_on"))
        days.append({"occurred_on": data["occurred_on"], "change": delta})
        daily = {}
        for day in days:
            daily[day["occurred_on"]] = daily.get(day["occurred_on"], Decimal("0")) + day["change"]
        running = Decimal("0")
        for date in sorted(daily):
            running += daily[date]
            if running < 0:
                raise ValidationError({"occurred_on": "This entry would create a refund balance before sufficient payments were recorded."})
    if kind in {"PAYMENT", "REFUND"} and data["reference"] and account.entries.filter(kind=kind, reference=data["reference"], reversal__isnull=True).exists():
        raise ValidationError({"reference": "This reference is already recorded for the lead."})
    after = {key: str(getattr(account, key)) if getattr(account, key) is not None else None for key in before}
    after["request"] = request_record
    return FinancialEntry.objects.create(account=account, actor=actor, kind=kind, amount=amount,
        occurred_on=data["occurred_on"], method=data["method"], reference=data["reference"], notes=data["notes"],
        reverses=original, idempotency_key=data["idempotency_key"], branch=branch_key(lead.branch), before=before, after=after)
