from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import CREViewSet, CsrfView, LoginView, LogoutView, MeView, RefreshView, SalesOfficerViewSet, UserLifecycleHistoryView, UserViewSet

router = DefaultRouter()
router.register("cre-users", CREViewSet, basename="cre-user")
router.register("sales-officers", SalesOfficerViewSet, basename="sales-officer")
router.register("users", UserViewSet, basename="user")

urlpatterns = [
    path("login/", LoginView.as_view()), path("refresh/", RefreshView.as_view()),
    path("logout/", LogoutView.as_view()), path("me/", MeView.as_view()), path("csrf/", CsrfView.as_view()),
    path("users/<int:user_id>/lifecycle-history/", UserLifecycleHistoryView.as_view()),
] + router.urls
