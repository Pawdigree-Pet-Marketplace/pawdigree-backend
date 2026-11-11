from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken

from accounts.models import User
from accounts.token_utils import SessionRefreshToken
from cart.tests.helpers import make_user

OLD = "OldPassw0rd!x"
NEW = "BrandNewPassw0rd!y"


class ChangePasswordTests(TestCase):
    def setUp(self):
        self.user = make_user("buyer1", User.Role.CUSTOMER)
        self.user.set_password(OLD)
        self.user.save()
        self.client = APIClient()
        self.url = reverse("change-password")

    def change(self, current=OLD, new=NEW):
        return self.client.post(
            self.url,
            {"current_password": current, "new_password": new},
            format="json",
        )

    def test_user_can_change_their_password(self):
        self.client.force_authenticate(user=self.user)

        response = self.change()

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW))
        self.assertFalse(self.user.check_password(OLD))

    def test_refresh_tokens_are_revoked(self):
        SessionRefreshToken.for_user(self.user)
        self.client.force_authenticate(user=self.user)

        self.change()

        self.assertEqual(
            BlacklistedToken.objects.filter(token__user=self.user).count(), 1
        )

    def test_wrong_current_password_is_refused(self):
        self.client.force_authenticate(user=self.user)

        response = self.change(current="not-my-password")

        self.assertEqual(response.status_code, 400)
        self.assertIn("current_password", response.data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(OLD))

    def test_weak_new_password_is_refused(self):
        self.client.force_authenticate(user=self.user)

        response = self.change(new="12345678")

        self.assertEqual(response.status_code, 400)
        self.assertIn("new_password", response.data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(OLD))

    def test_new_password_must_differ_from_current(self):
        self.client.force_authenticate(user=self.user)

        response = self.change(new=OLD)

        self.assertEqual(response.status_code, 400)
        self.assertIn("new_password", response.data)

    def test_anonymous_users_are_refused(self):
        response = self.change()

        self.assertIn(response.status_code, (401, 403))

    def test_an_admin_can_change_their_password(self):
        admin = make_user("admin1", User.Role.ADMIN)
        admin.set_password(OLD)
        admin.save()
        self.client.force_authenticate(user=admin)

        response = self.change()

        self.assertEqual(response.status_code, 200)
        admin.refresh_from_db()
        self.assertTrue(admin.check_password(NEW))
