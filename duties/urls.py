from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import DutyTypeViewSet, DutyInstanceViewSet


router = DefaultRouter()
router.register(r"duty-types", DutyTypeViewSet, basename="dutytype")
router.register(r"duties", DutyInstanceViewSet, basename="dutyinstance")


urlpatterns = [
    path("", include(router.urls)),
]

