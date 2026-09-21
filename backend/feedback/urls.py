from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import FeedbackViewSet
from .requests import FeedbackRequestViewSet

router = DefaultRouter()
router.register("feedback-requests", FeedbackRequestViewSet, basename="feedback-request")
router.register("feedback", FeedbackViewSet, basename="feedback")
urlpatterns = [
    path("ceo/feedback/", FeedbackViewSet.as_view({"get": "summary"})),
    path("ceo/export/feedback/", FeedbackViewSet.as_view({"get": "export"})),
] + router.urls
