from datetime import date, timedelta, time

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from duties.models import DutyType, DutyInstance
from .models import ScheduleRule, ReplacementRequest, ScheduleTemplate
from .services import (
    generate_from_template,
    generate_schedule,
    is_soldier_available,
    users_same_platoon,
)


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
        self.soldier2 = User.objects.create_user(
            username="soldier2",
            password="pass",
            role=User.Role.SOLDIER,
            military_rank="Private",
            platoon="Platoon-1",
        )
        self.duty_type = DutyType.objects.create(
            name="Test duty",
            code="test",
            required_soldiers=2,
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

    def test_generate_schedule_rejects_past_period(self):
        start = date.today() - timedelta(days=7)
        end = date.today() - timedelta(days=1)
        with self.assertRaises(ValueError):
            generate_schedule(start, end, [self.duty_type])

    def test_generate_from_template_creates_only_configured_days(self):
        start = date.today() + timedelta(days=1)
        # From tomorrow for 7 days to include all weekdays.
        end = start + timedelta(days=6)
        template = ScheduleTemplate.objects.create(
            name="Week template",
            rules={str(start.weekday()): [self.duty_type.id]},
        )
        created = generate_from_template(start, end, template)
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0].duty_type_id, self.duty_type.id)
        self.assertEqual(created[0].assigned_soldiers.count(), 2)

    def test_users_same_platoon_case_insensitive(self):
        User = get_user_model()
        a = User.objects.create_user(
            username="platoon_a",
            password="pass",
            role=User.Role.SOLDIER,
            military_rank="Private",
            platoon="  Alpha  ",
        )
        b = User.objects.create_user(
            username="platoon_b",
            password="pass",
            role=User.Role.SOLDIER,
            military_rank="Private",
            platoon="alpha",
        )
        self.assertTrue(users_same_platoon(a, b))
        self.assertFalse(users_same_platoon(a, self.soldier))


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
            start_time=time(8, 0),
            end_time=time(10, 0),
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

    def test_replacement_request_rejects_other_platoon(self):
        User = get_user_model()
        other_platoon = User.objects.create_user(
            username="soldier_platoon_2",
            password="pass",
            role=User.Role.SOLDIER,
            military_rank="Private",
            platoon="Platoon-2",
        )
        duty = DutyInstance.objects.create(
            duty_type=self.duty_type,
            date=date.today() + timedelta(days=10),
            start_time=time(8, 0),
            end_time=time(10, 0),
        )
        duty.assigned_soldiers.add(self.requester)

        self.client.force_authenticate(self.requester)
        response = self.client.post(
            "/api/v1/replacements/request/",
            {
                "duty_instance": duty.id,
                "requested_replacement": other_platoon.id,
                "reason": "Cross-platoon should fail",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_replacement_request_rejects_commander_as_target(self):
        duty = DutyInstance.objects.create(
            duty_type=self.duty_type,
            date=date.today() + timedelta(days=11),
            start_time=time(8, 0),
            end_time=time(10, 0),
        )
        duty.assigned_soldiers.add(self.requester)

        self.client.force_authenticate(self.requester)
        response = self.client.post(
            "/api/v1/replacements/request/",
            {
                "duty_instance": duty.id,
                "requested_replacement": self.commander.id,
                "reason": "Invalid target",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_replacement_request_rejects_admin_as_target_same_platoon(self):
        User = get_user_model()
        admin_p1 = User.objects.create_user(
            username="admin_in_platoon_1",
            password="pass",
            role=User.Role.ADMIN,
            military_rank="Major",
            platoon="Platoon-1",
        )
        duty = DutyInstance.objects.create(
            duty_type=self.duty_type,
            date=date.today() + timedelta(days=12),
            start_time=time(8, 0),
            end_time=time(10, 0),
        )
        duty.assigned_soldiers.add(self.requester)

        self.client.force_authenticate(self.requester)
        response = self.client.post(
            "/api/v1/replacements/request/",
            {
                "duty_instance": duty.id,
                "requested_replacement": admin_p1.id,
                "reason": "Admin cannot replace",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_replacement_respond_with_post_is_not_allowed(self):
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
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

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
        request_obj.refresh_from_db()
        duty.refresh_from_db()
        self.assertEqual(
            request_obj.status, ReplacementRequest.Status.PENDING_COMMANDER
        )
        self.assertIn(self.requester, duty.assigned_soldiers.all())
        self.assertNotIn(self.replacement, duty.assigned_soldiers.all())

        self.client.force_authenticate(self.commander)
        response2 = self.client.put(
            f"/api/v1/replacements/{request_obj.id}/commander-review/",
            {"action": "approve"},
            format="json",
        )
        self.assertEqual(response2.status_code, status.HTTP_200_OK)
        duty.refresh_from_db()
        request_obj.refresh_from_db()
        self.assertEqual(
            request_obj.status, ReplacementRequest.Status.APPROVED
        )
        self.assertNotIn(self.requester, duty.assigned_soldiers.all())
        self.assertIn(self.replacement, duty.assigned_soldiers.all())

    def test_replacement_create_without_request_route_is_not_allowed(self):
        duty = DutyInstance.objects.create(
            duty_type=self.duty_type,
            date=date.today() + timedelta(days=5),
            start_time=time(8, 0),
            end_time=time(10, 0),
        )
        duty.assigned_soldiers.add(self.requester)

        self.client.force_authenticate(self.requester)
        response = self.client.post(
            "/api/v1/replacements/",
            {
                "duty_instance": duty.id,
                "requested_replacement": self.replacement.id,
                "reason": "raw create should be blocked",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_replacement_patch_is_not_allowed(self):
        duty = DutyInstance.objects.create(
            duty_type=self.duty_type,
            date=date.today() + timedelta(days=6),
            start_time=time(8, 0),
            end_time=time(10, 0),
        )
        duty.assigned_soldiers.add(self.requester)
        request_obj = ReplacementRequest.objects.create(
            duty_instance=duty,
            requester=self.requester,
            requested_replacement=self.replacement,
            reason="initial",
        )

        self.client.force_authenticate(self.requester)
        response = self.client.patch(
            f"/api/v1/replacements/{request_obj.id}/",
            {"reason": "edited"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_generate_from_template_uses_default_template(self):
        self.client.force_authenticate(self.commander)
        target_day = (date.today() + timedelta(days=1)).weekday()
        ScheduleTemplate.objects.create(
            name="Default template",
            is_default=True,
            rules={str(target_day): [self.duty_type.id]},
        )
        response = self.client.post(
            "/api/v1/schedule/generate-from-template/",
            {
                "start_date": (date.today() + timedelta(days=1)).isoformat(),
                "end_date": (date.today() + timedelta(days=1)).isoformat(),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["created_count"], 1)

