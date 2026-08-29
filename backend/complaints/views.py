from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Q
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework import status as http_status
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from accounts.models import User
from analytics.cache import cache_analytics
from .models import Complaint, ComplaintNote
from .permissions import ComplaintAnalyticsPermission, ComplaintPermission
from .serializers import (
    ComplaintCreateSerializer,
    ComplaintDetailSerializer,
    ComplaintListSerializer,
    ComplaintNoteSerializer,
    ComplaintUpdateSerializer,
)


class ComplaintPagination(PageNumberPagination):
    page_size = 50


class ComplaintViewSet(ModelViewSet):
    pagination_class = ComplaintPagination
    serializer_class = ComplaintListSerializer
    permission_classes = [ComplaintPermission]

    def get_queryset(self):
        user = self.request.user
        queryset = Complaint.objects.select_related("logged_by", "assigned_to")

        # CRE users see only what they logged; admins and complaints department see the shared queue.
        if user.role == User.Role.CRE:
            queryset = queryset.filter(logged_by=user)

        # Annotate note count for list performance
        queryset = queryset.annotate(_note_count=Count("notes"))

        # Filters
        params = self.request.query_params
        if params.get("status"):
            queryset = queryset.filter(status=params["status"])
        if params.get("category"):
            queryset = queryset.filter(category=params["category"])
        if params.get("priority"):
            queryset = queryset.filter(priority=params["priority"])
        if params.get("source"):
            queryset = queryset.filter(source=params["source"])
        if params.get("date_from"):
            queryset = queryset.filter(created_at__date__gte=params["date_from"])
        if params.get("date_to"):
            queryset = queryset.filter(created_at__date__lte=params["date_to"])
        if params.get("q"):
            q = params["q"]
            queryset = queryset.filter(
                Q(customer_name__icontains=q)
                | Q(customer_phone__icontains=q)
                | Q(ticket_number__icontains=q)
                | Q(subject__icontains=q)
            )

        return queryset.order_by("-created_at")

    def get_serializer_class(self):
        if self.action == "retrieve":
            return ComplaintDetailSerializer
        if self.action == "create":
            return ComplaintCreateSerializer
        return ComplaintListSerializer

    def perform_create(self, serializer):
        serializer.save(logged_by=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        # Return the full list representation
        complaint = serializer.instance
        output = ComplaintListSerializer(complaint).data
        return Response(output, status=http_status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        complaint = self.get_object()
        previous_resolution_notes = complaint.resolution_notes
        serializer = ComplaintUpdateSerializer(
            data=request.data, context={"complaint": complaint}
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if "status" in data:
            complaint.status = data["status"]
            if data["status"] == Complaint.Status.RESOLVED and not complaint.resolved_at:
                complaint.resolved_at = timezone.now()
            elif data["status"] == Complaint.Status.CLOSED and not complaint.resolved_at:
                complaint.resolved_at = timezone.now()
        if "priority" in data:
            complaint.priority = data["priority"]
        if "resolution_notes" in data:
            complaint.resolution_notes = data["resolution_notes"]
        complaint.assigned_to = request.user
        complaint.save()
        if (
            "resolution_notes" in data
            and data["resolution_notes"].strip()
            and data["resolution_notes"].strip() != previous_resolution_notes.strip()
        ):
            ComplaintNote.objects.create(
                complaint=complaint,
                author=request.user,
                content=data["resolution_notes"].strip(),
            )
        output = ComplaintDetailSerializer(complaint).data
        return Response(output)

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="add-note")
    def add_note(self, request, pk=None):
        complaint = self.get_object()
        content = request.data.get("content", "").strip()
        if not content:
            return Response(
                {"content": "Remark content is required."},
                status=http_status.HTTP_400_BAD_REQUEST,
            )
        note = ComplaintNote.objects.create(
            complaint=complaint, author=request.user, content=content
        )
        return Response(ComplaintNoteSerializer(note).data, status=http_status.HTTP_201_CREATED)


class ComplaintAnalyticsView(APIView):
    permission_classes = [ComplaintAnalyticsPermission]

    @cache_analytics("complaints")
    def get(self, request):
        queryset = Complaint.objects.all()

        # Date range filter
        date_range = request.query_params.get("range", "mtd")
        today = timezone.localdate()
        if date_range == "today":
            queryset = queryset.filter(created_at__date=today)
        elif date_range == "mtd":
            queryset = queryset.filter(created_at__date__year=today.year, created_at__date__month=today.month)
        elif date_range == "week":
            from datetime import timedelta
            queryset = queryset.filter(created_at__date__gte=today - timedelta(days=7))
        elif request.query_params.get("date_from"):
            queryset = queryset.filter(created_at__date__gte=request.query_params["date_from"])
            if request.query_params.get("date_to"):
                queryset = queryset.filter(created_at__date__lte=request.query_params["date_to"])

        # Summary counts
        summary = queryset.aggregate(
            total=Count("id"),
            open=Count("id", filter=Q(status=Complaint.Status.OPEN)),
            in_progress=Count("id", filter=Q(status=Complaint.Status.IN_PROGRESS)),
            escalated=Count("id", filter=Q(status=Complaint.Status.ESCALATED)),
            resolved=Count("id", filter=Q(status=Complaint.Status.RESOLVED)),
            closed=Count("id", filter=Q(status=Complaint.Status.CLOSED)),
            average_resolution=Avg(
                ExpressionWrapper(F("resolved_at") - F("created_at"), output_field=DurationField()),
                filter=Q(resolved_at__isnull=False),
            ),
        )
        average = summary.pop("average_resolution")
        summary["avg_resolution_hours"] = round(average.total_seconds() / 3600, 1) if average else 0

        # Breakdown by category
        by_category = list(
            queryset.values("category")
            .annotate(count=Count("id"))
            .order_by("-count")
        )

        # Breakdown by priority
        by_priority = list(
            queryset.values("priority")
            .annotate(count=Count("id"))
            .order_by("-count")
        )

        # Breakdown by status
        by_status = list(
            queryset.values("status")
            .annotate(count=Count("id"))
            .order_by("status")
        )

        # Daily trend (last 30 days or within range)
        trend = list(
            queryset.annotate(date=TruncDate("created_at"))
            .values("date")
            .annotate(
                opened=Count("id"),
                resolved=Count("id", filter=Q(status__in=[Complaint.Status.RESOLVED, Complaint.Status.CLOSED])),
            )
            .order_by("date")
        )

        response = {
            "summary": summary,
            "by_category": by_category,
            "by_priority": by_priority,
            "by_status": by_status,
            "trend": trend,
            "generated_at": timezone.now(),
        }
        if request.user.is_admin:
            response["by_resolution_team"] = _resolution_team_performance(queryset)
        return Response(response)


def _resolution_team_performance(queryset):
    rows = queryset.filter(assigned_to__role=User.Role.COMPLAINTS).annotate(
        resolution_duration=ExpressionWrapper(
            F("resolved_at") - F("created_at"), output_field=DurationField()
        )
    ).values(
        "assigned_to_id", "assigned_to__first_name", "assigned_to__last_name", "assigned_to__email"
    ).annotate(
        total=Count("id"),
        open=Count("id", filter=Q(status=Complaint.Status.OPEN)),
        in_progress=Count("id", filter=Q(status=Complaint.Status.IN_PROGRESS)),
        escalated=Count("id", filter=Q(status=Complaint.Status.ESCALATED)),
        resolved=Count("id", filter=Q(status=Complaint.Status.RESOLVED)),
        closed=Count("id", filter=Q(status=Complaint.Status.CLOSED)),
        avg_resolution_hours=Avg("resolution_duration"),
    ).order_by("-total", "assigned_to__first_name", "assigned_to__last_name")
    performance = []
    for row in rows:
        resolved_count = row["resolved"] + row["closed"]
        average = row["avg_resolution_hours"]
        performance.append({
            "id": row["assigned_to_id"],
            "name": " ".join(filter(None, [row["assigned_to__first_name"], row["assigned_to__last_name"]])) or row["assigned_to__email"],
            "total": row["total"],
            "open": row["open"],
            "in_progress": row["in_progress"],
            "escalated": row["escalated"],
            "resolved": row["resolved"],
            "closed": row["closed"],
            "resolution_rate": round((resolved_count / row["total"]) * 100, 1) if row["total"] else 0,
            "avg_resolution_hours": round(average.total_seconds() / 3600, 1) if average else 0,
        })
    return performance
