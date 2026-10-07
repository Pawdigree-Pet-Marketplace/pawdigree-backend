from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User


class CustomerRegistrationTests(APITestCase):
    url = reverse('customer-register')

    def test_customer_can_register(self):
        payload = {
            'username': 'newcustomer',
            'first_name': 'Test',
            'last_name': 'Customer',
            'email': 'newcustomer@example.com',
            'phone': '0700000000',
            'password': 'SecurePass123',
        }

        response = self.client.post(self.url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        user = User.objects.get(email=payload['email'])

        self.assertEqual(user.role, User.Role.CUSTOMER)
        self.assertTrue(user.check_password(payload['password']))

    def test_customer_cannot_register_with_duplicate_email(self):
        User.objects.create_user(
            username='existingcustomer',
            email='existing@example.com',
            password='SecurePass123',
            role=User.Role.CUSTOMER,
        )

        payload = {
            'username': 'anothercustomer',
            'first_name': 'Another',
            'last_name': 'Customer',
            'email': 'existing@example.com',
            'phone': '0700000001',
            'password': 'SecurePass123',
        }

        response = self.client.post(self.url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.data)

class VendorRegistrationTests(APITestCase):
    url = reverse('vendor-register')

    def test_vendor_can_register(self):
        payload = {
            'username': 'newvendor',
            'first_name': 'Test',
            'last_name': 'Vendor',
            'email': 'newvendor@example.com',
            'phone': '0700000002',
            'password': 'SecurePass123',
        }

        response = self.client.post(self.url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        user = User.objects.get(email=payload['email'])

        self.assertEqual(user.role, User.Role.VENDOR)
        self.assertTrue(user.check_password(payload['password']))

    def test_vendor_cannot_register_with_duplicate_email(self):
        User.objects.create_user(
            username='existingvendor',
            email='existingvendor@example.com',
            password='SecurePass123',
            role=User.Role.VENDOR,
        )

        payload = {
            'username': 'anothervendor',
            'first_name': 'Another',
            'last_name': 'Vendor',
            'email': 'existingvendor@example.com',
            'phone': '0700000003',
            'password': 'SecurePass123',
        }

        response = self.client.post(self.url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.data)

class CustomerLoginTests(APITestCase):
    url = reverse('customer-login')

    def setUp(self):
        self.password = 'SecurePass123'

        self.customer = User.objects.create_user(
            username='logincustomer',
            email='logincustomer@example.com',
            password=self.password,
            role=User.Role.CUSTOMER,
        )

    def test_customer_can_login(self):
        payload = {
            'email': self.customer.email,
            'password': self.password,
        }

        response = self.client.post(self.url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

    def test_customer_cannot_login_with_wrong_password(self):
        payload = {
            'email': self.customer.email,
            'password': 'WrongPassword123',
        }

        response = self.client.post(self.url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('non_field_errors', response.data)

    def test_vendor_cannot_use_customer_login(self):
        vendor = User.objects.create_user(
            username='loginvendor',
            email='loginvendor@example.com',
            password=self.password,
            role=User.Role.VENDOR,
        )

        payload = {
            'email': vendor.email,
            'password': self.password,
        }

        response = self.client.post(self.url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('non_field_errors', response.data)


class VendorLoginTests(APITestCase):
    url = reverse('vendor-login')

    def setUp(self):
        self.password = 'SecurePass123'

        self.vendor = User.objects.create_user(
            username='loginvendor',
            email='loginvendor@example.com',
            password=self.password,
            role=User.Role.VENDOR,
        )

    def test_vendor_can_login(self):
        payload = {
            'email': self.vendor.email,
            'password': self.password,
        }

        response = self.client.post(self.url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

    def test_vendor_cannot_login_with_wrong_password(self):
        payload = {
            'email': self.vendor.email,
            'password': 'WrongPassword123',
        }

        response = self.client.post(self.url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('non_field_errors', response.data)

    def test_customer_cannot_use_vendor_login(self):
        customer = User.objects.create_user(
            username='customervendorlogin',
            email='customervendorlogin@example.com',
            password=self.password,
            role=User.Role.CUSTOMER,
        )

        payload = {
            'email': customer.email,
            'password': self.password,
        }

        response = self.client.post(self.url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('non_field_errors', response.data)


class LogoutTests(APITestCase):
    url = reverse('logout')

    def setUp(self):
        self.user = User.objects.create_user(
            username='logoutuser',
            email='logoutuser@example.com',
            password='SecurePass123',
            role=User.Role.CUSTOMER,
        )

        self.refresh_token = RefreshToken.for_user(self.user)

    def test_user_can_logout_with_valid_refresh_token(self):
        payload = {
            'refresh': str(self.refresh_token),
        }

        response = self.client.post(self.url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data['detail'],
            'Successfully logged out.',
        )

    def test_blacklisted_refresh_token_cannot_be_used_again(self):
        refresh_token = str(self.refresh_token)

        self.client.post(
            self.url,
            {'refresh': refresh_token},
            format='json',
        )

        response = self.client.post(
            self.url,
            {'refresh': refresh_token},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('non_field_errors', response.data)