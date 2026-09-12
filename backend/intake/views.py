import hashlib
import hmac
import json
from datetime import timedelta

from django.conf import settings
from django.db import DatabaseError, transaction
from django.db.models import Count, Min
from django.http import HttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes
from rest_framework import mixins, viewsets, serializers
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsAdmin
from .mapping import map_entries, sanitize_entries, normalize_phone
from .models import Connection, Heartbeat, IntakeAudit, IntakeForm, MappingVersion, Submission
from .serializers import (ErrorResponseSerializer, HealthSerializer, MappingPreviewResponseSerializer, QueuedResponseSerializer, WebhookResponseSerializer, ConnectionSerializer, FormSerializer, MappingSerializer, PreviewSerializer, ReceiptResponseSerializer, ReprocessSerializer, ResolutionSerializer, SubmissionDetailSerializer, SubmissionSerializer, WebsiteEnvelopeSerializer)
from .services import TERMINAL, accept, enqueue, payload_fingerprint, record, resolve, secret_config


class Pairs(list):
    pass


def object_dict(value):
    if not isinstance(value, Pairs) or len({key for key, _ in value}) != len(value):
        raise ValueError
    return dict(value)


def raw_body(request, limit):
    try:
        if int(request.META.get('CONTENT_LENGTH') or 0) > limit:
            return None
    except ValueError:
        raise ValidationError({'detail': 'Invalid content length.'})
    body = request._request.read(limit + 1)
    return body if len(body) <= limit else None


def constant_equal(left, right):
    return bool(right) and hmac.compare_digest(left.encode(), right.encode())


class WebsiteLeadView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = []

    @extend_schema(request=WebsiteEnvelopeSerializer, parameters=[OpenApiParameter("Authorization", str, OpenApiParameter.HEADER, required=True)], responses={202: ReceiptResponseSerializer, **{code: ErrorResponseSerializer for code in (400, 401, 403, 409, 413, 429, 503)}})
    def post(self, request):
        if not settings.INTAKE_ENABLED:
            return Response({'detail': 'Intake is temporarily unavailable.'}, status=503)
        authorization = request.META.get('HTTP_AUTHORIZATION', '')
        if not authorization.startswith('Bearer ') or len(authorization) > 1024:
            return Response({'detail': 'Invalid credentials.'}, status=401)
        token = authorization[7:]
        connection = None
        for candidate in Connection.objects.filter(origin='WEBSITE'):
            secrets = secret_config(candidate)
            if any(constant_equal(token, secrets.get(key, '')) for key in ('active', 'retiring')):
                connection = candidate
                break
        if connection is None:
            return Response({'detail': 'Invalid credentials.'}, status=401)
        if not connection.enabled:
            return Response({'detail': 'This connection is inactive.'}, status=403)
        raw = raw_body(request, settings.INTAKE_MAX_BYTES)
        if raw is None:
            return Response({'detail': 'Request exceeds 64 KiB.'}, status=413)
        if request.content_type != 'application/json':
            return Response({'detail': 'Use application/json.'}, status=400)
        try:
            payload = object_dict(json.loads(raw, object_pairs_hook=Pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError())))
            if set(payload) - {'submission_id', 'form_id', 'submitted_at', 'fields', 'attribution'}:
                raise ValueError
            for key in ('submission_id', 'form_id'):
                if not isinstance(payload.get(key), str) or not payload[key].strip() or len(payload[key]) > 160:
                    raise ValueError
            fields = payload.get('fields')
            if not isinstance(fields, Pairs) or len(fields) > settings.INTAKE_MAX_FIELDS:
                raise ValueError
            entries = []
            labels = [label for label, _ in fields]
            for index, (label, value) in enumerate(fields):
                if not label or len(label) > 160 or (value is not None and (isinstance(value, bool) or not isinstance(value, (str, int, float)))):
                    raise ValueError
                entries.append({'id': label if labels.count(label) == 1 else f'field:{index}', 'label': label, 'value': value})
            attribution = object_dict(payload.get('attribution', Pairs()))
            if set(attribution) - {'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content'} or any(not isinstance(v, str) or len(v) > 500 for v in attribution.values()):
                raise ValueError
            submitted = parse_datetime(payload['submitted_at']) if 'submitted_at' in payload else timezone.now()
            if not submitted or timezone.is_naive(submitted) or submitted > timezone.now():
                raise ValueError
            fingerprint = payload_fingerprint({'submission_id': payload['submission_id'], 'form_id': payload['form_id'], 'submitted_at': submitted.isoformat() if 'submitted_at' in payload else None,
                'fields': sorted(fields, key=lambda pair: (pair[0], json.dumps(pair[1]))), 'attribution': attribution})
        except (ValueError, TypeError, UnicodeError, OverflowError):
            return Response({'detail': 'Malformed intake envelope.'}, status=400)
        try:
            with transaction.atomic():
                connection = Connection.objects.select_for_update().get(pk=connection.pk)
                if not connection.enabled:
                    return Response({'detail': 'This connection is inactive.'}, status=403)
                form = connection.forms.filter(external_id=payload['form_id'], enabled=True).first()
                if not form or submitted < max(connection.activated_at, form.activated_at):
                    return Response({'detail': 'Unknown, inactive or pre-activation form submission.'}, status=403)
                now = timezone.now()
                if not connection.rate_window or connection.rate_window <= now - timedelta(minutes=1):
                    connection.rate_window, connection.rate_count = now, 0
                if connection.rate_count >= settings.INTAKE_RATE_PER_MINUTE:
                    return Response({'detail': 'Rate limit exceeded.'}, status=429, headers={'Retry-After': '60'})
                connection.rate_count += 1
                connection.save(update_fields=['rate_window', 'rate_count'])
            with transaction.atomic():
                form.connection = connection
                receipt, conflict = accept(form, payload['submission_id'], fingerprint, entries, submitted, attribution)
            if conflict:
                return Response({'detail': 'This submission ID has different content.'}, status=409)
            return Response({'receipt_id': str(receipt.pk), 'state': receipt.state}, status=202)
        except DatabaseError:
            return Response({'detail': 'Intake is temporarily unavailable. Retry with the same submission ID.'}, status=503)


