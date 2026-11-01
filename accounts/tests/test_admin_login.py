from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User

PASSWORD = 'TestPass123!Secure'


class AdminLoginAPITests(APITestCase):
    def setUp(self):
        self.url = reverse('admin-login')
        self.admin = User.objects.create_user(
            username='admin1',
            email='admin1@example.com',
            password=PASSWORD,
            role=User.Role.ADMIN,
        )
        self.system_admin = User.objects.create_user(
            username='sysadmin1',
            email='sysadmin1@example.com',
            password=PASSWORD,
            role=User.Role.SYSTEM_ADMIN,
        )
        self.vendor = User.objects.create_user(
            username='vendor1',
            email='vendor1@example.com',
            password=PASSWORD,
            role=User.Role.VENDOR,
        )

    def login(self, email, password=PASSWORD):
        return self.client.post(
            self.url,
            {'email': email, 'password': password},
            format='json',
        )

    def test_admin_can_log_in(self):
        response = self.login('admin1@example.com')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

    def test_system_admin_can_log_in(self):
        response = self.login('sysadmin1@example.com')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)

    def test_vendor_cannot_use_admin_login(self):
        response = self.login('vendor1@example.com')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_wrong_password_is_rejected(self):
        response = self.login('admin1@example.com', 'wrong-password')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_response_includes_role(self):
        response = self.login('sysadmin1@example.com')
        self.assertEqual(response.data['role'], User.Role.SYSTEM_ADMIN)

        response = self.login('admin1@example.com')
        self.assertEqual(response.data['role'], User.Role.ADMIN)

    def test_inactive_admin_cannot_log_in(self):
        self.system_admin.is_active = False
        self.system_admin.save()

        response = self.login('sysadmin1@example.com')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertNotIn('access', response.data)
