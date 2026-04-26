from datetime import date, time

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from duties.models import DutyType, DutyInstance
from schedule.models import ScheduleRule


class DutyInstanceValidationTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.commander = User.objects.create_user(
            username="duties_commander",
            password="pass",
            role=User.Role.COMMANDER,
            military_rank="Captain",
            platoon="Platoon-1",
        )
        self.soldier = User.objects.create_user(
            username="duties_soldier",
            password="pass",
            role=User.Role.SOLDIER,
            military_rank="Private",
            platoon="Platoon-1",
        )
        self.admin = User.objects.create_user(
            username="duties_admin",
            password="pass",
            role=User.Role.ADMIN,
            military_rank="Major",
            platoon="HQ",
        )
        self.duty_type = DutyType.objects.create(
            name="Guard",
            code="guard_test",
            required_soldiers=1,
            requires_special_skill=False,
        )

    def test_cannot_assign_non_soldier(self):
        self.client.force_authenticate(self.commander)
        response = self.client.post(
            "/api/v1/duties/",
            {
                "duty_type_id": self.duty_type.id,
                "date": date.today().isoformat(),
                "start_time": "10:00:00",
                "end_time": "12:00:00",
                "assigned_soldiers_ids": [self.admin.id],
                "status": "scheduled",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_assign_when_month_limit_reached(self):
        today = date.today()
        ScheduleRule.objects.create(
            name="Max one duty",
            rule_type=ScheduleRule.RuleType.MAX_DUTIES_PER_MONTH,
            value=1,
            is_active=True,
        )
        DutyInstance.objects.create(
            duty_type=self.duty_type,
            date=today.replace(day=1),
            start_time=time(10, 0),
            end_time=time(11, 0),
        ).assigned_soldiers.add(self.soldier)

        self.client.force_authenticate(self.commander)
        response = self.client.post(
            "/api/v1/duties/",
            {
                "duty_type_id": self.duty_type.id,
                "date": today.isoformat(),
                "start_time": "10:00:00",
                "end_time": "12:00:00",
                "assigned_soldiers_ids": [self.soldier.id],
                "status": "scheduled",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
