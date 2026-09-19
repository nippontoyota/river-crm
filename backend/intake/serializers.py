from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

from leads.serializers import validate_configured_source
from .mapping import FIELDS, validate_rules
from .models import Connection, IntakeAudit, IntakeForm, MappingVersion, Submission
from .services import matching_leads


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise serializers.ValidationError('Unknown request fields.')
        return super().to_internal_value(data)


class ConnectionSerializer(serializers.ModelSerializer):
    credentials_ready = serializers.SerializerMethodField()
    secret_ref = serializers.SlugField(write_only=True)

    class Meta:
        model = Connection
        fields = ['id', 'name', 'origin', 'source', 'secret_ref', 'activated_at', 'enabled', 'paused_reason', 'credentials_ready', 'last_receipt_at', 'last_import_at', 'created_at']
        read_only_fields = ['paused_reason', 'last_receipt_at', 'last_import_at', 'created_at']

    def get_credentials_ready(self, obj) -> bool:
        config = settings.INTAKE_SECRETS.get(obj.secret_ref, {})
        if obj.origin == 'WEBSITE':
            return bool(config.get('active'))
        return bool(config.get('access_token') and settings.META_GRAPH_VERSION and settings.META_APP_SECRET and settings.META_VERIFY_TOKEN)

    def validate_source(self, value):
        return validate_configured_source(value)

    def validate_secret_ref(self, value):
        if value not in settings.INTAKE_SECRETS:
            raise serializers.ValidationError('Ask your operator to configure this secret reference in the backend environment.')
        return value

    def validate(self, attrs):
        if self.instance and any(key in attrs and attrs[key] != getattr(self.instance, key) for key in ('origin', 'activated_at')):
            raise serializers.ValidationError('Origin and activation time are immutable. Create a new connection for a new import boundary.')
        origin = attrs.get('origin', getattr(self.instance, 'origin', None))
        secret_ref = attrs.get('secret_ref', getattr(self.instance, 'secret_ref', ''))
        if origin == 'WEBSITE':
            config = settings.INTAKE_SECRETS.get(secret_ref, {})
            tokens = {config.get(key) for key in ('active', 'retiring')} - {None, ''}
            for other in Connection.objects.filter(origin='WEBSITE').exclude(pk=getattr(self.instance, 'pk', None)):
                other_config = settings.INTAKE_SECRETS.get(other.secret_ref, {})
                if other.secret_ref == secret_ref or tokens.intersection({other_config.get(key) for key in ('active', 'retiring')}):
                    raise serializers.ValidationError({'secret_ref': 'Use dedicated credentials for each website connection.'})
        if attrs.get('enabled'):
            origin = attrs.get('origin', getattr(self.instance, 'origin', None))
            config = settings.INTAKE_SECRETS.get(attrs.get('secret_ref', getattr(self.instance, 'secret_ref', '')), {})
            if not config.get('active' if origin == 'WEBSITE' else 'access_token'):
                raise serializers.ValidationError('Configure backend credentials before activation.')
            if origin == 'META' and not (settings.META_GRAPH_VERSION and settings.META_APP_SECRET and settings.META_VERIFY_TOKEN):
                raise serializers.ValidationError('Configure a verified pinned Graph version, App Secret and verification token before activation.')
        return attrs


