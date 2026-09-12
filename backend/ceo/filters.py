from datetime import date, timedelta

from django.db.models import Q
from django.db.models.functions import Lower, Trim
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework.exceptions import ValidationError

from accounts.models import User
from leads.models import Lead
from .models import Milestone, OperationEvent

ROLES = {"CRE", "SO", "RECEPTIONIST", "SALES_MANAGER", "COMPLAINTS"}
DIMENSIONS = ("rto", "source", "campaign", "activity", "sub_activity", "model_interest")
AGE_BANDS = {"0_3": (0, 3), "4_7": (4, 7), "8_14": (8, 14), "15_30": (15, 30), "31_plus": (31, None)}


class ReportFilters:
    def __init__(self, params):
        self.params = params
        self.mode = params.get("mode", "period")
        if self.mode not in {"period", "cohort"}:
            raise ValidationError({"mode": "Choose period or cohort."})
        self.range = params.get("range", "mtd")
        today = timezone.localdate()
        ranges = {"today": (today, today), "mtd": (today.replace(day=1), today),
                  "quarter": (date(today.year, 1 + 3 * ((today.month - 1) // 3), 1), today), "all": (None, None)}
        previous_end = today.replace(day=1) - timedelta(days=1)
        ranges["previous_month"] = (previous_end.replace(day=1), previous_end)
        if self.range == "custom":
            try:
                self.start, self.end = parse_date(params.get("date_from", "")), parse_date(params.get("date_to", ""))
            except ValueError:
                raise ValidationError({"date_from": "Enter valid calendar dates."})
            if not self.start or not self.end or self.start > self.end:
                raise ValidationError({"date_from": "Enter a valid start and end date in order."})
        elif self.range in ranges:
            self.start, self.end = ranges[self.range]
        else:
            raise ValidationError({"range": "Choose a valid reporting period."})
        if self.end and self.end > today:
            raise ValidationError({"date_to": "Choose today or an earlier date."})
        self.branches = [value.strip().casefold() for value in params.getlist("branch") if value.strip()]
        self.employee = None
        if params.get("employee"):
            try:
                self.employee = User.objects.get(pk=int(params["employee"]), role__in=ROLES)
            except (ValueError, User.DoesNotExist):
                raise ValidationError({"employee": "Choose an operational employee."})
        if params.get("role") and params["role"] not in ROLES:
            raise ValidationError({"role": "Choose an operational role."})
        if self.employee and params.get("role") and self.employee.role != params["role"]:
            raise ValidationError({"employee": "Choose an employee in the selected role."})
        if params.get("status") and params["status"] not in Lead.Status.values:
            raise ValidationError({"status": "Choose a valid lead status."})
        if params.get("category") and params["category"] not in [*Lead.Category.values, "__unknown__"]:
            raise ValidationError({"category": "Choose a valid category."})
        if params.get("age") and params["age"] not in AGE_BANDS:
            raise ValidationError({"age": "Choose a valid lead age band."})
        if params.get("metric") and params["metric"] not in {"E", "T", "B", "R"}:
            raise ValidationError({"metric": "Choose E, T, B or R."})
        if params.get("followup") and params["followup"] not in {"overdue", "due", "missing", "unassigned", "reassignment", "untouched", "flagged", "incomplete"}:
            raise ValidationError({"followup": "Choose a valid workload filter."})

    def period(self, queryset, field):
        if self.start:
            queryset = queryset.filter(**{f"{field}__gte": self.start})
        if self.end:
            queryset = queryset.filter(**{f"{field}__lte": self.end})
        return queryset

    def dimensions(self, queryset, prefix="", snapshots=False, branch=True):
        if branch and self.branches:
            field = prefix + "branch"
            queryset = queryset.annotate(_filter_branch=Lower(Trim(field))).filter(_filter_branch__in=["" if b == "__unknown__" else b for b in self.branches])
        for key in DIMENSIONS:
            value = self.params.get(key)
            if value:
                queryset = queryset.filter(**{prefix + key: "" if value == "__unknown__" else value})
        return queryset

    def base_leads(self, include_archived=False, dimensions=True, employee=True):
        queryset = Lead.objects.all()
        if not include_archived:
            queryset = queryset.filter(deleted_at__isnull=True)
        if dimensions:
            queryset = self.dimensions(queryset)
        for key in ("status", "category"):
            if self.params.get(key):
                queryset = queryset.filter(**{key: "" if self.params[key] == "__unknown__" else self.params[key]})
        if self.params.get("q"):
            q = self.params["q"].strip()
            query = Q(name__icontains=q) | Q(phone__icontains=q) | Q(email__icontains=q)
            if q.isdigit():
                query |= Q(pk=int(q))
            queryset = queryset.filter(query)
        if employee and self.employee:
            relation = self.params.get("ownership", "current")
            if relation == "handled":
                queryset = queryset.filter(pk__in=self.period(OperationEvent.objects.filter(actor=self.employee), "occurred_at__date").values("lead_id"))
            elif self.employee.role == "CRE":
                queryset = queryset.filter(assigned_so=self.employee)
            elif self.employee.role == "SO":
                queryset = queryset.filter(assigned_ps=self.employee)
            elif self.employee.role == "RECEPTIONIST":
                queryset = queryset.filter(pk__in=Milestone.objects.filter(kind="E", actor=self.employee).values("lead_id"))
            elif self.employee.role == "SALES_MANAGER":
                queryset = queryset.annotate(_employee_branch=Lower(Trim("branch"))).filter(_employee_branch=self.employee.location.strip().casefold()) if self.employee.location.strip() else queryset.none()
            else:
                queryset = queryset.filter(complaints__assigned_to=self.employee)
        elif employee and self.params.get("role"):
            role = self.params["role"]
            if role == "CRE":
                queryset = queryset.filter(assigned_so__role=role)
            elif role == "SO":
                queryset = queryset.filter(assigned_ps__role=role)
            elif role == "RECEPTIONIST":
                queryset = queryset.filter(pk__in=Milestone.objects.filter(kind="E", actor__role=role).values("lead_id"))
            elif role == "COMPLAINTS":
                queryset = queryset.filter(complaints__assigned_to__role=role)
            else:
                locations = User.objects.filter(role=role).exclude(location="").annotate(key=Lower(Trim("location"))).values("key")
                queryset = queryset.annotate(_manager_branch=Lower(Trim("branch"))).filter(_manager_branch__in=locations)
        return self.workload(queryset).distinct()

    def workload(self, queryset):
        from leads.models import FollowUp
        today = timezone.localdate()
        active = ~Q(status__in=["WON", "LOST", "UNQUALIFIED"])
        open_followups = FollowUp.objects.filter(resolved_at__isnull=True)
        if self.params.get("age"):
            low, high = AGE_BANDS[self.params["age"]]
            queryset = queryset.filter(active, enquiry_date__lte=today - timedelta(days=low))
            if high is not None:
                queryset = queryset.filter(enquiry_date__gte=today - timedelta(days=high))
        filters = {
            "overdue": Q(pk__in=open_followups.filter(scheduled_for__lt=timezone.now()).values("lead_id")) & active,
            "due": Q(pk__in=open_followups.filter(scheduled_for__date=today).values("lead_id")) & active,
            "missing": ~Q(pk__in=open_followups.values("lead_id")) & active,
            "unassigned": (Q(assigned_so__isnull=True, assigned_ps__isnull=True) | Q(status="QUALIFIED", assigned_ps__isnull=True)) & active,
            "reassignment": Q(needs_cre_reassignment=True) | Q(needs_so_reassignment=True),
            "untouched": ~Q(pk__in=OperationEvent.objects.filter(kind="call").values("lead_id")) & active,
            "flagged": Q(flagged_to_manager=True),
            "incomplete": Q(rto="") | Q(branch=""),
        }
        return queryset.filter(filters[self.params["followup"]]) if self.params.get("followup") else queryset

    def milestones(self, apply_metric=False):
        queryset = Milestone.objects.filter(lead__deleted_at__isnull=True)
        if self.mode == "cohort":
            queryset = queryset.filter(lead_id__in=self.period(self.base_leads(), "enquiry_date").values("id"))
        else:
            queryset = self.period(self.dimensions(queryset), "occurred_on")
            queryset = queryset.filter(lead_id__in=self.base_leads(dimensions=False, employee=False).values("id"))
            if self.employee:
                user = self.employee
                if user.role in {"CRE", "SO"}:
                    queryset = queryset.filter(**{"cre" if user.role == "CRE" else "so": user})
                elif user.role == "RECEPTIONIST":
                    queryset = queryset.filter(lead_id__in=Milestone.objects.filter(kind="E", actor=user).values("lead_id"))
                elif user.role == "SALES_MANAGER":
                    queryset = queryset.filter(branch=user.location.strip().casefold()) if user.location.strip() else queryset.none()
                else:
                    queryset = queryset.filter(lead__complaints__assigned_to=user)
            elif self.params.get("role"):
                role = self.params["role"]
                if role in {"CRE", "SO"}:
                    queryset = queryset.filter(**{f"{'cre' if role == 'CRE' else 'so'}__role": role})
                else:
                    queryset = queryset.filter(lead_id__in=self.base_leads(dimensions=False).values("id"))
        if apply_metric and self.params.get("metric"):
            queryset = queryset.filter(kind=self.params["metric"])
        return queryset.distinct()

    def leads(self):
        if self.params.get("metric"):
            return Lead.objects.filter(pk__in=self.milestones(True).values("lead_id"))
        queryset = self.base_leads()
        return queryset if self.params.get("scope") == "workload" else self.period(queryset, "enquiry_date")

    def events(self):
        queryset = OperationEvent.objects.filter(Q(lead__deleted_at__isnull=True), lead__isnull=False)
        queryset = self.period(queryset, "occurred_at__date")
        if self.mode == "cohort":
            queryset = queryset.filter(lead_id__in=self.period(self.base_leads(employee=False), "enquiry_date").values("id"))
        else:
            if self.branches:
                queryset = queryset.filter(branch__in=["" if b == "__unknown__" else b for b in self.branches])
            for key in DIMENSIONS:
                if self.params.get(key):
                    queryset = queryset.filter(**{f"snapshot__{key}": "" if self.params[key] == "__unknown__" else self.params[key]})
            queryset = queryset.filter(lead_id__in=self.base_leads(dimensions=False, employee=False).values("id"))
        if self.employee:
            queryset = queryset.filter(actor=self.employee)
        elif self.params.get("role"):
            queryset = queryset.filter(actor__role=self.params["role"])
        return queryset

    def metadata(self):
        return {"mode": self.mode, "range": self.range, "date_from": self.start, "date_to": self.end,
                "branches": self.branches, "generated_at": timezone.now(), "timezone": "Asia/Kolkata"}

    def target_month(self):
        if self.mode == "period" and self.range in {"mtd", "previous_month"}:
            return self.start.replace(day=1)
        return None
