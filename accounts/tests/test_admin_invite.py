from unittest.mock import patch

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.admin_invites import make_invite_token
from accounts.models import User
from accounts.services import create_admin_account
from cart.tests.helpers import make_user

PASSWORD = "BrandNewPassw0rd!y"


@override_settings(ADMIN_PORTAL_URL="http://admin.test")
class AdminInviteTests(TestCase):
    def setUp(self):
        self.sysadmin = make_user("sysadmin1", User.Role.SYSTEM_ADMIN)
        self.client = APIClient()
        self.url = reverse("admin-set-password")

    def make_invited_admin(self):
        with self.captureOnCommitCallbacks(execute=True):
            return create_admin_account(
                actor=self.sysadmin,
                username="newadmin",
                email="new.admin@example.com",
                first_name="New",
                last_name="Admin",
            )

    def set_password(self, token, password=PASSWORD):
        return self.client.post(
            self.url,
            {"token": token, "new_password": password, "confirm_password": password},
            format="json",
        )

    def test_creating_an_admin_sends_an_invite_without_a_password(self):
        admin = self.make_invited_admin()

        self.assertFalse(admin.has_usable_password())
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, ["new.admin@example.com"])
        self.assertEqual(email.subject, "Your Pawdigree admin account")
        self.assertIn("http://admin.test/set-password/?token=", email.body)

    def test_creating_through_the_api_needs_no_password(self):
        self.client.force_authenticate(user=self.sysadmin)

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                "/api/admin/administrators/",
                {
                    "first_name": "New",
                    "last_name": "Admin",
                    "email": "api.admin@example.com",
                },
                format="json",
            )

        self.assertEqual(response.status_code, 201)
        self.assertNotIn("password", response.data)
        self.assertEqual(len(mail.outbox), 1)

    def test_an_account_created_with_a_password_sends_no_invite(self):
        with self.captureOnCommitCallbacks(execute=True):
            create_admin_account(
                actor=self.sysadmin,
                username="withpw",
                email="with.pw@example.com",
                password=PASSWORD,
            )

        self.assertEqual(len(mail.outbox), 0)

    def test_the_admin_can_set_a_password_and_log_in(self):
        admin = self.make_invited_admin()

        response = self.set_password(make_invite_token(admin))

        self.assertEqual(response.status_code, 200)
        login = self.client.post(
            reverse("admin-login"),
            {"email": "new.admin@example.com", "password": PASSWORD},
            format="json",
        )
        self.assertEqual(login.status_code, 200)

    def test_an_invite_link_works_only_once(self):
        admin = self.make_invited_admin()
        token = make_invite_token(admin)

        self.assertEqual(self.set_password(token).status_code, 200)
        second = self.set_password(token, password="AnotherPassw0rd!z")

        self.assertEqual(second.status_code, 400)
        admin.refresh_from_db()
        self.assertTrue(admin.check_password(PASSWORD))

    def test_an_expired_link_is_refused(self):
        admin = self.make_invited_admin()
        token = make_invite_token(admin)

        with patch("accounts.admin_invites.INVITE_MAX_AGE", -1):
            response = self.set_password(token)

        self.assertEqual(response.status_code, 400)
        admin.refresh_from_db()
        self.assertFalse(admin.has_usable_password())

    def test_a_tampered_link_is_refused(self):
        admin = self.make_invited_admin()

        response = self.set_password(make_invite_token(admin) + "x")

        self.assertEqual(response.status_code, 400)

    def test_a_weak_password_is_refused_and_the_link_still_works(self):
        admin = self.make_invited_admin()
        token = make_invite_token(admin)

        weak = self.set_password(token, password="12345678")

        self.assertEqual(weak.status_code, 400)
        self.assertIn("new_password", weak.data)
        self.assertEqual(self.set_password(token).status_code, 200)

    def test_a_deactivated_admin_cannot_use_the_link(self):
        admin = self.make_invited_admin()
        admin.is_active = False
        admin.save()

        response = self.set_password(make_invite_token(admin))

        self.assertEqual(response.status_code, 400)

    def test_the_link_does_not_work_for_other_roles(self):
        customer = make_user("buyer1", User.Role.CUSTOMER)
        customer.set_unusable_password()
        customer.save()

        response = self.set_password(make_invite_token(customer))

        self.assertEqual(response.status_code, 400)

    def test_mismatched_confirmation_is_refused(self):
        admin = self.make_invited_admin()

        response = self.client.post(
            self.url,
            {"token": make_invite_token(admin), "new_password": PASSWORD, "confirm_password": "Different1!x"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("confirm_password", response.data)
        admin.refresh_from_db()
        self.assertFalse(admin.has_usable_password())
