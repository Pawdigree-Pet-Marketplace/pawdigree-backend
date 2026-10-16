from unittest.mock import patch

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.google_auth import GoogleTokenError
from accounts.models import User

GOOGLE_INFO = {
    'email': 'newcustomer@example.com',
    'email_verified': True,
    'given_name': 'New',
    'family_name': 'Customer',
}


class GoogleLoginAPITests(APITestCase):
    def setUp(self):
        self.url = reverse('google-login')

    def login(self):
        return self.client.post(
            self.url, {'credential': 'fake-token'}, format='json'
        )

    @patch('accounts.serializers.verify_google_token')
    def test_new_google_user_becomes_a_customer(self, mock_verify):
        mock_verify.return_value = GOOGLE_INFO

        response = self.login()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

        user = User.objects.get(email='newcustomer@example.com')
        self.assertEqual(user.role, User.Role.CUSTOMER)
        self.assertFalse(user.has_usable_password())

    @patch('accounts.serializers.verify_google_token')
    def test_existing_customer_is_not_duplicated(self, mock_verify):
        mock_verify.return_value = GOOGLE_INFO
        User.objects.create_user(
            username='existing',
            email='newcustomer@example.com',
            password='TestPass123!Secure',
            role=User.Role.CUSTOMER,
        )

        response = self.login()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            User.objects.filter(email='newcustomer@example.com').count(), 1
        )

    @patch('accounts.serializers.verify_google_token')
    def test_vendor_email_cannot_use_google_customer_login(self, mock_verify):
        mock_verify.return_value = GOOGLE_INFO
        User.objects.create_user(
            username='vendor1',
            email='newcustomer@example.com',
            password='TestPass123!Secure',
            role=User.Role.VENDOR,
        )

        response = self.login()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertNotIn('access', response.data)

    @patch('accounts.serializers.verify_google_token')
    def test_invalid_google_token_is_rejected(self, mock_verify):
        mock_verify.side_effect = GoogleTokenError('Invalid Google token.')

        response = self.login()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)