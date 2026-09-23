from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import FollowUpViewSet, LeadViewSet, SystemConfigView
from .call_center import CallCenterLeadViewSet, InteractionView, TicketView, CallbackView, CallCenterSummaryView

router = DefaultRouter()
router.register("leads", LeadViewSet, basename="lead")
router.register("follow-ups", FollowUpViewSet, basename="follow-up")

urlpatterns = [
    path("call-center/leads/<int:pk>/", CallCenterLeadViewSet.as_view({"get": "retrieve", "patch": "partial_update"})),
    path("call-center/leads/<int:pk>/tickets/", TicketView.as_view()),
    path("call-center/interactions/", InteractionView.as_view()),
    path("call-center/callbacks/", CallbackView.as_view()),
    path("call-center/summary/", CallCenterSummaryView.as_view()),
    path("system-config/", SystemConfigView.as_view(), name="system-config"),
] + router.urls