class FormSerializer(serializers.ModelSerializer):
    page_id = serializers.CharField(required=False, allow_blank=True, default='', max_length=100)
    fetch_status = serializers.ReadOnlyField()
    class Meta:
        model = IntakeForm
        fields = ['id', 'connection', 'name', 'external_id', 'page_id', 'enabled', 'activated_at', 'checkpoint', 'last_reconciled_at', 'reconcile_error', 'fetch_requested_at', 'fetch_status']
        read_only_fields = ['checkpoint', 'last_reconciled_at', 'reconcile_error', 'fetch_requested_at', 'fetch_status']

    def validate(self, attrs):
        connection = attrs.get('connection', getattr(self.instance, 'connection', None))
        if self.instance and any(key in attrs and attrs[key] != getattr(self.instance, key) for key in ('connection', 'external_id', 'page_id', 'activated_at')):
            raise serializers.ValidationError('Form identifiers and activation time are immutable.')
        page = attrs.get('page_id', getattr(self.instance, 'page_id', ''))
        external = attrs.get('external_id', getattr(self.instance, 'external_id', ''))
        if ':' in external:
            raise serializers.ValidationError({'external_id': 'Form identifiers cannot contain a colon.'})
        if connection.origin == 'META' and not all(value.isascii() and value.isdigit() for value in (page, external)):
            raise serializers.ValidationError('Meta forms require numeric Page and Form IDs.')
        if connection.origin == 'WEBSITE' and page:
            raise serializers.ValidationError({'page_id': 'Website forms do not use a Page ID.'})
        return attrs


class MappingSerializer(serializers.ModelSerializer):
    class Meta:
        model = MappingVersion
        fields = ['id', 'form', 'template_name', 'version', 'rules', 'created_by', 'created_at']
        read_only_fields = ['id', 'version', 'created_by', 'created_at']
        validators = []  # Version allocation is serialized under the scope lock below.

    def validate(self, attrs):
        if bool(attrs.get('form')) == bool(attrs.get('template_name')):
            raise serializers.ValidationError('Choose a form or a named Excel template.')
        attrs['rules'] = validate_rules(attrs.get('rules', {}), excel=not attrs.get('form'))
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        form = validated_data.get('form')
        if form:
            IntakeForm.objects.select_for_update().get(pk=form.pk)
            versions = MappingVersion.objects.filter(form=form)
        else:
            # One lock per named template also protects the first version.
            from leads.phone_lock import lock_phones
            lock_phones('template:' + validated_data['template_name'])
            versions = MappingVersion.objects.filter(form__isnull=True, template_name=validated_data['template_name'])
        version = (versions.aggregate(value=Max('version'))['value'] or 0) + 1
        mapping = MappingVersion.objects.create(**validated_data, version=version, created_by=self.context['request'].user)
        IntakeAudit.objects.create(mapping_version=mapping, connection=form.connection if form else None, actor=self.context['request'].user, action='mapping_created')
        return mapping


class EntrySerializer(StrictSerializer):
    id = serializers.CharField(max_length=200)
    label = serializers.CharField(max_length=160, allow_blank=True)
    value = serializers.JSONField(required=False, default='')

    def validate_value(self, value):
        if value is not None and not isinstance(value, (str, int, float)):
            raise serializers.ValidationError('Use a scalar answer.')
        return value


class PreviewSerializer(StrictSerializer):
    entries = EntrySerializer(many=True)
    rules = serializers.JSONField(default=dict)
    excel = serializers.BooleanField(default=False)

    def validate(self, attrs):
        if len(attrs['entries']) > 100 or len({e['id'] for e in attrs['entries']}) != len(attrs['entries']):
            raise serializers.ValidationError('Use at most 100 entries with distinct IDs.')
        attrs['rules'] = validate_rules(attrs['rules'], attrs['excel'])
        return attrs


class ResolutionSerializer(StrictSerializer):
    action = serializers.ChoiceField(choices=['link', 'create_separately', 'dismiss', 'correct', 'retry'])
    lead_id = serializers.IntegerField(required=False)
    corrections = serializers.JSONField(required=False)


class ReprocessSerializer(StrictSerializer):
    receipt_ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=False, max_length=500)


class AuditSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source='actor.history_display_name', read_only=True, default='System')

    class Meta:
        model = IntakeAudit
        fields = ['id', 'action', 'actor', 'actor_name', 'created_at', 'lead', 'mapping_version']


class SubmissionSerializer(serializers.ModelSerializer):
    origin = serializers.CharField(source='connection.origin', read_only=True)
    form_name = serializers.CharField(source='form.name', read_only=True)

    class Meta:
        model = Submission
        fields = ['id', 'connection', 'form', 'origin', 'form_name', 'external_id', 'source', 'state', 'received_at', 'submitted_at', 'resolved_at', 'mapped_values', 'errors', 'review_reason', 'mapping_version', 'answers_expired', 'lead', 'blocked_by', 'attempts', 'next_attempt_at', 'attribution', 'campaign_name']
        read_only_fields = fields


