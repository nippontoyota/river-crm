from rest_framework.routers import DefaultRouter

from .views import UploadBatchViewSet

router = DefaultRouter()
router.register("uploads", UploadBatchViewSet, basename="upload")
urlpatterns = router.urls
