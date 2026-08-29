from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import FollowUpViewSet, LeadViewSet, SystemConfigView

router = DefaultRouter()
router.register("leads", LeadViewSet, basename="lead")
router.register("follow-ups", FollowUpViewSet, basename="follow-up")

urlpatterns = [
    path("system-config/", SystemConfigView.as_view(), name="system-config"),
] + router.urls
