from django.urls import path
from .views import CEOComplaintDetailView, CEOExportView, CEOHistoryView, CEOLeadDetailView, CEOOptionsView, CEOReportView, FinanceEntriesView, FinanceMaintenanceView, TargetHistoryView, TargetMaintenanceView

urlpatterns = [
    path("ceo/options/", CEOOptionsView.as_view()),
    path("ceo/leads/<int:pk>/", CEOLeadDetailView.as_view()),
    path("ceo/complaints/<int:pk>/", CEOComplaintDetailView.as_view()),
    path("ceo/finance/<int:pk>/entries/", FinanceEntriesView.as_view()),
    path("ceo/targets/<int:pk>/history/", TargetHistoryView.as_view()),
    path("ceo/<str:entity>/<int:pk>/history/", CEOHistoryView.as_view()),
    path("ceo/export/<str:section>/", CEOExportView.as_view()),
    path("ceo/<str:section>/", CEOReportView.as_view()),
    path("management/targets/", TargetMaintenanceView.as_view()),
    path("management/finance/", FinanceMaintenanceView.as_view()),
]
