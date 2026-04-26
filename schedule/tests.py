from datetime import date, timedelta, time

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from duties.models import DutyType, DutyInstance
from .models import ScheduleRule, ReplacementRequest
from .services import generate_schedule, is_soldier_available


class ScheduleServicesTests(TestCase):
    """Basic tests for schedule generation and availability."""

    def setUp(self):
        User = get_user_model()
        self.soldier = User.objects.create_user(
            username="soldier1",
            password="pass",
            role=User.Role.SOLDIER,
            military_rank="Private",
            platoon="Platoon-1",
        )
        self.duty_type = DutyType.objects.create(
            name="Test duty",
            code="test",
            required_soldiers=1,
            requires_special_skill=False,
        )

    def test_is_soldier_available_basic(self):
        d = date.today()
        self.assertTrue(is_soldier_available(self.soldier, d))

    def test_max_duties_per_month_rule(self):
        d = date.today().replace(day=1)
        ScheduleRule.objects.create(
            name="Max 1 per month",
            rule_type=ScheduleRule.RuleType.MAX_DUTIES_PER_MONTH,
            value=1,
            is_active=True,
        )
        DutyInstance.objects.create(
            duty_type=self.duty_type,
            date=d,
            start_time=None,
            end_time=None,
        ).assigned_soldiers.add(self.soldier)
        self.assertFalse(is_soldier_available(self.soldier, d + timedelta(days=1)))

    def test_generate_schedule_creates_instances(self):
        start = date.today()
        end = start + timedelta(days=2)
        result = generate_schedule(start, end, [self.duty_type])
        self.assertIn("assignments", result)
        self.assertGreaterEqual(len(result["assignments"]), 1)


class ScheduleApiTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user(
            username="schedule_admin",
            password="pass",
            role=User.Role.ADMIN,
            military_rank="Major",
            platoon="HQ",
        )
        self.commander = User.objects.create_user(
            username="schedule_commander",
            password="pass",
            role=User.Role.COMMANDER,
            military_rank="Captain",
            platoon="Platoon-1",
        )
        self.requester = User.objects.create_user(
            username="schedule_requester",
            password="pass",
            role=User.Role.SOLDIER,
            military_rank="Private",
            platoon="Platoon-1",
        )
        self.replacement = User.objects.create_user(
            username="schedule_replacement",
            password="pass",
            role=User.Role.SOLDIER,
            military_rank="Private",
            platoon="Platoon-1",
        )
        self.duty_type = DutyType.objects.create(
            name="Schedule test duty",
            code="schedule_test",
            required_soldiers=1,
            requires_special_skill=False,
        )

    def test_commander_cannot_create_rule(self):
        self.client.force_authenticate(self.commander)
        response = self.client.post(
            "/api/v1/schedule/rules/",
            {
                "name": "Forbidden create",
                "rule_type": ScheduleRule.RuleType.MAX_DUTIES_PER_MONTH,
                "value": 5,
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_commander_cannot_change_rule_type(self):
        rule = ScheduleRule.objects.create(
            name="Rule",
            rule_type=ScheduleRule.RuleType.MAX_DUTIES_PER_MONTH,
            value=5,
            is_active=True,
        )
        self.client.force_authenticate(self.commander)
        response = self.client.patch(
            f"/api/v1/schedule/rules/{rule.id}/",
            {"rule_type": ScheduleRule.RuleType.WEEKEND_ROTATION},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_commander_can_put_rule_without_rule_type(self):
        rule = ScheduleRule.objects.create(
            name="Rule before",
            rule_type=ScheduleRule.RuleType.MAX_DUTIES_PER_MONTH,
            value=3,
            is_active=True,
        )
        self.client.force_authenticate(self.commander)
        response = self.client.put(
            f"/api/v1/schedule/rules/{rule.id}/",
            {"name": "Rule after", "value": 10, "is_active": True},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rule.refresh_from_db()
        self.assertEqual(rule.name, "Rule after")
        self.assertEqual(rule.value, 10)
        self.assertEqual(rule.rule_type, ScheduleRule.RuleType.MAX_DUTIES_PER_MONTH)

    def test_replacement_can_respond_with_post(self):
        duty = DutyInstance.objects.create(
            duty_type=self.duty_type,
            date=date.today() + timedelta(days=3),
            start_time=time(8, 0),
            end_time=time(10, 0),
        )
        duty.assigned_soldiers.add(self.requester)
        request_obj = ReplacementRequest.objects.create(
            duty_instance=duty,
            requester=self.requester,
            requested_replacement=self.replacement,
            reason="test",
        )

        self.client.force_authenticate(self.replacement)
        response = self.client.post(
            f"/api/v1/replacements/{request_obj.id}/respond/",
            {"action": "approve"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_replacement_can_respond_with_put(self):
        duty = DutyInstance.objects.create(
            duty_type=self.duty_type,
            date=date.today() + timedelta(days=4),
            start_time=time(8, 0),
            end_time=time(10, 0),
        )
        duty.assigned_soldiers.add(self.requester)
        request_obj = ReplacementRequest.objects.create(
            duty_instance=duty,
            requester=self.requester,
            requested_replacement=self.replacement,
            reason="test put",
        )

        self.client.force_authenticate(self.replacement)
        response = self.client.put(
            f"/api/v1/replacements/{request_obj.id}/respond/",
            {"action": "approve"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

