from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from businesses.models import Business, BusinessCategory
from categories.models import Category

DAYS = (
    'monday',
    'tuesday',
    'wednesday',
    'thursday',
    'friday',
    'saturday',
    'sunday',
)


def make_hours():
    return {
        day: {'is_open': True, 'open': '09:00', 'close': '17:00'}
        for day in DAYS
    }


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
        self.category = Category.objects.create(
            name='Pet Grooming', kind=Category.Kind.MERCHANDISE
        )
        self.payload = {
            'name': 'Pawdigree Pet Care',
            'category': self.category.pk,
            'description': 'Pet grooming and care services.',
            'contact': '+256700123456',
            'email': 'business@example.com',
            'address': 'Plot 10, Example Road',
            'city_district': 'Kampala',
            'business_type': 'PRODUCT_SELLER',
            'business_hours': make_hours(),
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

        business = Business.objects.get()
        self.assertEqual(business.vendor, self.vendor)
        self.assertEqual(
            business.verification_status,
            Business.VerificationStatus.DRAFT,
        )
        self.assertTrue(
            BusinessCategory.objects.filter(
                business=business,
                category=self.category,
            ).exists()
        )

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
                'name': 'Pawdigree Veterinary Clinic',
                'email': 'clinic@example.com',
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
            {'name': 'Incomplete Business'},
            format='json',
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(Business.objects.count(), 0)

    def test_category_must_match_registered_business_type(self):
        self.client.force_authenticate(user=self.vendor)
        incompatible = Category.objects.create(
            name='Dogs', kind=Category.Kind.PETS
        )

        response = self.client.post(
            self.url,
            {**self.payload, 'category': incompatible.pk},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('category', response.data)
        self.assertEqual(Business.objects.count(), 0)

    def test_vendor_is_assigned_as_owner_and_hours_are_saved(self):
        self.client.force_authenticate(user=self.vendor)
        payload = {
            **self.payload,
            'vendor': self.other_vendor.pk,
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
        self.assertEqual(business.business_hours, make_hours())

    def test_incomplete_business_hours_are_rejected(self):
        self.client.force_authenticate(user=self.vendor)
        hours = make_hours()
        del hours['sunday']

        response = self.client.post(
            self.url,
            {**self.payload, 'business_hours': hours},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Business.objects.count(), 0)
