from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Business, BusinessHours, User


class BusinessRegistrationAPITests(APITestCase):
    def setUp(self):
        self.url = reverse('business-register')
        self.vendor = User.objects.create_user(
            username='vendor1',
            email='vendor1@example.com',
            password='TestPass123!Secure',
            role=User.Role.VENDOR,
        )
        self.other_vendor = User.objects.create_user(
            username='vendor2',
            email='vendor2@example.com',
            password='TestPass123!Secure',
            role=User.Role.VENDOR,
        )
        self.customer = User.objects.create_user(
            username='customer1',
            email='customer1@example.com',
            password='TestPass123!Secure',
            role=User.Role.CUSTOMER,
        )
        self.payload = {
            'business_name': 'Pawdigree Pet Care',
            'category': 'Pet Grooming',
            'description': 'Pet grooming and care services.',
            'business_phone': '+256700123456',
            'business_email': 'business@example.com',
            'address': 'Plot 10, Example Road',
            'city_district': 'Kampala',
        }

    def test_vendor_can_register_business(self):
        self.client.force_authenticate(user=self.vendor)

        response = self.client.post(
            self.url,
            self.payload,
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Business.objects.count(), 1)
        self.assertEqual(Business.objects.get().vendor, self.vendor)

    def test_vendor_can_register_multiple_businesses(self):
        self.client.force_authenticate(user=self.vendor)

        first = self.client.post(
            self.url,
            self.payload,
            format='json',
        )
        second = self.client.post(
            self.url,
            {
                **self.payload,
                'business_name': 'Pawdigree Veterinary Clinic',
                'business_email': 'clinic@example.com',
            },
            format='json',
        )

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            Business.objects.filter(vendor=self.vendor).count(),
            2,
        )

    def test_unauthenticated_user_cannot_register(self):
        response = self.client.post(
            self.url,
            self.payload,
            format='json',
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_customer_cannot_register_business(self):
        self.client.force_authenticate(user=self.customer)

        response = self.client.post(
            self.url,
            self.payload,
            format='json',
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(Business.objects.count(), 0)

    def test_missing_required_fields_are_rejected(self):
        self.client.force_authenticate(user=self.vendor)

        response = self.client.post(
            self.url,
            {'business_name': 'Incomplete Business'},
            format='json',
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(Business.objects.count(), 0)

    def test_vendor_is_assigned_as_owner_and_hours_are_saved(self):
        self.client.force_authenticate(user=self.vendor)
        payload = {
            **self.payload,
            'vendor': self.other_vendor.pk,
            'business_hours': [
                {
                    'day': BusinessHours.Day.MONDAY,
                    'is_open': True,
                    'opening_time': '09:00',
                    'closing_time': '17:00',
                },
                {
                    'day': BusinessHours.Day.TUESDAY,
                    'is_open': False,
                },
            ],
        }

        response = self.client.post(
            self.url,
            payload,
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertNotIn('vendor', response.data)
        business = Business.objects.get(pk=response.data['id'])
        self.assertEqual(business.vendor, self.vendor)
        self.assertEqual(
            list(business.business_hours.values_list('day', flat=True)),
            [BusinessHours.Day.MONDAY, BusinessHours.Day.TUESDAY],
        )
        closed_hours = business.business_hours.get(
            day=BusinessHours.Day.TUESDAY,
        )
        self.assertIsNone(closed_hours.opening_time)
        self.assertIsNone(closed_hours.closing_time)

    def test_duplicate_business_hours_days_are_rejected(self):
        self.client.force_authenticate(user=self.vendor)
        payload = {
            **self.payload,
            'business_hours': [
                {
                    'day': BusinessHours.Day.MONDAY,
                    'is_open': True,
                    'opening_time': '09:00',
                    'closing_time': '17:00',
                },
                {
                    'day': BusinessHours.Day.MONDAY,
                    'is_open': True,
                    'opening_time': '10:00',
                    'closing_time': '18:00',
                },
            ],
        }

        response = self.client.post(
            self.url,
            payload,
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Business.objects.count(), 0)