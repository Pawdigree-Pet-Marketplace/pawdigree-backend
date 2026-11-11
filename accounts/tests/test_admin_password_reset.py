from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken

from accounts.models import User
from accounts.password_reset import PasswordResetTokenGeneratorService
from accounts.token_utils import SessionRefreshToken
from cart.tests.helpers import make_user

OLD = "OldPassw0rd!x"
NEW = "BrandNewPassw0rd!y"


@override_settings(ADMIN_PORTAL_URL="http://admin.test", FRONTEND_URL="http://public.test")
class AdminPasswordResetTests(TestCase):
    def setUp(self):
        self.admin = make_user("admin1", User.Role.ADMIN)
        self.admin.set_password(OLD)
        self.admin.save()
        self.client = APIClient()
        self.request_url = reverse("password-reset-request")
        self.confirm_url = reverse("password-reset-confirm-uid")

    def credentials(self, user=None):
        user = user or self.admin
        uid = urlsafe_base64_encode(force_bytes(self.admin.pk))
        token = PasswordResetTokenGeneratorService().generate_token(user)
        return uid, token

    def confirm(self, uid, token, new=NEW, confirm=NEW):
        return self.client.post(
            self.confirm_url,
            {"uid": uid, "token": token, "new_password": new, "confirm_password": confirm},
            format="json",
        )

    def test_an_admin_reset_email_links_to_the_admin_portal(self):
        response = self.client.post(
            self.request_url, {"email": self.admin.email}, format="json"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("http://admin.test/reset-password/", mail.outbox[0].body)

    def test_an_unknown_email_gets_the_same_answer(self):
        known = self.client.post(
            self.request_url, {"email": self.admin.email}, format="json"
        )
        unknown = self.client.post(
            self.request_url, {"email": "nobody@example.com"}, format="json"
        )

        self.assertEqual(unknown.status_code, known.status_code)
        self.assertEqual(unknown.data, known.data)
        self.assertEqual(len(mail.outbox), 1)

    def test_the_admin_can_reset_and_old_sessions_end(self):
        SessionRefreshToken.for_user(self.admin)
        uid, token = self.credentials()

        response = self.confirm(uid, token)

        self.assertEqual(response.status_code, 200)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.check_password(NEW))
        self.assertEqual(
            BlacklistedToken.objects.filter(token__user=self.admin).count(), 1
        )

    def test_a_reset_link_works_only_once(self):
        uid, token = self.credentials()

        self.assertEqual(self.confirm(uid, token).status_code, 200)
        second = self.confirm(uid, token, new="AnotherPassw0rd!z", confirm="AnotherPassw0rd!z")

        self.assertEqual(second.status_code, 400)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.check_password(NEW))

    def test_an_expired_link_is_refused(self):
        uid, token = self.credentials()

        with self.settings(PASSWORD_RESET_TIMEOUT=-1):
            response = self.confirm(uid, token)

        self.assertEqual(response.status_code, 400)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.check_password(OLD))

    def test_mismatched_passwords_are_refused(self):
        uid, token = self.credentials()

        response = self.confirm(uid, token, confirm="Different1!x")

        self.assertEqual(response.status_code, 400)
        self.assertIn("confirm_password", response.data)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.check_password(OLD))

    def test_an_invalid_token_is_refused(self):
        uid, _ = self.credentials()

        response = self.confirm(uid, "not-a-real-token")

        self.assertEqual(response.status_code, 400)

    def test_someone_elses_token_cannot_reset_an_admins_password(self):
        customer = make_user("buyer1", User.Role.CUSTOMER)
        uid, token = self.credentials(user=customer)

        response = self.confirm(uid, token)

        self.assertEqual(response.status_code, 400)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.check_password(OLD))
