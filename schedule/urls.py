from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import ReplacementRequestViewSet, ScheduleRuleViewSet, ScheduleViewSet


router = DefaultRouter()
router.register(r"replacements", ReplacementRequestViewSet, basename="replacement")
router.register(r"schedule/rules", ScheduleRuleViewSet, basename="schedulerule")
router.register(r"schedule", ScheduleViewSet, basename="schedule")


urlpatterns = [
    path("", include(router.urls)),
]

