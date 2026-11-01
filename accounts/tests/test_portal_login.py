from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User
from businesses.models import Business

PASSWORD = 'StrongPass123!'


def make_user(role, email):
    return User.objects.create_user(
        username=email.split('@')[0],
        email=email,
        password=PASSWORD,
        role=role,
        is_email_verified=True,
    )


class LoginTests(TestCase):
    def test_correct_portal_still_works(self):
        customer = make_user(User.Role.CUSTOMER, 'cust@example.com')

        res = APIClient().post(
            reverse('customer-login'),
            {'email': customer.email, 'password': PASSWORD},
            format='json',
        )

        self.assertEqual(res.status_code, 200)
        self.assertIn('access', res.data)


class CurrentUserTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.customer = make_user(User.Role.CUSTOMER, 'cust@example.com')
        self.vendor = make_user(User.Role.VENDOR, 'vend@example.com')

    def test_requires_authentication(self):
        res = self.client.get(reverse('current-user'))
        self.assertEqual(res.status_code, 401)

    def test_customer_gets_role_and_no_businesses(self):
        self.client.force_authenticate(self.customer)
        res = self.client.get(reverse('current-user'))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['role'], 'CUSTOMER')
        self.assertTrue(res.data['is_email_verified'])
        self.assertEqual(res.data['businesses'], [])

    def test_vendor_gets_business_status(self):
        Business.objects.create(
            vendor=self.vendor,
            name='Happy Paws',
            description='Pets',
            contact='+256700000000',
            email='shop@example.com',
            address='Plot 1',
            city_district='Kampala',
        )
        self.client.force_authenticate(self.vendor)
        res = self.client.get(reverse('current-user'))
        self.assertEqual(res.data['businesses'][0]['name'], 'Happy Paws')
        self.assertEqual(
            res.data['businesses'][0]['verification_status'], 'draft'
        )


class GooglePasswordTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def google_login(self, email):
        with patch('accounts.serializers.verify_google_token') as verify:
            verify.return_value = {'email': email, 'email_verified': True}
            return self.client.post(
                reverse('google-login'), {'credential': 'x'}, format='json'
            )

    def test_verified_customer_keeps_password(self):
        user = make_user(User.Role.CUSTOMER, 'cust@example.com')
        res = self.google_login(user.email)
        self.assertEqual(res.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.has_usable_password())

    def test_unverified_account_password_is_wiped(self):
        user = make_user(User.Role.CUSTOMER, 'cust@example.com')
        user.is_email_verified = False
        user.save(update_fields=['is_email_verified'])

        res = self.google_login(user.email)
        self.assertEqual(res.status_code, 200)
        user.refresh_from_db()
        self.assertFalse(user.has_usable_password())
        self.assertTrue(user.is_email_verified)