class MetaWebhookView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = []

    @extend_schema(parameters=[OpenApiParameter(key, str, required=True) for key in ("hub.mode", "hub.verify_token", "hub.challenge")], responses={200: OpenApiTypes.STR, 403: ErrorResponseSerializer})
    def get(self, request):
        if request.query_params.get('hub.mode') == 'subscribe' and constant_equal(request.query_params.get('hub.verify_token', ''), settings.META_VERIFY_TOKEN):
            return HttpResponse(request.query_params.get('hub.challenge', ''), content_type='text/plain')
        return Response({'detail': 'Verification failed.'}, status=403)

    @extend_schema(request=OpenApiTypes.OBJECT, parameters=[OpenApiParameter('X-Hub-Signature-256', str, OpenApiParameter.HEADER, required=True)], responses={200: WebhookResponseSerializer, 400: ErrorResponseSerializer, 403: ErrorResponseSerializer, 413: ErrorResponseSerializer, 503: ErrorResponseSerializer})
    def post(self, request):
        if not settings.INTAKE_ENABLED or not settings.META_APP_SECRET:
            return Response({'detail': 'Intake is temporarily unavailable.'}, status=503)
        raw = raw_body(request, 1024 * 1024)
        if raw is None:
            return Response({'detail': 'Request too large.'}, status=413)
        expected = 'sha256=' + hmac.new(settings.META_APP_SECRET.encode(), raw, hashlib.sha256).hexdigest()
        if not constant_equal(request.META.get('HTTP_X_HUB_SIGNATURE_256', ''), expected):
            return Response({'detail': 'Invalid signature.'}, status=403)
        try:
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError
            if payload.get('object') != 'page':
                return Response({'received': True})
            events = []
            if not isinstance(payload.get('entry', []), list):
                raise ValueError
            for entry in payload.get('entry', []):
                for change in entry.get('changes', []):
                    if change.get('field') != 'leadgen':
                        continue
                    value = change.get('value', {})
                    page = str(value.get('page_id') or entry.get('id', ''))
                    form_id, lead_id = str(value.get('form_id', '')), str(value.get('leadgen_id', ''))
                    if str(entry.get('id', '')) != page or not all(v.isascii() and v.isdigit() and len(v) <= 100 for v in (page, form_id, lead_id)):
                        continue
                    events.append((page, form_id, lead_id))
        except (ValueError, TypeError, AttributeError):
            return Response({'detail': 'Malformed webhook.'}, status=400)
        try:
            with transaction.atomic():
                # Identity constraints serialize replays without holding connection locks.
                forms = list(IntakeForm.objects.filter(connection__origin='META', connection__enabled=True, enabled=True).select_related('connection'))
                connections = {c.pk: c for c in Connection.objects.filter(pk__in={f.connection_id for f in forms}).order_by('pk')}
                selected = {(f.page_id, f.external_id): f for f in forms}
                for page, form_id, lead_id in events:
                    form = selected.get((page, form_id))
                    if form and connections[form.connection_id].enabled:
                        form.connection = connections[form.connection_id]
                        accept(form, lead_id)
            return Response({'received': True})
        except DatabaseError:
            return Response({'detail': 'Intake is temporarily unavailable.'}, status=503)


class AdminViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAdmin]


class ConnectionViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, mixins.UpdateModelMixin, AdminViewSet):
    queryset = Connection.objects.order_by('id')
    serializer_class = ConnectionSerializer
    pagination_class = None

    def perform_create(self, serializer):
        connection = serializer.save()
        IntakeAudit.objects.create(connection=connection, actor=self.request.user, action='connection_created')

    def perform_update(self, serializer):
        with transaction.atomic():
            serializer.instance = Connection.objects.select_for_update().get(pk=serializer.instance.pk)
            connection = serializer.save()
            IntakeAudit.objects.create(connection=connection, actor=self.request.user, action='connection_updated')

    @extend_schema(request=None, responses=ConnectionSerializer)
    @action(detail=True, methods=['post'])
    def resume(self, request, pk=None):
        with transaction.atomic():
            connection = Connection.objects.select_for_update().get(pk=self.get_object().pk)
            connection.paused_reason = ''
            connection.save(update_fields=['paused_reason'])
            IntakeAudit.objects.create(connection=connection, actor=request.user, action='connection_resumed')
        return Response(self.get_serializer(connection).data)

    @extend_schema(responses=HealthSerializer)
    @action(detail=False, methods=['get'])
    def health(self, request):
        heartbeats = dict(Heartbeat.objects.values_list('name', 'seen_at'))
        result = []
        for connection in self.get_queryset():
            receipts = connection.submissions.all()
            pending = receipts.exclude(state__in=TERMINAL)
            oldest = pending.aggregate(oldest=Min('received_at'))['oldest']
            result.append({**self.get_serializer(connection).data, 'counts': dict(receipts.values('state').annotate(total=Count('pk')).values_list('state', 'total')),
                'oldest_pending_at': oldest, 'backlog_age_seconds': int((timezone.now() - oldest).total_seconds()) if oldest else 0,
                'forms': FormSerializer(connection.forms.all(), many=True).data})
        return Response({'enabled': settings.INTAKE_ENABLED, 'heartbeats': heartbeats, 'connections': result})


class FormViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, mixins.UpdateModelMixin, AdminViewSet):
    queryset = IntakeForm.objects.select_related('connection').order_by('id')
    serializer_class = FormSerializer
    pagination_class = None

    def perform_create(self, serializer):
        form = serializer.save()
        IntakeAudit.objects.create(connection=form.connection, actor=self.request.user, action='form_created')

    def perform_update(self, serializer):
        form = serializer.save()
        IntakeAudit.objects.create(connection=form.connection, actor=self.request.user, action='form_updated')


class MappingViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, AdminViewSet):
    serializer_class = MappingSerializer
    pagination_class = None

    def get_queryset(self):
        queryset = MappingVersion.objects.order_by('-created_at')
        if form := self.request.query_params.get('form'):
            queryset = queryset.filter(form=serializers.IntegerField(min_value=1).run_validation(form))
        if template := self.request.query_params.get('template_name'):
            queryset = queryset.filter(template_name=template)
        if self.request.query_params.get('excel') == 'true':
            queryset = queryset.filter(form__isnull=True)
        return queryset

    @extend_schema(request=PreviewSerializer, responses=MappingPreviewResponseSerializer)
    @action(detail=False, methods=['post'])
    def preview(self, request):
        serializer = PreviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        return Response(map_entries(data['entries'], data['rules'], data['excel']))

    @extend_schema(request=ReprocessSerializer, responses=QueuedResponseSerializer)
    @action(detail=True, methods=['post'])
    def reprocess(self, request, pk=None):
        mapping = self.get_object()
        serializer = ReprocessSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not mapping.form_id:
            raise ValidationError({'detail': 'Excel templates are applied through batch reparse.'})
        count = 0
        with transaction.atomic():
            for receipt in Submission.objects.select_for_update(no_key=True).filter(pk__in=serializer.validated_data['receipt_ids'], form=mapping.form).exclude(state__in=TERMINAL).order_by('pk'):
                if receipt.answers_expired or (receipt.lease_until and receipt.lease_until > timezone.now()):
                    continue
                receipt.mapping_version = mapping
                receipt.answers, ignored = sanitize_entries(receipt.answers, mapping.rules)
                receipt.ignored_labels = sorted(set(receipt.ignored_labels + ignored))
                result = map_entries(receipt.answers, mapping.rules, corrections=receipt.corrections)
                receipt.mapped_values = result['values']
                receipt.normalized_phone = normalize_phone(result['values'].get('phone'))
                receipt.state = Submission.State.RECEIVED
                receipt.attempts = 0
                receipt.next_attempt_at = timezone.now()
                receipt.lease_until = None
                receipt.lease_token = None
                receipt.save()
                record(receipt, 'mapping_reprocess', request.user)
                enqueue(receipt.pk)
                count += 1
        return Response({'queued': count})


class SubmissionViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, AdminViewSet):
    serializer_class = SubmissionSerializer

    def get_serializer_class(self):
        return SubmissionDetailSerializer if self.action in ('retrieve', 'resolve') else SubmissionSerializer

    def get_queryset(self):
        queryset = Submission.objects.select_related('connection', 'form').order_by('-received_at', '-id')
        for key, lookup in (('origin', 'connection__origin'), ('form', 'form_id'), ('state', 'state'), ('reason', 'review_reason')):
            if value := self.request.query_params.get(key):
                if key == 'form':
                    value = serializers.IntegerField(min_value=1).run_validation(value)
                queryset = queryset.filter(**{lookup: value})
        for key, lookup in (('date_from', 'received_at__date__gte'), ('date_to', 'received_at__date__lte')):
            if value := self.request.query_params.get(key):
                try:
                    parsed = parse_date(value)
                except ValueError:
                    parsed = None
                if parsed is None:
                    raise ValidationError({key: 'Use YYYY-MM-DD.'})
                queryset = queryset.filter(**{lookup: parsed})
        return queryset

    @extend_schema(request=ResolutionSerializer, responses=SubmissionDetailSerializer)
    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        receipt = self.get_object()
        serializer = ResolutionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        receipt = resolve(receipt.pk, data['action'], request.user, data.get('corrections'), data.get('lead_id'))
        return Response(SubmissionDetailSerializer(receipt).data)
