from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User
from cart.tests.helpers import make_user

NEW = "BrandNewPassw0rd!y"


class SetPasswordTests(TestCase):
    def setUp(self):
        # A user created through Google has no usable password.
        self.user = make_user("googlevendor", User.Role.VENDOR)
        self.user.set_unusable_password()
        self.user.save()
        self.client = APIClient()
        self.url = reverse("set-password")

    def set_password(self, new=NEW, confirm=None):
        return self.client.post(
            self.url,
            {"new_password": new, "confirm_password": confirm or new},
            format="json",
        )

    def test_user_without_a_password_can_set_one(self):
        self.client.force_authenticate(user=self.user)

        response = self.set_password()

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.has_usable_password())
        self.assertTrue(self.user.check_password(NEW))

    def test_user_with_a_password_must_use_change_password(self):
        self.user.set_password("OldPassw0rd!x")
        self.user.save()
        self.client.force_authenticate(user=self.user)

        response = self.set_password()

        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("OldPassw0rd!x"))
        self.assertFalse(self.user.check_password(NEW))

    def test_passwords_must_match(self):
        self.client.force_authenticate(user=self.user)

        response = self.set_password(confirm="SomethingElse1!z")

        self.assertEqual(response.status_code, 400)
        self.assertIn("confirm_password", response.json())
        self.user.refresh_from_db()
        self.assertFalse(self.user.has_usable_password())

    def test_weak_password_is_rejected(self):
        self.client.force_authenticate(user=self.user)

        response = self.set_password(new="12345678")

        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertFalse(self.user.has_usable_password())

    def test_login_is_required(self):
        response = self.set_password()

        self.assertEqual(response.status_code, 401)


class CurrentUserHasPasswordTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = reverse("current-user")

    def test_google_account_reports_no_password(self):
        user = make_user("googlevendor", User.Role.VENDOR)
        user.set_unusable_password()
        user.save()
        self.client.force_authenticate(user=user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertIs(response.json()["has_password"], False)

    def test_normal_account_reports_a_password(self):
        user = make_user("buyer1", User.Role.CUSTOMER)
        user.set_password("OldPassw0rd!x")
        user.save()
        self.client.force_authenticate(user=user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertIs(response.json()["has_password"], True)