class SubmissionDetailSerializer(SubmissionSerializer):
    history = AuditSerializer(many=True, read_only=True)
    matching_leads = serializers.SerializerMethodField()
    pending_receipts = serializers.SerializerMethodField()

    class Meta(SubmissionSerializer.Meta):
        fields = SubmissionSerializer.Meta.fields + ['answers', 'ignored_labels', 'history', 'matching_leads', 'pending_receipts']
        read_only_fields = fields

    @extend_schema_field({'type': 'array', 'items': {'type': 'object', 'properties': {'id': {'type': 'integer'}, 'name': {'type': 'string'}, 'phone': {'type': 'string'}, 'status': {'type': 'string'}, 'assigned_so': {'type': 'integer', 'nullable': True}, 'assigned_ps': {'type': 'integer', 'nullable': True}}}})
    def get_matching_leads(self, obj):
        return list(matching_leads(obj.normalized_phone).values('id', 'name', 'phone', 'status', 'assigned_so', 'assigned_ps')[:50])

    @extend_schema_field({'type': 'array', 'items': {'type': 'object', 'properties': {'id': {'type': 'string', 'format': 'uuid'}, 'state': {'type': 'string'}, 'received_at': {'type': 'string', 'format': 'date-time'}}}})
    def get_pending_receipts(self, obj):
        from .services import UNRESOLVED
        if not obj.normalized_phone:
            return []
        return list(Submission.objects.filter(normalized_phone=obj.normalized_phone, state__in=UNRESOLVED).exclude(pk=obj.pk).order_by('received_at').values('id', 'state', 'received_at')[:50])


class WebsiteEnvelopeSerializer(StrictSerializer):
    submission_id = serializers.CharField(max_length=160)
    form_id = serializers.CharField(max_length=160)
    submitted_at = serializers.DateTimeField(required=False)
    fields = serializers.DictField(child=serializers.JSONField())
    attribution = serializers.DictField(child=serializers.CharField(max_length=500, allow_blank=True), required=False)


class ReceiptResponseSerializer(serializers.Serializer):
    receipt_id = serializers.UUIDField()
    state = serializers.ChoiceField(choices=Submission.State.choices)


class MappingPreviewEntrySerializer(serializers.Serializer):
    id = serializers.CharField()
    label = serializers.CharField()
    sample = serializers.CharField()
    destination = serializers.CharField()


class MappingPreviewResponseSerializer(serializers.Serializer):
    values = serializers.DictField(child=serializers.CharField(allow_null=True, allow_blank=True))
    errors = serializers.DictField(child=serializers.CharField())
    entries = MappingPreviewEntrySerializer(many=True)


class QueuedResponseSerializer(serializers.Serializer):
    queued = serializers.IntegerField()


class HealthConnectionSerializer(ConnectionSerializer):
    counts = serializers.DictField(child=serializers.IntegerField())
    oldest_pending_at = serializers.DateTimeField(allow_null=True)
    backlog_age_seconds = serializers.IntegerField()
    forms = FormSerializer(many=True)

    class Meta(ConnectionSerializer.Meta):
        fields = ConnectionSerializer.Meta.fields + ['counts', 'oldest_pending_at', 'backlog_age_seconds', 'forms']


class HealthSerializer(serializers.Serializer):
    enabled = serializers.BooleanField()
    execution_mode = serializers.ChoiceField(choices=['celery', 'database'])
    heartbeats = serializers.DictField(child=serializers.DateTimeField())
    connections = HealthConnectionSerializer(many=True)


class ErrorResponseSerializer(serializers.Serializer):
    detail = serializers.CharField()


class WebhookResponseSerializer(serializers.Serializer):
    received = serializers.BooleanField()
