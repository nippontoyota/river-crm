from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import ConnectionViewSet, FormViewSet, MappingViewSet, MetaWebhookView, SubmissionViewSet, WebsiteLeadView

router = DefaultRouter()
router.register('intake/connections', ConnectionViewSet, basename='intake-connection')
router.register('intake/forms', FormViewSet, basename='intake-form')
router.register('intake/mappings', MappingViewSet, basename='intake-mapping')
router.register('intake/submissions', SubmissionViewSet, basename='intake-submission')
urlpatterns = router.urls + [
    path('integrations/website/leads/', WebsiteLeadView.as_view(), name='website-intake'),
    path('integrations/meta/webhook/', MetaWebhookView.as_view(), name='meta-webhook'),
]
