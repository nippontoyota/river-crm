from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import ComplaintAnalyticsView, ComplaintViewSet

router = DefaultRouter()
router.register("complaints", ComplaintViewSet, basename="complaint")

urlpatterns = [
    path("complaints/analytics/", ComplaintAnalyticsView.as_view(), name="complaint-analytics"),
] + router.urls
