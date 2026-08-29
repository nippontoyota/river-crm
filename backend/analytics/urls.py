from django.urls import path

from .views import AdminAnalyticsView, MyAnalyticsExportView, MyAnalyticsView, ReceptionistAnalyticsView, SalesManagerAnalyticsExportView, SalesManagerAnalyticsView, SalesManagerPSFollowupsView

urlpatterns = [
    path("analytics/admin/", AdminAnalyticsView.as_view()),
    path("analytics/me/", MyAnalyticsView.as_view()),
    path("analytics/me/export/", MyAnalyticsExportView.as_view()),
    path("analytics/receptionist/", ReceptionistAnalyticsView.as_view()),
    path("analytics/sales-manager/", SalesManagerAnalyticsView.as_view()),
    path("analytics/sales-manager/ps-followups/", SalesManagerPSFollowupsView.as_view()),
    path("analytics/sales-manager/export/", SalesManagerAnalyticsExportView.as_view()),
]
