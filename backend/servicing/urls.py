from rest_framework.routers import DefaultRouter
from .views import ServiceRequestViewSet, VehicleViewSet

router = DefaultRouter()
router.register("vehicles", VehicleViewSet, basename="vehicle")
router.register("service-requests", ServiceRequestViewSet, basename="service-request")
urlpatterns = router.urls
