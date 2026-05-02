from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, RequestFactory
from rest_framework import status
from rest_framework.test import APITestCase

from .permissions import IsAdmin, IsCommander, IsSoldier


class PermissionTests(TestCase):
    """Basic tests for custom role permissions."""

    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user(
            username="admin",
            password="pass",
            role=User.Role.ADMIN,
            military_rank="Major",
            platoon="HQ",
        )
        self.commander = User.objects.create_user(
            username="commander",
            password="pass",
            role=User.Role.COMMANDER,
            military_rank="Captain",
            platoon="Platoon-1",
        )
        self.soldier = User.objects.create_user(
            username="soldier",
            password="pass",
            role=User.Role.SOLDIER,
            military_rank="Private",
            platoon="Platoon-1",
        )
        self.factory = RequestFactory()

    def test_is_admin(self):
        request = self.factory.get("/")
        request.user = self.admin
        self.assertTrue(IsAdmin().has_permission(request, None))

    def test_is_commander(self):
        request = self.factory.get("/")
        request.user = self.commander
        self.assertTrue(IsCommander().has_permission(request, None))

    def test_is_soldier(self):
        request = self.factory.get("/")
        request.user = self.soldier
        self.assertTrue(IsSoldier().has_permission(request, None))


class UserApiPermissionTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.commander = User.objects.create_user(
            username="commander_api",
            password="pass",
            role=User.Role.COMMANDER,
            military_rank="Captain",
            platoon="Platoon-1",
        )
        self.soldier = User.objects.create_user(
            username="soldier_api",
            password="pass",
            role=User.Role.SOLDIER,
            military_rank="Private",
            platoon="Platoon-1",
            email="old@example.com",
            phone_number="123",
        )

    def test_soldier_cannot_create_user(self):
        self.client.force_authenticate(self.soldier)
        response = self.client.post(
            "/api/v1/users/",
            {
                "username": "new_soldier",
                "password": "pass123",
                "role": "soldier",
                "military_rank": "Private",
                "platoon": "Platoon-1",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_soldier_can_update_only_own_email(self):
        self.client.force_authenticate(self.soldier)
        response = self.client.patch(
            f"/api/v1/users/{self.soldier.id}/",
            {"email": "new@example.com"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.soldier.refresh_from_db()
        self.assertEqual(self.soldier.email, "new@example.com")

    def test_status_until_cannot_be_in_past(self):
        self.client.force_authenticate(self.commander)
        response = self.client.patch(
            f"/api/v1/users/{self.soldier.id}/",
            {"status_until": (date.today() - timedelta(days=1)).isoformat()},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_phone_must_match_russian_format(self):
        self.client.force_authenticate(self.commander)
        response = self.client.patch(
            f"/api/v1/users/{self.soldier.id}/",
            {"phone_number": "89991234567"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_email_must_have_dot_after_at(self):
        self.client.force_authenticate(self.commander)
        response = self.client.patch(
            f"/api/v1/users/{self.soldier.id}/",
            {"email": "user@localhost"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

